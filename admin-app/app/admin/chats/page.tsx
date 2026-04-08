'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import NextLink from 'next/link';
import {
  ArrowLeft,
  LogOut,
  Trash2,
  RefreshCw,
  AlertTriangle,
  Search,
  ShieldAlert,
  Link2,
  Copy,
  Loader2,
} from 'lucide-react';

interface AdminChatRow {
  chat_id: number;
  name: string | null;
  in_group_settings: boolean;
  as_client_in_connection: boolean;
  as_verifier_in_connection: boolean;
  invite_link: string | null;
}

interface InaccessibleRow {
  chat_id: number;
  name: string | null;
}

/** Одна партия на запрос — укладывается в proxy_read_timeout nginx (~60 с). Не слать 1000 в одном POST. */
const CHUNK_CHECK_CHATS = 45;
const CHUNK_INVITE_LINKS = 8;

export default function AdminChatsPage() {
  const router = useRouter();
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [chats, setChats] = useState<AdminChatRow[]>([]);
  const [inaccessible, setInaccessible] = useState<InaccessibleRow[]>([]);
  const [tab, setTab] = useState<'all' | 'inaccessible'>('all');
  const [loading, setLoading] = useState(true);
  const [loadingInacc, setLoadingInacc] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [checking, setChecking] = useState(false);
  const [inviting, setInviting] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [regeneratingId, setRegeneratingId] = useState<number | null>(null);
  /** Текст вида «Партия 3/23…» при длинных циклах (сотни/тысячи групп). */
  const [batchProgress, setBatchProgress] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/api/auth/session');
        if (!res.ok) {
          router.push('/login');
          return;
        }
        const data = await res.json();
        if (data.role !== 'admin') {
          router.replace('/');
          return;
        }
        setAllowed(true);
      } catch {
        router.push('/login');
      }
    })();
  }, [router]);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [res, resInc] = await Promise.all([
        fetch('/api/admin/chats'),
        fetch('/api/admin/chats/inaccessible'),
      ]);
      const data = await res.json();
      const incData = await resInc.json();
      if (!res.ok) throw new Error(data.error || 'Ошибка загрузки');
      if (resInc.ok) {
        setInaccessible(incData.chats || []);
      }
      setChats(data.chats || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadInaccessible = useCallback(async () => {
    setLoadingInacc(true);
    setErr(null);
    try {
      const res = await fetch('/api/admin/chats/inaccessible');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Ошибка загрузки');
      setInaccessible(data.chats || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setLoadingInacc(false);
    }
  }, []);

  useEffect(() => {
    if (allowed) void load();
  }, [allowed, load]);

  useEffect(() => {
    if (allowed && tab === 'inaccessible') void loadInaccessible();
  }, [allowed, tab, loadInaccessible]);

  const filteredChats = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return chats;
    return chats.filter((c) => {
      const idStr = String(c.chat_id);
      const name = (c.name || '').toLowerCase();
      return idStr.includes(q) || name.includes(q);
    });
  }, [chats, search]);

  const filteredInaccessible = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return inaccessible;
    return inaccessible.filter((c) => {
      const idStr = String(c.chat_id);
      const name = (c.name || '').toLowerCase();
      return idStr.includes(q) || name.includes(q);
    });
  }, [inaccessible, search]);

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  };

  const selectAllCurrent = () => {
    const ids =
      tab === 'all' ? filteredChats.map((c) => c.chat_id) : filteredInaccessible.map((c) => c.chat_id);
    setSelected(new Set(ids));
  };

  const clearSelection = () => setSelected(new Set());

  const idsForBulkAction = useMemo(() => {
    if (selected.size > 0) return [...selected];
    if (tab === 'all') return filteredChats.map((c) => c.chat_id);
    return filteredInaccessible.map((c) => c.chat_id);
  }, [selected, tab, filteredChats, filteredInaccessible]);

  const removeChat = async (chatId: number) => {
    if (
      !confirm(
        `Удалить чат ${chatId} из базы?\n\nБудут удалены чеки и настройки этой группы, она исчезнет из рассылки (включая ежедневную). Связи «клиент ↔ проверяющие» с этой группой будут отключены. Действие необратимо.`
      )
    ) {
      return;
    }
    setDeletingId(chatId);
    setErr(null);
    try {
      const res = await fetch(`/api/admin/chats/${chatId}`, { method: 'DELETE' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Не удалено');
      clearSelection();
      await load();
      await loadInaccessible();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setDeletingId(null);
    }
  };

  const bulkDelete = async () => {
    const ids =
      selected.size > 0
        ? [...selected]
        : tab === 'all'
          ? filteredChats.map((c) => c.chat_id)
          : filteredInaccessible.map((c) => c.chat_id);
    if (ids.length === 0) {
      setErr('Нет чатов для удаления.');
      return;
    }
    if (
      !confirm(
        `Удалить ${ids.length} чат(ов) из базы? Действие необратимо (чеки, настройки, рассылка, связи).`
      )
    ) {
      return;
    }
    setBulkDeleting(true);
    setErr(null);
    try {
      const res = await fetch('/api/admin/chats/bulk-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_ids: ids }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Ошибка');
      clearSelection();
      await load();
      await loadInaccessible();
      if (data.errors?.length) {
        setErr(`Удалено: ${data.deleted}, ошибок: ${data.failed}`);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setBulkDeleting(false);
    }
  };

  const runCheck = async () => {
    const chat_ids = chats.map((c) => c.chat_id);
    if (chat_ids.length === 0) {
      setErr('Нет чатов для проверки.');
      return;
    }
    setChecking(true);
    setErr(null);
    setBatchProgress(null);
    const totalBatches = Math.ceil(chat_ids.length / CHUNK_CHECK_CHATS);
    try {
      let checked = 0;
      let accessible = 0;
      let inaccessible = 0;
      let names_updated = 0;
      let batchNum = 0;
      for (let i = 0; i < chat_ids.length; i += CHUNK_CHECK_CHATS) {
        batchNum += 1;
        const slice = chat_ids.slice(i, i + CHUNK_CHECK_CHATS);
        const to = Math.min(i + slice.length, chat_ids.length);
        setBatchProgress(
          `Проверка доступа: запрос ${batchNum}/${totalBatches} (чаты ${i + 1}–${to} из ${chat_ids.length})`
        );
        const res = await fetch('/api/admin/chats/check-availability', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ chat_ids: slice }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Ошибка проверки');
        checked += data.checked ?? slice.length;
        accessible += data.accessible ?? 0;
        inaccessible += data.inaccessible ?? 0;
        names_updated += data.names_updated ?? 0;
      }
      await load();
      alert(
        `Проверено: ${checked}. Доступно: ${accessible}, недоступно: ${inaccessible}. Названий обновлено: ${names_updated}.`
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setBatchProgress(null);
      setChecking(false);
    }
  };

  const createInviteLinks = async (chat_ids: number[]) => {
    if (chat_ids.length === 0) {
      setErr('Выберите чаты или отфильтруйте список.');
      return;
    }
    setInviting(true);
    setErr(null);
    setBatchProgress(null);
    const totalBatches = Math.ceil(chat_ids.length / CHUNK_INVITE_LINKS);
    try {
      const allFailed: { error?: string }[] = [];
      let batchNum = 0;
      for (let i = 0; i < chat_ids.length; i += CHUNK_INVITE_LINKS) {
        batchNum += 1;
        const slice = chat_ids.slice(i, i + CHUNK_INVITE_LINKS);
        const to = Math.min(i + slice.length, chat_ids.length);
        setBatchProgress(
          `Ссылки-приглашения: запрос ${batchNum}/${totalBatches} (чаты ${i + 1}–${to} из ${chat_ids.length})`
        );
        const res = await fetch('/api/admin/chats/invite-links', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ chat_ids: slice }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Ошибка');
        const failed = (data.results || []).filter((r: { error?: string }) => r.error);
        allFailed.push(...failed);
      }
      if (allFailed.length) {
        setErr(
          `Создано с ошибками: ${allFailed.length}. Пример: ${allFailed[0].error || '—'}`
        );
      }
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setBatchProgress(null);
      setInviting(false);
    }
  };

  const regenerateOne = async (chatId: number) => {
    setRegeneratingId(chatId);
    setErr(null);
    try {
      const res = await fetch('/api/admin/chats/invite-links', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_ids: [chatId] }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Ошибка');
      const r = data.results?.[0] as
        | {
            chat_id: number;
            invite_link: string | null;
            error?: string | null;
            migrated_from?: number | null;
          }
        | undefined;
      if (r?.error) throw new Error(r.error);
      const newId = r?.chat_id ?? chatId;
      const link = r?.invite_link ?? null;
      setChats((prev) =>
        prev.map((c) => {
          if (c.chat_id !== chatId) return c;
          if (newId !== chatId) {
            return { ...c, chat_id: newId, invite_link: link };
          }
          return { ...c, invite_link: link };
        })
      );
      if (newId !== chatId) {
        setSelected((prev) => {
          if (!prev.has(chatId)) return prev;
          const n = new Set(prev);
          n.delete(chatId);
          n.add(newId);
          return n;
        });
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setRegeneratingId(null);
    }
  };

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      setErr('Не удалось скопировать в буфер.');
    }
  };

  const logout = async () => {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.push('/login');
  };

  if (allowed === null) {
    return (
      <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center">
        <p className="text-gray-400">Загрузка…</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white p-4">
      <div className="max-w-6xl mx-auto">
        <header className="flex flex-row items-center justify-between gap-3 mb-6 min-h-[3rem]">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <NextLink
              href="/"
              className="inline-flex items-center justify-center gap-2 px-3 py-2 bg-gray-800 rounded-lg hover:bg-gray-700 shrink-0"
            >
              <ArrowLeft className="h-4 w-4" />
              В панель
            </NextLink>
            <Trash2 className="h-8 w-8 text-rose-400 shrink-0" aria-hidden />
            <h1 className="text-2xl font-bold truncate min-w-0">Чаты и рассылка</h1>
          </div>
          <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
            <button
              type="button"
              onClick={() => void load()}
              disabled={loading}
              className="inline-flex items-center gap-2 px-4 py-2 bg-gray-800 rounded-lg hover:bg-gray-700 disabled:opacity-60 text-sm"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              Обновить
            </button>
            <button
              type="button"
              onClick={logout}
              className="inline-flex items-center gap-2 px-4 py-2 bg-gray-800 rounded-lg hover:bg-gray-700 text-sm"
            >
              <LogOut className="h-4 w-4" />
              Выход
            </button>
          </div>
        </header>

        <div className="rounded-lg border border-amber-900/50 bg-amber-950/20 p-4 mb-6 flex gap-3">
          <AlertTriangle className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
          <p className="text-sm text-amber-100/90 leading-relaxed">
            Только для главного администратора. Удаление убирает группу из списка рассылки и стирает связанные
            данные в CRM. Проверка доступа обращается к Telegram с сервера бота. Ссылки-приглашения создаёт бот
            (он должен быть администратором группы с правом приглашать участников). При сотнях и тысячах групп
            запросы идут партиями (несколько HTTP на всё действие), чтобы не упираться в таймаут прокси.
          </p>
        </div>

        {err && (
          <div className="mb-4 p-3 bg-red-900/30 border border-red-800 rounded text-red-200 text-sm">{err}</div>
        )}

        {batchProgress && (
          <div className="mb-4 p-3 bg-blue-950/40 border border-blue-800/50 rounded text-blue-100/95 text-sm flex items-start gap-2">
            <Loader2 className="h-4 w-4 animate-spin shrink-0 mt-0.5" aria-hidden />
            <span>{batchProgress}</span>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2 mb-4">
          <div className="relative flex-1 min-w-[200px] max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
            <input
              type="search"
              placeholder="Поиск по ID или названию…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white placeholder:text-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <button
            type="button"
            onClick={() => {
              setTab('all');
              clearSelection();
            }}
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm ${
              tab === 'all' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
            }`}
          >
            Все чаты
            <span className="bg-black/25 px-1.5 rounded text-xs tabular-nums">{chats.length}</span>
          </button>
          <button
            type="button"
            onClick={() => {
              setTab('inaccessible');
              clearSelection();
            }}
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm ${
              tab === 'inaccessible'
                ? 'bg-amber-700 text-white'
                : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
            }`}
          >
            <ShieldAlert className="h-4 w-4" />
            Недоступные
            <span className="bg-black/30 px-1.5 rounded text-xs tabular-nums">{inaccessible.length}</span>
          </button>
        </div>

        <div className="flex flex-wrap gap-2 mb-4">
          <button
            type="button"
            disabled={checking || loading}
            onClick={() => void runCheck()}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-800/80 hover:bg-emerald-700 text-sm disabled:opacity-50"
          >
            {checking ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Проверить доступность
          </button>
          <button
            type="button"
            disabled={inviting || loading || idsForBulkAction.length === 0}
            onClick={() => void createInviteLinks(idsForBulkAction)}
            title={
              selected.size > 0
                ? 'Создать ссылки для выбранных'
                : 'Создать ссылки для всех чатов в текущей вкладке (с учётом фильтра)'
            }
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-800/80 hover:bg-indigo-700 text-sm disabled:opacity-50"
          >
            {inviting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Link2 className="h-4 w-4" />}
            Ссылки-приглашения
          </button>
          <button
            type="button"
            onClick={selectAllCurrent}
            className="px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-sm"
          >
            Выделить все{tab === 'all' ? '' : ' (вкладка)'}
          </button>
          <button type="button" onClick={clearSelection} className="px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-sm">
            Снять выделение
          </button>
          <button
            type="button"
            disabled={
              bulkDeleting || (tab === 'all' ? filteredChats : filteredInaccessible).length === 0
            }
            onClick={() => void bulkDelete()}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-red-900/50 hover:bg-red-900/70 border border-red-800/50 text-sm disabled:opacity-50"
          >
            {bulkDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
            Удалить выбранные
          </button>
        </div>

        {loading && tab === 'all' ? (
          <p className="text-gray-400">Загрузка списка…</p>
        ) : tab === 'all' ? (
          <div className="rounded-xl border border-gray-700 overflow-hidden overflow-x-auto">
            <table className="w-full text-sm min-w-[720px]">
              <thead className="bg-gray-800/80 text-gray-400 text-left">
                <tr>
                  <th className="px-2 py-3 w-10"></th>
                  <th className="px-4 py-3 font-medium">ID чата</th>
                  <th className="px-4 py-3 font-medium">Название</th>
                  <th className="px-4 py-3 font-medium">Учёт</th>
                  <th className="px-4 py-3 font-medium">Приглашение</th>
                  <th className="px-4 py-3 font-medium w-40"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700/80">
                {filteredChats.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                      {chats.length === 0
                        ? 'Нет групп в базе.'
                        : 'Ничего не найдено по поиску.'}
                    </td>
                  </tr>
                ) : (
                  filteredChats.map((c) => (
                    <tr key={c.chat_id} className="bg-gray-900/40 hover:bg-gray-800/50">
                      <td className="px-2 py-3">
                        <input
                          type="checkbox"
                          checked={selected.has(c.chat_id)}
                          onChange={() => toggleSelect(c.chat_id)}
                          className="rounded border-gray-600"
                        />
                      </td>
                      <td className="px-4 py-3 font-mono text-gray-200">{c.chat_id}</td>
                      <td className="px-4 py-3 text-gray-300">{c.name || '—'}</td>
                      <td className="px-4 py-3 text-xs text-gray-400 space-y-1">
                        {c.in_group_settings && <div>Настройки группы</div>}
                        {c.as_client_in_connection && <div>Связка: клиенты</div>}
                        {c.as_verifier_in_connection && <div>Связка: проверяющие</div>}
                        {!c.in_group_settings && !c.as_client_in_connection && !c.as_verifier_in_connection && (
                          <span className="text-gray-600">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs">
                        {c.invite_link ? (
                          <span className="text-emerald-300/90 break-all line-clamp-2">{c.invite_link}</span>
                        ) : (
                          <span className="text-gray-600">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1.5">
                          {c.invite_link && (
                            <button
                              type="button"
                              onClick={() => void copyText(c.invite_link!)}
                              className="inline-flex items-center gap-1 px-2 py-1 rounded bg-gray-800 text-xs hover:bg-gray-700"
                            >
                              <Copy className="h-3 w-3" />
                              Копировать
                            </button>
                          )}
                          <button
                            type="button"
                            disabled={regeneratingId === c.chat_id}
                            onClick={() => void regenerateOne(c.chat_id)}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded bg-indigo-900/50 text-xs hover:bg-indigo-800/60 disabled:opacity-50"
                          >
                            {regeneratingId === c.chat_id ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              <RefreshCw className="h-3 w-3" />
                            )}
                            Пересоздать
                          </button>
                          <button
                            type="button"
                            disabled={deletingId === c.chat_id}
                            onClick={() => void removeChat(c.chat_id)}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded bg-red-900/40 text-xs text-red-100 hover:bg-red-900/60 disabled:opacity-50"
                          >
                            <Trash2 className="h-3 w-3" />
                            Удалить
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        ) : loadingInacc ? (
          <p className="text-gray-400">Загрузка недоступных…</p>
        ) : (
          <div className="rounded-xl border border-amber-900/40 overflow-hidden overflow-x-auto">
            <table className="w-full text-sm min-w-[560px]">
              <thead className="bg-amber-950/40 text-amber-200/90 text-left">
                <tr>
                  <th className="px-2 py-3 w-10"></th>
                  <th className="px-4 py-3 font-medium">ID чата</th>
                  <th className="px-4 py-3 font-medium">Название (кэш)</th>
                  <th className="px-4 py-3 font-medium w-36"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700/80">
                {filteredInaccessible.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-gray-500">
                      {inaccessible.length === 0
                        ? 'Нет недоступных чатов. Нажмите «Проверить доступность» на вкладке «Все чаты».'
                        : 'Ничего не найдено по поиску.'}
                    </td>
                  </tr>
                ) : (
                  filteredInaccessible.map((c) => (
                    <tr key={c.chat_id} className="bg-gray-900/40 hover:bg-gray-800/50">
                      <td className="px-2 py-3">
                        <input
                          type="checkbox"
                          checked={selected.has(c.chat_id)}
                          onChange={() => toggleSelect(c.chat_id)}
                          className="rounded border-gray-600"
                        />
                      </td>
                      <td className="px-4 py-3 font-mono text-gray-200">{c.chat_id}</td>
                      <td className="px-4 py-3 text-gray-300">{c.name || '—'}</td>
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          disabled={deletingId === c.chat_id}
                          onClick={() => void removeChat(c.chat_id)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-900/40 hover:bg-red-900/60 text-red-100 text-xs disabled:opacity-50"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          Удалить из базы
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}

        <p className="mt-4 text-xs text-gray-500">
          Выделение пустое → «Ссылки-приглашения» и «Удалить выбранные» действуют на все строки текущей вкладки
          с учётом поиска.
        </p>
      </div>
    </div>
  );
}
