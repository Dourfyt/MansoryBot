'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Lock, Eye, EyeOff, AlertCircle, Mail, ArrowLeft } from 'lucide-react';
import { hasTelegramWebContext } from '@/lib/telegram-init-data';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [totp, setTotp] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsTotp, setNeedsTotp] = useState(false);
  const [showBackToMini, setShowBackToMini] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const staff = new URLSearchParams(window.location.search).get('staff');
    if (staff === '1') {
      setShowBackToMini(true);
      return;
    }
    if (hasTelegramWebContext()) {
      router.replace('/mini' + (window.location.hash || ''));
    }
  }, [router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const body: Record<string, string> = { email, password };
      if (totp.trim()) body.totp = totp.trim();

      const response = await fetch('/api/auth/password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      const result = await response.json();

      if (response.ok && result.success) {
        router.push('/');
        return;
      }

      if (result.requiresTotp) {
        setNeedsTotp(true);
        setError('Введите код из приложения аутентификатора');
      } else {
        setError(result.error || 'Ошибка авторизации');
      }
    } catch {
      setError('Ошибка подключения к серверу');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="bg-gray-800 rounded-lg shadow-xl p-8">
          {showBackToMini && (
            <Link
              href="/mini"
              className="inline-flex items-center gap-2 text-sm text-gray-400 hover:text-white mb-6 transition-colors"
            >
              <ArrowLeft className="h-4 w-4 shrink-0" />
              Назад к чату
            </Link>
          )}
          <div className="text-center mb-8">
            <div className="mx-auto w-16 h-16 bg-blue-600 rounded-full flex items-center justify-center mb-4">
              <Lock className="h-8 w-8 text-white" />
            </div>
            <h1 className="text-2xl font-bold text-white mb-2">CRM</h1>
            <p className="text-gray-400">Вход по email и паролю</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-300 mb-2">
                Email
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-500" />
                <input
                  id="email"
                  type="email"
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full pl-10 pr-4 py-3 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="admin@example.com"
                  required
                />
              </div>
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-300 mb-2">
                Пароль
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Пароль"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-300"
                >
                  {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                </button>
              </div>
            </div>

            {(needsTotp || totp) && (
              <div>
                <label htmlFor="totp" className="block text-sm font-medium text-gray-300 mb-2">
                  Код 2FA
                </label>
                <input
                  id="totp"
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  value={totp}
                  onChange={(e) => setTotp(e.target.value)}
                  className="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-lg text-white"
                  placeholder="000000"
                  autoComplete="one-time-code"
                />
              </div>
            )}

            {error && (
              <div className="flex items-center space-x-2 text-red-400 bg-red-900/20 border border-red-800 rounded-lg px-4 py-3">
                <AlertCircle className="h-5 w-5 flex-shrink-0" />
                <span className="text-sm">{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white font-medium py-3 px-4 rounded-lg transition-colors duration-200 flex items-center justify-center"
            >
              {loading ? (
                <>
                  <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white mr-2"></div>
                  Вход...
                </>
              ) : (
                'Войти'
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
