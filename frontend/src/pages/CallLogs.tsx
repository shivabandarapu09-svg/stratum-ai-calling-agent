import React, { useEffect, useState } from 'react';
import {
  Search, Phone, Clock, ArrowUpRight, ShieldCheck, FileText, Activity, RefreshCw
} from 'lucide-react';
import { Call } from '../types';
import { fetchCalls, fetchCallDetail } from '../api';
import { 
  Button, Card, CardHeader, CardTitle, CardDescription, CardContent,
  Badge, Input, Select, Drawer, Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
  LoadingState, EmptyState 
} from '../components/ui';

export const CallLogs: React.FC = () => {
  const [calls, setCalls] = useState<Call[]>([]);
  const [selectedCall, setSelectedCall] = useState<Call | null>(null);
  const [languageFilter, setLanguageFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);

  const loadCalls = () => {
    setLoading(true);
    fetchCalls({
      language: languageFilter || undefined,
      status: statusFilter || undefined,
    })
      .then((data) => {
        setCalls(data || []);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Error fetching calls:', err);
        setLoading(false);
      });
  };

  useEffect(() => {
    loadCalls();
  }, [languageFilter, statusFilter]);

  const handleRowClick = async (callId: string) => {
    try {
      const detail = await fetchCallDetail(callId);
      setSelectedCall(detail);
    } catch (e) {
      console.error('Failed to load call detail:', e);
    }
  };

  const filteredCalls = calls.filter((c) => {
    const q = searchQuery.toLowerCase();
    return (
      (c.customer_name?.toLowerCase().includes(q) || '') ||
      c.customer_phone.includes(q) ||
      (c.agent_name?.toLowerCase().includes(q) || '') ||
      (c.company_name?.toLowerCase().includes(q) || '')
    );
  });

  const renderBantBadges = (bant?: Record<string, any>) => {
    const slots = [
      { key: 'budget', label: 'B' },
      { key: 'authority', label: 'A' },
      { key: 'need', label: 'N' },
      { key: 'timeline', label: 'T' },
    ];
    return (
      <div className="inline-flex items-center gap-1">
        {slots.map((s) => {
          const val = bant?.[s.key];
          const filled = Boolean(val && val !== 'Pending' && val !== 'Unknown');
          return (
            <span
              key={s.key}
              title={`${s.key.toUpperCase()}: ${val || 'Not captured'}`}
              className={`w-5 h-5 rounded text-[10px] font-mono font-bold flex items-center justify-center border ${
                filled
                  ? 'bg-emerald-100 dark:bg-emerald-950/90 text-emerald-700 dark:text-emerald-400 border-emerald-300 dark:border-emerald-800'
                  : 'bg-slate-100 dark:bg-slate-900 text-slate-400 dark:text-slate-500 border-slate-200 dark:border-slate-800'
              }`}
            >
              {s.label}
            </span>
          );
        })}
      </div>
    );
  };

  const sessionTrace: Array<{ timestamp?: string; event: string; detail?: Record<string, any> }> =
    selectedCall?.summary?.key_information?.session_trace || [];

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header & Search Filters */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Call Logs & BANT Qualification
            </h1>
            <Badge variant="indigo">Traceable</Badge>
          </div>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">
            Searchable record of customer conversations, company assignments, BANT qualification results, and session trace diagnostics.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={loadCalls}
            leftIcon={<RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row gap-4 items-center justify-between">
        <div className="w-full sm:w-80">
          <Input
            placeholder="Search contact, phone, company..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            leftIcon={<Search className="w-4 h-4" />}
          />
        </div>

        <div className="flex items-center gap-3 w-full sm:w-auto">
          <Select
            value={languageFilter}
            onChange={(e) => setLanguageFilter(e.target.value)}
            options={[
              { value: '', label: 'All Languages' },
              { value: 'hi', label: 'Hindi (HI)' },
              { value: 'en', label: 'English (EN)' },
              { value: 'te', label: 'Telugu (TE)' },
              { value: 'ta', label: 'Tamil (TA)' },
              { value: 'kn', label: 'Kannada (KN)' },
            ]}
            containerClassName="w-full sm:w-44"
          />

          <Select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            options={[
              { value: '', label: 'All Statuses' },
              { value: 'completed', label: 'Completed' },
              { value: 'in_progress', label: 'In Progress' },
              { value: 'ringing', label: 'Ringing' },
              { value: 'transferred', label: 'Transferred' },
              { value: 'failed', label: 'Failed' },
            ]}
            containerClassName="w-full sm:w-44"
          />
        </div>
      </div>

      {/* Calls Table */}
      {loading ? (
        <LoadingState message="Loading call history and diagnostic traces..." />
      ) : filteredCalls.length === 0 ? (
        <EmptyState
          icon={Phone}
          title="No calls match criteria"
          description="Try adjusting your search query, language filter, or status filter."
        />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Contact</TableHead>
              <TableHead>Company & Agent</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead>Language</TableHead>
              <TableHead>Lead Qualification</TableHead>
              <TableHead>BANT</TableHead>
              <TableHead>Summary</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredCalls.map((c) => {
              const qualStatus = c.summary?.qualification_status || 'Reviewed';
              return (
                <TableRow
                  key={c.id}
                  onClick={() => handleRowClick(c.id)}
                  className="cursor-pointer"
                >
                  <TableCell>
                    <div className="font-semibold text-slate-900 dark:text-white">
                      {c.customer_name || 'Caller'}
                    </div>
                    <div className="text-slate-500 dark:text-slate-400 font-mono text-xs">
                      {c.customer_phone}
                    </div>
                  </TableCell>

                  <TableCell>
                    <div className="text-slate-800 dark:text-slate-200 font-medium">
                      {c.company_name || 'Stratum Enterprise'}
                    </div>
                    <div className="text-slate-500 dark:text-slate-400 text-xs">
                      {c.agent_name || 'AI Employee'}
                    </div>
                  </TableCell>

                  <TableCell>
                    <Badge
                      variant={
                        c.status === 'completed'
                          ? 'success'
                          : c.status === 'transferred'
                          ? 'indigo'
                          : c.status === 'in_progress' || c.status === 'ringing'
                          ? 'warning'
                          : c.status === 'failed'
                          ? 'danger'
                          : 'neutral'
                      }
                      size="sm"
                    >
                      {c.status.toUpperCase()}
                    </Badge>
                  </TableCell>

                  <TableCell className="font-mono text-slate-700 dark:text-slate-300">
                    {c.duration_seconds}s
                  </TableCell>

                  <TableCell>
                    <Badge variant="neutral" size="sm">
                      {c.primary_language?.toUpperCase() || 'EN'}
                    </Badge>
                  </TableCell>

                  <TableCell>
                    <Badge
                      variant={
                        qualStatus === 'Hot'
                          ? 'success'
                          : qualStatus === 'Warm'
                          ? 'warning'
                          : 'neutral'
                      }
                      size="sm"
                    >
                      {qualStatus.toUpperCase()}
                    </Badge>
                  </TableCell>

                  <TableCell>{renderBantBadges(c.summary?.bant_score)}</TableCell>

                  <TableCell className="max-w-xs">
                    <p className="text-slate-500 dark:text-slate-400 text-xs truncate">
                      {c.summary?.summary_text || 'Transcript in drawer'}
                    </p>
                  </TableCell>

                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="xs"
                      rightIcon={<ArrowUpRight className="w-3.5 h-3.5" />}
                    >
                      Inspect
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}

      {/* Slide-Over Detail Drawer using UI Reusable Drawer */}
      <Drawer
        isOpen={!!selectedCall}
        onClose={() => setSelectedCall(null)}
        title="Call Session Details & BANT Assessment"
        description={
          selectedCall
            ? `Call ID: ${selectedCall.id} • Carrier: ${(selectedCall.telephony_provider || 'web_simulator').toUpperCase()}`
            : undefined
        }
        width="xl"
      >
        {selectedCall && (
          <div className="space-y-6">
            {/* Metadata Cards */}
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="bg-slate-50 dark:bg-slate-950/60 p-3.5 rounded-xl border border-slate-200 dark:border-slate-800">
                <span className="text-slate-500 dark:text-slate-400 text-[10px] uppercase font-semibold block mb-0.5">Contact</span>
                <strong className="text-slate-900 dark:text-white block truncate">{selectedCall.customer_name}</strong>
                <span className="text-slate-500 dark:text-slate-400 font-mono text-[11px]">{selectedCall.customer_phone}</span>
              </div>
              <div className="bg-slate-50 dark:bg-slate-950/60 p-3.5 rounded-xl border border-slate-200 dark:border-slate-800">
                <span className="text-slate-500 dark:text-slate-400 text-[10px] uppercase font-semibold block mb-0.5">Company & Agent</span>
                <strong className="text-indigo-600 dark:text-indigo-400 block truncate">{selectedCall.company_name || 'Stratum Enterprise'}</strong>
                <span className="text-slate-500 dark:text-slate-400 text-[11px]">{selectedCall.agent_name}</span>
              </div>
              <div className="bg-slate-50 dark:bg-slate-950/60 p-3.5 rounded-xl border border-slate-200 dark:border-slate-800">
                <span className="text-slate-500 dark:text-slate-400 text-[10px] uppercase font-semibold block mb-0.5">Duration & Cost</span>
                <strong className="text-slate-900 dark:text-white block">{selectedCall.duration_seconds}s ({selectedCall.status})</strong>
                <span className="text-slate-500 dark:text-slate-400 font-mono text-[11px]">₹{(selectedCall.cost_estimate * 83).toFixed(2)}</span>
              </div>
            </div>

            {/* BANT Qualification Scorecard */}
            {selectedCall.summary?.bant_score && (
              <div className="bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 rounded-xl p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-900 dark:text-white flex items-center gap-1.5">
                    <ShieldCheck className="w-4 h-4 text-emerald-500" /> BANT Qualification Breakdown
                  </span>
                  <Badge variant="success" size="sm">
                    {selectedCall.summary.qualification_status || 'Reviewed'}
                  </Badge>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="bg-white dark:bg-slate-900 p-2.5 rounded-lg border border-slate-200 dark:border-slate-800">
                    <span className="text-[10px] uppercase text-slate-500 dark:text-slate-400 font-medium block">Budget</span>
                    <strong className="text-slate-800 dark:text-slate-200">{selectedCall.summary.bant_score.budget || 'Not disclosed'}</strong>
                  </div>
                  <div className="bg-white dark:bg-slate-900 p-2.5 rounded-lg border border-slate-200 dark:border-slate-800">
                    <span className="text-[10px] uppercase text-slate-500 dark:text-slate-400 font-medium block">Authority</span>
                    <strong className="text-slate-800 dark:text-slate-200">{selectedCall.summary.bant_score.authority || 'Decision Maker'}</strong>
                  </div>
                  <div className="bg-white dark:bg-slate-900 p-2.5 rounded-lg border border-slate-200 dark:border-slate-800">
                    <span className="text-[10px] uppercase text-slate-500 dark:text-slate-400 font-medium block">Need</span>
                    <strong className="text-slate-800 dark:text-slate-200">{selectedCall.summary.bant_score.need || 'Discovered'}</strong>
                  </div>
                  <div className="bg-white dark:bg-slate-900 p-2.5 rounded-lg border border-slate-200 dark:border-slate-800">
                    <span className="text-[10px] uppercase text-slate-500 dark:text-slate-400 font-medium block">Timeline</span>
                    <strong className="text-emerald-600 dark:text-emerald-400">{selectedCall.summary.bant_score.timeline || 'Immediate'}</strong>
                  </div>
                </div>
              </div>
            )}

            {/* Executive Summary */}
            {selectedCall.summary && (
              <div className="bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 rounded-xl p-4 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-900 dark:text-white flex items-center gap-1.5">
                    <FileText className="w-4 h-4 text-indigo-500" /> Conversation Summary
                  </span>
                  <Badge variant="indigo" size="sm">
                    {selectedCall.summary.sentiment} Sentiment
                  </Badge>
                </div>
                <p className="text-slate-700 dark:text-slate-300 leading-relaxed">
                  {selectedCall.summary.summary_text}
                </p>
                {selectedCall.summary.next_action && (
                  <div className="text-[11px] text-indigo-600 dark:text-indigo-400 pt-2 border-t border-slate-200 dark:border-slate-800 font-medium">
                    <strong>Recommended Next Step:</strong> {selectedCall.summary.next_action}
                  </div>
                )}
              </div>
            )}

            {/* Transcript Turns */}
            <div className="space-y-3">
              <span className="text-xs font-semibold text-slate-900 dark:text-white uppercase tracking-wider block">
                Conversation Transcript ({selectedCall.transcripts?.length || 0} turns)
              </span>
              <div className="space-y-2.5 bg-slate-50 dark:bg-slate-950/60 p-4 rounded-xl border border-slate-200 dark:border-slate-800">
                {selectedCall.transcripts && selectedCall.transcripts.length > 0 ? (
                  selectedCall.transcripts.map((t, idx) => (
                    <div
                      key={idx}
                      className={`flex flex-col ${
                        t.speaker === 'agent' ? 'items-start' : 'items-end'
                      }`}
                    >
                      <span className="text-[10px] text-slate-500 dark:text-slate-400 mb-1">
                        {t.speaker === 'agent' ? selectedCall.agent_name : selectedCall.customer_name} • {t.language.toUpperCase()} • {t.latency_ms}ms
                      </span>
                      <div
                        className={`max-w-[85%] px-3.5 py-2.5 rounded-xl text-xs leading-relaxed ${
                          t.speaker === 'agent'
                            ? 'bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-100 border border-slate-200 dark:border-slate-800 shadow-2xs'
                            : 'bg-indigo-600 text-white'
                        }`}
                      >
                        {t.text}
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-slate-500 dark:text-slate-400 text-center py-4">No transcript turns recorded.</p>
                )}
              </div>
            </div>

            {/* Call-Session Trace Events */}
            {sessionTrace.length > 0 && (
              <div className="bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 rounded-xl p-4 space-y-2">
                <span className="text-xs font-semibold text-slate-900 dark:text-white flex items-center gap-1.5">
                  <Activity className="w-4 h-4 text-emerald-500" /> Call-Session Diagnostic Trace ({sessionTrace.length} events)
                </span>
                <div className="space-y-1.5 max-h-48 overflow-y-auto font-mono text-[11px]">
                  {sessionTrace.map((ev, idx) => (
                    <div key={idx} className="p-2 bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 flex items-center justify-between">
                      <span className="text-emerald-600 dark:text-emerald-400 font-semibold">{ev.event}</span>
                      <span className="text-slate-500 dark:text-slate-400 text-[10px]">
                        {ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : ''}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
};
