import React, { useState, useEffect } from 'react';
import { 
  PhoneCall, ShieldCheck, CheckCircle2, AlertTriangle, Key, 
  Globe, Radio, MessageSquare, Zap, Cpu, RefreshCw, Eye, EyeOff, Save, Link2, Wifi, Activity
} from 'lucide-react';
import { fetchTelephonyStatus, updateTelephonyConfig, testTwilioConnection, fetchTelephonyHealthPublic } from '../api';
import { 
  Button, Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter,
  Badge, Input, Select, LoadingState, ErrorState 
} from '../components/ui';

export const Integrations: React.FC = () => {
  const [telephonyStatus, setTelephonyStatus] = useState<any>(null);
  const [publicHealth, setPublicHealth] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Twilio form state
  const [twilioAccountSid, setTwilioAccountSid] = useState('');
  const [twilioAuthToken, setTwilioAuthToken] = useState('');
  const [showAuthToken, setShowAuthToken] = useState(false);
  const [twilioPhoneNumber, setTwilioPhoneNumber] = useState('');
  const [publicWebhookUrl, setPublicWebhookUrl] = useState('');
  const [activeProvider, setActiveProvider] = useState('twilio');

  // Test connection state
  const [isTesting, setIsTesting] = useState(false);
  const [isProbing, setIsProbing] = useState(false);
  const [testResult, setTestResult] = useState<{
    success?: boolean;
    message?: string;
    account_status?: string;
    account_type?: string;
    code?: number;
  } | null>(null);

  // Save state
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccessMessage, setSaveSuccessMessage] = useState<string | null>(null);

  const loadStatus = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [statusData, healthData] = await Promise.all([
        fetchTelephonyStatus(),
        fetchTelephonyHealthPublic(false).catch(() => null)
      ]);
      setTelephonyStatus(statusData);
      setPublicHealth(healthData);
      setActiveProvider(statusData.active_provider || 'twilio');
      if (statusData.twilio_phone_number) setTwilioPhoneNumber(statusData.twilio_phone_number);
      if (statusData.public_base_url || statusData.public_webhook_url) {
        setPublicWebhookUrl(statusData.public_base_url || statusData.public_webhook_url || '');
      }
    } catch (err: any) {
      console.error('Failed to load telephony status:', err);
      setError(err.message || 'Failed to fetch carrier status');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const handleProbeReachability = async () => {
    setIsProbing(true);
    try {
      const res = await fetchTelephonyHealthPublic(true);
      setPublicHealth(res);
    } catch (err: any) {
      console.error('Reachability probe error:', err);
    } finally {
      setIsProbing(false);
    }
  };

  const handleTestConnection = async () => {
    setIsTesting(true);
    setTestResult(null);
    try {
      const payload: { account_sid?: string; auth_token?: string } = {};
      if (twilioAccountSid.trim()) payload.account_sid = twilioAccountSid.trim();
      if (twilioAuthToken.trim()) payload.auth_token = twilioAuthToken.trim();

      const res = await testTwilioConnection(payload);
      setTestResult(res);
    } catch (err: any) {
      setTestResult({
        success: false,
        message: err.message || 'Twilio connection test failed.',
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleSaveTelephony = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setSaveSuccessMessage(null);
    try {
      const trimmedUrl = publicWebhookUrl.trim() || undefined;
      const payload: any = {
        provider: activeProvider,
        public_webhook_url: trimmedUrl,
        public_base_url: trimmedUrl,
      };
      if (twilioAccountSid.trim()) payload.twilio_account_sid = twilioAccountSid.trim();
      if (twilioAuthToken.trim()) payload.twilio_auth_token = twilioAuthToken.trim();
      if (twilioPhoneNumber.trim()) payload.twilio_phone_number = twilioPhoneNumber.trim();

      await updateTelephonyConfig(payload);
      setSaveSuccessMessage('Carrier settings successfully synchronized and validated on backend.');
      setTwilioAuthToken(''); // clear token input for security
      await loadStatus();
      setTimeout(() => setSaveSuccessMessage(null), 5000);
    } catch (err: any) {
      alert(`Failed to save configuration: ${err.message || 'Unknown error'}`);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Integrations & Carriers
            </h1>
            <Badge variant="purple">Infrastructure</Badge>
          </div>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Configure PSTN telephony carriers, messaging channels, AI speech models, and external CRMs.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={loadStatus}
          leftIcon={<RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />}
        >
          Refresh Status
        </Button>
      </div>

      {isLoading ? (
        <LoadingState message="Loading carrier integrations & credentials status..." />
      ) : error ? (
        <ErrorState message={error} onRetry={loadStatus} />
      ) : (
        <div className="space-y-8">
          {/* Telephony Carriers Section */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                  <PhoneCall className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                  Telephony Carrier (PSTN Outbound & Inbound)
                </h2>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Select your active carrier for real mobile telephone calls, SIP trunking, and bidirectional audio streams.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Twilio Card */}
              <div className="lg:col-span-2">
                <Card>
                  <CardHeader>
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <CardTitle>Twilio PSTN Integration</CardTitle>
                          {telephonyStatus?.twilio_configured ? (
                            <Badge variant="success" size="sm">Configured</Badge>
                          ) : (
                            <Badge variant="warning" size="sm">Action Required</Badge>
                          )}
                        </div>
                        <CardDescription className="mt-1">
                          Powers two-way PSTN calls, media stream WebSockets, and Indian mobile delivery.
                        </CardDescription>
                      </div>
                      <Radio className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                    </div>
                  </CardHeader>
                  <CardContent>
                    <form onSubmit={handleSaveTelephony} className="space-y-5">
                      {/* Status Overview Banner */}
                      <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 text-xs space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-slate-500 dark:text-slate-400 font-medium">Configured SID:</span>
                          <span className="font-mono text-slate-900 dark:text-slate-200 font-semibold">
                            {telephonyStatus?.twilio_account_sid_masked || 'Not configured'}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-slate-500 dark:text-slate-400 font-medium">Auth Token:</span>
                          <span className="font-mono text-slate-900 dark:text-slate-200 font-semibold">
                            {telephonyStatus?.twilio_has_auth_token ? '•••••••••••••••• (Secure in Backend)' : 'Missing'}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-slate-500 dark:text-slate-400 font-medium">Active Caller ID:</span>
                          <span className="font-mono text-slate-900 dark:text-slate-200 font-semibold">
                            {telephonyStatus?.twilio_phone_number || 'Not set'}
                          </span>
                        </div>
                      </div>

                      {/* Fields */}
                      <div className="space-y-4">
                        <Input
                          label="Twilio Account SID"
                          placeholder={telephonyStatus?.twilio_account_sid_masked || "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}
                          value={twilioAccountSid}
                          onChange={(e) => setTwilioAccountSid(e.target.value)}
                          helperText="Begins with AC. Found in your Twilio Console."
                        />

                        <div className="relative">
                          <Input
                            label="Twilio Auth Token"
                            type={showAuthToken ? 'text' : 'password'}
                            placeholder={telephonyStatus?.twilio_has_auth_token ? "Leave blank to preserve configured token" : "Enter your 32-character Auth Token"}
                            value={twilioAuthToken}
                            onChange={(e) => setTwilioAuthToken(e.target.value)}
                            helperText="Stored strictly on the backend. Never rendered in plain-text."
                          />
                          <button
                            type="button"
                            onClick={() => setShowAuthToken(!showAuthToken)}
                            className="absolute right-3 top-9 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                            title={showAuthToken ? "Hide token" : "Show token"}
                          >
                            {showAuthToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                          </button>
                        </div>

                        <Input
                          label="Twilio Caller ID / Purchased Number"
                          placeholder="+1234567890 or +91XXXXXXXXXX"
                          value={twilioPhoneNumber}
                          onChange={(e) => setTwilioPhoneNumber(e.target.value)}
                          helperText="Must be an E.164 verified caller ID or Twilio phone number."
                        />

                        <Input
                          label="Public Webhook Base URL (ngrok / Production Domain)"
                          placeholder="https://your-ngrok-subdomain.ngrok-free.app"
                          value={publicWebhookUrl}
                          onChange={(e) => setPublicWebhookUrl(e.target.value)}
                          helperText="Twilio requires a public HTTPS URL to reach the answered-call webhook & media stream."
                        />
                      </div>

                      {/* Feedback Banners */}
                      {saveSuccessMessage && (
                        <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 text-xs text-emerald-800 dark:text-emerald-300 flex items-center gap-2">
                          <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
                          <span>{saveSuccessMessage}</span>
                        </div>
                      )}

                      {testResult && (
                        <div
                          className={`p-3 rounded-lg border text-xs flex items-start gap-2.5 ${
                            testResult.success
                              ? 'bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-300'
                              : 'bg-rose-50 dark:bg-rose-950/30 border-rose-200 dark:border-rose-800 text-rose-800 dark:text-rose-300'
                          }`}
                        >
                          {testResult.success ? (
                            <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 flex-shrink-0 mt-0.5" />
                          ) : (
                            <AlertTriangle className="w-4 h-4 text-rose-600 dark:text-rose-400 flex-shrink-0 mt-0.5" />
                          )}
                          <div>
                            <p className="font-semibold">{testResult.message}</p>
                            {testResult.account_type && (
                              <p className="mt-0.5 text-[11px] opacity-90">
                                Type: {testResult.account_type} • Status: {testResult.account_status}
                              </p>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Buttons */}
                      <div className="flex items-center justify-between pt-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={handleTestConnection}
                          isLoading={isTesting}
                          leftIcon={<Key className="w-3.5 h-3.5" />}
                        >
                          Test Twilio Auth
                        </Button>
                        <Button
                          type="submit"
                          variant="primary"
                          size="sm"
                          isLoading={isSaving}
                          leftIcon={<Save className="w-3.5 h-3.5" />}
                        >
                          Save Credentials
                        </Button>
                      </div>
                    </form>
                  </CardContent>
                </Card>

                {/* Twilio Public Connectivity & Health Diagnostics */}
                <Card>
                  <CardHeader>
                    <div className="flex items-start justify-between">
                      <div>
                        <CardTitle className="text-base flex items-center gap-2">
                          <Activity className="w-4 h-4 text-brand-600 dark:text-brand-400" />
                          Twilio Public Connectivity & Webhook Health
                        </CardTitle>
                        <CardDescription className="text-xs">
                          Live verification of HTTPS endpoints, WSS media streams, and external reachability.
                        </CardDescription>
                      </div>
                      <Badge 
                        variant={
                          publicHealth?.status === 'healthy'
                            ? 'success'
                            : publicHealth?.status === 'placeholder_url' || publicHealth?.status === 'unreachable_tunnel'
                            ? 'danger'
                            : 'warning'
                        }
                        size="sm"
                      >
                        {publicHealth?.status === 'healthy'
                          ? 'PSTN Ready'
                          : publicHealth?.status === 'placeholder_url'
                          ? 'Placeholder Domain'
                          : publicHealth?.status === 'unreachable_tunnel'
                          ? 'Tunnel Unreachable'
                          : 'Configure HTTPS Tunnel'}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4 text-xs">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="font-semibold text-slate-700 dark:text-slate-300">HTTPS Public Webhook</span>
                          <Badge variant={publicHealth?.is_https ? 'success' : 'neutral'} size="sm">
                            {publicHealth?.is_https ? 'HTTPS Enabled' : 'No HTTPS'}
                          </Badge>
                        </div>
                        <p className="font-mono text-[11px] text-slate-600 dark:text-slate-400 truncate">
                          {publicHealth?.public_base_url || 'Not configured'}
                        </p>
                      </div>

                      <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="font-semibold text-slate-700 dark:text-slate-300">Media Stream (WSS)</span>
                          <Badge variant={publicHealth?.media_stream_is_wss ? 'success' : 'neutral'} size="sm">
                            {publicHealth?.media_stream_is_wss ? 'WSS Ready' : 'WS Only'}
                          </Badge>
                        </div>
                        <p className="font-mono text-[11px] text-slate-600 dark:text-slate-400 truncate">
                          {publicHealth?.endpoints?.media_stream_ws_template || 'wss://.../ws/voice/{call_id}'}
                        </p>
                      </div>
                    </div>

                    {/* Endpoints Table / Preview */}
                    {publicHealth?.endpoints && (
                      <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/20 font-mono text-[11px] space-y-1.5">
                        <div className="text-[10px] uppercase font-sans font-bold text-slate-500 tracking-wider mb-1">
                          Generated Twilio Routing Endpoints
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-slate-500">TwiML Entry:</span>
                          <span className="text-slate-700 dark:text-slate-300 truncate max-w-[280px]">
                            {publicHealth.endpoints.twiml_url_template}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-slate-500">Speech Gather Loop:</span>
                          <span className="text-slate-700 dark:text-slate-300 truncate max-w-[280px]">
                            {publicHealth.endpoints.gather_url_template}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-slate-500">Status Callback:</span>
                          <span className="text-slate-700 dark:text-slate-300 truncate max-w-[280px]">
                            {publicHealth.endpoints.status_callback_template}
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Reachability Probe Feedback */}
                    {publicHealth?.reachability_probe && (
                      <div className={`p-3 rounded-lg border text-xs ${
                        publicHealth.reachability_probe.reachable
                          ? 'bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-300'
                          : 'bg-rose-50 dark:bg-rose-950/30 border-rose-200 dark:border-rose-800 text-rose-800 dark:text-rose-300'
                      }`}>
                        <div className="flex items-center gap-2 font-semibold">
                          {publicHealth.reachability_probe.reachable ? (
                            <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                          ) : (
                            <AlertTriangle className="w-4 h-4 text-rose-600 dark:text-rose-400" />
                          )}
                          <span>
                            {publicHealth.reachability_probe.reachable 
                              ? `External reachability verified! (${publicHealth.reachability_probe.latency_ms} ms)` 
                              : `Probe failed: ${publicHealth.reachability_probe.error || 'Server unreachable'}`}
                          </span>
                        </div>
                        <p className="mt-1 text-[11px] opacity-80 font-mono">
                          Target: {publicHealth.reachability_probe.probe_target}
                        </p>
                      </div>
                    )}

                    {/* Diagnostics List */}
                    {publicHealth?.diagnostics && publicHealth.diagnostics.length > 0 && (
                      <ul className="space-y-1 text-[11px] text-slate-600 dark:text-slate-400 list-disc list-inside">
                        {publicHealth.diagnostics.map((diag: string, idx: number) => (
                          <li key={idx}>{diag}</li>
                        ))}
                      </ul>
                    )}

                    <div className="pt-1 flex items-center justify-end">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={handleProbeReachability}
                        isLoading={isProbing}
                        leftIcon={<Wifi className="w-3.5 h-3.5" />}
                        disabled={!publicWebhookUrl}
                      >
                        Probe External Reachability
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Exotel & Secondary Carriers */}
              <div className="space-y-6">
                <Card>
                  <CardHeader>
                    <div className="flex items-start justify-between">
                      <div>
                        <CardTitle className="text-base">Exotel Indian Carrier</CardTitle>
                        <CardDescription className="text-xs">
                          Direct Indian PRI / SIP trunking for low-latency domestic calls.
                        </CardDescription>
                      </div>
                      <Badge variant="neutral" size="sm">Available</Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3 text-xs text-slate-600 dark:text-slate-400">
                    <p>
                      Supports Indian TRAI DND filtering, CLI whitelisting, and localized Mumbai/Delhi gateways.
                    </p>
                    <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-950/50 border border-slate-200 dark:border-slate-800 font-mono text-[11px]">
                      Status: Ready for SIP pairing
                    </div>
                  </CardContent>
                </Card>

                {/* WhatsApp Cloud API */}
                <Card>
                  <CardHeader>
                    <div className="flex items-start justify-between">
                      <div>
                        <CardTitle className="text-base">WhatsApp Business API</CardTitle>
                        <CardDescription className="text-xs">
                          Meta Cloud API for post-call summaries, brochure PDFs, and booking links.
                        </CardDescription>
                      </div>
                      <Badge variant="success" size="sm">Connected</Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3 text-xs text-slate-600 dark:text-slate-400">
                    <p>
                      Dispatches instant WhatsApp messages upon call completion with verified business badge.
                    </p>
                    <div className="p-2.5 rounded-lg bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-900/30 text-emerald-800 dark:text-emerald-300 font-mono text-[11px]">
                      Webhook: /api/whatsapp/webhook
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>
          </div>

          {/* AI Providers & Speech Stack */}
          <div>
            <div className="mb-4">
              <h2 className="text-lg font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                <Cpu className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                AI Speech & Intelligence Stack
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Models powering real-time transcription, conversation orchestration, and low-latency speech synthesis.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* STT */}
              <Card>
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div>
                      <CardTitle className="text-base">Speech-to-Text (STT)</CardTitle>
                      <CardDescription className="text-xs">Sarvam Indic + Deepgram</CardDescription>
                    </div>
                    <Badge variant="indigo" size="sm">Live</Badge>
                  </div>
                </CardHeader>
                <CardContent className="text-xs text-slate-600 dark:text-slate-300 space-y-2">
                  <p>
                    Trained on 10 Indian languages with code-mixing & Hinglish audio recognition. Latency &lt; 220ms.
                  </p>
                  <div className="pt-2 border-t border-slate-100 dark:border-slate-800 text-slate-500 dark:text-slate-400">
                    Barge-in VAD: Silero + WebRTC VAD
                  </div>
                </CardContent>
              </Card>

              {/* LLM */}
              <Card>
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div>
                      <CardTitle className="text-base">LLM Conversation Engine</CardTitle>
                      <CardDescription className="text-xs">OpenAI GPT-4o-mini / Claude 3.5</CardDescription>
                    </div>
                    <Badge variant="purple" size="sm">Orchestrated</Badge>
                  </div>
                </CardHeader>
                <CardContent className="text-xs text-slate-600 dark:text-slate-300 space-y-2">
                  <p>
                    State machine with BANT lead qualification, dynamic objection rebuttal, and tenant-isolated RAG.
                  </p>
                  <div className="pt-2 border-t border-slate-100 dark:border-slate-800 text-slate-500 dark:text-slate-400">
                    Streaming Token Generation: Enabled
                  </div>
                </CardContent>
              </Card>

              {/* TTS */}
              <Card>
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div>
                      <CardTitle className="text-base">Voice Synthesis (TTS)</CardTitle>
                      <CardDescription className="text-xs">Sarvam Bulbul + ElevenLabs</CardDescription>
                    </div>
                    <Badge variant="cyan" size="sm">HD Audio</Badge>
                  </div>
                </CardHeader>
                <CardContent className="text-xs text-slate-600 dark:text-slate-300 space-y-2">
                  <p>
                    Natural Indian accent cadences, ambient call center noise, and filler word micro-injection.
                  </p>
                  <div className="pt-2 border-t border-slate-100 dark:border-slate-800 text-slate-500 dark:text-slate-400">
                    Sample Rate: 8kHz / 16kHz μ-law
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
