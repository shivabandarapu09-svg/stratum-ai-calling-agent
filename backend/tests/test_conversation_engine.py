import pytest
from app.database import SessionLocal, init_db
from app.models import Call
from app.voice.conversation_engine import VoiceConversationSession
from app.ai.llm_providers import MockLLMProvider
from app.ai.tts_providers import MockTTSProvider

def _run_coro_sync(coro):
    """Run a pure coroutine without creating OS loopback sockets."""
    try:
        while True:
            coro.send(None)
    except StopIteration as e:
        return e.value

@pytest.fixture(scope="module")
def setup_db():
    init_db()
    db = SessionLocal()
    yield db
    db.close()

def test_conversation_flow(setup_db):
    db = setup_db
    call = db.query(Call).first()
    assert call is not None

    session = VoiceConversationSession(
        call_id=call.id,
        db=db,
        llm=MockLLMProvider(),
        tts=MockTTSProvider()
    )

    # 1. Test Hindi inquiry about pricing
    turn_res = _run_coro_sync(session.process_user_utterance("नमस्ते, फ्लैट्स की प्राइसिंग क्या शुरू हो रही है?"))
    assert turn_res["detected_language"] == "hi"
    assert turn_res["is_transfer"] == False
    assert len(turn_res["ai_text"]) > 10
    assert turn_res["audio_bytes"] is not None
    assert "conversation_stage" in turn_res
    assert "emotion" in turn_res

    # 2. Test English code-switching inquiry & mid-call WhatsApp tool execution
    turn_en = _run_coro_sync(session.process_user_utterance("Can you please send me the brochure on WhatsApp?"))
    assert turn_en["detected_language"] == "en"
    assert session.whatsapp_triggered == True
    assert len(turn_en["tool_calls"]) >= 1

    # 3. Test Human transfer request
    turn_trans = _run_coro_sync(session.process_user_utterance("I want to speak with a human manager right now"))
    assert turn_trans["is_transfer"] == True
    assert session.is_transferred == True

    # 4. Finalize call
    session.complete_call()
    assert call.status == "transferred"
    assert call.summary is not None
    assert call.summary.outcome == "Human Transfer"
    assert "budget" in call.summary.bant_score
