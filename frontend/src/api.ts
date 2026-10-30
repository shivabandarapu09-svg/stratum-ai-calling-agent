import {
  Agent, Call, KnowledgeDoc, Campaign, DashboardAnalytics, InboundLead, BlueprintTemplate, TenantWorkspace, KnowledgeAuditLog
} from './types';

const API_BASE = '/api';

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/health`);
  return res.json();
}

export async function fetchAgents(): Promise<Agent[]> {
  const res = await fetch(`${API_BASE}/agents`);
  return res.json();
}

export async function fetchVoices(): Promise<Record<string, any>> {
  const res = await fetch(`${API_BASE}/agents/voices/available`);
  return res.json();
}

export async function previewVoiceSample(payload: {
  voice_id: string;
  language: string;
  text?: string;
  speaking_speed?: number;
  pitch?: string;
}): Promise<{
  voice_id: string;
  language: string;
  text: string;
  audio_base64: string | null;
  synthesis_latency_ms: number;
}> {
  const res = await fetch(`${API_BASE}/agents/voices/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  return res.json();
}

export async function fetchBlueprintTemplates(): Promise<BlueprintTemplate[]> {
  const res = await fetch(`${API_BASE}/agents/blueprints/templates`);
  return res.json();
}

export async function createAgent(agent: Partial<Agent>): Promise<Agent> {
  const res = await fetch(`${API_BASE}/agents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(agent)
  });
  return res.json();
}

export async function updateAgent(agentId: string, updates: Partial<Agent>): Promise<Agent> {
  const res = await fetch(`${API_BASE}/agents/${agentId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates)
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to update agent');
  }
  return res.json();
}

export async function fetchCalls(params?: { language?: string; status?: string }): Promise<Call[]> {
  const query = new URLSearchParams();
  if (params?.language) query.set('language', params.language);
  if (params?.status) query.set('status', params.status);

  const res = await fetch(`${API_BASE}/calls?${query.toString()}`);
  return res.json();
}

export async function fetchCallDetail(callId: string): Promise<Call> {
  const res = await fetch(`${API_BASE}/calls/${callId}`);
  return res.json();
}

export async function initiateOutboundCall(payload: {
  agent_id: string;
  customer_phone: string;
  customer_name?: string;
  preferred_language?: string;
  provider?: string;
  twilio_trial_mode?: boolean;
}): Promise<Call> {
  const res = await fetch(`${API_BASE}/calls/initiate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to initiate call (${res.status})`);
  }
  return res.json();
}

export async function terminateCall(callId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/calls/${callId}/terminate`, {
    method: 'POST'
  });
  return res.json();
}

export async function fetchAnalytics(): Promise<DashboardAnalytics> {
  const res = await fetch(`${API_BASE}/analytics/dashboard`);
  return res.json();
}

export async function fetchInboundLeads(source?: string): Promise<InboundLead[]> {
  const url = source ? `${API_BASE}/leads?source=${source}` : `${API_BASE}/leads`;
  const res = await fetch(url);
  return res.json();
}

export async function simulateSpeedToLead(payload: {
  agent_id: string;
  lead_name: string;
  phone: string;
  source: string;
  product_interest?: string;
}): Promise<{
  lead_id: string;
  call_id: string;
  status: string;
  speed_to_lead_time_sec: number;
  message: string;
}> {
  const res = await fetch(`${API_BASE}/leads/simulate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to simulate speed-to-lead');
  }
  return res.json();
}

export async function fetchTenantWorkspaces(): Promise<TenantWorkspace[]> {
  const res = await fetch(`${API_BASE}/knowledge/tenants`);
  return res.json();
}

export async function onboardCompanyTenant(payload: Partial<TenantWorkspace> & { company_name: string }): Promise<TenantWorkspace> {
  const res = await fetch(`${API_BASE}/knowledge/tenants/onboard`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to onboard company tenant');
  }
  return res.json();
}

export async function updateTenantWorkspace(organizationId: string, payload: Partial<TenantWorkspace>): Promise<TenantWorkspace> {
  const res = await fetch(`${API_BASE}/knowledge/tenants/${organizationId}/workspace`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-Tenant-ID': organizationId },
    body: JSON.stringify(payload)
  });
  return res.json();
}

export async function fetchKnowledgeDocs(organizationId?: string): Promise<KnowledgeDoc[]> {
  const query = organizationId ? `?organization_id=${encodeURIComponent(organizationId)}` : '';
  const headers: Record<string, string> = organizationId ? { 'X-Tenant-ID': organizationId } : {};
  const res = await fetch(`${API_BASE}/knowledge${query}`, { headers });
  return res.json();
}

export async function createKnowledgeDoc(payload: {
  title: string;
  content: string;
  source_type: string;
  organization_id?: string;
  agent_id?: string;
  auto_approve?: boolean;
}): Promise<KnowledgeDoc> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (payload.organization_id) headers['X-Tenant-ID'] = payload.organization_id;
  const res = await fetch(`${API_BASE}/knowledge`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to create document');
  }
  return res.json();
}

export async function ingestWebsiteSource(payload: {
  organization_id: string;
  url: string;
  max_pages?: number;
  simulated_html_pages?: Record<string, string>;
  auto_approve?: boolean;
}): Promise<KnowledgeDoc[]> {
  const res = await fetch(`${API_BASE}/knowledge/ingest/website`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Tenant-ID': payload.organization_id },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Website ingestion failed');
  }
  return res.json();
}

export async function ingestDocumentFile(payload: {
  organization_id: string;
  file_name: string;
  file_content_base64?: string;
  raw_text?: string;
  title?: string;
  auto_approve?: boolean;
}): Promise<KnowledgeDoc> {
  const res = await fetch(`${API_BASE}/knowledge/ingest/document`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Tenant-ID': payload.organization_id },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Document ingestion failed');
  }
  return res.json();
}

export async function approveOrDisableKnowledgeDoc(
  docId: string,
  organizationId: string,
  action: 'approve' | 'disable',
  actor: string = 'instructor@stratum.ai'
): Promise<KnowledgeDoc> {
  const res = await fetch(`${API_BASE}/knowledge/${docId}/approval`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Tenant-ID': organizationId },
    body: JSON.stringify({ action, actor })
  });
  return res.json();
}

export async function deleteKnowledgeDoc(docId: string, organizationId?: string): Promise<any> {
  const headers: Record<string, string> = organizationId ? { 'X-Tenant-ID': organizationId } : {};
  const res = await fetch(`${API_BASE}/knowledge/${docId}`, {
    method: 'DELETE',
    headers
  });
  return res.json();
}

export async function searchKnowledge(query: string, agentId?: string, organizationId?: string): Promise<any[]> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (organizationId) headers['X-Tenant-ID'] = organizationId;
  const res = await fetch(`${API_BASE}/knowledge/search`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ query, agent_id: agentId, organization_id: organizationId, limit: 3 })
  });
  return res.json();
}

export async function fetchKnowledgeAuditLogs(organizationId: string): Promise<KnowledgeAuditLog[]> {
  const res = await fetch(`${API_BASE}/knowledge/audit-logs?organization_id=${encodeURIComponent(organizationId)}`, {
    headers: { 'X-Tenant-ID': organizationId }
  });
  return res.json();
}

export async function fetchCampaigns(): Promise<Campaign[]> {
  const res = await fetch(`${API_BASE}/campaigns`);
  return res.json();
}

export async function createCampaign(payload: {
  name: string;
  agent_id: string;
  contacts: any[];
  retry_limit?: number;
}): Promise<Campaign> {
  const res = await fetch(`${API_BASE}/campaigns`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  return res.json();
}

export async function startCampaign(campaignId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/campaigns/${campaignId}/start`, {
    method: 'POST'
  });
  return res.json();
}

export async function fetchTelephonyStatus(): Promise<{
  active_provider: string;
  twilio_configured: boolean;
  twilio_account_sid_masked?: string;
  twilio_phone_number?: string;
  twilio_has_auth_token?: boolean;
  public_webhook_url?: string;
  public_base_url?: string;
  public_is_https?: boolean;
  public_ws_url_sample?: string;
  exotel_configured: boolean;
  exotel_subdomain?: string;
  exotel_caller_id?: string;
}> {
  const res = await fetch(`${API_BASE}/telephony/status`);
  return res.json();
}

export async function fetchTelephonyHealthPublic(probe = false): Promise<{
  status: string;
  configured: boolean;
  public_base_url: string;
  is_https: boolean;
  media_stream_is_wss: boolean;
  endpoints: {
    twiml_url_template: string;
    gather_url_template: string;
    reprompt_url_template: string;
    status_callback_template: string;
    media_stream_ws_template: string;
    inbound_webhook_url: string;
  };
  twilio_provider: {
    configured: boolean;
    account_sid_masked: string;
    phone_number: string;
    has_auth_token: boolean;
  };
  reachability_probe?: {
    probe_target: string;
    reachable: boolean;
    status_code?: number;
    latency_ms: number;
    response?: any;
    error?: string;
  } | null;
  diagnostics: string[];
}> {
  const res = await fetch(`${API_BASE}/telephony/health/public?probe=${probe}`);
  return res.json();
}

export async function updateTelephonyConfig(payload: {
  provider: string;
  twilio_account_sid?: string;
  twilio_auth_token?: string;
  twilio_phone_number?: string;
  public_webhook_url?: string;
  public_base_url?: string;
  exotel_api_key?: string;
  exotel_api_token?: string;
  exotel_subdomain?: string;
  exotel_caller_id?: string;
}): Promise<any> {
  const res = await fetch(`${API_BASE}/telephony/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  return res.json();
}

export async function testTwilioConnection(payload: {
  account_sid?: string;
  auth_token?: string;
}): Promise<{
  success: boolean;
  message: string;
  account_status?: string;
  account_type?: string;
  code?: number;
}> {
  const res = await fetch(`${API_BASE}/telephony/test-connection`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  return res.json();
}
