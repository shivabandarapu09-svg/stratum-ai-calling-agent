import React, { useEffect, useState } from 'react';
import {
  BookOpen, Plus, Search, FileText, CheckCircle, Database,
  ShieldAlert, Globe, Building2, Upload, Ban, Trash2, History, AlertTriangle, RefreshCw
} from 'lucide-react';
import { KnowledgeDoc, TenantWorkspace, KnowledgeAuditLog } from '../types';
import {
  fetchTenantWorkspaces, onboardCompanyTenant,
  fetchKnowledgeDocs, ingestWebsiteSource, ingestDocumentFile,
  approveOrDisableKnowledgeDoc, deleteKnowledgeDoc, searchKnowledge, fetchKnowledgeAuditLogs
} from '../api';
import { 
  Button, Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter,
  Badge, Input, Textarea, Select, Dialog, EmptyState, LoadingState 
} from '../components/ui';

export const KnowledgeBase: React.FC = () => {
  const [tenants, setTenants] = useState<TenantWorkspace[]>([]);
  const [activeTenantId, setActiveTenantId] = useState<string>('');
  const [docs, setDocs] = useState<KnowledgeDoc[]>([]);
  const [auditLogs, setAuditLogs] = useState<KnowledgeAuditLog[]>([]);
  const [statusBanner, setStatusBanner] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  // Modals
  const [showOnboardModal, setShowOnboardModal] = useState<boolean>(false);
  const [showIngestModal, setShowIngestModal] = useState<'website' | 'document' | null>(null);

  // Onboarding Form State
  const [newCompanyName, setNewCompanyName] = useState<string>('');
  const [newIndustry, setNewIndustry] = useState<string>('Solar & CleanTech');
  const [newProducts, setNewProducts] = useState<string>('');
  const [newAudience, setNewAudience] = useState<string>('');
  const [newObjectives, setNewObjectives] = useState<string>('');
  const [newTone, setNewTone] = useState<string>('Warm, Consultative, Respectful & Truthful');
  const [newInstructions, setNewInstructions] = useState<string>('');
  const [newDomains, setNewDomains] = useState<string>('');

  // Ingestion Form State
  const [websiteUrl, setWebsiteUrl] = useState<string>('https://stratum.ai/docs/pricing');
  const [websiteHtmlPreview, setWebsiteHtmlPreview] = useState<string>(
    '<html><head><title>Official Pricing & SLA</title></head><body><h1>Enterprise Calling Plans</h1><p>Usage starts at ₹4.50/min with 99.95% uptime SLA and 24/7 priority human transfer.</p></body></html>'
  );
  const [docFileName, setDocFileName] = useState<string>('Company_Policy_v1.txt');
  const [docTitle, setDocTitle] = useState<string>('');
  const [docRawText, setDocRawText] = useState<string>('');
  const [docBase64, setDocBase64] = useState<string>('');

  // Semantic Search Tester
  const [testQuery, setTestQuery] = useState<string>('Prestige Sky Meadows 3 BHK price and possession date');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState<boolean>(false);

  const activeWorkspace = tenants.find((t) => t.organization_id === activeTenantId) || tenants[0];

  const loadTenantData = async (orgId: string) => {
    if (!orgId) return;
    try {
      const [docsData, logsData] = await Promise.all([
        fetchKnowledgeDocs(orgId),
        fetchKnowledgeAuditLogs(orgId),
      ]);
      setDocs(docsData || []);
      setAuditLogs(logsData || []);
    } catch (e) {
      console.error('Error loading tenant knowledge:', e);
    }
  };

  useEffect(() => {
    setLoading(true);
    fetchTenantWorkspaces().then((list) => {
      setTenants(list || []);
      if (list && list.length > 0) {
        const initialOrg = list[0].organization_id;
        setActiveTenantId(initialOrg);
        loadTenantData(initialOrg);
      }
      setLoading(false);
    });
  }, []);

  const handleTenantSwitch = (orgId: string) => {
    setActiveTenantId(orgId);
    setSearchResults([]);
    loadTenantData(orgId);
  };

  const handleOnboardTenant = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const created = await onboardCompanyTenant({
        company_name: newCompanyName,
        industry: newIndustry,
        products_services: newProducts,
        target_audience: newAudience,
        call_objectives: newObjectives,
        tone: newTone,
        instructor_instructions: newInstructions,
        allowed_website_domains: newDomains.split(',').map((s) => s.trim()).filter(Boolean),
        require_instructor_approval: true,
      });
      setTenants([...tenants, created]);
      setActiveTenantId(created.organization_id);
      await loadTenantData(created.organization_id);
      setShowOnboardModal(false);
      setNewCompanyName('');
      setStatusBanner({ type: 'success', text: `Onboarded isolated tenant workspace for ${created.company_name}.` });
    } catch (err: any) {
      setStatusBanner({ type: 'error', text: err.message || 'Failed to onboard company' });
    }
  };

  const handleWebsiteIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeTenantId) return;
    try {
      const simulatedMap = websiteHtmlPreview.trim() ? { [websiteUrl.trim()]: websiteHtmlPreview } : undefined;
      const ingested = await ingestWebsiteSource({
        organization_id: activeTenantId,
        url: websiteUrl.trim(),
        max_pages: 2,
        simulated_html_pages: simulatedMap,
        auto_approve: false,
      });
      await loadTenantData(activeTenantId);
      setShowIngestModal(null);
      setStatusBanner({
        type: 'success',
        text: `Ingested ${ingested.length} page(s) in 'pending_review' state. Instructor approval is required before live calls use this source.`,
      });
    } catch (err: any) {
      setStatusBanner({ type: 'error', text: err.message || 'Website ingestion blocked' });
    }
  };

  const handleFileUploadChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setDocFileName(file.name);
    if (!docTitle) setDocTitle(file.name);
    const reader = new FileReader();
    reader.onload = () => {
      const resStr = reader.result as string;
      const base64Part = resStr.includes(',') ? resStr.split(',')[1] : resStr;
      setDocBase64(base64Part);
    };
    reader.readAsDataURL(file);
  };

  const handleDocumentIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeTenantId) return;
    try {
      const created = await ingestDocumentFile({
        organization_id: activeTenantId,
        file_name: docFileName,
        title: docTitle || docFileName,
        file_content_base64: docBase64 || undefined,
        raw_text: docRawText || undefined,
        auto_approve: false,
      });
      await loadTenantData(activeTenantId);
      setShowIngestModal(null);
      setDocRawText('');
      setDocBase64('');
      setStatusBanner({
        type: 'success',
        text: `Parsed & indexed '${created.title}' (${created.chunks_count} chunks). Status: ${created.approval_status}.`,
      });
    } catch (err: any) {
      setStatusBanner({ type: 'error', text: err.message || 'Document ingestion failed' });
    }
  };

  const handleApprovalAction = async (docId: string, action: 'approve' | 'disable') => {
    if (!activeTenantId) return;
    await approveOrDisableKnowledgeDoc(docId, activeTenantId, action);
    await loadTenantData(activeTenantId);
    setStatusBanner({
      type: 'success',
      text: action === 'approve'
        ? 'Source approved by instructor and activated for production calls.'
        : 'Source disabled and evicted from tenant retrieval cache.',
    });
  };

  const handleDeleteDoc = async (docId: string) => {
    if (!activeTenantId) return;
    await deleteKnowledgeDoc(docId, activeTenantId);
    await loadTenantData(activeTenantId);
    setStatusBanner({ type: 'success', text: 'Source and chunks deleted; tenant cache invalidated.' });
  };

  const handleTestSearch = async () => {
    if (!testQuery.trim() || !activeTenantId) return;
    setIsSearching(true);
    try {
      const results = await searchKnowledge(testQuery, undefined, activeTenantId);
      setSearchResults(results || []);
    } catch (e) {
      console.error('Search error:', e);
    } finally {
      setIsSearching(false);
    }
  };

  const approvedCount = docs.filter((d) => d.approval_status === 'approved').length;
  const pendingCount = docs.filter((d) => d.approval_status === 'pending_review').length;

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header & Tenant Selector */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Knowledge Hub (RAG)
            </h1>
            <Badge variant="purple">Tenant-Grounded</Badge>
          </div>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">
            Ingest company websites and documents, inspect extracted product facts and FAQs, and approve sources before production calls.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl px-3 py-1.5 shadow-2xs">
            <Building2 className="w-4 h-4 text-indigo-500" />
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Workspace:</span>
            <select
              value={activeTenantId}
              onChange={(e) => handleTenantSwitch(e.target.value)}
              className="bg-transparent text-slate-900 dark:text-white text-xs font-semibold focus:outline-none cursor-pointer"
            >
              {tenants.map((t) => (
                <option key={t.organization_id} value={t.organization_id} className="bg-white dark:bg-slate-900 text-slate-900 dark:text-white">
                  {t.company_name} ({t.industry})
                </option>
              ))}
            </select>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowOnboardModal(true)}
            leftIcon={<Plus className="w-3.5 h-3.5" />}
          >
            Onboard Tenant
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowIngestModal('website')}
            leftIcon={<Globe className="w-3.5 h-3.5" />}
          >
            Ingest Website
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={() => setShowIngestModal('document')}
            leftIcon={<Upload className="w-3.5 h-3.5" />}
          >
            Upload Document
          </Button>
        </div>
      </div>

      {statusBanner && (
        <div
          className={`p-3.5 rounded-xl border text-xs flex items-center justify-between ${
            statusBanner.type === 'success'
              ? 'bg-emerald-50 dark:bg-emerald-950/50 border-emerald-200 dark:border-emerald-700/60 text-emerald-800 dark:text-emerald-300'
              : 'bg-rose-50 dark:bg-rose-950/60 border-rose-200 dark:border-rose-700/60 text-rose-800 dark:text-rose-300'
          }`}
        >
          <span>{statusBanner.text}</span>
          <button
            onClick={() => setStatusBanner(null)}
            className="text-slate-400 hover:text-slate-600 dark:hover:text-white ml-4 font-semibold"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Company Profile, Product Overview, FAQs & Readiness Warning */}
      {activeWorkspace && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <Building2 className="w-4 h-4 text-indigo-500" />
                {activeWorkspace.company_name} — Knowledge Boundary
              </CardTitle>
              <div className="flex items-center gap-2">
                <Badge variant={approvedCount > 0 ? 'success' : 'warning'} size="sm">
                  {approvedCount} Approved Sources
                </Badge>
                {pendingCount > 0 && (
                  <Badge variant="warning" size="sm">
                    {pendingCount} Pending Review
                  </Badge>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs bg-slate-50 dark:bg-slate-950/60 p-4 rounded-xl border border-slate-200 dark:border-slate-800">
              <div>
                <span className="text-slate-400 dark:text-slate-500 uppercase font-semibold text-[10px] block">Company & Industry</span>
                <p className="text-slate-900 dark:text-white font-semibold mt-0.5">{activeWorkspace.company_name}</p>
                <p className="text-slate-500 dark:text-slate-400 mt-0.5">{activeWorkspace.industry} • {activeWorkspace.tone}</p>
              </div>
              <div>
                <span className="text-slate-400 dark:text-slate-500 uppercase font-semibold text-[10px] block">Products & Services</span>
                <p className="text-slate-700 dark:text-slate-300 mt-0.5 line-clamp-2">{activeWorkspace.products_services || 'Catalog not specified'}</p>
                <p className="text-indigo-600 dark:text-indigo-400 mt-0.5 line-clamp-1">{activeWorkspace.call_objectives}</p>
              </div>
              <div>
                <span className="text-slate-400 dark:text-slate-500 uppercase font-semibold text-[10px] block">Instructor Policies</span>
                <p className="text-slate-700 dark:text-slate-300 mt-0.5 line-clamp-2">
                  {activeWorkspace.instructor_instructions || 'Cite approved documents only; never invent pricing or commitments.'}
                </p>
              </div>
              <div>
                <span className="text-slate-400 dark:text-slate-500 uppercase font-semibold text-[10px] block">Freshness Cadence</span>
                <p className="text-slate-700 dark:text-slate-300 mt-0.5 font-medium">
                  Auto-sync every {activeWorkspace.freshness_policy_hours} hours
                </p>
                <span className="text-[11px] text-emerald-600 dark:text-emerald-400 mt-0.5 block font-mono">
                  Isolation: Strict
                </span>
              </div>
            </div>

            {/* Missing Knowledge Warning if 0 approved docs */}
            {approvedCount === 0 && (
              <div className="p-3.5 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/70 rounded-xl text-xs text-amber-800 dark:text-amber-200 flex items-center gap-2.5">
                <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
                <span>
                  <strong>Attention:</strong> This company currently has 0 approved knowledge sources. Live calls will rely only on basic company metadata and will decline factual product/pricing commitments until at least one source is approved.
                </span>
              </div>
            )}

            {/* Company FAQs Preview (if defined) */}
            {activeWorkspace.faqs && activeWorkspace.faqs.length > 0 && (
              <div>
                <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 block mb-2">
                  Company FAQs ({activeWorkspace.faqs.length})
                </span>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                  {activeWorkspace.faqs.slice(0, 4).map((faq, idx) => (
                    <div key={idx} className="p-3 bg-slate-50 dark:bg-slate-950/60 rounded-xl border border-slate-200 dark:border-slate-800 text-xs">
                      <strong className="text-slate-900 dark:text-slate-200 block mb-0.5">Q: {faq.question}</strong>
                      <span className="text-slate-600 dark:text-slate-400">A: {faq.answer}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left: Tenant Knowledge Sources & Approval Queue (7 cols) */}
        <div className="lg:col-span-7 space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base flex items-center gap-2">
                  <Database className="w-4 h-4 text-indigo-500" />
                  Ingested Knowledge Sources ({docs.length})
                </CardTitle>
                <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
                  SSRF & Injection Guarded
                </span>
              </div>
            </CardHeader>
            <CardContent>
              {docs.length === 0 ? (
                <EmptyState
                  icon={BookOpen}
                  title="No sources ingested"
                  description="No documents or website pages ingested for this company yet. Click 'Ingest Website' or 'Upload Document' to add grounded facts."
                  actionLabel="Ingest Website"
                  onAction={() => setShowIngestModal('website')}
                />
              ) : (
                <div className="space-y-3.5">
                  {docs.map((d) => (
                    <div
                      key={d.id}
                      className="bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 rounded-xl p-4 hover:border-slate-300 dark:hover:border-slate-700 transition-colors"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
                        <div className="flex items-center gap-2">
                          {d.source_type === 'url' ? (
                            <Globe className="w-4 h-4 text-indigo-500" />
                          ) : (
                            <FileText className="w-4 h-4 text-emerald-500" />
                          )}
                          <div>
                            <h3 className="text-xs font-semibold text-slate-900 dark:text-white">{d.title}</h3>
                            {d.canonical_url && (
                              <span className="text-[10px] text-indigo-600 dark:text-indigo-400 font-mono block">{d.canonical_url}</span>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-1.5">
                          <span className="bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-800 text-[10px] font-mono px-2 py-0.5 rounded">
                            v{d.version || 1} • {d.chunks_count} Chunks
                          </span>
                          <Badge
                            variant={
                              d.approval_status === 'approved'
                                ? 'success'
                                : d.approval_status === 'pending_review'
                                ? 'warning'
                                : 'danger'
                            }
                            size="sm"
                          >
                            {(d.approval_status || 'approved').toUpperCase()}
                          </Badge>
                        </div>
                      </div>

                      {d.prompt_injection_flagged && (
                        <div className="mb-2 p-2 rounded-lg bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-800 text-[11px] text-rose-700 dark:text-rose-300 flex items-center gap-2">
                          <ShieldAlert className="w-4 h-4 text-rose-500 shrink-0" />
                          <span>
                            Prompt-injection pattern neutralized ({(d.sanitized_warnings || []).join(', ')}).
                          </span>
                        </div>
                      )}

                      <p className="text-xs text-slate-600 dark:text-slate-400 line-clamp-3 bg-white dark:bg-slate-900 p-2.5 rounded-lg border border-slate-200 dark:border-slate-800/80 leading-relaxed font-mono">
                        {d.content}
                      </p>

                      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500">
                        <div>
                          <span>Format: {d.source_type.toUpperCase()}</span>
                          {d.content_hash && <span className="ml-3 font-mono">Hash: {d.content_hash.slice(0, 10)}…</span>}
                        </div>

                        <div className="flex items-center gap-2">
                          {d.approval_status !== 'approved' && (
                            <Button
                              variant="primary"
                              size="xs"
                              onClick={() => handleApprovalAction(d.id, 'approve')}
                              leftIcon={<CheckCircle className="w-3 h-3" />}
                            >
                              Approve for Calls
                            </Button>
                          )}
                          {d.approval_status === 'approved' && (
                            <Button
                              variant="outline"
                              size="xs"
                              onClick={() => handleApprovalAction(d.id, 'disable')}
                              leftIcon={<Ban className="w-3 h-3" />}
                            >
                              Disable
                            </Button>
                          )}
                          <Button
                            variant="danger"
                            size="xs"
                            onClick={() => handleDeleteDoc(d.id)}
                            leftIcon={<Trash2 className="w-3 h-3" />}
                          >
                            Delete
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right: Citation-Grounded RAG Tester & Audit Trail (5 cols) */}
        <div className="lg:col-span-5 space-y-6">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base flex items-center gap-2">
                  <BookOpen className="w-4 h-4 text-indigo-500" />
                  Retrieval & Citation Sandbox
                </CardTitle>
                <Badge variant="indigo" size="sm">Approved Only</Badge>
              </div>
              <CardDescription className="text-xs">
                Test what facts and citations the voice AI retrieves for {activeWorkspace?.company_name}.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2">
                <Input
                  value={testQuery}
                  onChange={(e) => setTestQuery(e.target.value)}
                  placeholder="Ask a product, pricing, or policy question..."
                  containerClassName="flex-1"
                />
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleTestSearch}
                  isLoading={isSearching}
                  leftIcon={<Search className="w-3.5 h-3.5" />}
                >
                  Retrieve
                </Button>
              </div>

              <div className="space-y-2.5 pt-1">
                <span className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider block">
                  Retrieved Chunks & Citations ({searchResults.length})
                </span>

                {searchResults.length === 0 ? (
                  <div className="bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 rounded-xl p-4 text-center text-slate-400 dark:text-slate-500 text-xs">
                    No approved chunks matched. The voice agent will abstain from inventing unverified facts.
                  </div>
                ) : (
                  searchResults.map((r, idx) => (
                    <div key={idx} className="bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 rounded-xl p-3 space-y-1.5 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-slate-900 dark:text-slate-200">{r.document_title}</span>
                        <span className="font-mono text-[10px] text-emerald-700 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-950 px-2 py-0.5 rounded border border-emerald-300 dark:border-emerald-800 font-semibold">
                          Match: {(r.score * 100).toFixed(1)}%
                        </span>
                      </div>
                      {r.citation && (
                        <div className="text-[10px] font-mono text-indigo-700 dark:text-indigo-300 bg-indigo-50 dark:bg-indigo-950/50 px-2 py-0.5 rounded border border-indigo-200 dark:border-indigo-800/50">
                          {r.citation}
                        </div>
                      )}
                      <p className="text-slate-600 dark:text-slate-400 text-[11px] leading-relaxed">"{r.text}"</p>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>

          {/* Audit Log */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center gap-2">
                <History className="w-4 h-4 text-indigo-500" />
                Knowledge Governance Audit Log
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 max-h-52 overflow-y-auto pr-1">
                {auditLogs.length === 0 ? (
                  <p className="text-xs text-slate-500">No lifecycle audit events yet.</p>
                ) : (
                  auditLogs.slice(0, 8).map((log) => (
                    <div key={log.id} className="bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800/80 rounded-lg p-2.5 text-[11px] flex items-center justify-between">
                      <div>
                        <span className="font-mono font-semibold text-slate-800 dark:text-slate-200">{log.action}</span>
                        <span className="text-slate-500 dark:text-slate-400 ml-2">by {log.actor}</span>
                      </div>
                      <Badge variant={log.status === 'success' ? 'success' : 'danger'} size="sm">
                        {log.status}
                      </Badge>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Modal 1: Onboard New Company Workspace */}
      <Dialog
        isOpen={showOnboardModal}
        onClose={() => setShowOnboardModal(false)}
        title="Onboard Company Workspace"
        description="Establish an isolated enterprise knowledge container."
      >
        <form onSubmit={handleOnboardTenant} className="space-y-3 text-xs">
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Company Name *"
              required
              placeholder="e.g. Aura Solar Energy Pvt Ltd"
              value={newCompanyName}
              onChange={(e) => setNewCompanyName(e.target.value)}
            />
            <Input
              label="Industry *"
              required
              value={newIndustry}
              onChange={(e) => setNewIndustry(e.target.value)}
            />
          </div>

          <Input
            label="Products & Services"
            placeholder="Rooftop solar panels, 3kW to 10kW residential systems..."
            value={newProducts}
            onChange={(e) => setNewProducts(e.target.value)}
          />

          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Target Audience"
              placeholder="Independent house owners & RWAs"
              value={newAudience}
              onChange={(e) => setNewAudience(e.target.value)}
            />
            <Input
              label="Call Objectives"
              placeholder="Qualify electricity bill & book survey"
              value={newObjectives}
              onChange={(e) => setNewObjectives(e.target.value)}
            />
          </div>

          <Input
            label="Approved Website Domains (comma-separated)"
            placeholder="aurasolar.in, docs.aurasolar.in"
            value={newDomains}
            onChange={(e) => setNewDomains(e.target.value)}
          />

          <Textarea
            label="Instructor Rules & Escalation Policy"
            rows={3}
            placeholder="Never quote subsidy amounts outside official table..."
            value={newInstructions}
            onChange={(e) => setNewInstructions(e.target.value)}
          />

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-100 dark:border-slate-800">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setShowOnboardModal(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              size="sm"
            >
              Create Workspace
            </Button>
          </div>
        </form>
      </Dialog>

      {/* Modal 2: Website Ingestion or Document Upload */}
      <Dialog
        isOpen={showIngestModal !== null}
        onClose={() => setShowIngestModal(null)}
        title={
          showIngestModal === 'website'
            ? 'Ingest Website URL (SSRF & Robots.txt Protected)'
            : 'Upload Document (PDF, DOCX, CSV, TXT, MD, JSON)'
        }
        description="Parse and index grounded company content into isolated chunks."
      >
        {showIngestModal === 'website' ? (
          <form onSubmit={handleWebsiteIngest} className="space-y-3 text-xs">
            <Input
              label="Target Website URL *"
              required
              value={websiteUrl}
              onChange={(e) => setWebsiteUrl(e.target.value)}
            />

            <Textarea
              label="Page HTML Content (Optional offline preview / test fixture)"
              rows={5}
              value={websiteHtmlPreview}
              onChange={(e) => setWebsiteHtmlPreview(e.target.value)}
            />

            <div className="flex justify-end gap-3 pt-4 border-t border-slate-100 dark:border-slate-800">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setShowIngestModal(null)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                size="sm"
              >
                Crawl & Queue for Approval
              </Button>
            </div>
          </form>
        ) : (
          <form onSubmit={handleDocumentIngest} className="space-y-3 text-xs">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-1.5">
                Select File (or paste text below)
              </label>
              <input
                type="file"
                accept=".pdf,.docx,.csv,.txt,.md,.json,.html"
                onChange={handleFileUploadChange}
                className="w-full text-slate-700 dark:text-slate-300 text-xs file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-indigo-50 file:text-indigo-700 dark:file:bg-indigo-950 dark:file:text-indigo-300 hover:file:bg-indigo-100"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Input
                label="File Name *"
                required
                value={docFileName}
                onChange={(e) => setDocFileName(e.target.value)}
              />
              <Input
                label="Display Title"
                value={docTitle}
                onChange={(e) => setDocTitle(e.target.value)}
              />
            </div>

            <Textarea
              label="Document Content / CSV Rows / Markdown"
              rows={5}
              placeholder="Paste text, CSV rows, or leave empty if uploading a binary file..."
              value={docRawText}
              onChange={(e) => setDocRawText(e.target.value)}
            />

            <div className="flex justify-end gap-3 pt-4 border-t border-slate-100 dark:border-slate-800">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setShowIngestModal(null)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                size="sm"
              >
                Parse & Queue for Approval
              </Button>
            </div>
          </form>
        )}
      </Dialog>
    </div>
  );
};
