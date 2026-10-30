import React, { useState, useEffect } from 'react';
import { 
  Building2, Plus, ShieldCheck, Database, Bot, Globe, CheckCircle2, 
  Search, RefreshCw 
} from 'lucide-react';
import { 
  fetchTenantWorkspaces, onboardCompanyTenant, fetchAgents, fetchKnowledgeDocs 
} from '../api';
import { TenantWorkspace, Agent, KnowledgeDoc } from '../types';
import { 
  Button, Card, CardHeader, CardTitle, CardDescription, CardContent, 
  Badge, Input, Select, Dialog, EmptyState, LoadingState, ErrorState 
} from '../components/ui';

export const Companies: React.FC = () => {
  const [workspaces, setWorkspaces] = useState<TenantWorkspace[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [docs, setDocs] = useState<KnowledgeDoc[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null);

  // New Company Modal State
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formData, setFormData] = useState({
    company_name: '',
    industry: 'Technology & SaaS',
    products_services: '',
    target_audience: '',
  });

  const loadData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [tenantsRes, agentsRes, docsRes] = await Promise.all([
        fetchTenantWorkspaces(),
        fetchAgents(),
        fetchKnowledgeDocs(),
      ]);
      setWorkspaces(tenantsRes || []);
      setAgents(agentsRes || []);
      setDocs(docsRes || []);
      if (tenantsRes?.length > 0 && !selectedOrgId) {
        setSelectedOrgId(tenantsRes[0].organization_id);
      }
    } catch (err: any) {
      console.error('Failed to load companies:', err);
      setError(err.message || 'Failed to fetch companies and tenant workspaces.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleCreateCompany = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.company_name.trim()) return;

    setIsSubmitting(true);
    try {
      const newTenant = await onboardCompanyTenant({
        company_name: formData.company_name.trim(),
        industry: formData.industry,
        products_services: formData.products_services.trim() || undefined,
        target_audience: formData.target_audience.trim() || undefined,
      });
      setWorkspaces((prev) => [...prev, newTenant]);
      setSelectedOrgId(newTenant.organization_id);
      setIsCreateOpen(false);
      setFormData({
        company_name: '',
        industry: 'Technology & SaaS',
        products_services: '',
        target_audience: '',
      });
    } catch (err: any) {
      alert(`Error creating company tenant: ${err.message || 'Unknown error'}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const filteredWorkspaces = workspaces.filter((ws) =>
    ws.company_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    ws.organization_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (ws.industry && ws.industry.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const activeTenant = workspaces.find((w) => w.organization_id === selectedOrgId) || workspaces[0];
  const tenantAgents = agents.filter((a) => 
    a.company?.toLowerCase() === activeTenant?.company_name?.toLowerCase()
  );
  const tenantDocs = docs.filter((d) => 
    d.organization_id === activeTenant?.organization_id
  );

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Company Workspaces
            </h1>
            <Badge variant="indigo">Multi-Tenant</Badge>
          </div>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Enterprise isolation boundaries, AI agent assignments, and grounded knowledge security.
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
            onClick={() => setIsCreateOpen(true)}
            leftIcon={<Plus className="w-4 h-4" />}
          >
            Add Company
          </Button>
        </div>
      </div>

      {isLoading ? (
        <LoadingState message="Loading company tenant workspaces..." />
      ) : error ? (
        <ErrorState message={error} onRetry={loadData} />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* Left Column: Tenant Directory */}
          <div className="lg:col-span-5 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                Directory ({workspaces.length})
              </h2>
            </div>

            <Input
              type="text"
              placeholder="Search by company or ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              leftIcon={<Search className="w-4 h-4" />}
            />

            <div className="space-y-2.5 max-h-[640px] overflow-y-auto pr-1">
              {filteredWorkspaces.length === 0 ? (
                <EmptyState
                  icon={Building2}
                  title="No companies found"
                  description="No tenant workspaces match your query. Add a new company to get started."
                />
              ) : (
                filteredWorkspaces.map((ws) => {
                  const isSelected = ws.organization_id === selectedOrgId;
                  const orgAgentCount = agents.filter(
                    (a) => a.company?.toLowerCase() === ws.company_name?.toLowerCase()
                  ).length;
                  const orgDocCount = docs.filter(
                    (d) => d.organization_id === ws.organization_id
                  ).length;

                  return (
                    <div
                      key={ws.organization_id}
                      onClick={() => setSelectedOrgId(ws.organization_id)}
                      className={`
                        p-4 rounded-xl border cursor-pointer transition-all text-left
                        ${
                          isSelected
                            ? 'bg-indigo-50/70 dark:bg-indigo-950/30 border-indigo-500 dark:border-indigo-500 shadow-sm'
                            : 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700'
                        }
                      `}
                    >
                      <div className="flex items-start justify-between">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-slate-900 dark:text-white">
                              {ws.company_name}
                            </span>
                            <Badge variant="success" size="sm">Active</Badge>
                          </div>
                          <span className="text-xs font-mono text-slate-400 dark:text-slate-500 mt-0.5 block">
                            {ws.organization_id}
                          </span>
                        </div>
                        <Badge variant="neutral" size="sm">{ws.industry || 'Enterprise'}</Badge>
                      </div>

                      <div className="mt-3 flex items-center gap-4 text-xs text-slate-500 dark:text-slate-400">
                        <span className="flex items-center gap-1">
                          <Bot className="w-3.5 h-3.5 text-indigo-500" />
                          {orgAgentCount} {orgAgentCount === 1 ? 'Agent' : 'Agents'}
                        </span>
                        <span className="flex items-center gap-1">
                          <Database className="w-3.5 h-3.5 text-emerald-500" />
                          {orgDocCount} {orgDocCount === 1 ? 'Doc' : 'Docs'}
                        </span>
                        <span className="flex items-center gap-1">
                          <ShieldCheck className="w-3.5 h-3.5 text-amber-500" />
                          Isolated
                        </span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Right Column: Tenant Details & Scoped Resources */}
          <div className="lg:col-span-7">
            {activeTenant ? (
              <div className="space-y-6">
                <Card>
                  <CardHeader>
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2.5">
                          <Building2 className="w-6 h-6 text-indigo-600 dark:text-indigo-400" />
                          <CardTitle className="text-xl">{activeTenant.company_name}</CardTitle>
                        </div>
                        <CardDescription className="mt-1">
                          Organization ID: <span className="font-mono text-xs text-slate-700 dark:text-slate-300">{activeTenant.organization_id}</span>
                        </CardDescription>
                      </div>
                      <Badge variant="purple" size="md">Strict Isolation</Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    {/* Metadata Grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 p-4 rounded-xl bg-slate-50 dark:bg-slate-950/60 border border-slate-200/80 dark:border-slate-800">
                      <div>
                        <p className="text-xs uppercase font-medium text-slate-500 dark:text-slate-400">Industry</p>
                        <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">
                          {activeTenant.industry || 'Enterprise'}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs uppercase font-medium text-slate-500 dark:text-slate-400">Products & Services</p>
                        <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white truncate">
                          {activeTenant.products_services || 'General Catalog'}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs uppercase font-medium text-slate-500 dark:text-slate-400">Target Audience</p>
                        <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white truncate">
                          {activeTenant.target_audience || 'B2B / B2C Buyers'}
                        </p>
                      </div>
                    </div>

                    {/* Assigned Voice Agents */}
                    <div>
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-1.5">
                          <Bot className="w-4 h-4 text-indigo-500" />
                          Assigned Voice Employees ({tenantAgents.length})
                        </h3>
                      </div>
                      {tenantAgents.length === 0 ? (
                        <p className="text-xs text-slate-500 dark:text-slate-400 italic p-3 rounded-lg border border-dashed border-slate-200 dark:border-slate-800">
                          No voice agents matching this company name yet. Create or assign an agent to {activeTenant.company_name}.
                        </p>
                      ) : (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          {tenantAgents.map((agent) => (
                            <div
                              key={agent.id}
                              className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center justify-between"
                            >
                              <div>
                                <p className="text-sm font-medium text-slate-900 dark:text-white">
                                  {agent.name}
                                </p>
                                <p className="text-xs text-slate-500 dark:text-slate-400">
                                  {agent.blueprint.replace('_', ' ')} • {agent.default_language}
                                </p>
                              </div>
                              <Badge variant={agent.is_active ? 'success' : 'neutral'} size="sm">
                                {agent.is_active ? 'Active' : 'Draft'}
                              </Badge>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Grounded Knowledge Documents */}
                    <div>
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-1.5">
                          <Database className="w-4 h-4 text-emerald-500" />
                          Grounded Knowledge Documents ({tenantDocs.length})
                        </h3>
                      </div>
                      {tenantDocs.length === 0 ? (
                        <p className="text-xs text-slate-500 dark:text-slate-400 italic p-3 rounded-lg border border-dashed border-slate-200 dark:border-slate-800">
                          No RAG knowledge documents ingested for this tenant yet. Ingest a document or website in Knowledge Hub.
                        </p>
                      ) : (
                        <div className="space-y-2">
                          {tenantDocs.slice(0, 4).map((doc) => {
                            const isApproved = doc.approval_status === 'approved';
                            return (
                              <div
                                key={doc.id}
                                className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center justify-between text-xs"
                              >
                                <div>
                                  <p className="font-medium text-slate-900 dark:text-white truncate max-w-xs">
                                    {doc.title}
                                  </p>
                                  <p className="text-slate-500 dark:text-slate-400 text-[11px]">
                                    Source: {doc.source_type} • Chunks: {doc.chunks_count || 1}
                                  </p>
                                </div>
                                <Badge variant={isApproved ? 'success' : 'warning'} size="sm">
                                  {isApproved ? 'Approved' : 'Pending Review'}
                                </Badge>
                              </div>
                            );
                          })}
                          {tenantDocs.length > 4 && (
                            <p className="text-xs text-center text-slate-500 dark:text-slate-400 pt-1">
                              + {tenantDocs.length - 4} more documents in Knowledge Hub
                            </p>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Security Compliance Note */}
                    <div className="p-3.5 rounded-lg bg-emerald-50/50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-900/40 text-xs text-emerald-800 dark:text-emerald-300 flex items-start gap-2.5">
                      <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 flex-shrink-0 mt-0.5" />
                      <div>
                        <span className="font-semibold">Tenant Boundary Enforced: </span>
                        All outbound calls, embeddings, and vector similarity queries are strictly filtered with <code className="px-1 py-0.5 bg-emerald-100 dark:bg-emerald-900/50 rounded font-mono text-[11px]">organization_id = '{activeTenant.organization_id}'</code>. Zero cross-company data leakage.
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            ) : (
              <EmptyState
                icon={Building2}
                title="Select a company"
                description="Choose a company workspace from the directory to review its isolated configuration."
              />
            )}
          </div>
        </div>
      )}

      {/* Add Company Dialog */}
      <Dialog
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Onboard New Company"
        description="Create an isolated tenant workspace for your client or business unit."
      >
        <form onSubmit={handleCreateCompany} className="space-y-4">
          <Input
            label="Company Legal Name"
            placeholder="e.g. Acme Health Technologies"
            value={formData.company_name}
            onChange={(e) => setFormData({ ...formData, company_name: e.target.value })}
            required
          />

          <Select
            label="Industry Domain"
            value={formData.industry}
            onChange={(e) => setFormData({ ...formData, industry: e.target.value })}
            options={[
              { value: 'Technology & SaaS', label: 'Technology & SaaS' },
              { value: 'Real Estate & Property', label: 'Real Estate & Property' },
              { value: 'Healthcare & Clinics', label: 'Healthcare & Clinics' },
              { value: 'Education & Admissions', label: 'Education & Admissions' },
              { value: 'BFSI & Fintech', label: 'BFSI & Fintech' },
              { value: 'E-Commerce & Retail', label: 'E-Commerce & Retail' },
              { value: 'Other', label: 'Other Enterprise' },
            ]}
          />

          <Input
            label="Products & Services Catalog Summary"
            placeholder="e.g. Cloud ERP Software, Payroll Modules"
            value={formData.products_services}
            onChange={(e) => setFormData({ ...formData, products_services: e.target.value })}
          />

          <Input
            label="Target Audience"
            placeholder="e.g. CFOs, IT Directors, Indian SMEs"
            value={formData.target_audience}
            onChange={(e) => setFormData({ ...formData, target_audience: e.target.value })}
          />

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-100 dark:border-slate-800">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setIsCreateOpen(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              size="sm"
              isLoading={isSubmitting}
            >
              Create Workspace
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
};
