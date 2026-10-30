import React, { useState, useEffect } from 'react';
import {
  Key, Phone, ShieldCheck, Save, Check, MessageSquare, Zap, Globe,
  AlertCircle, CheckCircle2, Eye, EyeOff, ExternalLink, RefreshCw, Server, Cpu, Link2
} from 'lucide-react';
import { fetchTelephonyStatus, updateTelephonyConfig, testTwilioConnection } from '../api';
import { 
  Button, Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter,
  Badge, Input, Select, LoadingState, ErrorState 
} from '../components/ui';

export const Settings: React.FC = () => {
  const [telephonyProvider, setTelephonyProvider] = useState<'web_simulator' | 'twilio' | 'exotel'>('web_simulator');

  // Twilio state
  const [twilioAccountSid, setTwilioAccountSid] = useState('');
  const [twilioAuthToken, setTwilioAuthToken] = useState('');
  const [twilioPhoneNumber, setTwilioPhoneNumber] = useState('');
  const [publicWebhookUrl, setPublicWebhookUrl] = useState('');
  const [showAuthToken, setShowAuthToken] = useState(false);
  const [twilioConfigured, setTwilioConfigured] = useState(false);
  const [twilioHasAuthToken, setTwilioHasAuthToken] = useState(false);
  const [twilioMaskedSid, setTwilioMaskedSid] = useState('');

  // Exotel state
  const [exotelApiKey, setExotelApiKey] = useState('');
  const [exotelApiToken, setExotelApiToken] = useState('');
  const [exotelSubdomain, setExotelSubdomain] = useState('');
  const [exotelCallerId, setExotelCallerId] = useState('');

  // AI, CRM & WhatsApp keys
  const [groqKey, setGroqKey] = useState('');
  const [sarvamKey, setSarvamKey] = useState('');
  const [whatsAppToken, setWhatsAppToken] = useState('');
  const [whatsAppPhoneId, setWhatsAppPhoneId] = useState('');
  const [crmWebhook, setCrmWebhook] = useState('https://crm.yourcompany.com/api/v1/leads/stratum-sync');

  // UI state
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    message: string;
    account_status?: string;
    account_type?: string;
  } | null>(null);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const status = await fetchTelephonyStatus();
      setTelephonyProvider((status.active_provider as any) || 'web_simulator');
      setTwilioConfigured(status.twilio_configured);
      setTwilioHasAuthToken(Boolean(status.twilio_has_auth_token));
      if (status.twilio_account_sid_masked) setTwilioMaskedSid(status.twilio_account_sid_masked);
      if (status.twilio_phone_number) setTwilioPhoneNumber(status.twilio_phone_number);
      if (status.public_webhook_url) setPublicWebhookUrl(status.public_webhook_url);
      if (status.exotel_subdomain) setExotelSubdomain(status.exotel_subdomain);
      if (status.exotel_caller_id) setExotelCallerId(status.exotel_caller_id);
    } catch (err) {
      console.error('Failed to load telephony settings:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleTestTwilio = async () => {
    setTestingConnection(true);
    setTestResult(null);
    try {
      const res = await testTwilioConnection({
        account_sid: twilioAccountSid || undefined,
        auth_token: twilioAuthToken || undefined,
      });
      setTestResult(res);
    } catch (err: any) {
      setTestResult({
        success: false,
        message: err.message || 'Failed to communicate with backend test endpoint.',
      });
    } finally {
      setTestingConnection(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSaved(false);

    try {
      await updateTelephonyConfig({
        provider: telephonyProvider,
        twilio_account_sid: twilioAccountSid || undefined,
        twilio_auth_token: twilioAuthToken || undefined,
        twilio_phone_number: twilioPhoneNumber,
        public_webhook_url: publicWebhookUrl,
        exotel_api_key: exotelApiKey || undefined,
        exotel_api_token: exotelApiToken || undefined,
        exotel_subdomain: exotelSubdomain,
        exotel_caller_id: exotelCallerId,
      });

      const updated = await fetchTelephonyStatus();
      setTwilioConfigured(updated.twilio_configured);
      setTwilioHasAuthToken(Boolean(updated.twilio_has_auth_token));
      if (updated.twilio_account_sid_masked) setTwilioMaskedSid(updated.twilio_account_sid_masked);
      setTwilioAccountSid('');
      setTwilioAuthToken('');

      setSaved(true);
      setTimeout(() => setSaved(false), 3500);
    } catch (err) {
      console.error('Failed to save telephony settings:', err);
    } finally {
      setSaving(false);
    }
  };

  const webhookIsHttps = publicWebhookUrl.trim().startsWith('https://');

  if (loading) {
    return <LoadingState message="Loading platform configuration..." />;
  }

  return (
    <div className="space-y-8 max-w-5xl pb-16 animate-fade-in">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              System Settings & Carriers
            </h1>
            <Badge variant={twilioConfigured ? 'success' : 'warning'}>
              {twilioConfigured ? 'Twilio Ready' : 'Config Incomplete'}
            </Badge>
          </div>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">
            Manage telephony carriers, server-side Twilio credentials, outbound caller IDs, TwiML webhooks, speech providers, and CRM integrations.
          </p>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={loadSettings}
          leftIcon={<RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />}
        >
          Refresh
        </Button>
      </div>

      <form onSubmit={handleSave} className="space-y-6 text-xs">
        {/* SECTION 1: Telephony Provider */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Phone className="w-4 h-4 text-indigo-500" />
              1. Active Telephony Provider
            </CardTitle>
            <CardDescription className="text-xs">
              Choose the default audio transport for outbound and inbound calls.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <label className={`p-4 rounded-xl border cursor-pointer transition-all ${
                telephonyProvider === 'web_simulator'
                  ? 'bg-indigo-50 dark:bg-indigo-950/40 border-indigo-500 text-indigo-900 dark:text-white shadow-xs'
                  : 'bg-slate-50 dark:bg-slate-950/60 border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-700'
              }`}>
                <input
                  type="radio"
                  name="provider"
                  value="web_simulator"
                  checked={telephonyProvider === 'web_simulator'}
                  onChange={() => setTelephonyProvider('web_simulator')}
                  className="hidden"
                />
                <strong className="block text-xs font-semibold text-slate-900 dark:text-white mb-1">Browser Audio Simulator</strong>
                <span className="text-[11px] block text-slate-500 dark:text-slate-400">
                  Low-latency WebSocket voice sessions directly in the browser studio without carrier charges.
                </span>
              </label>

              <label className={`p-4 rounded-xl border cursor-pointer transition-all ${
                telephonyProvider === 'twilio'
                  ? 'bg-indigo-50 dark:bg-indigo-950/40 border-indigo-500 text-indigo-900 dark:text-white shadow-xs'
                  : 'bg-slate-50 dark:bg-slate-950/60 border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-700'
              }`}>
                <input
                  type="radio"
                  name="provider"
                  value="twilio"
                  checked={telephonyProvider === 'twilio'}
                  onChange={() => setTelephonyProvider('twilio')}
                  className="hidden"
                />
                <div className="flex items-center justify-between mb-1">
                  <strong className="block text-xs font-semibold text-slate-900 dark:text-white">Twilio PSTN</strong>
                  {twilioConfigured && <span className="w-2 h-2 rounded-full bg-emerald-500" />}
                </div>
                <span className="text-[11px] block text-slate-500 dark:text-slate-400">
                  Outbound & inbound PSTN calls with multi-turn TwiML speech gathering and 8kHz media streaming.
                </span>
              </label>

              <label className={`p-4 rounded-xl border cursor-pointer transition-all ${
                telephonyProvider === 'exotel'
                  ? 'bg-indigo-50 dark:bg-indigo-950/40 border-indigo-500 text-indigo-900 dark:text-white shadow-xs'
                  : 'bg-slate-50 dark:bg-slate-950/60 border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-700'
              }`}>
                <input
                  type="radio"
                  name="provider"
                  value="exotel"
                  checked={telephonyProvider === 'exotel'}
                  onChange={() => setTelephonyProvider('exotel')}
                  className="hidden"
                />
                <strong className="block text-xs font-semibold text-slate-900 dark:text-white mb-1">Exotel India</strong>
                <span className="text-[11px] block text-slate-500 dark:text-slate-400">
                  Indian enterprise cloud telephony with regional trunk routing.
                </span>
              </label>
            </div>
          </CardContent>
        </Card>

        {/* SECTION 2 & 3: Twilio Credentials & Caller ID */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base flex items-center gap-2">
                  <Key className="w-4 h-4 text-indigo-500" />
                  2 & 3. Twilio Credentials & Outbound Caller ID
                </CardTitle>
                <CardDescription className="text-xs">
                  Secrets are stored exclusively on the backend (`backend/.env`) and are never returned to the browser.
                </CardDescription>
              </div>
              <a
                href="https://console.twilio.com/"
                target="_blank"
                rel="noreferrer"
                className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline flex items-center gap-1 font-medium"
              >
                Twilio Console <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Status Bar */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3.5 bg-slate-50 dark:bg-slate-950/60 rounded-xl border border-slate-200 dark:border-slate-800">
              <div>
                <span className="text-[10px] uppercase text-slate-500 font-semibold block">Account SID Status</span>
                <strong className="text-slate-900 dark:text-slate-200 font-mono">
                  {twilioMaskedSid ? `Configured (${twilioMaskedSid})` : 'Not Set'}
                </strong>
              </div>
              <div>
                <span className="text-[10px] uppercase text-slate-500 font-semibold block">Auth Token Status</span>
                <strong className={twilioHasAuthToken ? 'text-emerald-600 dark:text-emerald-400 font-semibold' : 'text-amber-600 dark:text-amber-400 font-semibold'}>
                  {twilioHasAuthToken ? 'Stored on Backend (Hidden)' : 'Not Set'}
                </strong>
              </div>
              <div>
                <span className="text-[10px] uppercase text-slate-500 font-semibold block">Outbound Caller ID</span>
                <strong className="text-slate-900 dark:text-slate-200 font-mono">
                  {twilioPhoneNumber || 'Not Set'}
                </strong>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Input
                label="Twilio Account SID"
                placeholder={twilioMaskedSid || 'ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'}
                value={twilioAccountSid}
                onChange={(e) => setTwilioAccountSid(e.target.value)}
                helperText="Leave blank to keep existing server SID."
              />

              <div className="relative">
                <Input
                  label="Twilio Auth Token"
                  type={showAuthToken ? 'text' : 'password'}
                  placeholder={twilioHasAuthToken ? '••••••••••••••••••••••••••••••••' : 'Enter 32-char Auth Token'}
                  value={twilioAuthToken}
                  onChange={(e) => setTwilioAuthToken(e.target.value)}
                  helperText="Write-only field; never exposed in API responses."
                />
                <button
                  type="button"
                  onClick={() => setShowAuthToken(!showAuthToken)}
                  className="absolute right-3 top-9 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                >
                  {showAuthToken ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                </button>
              </div>

              <Input
                label="Outbound Caller ID"
                placeholder="+14155552671"
                value={twilioPhoneNumber}
                onChange={(e) => setTwilioPhoneNumber(e.target.value)}
                helperText="Active Twilio voice number in E.164 format."
              />
            </div>
          </CardContent>
        </Card>

        {/* SECTION 4 & 8: Webhook, Media-Stream Health & Diagnostics */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Server className="w-4 h-4 text-emerald-500" />
              4 & 8. Webhook, Media-Stream Health & Connection Diagnostics
            </CardTitle>
            <CardDescription className="text-xs">
              For real PSTN calls to hold a live multi-turn AI conversation, Twilio must reach your backend's endpoints via an HTTPS URL.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Input
                label="Public Webhook Base URL (PUBLIC_WEBHOOK_URL)"
                placeholder="https://your-tunnel.ngrok-free.app"
                value={publicWebhookUrl}
                onChange={(e) => setPublicWebhookUrl(e.target.value)}
                helperText="Expose port 8000 via Ngrok or Cloudflare Tunnel when testing live PSTN calls."
              />

              <div className="bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 rounded-xl p-3.5 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-slate-500 dark:text-slate-400">TwiML Speech Gather Loop:</span>
                  <span className="font-mono text-emerald-600 dark:text-emerald-400 text-[11px] font-semibold">/api/telephony/twilio/gather/*</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500 dark:text-slate-400">8kHz μ-law Media Stream:</span>
                  <span className="font-mono text-emerald-600 dark:text-emerald-400 text-[11px] font-semibold">/ws/voice/*</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500 dark:text-slate-400">Public HTTPS Reachability:</span>
                  <Badge variant={webhookIsHttps ? 'success' : 'warning'} size="sm">
                    {webhookIsHttps ? 'HTTPS Configured' : 'Missing HTTPS URL'}
                  </Badge>
                </div>
              </div>
            </div>

            {/* Test Connection Button & Diagnostic Output */}
            <div className="pt-3 border-t border-slate-100 dark:border-slate-800 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleTestTwilio}
                disabled={testingConnection || (!twilioAccountSid && !twilioMaskedSid)}
                isLoading={testingConnection}
                leftIcon={<Zap className="w-3.5 h-3.5 text-indigo-500" />}
              >
                Test Twilio Connection
              </Button>

              {testResult && (
                <div className={`p-2.5 rounded-lg text-[11px] font-medium flex items-center gap-2 border ${
                  testResult.success
                    ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-300 border-emerald-200 dark:border-emerald-700/50'
                    : 'bg-rose-50 dark:bg-rose-950/40 text-rose-800 dark:text-rose-300 border-rose-200 dark:border-rose-700/50'
                }`}>
                  {testResult.success ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
                  ) : (
                    <AlertCircle className="w-4 h-4 text-rose-600 dark:text-rose-400 shrink-0" />
                  )}
                  <span>{testResult.message}</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* SECTION 5: AI & Speech Provider */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Cpu className="w-4 h-4 text-indigo-500" />
              5. AI Reasoning & Speech Synthesis Providers
            </CardTitle>
            <CardDescription className="text-xs">
              Edge-TTS neural voices and the deterministic domain conversation engine operate out-of-the-box.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Input
                label="Groq API Key (Llama 3.3 70B Voice LLM)"
                type="password"
                placeholder="gsk_..."
                value={groqKey}
                onChange={(e) => setGroqKey(e.target.value)}
              />
              <Input
                label="Sarvam AI Key (Saarika Indic STT & Bulbul TTS)"
                type="password"
                placeholder="sarvam_..."
                value={sarvamKey}
                onChange={(e) => setSarvamKey(e.target.value)}
              />
            </div>
          </CardContent>
        </Card>

        {/* SECTION 6 & 7: CRM Integrations & WhatsApp Business */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Link2 className="w-4 h-4 text-indigo-500" />
                6. CRM Webhook Integration
              </CardTitle>
              <CardDescription className="text-xs">
                Sync post-call BANT scores, transcripts, and lead dispositions.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Input
                label="CRM Lead Sync Webhook URL"
                value={crmWebhook}
                onChange={(e) => setCrmWebhook(e.target.value)}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <MessageSquare className="w-4 h-4 text-emerald-500" />
                7. WhatsApp Business Cloud API
              </CardTitle>
              <CardDescription className="text-xs">
                Dispatch brochures and appointment confirmations via WhatsApp.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Input
                  label="WhatsApp Cloud Token"
                  type="password"
                  placeholder="EAA..."
                  value={whatsAppToken}
                  onChange={(e) => setWhatsAppToken(e.target.value)}
                />
                <Input
                  label="WhatsApp Phone ID"
                  placeholder="1092837465..."
                  value={whatsAppPhoneId}
                  onChange={(e) => setWhatsAppPhoneId(e.target.value)}
                />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Sticky Save Footer */}
        <div className="sticky bottom-4 bg-white/95 dark:bg-slate-900/95 backdrop-blur border border-slate-200 dark:border-slate-800 rounded-xl p-4 flex justify-between items-center shadow-lg">
          <div>
            {saved ? (
              <span className="text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1.5 text-xs">
                <Check className="w-4 h-4" /> Configuration saved to server environment.
              </span>
            ) : (
              <span className="text-slate-500 dark:text-slate-400 text-xs font-medium">
                Active Carrier: <strong className="text-slate-900 dark:text-white uppercase font-mono">{telephonyProvider}</strong>
              </span>
            )}
          </div>

          <Button
            type="submit"
            variant="primary"
            size="sm"
            isLoading={saving}
            leftIcon={<Save className="w-4 h-4" />}
          >
            Save Configuration
          </Button>
        </div>
      </form>
    </div>
  );
};
