import React, { useState, useEffect } from 'react';
import { 
  Users, PhoneCall, Plus, Search, Filter, ArrowUpRight, Zap, 
  MessageSquare, Globe, Clock, CheckCircle2, RefreshCw 
} from 'lucide-react';
import { fetchInboundLeads, fetchAgents, simulateSpeedToLead } from '../api';
import { InboundLead, Agent } from '../types';
import { 
  Button, Card, CardHeader, CardTitle, CardDescription, CardContent,
  Badge, Input, Select, Dialog, Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
  EmptyState, LoadingState, ErrorState 
} from '../components/ui';

interface ContactsLeadsProps {
  onInitiateCall?: (customerName: string, customerPhone: string, agentId?: string) => void;
}

export const ContactsLeads: React.FC<ContactsLeadsProps> = ({ onInitiateCall }) => {
  const [leads, setLeads] = useState<InboundLead[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [sourceFilter, setSourceFilter] = useState('all');

  // New Lead / Speed-to-lead modal
  const [isSimulateOpen, setIsSimulateOpen] = useState(false);
  const [isSimulating, setIsSimulating] = useState(false);
  const [simulationResult, setSimulationResult] = useState<any>(null);
  const [formData, setFormData] = useState({
    lead_name: '',
    phone: '',
    source: 'website_form',
    product_interest: '',
    agent_id: '',
  });

  const loadData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [leadsRes, agentsRes] = await Promise.all([
        fetchInboundLeads(sourceFilter === 'all' ? undefined : sourceFilter),
        fetchAgents(),
      ]);
      setLeads(leadsRes || []);
      setAgents(agentsRes || []);
      if (agentsRes?.length > 0 && !formData.agent_id) {
        setFormData((prev) => ({ ...prev, agent_id: agentsRes[0].id }));
      }
    } catch (err: any) {
      console.error('Failed to load leads:', err);
      setError(err.message || 'Failed to fetch inbound leads and contacts.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [sourceFilter]);

  const handleSimulateSpeedToLead = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.lead_name || !formData.phone || !formData.agent_id) return;

    setIsSimulating(true);
    setSimulationResult(null);
    try {
      const res = await simulateSpeedToLead({
        agent_id: formData.agent_id,
        lead_name: formData.lead_name,
        phone: formData.phone,
        source: formData.source,
        product_interest: formData.product_interest || undefined,
      });
      setSimulationResult(res);
      await loadData();
    } catch (err: any) {
      alert(`Speed-to-lead error: ${err.message || 'Simulation failed'}`);
    } finally {
      setIsSimulating(false);
    }
  };

  const filteredLeads = leads.filter((lead) => {
    const q = searchQuery.toLowerCase();
    const matchName = lead.name?.toLowerCase().includes(q);
    const matchPhone = lead.phone?.toLowerCase().includes(q);
    const matchCampaign = lead.campaign_name?.toLowerCase().includes(q);
    const matchCustom = JSON.stringify(lead.custom_data || {}).toLowerCase().includes(q);
    return matchName || matchPhone || matchCampaign || matchCustom;
  });

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Contacts & Inbound Leads
            </h1>
            <Badge variant="success">Speed-to-Lead</Badge>
          </div>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Real-time lead capture, instant outbound qualification calls, and customer CRM records.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={loadData}
            leftIcon={<RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />}
          >
            Refresh
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              setSimulationResult(null);
              setIsSimulateOpen(true);
            }}
            leftIcon={<Zap className="w-4 h-4" />}
          >
            Simulate Speed-to-Lead
          </Button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row gap-4 items-center justify-between">
        <div className="w-full sm:w-80">
          <Input
            placeholder="Search leads by name, phone, or campaign..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            leftIcon={<Search className="w-4 h-4" />}
          />
        </div>
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <Select
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
            options={[
              { value: 'all', label: 'All Inbound Sources' },
              { value: 'website_form', label: 'Website Form' },
              { value: 'meta_ads', label: 'Meta Ads (Facebook/IG)' },
              { value: 'whatsapp_qr', label: 'WhatsApp QR / Direct' },
              { value: 'inbound_call', label: 'Inbound PSTN Call' },
            ]}
            containerClassName="w-full sm:w-56"
          />
        </div>
      </div>

      {/* Leads Table */}
      {isLoading ? (
        <LoadingState message="Loading contacts and inbound leads..." />
      ) : error ? (
        <ErrorState message={error} onRetry={loadData} />
      ) : filteredLeads.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No leads found"
          description="There are currently no inbound leads matching your criteria. Try changing filters or trigger a speed-to-lead simulation."
          actionLabel="Simulate Inbound Lead"
          onAction={() => setIsSimulateOpen(true)}
        />
      ) : (
        <div className="space-y-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Lead Contact</TableHead>
                <TableHead>Campaign & Details</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Speed to Lead</TableHead>
                <TableHead>Lead Score</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredLeads.map((lead) => {
                const isDispatched = !!lead.call_id;
                const productInterest = lead.custom_data?.product_interest || lead.campaign_name || 'General Inquiry';
                return (
                  <TableRow key={lead.id}>
                    <TableCell>
                      <div>
                        <div className="font-semibold text-slate-900 dark:text-white">
                          {lead.name}
                        </div>
                        <div className="text-xs font-mono text-slate-500 dark:text-slate-400">
                          {lead.phone}
                        </div>
                      </div>
                    </TableCell>

                    <TableCell>
                      <div>
                        <div className="text-sm font-medium text-slate-800 dark:text-slate-200">
                          {productInterest}
                        </div>
                        <div className="text-xs text-slate-400 dark:text-slate-500">
                          {lead.email || 'No email provided'}
                        </div>
                      </div>
                    </TableCell>

                    <TableCell>
                      <Badge variant="neutral" size="sm">
                        {lead.source?.replace('_', ' ')}
                      </Badge>
                    </TableCell>

                    <TableCell>
                      <div className="flex items-center gap-1.5 text-xs font-medium text-slate-600 dark:text-slate-300">
                        <Clock className="w-3.5 h-3.5 text-emerald-500" />
                        <span>{lead.response_time_seconds ? `${lead.response_time_seconds}s` : '< 15s (Instant)'}</span>
                      </div>
                    </TableCell>

                    <TableCell>
                      <span className="font-mono text-xs font-bold text-indigo-600 dark:text-indigo-400">
                        {lead.lead_score || 85}/100
                      </span>
                    </TableCell>

                    <TableCell>
                      <Badge
                        variant={
                          lead.status === 'called' || isDispatched
                            ? 'success'
                            : lead.status === 'pending'
                            ? 'warning'
                            : 'neutral'
                        }
                        size="sm"
                      >
                        {lead.status === 'called' || isDispatched ? 'Qualified / Called' : 'Pending Call'}
                      </Badge>
                    </TableCell>

                    <TableCell className="text-right">
                      <Button
                        variant="subtle"
                        size="xs"
                        onClick={() => {
                          if (onInitiateCall) {
                            onInitiateCall(lead.name, lead.phone, lead.agent_id);
                          } else {
                            alert(`Ready to dial ${lead.name} (${lead.phone}). Open Live Voice Studio.`);
                          }
                        }}
                        leftIcon={<PhoneCall className="w-3 h-3 text-indigo-600 dark:text-indigo-400" />}
                      >
                        Call Now
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Speed to Lead Simulation Dialog */}
      <Dialog
        isOpen={isSimulateOpen}
        onClose={() => setIsSimulateOpen(false)}
        title="Simulate Inbound Lead (Speed-to-Lead)"
        description="Emulate a high-value customer submitting an inquiry form or clicking a Meta ad."
      >
        {simulationResult ? (
          <div className="space-y-4">
            <div className="p-4 rounded-xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 text-emerald-900 dark:text-emerald-200">
              <div className="flex items-center gap-2 font-semibold text-sm">
                <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                <span>Speed-to-Lead Triggered!</span>
              </div>
              <p className="mt-1 text-xs text-emerald-700 dark:text-emerald-300">
                AI Agent dialed customer in <strong>{simulationResult.speed_to_lead_time_sec} seconds</strong>. Call record created.
              </p>
              <div className="mt-3 font-mono text-xs text-slate-700 dark:text-slate-300">
                Call ID: {simulationResult.call_id}
              </div>
            </div>
            <div className="flex justify-end pt-2">
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  setSimulationResult(null);
                  setIsSimulateOpen(false);
                }}
              >
                Done
              </Button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSimulateSpeedToLead} className="space-y-4">
            <Input
              label="Customer Name"
              placeholder="e.g. Vikram Sharma"
              value={formData.lead_name}
              onChange={(e) => setFormData({ ...formData, lead_name: e.target.value })}
              required
            />

            <Input
              label="Phone Number"
              placeholder="+919876543210"
              value={formData.phone}
              onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
              required
              helperText="Indian mobile format (+91XXXXXXXXXX) or E.164"
            />

            <Select
              label="Assign Voice Agent"
              value={formData.agent_id}
              onChange={(e) => setFormData({ ...formData, agent_id: e.target.value })}
              options={agents.map((a) => ({
                value: a.id,
                label: `${a.name} (${a.company || 'Enterprise'})`,
              }))}
            />

            <Select
              label="Inbound Lead Channel"
              value={formData.source}
              onChange={(e) => setFormData({ ...formData, source: e.target.value })}
              options={[
                { value: 'website_form', label: 'Website Pricing / Demo Form' },
                { value: 'meta_ads', label: 'Facebook / Instagram Lead Ad' },
                { value: 'whatsapp_qr', label: 'WhatsApp Scan / Direct Message' },
                { value: 'inbound_call', label: 'Inbound PSTN Missed Call' },
              ]}
            />

            <Input
              label="Product / Service Interest"
              placeholder="e.g. 3BHK Luxury Villa in Whitefield"
              value={formData.product_interest}
              onChange={(e) => setFormData({ ...formData, product_interest: e.target.value })}
            />

            <div className="flex justify-end gap-3 pt-4 border-t border-slate-100 dark:border-slate-800">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setIsSimulateOpen(false)}
                disabled={isSimulating}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                size="sm"
                isLoading={isSimulating}
                leftIcon={<Zap className="w-3.5 h-3.5" />}
              >
                Fire Speed-to-Lead
              </Button>
            </div>
          </form>
        )}
      </Dialog>
    </div>
  );
};
