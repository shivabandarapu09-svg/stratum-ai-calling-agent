import React, { useEffect, useState, useRef } from 'react';
import {
  Bot, Plus, Languages, PhoneForwarded, Volume2,
  Play, Pause, CheckCircle2, Edit3, BookOpen, PhoneCall, Wrench, RefreshCw
} from 'lucide-react';
import { Agent, BlueprintTemplate, KnowledgeDoc } from '../types';
import {
  fetchAgents, createAgent, updateAgent, fetchBlueprintTemplates,
  previewVoiceSample, fetchKnowledgeDocs
} from '../api';
import { 
  Button, Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter,
  Badge, Input, Textarea, Select, Dialog, LoadingState, EmptyState 
} from '../components/ui';

export const Agents: React.FC<{ onNavigate?: (tab: string) => void }> = ({ onNavigate }) => {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [blueprints, setBlueprints] = useState<BlueprintTemplate[]>([]);
  const [knowledgeDocs, setKnowledgeDocs] = useState<KnowledgeDoc[]>([]);
  const [showModal, setShowModal] = useState<boolean>(false);
  const [editingAgentId, setEditingAgentId] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [playingAgentId, setPlayingAgentId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Agent Configuration Form
  const [formName, setFormName] = useState('Vikram');
  const [formCompany, setFormCompany] = useState('Prestige & Godrej Luxury Living');
  const [formPurpose, setFormPurpose] = useState('Real Estate Lead Qualification & Site Visit Scheduling');
  const [formBlueprint, setFormBlueprint] = useState('real_estate');
  const [formPersonality, setFormPersonality] = useState('Warm, Consultative, Respectful & Clear');
  const [formGreeting, setFormGreeting] = useState('नमस्ते जी! मैं प्रेस्टीज लक्ज़री हाइट्स से विक्रम बात कर रहा हूँ। क्या अभी 2 मिनट बात करने का सही समय है?');
  const [formPrompt, setFormPrompt] = useState('Introduce yourself and the company clearly. Understand customer requirements, answer questions using approved knowledge documents, and schedule a site visit or consultation.');
  const [formLang, setFormLang] = useState('hi');
  const [formSupportedLangs, setFormSupportedLangs] = useState<string[]>(['hi', 'en', 'te', 'ta', 'kn']);
  const [formVoice, setFormVoice] = useState('hi-IN-MadhurNeural');
  const [formSpeed, setFormSpeed] = useState<number>(1.04);
  const [formAmbient, setFormAmbient] = useState<string>('office_call_center');
  const [formTransfer, setFormTransfer] = useState('+919876543210');
  const [formWhatsApp, setFormWhatsApp] = useState('Hi {name}, thank you for speaking with us. Here are the product details you requested: {link}');
  const [formSpeedToLead, setFormSpeedToLead] = useState(true);

  const loadData = () => {
    setLoading(true);
    Promise.all([fetchAgents(), fetchBlueprintTemplates(), fetchKnowledgeDocs()])
      .then(([agentsData, bpData, docsData]) => {
        setAgents(agentsData || []);
        setBlueprints(bpData || []);
        setKnowledgeDocs(docsData || []);
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

  const approvedDocCount = knowledgeDocs.filter((d) => d.approval_status === 'approved').length;

  const handlePlaySample = async (agent: Agent) => {
    setPlayingAgentId(agent.id);
    try {
      const res = await previewVoiceSample({
        voice_id: agent.voice_id,
        language: agent.default_language,
        text: agent.greeting,
        speaking_speed: agent.speaking_speed,
      });

      if (res.audio_base64) {
        if (audioRef.current) {
          audioRef.current.src = `data:audio/mp3;base64,${res.audio_base64}`;
          audioRef.current.play();
          audioRef.current.onended = () => setPlayingAgentId(null);
        }
      } else {
        if ('speechSynthesis' in window) {
          window.speechSynthesis.cancel();
          const utterance = new SpeechSynthesisUtterance(agent.greeting);
          utterance.rate = agent.speaking_speed || 1.0;
          utterance.onend = () => setPlayingAgentId(null);
          utterance.onerror = () => setPlayingAgentId(null);
          window.speechSynthesis.speak(utterance);
        }
      }
    } catch (e) {
      console.error('Audio preview error:', e);
      setPlayingAgentId(null);
    }
  };

  const handleToggleActive = async (agent: Agent) => {
    try {
      const updated = await updateAgent(agent.id, { is_active: !agent.is_active });
      setAgents((prev) => prev.map((a) => (a.id === agent.id ? updated : a)));
    } catch (e) {
      console.error('Toggle active error:', e);
    }
  };

  const openCreateModal = () => {
    setEditingAgentId(null);
    setFormName('Aditi');
    setFormCompany('Apex Care Hospitals');
    setFormPurpose('Specialist Doctor Appointment Booking & Patient Follow-up');
    setFormBlueprint('clinic_healthcare');
    setFormPersonality('Empathetic, Courteous, Highly Professional');
    setFormGreeting('Hello! This is Aditi calling from Apex Care Hospitals regarding your recent health consultation inquiry.');
    setFormPrompt('Verify patient symptoms, quote consultation fees, and schedule an appointment with the appropriate specialist.');
    setFormLang('en');
    setFormSupportedLangs(['en', 'hi', 'te']);
    setFormVoice('en-IN-NeerjaNeural');
    setFormSpeed(1.0);
    setFormAmbient('executive_room');
    setFormTransfer('+919876543210');
    setFormWhatsApp('Thank you for booking with Apex Care. Your appointment token is: {link}');
    setFormSpeedToLead(true);
    setShowModal(true);
  };

  const openEditModal = (agent: Agent) => {
    setEditingAgentId(agent.id);
    setFormName(agent.name);
    setFormCompany(agent.company);
    setFormPurpose(agent.purpose);
    setFormBlueprint(agent.blueprint);
    setFormPersonality(agent.personality);
    setFormGreeting(agent.greeting);
    setFormPrompt(agent.system_prompt);
    setFormLang(agent.default_language);
    setFormSupportedLangs(agent.supported_languages || [agent.default_language]);
    setFormVoice(agent.voice_id);
    setFormSpeed(agent.speaking_speed || 1.0);
    setFormAmbient(agent.ambient_sound || 'office_call_center');
    setFormTransfer(agent.transfer_number || '');
    setFormWhatsApp(agent.whatsapp_template || '');
    setFormSpeedToLead(agent.speed_to_lead_enabled ?? true);
    setShowModal(true);
  };

  const handleApplyBlueprint = (bp: BlueprintTemplate) => {
    setEditingAgentId(null);
    setFormBlueprint(bp.blueprint);
    setFormName(bp.title.split(' ')[0]);
    setFormCompany(bp.default_company);
    setFormPurpose(bp.description);
    setFormLang(bp.default_language);
    setFormVoice(bp.voice_id);
    setShowModal(true);
  };

  const toggleSupportedLang = (code: string) => {
    setFormSupportedLangs((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]
    );
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    const payload = {
      name: formName,
      company: formCompany,
      purpose: formPurpose,
      blueprint: formBlueprint,
      personality: formPersonality,
      greeting: formGreeting,
      system_prompt: formPrompt,
      default_language: formLang,
      supported_languages: formSupportedLangs.length > 0 ? formSupportedLangs : [formLang],
      voice_id: formVoice,
      speaking_speed: formSpeed,
      ambient_sound: formAmbient,
      transfer_number: formTransfer,
      whatsapp_template: formWhatsApp,
      speed_to_lead_enabled: formSpeedToLead,
    };

    try {
      if (editingAgentId) {
        const updated = await updateAgent(editingAgentId, payload);
        setAgents((prev) => prev.map((a) => (a.id === editingAgentId ? updated : a)));
      } else {
        const created = await createAgent(payload);
        setAgents((prev) => [...prev, created]);
      }
      setShowModal(false);
    } catch (e) {
      console.error('Error saving agent:', e);
    }
  };

  if (loading) {
    return <LoadingState message="Loading AI Employees & Industry Blueprints..." />;
  }

  return (
    <div className="space-y-8 animate-fade-in">
      <audio ref={audioRef} className="hidden" />

      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              AI Employees
            </h1>
            <Badge variant="indigo">Persona Engine</Badge>
          </div>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">
            Create, configure, test, and publish company-assigned voice agents with approved knowledge sources and tools.
          </p>
        </div>

        <Button
          variant="primary"
          size="sm"
          onClick={openCreateModal}
          leftIcon={<Plus className="w-4 h-4" />}
        >
          Create AI Employee
        </Button>
      </div>

      {/* Industry Templates Bar */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm">Start from an Industry Role Template</CardTitle>
            <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
              {blueprints.length} templates available
            </span>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-2.5">
            {blueprints.map((bp) => (
              <button
                key={bp.blueprint}
                onClick={() => handleApplyBlueprint(bp)}
                className="text-left bg-slate-50 dark:bg-slate-950 hover:bg-slate-100 dark:hover:bg-slate-800/80 p-3 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-indigo-500/50 transition-all text-xs"
              >
                <strong className="text-xs text-slate-900 dark:text-white block truncate mb-1">
                  {bp.title}
                </strong>
                <p className="text-[11px] text-slate-500 dark:text-slate-400 line-clamp-2">
                  {bp.description}
                </p>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Agents Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {agents.map((agent) => (
          <Card key={agent.id} className="flex flex-col justify-between hover:shadow-md transition-shadow">
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-indigo-50 dark:bg-indigo-600/15 border border-indigo-200 dark:border-indigo-500/30 flex items-center justify-center text-indigo-600 dark:text-indigo-400 font-bold text-sm">
                    {agent.name[0]}
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-slate-900 dark:text-white leading-tight">
                      {agent.name}
                    </h2>
                    <span className="text-xs text-indigo-600 dark:text-indigo-400 font-medium block">
                      {agent.company}
                    </span>
                  </div>
                </div>

                <Badge variant={agent.is_active ? 'success' : 'neutral'} size="sm">
                  {agent.is_active ? 'PUBLISHED' : 'PAUSED'}
                </Badge>
              </div>
            </CardHeader>

            <CardContent className="space-y-3.5">
              <p className="text-xs text-slate-600 dark:text-slate-300 line-clamp-2">
                {agent.purpose}
              </p>

              {/* Structured Configuration Specs */}
              <div className="space-y-2 text-xs bg-slate-50 dark:bg-slate-950/60 p-3.5 rounded-xl border border-slate-200 dark:border-slate-800">
                <div className="flex items-center justify-between">
                  <span className="text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
                    <Volume2 className="w-3.5 h-3.5 text-indigo-500" /> Voice & Style
                  </span>
                  <span className="text-slate-800 dark:text-slate-200 font-mono text-[11px] truncate max-w-[130px]">
                    {agent.voice_id}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
                    <Languages className="w-3.5 h-3.5 text-emerald-500" /> Languages
                  </span>
                  <span className="text-slate-800 dark:text-slate-200 font-mono text-[11px] uppercase">
                    {agent.supported_languages?.join(', ') || agent.default_language}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
                    <BookOpen className="w-3.5 h-3.5 text-indigo-500" /> Knowledge Base
                  </span>
                  <span className="text-emerald-600 dark:text-emerald-400 font-medium text-[11px]">
                    {approvedDocCount} Approved RAG Docs
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
                    <PhoneForwarded className="w-3.5 h-3.5 text-slate-400" /> Escalation
                  </span>
                  <span className="text-slate-800 dark:text-slate-300 font-mono text-[11px]">
                    {agent.transfer_number}
                  </span>
                </div>
              </div>

              {/* Greeting Preview */}
              <div className="p-2.5 bg-slate-50/70 dark:bg-slate-950/40 rounded-lg border border-slate-200/80 dark:border-slate-800/60 text-[11px] text-slate-500 dark:text-slate-400 italic line-clamp-2">
                "{agent.greeting}"
              </div>
            </CardContent>

            <CardFooter className="pt-3 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between gap-2 text-xs">
              <div className="flex items-center gap-1.5">
                <Button
                  variant="outline"
                  size="xs"
                  onClick={() => handlePlaySample(agent)}
                  leftIcon={<Play className="w-3 h-3 text-indigo-500 fill-indigo-500" />}
                >
                  {playingAgentId === agent.id ? 'Playing...' : 'Voice'}
                </Button>
                {onNavigate && (
                  <Button
                    variant="subtle"
                    size="xs"
                    onClick={() => onNavigate('simulator')}
                    leftIcon={<PhoneCall className="w-3 h-3 text-indigo-500" />}
                  >
                    Test Call
                  </Button>
                )}
              </div>

              <div className="flex items-center gap-1.5">
                <Button
                  variant="ghost"
                  size="xs"
                  onClick={() => openEditModal(agent)}
                  title="Edit Agent Configuration"
                >
                  <Edit3 className="w-3.5 h-3.5" />
                </Button>
                <Button
                  variant={agent.is_active ? 'outline' : 'primary'}
                  size="xs"
                  onClick={() => handleToggleActive(agent)}
                >
                  {agent.is_active ? (
                    <>
                      <Pause className="w-3 h-3 mr-1" /> Pause
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-3 h-3 mr-1" /> Publish
                    </>
                  )}
                </Button>
              </div>
            </CardFooter>
          </Card>
        ))}
      </div>

      {/* Create / Edit Agent Dialog */}
      <Dialog
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title={editingAgentId ? 'Edit AI Employee Configuration' : 'Create AI Employee'}
        description="Configure voice persona, language capabilities, and approved corporate instructions."
        maxWidth="xl"
      >
        <form onSubmit={handleSave} className="space-y-4 text-xs">
          {/* 1. Name, Role & Company Assignment */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input
              label="Agent Name"
              required
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
            />
            <Input
              label="Assigned Company / Tenant"
              required
              value={formCompany}
              onChange={(e) => setFormCompany(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input
              label="Role & Call Objective"
              required
              value={formPurpose}
              onChange={(e) => setFormPurpose(e.target.value)}
            />
            <Input
              label="Communication Style & Tone"
              value={formPersonality}
              onChange={(e) => setFormPersonality(e.target.value)}
            />
          </div>

          {/* 2. Voice & Supported Languages */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Select
              label="Primary Language"
              value={formLang}
              onChange={(e) => {
                setFormLang(e.target.value);
                if (e.target.value === 'hi') setFormVoice('hi-IN-MadhurNeural');
                else if (e.target.value === 'en') setFormVoice('en-IN-NeerjaNeural');
                else if (e.target.value === 'te') setFormVoice('te-IN-ShrutiNeural');
                else if (e.target.value === 'ta') setFormVoice('ta-IN-PallaviNeural');
              }}
              options={[
                { value: 'hi', label: 'Hindi / Hinglish' },
                { value: 'en', label: 'English (India)' },
                { value: 'te', label: 'Telugu' },
                { value: 'ta', label: 'Tamil' },
                { value: 'kn', label: 'Kannada' },
                { value: 'ml', label: 'Malayalam' },
              ]}
            />

            <Select
              label="Neural Voice Persona"
              value={formVoice}
              onChange={(e) => setFormVoice(e.target.value)}
              options={[
                { value: 'hi-IN-SwaraNeural', label: 'hi-IN-SwaraNeural (F)' },
                { value: 'hi-IN-MadhurNeural', label: 'hi-IN-MadhurNeural (M)' },
                { value: 'en-IN-NeerjaNeural', label: 'en-IN-NeerjaNeural (F)' },
                { value: 'en-IN-PrabhatNeural', label: 'en-IN-PrabhatNeural (M)' },
                { value: 'te-IN-ShrutiNeural', label: 'te-IN-ShrutiNeural (F)' },
                { value: 'te-IN-MohanNeural', label: 'te-IN-MohanNeural (M)' },
                { value: 'ta-IN-PallaviNeural', label: 'ta-IN-PallaviNeural (F)' },
              ]}
            />

            <Select
              label="Speaking Pace"
              value={formSpeed.toString()}
              onChange={(e) => setFormSpeed(parseFloat(e.target.value))}
              options={[
                { value: '0.96', label: '0.96x (Calm)' },
                { value: '1.04', label: '1.04x (Natural)' },
                { value: '1.10', label: '1.10x (Brisk)' },
              ]}
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-1.5">
              Supported Conversation Languages
            </label>
            <div className="flex flex-wrap gap-2">
              {[
                { code: 'hi', label: 'Hindi (HI)' },
                { code: 'en', label: 'English (EN)' },
                { code: 'te', label: 'Telugu (TE)' },
                { code: 'ta', label: 'Tamil (TA)' },
                { code: 'kn', label: 'Kannada (KN)' },
                { code: 'ml', label: 'Malayalam (ML)' },
              ].map((lang) => (
                <button
                  type="button"
                  key={lang.code}
                  onClick={() => toggleSupportedLang(lang.code)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                    formSupportedLangs.includes(lang.code)
                      ? 'bg-indigo-50 dark:bg-indigo-600/20 border-indigo-400 dark:border-indigo-500 text-indigo-700 dark:text-indigo-300'
                      : 'bg-white dark:bg-slate-950 border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400'
                  }`}
                >
                  {lang.label}
                </button>
              ))}
            </div>
          </div>

          {/* 3. Greeting & System Instructions */}
          <Textarea
            label="Opening Spoken Greeting"
            rows={2}
            value={formGreeting}
            onChange={(e) => setFormGreeting(e.target.value)}
          />

          <Textarea
            label="Agent Instructions & Guardrails"
            rows={3}
            value={formPrompt}
            onChange={(e) => setFormPrompt(e.target.value)}
          />

          {/* 4. Approved Tools & Escalation */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input
              label="Human Escalation Phone Number"
              value={formTransfer}
              onChange={(e) => setFormTransfer(e.target.value)}
            />
            <Input
              label="Mid-Call WhatsApp Follow-Up Template"
              value={formWhatsApp}
              onChange={(e) => setFormWhatsApp(e.target.value)}
            />
          </div>

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
              {editingAgentId ? 'Save Changes' : 'Create & Publish Agent'}
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
};
