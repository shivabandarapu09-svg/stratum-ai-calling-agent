import React, { useState } from 'react';
import { Layers, Lock, Mail } from 'lucide-react';
import { login, AuthSession } from '../api';
import { Button, Input } from '../components/ui';

interface LoginProps {
  onLoggedIn: (session: AuthSession) => void;
  sessionExpired?: boolean;
}

export const Login: React.FC<LoginProps> = ({ onLoggedIn, sessionExpired = false }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);
    try {
      const session = await login(email.trim(), password);
      onLoggedIn(session);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm p-8 space-y-5"
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-600 flex items-center justify-center text-white shadow-md shadow-indigo-500/20">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <h1 className="font-bold text-base tracking-tight text-slate-900 dark:text-white">STRATUM AI</h1>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">Sign in to your workspace</p>
          </div>
        </div>

        {sessionExpired && !error && (
          <div role="status" className="text-xs rounded-lg bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-900 px-3 py-2">
            Your session has expired. Please sign in again.
          </div>
        )}
        {error && (
          <div role="alert" className="text-xs rounded-lg bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-900 px-3 py-2">
            {error}
          </div>
        )}

        <Input
          label="Email"
          type="email"
          autoComplete="username"
          required
          autoFocus
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          leftIcon={<Mail className="w-4 h-4" />}
        />
        <Input
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          leftIcon={<Lock className="w-4 h-4" />}
        />

        <Button type="submit" size="lg" className="w-full" isLoading={isLoading} disabled={!email || !password}>
          Sign in
        </Button>
      </form>
    </div>
  );
};
