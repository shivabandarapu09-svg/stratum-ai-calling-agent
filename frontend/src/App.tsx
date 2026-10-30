import React, { useState, useEffect } from 'react';
import {
  LayoutDashboard, PhoneCall, History, Bot, BookOpen,
  Send, BarChart3, Settings as SettingsIcon, Zap, Layers, ShieldCheck,
  Building2, Users, Cpu, ChevronLeft, ChevronRight, Menu, X
} from 'lucide-react';
import { Dashboard } from './pages/Dashboard';
import { LiveCallSimulator } from './pages/LiveCallSimulator';
import { SpeedToLead } from './pages/SpeedToLead';
import { CallLogs } from './pages/CallLogs';
import { Agents } from './pages/Agents';
import { KnowledgeBase } from './pages/KnowledgeBase';
import { Campaigns } from './pages/Campaigns';
import { Analytics } from './pages/Analytics';
import { Settings } from './pages/Settings';
import { Companies } from './pages/Companies';
import { Integrations } from './pages/Integrations';
import { ContactsLeads } from './pages/ContactsLeads';
import { fetchHealth } from './api';
import { ThemeToggle } from './components/ui/ThemeToggle';
import { Badge } from './components/ui/Badge';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<string>('simulator');
  const [isHealthy, setIsHealthy] = useState<boolean>(true);
  const [isCollapsed, setIsCollapsed] = useState<boolean>(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState<boolean>(false);

  useEffect(() => {
    fetchHealth()
      .then((h) => setIsHealthy(h.status === 'healthy'))
      .catch(() => setIsHealthy(false));
  }, []);

  const navGroups = [
    {
      title: 'Workspace',
      items: [
        { id: 'dashboard', label: 'Overview', icon: LayoutDashboard },
        { id: 'simulator', label: 'Live Voice Studio', icon: PhoneCall },
        { id: 'agents', label: 'AI Employees', icon: Bot },
        { id: 'campaigns', label: 'Campaigns & Dialer', icon: Send },
        { id: 'contacts', label: 'Contacts & Leads', icon: Users },
        { id: 'calls', label: 'Conversations & Logs', icon: History },
      ],
    },
    {
      title: 'Intelligence',
      items: [
        { id: 'knowledge', label: 'Knowledge Hub (RAG)', icon: BookOpen },
        { id: 'speed_to_lead', label: 'Speed-to-Lead Engine', icon: Zap },
        { id: 'analytics', label: 'Latency & Economics', icon: BarChart3 },
      ],
    },
    {
      title: 'Administration',
      items: [
        { id: 'companies', label: 'Company Workspaces', icon: Building2 },
        { id: 'integrations', label: 'Carriers & Integrations', icon: Cpu },
        { id: 'settings', label: 'System Settings', icon: SettingsIcon },
      ],
    },
  ];

  const allItems = navGroups.flatMap((g) => g.items);
  const currentItem = allItems.find((i) => i.id === activeTab) || allItems[0];

  const handleNavigate = (tab: string) => {
    setActiveTab(tab);
    setIsMobileMenuOpen(false);
  };

  return (
    <div className="flex h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 font-sans overflow-hidden transition-colors duration-200">
      {/* Mobile Backdrop */}
      {isMobileMenuOpen && (
        <div
          className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-40 lg:hidden"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}

      {/* Enterprise Sidebar */}
      <aside
        className={`
          fixed lg:static inset-y-0 left-0 z-50 flex flex-col justify-between flex-shrink-0
          bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800/80 shadow-sm transition-all duration-300 ease-in-out
          ${isCollapsed ? 'w-20' : 'w-64'}
          ${isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        `}
      >
        <div className="flex-1 flex flex-col min-h-0 overflow-y-auto">
          {/* Brand Header */}
          <div className="h-16 px-4 flex items-center justify-between border-b border-slate-100 dark:border-slate-800/80 flex-shrink-0">
            <div className="flex items-center gap-3 overflow-hidden">
              <div className="w-9 h-9 rounded-xl bg-indigo-600 flex items-center justify-center text-white shadow-md shadow-indigo-500/20 flex-shrink-0">
                <Layers className="w-5 h-5" />
              </div>
              {!isCollapsed && (
                <div className="truncate">
                  <span className="font-bold text-sm tracking-tight text-slate-900 dark:text-white block">
                    STRATUM AI
                  </span>
                  <span className="text-[11px] font-medium text-slate-400 dark:text-slate-500 block truncate">
                    Enterprise Voice Platform
                  </span>
                </div>
              )}
            </div>

            {/* Mobile close button */}
            <button
              type="button"
              onClick={() => setIsMobileMenuOpen(false)}
              className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Grouped Navigation */}
          <div className="p-3 space-y-6 flex-1">
            {navGroups.map((group) => (
              <div key={group.title}>
                {!isCollapsed && (
                  <span className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 block mb-2">
                    {group.title}
                  </span>
                )}
                <nav className="space-y-1">
                  {group.items.map((item) => {
                    const Icon = item.icon;
                    const isActive = activeTab === item.id;
                    return (
                      <button
                        key={item.id}
                        onClick={() => handleNavigate(item.id)}
                        title={isCollapsed ? item.label : undefined}
                        className={`
                          w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-semibold transition-all
                          ${
                            isActive
                              ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-600/30'
                              : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 hover:bg-slate-100/80 dark:hover:bg-slate-800/60'
                          }
                          ${isCollapsed ? 'justify-center px-0' : ''}
                        `}
                      >
                        <Icon className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-white' : 'text-slate-400 dark:text-slate-500'}`} />
                        {!isCollapsed && (
                          <span className="flex-1 text-left truncate">{item.label}</span>
                        )}
                      </button>
                    );
                  })}
                </nav>
              </div>
            ))}
          </div>
        </div>

        {/* Footer Area: System Status & Collapse Toggle */}
        <div className="p-3 border-t border-slate-100 dark:border-slate-800/80 bg-slate-50/50 dark:bg-slate-950/40 text-xs">
          {!isCollapsed ? (
            <div className="space-y-2 mb-2">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-slate-700 dark:text-slate-300 font-medium text-[11px]">
                  <span className={`w-2 h-2 rounded-full ${isHealthy ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`} />
                  {isHealthy ? 'Carrier Pipeline Ready' : 'Backend Unreachable'}
                </span>
                <Badge variant={isHealthy ? 'success' : 'danger'} size="sm">
                  {isHealthy ? 'Live' : 'Down'}
                </Badge>
              </div>
              <div className="flex items-center gap-1.5 text-[10px] text-slate-500 dark:text-slate-400">
                <ShieldCheck className="w-3.5 h-3.5 text-indigo-500" />
                <span className="truncate">Tenant-Isolated RAG • E.164</span>
              </div>
            </div>
          ) : (
            <div className="flex justify-center mb-2">
              <span className={`w-2.5 h-2.5 rounded-full ${isHealthy ? 'bg-emerald-500' : 'bg-rose-500'}`} title={isHealthy ? 'Pipeline Ready' : 'Offline'} />
            </div>
          )}

          {/* Collapse sidebar toggle button (desktop) */}
          <button
            type="button"
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="hidden lg:flex w-full items-center justify-center p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {isCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col h-screen overflow-hidden bg-slate-50 dark:bg-slate-950 transition-colors duration-200">
        {/* Clean Enterprise Top Bar */}
        <header className="h-16 border-b border-slate-200 dark:border-slate-800/80 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md px-4 sm:px-8 flex items-center justify-between flex-shrink-0 z-10">
          <div className="flex items-center gap-3">
            {/* Mobile menu trigger */}
            <button
              type="button"
              onClick={() => setIsMobileMenuOpen(true)}
              className="lg:hidden p-2 rounded-lg text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
            >
              <Menu className="w-5 h-5" />
            </button>

            <div>
              <div className="flex items-center gap-2.5">
                <h2 className="text-base font-bold text-slate-900 dark:text-white tracking-tight">
                  {currentItem.label}
                </h2>
              </div>
              <p className="hidden sm:block text-[11px] font-medium text-slate-500 dark:text-slate-400 truncate max-w-md">
                Enterprise AI voice pipelines, carrier SIP gateways, and multi-tenant isolation.
              </p>
            </div>
          </div>

          {/* Quick Actions & Theme Control */}
          <div className="flex items-center gap-3 text-xs">
            {/* Direct Quick Launch Buttons */}
            <button
              onClick={() => handleNavigate('integrations')}
              className="hidden md:flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800/80 font-medium transition-colors shadow-xs"
            >
              <Cpu className="w-3.5 h-3.5 text-indigo-500" />
              <span>Carriers</span>
            </button>

            <button
              onClick={() => handleNavigate('simulator')}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition-all shadow-sm shadow-indigo-600/30"
            >
              <PhoneCall className="w-3.5 h-3.5" />
              <span>Voice Studio</span>
            </button>

            {/* Dual Theme Switcher (Stripe/Linear style) */}
            <div className="pl-1 border-l border-slate-200 dark:border-slate-800">
              <ThemeToggle variant="icon" />
            </div>
          </div>
        </header>

        {/* Scrollable View Content */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
          <div className="max-w-7xl mx-auto pb-12">
            {activeTab === 'dashboard' && <Dashboard onNavigate={handleNavigate} />}
            {activeTab === 'simulator' && <LiveCallSimulator onNavigate={handleNavigate} />}
            {activeTab === 'agents' && <Agents onNavigate={handleNavigate} />}
            {activeTab === 'campaigns' && <Campaigns />}
            {activeTab === 'contacts' && <ContactsLeads onInitiateCall={(name, phone) => {
              setActiveTab('simulator');
            }} />}
            {activeTab === 'calls' && <CallLogs />}
            {activeTab === 'knowledge' && <KnowledgeBase />}
            {activeTab === 'speed_to_lead' && <SpeedToLead />}
            {activeTab === 'analytics' && <Analytics />}
            {activeTab === 'companies' && <Companies />}
            {activeTab === 'integrations' && <Integrations />}
            {activeTab === 'settings' && <Settings />}
          </div>
        </div>
      </main>
    </div>
  );
};
