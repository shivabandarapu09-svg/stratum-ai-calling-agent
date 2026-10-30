from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

# Auth
class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_name: str
    organization_id: str
    organization_name: str

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    full_name: Optional[str] = None
    role: str
    organization_id: str

# Agent
class AgentBase(BaseModel):
    name: str
    company: str = "Stratum Enterprise"
    purpose: str = "Lead Qualification & Sales SDR"
    blueprint: str = "b2b_saas_sdr" # real_estate, clinic_healthcare, education_admissions, ecommerce_cod, b2b_saas_sdr, bfsi_fintech, custom
    personality: str = "Warm, Empathetic, Natural & Consultative"
    system_prompt: str
    greeting: str
    default_language: str = "hi"
    supported_languages: List[str] = ["hi", "en", "te", "ta", "kn"]
    voice_id: str = "hi-IN-SwaraNeural"
    speaking_speed: float = 1.04
    voice_pitch: Optional[str] = "+0Hz"
    transfer_number: str = "+919876543210"
    consent_disclosure: str = "This call is recorded by Stratum AI for quality and training purposes."

    # Stratum Human-Realism Controls (Retell AI + Vapi + Sarvam AI)
    ambient_sound: Optional[str] = "office_call_center" # office_call_center, executive_room, warm_cafe, none
    backchannel_enabled: Optional[bool] = True
    filler_words_enabled: Optional[bool] = True
    interruption_sensitivity: Optional[float] = 0.85
    endpointing_ms: Optional[int] = 320

    # Stratum Qualification & Automation
    qualification_framework: str = "BANT"
    qualification_questions: List[str] = []
    objection_rebuttals: List[Dict[str, str]] = []
    whatsapp_template: str = "Hi {name}, thanks for speaking with us! Here are the details you requested: {link}"
    webhook_url: str = ""
    speed_to_lead_enabled: bool = True

class AgentCreate(AgentBase):
    pass

class AgentUpdate(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    purpose: Optional[str] = None
    blueprint: Optional[str] = None
    personality: Optional[str] = None
    system_prompt: Optional[str] = None
    greeting: Optional[str] = None
    default_language: Optional[str] = None
    supported_languages: Optional[List[str]] = None
    voice_id: Optional[str] = None
    speaking_speed: Optional[float] = None
    voice_pitch: Optional[str] = None
    transfer_number: Optional[str] = None
    consent_disclosure: Optional[str] = None
    ambient_sound: Optional[str] = None
    backchannel_enabled: Optional[bool] = None
    filler_words_enabled: Optional[bool] = None
    interruption_sensitivity: Optional[float] = None
    endpointing_ms: Optional[int] = None
    qualification_framework: Optional[str] = None
    qualification_questions: Optional[List[str]] = None
    objection_rebuttals: Optional[List[Dict[str, str]]] = None
    whatsapp_template: Optional[str] = None
    webhook_url: Optional[str] = None
    speed_to_lead_enabled: Optional[bool] = None
    is_active: Optional[bool] = None

class AgentOut(AgentBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    organization_id: str
    is_active: bool
    created_at: datetime

class VoicePreviewRequest(BaseModel):
    voice_id: str = "hi-IN-SwaraNeural"
    language: str = "hi"
    text: Optional[str] = None
    speaking_speed: float = 1.04
    pitch: str = "+0Hz"

# Customer
class CustomerCreate(BaseModel):
    name: Optional[str] = None
    phone: str
    email: Optional[str] = None
    preferred_language: str = "hi"
    status: str = "Lead"
    tags: List[str] = []
    custom_data: Dict[str, Any] = {}

class CustomerOut(CustomerCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    organization_id: str
    created_at: datetime

# Calls
class CallInitiateRequest(BaseModel):
    agent_id: str
    customer_phone: str
    customer_name: Optional[str] = None
    preferred_language: Optional[str] = "hi"
    provider: Optional[str] = "web_simulator" # web_simulator, twilio, exotel
    twilio_trial_mode: bool = False

class CallTranscriptTurnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    speaker: str
    text: str
    language: str
    is_code_switched: bool
    timestamp: datetime
    latency_ms: int

class CallSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    intent: str
    outcome: str
    sentiment: str
    summary_text: str
    key_information: Dict[str, Any]
    next_action: Optional[str] = None
    human_transfer_reason: Optional[str] = None
    qualification_status: Optional[str] = "Hot"
    bant_score: Optional[Dict[str, Any]] = {}
    whatsapp_sent: Optional[bool] = False
    meeting_scheduled: Optional[bool] = False

class CallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    agent_id: str
    agent_name: Optional[str] = None
    company_name: Optional[str] = None
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: str
    direction: str
    status: str
    telephony_provider: Optional[str] = "web_simulator"
    duration_seconds: int
    primary_language: str
    languages_detected: List[str]
    recording_url: Optional[str] = None
    cost_estimate: float
    started_at: datetime
    ended_at: Optional[datetime] = None
    summary: Optional[CallSummaryOut] = None

class CallDetailOut(CallOut):
    transcripts: List[CallTranscriptTurnOut] = []

# Inbound Leads & Speed-to-Lead
class InboundLeadCreate(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    source: str = "meta_ads" # meta_ads, google_ads, indiamart, justdial, webhook
    campaign_name: str = "Direct Form Submission"
    agent_id: Optional[str] = None
    custom_data: Dict[str, Any] = {}

class InboundLeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    organization_id: str
    agent_id: str
    agent_name: Optional[str] = None
    customer_id: Optional[str] = None
    call_id: Optional[str] = None
    name: str
    phone: str
    email: Optional[str] = None
    source: str
    campaign_name: str
    lead_score: int
    custom_data: Dict[str, Any] = {}
    status: str
    response_time_seconds: float
    created_at: datetime

class SpeedToLeadSimulateRequest(BaseModel):
    agent_id: str
    lead_name: str
    phone: str
    source: str = "meta_ads"
    product_interest: Optional[str] = None

class SpeedToLeadResponse(BaseModel):
    lead_id: str
    call_id: str
    status: str
    speed_to_lead_time_sec: float
    message: str

# Knowledge Base & Multi-Tenant Onboarding
class KnowledgeDocCreate(BaseModel):
    title: str
    source_type: str = "txt"
    content: str
    agent_id: Optional[str] = None
    organization_id: Optional[str] = None
    source_url: Optional[str] = None
    file_name: Optional[str] = None
    auto_approve: bool = False

class KnowledgeDocOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    organization_id: Optional[str] = None
    title: str
    source_type: str
    content: str
    agent_id: Optional[str] = None
    source_url: Optional[str] = None
    canonical_url: Optional[str] = None
    file_name: Optional[str] = None
    content_hash: Optional[str] = None
    version: int = 1
    approval_status: str = "approved"
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    is_active: bool = True
    ingestion_status: str = "indexed"
    error_message: Optional[str] = None
    prompt_injection_flagged: bool = False
    sanitized_warnings: List[str] = []
    last_checked_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    chunks_count: Optional[int] = 0

class KnowledgeSearchQuery(BaseModel):
    query: str
    organization_id: Optional[str] = None
    agent_id: Optional[str] = None
    limit: int = 3

class KnowledgeSearchResult(BaseModel):
    document_id: Optional[str] = None
    document_title: str
    source_type: str = "txt"
    canonical_url: Optional[str] = None
    page_number: int = 1
    section_title: str = "General"
    version: int = 1
    citation: str = ""
    text: str
    score: float

class TenantWorkspaceOnboardRequest(BaseModel):
    company_name: str
    industry: str = "Enterprise Services"
    products_services: str = ""
    target_audience: str = ""
    call_objectives: str = ""
    preferred_languages: List[str] = ["hi", "en", "te", "ta", "ml", "kn"]
    tone: str = "Warm, Consultative, Respectful & Truthful"
    faqs: List[Dict[str, str]] = []
    business_policies: Dict[str, Any] = {}
    escalation_rules: Dict[str, Any] = {}
    instructor_instructions: str = ""
    allowed_website_domains: List[str] = []
    freshness_policy_hours: int = 168
    auto_recrawl_enabled: bool = False
    require_instructor_approval: bool = True
    instructor_email: str = "instructor@stratum.ai"

class TenantWorkspaceUpdateRequest(BaseModel):
    company_name: Optional[str] = None
    industry: Optional[str] = None
    products_services: Optional[str] = None
    target_audience: Optional[str] = None
    call_objectives: Optional[str] = None
    preferred_languages: Optional[List[str]] = None
    tone: Optional[str] = None
    faqs: Optional[List[Dict[str, str]]] = None
    business_policies: Optional[Dict[str, Any]] = None
    escalation_rules: Optional[Dict[str, Any]] = None
    instructor_instructions: Optional[str] = None
    allowed_website_domains: Optional[List[str]] = None
    freshness_policy_hours: Optional[int] = None
    auto_recrawl_enabled: Optional[bool] = None
    require_instructor_approval: Optional[bool] = None
    updated_by: str = "instructor@stratum.ai"

class TenantWorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    organization_id: str
    company_name: str
    industry: str
    products_services: str
    target_audience: str
    call_objectives: str
    preferred_languages: List[str]
    tone: str
    faqs: List[Dict[str, str]]
    business_policies: Dict[str, Any]
    escalation_rules: Dict[str, Any]
    instructor_instructions: str
    allowed_website_domains: List[str]
    freshness_policy_hours: int
    auto_recrawl_enabled: bool
    require_instructor_approval: bool
    updated_by: str
    updated_at: datetime
    created_at: datetime

class WebsiteIngestRequest(BaseModel):
    organization_id: Optional[str] = None
    agent_id: Optional[str] = None
    url: str
    max_pages: int = 3
    allowed_scope_prefix: Optional[str] = None
    simulated_html_pages: Optional[Dict[str, str]] = None # Optional offline/sandbox test fixture map
    simulated_robots_txt: Optional[str] = None
    auto_approve: bool = False

class DocumentFileIngestRequest(BaseModel):
    organization_id: Optional[str] = None
    agent_id: Optional[str] = None
    file_name: str
    file_content_base64: Optional[str] = None
    raw_text: Optional[str] = None
    title: Optional[str] = None
    auto_approve: bool = False

class KnowledgeSourceReplaceRequest(BaseModel):
    title: Optional[str] = None
    content: str
    actor: str = "instructor@stratum.ai"
    auto_approve: bool = True

class KnowledgeApprovalRequest(BaseModel):
    action: str = "approve" # approve, disable
    actor: str = "instructor@stratum.ai"

class KnowledgeAuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    organization_id: str
    document_id: Optional[str] = None
    actor: str
    action: str
    status: str
    details: Dict[str, Any]
    created_at: datetime

# Campaigns
class CampaignCreate(BaseModel):
    name: str
    agent_id: str
    contacts: List[Dict[str, Any]]
    retry_limit: int = 2
    calling_hours_start: int = 9
    calling_hours_end: int = 20

class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    agent_id: str
    agent_name: Optional[str] = None
    status: str
    total_contacts: int
    completed_calls: int
    successful_calls: int
    retry_limit: int
    created_at: datetime

# Analytics
class DashboardKPIs(BaseModel):
    total_calls: int
    calls_today: int = 0
    successful_calls: int
    failed_calls: int
    transferred_calls: int
    answer_rate_pct: float
    conversion_rate_pct: float = 0.0
    avg_duration_seconds: float
    leads_qualified: int
    positive_sentiment_pct: float
    estimated_total_cost: float
    avg_cost_per_call: float = 0.0
    active_agents_count: int
    speed_to_lead_avg_seconds: float
    hot_leads_count: int
    whatsapp_delivered_count: int

class LanguageDistributionItem(BaseModel):
    language_code: str
    language_name: str
    call_count: int
    percentage: float

class CallOutcomeItem(BaseModel):
    outcome: str
    count: int

class LatencyMetrics(BaseModel):
    avg_stt_latency_ms: int
    avg_llm_latency_ms: int
    avg_tts_latency_ms: int
    avg_total_latency_ms: int
