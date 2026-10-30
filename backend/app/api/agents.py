import base64
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Agent, Organization
from app.schemas import AgentCreate, AgentUpdate, AgentOut, VoicePreviewRequest
from app.config import settings
from app.ai.tts_providers import get_tts_provider

router = APIRouter(prefix="/agents", tags=["Agents"])

@router.get("", response_model=List[AgentOut])
def list_agents(db: Session = Depends(get_db)):
    agents = db.query(Agent).all()
    return agents

@router.get("/voices/available")
def get_available_voices():
    """Return dictionary of available Indian neural voices & personas per language."""
    return settings.DEFAULT_VOICES

@router.post("/voices/preview")
async def preview_voice(req: VoicePreviewRequest):
    """
    Synthesize a live neural voice sample so users can audition voice personas
    (pitch, speed, language, Hinglish warmth) directly in the Stratum Studio.
    """
    default_samples = {
        "hi": "नमस्ते जी! मैं स्ट्रैटम एआई से बात कर रही हूँ। बताइए, आज मैं आपकी किस प्रकार मदद कर सकती हूँ?",
        "en": "Hi there! This is Stratum AI calling on a live neural voice line. Do you have a quick minute to chat?",
        "te": "నమస్కారం అండి! నేను స్ట్రాటమ్ ఏఐ నుండి మాట్లాడుతున్నాను. మీకు ఏ విధంగా సహాయం చేయగలను?",
        "ta": "வணக்கம்! நான் ஸ்ட்ராட்டம் ஏஐ-யிலிருந்து பேசுகிறேன். உங்களுக்கு எப்படி உதவலாம்?"
    }
    sample_text = req.text or default_samples.get(req.language, default_samples["hi"])
    tts = get_tts_provider()
    audio_bytes, dur_ms = await tts.synthesize(
        text=sample_text,
        language=req.language,
        voice_id=req.voice_id,
        speaking_speed=req.speaking_speed,
        pitch=req.pitch
    )
    aud_b64 = base64.b64encode(audio_bytes).decode("utf-8") if audio_bytes else None
    return {
        "voice_id": req.voice_id,
        "language": req.language,
        "text": sample_text,
        "audio_base64": aud_b64,
        "synthesis_latency_ms": dur_ms
    }

@router.get("/blueprints/templates")
def get_blueprint_templates():
    """Return pre-configured Stratum industry blueprints for instant AI employee deployment."""
    return [
        {
            "blueprint": "real_estate",
            "title": "Real Estate Luxury SDR",
            "description": "Qualifies homebuyers in colloquial Hinglish/English, handles price objections with rental yields, and books weekend VIP site visits.",
            "default_company": "Prestige & Godrej Luxury Living",
            "default_language": "hi",
            "voice_id": "hi-IN-MadhurNeural",
            "qualification_framework": "BANT",
            "suggested_questions": [
                "Are you exploring a 3 BHK or 4 BHK configuration for your family?",
                "What is your comfortable budget bracket?",
                "Are you evaluating this for self-use or long-term rental yield?",
                "Can I lock in your VIP site visit for this Saturday at 11:00 AM?"
            ]
        },
        {
            "blueprint": "clinic_healthcare",
            "title": "Healthcare & Clinic AI Receptionist",
            "description": "Empathetic 24/7 patient triage, specialist doctor appointment booking, tele-consultations, and instant WhatsApp clinic tokens.",
            "default_company": "Apollo & Aster Multi-Specialty Clinics",
            "default_language": "en",
            "voice_id": "en-IN-NeerjaNeural",
            "qualification_framework": "APPOINTMENT",
            "suggested_questions": [
                "Which doctor specialty would you like to consult today?",
                "Would you prefer an in-clinic visit or a video consultation from home?",
                "Does tomorrow morning at 10:30 AM work well for your schedule?"
            ]
        },
        {
            "blueprint": "education_admissions",
            "title": "EdTech & Admissions Counselor",
            "description": "Screens working professionals for Executive AI programs, calculates early-bird scholarships & EMI, and books faculty interviews.",
            "default_company": "Stratum Institute of Technology & AI",
            "default_language": "hi",
            "voice_id": "hi-IN-MadhurNeural",
            "qualification_framework": "BANT",
            "suggested_questions": [
                "How many years of work experience do you currently have?",
                "Are you aiming for a career transition into GenAI & Cloud Architecture?",
                "Can I schedule your 15-minute scholarship evaluation call this Thursday at 4 PM?"
            ]
        },
        {
            "blueprint": "ecommerce_cod",
            "title": "E-Commerce COD & RTO Reducer",
            "description": "Eliminates Return-to-Origin losses by verifying Cash on Delivery orders, confirming pin codes, and pitching ₹150 instant UPI discounts.",
            "default_company": "UrbanTrend Lifestyle",
            "default_language": "hi",
            "voice_id": "hi-IN-SwaraNeural",
            "qualification_framework": "ORDER_VERIFY",
            "suggested_questions": [
                "Do you confirm your ₹2,499 order for priority dispatch?",
                "Is your delivery address and pin code accurate?",
                "Would you like an instant ₹150 discount via UPI payment link on WhatsApp?"
            ]
        },
        {
            "blueprint": "b2b_saas_sdr",
            "title": "Stratum B2B Speed-to-Lead SDR",
            "description": "Dials inbound Meta & Google Ads leads in under 5 seconds, discovers monthly call volume & CRM stack, and books live architecture demos.",
            "default_company": "Stratum AI Voice Systems",
            "default_language": "en",
            "voice_id": "en-IN-NeerjaNeural",
            "qualification_framework": "BANT",
            "suggested_questions": [
                "How many inbound leads or outbound calls does your team handle monthly?",
                "Which CRM are you currently using—HubSpot, Zoho, or LeadSquared?",
                "Shall we lock in a 20-minute live architecture demo for Wednesday at 3 PM?"
            ]
        },
        {
            "blueprint": "bfsi_fintech",
            "title": "BFSI & FinTech Credit Advisor",
            "description": "Qualifies pre-approved business & personal credit lines, explains ROI/EMI breakdowns without jargon, and dispatches instant sanction links.",
            "default_company": "Stratum FinServ Capital",
            "default_language": "hi",
            "voice_id": "hi-IN-MadhurNeural",
            "qualification_framework": "BANT",
            "suggested_questions": [
                "What working capital or credit limit bracket are you exploring right now?",
                "Would a 24-month or 36-month flexible EMI tenure suit your cashflow better?",
                "Shall I send the zero-foreclosure sanction breakdown to your WhatsApp?"
            ]
        }
    ]

@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: str, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent

@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(payload: AgentCreate, db: Session = Depends(get_db)):
    org = db.query(Organization).first()
    if not org:
        raise HTTPException(status_code=400, detail="Organization not found")

    agent = Agent(
        organization_id=org.id,
        name=payload.name,
        company=payload.company,
        purpose=payload.purpose,
        blueprint=payload.blueprint,
        personality=payload.personality,
        system_prompt=payload.system_prompt,
        greeting=payload.greeting,
        default_language=payload.default_language,
        supported_languages=payload.supported_languages,
        voice_id=payload.voice_id,
        speaking_speed=payload.speaking_speed,
        voice_pitch=payload.voice_pitch or "+0Hz",
        transfer_number=payload.transfer_number,
        consent_disclosure=payload.consent_disclosure,
        ambient_sound=payload.ambient_sound or "office_call_center",
        backchannel_enabled=payload.backchannel_enabled if payload.backchannel_enabled is not None else True,
        filler_words_enabled=payload.filler_words_enabled if payload.filler_words_enabled is not None else True,
        interruption_sensitivity=payload.interruption_sensitivity or 0.85,
        endpointing_ms=payload.endpointing_ms or 320,
        qualification_framework=payload.qualification_framework,
        qualification_questions=payload.qualification_questions,
        objection_rebuttals=payload.objection_rebuttals,
        whatsapp_template=payload.whatsapp_template,
        webhook_url=payload.webhook_url,
        speed_to_lead_enabled=payload.speed_to_lead_enabled
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent

@router.put("/{agent_id}", response_model=AgentOut)
def update_agent(agent_id: str, payload: AgentUpdate, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(agent, field, val)

    db.commit()
    db.refresh(agent)
    return agent

@router.delete("/{agent_id}")
def delete_agent(agent_id: str, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    db.delete(agent)
    db.commit()
    return {"status": "success", "message": "Agent deleted"}
