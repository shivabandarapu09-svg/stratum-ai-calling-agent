import React, { useState, useEffect, useRef } from 'react';
import {
  Phone, PhoneOff, Mic, Volume2, ShieldAlert,
  UserCheck, Languages, Activity, CheckCircle2, AlertTriangle,
  Smartphone, Monitor, Send, MessageSquare,
  Play, BookOpen, Building2, Target, Terminal, Clock
} from 'lucide-react';
import { Agent, ToolCallEvent, KnowledgeDoc, TenantWorkspace } from '../types';
import {
  fetchAgents, initiateOutboundCall, terminateCall, fetchCallDetail,
  fetchTelephonyStatus, previewVoiceSample, fetchKnowledgeDocs, fetchTenantWorkspaces
} from '../api';

type ConnectionStep =
  | 'Ready'
  | 'Connecting'
  | 'Ringing'
  | 'Answered'
  | 'AI Connected'
  | 'Conversation Active'
  | 'Completed'
  | 'Failed';

const LIFECYCLE_STEPS: ConnectionStep[] = [
  'Ready',
  'Connecting',
  'Ringing',
  'Answered',
  'AI Connected',
  'Conversation Active',
  'Completed',
];

export const LiveCallSimulator: React.FC<{ onNavigate?: (tab: string) => void }> = ({ onNavigate }) => {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tenants, setTenants] = useState<TenantWorkspace[]>([]);
  const [knowledgeDocs, setKnowledgeDocs] = useState<KnowledgeDoc[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string>('');
  const [phone, setPhone] = useState<string>('+919876543210');
  const [customerName, setCustomerName] = useState<string>('Kalyan Varma');
  const [customUtterance, setCustomUtterance] = useState<string>('');

  // Call mode: 'browser' (Browser Microphone Simulation) or 'real_phone' (Real PSTN Call)
  const [callMode, setCallMode] = useState<'browser' | 'real_phone'>('browser');
  const [twilioTrialMode, setTwilioTrialMode] = useState<boolean>(false);
  const [telephonyStatus, setTelephonyStatus] = useState<any>(null);
  const [dialError, setDialError] = useState<string | null>(null);

  // Voice & Acoustic Controls
  const [ambientMode, setAmbientMode] = useState<'office_call_center' | 'executive_room' | 'none'>('office_call_center');
  const [voiceSpeed, setVoiceSpeed] = useState<number>(1.04);
  const [isAuditioning, setIsAuditioning] = useState<boolean>(false);
  const [voiceEngineLabel, setVoiceEngineLabel] = useState<string>('Neural TTS');

  // Call Lifecycle State
  const [callActive, setCallActive] = useState<boolean>(false);
  const [callId, setCallId] = useState<string | null>(null);
  const [lifecycleStep, setLifecycleStep] = useState<ConnectionStep>('Ready');
  const [detectedLanguage, setDetectedLanguage] = useState<string>('hi');
  const [isAiSpeaking, setIsAiSpeaking] = useState<boolean>(false);
  const [isCustomerSpeaking, setIsCustomerSpeaking] = useState<boolean>(false);
  const [transferAlert, setTransferAlert] = useState<string | null>(null);
  const [whatsAppAlert, setWhatsAppAlert] = useState<string | null>(null);
  const [isRecordingPTT, setIsRecordingPTT] = useState<boolean>(false);

  // Conversation State & Telemetry
  const [currentStage, setCurrentStage] = useState<string>('1. Hook & Rapport');
  const [toolEvents, setToolEvents] = useState<ToolCallEvent[]>([]);
  const [sessionTrace, setSessionTrace] = useState<Array<{ timestamp?: string; event: string; detail?: Record<string, any> }>>([]);
  const [lastLatency, setLastLatency] = useState<{ stt: number; llm: number; tts: number; total: number }>({
    stt: 95, llm: 210, tts: 145, total: 450
  });
  const [bantQualified, setBantQualified] = useState<{
    budget: boolean;
    authority: boolean;
    need: boolean;
    timeline: boolean;
  }>({ budget: false, authority: true, need: false, timeline: false });

  // Transcripts & Post-call summary
  const [transcripts, setTranscripts] = useState<Array<{
    speaker: 'customer' | 'agent' | 'system';
    text: string;
    language?: string;
    latency?: number;
    stage?: string;
  }>>([]);
  const [callSummary, setCallSummary] = useState<any>(null);

  // Refs
  const wsRef = useRef<WebSocket | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const transcriptBottomRef = useRef<HTMLDivElement | null>(null);
  const isAiSpeakingRef = useRef<boolean>(false);
  const recognitionRef = useRef<any>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const ambientNodeRef = useRef<AudioNode | null>(null);
  const pstnPollTimerRef = useRef<number | null>(null);

  useEffect(() => {
    Promise.all([
      fetchAgents(),
      fetchTelephonyStatus(),
      fetchTenantWorkspaces(),
      fetchKnowledgeDocs()
    ]).then(([agentList, telStatus, tenantList, docsList]) => {
      setAgents(agentList);
      setTelephonyStatus(telStatus);
      setTenants(tenantList);
      setKnowledgeDocs(docsList);
      if (agentList.length > 0) {
        setSelectedAgentId(agentList[0].id);
        setDetectedLanguage(agentList[0].default_language || 'hi');
        setVoiceSpeed(agentList[0].speaking_speed || 1.04);
      }
    }).catch(console.error);

    if ('speechSynthesis' in window) {
      window.speechSynthesis.getVoices();
    }
    return () => {
      stopAmbientSoundscape();
      if (pstnPollTimerRef.current) window.clearInterval(pstnPollTimerRef.current);
    };
  }, []);

  const activeAgent = agents.find(a => a.id === selectedAgentId) || agents[0];

  useEffect(() => {
    if (activeAgent) {
      setDetectedLanguage(activeAgent.default_language || 'hi');
      setVoiceSpeed(activeAgent.speaking_speed || 1.04);
      if (activeAgent.ambient_sound) {
        setAmbientMode(activeAgent.ambient_sound as any);
      }
    }
  }, [selectedAgentId]);

  useEffect(() => {
    transcriptBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcripts, toolEvents]);

  // Approved knowledge docs for the active agent / tenant
  const approvedDocs = knowledgeDocs.filter(d => d.approval_status === 'approved' && d.is_active !== false);
  const totalApprovedChunks = approvedDocs.reduce((acc, d) => acc + (d.chunks_count || 0), 0);
  const matchedWorkspace = tenants.find(
    t => activeAgent && t.company_name.toLowerCase().includes(activeAgent.company.split(' ')[0].toLowerCase())
  ) || tenants[0];

  // ------------------------------------------------------------------
  // WEB AUDIO API ACOUSTICS & PLAYBACK
  // ------------------------------------------------------------------
  const getOrCreateAudioContext = (): AudioContext | null => {
    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioCtx) return null;
      if (!audioCtxRef.current) {
        audioCtxRef.current = new AudioCtx();
      }
      if (audioCtxRef.current.state === 'suspended') {
        audioCtxRef.current.resume();
      }
      return audioCtxRef.current;
    } catch {
      return null;
    }
  };

  const startAmbientSoundscape = (mode: string) => {
    stopAmbientSoundscape();
    if (mode === 'none') return;
    const ctx = getOrCreateAudioContext();
    if (!ctx) return;
    try {
      const bufferSize = ctx.sampleRate * 2;
      const noiseBuffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
      const output = noiseBuffer.getChannelData(0);
      let lastOut = 0.0;
      for (let i = 0; i < bufferSize; i++) {
        const white = Math.random() * 2 - 1;
        output[i] = (lastOut + 0.02 * white) / 1.02;
        lastOut = output[i];
        output[i] *= 0.25;
      }
      const whiteNoise = ctx.createBufferSource();
      whiteNoise.buffer = noiseBuffer;
      whiteNoise.loop = true;

      const filter = ctx.createBiquadFilter();
      filter.type = 'bandpass';
      filter.frequency.value = mode === 'office_call_center' ? 420 : 280;
      filter.Q.value = 0.7;

      const gainNode = ctx.createGain();
      gainNode.gain.value = mode === 'office_call_center' ? 0.015 : 0.007;

      whiteNoise.connect(filter);
      filter.connect(gainNode);
      gainNode.connect(ctx.destination);

      whiteNoise.start(0);
      ambientNodeRef.current = whiteNoise;
    } catch {
      // ignore
    }
  };

  const stopAmbientSoundscape = () => {
    try {
      if (ambientNodeRef.current) {
        (ambientNodeRef.current as AudioBufferSourceNode).stop();
        ambientNodeRef.current.disconnect();
        ambientNodeRef.current = null;
      }
    } catch {
      ambientNodeRef.current = null;
    }
  };

  const selectBestBrowserVoice = (lang: string, voiceId?: string): SpeechSynthesisVoice | null => {
    if (!('speechSynthesis' in window)) return null;
    const voices = window.speechSynthesis.getVoices();
    if (!voices || voices.length === 0) return null;
    const wantsMale = voiceId ? /madhur|prabhat|mohan|valluvar|amol/i.test(voiceId) : false;
    const langPrefix = lang === 'te' ? 'te' : lang === 'ta' ? 'ta' : lang === 'en' ? 'en' : 'hi';

    const scored = voices.map(v => {
      let score = 0;
      const vLang = v.lang.toLowerCase();
      const vName = v.name.toLowerCase();
      if (vLang.startsWith(langPrefix)) score += 50;
      else if (langPrefix === 'hi' && vLang.includes('in')) score += 20;
      else if (langPrefix === 'en' && vLang.includes('en-in')) score += 60;
      if (vName.includes('natural') || vName.includes('online')) score += 45;
      if (vName.includes('neural') || vName.includes('google')) score += 30;
      if (wantsMale && (vName.includes('madhur') || vName.includes('prabhat') || vName.includes('mohan') || vName.includes('male'))) score += 25;
      if (!wantsMale && (vName.includes('swara') || vName.includes('neerja') || vName.includes('shruti') || vName.includes('female'))) score += 25;
      return { voice: v, score };
    });
    scored.sort((a, b) => b.score - a.score);
    return scored[0]?.score > 0 ? scored[0].voice : null;
  };

  const playAgentAudio = async (text: string, lang: string, audioBase64?: string | null) => {
    isAiSpeakingRef.current = true;
    setIsAiSpeaking(true);

    if (audioBase64 && audioBase64.length > 200 && audioRef.current) {
      try {
        if ('speechSynthesis' in window) window.speechSynthesis.cancel();
        audioRef.current.pause();
        audioRef.current.src = `data:audio/mp3;base64,${audioBase64}`;
        audioRef.current.playbackRate = voiceSpeed;
        setVoiceEngineLabel(`Neural Stream (${activeAgent?.voice_id || 'HD'})`);

        audioRef.current.onended = () => {
          isAiSpeakingRef.current = false;
          setIsAiSpeaking(false);
          if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type: 'ai_audio_finished' }));
          }
        };
        audioRef.current.onerror = () => {
          playSmartBrowserFallback(text, lang);
        };
        await audioRef.current.play();
        return;
      } catch {
        // fallback below
      }
    }
    playSmartBrowserFallback(text, lang);
  };

  const playSmartBrowserFallback = (text: string, lang: string) => {
    try {
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const cleanText = text.replace(/[\*\#\_]/g, '').trim();
        const utterance = new SpeechSynthesisUtterance(cleanText);
        const bestVoice = selectBestBrowserVoice(lang, activeAgent?.voice_id);
        if (bestVoice) {
          utterance.voice = bestVoice;
          utterance.lang = bestVoice.lang;
          setVoiceEngineLabel(`${bestVoice.name.split(' ')[0]} Voice`);
        } else {
          utterance.lang = lang === 'hi' ? 'hi-IN' : lang === 'te' ? 'te-IN' : lang === 'ta' ? 'ta-IN' : 'en-IN';
          setVoiceEngineLabel('Browser Speech Synthesis');
        }
        utterance.rate = voiceSpeed;
        utterance.onend = () => {
          isAiSpeakingRef.current = false;
          setIsAiSpeaking(false);
        };
        utterance.onerror = () => {
          isAiSpeakingRef.current = false;
          setIsAiSpeaking(false);
        };
        window.speechSynthesis.speak(utterance);
      } else {
        setTimeout(() => {
          isAiSpeakingRef.current = false;
          setIsAiSpeaking(false);
        }, 2000);
      }
    } catch {
      isAiSpeakingRef.current = false;
      setIsAiSpeaking(false);
    }
  };

  const handleAuditionVoice = async () => {
    if (!activeAgent || isAuditioning) return;
    setIsAuditioning(true);
    try {
      const sampleRes = await previewVoiceSample({
        voice_id: activeAgent.voice_id,
        language: activeAgent.default_language,
        text: activeAgent.greeting,
        speaking_speed: voiceSpeed
      });
      await playAgentAudio(sampleRes.text, sampleRes.language, sampleRes.audio_base64);
    } catch {
      playSmartBrowserFallback(activeAgent.greeting, activeAgent.default_language);
    } finally {
      setIsAuditioning(false);
    }
  };

  const handleInterruptAi = () => {
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    isAiSpeakingRef.current = false;
    setIsAiSpeaking(false);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'barge_in' }));
    }
  };

  // ------------------------------------------------------------------
  // REAL PSTN CALL LIVE POLLING
  // ------------------------------------------------------------------
  const startPstnStatusPolling = (targetCallId: string) => {
    if (pstnPollTimerRef.current) window.clearInterval(pstnPollTimerRef.current);
    pstnPollTimerRef.current = window.setInterval(async () => {
      try {
        const detail = await fetchCallDetail(targetCallId);
        if (detail.transcripts && detail.transcripts.length > 0) {
          setTranscripts(
            detail.transcripts.map(t => ({
              speaker: (t.speaker as any) || 'agent',
              text: t.text,
              language: t.language,
              latency: t.latency_ms,
            }))
          );
        }
        if (detail.status === 'ringing') {
          setLifecycleStep('Ringing');
        } else if (detail.status === 'in_progress') {
          setLifecycleStep(detail.transcripts && detail.transcripts.length > 1 ? 'Conversation Active' : 'AI Connected');
        } else if (detail.status === 'completed' || detail.status === 'transferred') {
          setLifecycleStep('Completed');
          setCallActive(false);
          if (detail.summary) {
            setCallSummary(detail.summary);
            if (detail.summary.key_information?.session_trace) {
              setSessionTrace(detail.summary.key_information.session_trace);
            }
          }
          if (pstnPollTimerRef.current) window.clearInterval(pstnPollTimerRef.current);
        } else if (detail.status === 'failed') {
          setLifecycleStep('Failed');
          setCallActive(false);
          if (pstnPollTimerRef.current) window.clearInterval(pstnPollTimerRef.current);
        }
      } catch {
        // ignore transient polling error
      }
    }, 2000);
  };

  // ------------------------------------------------------------------
  // START & END CALL
  // ------------------------------------------------------------------
  const handleStartCall = async () => {
    if (!activeAgent) return;
    setDialError(null);
    setTranscripts([]);
    setToolEvents([]);
    setSessionTrace([]);
    setCallSummary(null);
    setTransferAlert(null);
    setWhatsAppAlert(null);
    setLifecycleStep('Connecting');
    setCurrentStage('1. Hook & Rapport');
    setBantQualified({ budget: false, authority: true, need: false, timeline: false });

    try {
      setLifecycleStep('Ringing');
      const callData = await initiateOutboundCall({
        agent_id: activeAgent.id,
        customer_phone: phone,
        customer_name: customerName,
        preferred_language: activeAgent.default_language,
        provider: callMode === 'real_phone' ? 'twilio' : 'web_simulator',
        twilio_trial_mode: callMode === 'real_phone' ? twilioTrialMode : false
      });

      setCallId(callData.id);

      if (callMode === 'real_phone') {
        setCallActive(true);
        setLifecycleStep('Ringing');
        if (callData.transcripts && callData.transcripts.length > 0) {
          setTranscripts(
            callData.transcripts.map(t => ({
              speaker: (t.speaker as any) || 'agent',
              text: t.text,
              language: t.language,
              latency: t.latency_ms,
            }))
          );
        }
        startPstnStatusPolling(callData.id);
        return;
      }

      // Browser Microphone Simulation via WebSocket
      startAmbientSoundscape(ambientMode);
      const loc = window.location;
      const wsProtocol = loc.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${wsProtocol}//${loc.host}/ws/voice/${callData.id}`;
      const socket = new WebSocket(wsUrl);
      wsRef.current = socket;

      socket.onopen = () => {
        setCallActive(true);
        setLifecycleStep('Answered');
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'greeting' || data.type === 'ai_response') {
            const aiText = data.text;
            const lang = data.language || 'hi';
            setDetectedLanguage(lang);
            setLifecycleStep(data.type === 'greeting' ? 'AI Connected' : 'Conversation Active');

            if (data.conversation_stage) setCurrentStage(data.conversation_stage);

            if (data.tool_calls && Array.isArray(data.tool_calls) && data.tool_calls.length > 0) {
              setToolEvents(prev => [...data.tool_calls, ...prev].slice(0, 8));
            }

            if (data.bant_progress) {
              setBantQualified(prev => ({
                budget: prev.budget || Boolean(data.bant_progress.budget),
                authority: prev.authority || Boolean(data.bant_progress.authority),
                need: prev.need || Boolean(data.bant_progress.need),
                timeline: prev.timeline || Boolean(data.bant_progress.timeline)
              }));
            }

            if (data.metrics) {
              setLastLatency({
                stt: 85,
                llm: data.metrics.llm_latency_ms || 195,
                tts: data.metrics.tts_latency_ms || 135,
                total: data.metrics.total_latency_ms || 415
              });
            }

            setTranscripts(prev => [
              ...prev,
              {
                speaker: 'agent',
                text: aiText,
                language: lang,
                latency: data.metrics?.total_latency_ms,
                stage: data.conversation_stage
              }
            ]);

            playAgentAudio(aiText, lang, data.audio);

            if (data.is_transfer) {
              setTransferAlert(`Escalated to ${activeAgent.company} specialist: ${data.transfer_number}`);
            }
            if (data.whatsapp_triggered) {
              setWhatsAppAlert(`Product brochure & summary dispatched to ${phone}`);
              setTimeout(() => setWhatsAppAlert(null), 6000);
            }
          } else if (data.type === 'call_summary') {
            stopAmbientSoundscape();
            setCallSummary(data.summary);
            if (data.session_trace && Array.isArray(data.session_trace)) {
              setSessionTrace(data.session_trace);
            } else if (data.summary?.key_information?.session_trace) {
              setSessionTrace(data.summary.key_information.session_trace);
            }
            setLifecycleStep('Completed');
            setCallActive(false);
          }
        } catch (e) {
          console.error(e);
        }
      };

      socket.onerror = () => {
        stopAmbientSoundscape();
        setDialError('WebSocket connection error. Verify the backend voice service is running on port 8000.');
        setLifecycleStep('Failed');
        setCallActive(false);
      };

      socket.onclose = () => {
        stopAmbientSoundscape();
        setCallActive(false);
      };
    } catch (err: any) {
      stopAmbientSoundscape();
      setDialError(err.message || 'Failed to initiate call');
      setLifecycleStep('Failed');
      setCallActive(false);
    }
  };

  const handleEndCall = async () => {
    stopAmbientSoundscape();
    if (pstnPollTimerRef.current) window.clearInterval(pstnPollTimerRef.current);
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    if (audioRef.current) audioRef.current.pause();

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'end_call' }));
    } else if (callId) {
      try {
        await terminateCall(callId);
        const detail = await fetchCallDetail(callId);
        if (detail.summary) {
          setCallSummary(detail.summary);
          if (detail.summary.key_information?.session_trace) {
            setSessionTrace(detail.summary.key_information.session_trace);
          }
        }
      } catch {
        // ignore
      }
      setCallActive(false);
      setLifecycleStep('Completed');
    }
  };

  const sendCustomerUtterance = (text: string) => {
    if (!text.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    handleInterruptAi();
    setLifecycleStep('Conversation Active');
    setTranscripts(prev => [
      ...prev,
      { speaker: 'customer', text: text.trim(), language: detectedLanguage }
    ]);
    wsRef.current.send(JSON.stringify({
      type: 'user_utterance',
      text: text.trim(),
      language: detectedLanguage
    }));
  };

  const handleCustomSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!customUtterance.trim()) return;
    sendCustomerUtterance(customUtterance);
    setCustomUtterance('');
  };

  const startPushToTalk = () => {
    handleInterruptAi();
    setIsRecordingPTT(true);
    setIsCustomerSpeaking(true);
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = detectedLanguage === 'te' ? 'te-IN' : detectedLanguage === 'en' ? 'en-IN' : 'hi-IN';
      recognition.onresult = (event: any) => {
        const spokenText = event.results[0][0].transcript;
        if (spokenText) sendCustomerUtterance(spokenText);
      };
      recognition.onerror = () => {
        setIsCustomerSpeaking(false);
        setIsRecordingPTT(false);
      };
      recognition.onend = () => {
        setIsCustomerSpeaking(false);
        setIsRecordingPTT(false);
      };
      recognitionRef.current = recognition;
      recognition.start();
    }
  };

  const stopPushToTalk = () => {
    setIsRecordingPTT(false);
    setIsCustomerSpeaking(false);
    if (recognitionRef.current) recognitionRef.current.stop();
  };

  const getProductTestPrompts = () => {
    const bp = activeAgent?.blueprint;
    if (bp === 'real_estate') {
      return [
        { label: 'Product & Pricing Inquiry', text: 'नमस्ते! मैं फैमिली के लिए 3 BHK देख रहा हूँ—प्राइसिंग और पजेशन क्या है?' },
        { label: 'Price Objection', text: '₹2.15 करोड़ का प्राइस थोड़ा ज्यादा लग रहा है, क्या कोई फ्लेक्सिबल पेमेंट प्लान है?' },
        { label: 'Request Brochure on WhatsApp', text: 'क्या आप मुझे फ्लोर प्लान और प्राइस शीट व्हाट्सएप पर भेज सकते हैं?' },
        { label: 'Schedule Site Visit', text: 'इस शनिवार सुबह 11:00 बजे का साइट विजिट स्लॉट बुक कर दीजिए।' }
      ];
    } else if (bp === 'clinic_healthcare') {
      return [
        { label: 'Specialist Consultation', text: 'Hello, I would like to consult a senior Cardiologist for a checkup.' },
        { label: 'Fees & Timings', text: 'What is the consultation fee, and do you offer video consultations?' },
        { label: 'Confirm Appointment', text: 'Please book my appointment for tomorrow morning at 10:30 AM.' }
      ];
    } else {
      return [
        { label: 'Product Capability Inquiry', text: 'How fast can your platform dial inbound leads and what languages are supported?' },
        { label: 'Pricing & SLA Question', text: 'What is your per-minute pricing and uptime SLA?' },
        { label: 'Schedule Live Demo', text: 'Please schedule a 20-minute architecture demo for Wednesday at 3 PM.' }
      ];
    }
  };

  const activeLifecycleIndex = LIFECYCLE_STEPS.indexOf(
    lifecycleStep === 'Failed' ? 'Ringing' : lifecycleStep
  );

  return (
    <div className="space-y-6">
      <audio ref={audioRef} className="hidden" />

      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 dark:border-slate-800/80 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">Live Voice Studio</h1>
            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-50 dark:bg-indigo-950/80 text-indigo-600 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-800/60">
              Interactive AI
            </span>
          </div>
          <p className="text-slate-500 dark:text-slate-400 text-xs mt-1">
            Configure, test, and monitor real-time company-grounded AI voice conversations via Browser Simulation or Twilio PSTN.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-500 dark:text-slate-400">Session State:</span>
          <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${
            lifecycleStep === 'Conversation Active' || lifecycleStep === 'AI Connected'
              ? 'bg-emerald-50 dark:bg-emerald-950/90 text-emerald-700 dark:text-emerald-400 border-emerald-300 dark:border-emerald-800'
              : lifecycleStep === 'Ringing' || lifecycleStep === 'Connecting'
              ? 'bg-amber-50 dark:bg-amber-950/90 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-800 animate-pulse'
              : lifecycleStep === 'Failed'
              ? 'bg-rose-50 dark:bg-rose-950/90 text-rose-700 dark:text-rose-400 border-rose-300 dark:border-rose-800'
              : 'bg-slate-100 dark:bg-slate-900 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-800'
          }`}>
            <span className={`w-2 h-2 rounded-full ${
              lifecycleStep === 'Conversation Active' || lifecycleStep === 'AI Connected'
                ? 'bg-emerald-500'
                : lifecycleStep === 'Ringing' || lifecycleStep === 'Connecting'
                ? 'bg-amber-500'
                : lifecycleStep === 'Failed'
                ? 'bg-rose-500'
                : 'bg-slate-400'
            }`} />
            {lifecycleStep}
          </span>
        </div>
      </div>

      {/* Connection Lifecycle Stepper (Section 6 Top Bar) */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800/90 rounded-xl p-4 shadow-xs">
        <div className="flex items-center justify-between mb-2.5">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Call Session Lifecycle
          </span>
          <span className="text-[11px] font-mono font-medium text-indigo-600 dark:text-indigo-400">
            Stage: {currentStage}
          </span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-7 gap-2">
          {LIFECYCLE_STEPS.map((step, idx) => {
            const isCurrent = lifecycleStep === step;
            const isPassed = idx < activeLifecycleIndex && lifecycleStep !== 'Failed';
            return (
              <div
                key={step}
                className={`px-2.5 py-2 rounded-lg border text-[11px] flex items-center gap-2 transition-colors ${
                  isCurrent
                    ? 'bg-indigo-50 dark:bg-indigo-600/20 border-indigo-300 dark:border-indigo-500 text-indigo-900 dark:text-white font-semibold'
                    : isPassed
                    ? 'bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800/60 text-emerald-800 dark:text-emerald-300'
                    : 'bg-slate-50 dark:bg-slate-950 border-slate-200 dark:border-slate-800/80 text-slate-400 dark:text-slate-500'
                }`}
              >
                <span className={`w-4 h-4 rounded-full text-[10px] flex items-center justify-center font-bold shrink-0 ${
                  isCurrent ? 'bg-indigo-600 text-white' : isPassed ? 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400' : 'bg-slate-200 dark:bg-slate-800 text-slate-500'
                }`}>
                  {isPassed ? '✓' : idx + 1}
                </span>
                <span className="truncate">{step}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Actionable Error Banner */}
      {dialError && (
        <div className="p-4 bg-rose-950/50 border border-rose-800 rounded-xl text-rose-200 text-xs flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 shrink-0 text-rose-400 mt-0.5" />
            <div>
              <strong className="block text-white font-semibold mb-0.5">Call Initiation Blocked</strong>
              <p className="leading-relaxed">{dialError}</p>
            </div>
          </div>
          {onNavigate && (
            <button
              onClick={() => onNavigate('settings')}
              className="px-3 py-1.5 bg-rose-900/80 hover:bg-rose-800 text-white rounded-lg font-medium shrink-0"
            >
              Open Carrier Config
            </button>
          )}
        </div>
      )}

      {/* Main Workspace Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Sections 1, 2, 3, 4, 5 (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          {/* SECTION 1: Company & AI Employee Selection */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800/90 rounded-xl p-5 space-y-3 shadow-xs">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300 flex items-center gap-2">
                <Building2 className="w-4 h-4 text-indigo-500" />
                1. Company &amp; AI Employee
              </h2>
              <button
                type="button"
                onClick={handleAuditionVoice}
                disabled={isAuditioning}
                className="text-[11px] font-medium bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 px-2.5 py-1 rounded-lg flex items-center gap-1.5 transition-colors"
              >
                <Play className="w-3 h-3 text-indigo-500 fill-indigo-500" />
                {isAuditioning ? 'Playing...' : 'Preview Voice'}
              </button>
            </div>

            <div>
              <label className="block text-[11px] font-medium text-slate-500 dark:text-slate-400 mb-1">Active Company &amp; Assigned Agent</label>
              <select
                disabled={callActive}
                value={selectedAgentId}
                onChange={(e) => setSelectedAgentId(e.target.value)}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none focus:border-indigo-500"
              >
                {agents.map((ag) => (
                  <option key={ag.id} value={ag.id} className="bg-white dark:bg-slate-900 text-slate-900 dark:text-white">
                    {ag.company} — {ag.name} ({ag.purpose})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* SECTION 2: Product / Service Knowledge Status */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800/90 rounded-xl p-5 space-y-2.5 shadow-xs">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300 flex items-center gap-2">
                <BookOpen className="w-4 h-4 text-emerald-500" />
                2. Product &amp; Service Knowledge (RAG)
              </h2>
              {onNavigate && (
                <button
                  onClick={() => onNavigate('knowledge')}
                  className="text-[11px] text-indigo-600 dark:text-indigo-400 hover:underline font-medium"
                >
                  Manage Sources
                </button>
              )}
            </div>

            <div className="p-3 bg-slate-50 dark:bg-slate-950/60 rounded-lg border border-slate-200 dark:border-slate-800 text-xs space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-slate-500 dark:text-slate-400">Tenant Workspace:</span>
                <span className="font-semibold text-slate-900 dark:text-white">{activeAgent?.company || matchedWorkspace?.company_name}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500 dark:text-slate-400">Approved Sources:</span>
                <span className="font-mono text-emerald-600 dark:text-emerald-400 font-semibold">
                  {approvedDocs.length} documents ({totalApprovedChunks} chunks indexed)
                </span>
              </div>
              {matchedWorkspace?.products_services && (
                <p className="text-[11px] text-slate-600 dark:text-slate-400 pt-1 border-t border-slate-200 dark:border-slate-800 line-clamp-2">
                  {matchedWorkspace.products_services}
                </p>
              )}
            </div>
          </div>

          {/* SECTION 3 & 4: Call Purpose, Language, Voice & Tone */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800/90 rounded-xl p-5 space-y-3 shadow-xs">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300 flex items-center gap-2">
              <Target className="w-4 h-4 text-indigo-500" />
              3 &amp; 4. Call Objective, Language &amp; Voice
            </h2>

            <div className="p-3 bg-slate-50 dark:bg-slate-950/60 rounded-lg border border-slate-200 dark:border-slate-800 text-xs space-y-2">
              <div>
                <span className="text-[10px] uppercase text-slate-500 font-semibold block">Campaign Objective</span>
                <span className="text-slate-800 dark:text-slate-200 font-medium">{activeAgent?.purpose} ({activeAgent?.qualification_framework || 'BANT'})</span>
              </div>
              <div>
                <span className="text-[10px] uppercase text-slate-500 font-semibold block">Opening Greeting</span>
                <p className="text-slate-700 dark:text-slate-300 italic text-[11px] line-clamp-2">"{activeAgent?.greeting}"</p>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2 text-xs">
              <div className="bg-slate-50 dark:bg-slate-950/60 p-2.5 rounded-lg border border-slate-200 dark:border-slate-800">
                <span className="text-[10px] text-slate-500 uppercase font-semibold block">Language</span>
                <strong className="text-slate-800 dark:text-slate-200 uppercase font-mono">
                  {detectedLanguage} ({activeAgent?.supported_languages?.join('/') || 'multi'})
                </strong>
              </div>
              <div className="bg-slate-50 dark:bg-slate-950/60 p-2.5 rounded-lg border border-slate-200 dark:border-slate-800">
                <span className="text-[10px] text-slate-500 uppercase font-semibold block">Pace</span>
                <select
                  value={voiceSpeed}
                  onChange={(e) => setVoiceSpeed(parseFloat(e.target.value))}
                  className="bg-transparent text-slate-800 dark:text-slate-200 font-mono text-xs focus:outline-none w-full"
                >
                  <option value={0.96} className="bg-white dark:bg-slate-900 text-slate-900 dark:text-white">0.96x Calm</option>
                  <option value={1.04} className="bg-white dark:bg-slate-900 text-slate-900 dark:text-white">1.04x Natural</option>
                  <option value={1.1} className="bg-white dark:bg-slate-900 text-slate-900 dark:text-white">1.10x Brisk</option>
                </select>
              </div>
              <div className="bg-slate-50 dark:bg-slate-950/60 p-2.5 rounded-lg border border-slate-200 dark:border-slate-800">
                <span className="text-[10px] text-slate-500 uppercase font-semibold block">Ambience</span>
                <select
                  value={ambientMode}
                  onChange={(e) => {
                    const next = e.target.value as any;
                    setAmbientMode(next);
                    if (callActive) startAmbientSoundscape(next);
                  }}
                  className="bg-transparent text-slate-800 dark:text-slate-200 text-xs focus:outline-none w-full"
                >
                  <option value="office_call_center" className="bg-white dark:bg-slate-900 text-slate-900 dark:text-white">Office Floor</option>
                  <option value="executive_room" className="bg-white dark:bg-slate-900 text-slate-900 dark:text-white">Quiet Room</option>
                  <option value="none" className="bg-white dark:bg-slate-900 text-slate-900 dark:text-white">None</option>
                </select>
              </div>
            </div>
          </div>

          {/* SECTION 5: Test-Call Configuration & Execution */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800/90 rounded-xl p-5 space-y-4 shadow-xs">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300 flex items-center gap-2">
              <Phone className="w-4 h-4 text-indigo-500" />
              5. Test-Call Mode &amp; Controls
            </h2>

            {/* Mode Selector */}
            <div className="grid grid-cols-2 gap-2 p-1 bg-slate-100 dark:bg-slate-950 rounded-lg border border-slate-200 dark:border-slate-800">
              <button
                type="button"
                disabled={callActive}
                onClick={() => setCallMode('browser')}
                className={`py-2 px-3 rounded-md text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors ${
                  callMode === 'browser'
                    ? 'bg-white dark:bg-indigo-600 text-indigo-600 dark:text-white shadow-xs'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                }`}
              >
                <Monitor className="w-3.5 h-3.5" /> Browser Simulation
              </button>
              <button
                type="button"
                disabled={callActive}
                onClick={() => setCallMode('real_phone')}
                className={`py-2 px-3 rounded-md text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors ${
                  callMode === 'real_phone'
                    ? 'bg-white dark:bg-indigo-600 text-indigo-600 dark:text-white shadow-xs'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                }`}
              >
                <Smartphone className="w-3.5 h-3.5" /> Real PSTN Call
              </button>
            </div>

            {/* Real PSTN Readiness Check */}
            {callMode === 'real_phone' && (
              <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 text-xs space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-slate-500 dark:text-slate-400">Twilio Carrier:</span>
                  <span className={telephonyStatus?.twilio_configured ? 'text-emerald-600 dark:text-emerald-400 font-medium' : 'text-amber-600 dark:text-amber-400 font-medium'}>
                    {telephonyStatus?.twilio_configured
                      ? `Ready (${telephonyStatus.twilio_phone_number || telephonyStatus.twilio_account_sid_masked})`
                      : 'Credentials Missing'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500 dark:text-slate-400">Public Webhook URL:</span>
                  <span className={telephonyStatus?.public_webhook_url ? 'text-emerald-600 dark:text-emerald-400 font-mono text-[11px]' : 'text-amber-600 dark:text-amber-400 text-[11px]'}>
                    {telephonyStatus?.public_webhook_url || 'Not set (Required for live PSTN AI)'}
                  </span>
                </div>
                <label className="flex items-center gap-2 pt-1.5 border-t border-slate-200 dark:border-slate-800 cursor-pointer text-slate-700 dark:text-slate-300">
                  <input
                    type="checkbox"
                    checked={twilioTrialMode}
                    onChange={(e) => setTwilioTrialMode(e.target.checked)}
                    className="rounded accent-indigo-600"
                  />
                  <span className="text-[11px]">
                    Twilio Free-Trial Connectivity Check Only (plays Twilio demo XML; uncheck for live AI conversation)
                  </span>
                </label>
              </div>
            )}

            {/* Recipient Inputs */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] font-medium text-slate-500 dark:text-slate-400 mb-1">Contact Name</label>
                <input
                  type="text"
                  disabled={callActive}
                  value={customerName}
                  onChange={(e) => setCustomerName(e.target.value)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div>
                <label className="block text-[11px] font-medium text-slate-500 dark:text-slate-400 mb-1">Phone Number (E.164)</label>
                <input
                  type="text"
                  disabled={callActive}
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-900 dark:text-white font-mono focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            {/* Primary Call Action Buttons */}
            {!callActive ? (
              <button
                onClick={handleStartCall}
                className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-semibold py-3 px-4 rounded-lg text-xs flex items-center justify-center gap-2 shadow-sm transition-colors"
              >
                <Phone className="w-4 h-4" />
                {callMode === 'real_phone'
                  ? `Place Outbound PSTN Call (${phone})`
                  : `Start Simulated Call with ${activeAgent?.name || 'AI Employee'}`}
              </button>
            ) : (
              <div className="space-y-2.5">
                {callMode === 'browser' && (
                  <button
                    onMouseDown={startPushToTalk}
                    onMouseUp={stopPushToTalk}
                    onTouchStart={startPushToTalk}
                    onTouchEnd={stopPushToTalk}
                    className={`w-full py-2.5 px-4 rounded-lg font-semibold text-xs flex items-center justify-center gap-2 transition-colors ${
                      isRecordingPTT
                        ? 'bg-rose-600 text-white animate-pulse'
                        : 'bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-100 border border-slate-300 dark:border-slate-700'
                    }`}
                  >
                    <Mic className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                    {isRecordingPTT ? 'Listening... Release to Send' : 'Hold to Speak (Microphone)'}
                  </button>
                )}

                <div className="grid grid-cols-2 gap-2.5">
                  <button
                    onClick={handleInterruptAi}
                    disabled={!isAiSpeaking}
                    className={`py-2 px-3 rounded-lg font-medium text-xs flex items-center justify-center gap-1.5 transition-colors ${
                      isAiSpeaking
                        ? 'bg-amber-500/20 text-amber-700 dark:text-amber-300 border border-amber-500/40 hover:bg-amber-500/30'
                        : 'bg-slate-100 dark:bg-slate-950 text-slate-400 dark:text-slate-600 border border-slate-200 dark:border-slate-800 cursor-not-allowed'
                    }`}
                  >
                    <ShieldAlert className="w-3.5 h-3.5" /> Interrupt (Barge-In)
                  </button>

                  <button
                    onClick={handleEndCall}
                    className="bg-rose-600 hover:bg-rose-500 text-white font-semibold py-2 px-3 rounded-lg text-xs flex items-center justify-center gap-1.5 transition-colors"
                  >
                    <PhoneOff className="w-3.5 h-3.5" /> End Call
                  </button>
                </div>
              </div>
            )}

            {transferAlert && (
              <div className="p-2.5 bg-indigo-50 dark:bg-indigo-950/60 border border-indigo-200 dark:border-indigo-800 rounded-lg text-indigo-800 dark:text-indigo-200 text-xs flex items-center gap-2">
                <UserCheck className="w-4 h-4 text-indigo-600 dark:text-indigo-400 shrink-0" />
                <span>{transferAlert}</span>
              </div>
            )}
            {whatsAppAlert && (
              <div className="p-2.5 bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800 rounded-lg text-emerald-800 dark:text-emerald-200 text-xs flex items-center gap-2">
                <MessageSquare className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
                <span>{whatsAppAlert}</span>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Sections 6 & 7 (7 cols) */}
        <div className="lg:col-span-7 space-y-4">
          {/* SECTION 6: Real-Time Call Status & Conversation Transcript */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800/90 rounded-xl overflow-hidden flex flex-col h-[500px] shadow-xs">
            {/* Transcript Header */}
            <div className="px-5 py-3.5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50/80 dark:bg-slate-950/60">
              <div className="flex items-center gap-2.5">
                <MessageSquare className="w-4 h-4 text-indigo-500" />
                <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-900 dark:text-white">
                  6. Live Conversation Transcript
                </h2>
                {isAiSpeaking && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-indigo-50 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-300 text-[10px] font-semibold">
                    <Volume2 className="w-3 h-3 animate-pulse" /> AI Speaking
                  </span>
                )}
              </div>

              <div className="flex items-center gap-3 text-[11px] text-slate-500 dark:text-slate-400">
                <span>Engine: <strong className="text-slate-700 dark:text-slate-200">{voiceEngineLabel}</strong></span>
                <span>•</span>
                <span className="font-mono text-emerald-600 dark:text-emerald-400 font-semibold">{lastLatency.total}ms turn</span>
              </div>
            </div>

            {/* Messages Area */}
            <div className="flex-1 p-5 overflow-y-auto space-y-3.5 bg-white dark:bg-slate-900/50">
              {transcripts.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-slate-400 dark:text-slate-500 text-xs text-center px-6">
                  <Phone className="w-8 h-8 text-slate-300 dark:text-slate-700 mb-2.5" />
                  <p className="text-slate-700 dark:text-slate-300 font-semibold mb-1">No Active Conversation</p>
                  <p className="max-w-md text-slate-500 dark:text-slate-400">
                    Start a Browser Simulation or Real PSTN Call on the left to begin a multi-turn conversation grounded in {activeAgent?.company}'s approved knowledge base.
                  </p>
                </div>
              ) : (
                transcripts.map((t, idx) => (
                  <div
                    key={idx}
                    className={`flex flex-col ${
                      t.speaker === 'agent' ? 'items-start' :
                      t.speaker === 'customer' ? 'items-end' : 'items-center'
                    }`}
                  >
                    <div className="flex items-center gap-1.5 mb-1 text-[10px] text-slate-400 dark:text-slate-500">
                      <span className="font-semibold text-slate-700 dark:text-slate-300">
                        {t.speaker === 'agent' ? activeAgent?.name : t.speaker === 'customer' ? customerName : 'System'}
                      </span>
                      {t.language && <span className="uppercase text-indigo-600 dark:text-indigo-400 font-mono font-medium">• {t.language}</span>}
                      {t.latency && <span className="text-emerald-600 dark:text-emerald-400 font-mono">• {t.latency}ms</span>}
                    </div>
                    <div
                      className={`max-w-[85%] px-4 py-3 rounded-xl text-xs leading-relaxed ${
                        t.speaker === 'agent'
                          ? 'bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-slate-100 border border-slate-200 dark:border-slate-700/80'
                          : t.speaker === 'customer'
                          ? 'bg-indigo-600 text-white shadow-xs'
                          : 'bg-slate-50 dark:bg-slate-950 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-800 text-center text-[11px]'
                      }`}
                    >
                      {t.text}
                    </div>
                  </div>
                ))
              )}
              <div ref={transcriptBottomRef} />
            </div>

            {/* Quick Product Prompts Bar (when Browser Call is active) */}
            {callMode === 'browser' && (
              <div className="px-4 py-2.5 bg-slate-50 dark:bg-slate-950/90 border-t border-slate-200 dark:border-slate-800/80 flex items-center gap-2 overflow-x-auto">
                <span className="text-[10px] text-slate-500 dark:text-slate-400 uppercase font-semibold shrink-0">Quick Prompts:</span>
                {getProductTestPrompts().map((p, idx) => (
                  <button
                    key={idx}
                    disabled={!callActive}
                    onClick={() => sendCustomerUtterance(p.text)}
                    className="px-2.5 py-1 rounded-md bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-800 text-[11px] whitespace-nowrap disabled:opacity-40 transition-colors"
                  >
                    {p.label}
                  </button>
                ))}
                <button
                  disabled={!callActive}
                  onClick={() => sendCustomerUtterance('Can you explain in English?')}
                  className="px-2.5 py-1 rounded-md bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-indigo-600 dark:text-indigo-400 border border-slate-200 dark:border-slate-800 text-[11px] whitespace-nowrap disabled:opacity-40"
                >
                  Switch to English
                </button>
                <button
                  disabled={!callActive}
                  onClick={() => sendCustomerUtterance('తెలుగులో చెప్పండి')}
                  className="px-2.5 py-1 rounded-md bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-indigo-600 dark:text-indigo-400 border border-slate-200 dark:border-slate-800 text-[11px] whitespace-nowrap disabled:opacity-40"
                >
                  Switch to Telugu
                </button>
              </div>
            )}

            {/* Text Utterance Input */}
            <form
              onSubmit={handleCustomSubmit}
              className="p-3 bg-slate-50 dark:bg-slate-950 border-t border-slate-200 dark:border-slate-800 flex items-center gap-2"
            >
              <input
                type="text"
                disabled={!callActive || callMode !== 'browser'}
                value={customUtterance}
                onChange={(e) => setCustomUtterance(e.target.value)}
                placeholder={
                  callActive && callMode === 'browser'
                    ? `Ask ${activeAgent?.name} a question about ${activeAgent?.company}...`
                    : callMode === 'real_phone'
                    ? 'Speak directly into your phone handset during a PSTN call...'
                    : 'Start a simulated call to type or speak customer responses...'
                }
                className="flex-1 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-800 rounded-lg px-3.5 py-2 text-xs text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:border-indigo-500 disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!callActive || callMode !== 'browser' || !customUtterance.trim()}
                className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white font-medium px-4 py-2 rounded-lg text-xs flex items-center gap-1.5 transition-colors"
              >
                <Send className="w-3.5 h-3.5" /> Send
              </button>
            </form>
          </div>

          {/* SECTION 7: Call Result, BANT & Quality Assessment */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800/90 rounded-xl p-5 space-y-4 shadow-xs">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                7. Call Result, BANT Qualification &amp; Session Trace
              </h2>
              <span className="text-[11px] font-mono text-emerald-600 dark:text-emerald-400 font-semibold">
                {Object.values(bantQualified).filter(Boolean).length}/4 BANT Verified
              </span>
            </div>

            {/* Live BANT Slots */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
              <div className={`p-3 rounded-lg border ${
                bantQualified.budget || callSummary?.bant_score?.budget
                  ? 'bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800/70 text-emerald-800 dark:text-emerald-300'
                  : 'bg-slate-50 dark:bg-slate-950 border-slate-200 dark:border-slate-800/80 text-slate-500 dark:text-slate-400'
              }`}>
                <span className="text-[10px] uppercase text-slate-400 dark:text-slate-500 font-semibold block">Budget</span>
                <strong className="block mt-0.5 truncate text-slate-900 dark:text-white">
                  {callSummary?.bant_score?.budget || (bantQualified.budget ? 'Verified' : 'Pending')}
                </strong>
              </div>
              <div className={`p-3 rounded-lg border ${
                bantQualified.authority || callSummary?.bant_score?.authority
                  ? 'bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800/70 text-emerald-800 dark:text-emerald-300'
                  : 'bg-slate-50 dark:bg-slate-950 border-slate-200 dark:border-slate-800/80 text-slate-500 dark:text-slate-400'
              }`}>
                <span className="text-[10px] uppercase text-slate-400 dark:text-slate-500 font-semibold block">Authority</span>
                <strong className="block mt-0.5 truncate text-slate-900 dark:text-white">
                  {callSummary?.bant_score?.authority || (bantQualified.authority ? 'Decision Maker' : 'Pending')}
                </strong>
              </div>
              <div className={`p-3 rounded-lg border ${
                bantQualified.need || callSummary?.bant_score?.need
                  ? 'bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800/70 text-emerald-800 dark:text-emerald-300'
                  : 'bg-slate-50 dark:bg-slate-950 border-slate-200 dark:border-slate-800/80 text-slate-500 dark:text-slate-400'
              }`}>
                <span className="text-[10px] uppercase text-slate-400 dark:text-slate-500 font-semibold block">Need</span>
                <strong className="block mt-0.5 truncate text-slate-900 dark:text-white">
                  {callSummary?.bant_score?.need || (bantQualified.need ? 'Identified' : 'Pending')}
                </strong>
              </div>
              <div className={`p-3 rounded-lg border ${
                bantQualified.timeline || callSummary?.bant_score?.timeline
                  ? 'bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800/70 text-emerald-800 dark:text-emerald-300'
                  : 'bg-slate-50 dark:bg-slate-950 border-slate-200 dark:border-slate-800/80 text-slate-500 dark:text-slate-400'
              }`}>
                <span className="text-[10px] uppercase text-slate-400 dark:text-slate-500 font-semibold block">Timeline</span>
                <strong className="block mt-0.5 truncate text-slate-900 dark:text-white">
                  {callSummary?.bant_score?.timeline || (bantQualified.timeline ? 'Confirmed' : 'Pending')}
                </strong>
              </div>
            </div>

            {/* Post-Call Summary (when available) */}
            {callSummary && (
              <div className="p-4 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <strong className="text-slate-900 dark:text-white">Executive Summary</strong>
                  <span className="px-2 py-0.5 rounded bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800 text-[10px] font-semibold">
                    {callSummary.qualification_status || callSummary.outcome}
                  </span>
                </div>
                <p className="text-slate-700 dark:text-slate-300 leading-relaxed">{callSummary.summary_text}</p>
                {callSummary.next_action && (
                  <p className="text-indigo-600 dark:text-indigo-300 text-[11px] pt-1 border-t border-slate-200 dark:border-slate-800 font-medium">
                    <strong>Next Step:</strong> {callSummary.next_action}
                  </p>
                )}
              </div>
            )}

            {/* Verified Tool Execution & Session Trace */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800/80 rounded-lg p-3">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 flex items-center gap-1.5 mb-2">
                  <Terminal className="w-3.5 h-3.5 text-indigo-500" /> Verified Tool Calls ({toolEvents.length})
                </span>
                {toolEvents.length === 0 ? (
                  <p className="text-[11px] text-slate-400 dark:text-slate-500">No mid-call tools executed yet.</p>
                ) : (
                  <div className="space-y-1.5 max-h-28 overflow-y-auto">
                    {toolEvents.map((ev, i) => (
                      <div key={i} className="text-[11px] font-mono flex items-center justify-between text-slate-700 dark:text-slate-300">
                        <span className="truncate"><strong className="text-indigo-600 dark:text-indigo-300">{ev.name}</strong> — {ev.detail}</span>
                        <span className="text-emerald-600 dark:text-emerald-400 ml-2 shrink-0">{ev.latency_ms}ms</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800/80 rounded-lg p-3">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 flex items-center gap-1.5 mb-2">
                  <Clock className="w-3.5 h-3.5 text-emerald-500" /> Call-Session Trace ({sessionTrace.length})
                </span>
                {sessionTrace.length === 0 ? (
                  <p className="text-[11px] text-slate-400 dark:text-slate-500">
                    Lifecycle trace events populate upon call completion.
                  </p>
                ) : (
                  <div className="space-y-1 max-h-28 overflow-y-auto font-mono text-[10px]">
                    {sessionTrace.map((ev, idx) => (
                      <div key={idx} className="text-slate-700 dark:text-slate-300 flex items-center justify-between">
                        <span className="text-emerald-600 dark:text-emerald-400">{ev.event}</span>
                        <span className="text-slate-400 dark:text-slate-500">
                          {ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : ''}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
