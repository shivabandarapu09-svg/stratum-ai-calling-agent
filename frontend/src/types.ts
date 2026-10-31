export interface Agent {
  id: string;
  name: string;
  company: string;
  purpose: string;
  blueprint: string; // real_estate, clinic_healthcare, education_admissions, ecommerce_cod, b2b_saas_sdr, bfsi_fintech, custom
  personality: string;
  system_prompt: string;
  greeting: string;
  default_language: string;
  supported_languages: string[];
  voice_id: string;
  speaking_speed: number;
  voice_pitch?: string;
  transfer_number: string;
  consent_disclosure: string;
  // Stratum Human-Realism Pipeline Fields
  ambient_sound?: 'office_call_center' | 'executive_room' | 'warm_cafe' | 'none' | string;
  backchannel_enabled?: boolean;
  filler_words_enabled?: boolean;
  interruption_sensitivity?: number;
  endpointing_ms?: number;
  // Qualification & Automation
  qualification_framework?: string;
  qualification_questions?: string[];
  objection_rebuttals?: Array<{ objection: string; rebuttal: string }>;
  whatsapp_template?: string;
  webhook_url?: string;
  speed_to_lead_enabled?: boolean;
  is_active: boolean;
  created_at: string;
}

export interface ToolCallEvent {
  name: string;
  status: string;
  latency_ms: number;
  detail: string;
}

export interface CallTranscriptTurn {
  id: string;
  speaker: 'customer' | 'agent' | 'system';
  text: string;
  language: string;
  is_code_switched: boolean;
  timestamp: string;
  latency_ms: number;
}

export interface CallSummary {
  id: string;
  intent: string;
  outcome: string;
  sentiment: 'Positive' | 'Neutral' | 'Negative' | 'Angry';
  summary_text: string;
  key_information: Record<string, any>;
  next_action?: string;
  human_transfer_reason?: string;
  qualification_status?: 'Hot' | 'Warm' | 'Cold' | 'Not Interested' | 'Disqualified';
  bant_score?: {
    budget?: string;
    authority?: string;
    need?: string;
    timeline?: string;
    [key: string]: any;
  };
  whatsapp_sent?: boolean;
  meeting_scheduled?: boolean;
}

export interface Call {
  id: string;
  agent_id: string;
  agent_name?: string;
  company_name?: string;
  customer_id?: string;
  customer_name?: string;
  customer_phone: string;
  direction: 'outbound' | 'inbound';
  status: 'initiated' | 'ringing' | 'in_progress' | 'completed' | 'failed' | 'transferred';
  telephony_provider?: string;
  duration_seconds: number;
  primary_language: string;
  languages_detected: string[];
  recording_url?: string;
  cost_estimate: number;
  started_at: string;
  ended_at?: string;
  transcripts?: CallTranscriptTurn[];
  summary?: CallSummary;
  /** Short-lived signed ticket for opening /ws/voice/{id} (returned by call initiate/detail). */
  ws_ticket?: string;
}

export interface InboundLead {
  id: string;
  organization_id: string;
  agent_id: string;
  agent_name?: string;
  customer_id?: string;
  call_id?: string;
  name: string;
  phone: string;
  email?: string;
  source: string; // meta_ads, google_ads, indiamart, justdial, webhook
  campaign_name: string;
  lead_score: number;
  custom_data: Record<string, any>;
  status: string;
  response_time_seconds: number;
  created_at: string;
}

export interface BlueprintTemplate {
  blueprint: string;
  title: string;
  description: string;
  default_company: string;
  default_language: string;
  voice_id: string;
  qualification_framework: string;
  suggested_questions: string[];
}

export interface KnowledgeDoc {
  id: string;
  organization_id?: string;
  title: string;
  source_type: string;
  content: string;
  agent_id?: string;
  source_url?: string;
  canonical_url?: string;
  file_name?: string;
  content_hash?: string;
  version?: number;
  approval_status?: 'pending_review' | 'approved' | 'disabled' | 'failed' | string;
  approved_by?: string;
  approved_at?: string;
  is_active?: boolean;
  ingestion_status?: string;
  error_message?: string;
  prompt_injection_flagged?: boolean;
  sanitized_warnings?: string[];
  last_checked_at?: string;
  expires_at?: string;
  created_at: string;
  chunks_count: number;
}

export interface TenantWorkspace {
  id: string;
  organization_id: string;
  company_name: string;
  industry: string;
  products_services: string;
  target_audience: string;
  call_objectives: string;
  preferred_languages: string[];
  tone: string;
  faqs: Array<{ question: string; answer: string }>;
  business_policies: Record<string, any>;
  escalation_rules: Record<string, any>;
  instructor_instructions: string;
  allowed_website_domains: string[];
  freshness_policy_hours: number;
  auto_recrawl_enabled: boolean;
  require_instructor_approval: boolean;
  updated_by: string;
  updated_at: string;
  created_at: string;
}

export interface KnowledgeAuditLog {
  id: string;
  organization_id: string;
  document_id?: string;
  actor: string;
  action: string;
  status: string;
  details: Record<string, any>;
  created_at: string;
}

export interface Campaign {
  id: string;
  name: string;
  agent_id: string;
  agent_name?: string;
  status: 'draft' | 'running' | 'paused' | 'completed';
  total_contacts: number;
  completed_calls: number;
  successful_calls: number;
  retry_limit: number;
  created_at: string;
}

export interface DashboardKPIs {
  total_calls: number;
  calls_today?: number;
  successful_calls: number;
  failed_calls: number;
  transferred_calls: number;
  answer_rate_pct: number;
  conversion_rate_pct?: number;
  avg_duration_seconds: number;
  leads_qualified: number;
  positive_sentiment_pct: number;
  estimated_total_cost: number;
  avg_cost_per_call?: number;
  active_agents_count: number;
  speed_to_lead_avg_seconds?: number;
  hot_leads_count?: number;
  whatsapp_delivered_count?: number;
}

export interface LanguageDistribution {
  language_code: string;
  language_name: string;
  call_count: number;
  percentage: number;
}

export interface CallOutcome {
  outcome: string;
  count: number;
}

export interface LatencyMetrics {
  avg_stt_latency_ms: number;
  avg_llm_latency_ms: number;
  avg_tts_latency_ms: number;
  avg_total_latency_ms: number;
}

export interface SystemHealthSummary {
  telephony_provider: string;
  twilio_configured: boolean;
  public_webhook_configured: boolean;
  knowledge_sources_approved: number;
  active_agents_count: number;
  stt_provider: string;
  llm_provider: string;
  tts_provider: string;
}

export interface DashboardAnalytics {
  kpis: DashboardKPIs;
  languages: LanguageDistribution[];
  outcomes: CallOutcome[];
  latencies: LatencyMetrics;
  system_health?: SystemHealthSummary;
}
