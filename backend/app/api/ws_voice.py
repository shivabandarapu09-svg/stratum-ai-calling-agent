import asyncio
import json
import base64
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Call
from app.voice.conversation_engine import VoiceConversationSession
from app.voice.audio_codec import (
    mulaw_to_pcm16,
    pcm16_to_mulaw,
    pcm16_to_wav,
    validate_twilio_media_format,
)
from app.ai.stt_providers import get_stt_provider

router = APIRouter(tags=["WebSocket Voice"])


@router.websocket("/ws/voice/{call_id}")
async def websocket_voice_endpoint(websocket: WebSocket, call_id: str):
    await websocket.accept()
    db: Session = SessionLocal()

    session: VoiceConversationSession = None
    try:
        session = VoiceConversationSession(call_id=call_id, db=db)
    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        await websocket.close()
        db.close()
        return

    stream_sid: str = ""
    twilio_media_buffer = bytearray()
    stt_provider = get_stt_provider()

    # Callback when barge-in occurs
    def handle_barge_in():
        session.tracer.record("barge_in_interrupted", detail="Caller speech interrupted active AI audio")
        if stream_sid:
            asyncio.create_task(
                websocket.send_json({"event": "clear", "streamSid": stream_sid})
            )
        asyncio.create_task(
            websocket.send_json(
                {
                    "type": "barge_in",
                    "message": "AI audio cancelled (<120ms) due to customer speech",
                }
            )
        )

    session.interruption_coordinator.on_barge_in = handle_barge_in

    try:
        # 1. Send initial session ready & company-specific greeting
        greeting_text, lang = session.get_greeting()
        speed = getattr(session.agent, "speaking_speed", 1.04) or 1.04
        pitch = getattr(session.agent, "voice_pitch", "+0Hz") or "+0Hz"

        try:
            greeting_audio = await session.tts.synthesize_speech(
                text=greeting_text,
                language=lang,
                voice_id=session.agent.voice_id,
                speaking_speed=speed,
                pitch=pitch,
            )
            audio_b64 = base64.b64encode(greeting_audio).decode("utf-8") if greeting_audio else None
        except Exception as e:
            print(f"[Stratum Greeting TTS Warning]: {e}")
            audio_b64 = None

        company_name = (
            session.tenant_profile.company_name
            if session.tenant_profile
            else getattr(session.agent, "company", "")
        )

        await websocket.send_json(
            {
                "type": "greeting",
                "session_type": "session_started",
                "call_id": call_id,
                "agent_name": session.agent.name,
                "company_name": company_name,
                "voice_id": session.agent.voice_id,
                "ambient_sound": getattr(session.agent, "ambient_sound", "office_call_center"),
                "language": lang,
                "text": greeting_text,
                "greeting_text": greeting_text,
                "audio": audio_b64,
                "conversation_stage": "1. Hook & Rapport",
                "emotion": "Warm & Welcoming",
                "session_trace": session.tracer.to_list(),
            }
        )

        session.interruption_coordinator.set_ai_speaking(True if audio_b64 else False)

        # 2. Main WebSocket Event Loop (Supports both Browser JSON Protocol & Twilio Media Streams Protocol)
        while True:
            raw_msg = await websocket.receive_text()
            data = json.loads(raw_msg)
            event_type = data.get("type")
            twilio_event = data.get("event")

            # ------------------------------------------------------------------
            # A. Twilio Media Streams Protocol (`connected`, `start`, `media`, `stop`)
            # ------------------------------------------------------------------
            if twilio_event == "connected":
                session.tracer.record("twilio_stream_connected", detail="Twilio Media Stream connected")
                continue

            elif twilio_event == "start":
                start_info = data.get("start") or {}
                stream_sid = start_info.get("streamSid") or data.get("streamSid") or "stream-default"
                fmt_check = validate_twilio_media_format(start_info.get("mediaFormat"))
                session.tracer.record(
                    "twilio_stream_started",
                    detail=f"streamSid={stream_sid}, encoding={fmt_check['encoding']}, rate={fmt_check['sample_rate']}",
                    metadata=fmt_check,
                )
                # Send initial greeting frame in 8kHz mu-law to Twilio stream
                if greeting_audio:
                    mulaw_greeting = pcm16_to_mulaw(greeting_audio[:16000]) or greeting_audio[:8000]
                    await websocket.send_json(
                        {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {"payload": base64.b64encode(mulaw_greeting).decode("utf-8")},
                        }
                    )
                continue

            elif twilio_event == "media":
                media_info = data.get("media") or {}
                payload_b64 = media_info.get("payload", "")
                if payload_b64:
                    mulaw_bytes = base64.b64decode(payload_b64)
                    pcm16 = mulaw_to_pcm16(mulaw_bytes)
                    twilio_media_buffer.extend(pcm16)
                    interrupted = session.interruption_coordinator.handle_incoming_pcm(pcm16)
                    if interrupted and stream_sid:
                        await websocket.send_json({"event": "clear", "streamSid": stream_sid})

                # If an end-of-utterance marker or simulated transcript accompanies the media frame, process turn
                utterance_override = media_info.get("speech_text") or data.get("speech_text")
                flush_utterance = bool(media_info.get("end_of_utterance") or data.get("end_of_utterance"))
                if utterance_override or (flush_utterance and len(twilio_media_buffer) > 0):
                    if utterance_override:
                        spoken_text = str(utterance_override).strip()
                    else:
                        wav_bytes = pcm16_to_wav(bytes(twilio_media_buffer), sample_rate=8000)
                        stt_res = await stt_provider.transcribe_audio(
                            wav_bytes, language_hint=session.current_language
                        )
                        spoken_text = stt_res.get("transcript", "").strip()
                    twilio_media_buffer.clear()

                    if spoken_text:
                        turn_res = await session.process_user_utterance(spoken_text)
                        ai_pcm = turn_res.get("audio_bytes") or b"\x00\x00" * 800
                        mulaw_out = pcm16_to_mulaw(ai_pcm) or b"\xff" * 400
                        await websocket.send_json(
                            {
                                "event": "media",
                                "streamSid": stream_sid or "stream-default",
                                "media": {
                                    "payload": base64.b64encode(mulaw_out).decode("utf-8"),
                                    "ai_text": turn_res.get("ai_text", ""),
                                    "language": turn_res.get("detected_language", session.current_language),
                                    "citations": turn_res.get("citations", []),
                                },
                            }
                        )
                        await websocket.send_json(
                            {
                                "event": "mark",
                                "streamSid": stream_sid or "stream-default",
                                "mark": {"name": "ai_turn_completed"},
                            }
                        )
                continue

            elif twilio_event == "stop":
                session.complete_call(final_status="completed")
                break

            # ------------------------------------------------------------------
            # B. Browser Studio WebSocket Protocol (`utterance`, `audio_chunk`, `barge_in`, `end_call`)
            # ------------------------------------------------------------------
            if event_type in ("ai_audio_finished", "speech_stopped"):
                session.interruption_coordinator.set_ai_speaking(False)

            elif event_type == "barge_in":
                session.interruption_coordinator.set_ai_speaking(False)
                session.tracer.record("barge_in_interrupted", detail="Customer triggered barge-in")
                await websocket.send_json({"type": "barge_in_acknowledged"})

            elif event_type == "audio_chunk":
                raw_b64 = data.get("data", "")
                if raw_b64:
                    pcm = base64.b64decode(raw_b64)
                    interrupted = session.interruption_coordinator.handle_incoming_pcm(pcm)
                    if interrupted:
                        await websocket.send_json(
                            {"type": "barge_in", "message": "Caller interrupted playback"}
                        )

            elif event_type in ("utterance", "user_utterance"):
                user_text = data.get("text", "")
                if not user_text:
                    continue

                session.interruption_coordinator.set_ai_speaking(False)

                try:
                    result = await session.process_user_utterance(user_text)
                except Exception as turn_err:
                    session.tracer.record("error_recovered", detail=str(turn_err))
                    await websocket.send_json(
                        {
                            "type": "ai_response",
                            "text": "I apologize, I experienced a brief audio delay. Could you please repeat that?",
                            "language": session.current_language,
                            "emotion": "Calm & Attentive",
                            "conversation_stage": session.current_stage,
                            "bant_progress": session.bant_progress,
                            "session_trace": session.tracer.to_list(),
                        }
                    )
                    continue

                if not result:
                    continue

                aud_b64 = result.get("audio_base64")
                if not aud_b64:
                    audio_bytes = result.get("audio_bytes", b"")
                    aud_b64 = base64.b64encode(audio_bytes).decode("utf-8") if audio_bytes else None

                session.interruption_coordinator.set_ai_speaking(True if aud_b64 else False)

                await websocket.send_json(
                    {
                        "type": "ai_response",
                        "text": result.get("ai_text"),
                        "language": result.get("detected_language") or result.get("language") or "hi",
                        "is_code_switched": result.get("is_code_switched", False),
                        "audio": aud_b64,
                        "is_transfer": result.get("is_transfer", False),
                        "transfer_number": result.get("transfer_number"),
                        "should_end_call": result.get("should_end_call", False),
                        "whatsapp_triggered": result.get("whatsapp_triggered", False),
                        "meeting_booked": result.get("meeting_booked", False),
                        "emotion": result.get("emotion", "Engaged"),
                        "conversation_stage": result.get("conversation_stage", "2. Need Discovery"),
                        "backchannel_cue": result.get("backchannel_cue"),
                        "tool_calls": result.get("tool_calls", []),
                        "citations": result.get("citations", []),
                        "bant_progress": result.get("bant_progress", {}),
                        "session_trace": result.get("session_trace", []),
                        "metrics": result.get("metrics", {}),
                    }
                )

                if result.get("should_end_call"):
                    session.complete_call(final_status="completed")
                    call_record = db.query(Call).filter(Call.id == call_id).first()
                    summary = call_record.summary if call_record else None
                    await websocket.send_json(
                        {
                            "type": "call_summary",
                            "summary": {
                                "intent": summary.intent if summary else "General",
                                "outcome": summary.outcome if summary else "Completed",
                                "sentiment": summary.sentiment if summary else "Positive",
                                "summary_text": summary.summary_text if summary else "",
                                "qualification_status": getattr(summary, "qualification_status", "Warm"),
                                "bant_score": getattr(summary, "bant_score", {}),
                                "whatsapp_sent": getattr(summary, "whatsapp_sent", False),
                                "meeting_scheduled": getattr(summary, "meeting_scheduled", False),
                                "next_action": getattr(summary, "next_action", ""),
                                "key_information": getattr(summary, "key_information", {}),
                            },
                        }
                    )
                    break

            elif event_type in ("end", "end_call", "terminate"):
                session.complete_call(final_status="completed")
                call_record = db.query(Call).filter(Call.id == call_id).first()
                summary = call_record.summary if call_record else None
                await websocket.send_json(
                    {
                        "type": "call_summary",
                        "summary": {
                            "intent": summary.intent if summary else "General",
                            "outcome": summary.outcome if summary else "Completed",
                            "sentiment": summary.sentiment if summary else "Positive",
                            "summary_text": summary.summary_text if summary else "",
                            "qualification_status": getattr(summary, "qualification_status", "Hot"),
                            "bant_score": getattr(summary, "bant_score", {}),
                            "whatsapp_sent": getattr(summary, "whatsapp_sent", False),
                            "meeting_scheduled": getattr(summary, "meeting_scheduled", False),
                            "next_action": getattr(summary, "next_action", ""),
                            "key_information": getattr(summary, "key_information", {}),
                        },
                    }
                )
                break

    except WebSocketDisconnect:
        print(f"[Stratum WS Disconnected] Call {call_id}")
        if session and session.is_active:
            session.complete_call(final_status="completed")
    except Exception as e:
        print(f"[Stratum WS Error]: {e}")
        if session and session.is_active:
            session.complete_call(final_status="failed")
    finally:
        db.close()
