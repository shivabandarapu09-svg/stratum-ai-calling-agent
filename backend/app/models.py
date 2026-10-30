import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, JSON
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

def generate_uuid():
    return str(uuid.uuid4())

def utc_now():
    return datetime.now(timezone.utc)

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=utc_now)

    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    agents = relationship("Agent", back_populates="organization", cascade="all, delete-orphan")
    customers = relationship("Customer", back_populates="organization", cascade="all, delete-orphan")
    calls = relationship("Call", back_populates="organization", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="organization", cascade="all, delete-orphan")
    knowledge_docs = relationship("KnowledgeDoc", back_populates="organization", cascade="all, delete-orphan")
    inbound_leads = relationship("InboundLead", back_populates="organization", cascade="all, delete-orphan")

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(String(50), default="admin") # superadmin, admin, agent_manager
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)

    organization = relationship("Organization", back_populates="users")

class Agent(Base):
    __tablename__ = "agents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    name = Column(String(255), nullable=False)
    company = Column(String(255), default="Stratum Enterprise")
    purpose = Column(String(255), default="Lead Qualification & Sales SDR")
    blueprint = Column(String(50), default="b2b_saas_sdr") # real_estate, clinic_healthcare, education_admissions, ecommerce_cod, b2b_saas_sdr, bfsi_fintech, custom
    personality = Column(String(100), default="Warm, Empathetic, Natural & Consultative")
    system_prompt = Column(Text, nullable=False)
    greeting = Column(Text, nullable=False)
    default_language = Column(String(10), default="hi") # hi, en, te, ta, ml, kn, mr
    supported_languages = Column(JSON, default=lambda: ["hi", "en", "te", "ta", "ml", "kn"])
    voice_id = Column(String(100), default="hi-IN-SwaraNeural")
    speaking_speed = Column(Float, default=1.04)
    voice_pitch = Column(String(20), default="+0Hz")
    transfer_number = Column(String(50), default="+919876543210")
    consent_disclosure = Column(Text, default="This call is recorded by Stratum AI for quality and verification purposes.")

    # Stratum Acoustic Realism & Pipeline Controls
    ambient_sound = Column(String(50), default="office_call_center") # office_call_center, executive_room, warm_cafe, none
    backchannel_enabled = Column(Boolean, default=True)
    filler_words_enabled = Column(Boolean, default=True)
    interruption_sensitivity = Column(Float, default=0.85)
    endpointing_ms = Column(Integer, default=320)

    # Qualification & Automation Capabilities
    qualification_framework = Column(String(50), default="BANT") # BANT, APPOINTMENT, ORDER_VERIFY, CUSTOM
    qualification_questions = Column(JSON, default=list)
    objection_rebuttals = Column(JSON, default=list) # [{objection: "...", rebuttal: "..."}]
    whatsapp_template = Column(Text, default="Hi {name}, thanks for speaking with us! Here are the details you requested: {link}")
    webhook_url = Column(String(500), default="")
    speed_to_lead_enabled = Column(Boolean, default=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)

    organization = relationship("Organization", back_populates="agents")
    calls = relationship("Call", back_populates="agent")
    knowledge_docs = relationship("KnowledgeDoc", back_populates="agent")
    inbound_leads = relationship("InboundLead", back_populates="agent")

class KnowledgeDoc(Base):
    __tablename__ = "knowledge_docs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    agent_id = Column(String(36), ForeignKey("agents.id"), nullable=True)
    title = Column(String(255), nullable=False)
    source_type = Column(String(50), default="txt") # pdf, docx, txt, csv, md, json, faq, url
    content = Column(Text, nullable=False)

    # Multi-Tenant Knowledge Lifecycle, Provenance & Security Fields
    source_url = Column(String(1000), nullable=True)
    canonical_url = Column(String(1000), nullable=True)
    file_name = Column(String(255), nullable=True)
    content_hash = Column(String(128), nullable=True, index=True)
    version = Column(Integer, default=1)
    approval_status = Column(String(50), default="approved") # pending_review, approved, disabled, failed
    approved_by = Column(String(255), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    ingestion_status = Column(String(50), default="indexed") # pending, indexing, indexed, failed, outdated
    error_message = Column(Text, nullable=True)
    prompt_injection_flagged = Column(Boolean, default=False)
    sanitized_warnings = Column(JSON, default=list)
    last_checked_at = Column(DateTime, default=utc_now)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    organization = relationship("Organization", back_populates="knowledge_docs")
    agent = relationship("Agent", back_populates="knowledge_docs")
    chunks = relationship("KnowledgeChunk", back_populates="document", cascade="all, delete-orphan")

class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    document_id = Column(String(36), ForeignKey("knowledge_docs.id"), nullable=False, index=True)
    chunk_index = Column(Integer, default=0)
    page_number = Column(Integer, default=1)
    section_title = Column(String(255), default="General")
    text = Column(Text, nullable=False)
    table_data = Column(JSON, nullable=True) # Extracted structured table rows if present
    content_hash = Column(String(128), nullable=True)
    embedding = Column(JSON, nullable=True) # list of floats for vector search

    document = relationship("KnowledgeDoc", back_populates="chunks")

class Customer(Base):
    __tablename__ = "customers"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    name = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=False, index=True)
    email = Column(String(255), nullable=True)
    preferred_language = Column(String(10), default="hi")
    status = Column(String(50), default="Lead") # Lead, Qualified, DNC, Customer
    tags = Column(JSON, default=list)
    custom_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utc_now)

    organization = relationship("Organization", back_populates="customers")
    calls = relationship("Call", back_populates="customer")
    appointments = relationship("Appointment", back_populates="customer")

class Call(Base):
    __tablename__ = "calls"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    agent_id = Column(String(36), ForeignKey("agents.id"), nullable=False)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True)
    customer_phone = Column(String(50), nullable=False)
    direction = Column(String(20), default="outbound") # outbound, inbound
    status = Column(String(50), default="initiated") # initiated, ringing, in_progress, completed, failed, transferred
    duration_seconds = Column(Integer, default=0)
    primary_language = Column(String(10), default="hi")
    languages_detected = Column(JSON, default=list) # e.g. ["hi", "en"]
    recording_url = Column(String(500), nullable=True)
    provider_call_id = Column(String(255), nullable=True)
    telephony_provider = Column(String(50), default="web_simulator")
    cost_estimate = Column(Float, default=0.0)
    started_at = Column(DateTime, default=utc_now)
    ended_at = Column(DateTime, nullable=True)

    organization = relationship("Organization", back_populates="calls")
    agent = relationship("Agent", back_populates="calls")
    customer = relationship("Customer", back_populates="calls")
    transcripts = relationship("CallTranscriptTurn", back_populates="call", cascade="all, delete-orphan", order_by="CallTranscriptTurn.timestamp")
    summary = relationship("CallSummary", back_populates="call", uselist=False, cascade="all, delete-orphan")
    appointment = relationship("Appointment", back_populates="call", uselist=False)

class CallTranscriptTurn(Base):
    __tablename__ = "call_transcript_turns"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    call_id = Column(String(36), ForeignKey("calls.id"), nullable=False)
    speaker = Column(String(20), nullable=False) # customer, agent, system
    text = Column(Text, nullable=False)
    language = Column(String(10), default="hi")
    is_code_switched = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=utc_now)
    latency_ms = Column(Integer, default=0)

    call = relationship("Call", back_populates="transcripts")

class CallSummary(Base):
    __tablename__ = "call_summaries"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    call_id = Column(String(36), ForeignKey("calls.id"), unique=True, nullable=False)
    intent = Column(String(255), default="Lead Qualification")
    outcome = Column(String(100), default="Completed") # Interested, Not Interested, Follow-up, Appointment Booked, Human Transfer, Failed
    sentiment = Column(String(50), default="Positive") # Positive, Neutral, Negative
    summary_text = Column(Text, nullable=False)
    key_information = Column(JSON, default=dict)
    next_action = Column(String(255), nullable=True)
    human_transfer_reason = Column(String(255), nullable=True)

    # Stratum Structured Intelligence
    qualification_status = Column(String(50), default="Hot") # Hot, Warm, Cold, Not Interested, Disqualified
    bant_score = Column(JSON, default=dict) # {"budget": "₹80L", "authority": "Decision Maker", "need": "3BHK flat", "timeline": "30 days"}
    whatsapp_sent = Column(Boolean, default=False)
    meeting_scheduled = Column(Boolean, default=False)

    created_at = Column(DateTime, default=utc_now)

    call = relationship("Call", back_populates="summary")

class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    agent_id = Column(String(36), ForeignKey("agents.id"), nullable=False)
    name = Column(String(255), nullable=False)
    status = Column(String(50), default="draft") # draft, running, paused, completed
    total_contacts = Column(Integer, default=0)
    completed_calls = Column(Integer, default=0)
    successful_calls = Column(Integer, default=0)
    retry_limit = Column(Integer, default=2)
    calling_hours_start = Column(Integer, default=9)
    calling_hours_end = Column(Integer, default=20)
    created_at = Column(DateTime, default=utc_now)

    organization = relationship("Organization", back_populates="campaigns")
    contacts = relationship("CampaignContact", back_populates="campaign", cascade="all, delete-orphan")

class CampaignContact(Base):
    __tablename__ = "campaign_contacts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), nullable=False)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False)
    status = Column(String(50), default="pending") # pending, calling, completed, failed, dnc
    attempts = Column(Integer, default=0)
    last_attempt_at = Column(DateTime, nullable=True)
    result_outcome = Column(String(100), nullable=True)

    campaign = relationship("Campaign", back_populates="contacts")
    customer = relationship("Customer")

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False)
    agent_id = Column(String(36), ForeignKey("agents.id"), nullable=False)
    call_id = Column(String(36), ForeignKey("calls.id"), nullable=True)
    scheduled_at = Column(DateTime, nullable=False)
    purpose = Column(String(255), default="Product Demo")
    notes = Column(Text, nullable=True)
    status = Column(String(50), default="confirmed") # confirmed, cancelled, completed
    created_at = Column(DateTime, default=utc_now)

    customer = relationship("Customer", back_populates="appointments")
    call = relationship("Call", back_populates="appointment")

class InboundLead(Base):
    __tablename__ = "inbound_leads"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    agent_id = Column(String(36), ForeignKey("agents.id"), nullable=False)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True)
    call_id = Column(String(36), ForeignKey("calls.id"), nullable=True)
    name = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=False, index=True)
    email = Column(String(255), nullable=True)
    source = Column(String(50), default="meta_ads") # meta_ads, google_ads, indiamart, justdial, webhook
    campaign_name = Column(String(255), default="Direct Inbound")
    lead_score = Column(Integer, default=85)
    custom_data = Column(JSON, default=dict)
    status = Column(String(50), default="called") # received, calling, called, qualified, failed
    response_time_seconds = Column(Float, default=4.2)
    created_at = Column(DateTime, default=utc_now)

    organization = relationship("Organization", back_populates="inbound_leads")
    agent = relationship("Agent", back_populates="inbound_leads")

class ToolExecutionLog(Base):
    __tablename__ = "tool_execution_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    call_id = Column(String(36), ForeignKey("calls.id"), nullable=False, index=True)
    turn_index = Column(Integer, default=0)
    tool_name = Column(String(100), nullable=False)
    idempotency_key = Column(String(128), nullable=False, index=True)
    input_args = Column(JSON, default=dict)
    output_payload = Column(JSON, default=dict)
    status = Column(String(50), default="success") # success, policy_infeasible, tool_infeasible, backend_error, skipped_clarification
    retry_count = Column(Integer, default=0)
    latency_ms = Column(Float, default=0.0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)


class TenantWorkspaceProfile(Base):
    """
    Multi-Tenant Company Onboarding & Instructor Configuration Workspace.
    Stores company-level instructions, products/services, target audience, call objectives,
    preferred languages, tone, FAQs, business policies, escalation rules, and freshness settings.
    """
    __tablename__ = "tenant_workspace_profiles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), unique=True, nullable=False, index=True)
    company_name = Column(String(255), nullable=False)
    industry = Column(String(100), default="Enterprise Services")
    products_services = Column(Text, default="")
    target_audience = Column(Text, default="")
    call_objectives = Column(Text, default="")
    preferred_languages = Column(JSON, default=lambda: ["hi", "en", "te", "ta", "ml", "kn"])
    tone = Column(String(255), default="Warm, Consultative, Respectful & Truthful")
    faqs = Column(JSON, default=list) # [{"question": "...", "answer": "..."}]
    business_policies = Column(JSON, default=dict) # {"max_discount_pct": 8, "refund_policy": "...", "operating_hours": "..."}
    escalation_rules = Column(JSON, default=dict) # {"transfer_number": "+919876543210", "triggers": ["manager", "complaint"]}
    instructor_instructions = Column(Text, default="")
    allowed_website_domains = Column(JSON, default=list) # ["example.com", "docs.example.com"]
    freshness_policy_hours = Column(Integer, default=168) # 7 days default
    auto_recrawl_enabled = Column(Boolean, default=False)
    require_instructor_approval = Column(Boolean, default=True)
    updated_by = Column(String(255), default="instructor@stratum.ai")
    updated_at = Column(DateTime, default=utc_now)
    created_at = Column(DateTime, default=utc_now)


class KnowledgeAuditLog(Base):
    """
    Tamper-evident audit log for tenant onboarding, source ingestion, approval,
    lifecycle actions, SSRF blocks, and prompt-injection detections (zero customer PII).
    """
    __tablename__ = "knowledge_audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    document_id = Column(String(36), nullable=True, index=True)
    actor = Column(String(255), default="instructor@stratum.ai")
    action = Column(String(100), nullable=False) # onboard_tenant, ingest_website, upload_document, approve_source, disable_source, replace_source, delete_source, ssrf_blocked, prompt_injection_sanitized
    status = Column(String(50), default="success")
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utc_now)
