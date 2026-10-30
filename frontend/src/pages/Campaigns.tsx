import React, { useEffect, useState } from 'react';
import {
  Send, Plus, Play, Pause, CheckCircle2, ShieldCheck, Clock, RefreshCw
} from 'lucide-react';
import { Campaign, Agent } from '../types';
import { fetchCampaigns, fetchAgents, createCampaign, startCampaign } from '../api';
import { 
  Button, Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter,
  Badge, Input, Textarea, Select, Dialog, EmptyState, LoadingState 
} from '../components/ui';

export const Campaigns: React.FC = () => {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [showModal, setShowModal] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);

  // New campaign state
  const [name, setName] = useState('Luxury Real Estate VIP Site Visit Outreach - Batch 1');
  const [agentId, setAgentId] = useState('');
  const [rawContacts, setRawContacts] = useState(
    'Kalyan Varma,+919876543210,Prestige 3BHK\nAnanya Sharma,+919812345678,Godrej 4BHK\nRohit Agarwal,+919920112233,Weekend Visit'
  );

  const loadData = () => {
    setLoading(true);
    Promise.all([fetchCampaigns(), fetchAgents()])
      .then(([campData, agentsData]) => {
        setCampaigns(campData || []);
        setAgents(agentsData || []);
        if (agentsData?.length > 0 && !agentId) setAgentId(agentsData[0].id);
        setLoading(false);
      })
      .catch((e) => {
        console.error(e);
        setLoading(false);
      });
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleStart = async (id: string) => {
    try {
      await startCampaign(id);
      setCampaigns(campaigns.map((c) => (c.id === id ? { ...c, status: 'running' } : c)));
    } catch (e) {
      console.error('Error starting campaign:', e);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const lines = rawContacts.split('\n').filter((l) => l.trim().length > 0);
    const contacts = lines.map((line) => {
      const parts = line.split(',');
      return {
        name: parts[0]?.trim() || 'Prospect',
        phone: parts[1]?.trim() || parts[0]?.trim(),
        product: parts[2]?.trim() || 'General Inquiry',
      };
    });

    try {
      const newCamp = await createCampaign({
        name,
        agent_id: agentId,
        contacts,
        retry_limit: 2,
      });
      setCampaigns([newCamp, ...campaigns]);
      setShowModal(false);
    } catch (e) {
      console.error('Error creating campaign:', e);
    }
  };

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Outbound Bulk Campaigns
            </h1>
            <Badge variant="indigo">High-Concurrency Dialer</Badge>
          </div>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">
            Automate targeted voice outreach with TRAI 9 AM - 8 PM compliance, DND checks, and smart retry logic.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={loadData}
            leftIcon={<RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />}
          >
            Refresh
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => setShowModal(true)}
            leftIcon={<Plus className="w-4 h-4" />}
          >
            Create Campaign
          </Button>
        </div>
      </div>

      {/* Compliance Notice */}
      <div className="p-4 bg-amber-50/60 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/40 rounded-xl flex items-start gap-3 text-xs text-amber-900 dark:text-amber-200">
        <ShieldCheck className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
        <div className="space-y-1">
          <strong className="block font-semibold">Indian Telecom (TRAI) Calling Compliance Active</strong>
          <p className="text-amber-800/80 dark:text-amber-300/80 leading-relaxed">
            Calls are automatically restricted to standard hours (9:00 AM – 8:00 PM IST). National Do Not Call (NDNC/DND) scrubbing and mandatory AI voice recording disclosures are enforced on every outbound connection.
          </p>
        </div>
      </div>

      {/* Campaigns Grid */}
      {loading ? (
        <LoadingState message="Loading outbound dialing campaigns..." />
      ) : campaigns.length === 0 ? (
        <EmptyState
          icon={Send}
          title="No campaigns yet"
          description="Create your first outbound campaign to automate multi-lingual customer calls."
          actionLabel="Create Campaign"
          onAction={() => setShowModal(true)}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {campaigns.map((c) => {
            const progress = c.total_contacts > 0
              ? Math.round((c.completed_calls / c.total_contacts) * 100)
              : 0;

            return (
              <Card key={c.id} className="flex flex-col justify-between hover:shadow-md transition-shadow">
                <div>
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between mb-2">
                      <Badge
                        variant={
                          c.status === 'running'
                            ? 'success'
                            : c.status === 'completed'
                            ? 'neutral'
                            : 'warning'
                        }
                        size="sm"
                      >
                        {c.status.toUpperCase()}
                      </Badge>
                      <span className="text-[11px] text-slate-400 font-mono">
                        {new Date(c.created_at).toLocaleDateString()}
                      </span>
                    </div>

                    <CardTitle className="text-base line-clamp-1">{c.name}</CardTitle>
                    <CardDescription className="text-xs">
                      Assigned Agent: <strong className="text-slate-700 dark:text-slate-300">{c.agent_name || 'Outbound SDR'}</strong>
                    </CardDescription>
                  </CardHeader>

                  <CardContent className="space-y-4">
                    {/* Progress bar */}
                    <div className="space-y-1.5">
                      <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400 font-medium">
                        <span>Progress ({progress}%)</span>
                        <span>{c.completed_calls} / {c.total_contacts} Contacts</span>
                      </div>
                      <div className="w-full bg-slate-100 dark:bg-slate-950 rounded-full h-2 overflow-hidden border border-slate-200 dark:border-slate-800">
                        <div
                          className="bg-indigo-600 h-full rounded-full transition-all duration-500"
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                    </div>

                    {/* Metrics */}
                    <div className="grid grid-cols-2 gap-2 text-xs bg-slate-50 dark:bg-slate-950/60 p-3 rounded-xl border border-slate-200 dark:border-slate-800">
                      <div>
                        <span className="text-slate-500 dark:text-slate-400 text-[10px] uppercase font-semibold block">Qualified Leads</span>
                        <strong className="text-emerald-600 dark:text-emerald-400 text-sm">{c.successful_calls}</strong>
                      </div>
                      <div>
                        <span className="text-slate-500 dark:text-slate-400 text-[10px] uppercase font-semibold block">Retry Limit</span>
                        <strong className="text-slate-700 dark:text-slate-300 text-sm">{c.retry_limit} attempts</strong>
                      </div>
                    </div>
                  </CardContent>
                </div>

                <CardFooter className="pt-3 border-t border-slate-100 dark:border-slate-800">
                  {c.status === 'draft' ? (
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => handleStart(c.id)}
                      className="w-full"
                      leftIcon={<Play className="w-3.5 h-3.5" />}
                    >
                      Start Auto-Dialing
                    </Button>
                  ) : c.status === 'running' ? (
                    <div className="w-full bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-400 py-2 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-2">
                      <Clock className="w-3.5 h-3.5 animate-spin" /> Dialing Concurrently...
                    </div>
                  ) : (
                    <div className="w-full bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 py-2 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-2">
                      <CheckCircle2 className="w-3.5 h-3.5 text-indigo-500" /> Campaign Completed
                    </div>
                  )}
                </CardFooter>
              </Card>
            );
          })}
        </div>
      )}

      {/* Create Modal */}
      <Dialog
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title="Create Outbound Batch Campaign"
        description="Schedule a batch calling list for multi-lingual AI outreach."
      >
        <form onSubmit={handleCreate} className="space-y-4 text-xs">
          <Input
            label="Campaign Name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />

          <Select
            label="Assign AI Voice Agent"
            value={agentId}
            onChange={(e) => setAgentId(e.target.value)}
            options={agents.map((a) => ({
              value: a.id,
              label: `${a.name} (${a.company || 'Enterprise'})`,
            }))}
          />

          <Textarea
            label="Contacts List (Format: Name,Phone,Product - one per line)"
            rows={5}
            value={rawContacts}
            onChange={(e) => setRawContacts(e.target.value)}
            placeholder="Kalyan Varma,+919876543210,Prestige 3BHK"
          />

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-100 dark:border-slate-800">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setShowModal(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              size="sm"
            >
              Create Campaign
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
};
