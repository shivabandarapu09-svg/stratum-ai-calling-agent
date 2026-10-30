import React, { useEffect, useState } from 'react';
import {
  BarChart3, PieChart, Clock, Languages, DollarSign, Activity, RefreshCw
} from 'lucide-react';
import { DashboardAnalytics } from '../types';
import { fetchAnalytics } from '../api';
import { 
  Button, Card, CardHeader, CardTitle, CardDescription, CardContent,
  Badge, LoadingState, ErrorState 
} from '../components/ui';

export const Analytics: React.FC = () => {
  const [analytics, setAnalytics] = useState<DashboardAnalytics | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = () => {
    setLoading(true);
    setError(null);
    fetchAnalytics()
      .then((data) => {
        setAnalytics(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setError('Failed to load telemetry analytics.');
        setLoading(false);
      });
  };

  useEffect(() => {
    loadData();
  }, []);

  if (loading) {
    return <LoadingState message="Loading performance telemetry & economics..." />;
  }

  if (error || !analytics) {
    return <ErrorState message={error || 'Analytics unavailable'} onRetry={loadData} />;
  }

  const { kpis, languages, outcomes, latencies } = analytics;

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Latency & Economics
            </h1>
            <Badge variant="indigo">Observability</Badge>
          </div>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">
            Detailed telemetry for Indian language accuracy, call outcomes, speech latency, and cost per minute.
          </p>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={loadData}
          leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
        >
          Refresh
        </Button>
      </div>

      {/* Latency Pipeline Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Clock className="w-4 h-4 text-emerald-500" />
              End-to-End Voice Turn-Cycle Breakdown
            </CardTitle>
            <Badge variant="success" size="sm">Real-Time Sub-400ms</Badge>
          </div>
          <CardDescription className="text-xs">
            Acoustic streaming latency benchmarked across Indian telecom carriers
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-slate-50 dark:bg-slate-950/60 p-4 rounded-xl border border-slate-200 dark:border-slate-800">
              <span className="text-xs text-slate-500 dark:text-slate-400 font-medium block mb-1">1. Speech-to-Text (ASR)</span>
              <strong className="text-2xl text-slate-900 dark:text-white font-mono">{latencies.avg_stt_latency_ms}ms</strong>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1">Sarvam Indic & Whisper streaming</p>
            </div>

            <div className="bg-slate-50 dark:bg-slate-950/60 p-4 rounded-xl border border-slate-200 dark:border-slate-800">
              <span className="text-xs text-slate-500 dark:text-slate-400 font-medium block mb-1">2. LLM Reasoning</span>
              <strong className="text-2xl text-indigo-600 dark:text-indigo-400 font-mono">{latencies.avg_llm_latency_ms}ms</strong>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1">Grounded RAG & BANT turn evaluation</p>
            </div>

            <div className="bg-slate-50 dark:bg-slate-950/60 p-4 rounded-xl border border-slate-200 dark:border-slate-800">
              <span className="text-xs text-slate-500 dark:text-slate-400 font-medium block mb-1">3. Neural TTS Synthesis</span>
              <strong className="text-2xl text-emerald-600 dark:text-emerald-400 font-mono">{latencies.avg_tts_latency_ms}ms</strong>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1">Sarvam Bulbul / ElevenLabs streaming</p>
            </div>

            <div className="bg-emerald-50/50 dark:bg-emerald-950/30 p-4 rounded-xl border border-emerald-200 dark:border-emerald-800/60">
              <span className="text-xs text-emerald-800 dark:text-emerald-300 font-semibold block mb-1">Total Turn-Cycle</span>
              <strong className="text-2xl text-slate-900 dark:text-white font-mono">{latencies.avg_total_latency_ms}ms</strong>
              <p className="text-[11px] text-emerald-700/80 dark:text-emerald-400/80 mt-1">Conversational & natural response</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Grid: Language & Outcome Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Language Breakdown */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <Languages className="w-4 h-4 text-emerald-500" />
                Calls by Language
              </CardTitle>
              <span className="text-xs text-slate-400">{kpis.total_calls} calls</span>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {languages.map((l) => (
              <div key={l.language_code}>
                <div className="flex justify-between text-xs mb-1.5">
                  <span className="font-semibold text-slate-700 dark:text-slate-200">{l.language_name}</span>
                  <span className="text-slate-500 dark:text-slate-400 font-mono">{l.call_count} calls ({l.percentage}%)</span>
                </div>
                <div className="w-full bg-slate-100 dark:bg-slate-950 rounded-full h-2.5 overflow-hidden border border-slate-200 dark:border-slate-800">
                  <div
                    className="bg-indigo-600 h-full rounded-full transition-all"
                    style={{ width: `${l.percentage}%` }}
                  />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Call Outcomes */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <PieChart className="w-4 h-4 text-indigo-500" />
                Call Outcomes & Dispositions
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {outcomes.map((o) => (
              <div
                key={o.outcome}
                className="bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 rounded-xl p-3.5 flex items-center justify-between text-xs"
              >
                <span className="font-medium text-slate-800 dark:text-slate-200">{o.outcome}</span>
                <Badge variant="indigo" size="sm">
                  {o.count} calls
                </Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Cost Observability */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <DollarSign className="w-4 h-4 text-amber-500" />
              Unit Economics & Cost Tracking
            </CardTitle>
            <Badge variant="neutral" size="sm">INR (₹) / Minute</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
            <div className="bg-slate-50 dark:bg-slate-950/60 p-4 rounded-xl border border-slate-200 dark:border-slate-800">
              <span className="text-slate-500 dark:text-slate-400 font-medium block mb-1">Telephony Carrier (PSTN)</span>
              <strong className="text-base text-slate-900 dark:text-white">₹0.30 / min</strong>
            </div>
            <div className="bg-slate-50 dark:bg-slate-950/60 p-4 rounded-xl border border-slate-200 dark:border-slate-800">
              <span className="text-slate-500 dark:text-slate-400 font-medium block mb-1">STT Transcription (Sarvam)</span>
              <strong className="text-base text-slate-900 dark:text-white">₹0.15 / min</strong>
            </div>
            <div className="bg-slate-50 dark:bg-slate-950/60 p-4 rounded-xl border border-slate-200 dark:border-slate-800">
              <span className="text-slate-500 dark:text-slate-400 font-medium block mb-1">LLM Orchestration</span>
              <strong className="text-base text-slate-900 dark:text-white">₹0.05 / min</strong>
            </div>
            <div className="bg-emerald-50/50 dark:bg-emerald-950/30 p-4 rounded-xl border border-emerald-200 dark:border-emerald-800/60">
              <span className="text-emerald-800 dark:text-emerald-300 font-semibold block mb-1">Total Estimated / Call</span>
              <strong className="text-base text-slate-900 dark:text-white font-mono">
                ₹{((kpis.estimated_total_cost / Math.max(kpis.total_calls, 1)) * 83).toFixed(2)}
              </strong>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
