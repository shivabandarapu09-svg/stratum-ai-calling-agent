import React, { useState, useEffect } from 'react';
import {
  Zap, PhoneCall, ShieldCheck, CheckCircle2, Clock,
  Globe, Copy, Sparkles, RefreshCw
} from 'lucide-react';
import { InboundLead, Agent } from '../types';
import { fetchInboundLeads, simulateSpeedToLead, fetchAgents } from '../api';
import { 
  Button, Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter,
  Badge, Input, Select, Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
  EmptyState, LoadingState 
} from '../components/ui';

export const SpeedToLead: React.FC = () => {
  const [leads, setLeads] = useState<InboundLead[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [copiedWebhook, setCopiedWebhook] = useState<boolean>(false);

  // Simulation form
  const [simName, setSimName] = useState<string>('Rahul Singhania');
  const [simPhone, setSimPhone] = useState<string>('+919876543210');
  const [simSource, setSimSource] = useState<string>('meta_ads');
  const [simInterest, setSimInterest] = useState<string>('Prestige 3BHK Luxury Flat');
  const [simulating, setSimulating] = useState<boolean>(false);
  const [simResult, setSimResult] = useState<any>(null);

  const webhookUrl = `${window.location.origin}/api/leads/webhook`;

  const loadData = async () => {
    try {
      const [leadsData, agentsData] = await Promise.all([
        fetchInboundLeads(),
        fetchAgents(),
      ]);
      setLeads(leadsData || []);
      setAgents(agentsData || []);
      if (agentsData?.length > 0 && !selectedAgentId) {
        setSelectedAgentId(agentsData[0].id);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedWebhook(true);
    setTimeout(() => setCopiedWebhook(false), 2000);
  };

  const handleSimulate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAgentId) return;

    setSimulating(true);
    setSimResult(null);

    try {
      const res = await simulateSpeedToLead({
        agent_id: selectedAgentId,
        lead_name: simName,
        phone: simPhone,
        source: simSource,
        product_interest: simInterest,
      });
      setSimResult(res);
      await loadData();
    } catch (err: any) {
      alert(err.message || 'Simulation failed');
    } finally {
      setSimulating(false);
    }
  };

  const getSourceBadge = (source: string) => {
    switch (source) {
      case 'meta_ads':
        return <Badge variant="indigo" size="sm">Meta Ads</Badge>;
      case 'google_ads':
        return <Badge variant="warning" size="sm">Google Ads</Badge>;
      case 'indiamart':
        return <Badge variant="success" size="sm">IndiaMART</Badge>;
      default:
        return <Badge variant="neutral" size="sm">API Webhook</Badge>;
    }
  };

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Speed-to-Lead Engine
            </h1>
            <Badge variant="success">Instant Trigger</Badge>
          </div>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">
            Connect Meta Ads, Google Ads, IndiaMART, or Web forms. Stratum triggers an automated voice call within seconds of submission.
          </p>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={loadData}
          leftIcon={<RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />}
        >
          Refresh Leads
        </Button>
      </div>

      {/* Value Metrics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-2">
            <span className="font-semibold uppercase tracking-wider text-[11px]">Avg Response</span>
            <Clock className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 font-mono">4.8s</div>
          <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">Target: Sub-30 seconds</p>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-2">
            <span className="font-semibold uppercase tracking-wider text-[11px]">Contact Rate Boost</span>
            <Sparkles className="w-4 h-4 text-indigo-500" />
          </div>
          <div className="text-2xl font-bold text-indigo-600 dark:text-indigo-400 font-mono">+391%</div>
          <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">Calling &lt;1 min vs 1 hour</p>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-2">
            <span className="font-semibold uppercase tracking-wider text-[11px]">Inbound Captured</span>
            <PhoneCall className="w-4 h-4 text-indigo-500" />
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-white font-mono">{leads.length}</div>
          <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">Live synchronized in CRM</p>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-2">
            <span className="font-semibold uppercase tracking-wider text-[11px]">Qualification Rate</span>
            <ShieldCheck className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-white font-mono">82.4%</div>
          <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">BANT Framework verification</p>
        </div>
      </div>

      {/* Simulator & Webhook Setup Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Live Simulator (7 cols) */}
        <div className="lg:col-span-7">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-indigo-500" />
                    Live Speed-to-Lead Simulator
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Simulate a live form submission and watch the AI dial immediately.
                  </CardDescription>
                </div>
                <Badge variant="indigo" size="sm">Real-Time</Badge>
              </div>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSimulate} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <Select
                    label="Target AI Agent"
                    value={selectedAgentId}
                    onChange={(e) => setSelectedAgentId(e.target.value)}
                    options={agents.map((ag) => ({
                      value: ag.id,
                      label: `${ag.name} (${ag.company || 'Enterprise'})`,
                    }))}
                  />

                  <Select
                    label="Inbound Channel"
                    value={simSource}
                    onChange={(e) => setSimSource(e.target.value)}
                    options={[
                      { value: 'meta_ads', label: 'Meta Instant Form (FB/IG)' },
                      { value: 'google_ads', label: 'Google Search Lead Form' },
                      { value: 'indiamart', label: 'IndiaMART B2B Lead' },
                      { value: 'webhook', label: 'Website Landing Page Webhook' },
                    ]}
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <Input
                    label="Prospect Name"
                    value={simName}
                    onChange={(e) => setSimName(e.target.value)}
                    required
                  />
                  <Input
                    label="Prospect Mobile Number"
                    value={simPhone}
                    onChange={(e) => setSimPhone(e.target.value)}
                    required
                    helperText="E.164 format (+91XXXXXXXXXX)"
                  />
                </div>

                <Input
                  label="Product / Interest Specification"
                  value={simInterest}
                  onChange={(e) => setSimInterest(e.target.value)}
                  placeholder="e.g. 3 BHK Luxury Apartment / Executive AI Course"
                />

                <Button
                  type="submit"
                  variant="primary"
                  size="md"
                  className="w-full"
                  isLoading={simulating}
                  leftIcon={<Zap className="w-4 h-4" />}
                >
                  Trigger Speed-to-Lead Call Now
                </Button>
              </form>

              {/* Simulation Output Card */}
              {simResult && (
                <div className="mt-4 p-4 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 rounded-xl space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-emerald-800 dark:text-emerald-300 flex items-center gap-1.5">
                      <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                      Instant Call Dispatched!
                    </span>
                    <Badge variant="success" size="sm">
                      Dialed in {simResult.speed_to_lead_time_sec}s
                    </Badge>
                  </div>
                  <p className="text-xs text-emerald-900 dark:text-emerald-200">{simResult.message}</p>
                  <div className="text-[11px] text-emerald-700 dark:text-emerald-400 flex items-center gap-2 pt-1 border-t border-emerald-200 dark:border-emerald-900">
                    <span>Call ID: <code className="font-mono">{simResult.call_id.slice(0, 16)}...</code></span>
                    <span>•</span>
                    <span>Status: <strong>Ringing</strong></span>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Integration Instructions & Webhook URL (5 cols) */}
        <div className="lg:col-span-5 space-y-6">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Globe className="w-4 h-4 text-indigo-500" />
                  Inbound Webhook Endpoint
                </CardTitle>
                <Badge variant="neutral" size="sm">POST</Badge>
              </div>
              <CardDescription className="text-xs">
                Paste this webhook into Meta Ads, Zapier, or your landing page forms to trigger immediate calls:
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="p-3 bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 rounded-xl flex items-center justify-between gap-2">
                <code className="text-xs text-indigo-600 dark:text-indigo-400 font-mono break-all">{webhookUrl}</code>
                <Button
                  variant="ghost"
                  size="xs"
                  onClick={() => copyToClipboard(webhookUrl)}
                  title="Copy Webhook URL"
                >
                  {copiedWebhook ? <CheckCircle2 className="w-4 h-4 text-emerald-500" /> : <Copy className="w-4 h-4" />}
                </Button>
              </div>

              <div className="space-y-2">
                <span className="text-xs font-semibold text-slate-700 dark:text-slate-300 block">Example Payload:</span>
                <pre className="p-3 bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 rounded-xl text-[10px] font-mono text-slate-700 dark:text-slate-300 overflow-x-auto">
{`{
  "name": "Kalyan Varma",
  "phone": "+919876543210",
  "source": "meta_ads",
  "campaign_name": "Prestige Sky Meadows",
  "custom_data": { "budget": "₹2.2 Cr" }
}`}
                </pre>
              </div>

              <div className="pt-2">
                <span className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 dark:text-slate-500 block mb-2">
                  Supported Gateways
                </span>
                <div className="flex flex-wrap gap-1.5">
                  <Badge variant="neutral" size="sm">Meta Lead Ads</Badge>
                  <Badge variant="neutral" size="sm">Google Ads</Badge>
                  <Badge variant="neutral" size="sm">IndiaMART</Badge>
                  <Badge variant="neutral" size="sm">Zapier / Make</Badge>
                  <Badge variant="neutral" size="sm">n8n</Badge>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Captured Leads Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Captured Inbound Leads</CardTitle>
              <CardDescription>
                Live log of prospects called within seconds of form submission.
              </CardDescription>
            </div>
            <Badge variant="indigo" size="sm">Total: {leads.length}</Badge>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {leads.length === 0 ? (
            <EmptyState
              icon={PhoneCall}
              title="No inbound leads yet"
              description="Use the simulator above or submit via the webhook endpoint to capture instant leads."
            />
          ) : (
            <Table className="border-0 rounded-none shadow-none">
              <TableHeader>
                <TableRow>
                  <TableHead>Prospect</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Campaign</TableHead>
                  <TableHead>Assigned Agent</TableHead>
                  <TableHead>Response Time</TableHead>
                  <TableHead>Lead Score</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Date</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {leads.map((l) => (
                  <TableRow key={l.id}>
                    <TableCell>
                      <div className="font-semibold text-slate-900 dark:text-white">{l.name}</div>
                      <div className="text-[11px] text-slate-500 dark:text-slate-400 font-mono">{l.phone}</div>
                    </TableCell>
                    <TableCell>{getSourceBadge(l.source)}</TableCell>
                    <TableCell className="max-w-xs truncate text-slate-700 dark:text-slate-300 font-medium">
                      {l.campaign_name}
                    </TableCell>
                    <TableCell>
                      <span className="font-medium text-slate-800 dark:text-slate-200">{l.agent_name || 'AI Employee'}</span>
                    </TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-1 font-mono font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/80 px-2 py-0.5 rounded border border-emerald-200 dark:border-emerald-800 text-[11px]">
                        <Clock className="w-3 h-3" /> {l.response_time_seconds}s
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="font-mono text-xs font-bold text-indigo-600 dark:text-indigo-400">
                        {l.lead_score || 85}/100
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          l.status === 'qualified'
                            ? 'success'
                            : l.status === 'called'
                            ? 'indigo'
                            : 'neutral'
                        }
                        size="sm"
                      >
                        {l.status.toUpperCase()}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right text-slate-400 text-xs font-mono">
                      {new Date(l.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
};
