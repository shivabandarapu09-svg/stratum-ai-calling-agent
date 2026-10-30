import React, { useEffect, useState } from 'react';
import {
  PhoneCall, Users, CheckCircle2, Clock, TrendingUp, DollarSign,
  ArrowUpRight, Activity, Server, ShieldCheck, RefreshCw
} from 'lucide-react';
import { DashboardAnalytics, Call } from '../types';
import { fetchAnalytics, fetchCalls } from '../api';
import { 
  Button, Card, CardHeader, CardTitle, CardDescription, CardContent,
  Badge, Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
  LoadingState, ErrorState, EmptyState 
} from '../components/ui';

interface DashboardProps {
  onNavigate: (page: string) => void;
}

export const Dashboard: React.FC<DashboardProps> = ({ onNavigate }) => {
  const [analytics, setAnalytics] = useState<DashboardAnalytics | null>(null);
  const [recentCalls, setRecentCalls] = useState<Call[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = () => {
    setLoading(true);
    setError(null);
    Promise.all([fetchAnalytics(), fetchCalls()])
      .then(([analyticsData, callsData]) => {
        setAnalytics(analyticsData);
        setRecentCalls(callsData.slice(0, 8));
        setLoading(false);
      })
      .catch((err) => {
        console.error('Error loading dashboard:', err);
        setError('Unable to load executive metrics from the backend server.');
        setLoading(false);
      });
  };

  useEffect(() => {
    loadDashboard();
  }, []);

  if (loading) {
    return <LoadingState message="Loading executive operational metrics..." />;
  }

  if (error || !analytics) {
    return <ErrorState message={error || 'Dashboard analytics unavailable.'} onRetry={loadDashboard} />;
  }

  const { kpis, languages, outcomes, system_health } = analytics;
  const avgCostUsd = kpis.avg_cost_per_call ?? (kpis.total_calls > 0 ? kpis.estimated_total_cost / kpis.total_calls : 0);
  const conversionRate = kpis.conversion_rate_pct ?? (kpis.successful_calls > 0 ? Math.round((kpis.leads_qualified / kpis.successful_calls) * 1000) / 10 : 0);

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Executive Overview
            </h1>
            <Badge variant="indigo">Live Telephony</Badge>
          </div>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">
            Real-time operational performance, lead qualification rates, call economics, and carrier health.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={loadDashboard}
            leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
          >
            Refresh
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => onNavigate('simulator')}
            leftIcon={<PhoneCall className="w-3.5 h-3.5" />}
          >
            Live Voice Studio
          </Button>
        </div>
      </div>

      {/* High-Signal KPI Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3.5">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 mb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Calls Today</span>
            <PhoneCall className="w-3.5 h-3.5 text-indigo-500" />
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-white">{kpis.calls_today ?? kpis.total_calls}</div>
          <span className="text-[11px] text-slate-400 dark:text-slate-500 mt-1 block font-medium">
            {kpis.total_calls} total recorded
          </span>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 mb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Answer Rate</span>
            <Activity className="w-3.5 h-3.5 text-emerald-500" />
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-white">{kpis.answer_rate_pct}%</div>
          <span className="text-[11px] text-slate-400 dark:text-slate-500 mt-1 block font-medium">
            Connected calls
          </span>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 mb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Successful Calls</span>
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-white">{kpis.successful_calls}</div>
          <span className="text-[11px] text-slate-400 dark:text-slate-500 mt-1 block font-medium">
            {kpis.failed_calls} failed
          </span>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 mb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Qualified Leads</span>
            <Users className="w-3.5 h-3.5 text-indigo-500" />
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-white">{kpis.leads_qualified}</div>
          <span className="text-[11px] text-slate-400 dark:text-slate-500 mt-1 block font-medium">
            BANT verified
          </span>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 mb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Conversion</span>
            <TrendingUp className="w-3.5 h-3.5 text-emerald-500" />
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-white">{conversionRate}%</div>
          <span className="text-[11px] text-slate-400 dark:text-slate-500 mt-1 block font-medium">
            Qualified / connected
          </span>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 mb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Avg Duration</span>
            <Clock className="w-3.5 h-3.5 text-slate-400" />
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-white">{kpis.avg_duration_seconds}s</div>
          <span className="text-[11px] text-slate-400 dark:text-slate-500 mt-1 block font-medium">
            Per session
          </span>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 mb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Cost / Call</span>
            <DollarSign className="w-3.5 h-3.5 text-slate-400" />
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-white font-mono">
            ₹{(avgCostUsd * 83).toFixed(2)}
          </div>
          <span className="text-[11px] text-slate-400 dark:text-slate-500 mt-1 block font-medium">
            ${avgCostUsd.toFixed(3)} USD avg
          </span>
        </div>
      </div>

      {/* Middle Row: System Health + Language & Outcome Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* System Health Card (4 cols) */}
        <div className="lg:col-span-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 flex flex-col justify-between shadow-xs">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                <Server className="w-4 h-4 text-indigo-500" />
                Pipeline Health
              </h2>
              <Badge variant="success" size="sm">Operational</Badge>
            </div>

            <div className="space-y-2.5 text-xs">
              <div className="flex items-center justify-between p-2.5 bg-slate-50 dark:bg-slate-950/60 rounded-lg border border-slate-200 dark:border-slate-800">
                <span className="text-slate-500 dark:text-slate-400 font-medium">Telephony Carrier</span>
                <span className="font-mono font-semibold text-slate-900 dark:text-slate-200 uppercase">
                  {system_health?.telephony_provider || 'Twilio PSTN'}
                </span>
              </div>

              <div className="flex items-center justify-between p-2.5 bg-slate-50 dark:bg-slate-950/60 rounded-lg border border-slate-200 dark:border-slate-800">
                <span className="text-slate-500 dark:text-slate-400 font-medium">Twilio Credentials</span>
                <Badge variant={system_health?.twilio_configured ? 'success' : 'warning'} size="sm">
                  {system_health?.twilio_configured ? 'Configured' : 'Not Configured'}
                </Badge>
              </div>

              <div className="flex items-center justify-between p-2.5 bg-slate-50 dark:bg-slate-950/60 rounded-lg border border-slate-200 dark:border-slate-800">
                <span className="text-slate-500 dark:text-slate-400 font-medium">Public Webhook</span>
                <Badge variant={system_health?.public_webhook_configured ? 'success' : 'neutral'} size="sm">
                  {system_health?.public_webhook_configured ? 'Active' : 'Local / Trial'}
                </Badge>
              </div>

              <div className="flex items-center justify-between p-2.5 bg-slate-50 dark:bg-slate-950/60 rounded-lg border border-slate-200 dark:border-slate-800">
                <span className="text-slate-500 dark:text-slate-400 font-medium">Approved RAG Sources</span>
                <span className="font-mono font-semibold text-emerald-600 dark:text-emerald-400">
                  {system_health?.knowledge_sources_approved ?? 'Active'} indexed
                </span>
              </div>

              <div className="flex items-center justify-between p-2.5 bg-slate-50 dark:bg-slate-950/60 rounded-lg border border-slate-200 dark:border-slate-800">
                <span className="text-slate-500 dark:text-slate-400 font-medium">Active AI Employees</span>
                <span className="font-mono font-semibold text-slate-900 dark:text-slate-200">
                  {kpis.active_agents_count} published
                </span>
              </div>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between text-xs">
            <button
              onClick={() => onNavigate('integrations')}
              className="text-indigo-600 dark:text-indigo-400 hover:underline font-medium flex items-center gap-1"
            >
              Configure Carriers <ArrowUpRight className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => onNavigate('knowledge')}
              className="text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 font-medium"
            >
              Manage RAG
            </button>
          </div>
        </div>

        {/* Language & Disposition Breakdown (8 cols) */}
        <div className="lg:col-span-8 grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Language Distribution */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 shadow-xs">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Conversation Languages</h2>
              <span className="text-[11px] text-slate-500 dark:text-slate-400">{kpis.total_calls} sessions</span>
            </div>

            {languages.length === 0 ? (
              <div className="text-xs text-slate-500 py-8 text-center">
                No language metrics recorded yet.
              </div>
            ) : (
              <div className="space-y-3">
                {languages.map((lang) => (
                  <div key={lang.language_code}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-slate-700 dark:text-slate-300 font-medium">{lang.language_name}</span>
                      <span className="text-slate-500 dark:text-slate-400 font-mono">{lang.call_count} ({lang.percentage}%)</span>
                    </div>
                    <div className="w-full bg-slate-100 dark:bg-slate-950 rounded-full h-2 overflow-hidden border border-slate-200 dark:border-slate-800">
                      <div
                        className="bg-indigo-600 h-full rounded-full transition-all"
                        style={{ width: `${lang.percentage}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Qualification & Dispositions */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 shadow-xs">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-500" />
                Call Dispositions
              </h2>
              <span className="text-[11px] text-slate-500 dark:text-slate-400">Post-call outcomes</span>
            </div>

            {outcomes.length === 0 ? (
              <div className="text-xs text-slate-500 py-8 text-center">
                No call outcomes recorded yet.
              </div>
            ) : (
              <div className="space-y-2.5">
                {outcomes.map((item) => (
                  <div
                    key={item.outcome}
                    className="flex items-center justify-between px-3.5 py-2.5 bg-slate-50 dark:bg-slate-950/60 rounded-lg border border-slate-200 dark:border-slate-800 text-xs"
                  >
                    <span className="font-medium text-slate-800 dark:text-slate-200">{item.outcome}</span>
                    <Badge variant="indigo" size="sm">
                      {item.count}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Recent Activity Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Recent Call Activity</CardTitle>
              <CardDescription>
                Latest inbound and outbound AI conversations across active company workspaces
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="xs"
              onClick={() => onNavigate('calls')}
              rightIcon={<ArrowUpRight className="w-3.5 h-3.5" />}
            >
              View All Logs
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {recentCalls.length === 0 ? (
            <EmptyState
              icon={PhoneCall}
              title="No calls recorded yet"
              description="Open the Live Voice Studio to initiate your first interactive AI voice conversation."
              actionLabel="Open Live Studio"
              onAction={() => onNavigate('simulator')}
            />
          ) : (
            <Table className="border-0 rounded-none shadow-none">
              <TableHeader>
                <TableRow>
                  <TableHead>Contact</TableHead>
                  <TableHead>Company & Agent</TableHead>
                  <TableHead>Language</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Lead Qualification</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Started</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recentCalls.map((c) => (
                  <TableRow
                    key={c.id}
                    onClick={() => onNavigate('calls')}
                    className="cursor-pointer"
                  >
                    <TableCell>
                      <div className="font-semibold text-slate-900 dark:text-white">
                        {c.customer_name || 'Caller'}
                      </div>
                      <div className="text-[11px] text-slate-500 dark:text-slate-400 font-mono">
                        {c.customer_phone}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="font-medium text-slate-800 dark:text-slate-200">
                        {c.company_name || 'Stratum Enterprise'}
                      </div>
                      <div className="text-[11px] text-slate-500 dark:text-slate-400">
                        {c.agent_name || 'AI Employee'}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="neutral" size="sm">
                        {c.primary_language?.toUpperCase() || 'EN'}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-slate-700 dark:text-slate-300">
                      {c.duration_seconds}s
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          c.summary?.qualification_status === 'Hot'
                            ? 'success'
                            : c.summary?.qualification_status === 'Warm'
                            ? 'warning'
                            : 'neutral'
                        }
                        size="sm"
                      >
                        {c.summary?.qualification_status || c.summary?.outcome || 'In Review'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          c.status === 'completed'
                            ? 'success'
                            : c.status === 'in_progress'
                            ? 'indigo'
                            : c.status === 'failed'
                            ? 'danger'
                            : 'neutral'
                        }
                        size="sm"
                      >
                        {c.status.toUpperCase()}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right text-slate-500 dark:text-slate-400 text-xs font-mono">
                      {new Date(c.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
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
