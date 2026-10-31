import os
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings
from app.models import (
    Base, Organization, User, Agent, KnowledgeDoc, KnowledgeChunk,
    Customer, Call, CallTranscriptTurn, CallSummary, Campaign, CampaignContact,
    InboundLead, TenantWorkspaceProfile, KnowledgeAuditLog
)

connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

from app.passwords import hash_password  # noqa: E402,F401  (bcrypt; re-exported for backwards compatibility)

def utc_now():
    return datetime.now(timezone.utc)

def seed_database(db: Session):
    existing_agent = db.query(Agent).filter(Agent.name == "Aarav").first()
    if existing_agent:
        return

    print("[Stratum DB] Initializing Stratum AI Enterprise Calling Database with 6 Human-Realism Industry Blueprints...")

    # 1. Organization
    org = db.query(Organization).first()
    if not org:
        org = Organization(
            id="org-stratum-global-001",
            name="Stratum AI Enterprise Technologies",
            created_at=utc_now()
        )
        db.add(org)
        db.flush()
    else:
        org.name = "Stratum AI Enterprise Technologies"
        db.commit()

    # 2. Admin User
    admin_password = settings.ADMIN_PASSWORD
    generated_password = False
    if not admin_password:
        admin_password = secrets.token_urlsafe(12)
        generated_password = True
    admin = db.query(User).filter(User.email == settings.ADMIN_EMAIL).first()
    if not admin:
        if generated_password:
            print(
                f"[Stratum DB] Created bootstrap admin '{settings.ADMIN_EMAIL}' with generated password: "
                f"{admin_password}  (shown once - set ADMIN_PASSWORD in .env to choose your own)"
            )
        admin = User(
            id="user-admin-001",
            organization_id=org.id,
            email=settings.ADMIN_EMAIL,
            hashed_password=hash_password(admin_password),
            full_name="Vikramaditya Roy",
            role="superadmin",
            created_at=utc_now()
        )
        db.add(admin)

    # 3. Agent 1: Aarav (Real Estate AI SDR - Luxury Properties)
    aarav = Agent(
        id="agent-aarav-real-estate-001",
        organization_id=org.id,
        name="Aarav",
        company="Prestige & Godrej Luxury Living",
        purpose="Inbound & Outbound Real Estate SDR - VIP Site Visit Booking",
        blueprint="real_estate",
        personality="Warm, Consultative, Persuasive & Colloquial Hinglish",
        system_prompt="""You are Aarav, a senior luxury real estate advisor for Prestige & Godrej Luxury Living, powered by Stratum AI.
Your mission is to have a warm, human-like phone conversation with prospects who inquired about 'Prestige Sky Meadows' in Gachibowli / Financial District.
Project Facts:
- 3 BHK (2,400 sq.ft) starting at ₹2.15 Crores.
- 4 BHK (3,650 sq.ft) starting at ₹3.45 Crores.
- 75,000 sq.ft Olympic-grade clubhouse, heated infinity pool, EV bays, 82% open landscaped greens.
- Possession: Ready for fit-outs by March 2027 (RERA approved).

Human Conversation Rules:
1. Speak in natural spoken Hinglish/English with conversational empathy openers ("हाँ जी, बिल्कुल—", "अच्छा सवाल है आपका!").
2. Discover configuration (3 or 4 BHK), comfortable budget, and whether it's for family self-use or rental yield.
3. Rebut price objections warmly using Financial District's 7-8% rental yield and Mivan construction quality.
4. Dispatch floor plans on WhatsApp mid-call and lock a Saturday or Sunday 11:00 AM VIP site visit.""",
        greeting="नमस्ते जी! मैं प्रेस्टीज लक्ज़री हाइट्स से आरव बोल रहा हूँ। आपने अभी हमारे गचीबोवली 3 और 4 BHK लक्ज़री होम्स के बारे में पूछा था—क्या अभी बात करने का सही समय है?",
        default_language="hi",
        supported_languages=["hi", "en", "te"],
        voice_id="hi-IN-MadhurNeural",
        speaking_speed=1.05,
        voice_pitch="+0Hz",
        ambient_sound="office_call_center",
        backchannel_enabled=True,
        filler_words_enabled=True,
        interruption_sensitivity=0.85,
        endpointing_ms=300,
        transfer_number="+919876543210",
        consent_disclosure="This call is recorded by Stratum AI for quality and verification purposes.",
        qualification_framework="BANT",
        qualification_questions=[
            "Are you exploring a 3 BHK or 4 BHK layout for your family?",
            "What is your comfortable budget bracket for the property?",
            "Are you planning to move in with family or looking at rental yield?",
            "Shall I lock in an exclusive VIP site visit for you this Saturday at 11 AM?"
        ],
        objection_rebuttals=[
            {"objection": "Price is too high", "rebuttal": "हाँ जी, मैं बिल्कुल समझ सकता हूँ! गचीबोवली फाइनेंशियल डिस्ट्रिक्ट में 82% ओपन ग्रीनरी और 7-8% रेंटल यील्ड की वजह से यहाँ सालाना 14% एप्रिसिएशन मिल रहा है।"},
            {"objection": "Send details on WhatsApp", "rebuttal": "लीजिए, मैंने अभी आपके व्हाट्सएप नंबर पर पूरा फ्लोर प्लान और प्राइस शीट भेज दिया है! क्या शनिवार सुबह 11 बजे एक छोटा सा विजिट स्लॉट भी ब्लॉक कर दूँ?"}
        ],
        whatsapp_template="Hi {name}! Thanks for speaking with Aarav. View your exclusive Prestige Sky Meadows 3&4 BHK floor plans & price sheet here: https://stratum.ai/p/prestige-sky",
        webhook_url="https://crm.stratum.ai/api/v1/leads/sync",
        speed_to_lead_enabled=True,
        is_active=True,
        created_at=utc_now()
    )
    db.add(aarav)

    # Agent 2: Priya (Healthcare & Clinic AI Receptionist)
    priya = Agent(
        id="agent-priya-healthcare-002",
        organization_id=org.id,
        name="Priya",
        company="Apollo & Aster Multi-Specialty Clinics",
        purpose="24/7 Patient Care Coordinator, Doctor Appointments & Triage",
        blueprint="clinic_healthcare",
        personality="Empathetic, Calm, Reassuring & Attentive",
        system_prompt="""You are Priya, the Patient Care Coordinator for Apollo & Aster Multi-Specialty Clinics, powered by Stratum AI.
Your role is to warmly assist callers with specialist doctor appointments, clinic timings, and tele-consultations.
Specialties: Cardiology, Pediatrics, Orthopedics, General Medicine, and Dermatology.
Consultation fee: ₹800 in-clinic (includes 1 free follow-up within 7 days), ₹600 video consultation.
Clinic hours: Monday to Saturday, 8:00 AM to 8:30 PM.
Rules:
- Speak with genuine warmth and reassurance ("Sure thing, I'd be glad to help with that!").
- Never provide formal medical diagnosis or prescribe medication.
- For acute symptoms (chest pain, breathing difficulty), advise immediate visit to 24/7 Emergency/Trauma.
- Confirm preferred time slot and send zero-wait digital clinic token on WhatsApp.""",
        greeting="Hello, good day! This is Priya from Apollo & Aster Clinics. Thank you for reaching out—how can I help you with doctor appointments or specialist timings today?",
        default_language="en",
        supported_languages=["en", "hi", "ta", "te"],
        voice_id="en-IN-NeerjaNeural",
        speaking_speed=1.02,
        voice_pitch="+0Hz",
        ambient_sound="executive_room",
        backchannel_enabled=True,
        filler_words_enabled=True,
        interruption_sensitivity=0.88,
        endpointing_ms=320,
        transfer_number="+919876543211",
        consent_disclosure="This call is recorded by Stratum Healthcare AI for clinical quality assurance.",
        qualification_framework="APPOINTMENT",
        qualification_questions=[
            "Which department or senior specialist would you like to consult?",
            "Would you be more comfortable coming into the clinic or doing a video consultation?",
            "Does tomorrow morning at 10:30 AM work well for your schedule?",
            "Shall I send your zero-wait digital clinic pass on WhatsApp?"
        ],
        objection_rebuttals=[
            {"objection": "Doctor fees are high", "rebuttal": "Right, I understand! Our senior consultants have over 15 years of clinical experience, and the ₹800 fee actually includes a complimentary follow-up visit within 7 days."},
            {"objection": "Is emergency care available", "rebuttal": "Yes, our 24/7 Emergency and Cardiac Trauma center is open right now with zero waiting time."}
        ],
        whatsapp_template="Dear {name}, your appointment at Apollo & Aster Clinics is confirmed for tomorrow at 10:30 AM. Digital token: https://stratum.ai/appt/token-882",
        webhook_url="https://his.apollo.com/webhooks/appointments",
        speed_to_lead_enabled=True,
        is_active=True,
        created_at=utc_now()
    )
    db.add(priya)

    # Agent 3: Rohan (EdTech & Admissions AI Counselor)
    rohan = Agent(
        id="agent-rohan-education-003",
        organization_id=org.id,
        name="Rohan",
        company="Stratum Institute of AI & Executive Management",
        purpose="Executive Admissions Counselor & Scholarship Evaluator",
        blueprint="education_admissions",
        personality="Inspiring, Friendly, Mentor-like & Articulate",
        system_prompt="""You are Rohan, Senior Admissions Mentor at Stratum Institute of Technology & AI.
You are speaking with working professionals who inquired about the 'Executive Post-Graduate Program in Generative AI & Cloud Architecture' (in partnership with IIT faculty).
Program Details:
- 9-month weekend live online program designed for working professionals.
- Eligibility: 2+ years tech/engineering or analytical experience.
- Fee: ₹2,45,000 (Early-bird scholarship up to ₹50,000 this week + 0% no-cost EMI from ₹16,250/month).
- Outcomes: 100% placement & career transition support across Microsoft, Amazon, Swiggy, and Tier-1 AI labs.
Speak like an encouraging mentor in natural Hinglish/English.""",
        greeting="नमस्ते जी! मैं स्ट्रैटम इंस्टीट्यूट ऑफ एआई से रोहन बात कर रहा हूँ। आपने हमारे IIT-पार्टनर्ड एग्जीक्यूटिव GenAI प्रोग्राम का ब्रोशर डाउनलोड किया था—कैसे हैं आप, क्या अभी 2 मिनट बात हो सकती है?",
        default_language="hi",
        supported_languages=["hi", "en"],
        voice_id="hi-IN-MadhurNeural",
        speaking_speed=1.05,
        voice_pitch="+0Hz",
        ambient_sound="office_call_center",
        backchannel_enabled=True,
        filler_words_enabled=True,
        interruption_sensitivity=0.85,
        endpointing_ms=320,
        transfer_number="+919876543212",
        consent_disclosure="This call is recorded by Stratum AI for educational admissions standards.",
        qualification_framework="BANT",
        qualification_questions=[
            "How many years of work experience do you currently have?",
            "Are you looking for a salary jump or transitioning into GenAI Architecture?",
            "Are weekend live classes comfortable alongside your current job?",
            "Shall I lock in your 15-minute scholarship interview with our Academic Director this Thursday?"
        ],
        whatsapp_template="Hi {name}, here is your IIT-partnered Executive GenAI curriculum & scholarship breakdown: https://stratum.ai/edu/syllabus-2026",
        speed_to_lead_enabled=True,
        is_active=True,
        created_at=utc_now()
    )
    db.add(rohan)

    # Agent 4: Neha (E-Commerce COD & Order Verification)
    neha = Agent(
        id="agent-neha-ecommerce-004",
        organization_id=org.id,
        name="Neha",
        company="UrbanTrend Fashion & Lifestyle",
        purpose="Cash on Delivery Order Verification & Instant Prepaid Conversion",
        blueprint="ecommerce_cod",
        personality="Lively, Cheerful, Crisp & Helpful",
        system_prompt="""You are Neha, the Customer Order Specialist for UrbanTrend Fashion & Lifestyle, powered by Stratum AI.
Your goal is to verify Cash on Delivery orders quickly and warmly to eliminate RTO losses:
1. Confirm customer placed the ₹2,499 order (Italian Leather Handbag + Wallet combo).
2. Confirm delivery address and pin code for 3-day priority dispatch.
3. Offer a flat ₹150 instant cashback/discount if they switch to UPI prepaid via WhatsApp link right now.""",
        greeting="हेलो जी नमस्ते! मैं अर्बन ट्रेंड फैशन से नेहा बोल रही हूँ। आपने अभी हमारी ऐप पर ₹2,499 का कैश ऑन डिलीवरी आर्डर प्लेस किया था—मैं बस आज ही प्रायोरिटी डिस्पैच के लिए आपका आर्डर कन्फर्म कर रही थी!",
        default_language="hi",
        supported_languages=["hi", "en"],
        voice_id="hi-IN-SwaraNeural",
        speaking_speed=1.06,
        voice_pitch="+2Hz",
        ambient_sound="office_call_center",
        backchannel_enabled=True,
        filler_words_enabled=True,
        interruption_sensitivity=0.85,
        endpointing_ms=280,
        transfer_number="+919876543213",
        consent_disclosure="This call is recorded by Stratum E-Com verification engine.",
        qualification_framework="ORDER_VERIFY",
        qualification_questions=[
            "Do you confirm this ₹2,499 order for dispatch today?",
            "Is your shipping address and pin code accurate for delivery in 3 days?",
            "Would you like a flat ₹150 instant discount link on WhatsApp to pay via UPI?"
        ],
        whatsapp_template="Order #COD-4421 confirmed! Track your priority shipment or claim ₹150 UPI discount here: https://stratum.ai/track/cod-4421",
        speed_to_lead_enabled=True,
        is_active=True,
        created_at=utc_now()
    )
    db.add(neha)

    # Agent 5: Kavya (Stratum Speed-to-Lead B2B SaaS SDR)
    kavya = Agent(
        id="agent-kavya-b2b-saas-005",
        organization_id=org.id,
        name="Kavya",
        company="Stratum AI Voice Systems",
        purpose="Enterprise B2B SaaS Inbound Speed-to-Lead SDR",
        blueprint="b2b_saas_sdr",
        personality="Sharp, Polished, Conversational & Executive",
        system_prompt="""You are Kavya, Senior Growth SDR at Stratum AI (stratum.ai).
Stratum AI is the next-generation hyper-realistic multilingual AI calling platform that combines:
- Sub-5-second Speed-to-Lead auto-dialing for Meta Ads, Google Ads, and IndiaMART leads.
- Indistinguishable human voice realism with backchanneling, office ambience, and <120ms barge-in suppression.
- Colloquial mid-sentence code-switching across 10 Indian languages (Hinglish, Tenglish, Tanglish, Indian English).
- Live mid-call tool execution (WhatsApp collateral dispatch, Calendar booking, CRM sync, SIP transfer).
- Usage pricing starting at ₹4.50/min with built-in TRAI 9AM-8PM compliance.
Qualify marketing and sales leaders on monthly lead volume and CRM stack, and book a 20-minute live architecture demo.""",
        greeting="Hi there! This is Kavya calling from Stratum AI. I noticed you were checking out our hyper-realistic multilingual voice agents—do you have a quick minute to see how we dial and qualify inbound leads in under 5 seconds?",
        default_language="en",
        supported_languages=["en", "hi", "te"],
        voice_id="en-IN-NeerjaNeural",
        speaking_speed=1.04,
        voice_pitch="+0Hz",
        ambient_sound="office_call_center",
        backchannel_enabled=True,
        filler_words_enabled=True,
        interruption_sensitivity=0.90,
        endpointing_ms=300,
        transfer_number="+917810068682",
        consent_disclosure="This call is recorded by Stratum AI Enterprise calling platform.",
        qualification_framework="BANT",
        qualification_questions=[
            "Roughly how many inbound leads or outbound calls does your team handle each month?",
            "Which CRM or lead sources are you currently running—Meta Ads, Google Ads, or HubSpot/Zoho?",
            "What is your target timeline to automate your first calling workflow?",
            "Shall we lock in a 20-minute live screen-share demo for this Wednesday at 3 PM?"
        ],
        whatsapp_template="Hi {name}, great speaking with you! Explore the Stratum AI Enterprise Architecture deck & live voice samples: https://stratum.ai/enterprise-deck",
        webhook_url="https://api.stratum.ai/v1/crm/leads",
        speed_to_lead_enabled=True,
        is_active=True,
        created_at=utc_now()
    )
    db.add(kavya)

    # Agent 6: Kabir (BFSI & FinTech Pre-Approved Credit Advisor)
    kabir = Agent(
        id="agent-kabir-bfsi-006",
        organization_id=org.id,
        name="Kabir",
        company="Stratum FinServ Capital",
        purpose="Pre-Approved Working Capital & Credit Line Advisor",
        blueprint="bfsi_fintech",
        personality="Trustworthy, Crisp, Articulate & Consultative",
        system_prompt="""You are Kabir, Senior Credit & Wealth Advisor at Stratum FinServ Capital.
You are speaking with business owners and salaried executives eligible for a pre-approved ₹25 Lakh credit line at 10.75% p.a. with zero foreclosure charges and 2-hour digital disbursal.
Discover their required loan bracket, preferred tenure (12-48 months), and dispatch the sanction breakdown on WhatsApp.""",
        greeting="नमस्ते! मैं स्ट्रैटम फिनसर्व कैपिटल से कबीर बोल रहा हूँ। आपके शानदार ट्रैक रिकॉर्ड के आधार पर ₹25 लाख तक की प्री-अप्रूव्ड क्रेडिट लाइन 10.75% ब्याज दर पर एक्टिवेट हुई है—क्या मैं आपको 30 सेकंड में इसकी डिटेल्स बता सकता हूँ?",
        default_language="hi",
        supported_languages=["hi", "en"],
        voice_id="hi-IN-MadhurNeural",
        speaking_speed=1.04,
        voice_pitch="+0Hz",
        ambient_sound="executive_room",
        backchannel_enabled=True,
        filler_words_enabled=True,
        interruption_sensitivity=0.85,
        endpointing_ms=310,
        transfer_number="+919876543215",
        consent_disclosure="This call is recorded by Stratum FinServ AI for RBI & quality compliance.",
        qualification_framework="BANT",
        qualification_questions=[
            "What working capital or credit bracket would be most useful for you right now?",
            "Would a 24-month or 36-month flexible EMI plan fit your monthly cashflow best?",
            "Shall I send the zero-foreclosure digital sanction sheet to your WhatsApp right now?"
        ],
        whatsapp_template="Hi {name}, view your pre-approved ₹25L @ 10.75% p.a. Stratum FinServ sanction breakdown: https://stratum.ai/finserv/sanction",
        speed_to_lead_enabled=True,
        is_active=True,
        created_at=utc_now()
    )
    db.add(kabir)

    db.flush()

    # 4. Knowledge Base for Real Estate & Stratum Platform
    kd1 = KnowledgeDoc(
        id="kd-prestige-luxury-001",
        organization_id=org.id,
        agent_id=aarav.id,
        title="Prestige Sky Meadows - Master Property Fact Sheet & FAQs",
        source_type="faq",
        content="""Project: Prestige Sky Meadows
Location: Financial District, Nanakramguda, Hyderabad (3 mins from ORR Exit)
Towers: 4 Iconic High-Rise Towers (G+42 Floors)
Units: 3 BHK (2,400 sq.ft) and 4 BHK (3,650 sq.ft)
Pricing: 3 BHK starting at ₹2.15 Cr, 4 BHK starting at ₹3.45 Cr + registration/stamp duty
Possession Date: March 2027 (RERA approved: P02400005512)
Amenities: 75,000 sq.ft central clubhouse, heated indoor pool, outdoor infinity pool, squash courts, cricket simulator, banquet hall, 24/7 medical room, rooftop sky lounge
Payment Plans: 20:80 Construction Linked Plan and Subvention scheme with HDFC, SBI & ICICI Bank
Site Visit Timings: 10:00 AM to 6:00 PM daily. Complimentary luxury chauffeur pickup available for scheduled weekend visits.""",
        created_at=utc_now()
    )
    db.add(kd1)

    kd2 = KnowledgeDoc(
        id="kd-stratum-platform-002",
        organization_id=org.id,
        agent_id=kavya.id,
        title="Stratum AI Architecture, Human-Realism & Compliance Guide",
        source_type="txt",
        content="""Stratum AI Platform Specifications:
- Latency: Sub-550ms end-to-end voice roundtrip using streaming pipeline.
- Acoustic Realism: Built-in Web Audio ambient soundscapes (Call Center Floor, Executive Office, Cafe), natural conversational fillers, backchanneling, and <120ms barge-in VAD suppression.
- Multi-Layered Conversation Engine: 5-Stratum progression (1. Hook & Rapport -> 2. Need Discovery -> 3. Grounded Value Pitch -> 4. Objection Resolution -> 5. Action & Commitment).
- Telephony: Carrier abstraction layer supporting Twilio, Exotel, Plivo, and private SIP trunking.
- Speed-to-Lead: Webhook triggered automatic dialing within 4 to 10 seconds of lead submission.
- Indian Languages: Hindi/Hinglish, Indian English, Telugu/Tenglish, Tamil/Tanglish, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi.
- Compliance: Full TRAI calling hours restriction (9:00 AM - 8:00 PM IST), NDNC/DND database scrubber, consent disclosure announcements, and DPDP Act compliance.
- Pricing: ₹4.50/min connected talk-time with zero upfront setup fees.""",
        created_at=utc_now()
    )
    db.add(kd2)

    # 5. Customers
    c1 = Customer(
        id="cust-kalyan-001",
        organization_id=org.id,
        name="Kalyan Varma",
        phone="+919876543210",
        email="kalyan.varma@techsol.in",
        preferred_language="hi",
        status="Qualified",
        tags=["High Net Worth", "3BHK Seeker", "Hot Lead"],
        custom_data={"budget": "₹2.2 Cr", "property": "Prestige Sky Meadows", "source": "Meta Ads"},
        created_at=utc_now() - timedelta(days=2)
    )
    db.add(c1)

    c2 = Customer(
        id="cust-sunita-002",
        organization_id=org.id,
        name="Dr. Sunita Rao",
        phone="+919812345678",
        email="dr.sunita@medicare.org",
        preferred_language="en",
        status="Customer",
        tags=["Healthcare", "Doctor Appt"],
        custom_data={"specialty": "Cardiology", "clinic": "Apollo Gachibowli"},
        created_at=utc_now() - timedelta(days=1)
    )
    db.add(c2)

    c3 = Customer(
        id="cust-amit-003",
        organization_id=org.id,
        name="Amitabh Deshmukh",
        phone="+919920112233",
        email="amit.d@apexinfra.com",
        preferred_language="en",
        status="Lead",
        tags=["B2B SaaS", "VP Sales"],
        custom_data={"company": "Apex Infra", "monthly_leads": "5000", "source": "Google Ads"},
        created_at=utc_now() - timedelta(hours=5)
    )
    db.add(c3)

    db.flush()

    # 6. Calls & Structured Summaries
    call1 = Call(
        id="call-stratum-seed-001",
        organization_id=org.id,
        agent_id=aarav.id,
        customer_id=c1.id,
        customer_phone=c1.phone,
        direction="outbound",
        status="completed",
        duration_seconds=145,
        primary_language="hi",
        languages_detected=["hi", "en"],
        provider_call_id="CA-STRATUM-001",
        telephony_provider="web_simulator",
        cost_estimate=10.80,
        started_at=utc_now() - timedelta(hours=4),
        ended_at=utc_now() - timedelta(hours=4, minutes=-2, seconds=-25)
    )
    db.add(call1)
    db.flush()

    summary1 = CallSummary(
        id="sum-001",
        call_id=call1.id,
        intent="Property Inquiry & VIP Site Visit Booking",
        outcome="Appointment Booked",
        sentiment="Positive",
        summary_text="Prospect Kalyan Varma inquired about a 3 BHK luxury residence in Gachibowli within a ₹2.2 Cr budget for family self-use. Aarav (Stratum AI) naturally addressed pricing using Financial District rental yields, dispatched the floor plan PDF on WhatsApp mid-call, and locked an exclusive VIP site visit for Saturday 11:00 AM.",
        key_information={"unit_type": "3 BHK", "budget": "₹2.2 Cr", "visit_scheduled": "Saturday 11:00 AM", "final_stratum_stage": "5. Action & Commitment"},
        next_action="Send chauffeur pickup confirmation on WhatsApp 2 hours prior to Saturday visit",
        qualification_status="Hot",
        bant_score={"budget": "₹2.2 Cr (Matches 3BHK tier)", "authority": "Primary Family Decision Maker", "need": "Upgrading to gated luxury community", "timeline": "VIP Site Visit Saturday 11 AM"},
        whatsapp_sent=True,
        meeting_scheduled=True,
        created_at=utc_now() - timedelta(hours=4)
    )
    db.add(summary1)

    t1 = CallTranscriptTurn(call_id=call1.id, speaker="agent", text="नमस्ते जी! मैं प्रेस्टीज लक्ज़री हाइट्स से आरव बोल रहा हूँ। आपने अभी हमारे गचीबोवली 3 और 4 BHK लक्ज़री होम्स के बारे में पूछा था—क्या अभी बात करने का सही समय है?", language="hi", timestamp=call1.started_at, latency_ms=380)
    t2 = CallTranscriptTurn(call_id=call1.id, speaker="customer", text="हाँ आरव, मैं फैमिली के लिए 3 BHK देख रहा हूँ। प्राइस क्या शुरू हो रहा है और पजेशन कब तक है?", language="hi", timestamp=call1.started_at + timedelta(seconds=12), latency_ms=0)
    t3 = CallTranscriptTurn(call_id=call1.id, speaker="agent", text="जी बिल्कुल, अच्छा सवाल है! देखिए प्रेस्टीज स्काई मीडोज में हमारे 2,400 स्क्वायर फीट के 3 BHK ₹2.15 Crore से शुरू होते हैं और मार्च 2027 तक पजेशन मिल जाएगा। क्या मैं शनिवार सुबह 11 बजे आपके लिए VIP साइट विजिट स्लॉट रख लूँ?", language="hi", timestamp=call1.started_at + timedelta(seconds=28), latency_ms=510)
    t4 = CallTranscriptTurn(call_id=call1.id, speaker="customer", text="Sounds good, please WhatsApp me the floor plans and lock the Saturday 11 AM slot.", language="en", timestamp=call1.started_at + timedelta(seconds=45), latency_ms=0)
    t5 = CallTranscriptTurn(call_id=call1.id, speaker="agent", text="अरे वाह, बहुत बढ़िया कल्याण जी! मैंने अभी आपके व्हाट्सएप पर फ्लोर प्लान और गेट पास भेज दिया है, और शनिवार सुबह 11:00 AM की VIP विजिट लॉक कर दी है!", language="hi", timestamp=call1.started_at + timedelta(seconds=58), latency_ms=460)
    db.add_all([t1, t2, t3, t4, t5])

    # 7. Speed to Lead Inbound Leads
    l1 = InboundLead(
        id="lead-speed-001",
        organization_id=org.id,
        agent_id=aarav.id,
        customer_id=c1.id,
        call_id=call1.id,
        name="Kalyan Varma",
        phone="+919876543210",
        email="kalyan.varma@techsol.in",
        source="meta_ads",
        campaign_name="Prestige Sky Meadows Luxury Lead Gen",
        lead_score=96,
        custom_data={"project": "Prestige Sky Meadows", "ad_set": "Hyderabad HNI 35-50"},
        status="qualified",
        response_time_seconds=4.2,
        created_at=utc_now() - timedelta(hours=4)
    )
    l2 = InboundLead(
        id="lead-speed-002",
        organization_id=org.id,
        agent_id=kavya.id,
        customer_id=c3.id,
        name="Amitabh Deshmukh",
        phone="+919920112233",
        email="amit.d@apexinfra.com",
        source="google_ads",
        campaign_name="Stratum AI Enterprise SDR Search Campaign",
        lead_score=91,
        custom_data={"intent": "Automate 5,000 monthly inbound leads", "crm": "HubSpot"},
        status="called",
        response_time_seconds=3.8,
        created_at=utc_now() - timedelta(hours=2)
    )
    db.add_all([l1, l2])

    # 8. Outbound Campaign
    campaign = Campaign(
        id="camp-re-weekend-001",
        organization_id=org.id,
        agent_id=aarav.id,
        name="Prestige Weekend VIP Site Visit Outreach - Batch 1",
        status="running",
        total_contacts=50,
        completed_calls=34,
        successful_calls=26,
        retry_limit=2,
        calling_hours_start=9,
        calling_hours_end=20,
        created_at=utc_now() - timedelta(days=1)
    )
    db.add(campaign)
    db.flush()

    cc1 = CampaignContact(
        id="cc-001",
        campaign_id=campaign.id,
        customer_id=c1.id,
        status="completed",
        attempts=1,
        last_attempt_at=utc_now() - timedelta(hours=4),
        result_outcome="Hot - VIP Site Visit Booked"
    )
    db.add(cc1)

    db.commit()
    print("[Stratum DB] Stratum AI Enterprise seeding completed successfully.")

def _ensure_sqlite_columns():
    """Idempotently add new multi-tenant & lifecycle columns to existing SQLite tables."""
    doc_cols = {
        "source_url": "VARCHAR(1000)",
        "canonical_url": "VARCHAR(1000)",
        "file_name": "VARCHAR(255)",
        "content_hash": "VARCHAR(128)",
        "version": "INTEGER DEFAULT 1",
        "approval_status": "VARCHAR(50) DEFAULT 'approved'",
        "approved_by": "VARCHAR(255)",
        "approved_at": "DATETIME",
        "is_active": "BOOLEAN DEFAULT 1",
        "ingestion_status": "VARCHAR(50) DEFAULT 'indexed'",
        "error_message": "TEXT",
        "prompt_injection_flagged": "BOOLEAN DEFAULT 0",
        "sanitized_warnings": "JSON",
        "last_checked_at": "DATETIME",
        "expires_at": "DATETIME",
    }
    chunk_cols = {
        "organization_id": "VARCHAR(36)",
        "page_number": "INTEGER DEFAULT 1",
        "section_title": "VARCHAR(255) DEFAULT 'General'",
        "table_data": "JSON",
        "content_hash": "VARCHAR(128)",
    }
    with engine.begin() as conn:
        existing_doc = {row[1] for row in conn.execute(text("PRAGMA table_info(knowledge_docs)")).fetchall()}
        for col, col_type in doc_cols.items():
            if col not in existing_doc:
                conn.execute(text(f"ALTER TABLE knowledge_docs ADD COLUMN {col} {col_type}"))

        existing_chunk = {row[1] for row in conn.execute(text("PRAGMA table_info(knowledge_chunks)")).fetchall()}
        for col, col_type in chunk_cols.items():
            if col not in existing_chunk:
                conn.execute(text(f"ALTER TABLE knowledge_chunks ADD COLUMN {col} {col_type}"))


def _ensure_default_workspace_profile(db: Session):
    """Ensure every Organization has a TenantWorkspaceProfile and existing chunks have organization_id."""
    orgs = db.query(Organization).all()
    for org in orgs:
        profile = db.query(TenantWorkspaceProfile).filter(
            TenantWorkspaceProfile.organization_id == org.id
        ).first()
        if not profile:
            profile = TenantWorkspaceProfile(
                organization_id=org.id,
                company_name=org.name,
                industry="Real Estate, Healthcare, EdTech, D2C & Enterprise AI",
                products_services="Prestige Sky Meadows 3/4 BHK Luxury Residences, Apollo Care Clinic OPD, Stratum Enterprise AI Voice Agents",
                target_audience="Homebuyers, Patients, D2C Shoppers, and Enterprise Sales Teams across India",
                call_objectives="Qualify leads using BANT, answer verified product/policy questions with source citations, and book confirmed appointments.",
                preferred_languages=["hi", "en", "te", "ta", "ml", "kn"],
                tone="Warm, Empathetic, Consultative & Strictly Grounded",
                faqs=[
                    {"question": "What are the configurations at Prestige Sky Meadows?", "answer": "3 BHK (2,400 sq.ft from ₹2.15 Cr) and 4 BHK (3,650 sq.ft from ₹3.45 Cr)."},
                    {"question": "What are Apollo Care Clinic OPD hours?", "answer": "Monday to Saturday, 8:00 AM to 8:30 PM (Closed on Sundays)."},
                ],
                business_policies={
                    "max_discount_pct": 8,
                    "healthcare_no_tele_prescription": True,
                    "high_value_order_verification_required": True,
                    "calling_window_ist": "09:00-20:00",
                },
                escalation_rules={
                    "transfer_number": "+919876543210",
                    "triggers": ["human", "manager", "officer", "complaint", "unverified_policy_exception"],
                },
                instructor_instructions="Always cite official company documents when stating prices, possession dates, or clinic hours. Never invent unlisted discounts or medical advice.",
                allowed_website_domains=["stratum.ai", "prestigeskymeadows.example.com", "apollocare.example.com"],
                freshness_policy_hours=168,
                require_instructor_approval=True,
            )
            db.add(profile)

    # Backfill organization_id and approval defaults on existing docs & chunks
    docs = db.query(KnowledgeDoc).all()
    for d in docs:
        if not d.approval_status:
            d.approval_status = "approved"
        if d.is_active is None:
            d.is_active = True
        if not d.ingestion_status:
            d.ingestion_status = "indexed"
        if not d.version:
            d.version = 1
        if not d.content_hash and d.content:
            d.content_hash = hashlib.sha256(d.content.encode("utf-8")).hexdigest()
        for ch in d.chunks:
            if not ch.organization_id:
                ch.organization_id = d.organization_id
            if not ch.page_number:
                ch.page_number = 1
            if not ch.section_title:
                ch.section_title = d.title
    db.commit()


def init_db():
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()
    db = SessionLocal()
    try:
        seed_database(db)
        _ensure_default_workspace_profile(db)
    finally:
        db.close()
