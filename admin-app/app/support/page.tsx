'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  MessageCircle,
  Send,
  LogOut,
  Lock,
  ArrowLeft,
  Trash2,
  Search,
  RefreshCw,
} from 'lucide-react';

interface Ticket {
  id: number;
  telegram_user_id: number;
  telegram_username: string | null;
  status: string;
  last_message_at: string | null;
  last_body: string | null;
  unread_count: number;
}

function sortTicketsByUnreadThenTime(list: Ticket[]): Ticket[] {
  return list.slice().sort((a, b) => {
    const ua = a.unread_count ?? 0;
    const ub = b.unread_count ?? 0;
    if (ub !== ua) return ub - ua;
    const ta = a.last_message_at ? new Date(a.last_message_at).getTime() : 0;
    const tb = b.last_message_at ? new Date(b.last_message_at).getTime() : 0;
    return tb - ta;
  });
}

function ticketMatchesSearch(t: Ticket, rawQuery: string): boolean {
  const q = rawQuery.trim().toLowerCase();
  if (!q) return true;
  const idStr = String(t.id);
  const tid = String(t.telegram_user_id);
  const un = (t.telegram_username || '').toLowerCase();
  const body = (t.last_body || '').toLowerCase();
  const qNoHash = q.startsWith('#') ? q.slice(1).trim() : q;
  const qUser = q.replace(/^@/, '');
  return (
    idStr.includes(qNoHash) ||
    tid.includes(q) ||
    un.includes(qUser) ||
    body.includes(q)
  );
}

interface MsgRow {
  id: number;
  direction: string;
  body: string | null;
  created_at: string | null;
}

export default function SupportInboxPage() {
  const router = useRouter();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Ticket | null>(null);
  const [messages, setMessages] = useState<MsgRow[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [reply, setReply] = useState('');
  const [sending, setSending] = useState(false);
  const [closing, setClosing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ticketSearch, setTicketSearch] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const filteredTickets = useMemo(() => {
    return tickets.filter((t) => ticketMatchesSearch(t, ticketSearch));
  }, [tickets, ticketSearch]);

  const load = async (opts?: { silent?: boolean }) => {
    const silent = opts?.silent ?? false;
    if (!silent) setLoading(true);
    setErr(null);
    try {
      const res = await fetch('/api/support/tickets');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Ошибка загрузки');
      const raw = (data.tickets || []) as Ticket[];
      const normalized = raw.map((t) => ({
        ...t,
        unread_count: typeof t.unread_count === 'number' ? t.unread_count : 0,
      }));
      setTickets(sortTicketsByUnreadThenTime(normalized));
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    setErr(null);
    try {
      await load({ silent: true });
      if (selected) await loadDetail(selected.id);
    } finally {
      setRefreshing(false);
    }
  };

  const loadDetail = async (ticketId: number) => {
    setDetailLoading(true);
    setErr(null);
    try {
      const res = await fetch(`/api/support/tickets/${ticketId}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Ошибка загрузки тикета');
      setMessages(data.messages || []);
      if (data.ticket) {
        setSelected((prev) => {
          if (!prev || prev.id !== ticketId) return prev;
          return {
            ...prev,
            status: data.ticket.status,
            last_message_at: data.ticket.last_message_at,
            telegram_username: data.ticket.telegram_username ?? prev.telegram_username,
            unread_count: 0,
          };
        });
      }
      setTickets((prev) =>
        sortTicketsByUnreadThenTime(
          prev.map((t) => (t.id === ticketId ? { ...t, unread_count: 0 } : t))
        )
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setDetailLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const id = setInterval(() => {
      fetch('/api/support/tickets')
        .then((res) => {
          if (!res.ok) return null;
          return res.json();
        })
        .then((data) => {
          if (!data?.tickets) return;
          const raw = data.tickets as Ticket[];
          const normalized = raw.map((t) => ({
            ...t,
            unread_count: typeof t.unread_count === 'number' ? t.unread_count : 0,
          }));
          setTickets(sortTicketsByUnreadThenTime(normalized));
        })
        .catch(() => {});
    }, 30000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!selected) {
      setMessages([]);
      return;
    }
    loadDetail(selected.id);
  }, [selected?.id]);

  const sendReply = async () => {
    if (!selected || !reply.trim()) return;
    setSending(true);
    setErr(null);
    try {
      const res = await fetch('/api/support/tickets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticket_id: selected.id, text: reply.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Не удалось отправить');
      setReply('');
      await load();
      await loadDetail(selected.id);
      setSelected((t) =>
        t ? { ...t, status: 'open', last_message_at: new Date().toISOString() } : t
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setSending(false);
    }
  };

  const closeTicket = async () => {
    if (!selected) return;
    setClosing(true);
    setErr(null);
    try {
      const res = await fetch(`/api/support/tickets/${selected.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'close' }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Не удалось закрыть');
      setSelected((t) => (t ? { ...t, status: 'closed' } : t));
      await load();
      await loadDetail(selected.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setClosing(false);
    }
  };

  const deleteTicket = async () => {
    if (!selected) return;
    if (
      !window.confirm(
        `Удалить тикет #${selected.id} и всю переписку? Действие необратимо.`
      )
    ) {
      return;
    }
    setDeleting(true);
    setErr(null);
    const id = selected.id;
    try {
      const res = await fetch(`/api/support/tickets/${id}`, { method: 'DELETE' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Не удалось удалить');
      setSelected(null);
      setMessages([]);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setDeleting(false);
    }
  };

  const logout = async () => {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.push('/login');
  };

  const formatTime = (s: string | null) => {
    if (!s) return '';
    try {
      const d = new Date(s);
      return d.toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' });
    } catch {
      return s;
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white p-4">
      <div className="max-w-6xl mx-auto">
        <header className="flex items-center justify-between mb-6 gap-3 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <MessageCircle className="h-8 w-8 text-blue-400" />
            <h1 className="text-2xl font-bold">Поддержка</h1>
            {tickets.some((t) => (t.unread_count ?? 0) > 0) && (
              <span className="text-sm font-medium text-emerald-400/90">
                ·{' '}
                {tickets.reduce((s, t) => s + (t.unread_count ?? 0), 0)} нов.
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void handleRefresh()}
              disabled={refreshing}
              className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-gray-800 rounded-lg hover:bg-gray-700 disabled:opacity-60 text-sm whitespace-nowrap"
              aria-label="Обновить"
            >
              <RefreshCw className={`h-4 w-4 shrink-0 ${refreshing ? 'animate-spin' : ''}`} />
              Обновить
            </button>
            <button
              type="button"
              onClick={() => router.push('/')}
              className="flex items-center gap-2 px-4 py-2 bg-gray-800 rounded-lg hover:bg-gray-700"
            >
              <ArrowLeft className="h-4 w-4" />
              В панель
            </button>
            <button
              type="button"
              onClick={logout}
              className="flex items-center gap-2 px-4 py-2 bg-gray-800 rounded-lg hover:bg-gray-700"
            >
              <LogOut className="h-4 w-4" />
              Выход
            </button>
          </div>
        </header>

        {err && (
          <div className="mb-4 p-3 bg-red-900/30 border border-red-800 rounded text-red-200 text-sm">{err}</div>
        )}

        {loading ? (
          <p className="text-gray-400">Загрузка…</p>
        ) : (
          <div className="grid md:grid-cols-2 gap-4 md:items-start">
            <div className="bg-gray-800 rounded-lg p-4 max-h-[75vh] overflow-y-auto flex flex-col min-h-0">
              <div className="mb-3 space-y-2 shrink-0">
                <div className="flex items-center justify-between gap-2">
                  <h2 className="text-sm font-semibold text-gray-400">Тикеты</h2>
                  {ticketSearch.trim() ? (
                    <span className="text-xs text-gray-500">
                      {filteredTickets.length} из {tickets.length}
                    </span>
                  ) : null}
                </div>
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500 pointer-events-none" />
                  <input
                    type="text"
                    name="support-ticket-query"
                    value={ticketSearch}
                    onChange={(e) => setTicketSearch(e.target.value)}
                    placeholder="Поиск: № тикета, Telegram ID, @username, текст…"
                    autoComplete="off"
                    autoCorrect="off"
                    spellCheck={false}
                    className="w-full pl-9 pr-3 py-2 rounded-lg bg-gray-900 border border-gray-600 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>
              <ul className="space-y-2 overflow-y-auto flex-1 min-h-0">
                {filteredTickets.map((t) => (
                  <li key={t.id}>
                    <button
                      type="button"
                      onClick={() => setSelected(t)}
                      className={`w-full text-left p-3 rounded-lg border transition ${
                        selected?.id === t.id
                          ? 'border-blue-500 bg-gray-700/80'
                          : (t.unread_count ?? 0) > 0
                            ? 'border-emerald-500/70 bg-emerald-950/25 hover:border-emerald-400/80'
                            : 'border-gray-700 hover:border-gray-600'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span
                          className={`text-sm font-medium ${
                            (t.unread_count ?? 0) > 0 ? 'text-white' : 'text-gray-200'
                          }`}
                        >
                          #{t.id} · {t.telegram_username || t.telegram_user_id}
                          {(t.unread_count ?? 0) > 0 && (
                            <span className="ml-2 inline-flex items-center justify-center min-w-[1.375rem] h-5 px-1.5 rounded-full bg-emerald-600 text-white text-xs font-bold tabular-nums">
                              {t.unread_count > 99 ? '99+' : t.unread_count}
                            </span>
                          )}
                        </span>
                        <span
                          className={`text-[10px] uppercase px-2 py-0.5 rounded shrink-0 ${
                            t.status === 'closed'
                              ? 'bg-gray-600 text-gray-300'
                              : 'bg-emerald-900/60 text-emerald-200'
                          }`}
                        >
                          {t.status === 'closed' ? 'закрыт' : 'открыт'}
                        </span>
                      </div>
                      <div className="text-xs text-gray-500 truncate mt-0.5">{t.last_body || '—'}</div>
                    </button>
                  </li>
                ))}
              </ul>
              {tickets.length === 0 && <p className="text-gray-500 text-sm">Нет обращений</p>}
              {tickets.length > 0 && filteredTickets.length === 0 && (
                <p className="text-gray-500 text-sm mt-2">Ничего не найдено — измените запрос</p>
              )}
            </div>

            <div className="bg-gray-800 rounded-lg p-4 flex flex-col min-h-[420px] max-h-[75vh]">
              <h2 className="text-sm font-semibold text-gray-400 mb-3">Переписка</h2>
              {selected ? (
                <>
                  <p className="text-xs text-gray-500 mb-2">
                    Telegram: {selected.telegram_user_id}
                    {selected.telegram_username ? ` (@${selected.telegram_username})` : ''}
                    {selected.status === 'closed' && (
                      <span className="ml-2 text-amber-400/90">· тикет закрыт (ответ откроет снова)</span>
                    )}
                  </p>

                  <div className="flex-1 overflow-y-auto space-y-2 mb-3 min-h-[200px] max-h-[40vh] border border-gray-700 rounded-lg p-2 bg-gray-900/50">
                    {detailLoading ? (
                      <p className="text-gray-500 text-sm p-2">Загрузка истории…</p>
                    ) : messages.length === 0 ? (
                      <p className="text-gray-500 text-sm p-2">Нет сообщений</p>
                    ) : (
                      messages.map((m) => (
                        <div
                          key={m.id}
                          className={`rounded-lg px-3 py-2 text-sm max-w-[95%] ${
                            m.direction === 'in'
                              ? 'bg-gray-700 mr-auto text-gray-100'
                              : 'bg-blue-900/50 ml-auto text-blue-100 border border-blue-800/40'
                          }`}
                        >
                          <div className="text-[10px] opacity-70 mb-1">
                            {m.direction === 'in' ? 'Клиент' : 'Поддержка'} · {formatTime(m.created_at)}
                          </div>
                          <div className="whitespace-pre-wrap break-words">{m.body || '—'}</div>
                        </div>
                      ))
                    )}
                  </div>

                  <div className="flex flex-wrap gap-2 mb-2">
                    <button
                      type="button"
                      disabled={closing || selected.status === 'closed'}
                      onClick={closeTicket}
                      className="flex items-center gap-2 px-3 py-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-40 rounded-lg text-sm"
                    >
                      <Lock className="h-4 w-4" />
                      {closing ? '…' : 'Закрыть тикет'}
                    </button>
                    <button
                      type="button"
                      disabled={deleting}
                      onClick={deleteTicket}
                      className="flex items-center gap-2 px-3 py-2 bg-red-900/50 hover:bg-red-900/70 border border-red-800/60 disabled:opacity-40 rounded-lg text-sm text-red-100"
                    >
                      <Trash2 className="h-4 w-4" />
                      {deleting ? '…' : 'Удалить тикет'}
                    </button>
                  </div>

                  <textarea
                    value={reply}
                    onChange={(e) => setReply(e.target.value)}
                    className="w-full min-h-[100px] bg-gray-700 border border-gray-600 rounded-lg p-3 text-sm mb-3"
                    placeholder="Ответ клиенту в Telegram (в чат уйдёт с пометкой «Сообщение от поддержки»)…"
                  />
                  <button
                    type="button"
                    disabled={sending || !reply.trim()}
                    onClick={sendReply}
                    className="flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 py-3 rounded-lg font-medium w-full"
                  >
                    <Send className="h-4 w-4" />
                    {sending ? 'Отправка…' : 'Отправить в Telegram'}
                  </button>
                </>
              ) : (
                <p className="text-gray-500 text-sm">Выберите тикет слева</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
