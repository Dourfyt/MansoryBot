'use client';

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import {
  Trash2,
  Search,
  Users,
  Plus,
  RefreshCw,
  Settings2,
} from 'lucide-react';
import { AnonymousRoomSettingsModal } from '@/components/AnonymousRoomSettingsModal';

export interface AnonChat {
  id: number;
  title: string;
  created_at: string;
  is_active: boolean;
  member_count: number;
  child_bot_username: string | null;
  verifier_group_id: number | null;
}

interface AnonymousChatsPanelProps {
  /** Если false — не грузим список (вкладка скрыта). */
  enabled: boolean;
}

export function AnonymousChatsPanel({ enabled }: AnonymousChatsPanelProps) {
  const [err, setErr] = useState<string | null>(null);
  const [anonChats, setAnonChats] = useState<AnonChat[]>([]);
  const [anonLoading, setAnonLoading] = useState(false);
  const [newChatTitle, setNewChatTitle] = useState('');
  const [creatingChat, setCreatingChat] = useState(false);
  const [inviteMinting, setInviteMinting] = useState(false);
  const [modalInviteText, setModalInviteText] = useState<string | null>(null);
  const [anonSearch, setAnonSearch] = useState('');
  const [debouncedAnonSearch, setDebouncedAnonSearch] = useState('');
  const [settingsRoom, setSettingsRoom] = useState<AnonChat | null>(null);
  const [deletingAnonId, setDeletingAnonId] = useState<number | null>(null);
  const [botTokenDraft, setBotTokenDraft] = useState('');
  const [savingBotToken, setSavingBotToken] = useState(false);
  const [listRefreshing, setListRefreshing] = useState(false);
  const [verifierGroupDraft, setVerifierGroupDraft] = useState('');
  const [savingVerifier, setSavingVerifier] = useState(false);

  const anonRoomSearchInputId = useId();
  const settingsRoomRef = useRef<AnonChat | null>(null);
  useLayoutEffect(() => {
    settingsRoomRef.current = settingsRoom;
  }, [settingsRoom]);

  useEffect(() => {
    if (!settingsRoom) {
      setVerifierGroupDraft('');
      return;
    }
    setVerifierGroupDraft(
      settingsRoom.verifier_group_id != null ? String(settingsRoom.verifier_group_id) : ''
    );
  }, [settingsRoom?.id, settingsRoom?.verifier_group_id]);

  const loadAnonymous = async (searchQ?: string) => {
    setAnonLoading(true);
    setErr(null);
    try {
      const q = (searchQ ?? '').trim();
      const url = q
        ? `/api/support/anonymous-chats?q=${encodeURIComponent(q)}`
        : '/api/support/anonymous-chats';
      const res = await fetch(url);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Ошибка загрузки');
      let list = (data.chats || []) as AnonChat[];
      const sel = settingsRoomRef.current;
      if (sel && !list.some((c) => c.id === sel.id)) {
        list = [sel, ...list];
      }
      setAnonChats(list);
      setSettingsRoom((prev) => {
        if (!prev) return null;
        const row = list.find((c) => c.id === prev.id);
        return row ?? prev;
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setAnonLoading(false);
    }
  };

  useEffect(() => {
    const t = setTimeout(() => setDebouncedAnonSearch(anonSearch), 350);
    return () => clearTimeout(t);
  }, [anonSearch]);

  useEffect(() => {
    if (!enabled) return;
    loadAnonymous(debouncedAnonSearch);
  }, [enabled, debouncedAnonSearch]);

  useEffect(() => {
    setBotTokenDraft('');
  }, [settingsRoom?.id]);

  const openSettingsModal = (c: AnonChat) => {
    setSettingsRoom(c);
    setVerifierGroupDraft(c.verifier_group_id != null ? String(c.verifier_group_id) : '');
    setBotTokenDraft('');
    setModalInviteText(null);
  };

  const closeSettingsModal = useCallback(() => {
    setSettingsRoom(null);
    setModalInviteText(null);
  }, []);

  const createAnonymousChat = async () => {
    setCreatingChat(true);
    setErr(null);
    try {
      const res = await fetch('/api/support/anonymous-chats', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newChatTitle.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Не удалось создать');
      setNewChatTitle('');
      await loadAnonymous(debouncedAnonSearch);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setCreatingChat(false);
    }
  };

  const deleteAnonChat = async (chatId: number) => {
    if (
      !window.confirm(
        'Удалить этот анонимный чат? Участники потеряют доступ, история и инвайты будут удалены безвозвратно.'
      )
    ) {
      return;
    }
    setDeletingAnonId(chatId);
    setErr(null);
    try {
      const res = await fetch(`/api/support/anonymous-chats/${chatId}`, { method: 'DELETE' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Не удалось удалить');
      if (settingsRoom?.id === chatId) {
        closeSettingsModal();
      }
      await loadAnonymous(debouncedAnonSearch);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setDeletingAnonId(null);
    }
  };

  const saveVerifierGroup = async () => {
    if (!settingsRoom) return;
    setSavingVerifier(true);
    setErr(null);
    try {
      const trimmed = verifierGroupDraft.trim();
      let body: { verifier_group_id: number | null };
      if (trimmed === '') {
        body = { verifier_group_id: null };
      } else {
        const n = parseInt(trimmed, 10);
        if (!Number.isFinite(n) || n === 0) {
          throw new Error('Укажите ID группы Telegram (ненулевое число, для супергруппы — отрицательное)');
        }
        body = { verifier_group_id: n };
      }
      const res = await fetch(`/api/support/anonymous-chats/${settingsRoom.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Не сохранено');
      const v = body.verifier_group_id;
      setSettingsRoom((prev) => (prev ? { ...prev, verifier_group_id: v ?? null } : null));
      setAnonChats((prev) =>
        prev.map((c) => (c.id === settingsRoom.id ? { ...c, verifier_group_id: v ?? null } : c))
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setSavingVerifier(false);
    }
  };

  const saveChildBotToken = async () => {
    if (!settingsRoom || !botTokenDraft.trim()) return;
    setSavingBotToken(true);
    setErr(null);
    try {
      const res = await fetch(`/api/support/anonymous-chats/${settingsRoom.id}/bot-token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: botTokenDraft.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Не удалось сохранить');
      setBotTokenDraft('');
      await loadAnonymous(debouncedAnonSearch);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setSavingBotToken(false);
    }
  };

  const mintInviteInModal = async () => {
    if (!settingsRoom) return;
    setInviteMinting(true);
    setErr(null);
    try {
      const res = await fetch(`/api/support/anonymous-chats/${settingsRoom.id}/invite`, {
        method: 'POST',
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Не удалось создать ссылку');
      setModalInviteText(data.invite_text as string);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setInviteMinting(false);
    }
  };

  const copyModalInvite = async () => {
    if (!modalInviteText) return;
    try {
      await navigator.clipboard.writeText(modalInviteText);
    } catch {
      setErr('Не удалось скопировать в буфер');
    }
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

  const handleRefreshAll = async () => {
    setListRefreshing(true);
    setErr(null);
    try {
      await loadAnonymous(debouncedAnonSearch);
    } finally {
      setListRefreshing(false);
    }
  };

  if (!enabled) {
    return null;
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => void handleRefreshAll()}
          disabled={listRefreshing}
          className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-gray-800/80 border border-border rounded-lg hover:bg-white/10 disabled:opacity-60 text-sm text-gray-200"
          aria-label="Обновить список анонимных чатов"
        >
          <RefreshCw className={`h-4 w-4 shrink-0 ${listRefreshing ? 'animate-spin' : ''}`} />
          Обновить список
        </button>
      </div>

      {err && (
        <div className="p-3 bg-red-900/30 border border-red-800 rounded text-red-200 text-sm">{err}</div>
      )}

      <div className="bg-gray-800/80 rounded-lg p-4 border border-gray-700/80">
        <h2 className="text-sm font-semibold text-gray-300 mb-2">Как устроена комната</h2>
        <p className="text-xs text-gray-400 leading-relaxed mb-3">
          Каждая комната может работать через <span className="text-gray-200">отдельного</span> Telegram-бота:
          создайте бота в @BotFather (<code className="text-gray-300">/newbot</code>),
          придумайте имя и username (должен оканчиваться на <code className="text-gray-300">bot</code>),
          скопируйте токен и укажите его в окне настроек комнаты (кнопка по строке в списке). Ссылки-приглашения будут
          вести на этого бота, а не на основного.
        </p>
        <p className="text-xs text-gray-400 leading-relaxed mb-3">
          Укажите <span className="text-gray-200">ID группы проверяющих</span> (тот же, что в связках групп в CRM):
          тогда участник анонимного чата сможет отправить фото с командой <code className="text-gray-300">/п</code> в
          личку основному боту — фото уйдёт в эту группу с кнопками подтверждения, как из группы клиентов.
        </p>
        <p className="text-xs text-gray-500 leading-relaxed">
          Команды в боте: <code className="text-gray-400">/delete</code>,{' '}
          <code className="text-gray-400">/delete_all</code>, <code className="text-gray-400">/delete_all 120</code>{' '}
          (минуты).
        </p>
      </div>

      <div className="bg-gray-800 rounded-lg p-4 border border-border/80">
        <h2 className="text-sm font-semibold text-gray-400 mb-3">Новый анонимный чат</h2>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            type="text"
            name="anon-new-room-title"
            value={newChatTitle}
            onChange={(e) => setNewChatTitle(e.target.value)}
            placeholder="Название (необязательно)"
            autoComplete="off"
            autoCorrect="off"
            spellCheck={false}
            className="flex-1 px-3 py-2 rounded-lg bg-gray-900 border border-gray-600 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="button"
            disabled={creatingChat}
            onClick={createAnonymousChat}
            className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg text-sm font-medium"
          >
            <Plus className="h-4 w-4" />
            {creatingChat ? 'Создание…' : 'Создать'}
          </button>
        </div>
      </div>

      <div className="bg-gray-800 rounded-lg p-4 flex flex-col min-h-0 max-h-[75vh] border border-border/80">
        <div className="mb-3 space-y-2 shrink-0">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-gray-400 flex items-center gap-2">
              <Users className="h-4 w-4" />
              Комнаты
            </h2>
            {anonSearch.trim() ? (
              <span className="text-xs text-gray-500">
                {anonChats.length} {anonLoading ? '' : 'найдено'}
              </span>
            ) : null}
          </div>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500 pointer-events-none" />
            <input
              id={anonRoomSearchInputId}
              type="text"
              name={`anon-room-list-query-${anonRoomSearchInputId}`}
              value={anonSearch}
              onChange={(e) => setAnonSearch(e.target.value)}
              placeholder="Поиск: № комнаты, название…"
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
              data-1p-ignore
              data-lpignore="true"
              data-form-type="other"
              className="w-full pl-9 pr-3 py-2 rounded-lg bg-gray-900 border border-gray-600 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>
        {anonLoading ? (
          <p className="text-gray-400 text-sm">Загрузка…</p>
        ) : (
          <ul className="space-y-2 overflow-y-auto flex-1 min-h-0">
            {anonChats.map((c) => (
              <li key={c.id}>
                <div
                  className={`rounded-lg border p-3 transition ${
                    settingsRoom?.id === c.id
                      ? 'border-blue-500 bg-gray-700/80'
                      : 'border-gray-700 bg-gray-900/40 hover:border-gray-600'
                  }`}
                >
                  <button
                    type="button"
                    onMouseDown={(e) => {
                      if (e.button !== 0) return;
                      e.preventDefault();
                    }}
                    onClick={() => openSettingsModal(c)}
                    className="w-full text-left"
                  >
                    <div className="text-sm font-medium text-gray-100 flex items-center gap-2 flex-wrap">
                      <span>
                        #{c.id} · {c.title || 'Без названия'}
                      </span>
                      <Settings2 className="h-3.5 w-3.5 text-gray-500 shrink-0" aria-hidden />
                    </div>
                    <div className="text-xs text-gray-500 mt-0.5">
                      участников: {c.member_count} · {formatTime(c.created_at)}
                      {c.child_bot_username ? (
                        <span className="ml-2 text-emerald-400/90">@{c.child_bot_username}</span>
                      ) : (
                        <span className="ml-2 text-gray-600">мастер-бот</span>
                      )}
                      {typeof c.verifier_group_id === 'number' && (
                        <span className="ml-2 text-sky-400/90">проверяющие: {c.verifier_group_id}</span>
                      )}
                      {!c.is_active && <span className="ml-2 text-amber-500/90">неактивен</span>}
                    </div>
                    <p className="text-[11px] text-gray-600 mt-1.5">Нажмите, чтобы открыть настройки и ссылку</p>
                  </button>
                  <div className="flex flex-wrap gap-2 mt-2 pt-2 border-t border-gray-700/80 justify-end">
                    <button
                      type="button"
                      disabled={deletingAnonId === c.id}
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteAnonChat(c.id);
                      }}
                      className="inline-flex items-center justify-center gap-1.5 px-2.5 py-1.5 bg-red-900/40 hover:bg-red-900/60 border border-red-800/50 disabled:opacity-40 rounded text-xs text-red-100 shrink-0"
                    >
                      <Trash2 className="h-3 w-3" />
                      {deletingAnonId === c.id ? '…' : 'Удалить'}
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
        {!anonLoading && anonChats.length === 0 && (
          <p className="text-gray-500 text-sm mt-2">Нет комнат по запросу или список пуст.</p>
        )}
      </div>

      <AnonymousRoomSettingsModal
        isOpen={settingsRoom !== null}
        room={settingsRoom}
        onClose={closeSettingsModal}
        verifierGroupDraft={verifierGroupDraft}
        onVerifierGroupDraftChange={setVerifierGroupDraft}
        onSaveVerifier={() => void saveVerifierGroup()}
        savingVerifier={savingVerifier}
        botTokenDraft={botTokenDraft}
        onBotTokenDraftChange={setBotTokenDraft}
        onSaveBotToken={() => void saveChildBotToken()}
        savingBotToken={savingBotToken}
        inviteText={modalInviteText}
        onMintInvite={() => void mintInviteInModal()}
        mintingInvite={inviteMinting}
        onCopyInvite={() => void copyModalInvite()}
        formatTime={formatTime}
      />
    </div>
  );
}
