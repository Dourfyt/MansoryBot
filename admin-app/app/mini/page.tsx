'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ExternalLink, Headphones, Loader2, LogIn, Send, RefreshCw } from 'lucide-react';
import { getInitDataFromLocationHash } from '@/lib/telegram-init-data';

type Msg = { id: number; direction: string; body: string | null; created_at: string | null };

type WelcomeLink = { label: string; url: string };

declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        ready: () => void;
        expand: () => void;
        initData: string;
      };
    };
  }
}

function loadTelegramScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.Telegram?.WebApp) {
      resolve();
      return;
    }
    const s = document.createElement('script');
    s.src = 'https://telegram.org/js/telegram-web-app.js';
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error('script'));
    document.head.appendChild(s);
  });
}

export default function MiniSupportPage() {
  const [phase, setPhase] = useState<'loading' | 'no_tg' | 'auth' | 'chat' | 'error'>('loading');
  const [err, setErr] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [ticketStatus, setTicketStatus] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [welcomeMessage, setWelcomeMessage] = useState('');
  const [welcomeLinks, setWelcomeLinks] = useState<WelcomeLink[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/telegram/support/welcome')
      .then((r) => r.json())
      .then((data: { welcome_message?: string; welcome_links?: unknown }) => {
        if (cancelled) return;
        setWelcomeMessage(typeof data.welcome_message === 'string' ? data.welcome_message : '');
        const raw = data.welcome_links;
        setWelcomeLinks(
          Array.isArray(raw)
            ? raw
                .filter(
                  (x): x is WelcomeLink =>
                    Boolean(x) &&
                    typeof x === 'object' &&
                    typeof (x as WelcomeLink).url === 'string' &&
                    (x as WelcomeLink).url.trim().length > 0
                )
                .map((x) => ({
                  label: typeof x.label === 'string' && x.label.trim() ? x.label.trim() : 'Ссылка',
                  url: x.url.trim(),
                }))
            : []
        );
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const loadTicket = useCallback(async () => {
    const r = await fetch('/api/telegram/support/ticket', { credentials: 'include' });
    if (!r.ok) {
      if (r.status === 401) throw new Error('session');
      const j = await r.json().catch(() => ({}));
      throw new Error(typeof j.error === 'string' ? j.error : 'load');
    }
    const data = await r.json();
    setMessages(data.messages ?? []);
    setTicketStatus(data.ticket?.status ?? null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let poll: ReturnType<typeof setInterval> | undefined;

    (async () => {
      try {
        await loadTelegramScript();
      } catch {
        /* скрипт может не загрузиться вне TG — initData всё ещё может быть в #tgWebAppData */
      }

      const tg = window.Telegram?.WebApp;
      if (tg) {
        tg.ready();
        tg.expand();
      }

      const initData =
        (tg?.initData || '').trim() || getInitDataFromLocationHash() || '';
      if (!initData) {
        if (!cancelled) setPhase('no_tg');
        return;
      }

      if (!cancelled) setPhase('auth');

      const ar = await fetch('/api/telegram/support/auth', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ initData }),
      });
      const aj = await ar.json().catch(() => ({}));
      if (!ar.ok) {
        if (!cancelled) {
          setPhase('error');
          setErr(typeof aj.error === 'string' ? aj.error : 'Ошибка авторизации');
        }
        return;
      }

      await loadTicket();
      if (!cancelled) {
        if (window.location.hash && window.history.replaceState) {
          window.history.replaceState(null, '', window.location.pathname + window.location.search);
        }
        setPhase('chat');
        poll = setInterval(() => {
          loadTicket().catch(() => {});
        }, 8000);
      }
    })();

    return () => {
      cancelled = true;
      if (poll) clearInterval(poll);
    };
  }, [loadTicket]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleRefreshChat = async () => {
    if (phase !== 'chat') return;
    setRefreshing(true);
    setErr(null);
    try {
      await loadTicket();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Не удалось обновить');
    } finally {
      setRefreshing(false);
    }
  };

  const send = async () => {
    const t = input.trim();
    if (!t || sending) return;
    setSending(true);
    setErr(null);
    try {
      const r = await fetch('/api/telegram/support/ticket', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: t }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) {
        setErr(typeof j.error === 'string' ? j.error : 'Не удалось отправить');
        return;
      }
      setInput('');
      await loadTicket();
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 flex flex-col">
      <header className="flex items-center justify-between gap-3 px-4 py-3 border-b border-gray-800 bg-gray-950/80 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <Headphones className="h-5 w-5 text-blue-400 shrink-0" />
          <span className="text-white font-medium truncate">Поддержка</span>
          {ticketStatus === 'closed' && (
            <span className="text-xs text-amber-400 shrink-0">(закрыт — новое сообщение откроет)</span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {phase === 'chat' && (
            <button
              type="button"
              onClick={() => void handleRefreshChat()}
              disabled={refreshing}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-sm text-gray-200 bg-gray-800 hover:bg-gray-700 disabled:opacity-60"
              aria-label="Обновить"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
              Обновить
            </button>
          )}
          <Link
            href="/login?staff=1"
            className="inline-flex items-center gap-1.5 text-sm text-blue-400 hover:text-blue-300"
          >
            <LogIn className="h-4 w-4" />
            Войти
          </Link>
        </div>
      </header>

      {phase === 'loading' || phase === 'auth' ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 text-gray-400">
          <Loader2 className="h-10 w-10 animate-spin" />
          <p className="text-sm">{phase === 'auth' ? 'Подключение…' : 'Загрузка…'}</p>
        </div>
      ) : null}

      {phase === 'no_tg' ? (
        <div className="flex-1 flex flex-col items-center justify-center p-6 text-center max-w-md mx-auto">
          <p className="text-gray-300 mb-4">
            Чат поддержки доступен при открытии сайта из Telegram (Mini App). В браузере можно войти в CRM.
          </p>
          <Link
            href="/login"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm"
          >
            <LogIn className="h-4 w-4" />
            Вход в CRM
          </Link>
        </div>
      ) : null}

      {phase === 'error' ? (
        <div className="flex-1 flex flex-col items-center justify-center p-6">
          <p className="text-red-400 text-center mb-4">{err || 'Ошибка'}</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="text-blue-400 text-sm hover:underline"
          >
            Обновить страницу
          </button>
        </div>
      ) : null}

      {phase === 'chat' ? (
        <>
          <div className="flex-1 overflow-y-auto px-3 py-4 space-y-3">
            {(welcomeMessage.trim() || welcomeLinks.length > 0) && (
              <div className="rounded-xl border border-gray-700/80 bg-gray-800/60 p-3 space-y-3">
                {welcomeMessage.trim() ? (
                  <p className="text-sm text-gray-100 whitespace-pre-wrap break-words">{welcomeMessage.trim()}</p>
                ) : null}
                {welcomeLinks.length > 0 ? (
                  <div className="flex flex-col gap-2">
                    {welcomeLinks.map((link, i) => (
                      <a
                        key={`${link.url}-${i}`}
                        href={link.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600/90 hover:bg-blue-600 text-white text-sm font-medium px-3 py-2.5 transition-colors"
                      >
                        {link.label}
                        <ExternalLink className="h-4 w-4 shrink-0 opacity-90" />
                      </a>
                    ))}
                  </div>
                ) : null}
              </div>
            )}
            {messages.length === 0 && (
              <p className="text-center text-gray-500 text-sm">Напишите сообщение — ответит оператор.</p>
            )}
            {messages.map((m) => {
              const mine = m.direction === 'in';
              return (
                <div key={m.id} className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
                      mine ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-100'
                    }`}
                  >
                    <p className="whitespace-pre-wrap break-words">{m.body || ''}</p>
                    {m.created_at && (
                      <p className={`text-[10px] mt-1 opacity-70 ${mine ? 'text-blue-100' : 'text-gray-500'}`}>
                        {new Date(m.created_at).toLocaleString()}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
            <div ref={bottomRef} />
          </div>

          {err && (
            <div className="px-3 py-2 text-sm text-red-400 bg-red-950/40 border-t border-red-900/50">{err}</div>
          )}

          <div className="p-3 border-t border-gray-800 bg-gray-950/80 flex gap-2 shrink-0 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), send())}
              placeholder="Сообщение…"
              className="flex-1 min-w-0 px-3 py-2 rounded-xl bg-gray-800 border border-gray-700 text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              type="button"
              disabled={sending || !input.trim()}
              onClick={send}
              className="shrink-0 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white"
            >
              {sending ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
            </button>
          </div>
        </>
      ) : null}
    </div>
  );
}
