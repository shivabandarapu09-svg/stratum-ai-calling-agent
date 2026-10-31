import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.config import settings
from app.models import Call, Agent, Customer, CallTranscriptTurn, CallSummary, Organization, User
from app.security import get_current_user, create_call_ticket
from app.schemas import CallInitiateRequest, CallOut, CallDetailOut
from app.telephony.web_simulator_provider import get_telephony_provider
from app.voice.conversation_engine import VoiceConversationSession

router = APIRouter(prefix="/calls", tags=["Calls"])

def utc_now():
    return datetime.now(timezone.utc)

@router.post("/initiate", response_model=CallDetailOut)
async def initiate_call(req: CallInitiateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = db.query(Agent).filter(Agent.id == req.agent_id, Agent.organization_id == user.organization_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    org_id = agent.organization_id
    if not org_id:
        first_org = db.query(Organization).first()
        org_id = first_org.id if first_org else "org-stratum-global-001"

    # Find or create customer scoped to the agent's organization
    customer = (
        db.query(Customer)
        .filter(Customer.phone == req.customer_phone, Customer.organization_id == org_id)
        .first()
    )
    if not customer:
        customer = Customer(
            organization_id=org_id,
            name=req.customer_name or "New Caller",
            phone=req.customer_phone,
            preferred_language=req.preferred_language or agent.default_language or "hi",
            status="Lead"
        )
        db.add(customer)
        db.flush()

    call_id = str(uuid.uuid4())
    public_base = settings.get_public_base_url()

    # Pre-flight validation for Twilio PSTN calls: prevent placeholder / unreachable tunnels from triggering Twilio "check the URL" errors
    if req.provider == "twilio" and not req.twilio_trial_mode:
        if not public_base:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Public Webhook URL is missing. Twilio PSTN requires an active public HTTPS URL "
                    "(e.g., https://your-id.ngrok-free.app or your production domain) so Twilio can connect "
                    "the call to Stratum's AI voice engine. Configure PUBLIC_BASE_URL in Settings or Integrations, "
                    "or check 'Twilio Free-Trial Connectivity Check' for static testing."
                )
            )
        if any(ph in public_base.lower() for ph in ["your-domain", "example.com", "localhost", "127.0.0.1"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid Public Webhook URL '{public_base}'. This is a placeholder domain that Twilio cannot reach. "
                    "Please configure your active public HTTPS tunnel URL (e.g. from ngrok or your cloud domain) "
                    "in Settings or Integrations before initiating real telephone calls."
                )
            )

    status_callback_url = ""
    if public_base and not req.twilio_trial_mode:
        callback_url = settings.get_public_http_url(f"/api/telephony/twilio/twiml/{call_id}")
        status_callback_url = settings.get_public_http_url(f"/api/telephony/twilio/status/{call_id}")
    else:
        callback_url = f"/api/telephony/twilio/twiml/{call_id}"

    # Telephony invocation
    provider = get_telephony_provider(req.provider)
    caller_from = None if req.provider == "twilio" else (agent.transfer_number or "+919876543210")
    try:
        tele_res = await provider.initiate_call(
            to_phone=req.customer_phone,
            from_phone=caller_from,
            callback_url=callback_url,
            metadata={
                "twilio_trial_mode": req.twilio_trial_mode,
                "status_callback_url": status_callback_url,
                "call_id": call_id,
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Telephony Dialing Error: {str(e)}"
        )

    provider_status = str(tele_res.get("status", "in_progress")).lower()
    if req.provider in ("twilio", "exotel") and provider_status in ("queued", "initiated", "ringing"):
        initial_status = "ringing"
    else:
        initial_status = "in_progress"

    # Create Call entity
    call = Call(
        id=call_id,
        organization_id=org_id,
        agent_id=agent.id,
        customer_id=customer.id,
        customer_phone=req.customer_phone,
        direction="outbound",
        status=initial_status,
        primary_language=req.preferred_language or agent.default_language or "hi",
        languages_detected=[req.preferred_language or agent.default_language or "hi"],
        provider_call_id=tele_res.get("provider_call_id"),
        telephony_provider=req.provider or "web_simulator",
        started_at=utc_now()
    )
    db.add(call)
    db.flush()

    # Add initial company-specific greeting turn to transcripts
    session_tmp = VoiceConversationSession(call_id=call.id, db=db)
    greeting_text, _ = session_tmp.get_greeting()
    greeting_turn = CallTranscriptTurn(
        call_id=call.id,
        speaker="agent",
        text=greeting_text,
        language=call.primary_language,
        latency_ms=100,
        timestamp=utc_now()
    )
    db.add(greeting_turn)
    db.commit()
    db.refresh(call)

    # Format response
    return CallDetailOut(
        id=call.id,
        agent_id=call.agent_id,
        agent_name=agent.name,
        company_name=agent.company,
        customer_id=customer.id,
        customer_name=customer.name,
        customer_phone=call.customer_phone,
        direction=call.direction,
        status=call.status,
        telephony_provider=call.telephony_provider or "web_simulator",
        duration_seconds=call.duration_seconds,
        primary_language=call.primary_language,
        languages_detected=call.languages_detected or [],
        recording_url=call.recording_url,
        cost_estimate=call.cost_estimate,
        started_at=call.started_at,
        ended_at=call.ended_at,
        transcripts=[greeting_turn],
        summary=None,
        ws_ticket=create_call_ticket(call.id, org_id),
    )

@router.get("", response_model=List[CallOut])
def list_calls(
    language: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Call).filter(Call.organization_id == user.organization_id).order_by(Call.started_at.desc())
    if language:
        query = query.filter(Call.primary_language == language)
    if status_filter:
        query = query.filter(Call.status == status_filter)

    calls = query.limit(50).all()

    result = []
    for c in calls:
        agent_name = c.agent.name if c.agent else "Stratum SDR"
        company_name = c.agent.company if c.agent else "Stratum Enterprise"
        cust_name = c.customer.name if c.customer else "Caller"
        result.append(CallOut(
            id=c.id,
            agent_id=c.agent_id,
            agent_name=agent_name,
            company_name=company_name,
            customer_id=c.customer_id,
            customer_name=cust_name,
            customer_phone=c.customer_phone,
            direction=c.direction,
            status=c.status,
            telephony_provider=c.telephony_provider or "web_simulator",
            duration_seconds=c.duration_seconds,
            primary_language=c.primary_language,
            languages_detected=c.languages_detected or [],
            recording_url=c.recording_url,
            cost_estimate=c.cost_estimate,
            started_at=c.started_at,
            ended_at=c.ended_at,
            summary=c.summary
        ))
    return result

@router.get("/{call_id}", response_model=CallDetailOut)
def get_call_detail(call_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    call = db.query(Call).filter(Call.id == call_id, Call.organization_id == user.organization_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    agent_name = call.agent.name if call.agent else "Stratum SDR"
    company_name = call.agent.company if call.agent else "Stratum Enterprise"
    cust_name = call.customer.name if call.customer else "Caller"

    return CallDetailOut(
        id=call.id,
        agent_id=call.agent_id,
        agent_name=agent_name,
        company_name=company_name,
        customer_id=call.customer_id,
        customer_name=cust_name,
        customer_phone=call.customer_phone,
        direction=call.direction,
        status=call.status,
        telephony_provider=call.telephony_provider or "web_simulator",
        duration_seconds=call.duration_seconds,
        primary_language=call.primary_language,
        languages_detected=call.languages_detected or [],
        recording_url=call.recording_url,
        cost_estimate=call.cost_estimate,
        started_at=call.started_at,
        ended_at=call.ended_at,
        transcripts=call.transcripts,
        summary=call.summary,
        ws_ticket=create_call_ticket(call.id, call.organization_id),
    )

@router.post("/{call_id}/terminate")
async def terminate_call(call_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    call = db.query(Call).filter(Call.id == call_id, Call.organization_id == user.organization_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    if call.telephony_provider == "twilio" and call.provider_call_id:
        try:
            provider = get_telephony_provider("twilio")
            await provider.terminate_call(call.provider_call_id)
        except Exception:
            pass

    try:
        session = VoiceConversationSession(call_id=call_id, db=db)
        session.complete_call(final_status="completed")
    except Exception:
        call.status = "completed"
        call.ended_at = utc_now()
        if call.started_at:
            end_t = call.ended_at
            start_t = call.started_at
            call.duration_seconds = max(int(abs((end_t.replace(tzinfo=None) - start_t.replace(tzinfo=None)).total_seconds())), 1)
        db.commit()
    return {"status": "success", "message": "Call terminated and summary generated"}
