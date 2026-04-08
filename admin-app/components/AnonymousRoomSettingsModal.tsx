'use client';

import { useCallback, useEffect, useState } from 'react';
import { X, Copy, Link2, Loader2, UserCog, Trash2 } from 'lucide-react';

export interface AnonymousRoomModalChat {
  id: number;
  title: string;
  created_at: string;
  is_active: boolean;
  member_count: number;
  child_bot_username: string | null;
  verifier_group_id: number | null;
}

interface AnonymousRoomSettingsModalProps {
  isOpen: boolean;
  room: AnonymousRoomModalChat | null;
  onClose: () => void;
  verifierGroupDraft: string;
  onVerifierGroupDraftChange: (value: string) => void;
  onSaveVerifier: () => void;
  savingVerifier: boolean;
  botTokenDraft: string;
  onBotTokenDraftChange: (value: string) => void;
  onSaveBotToken: () => void;
  savingBotToken: boolean;
  inviteText: string | null;
  onMintInvite: () => void;
  mintingInvite: boolean;
  onCopyInvite: () => void;
  formatTime: (s: string | null) => string;
}

export function AnonymousRoomSettingsModal({
  isOpen,
  room,
  onClose,
  verifierGroupDraft,
  onVerifierGroupDraftChange,
  onSaveVerifier,
  savingVerifier,
  botTokenDraft,
  onBotTokenDraftChange,
  onSaveBotToken,
  savingBotToken,
  inviteText,
  onMintInvite,
  mintingInvite,
  onCopyInvite,
  formatTime,
}: AnonymousRoomSettingsModalProps) {
  const [supportLoading, setSupportLoading] = useState(false);
  const [supportErr, setSupportErr] = useState<string | null>(null);
  const [supportAssigned, setSupportAssigned] = useState<
    { crm_user_id: number; label: string; email: string; telegram_user_id: string | null }[]
  >([]);
  const [supportPool, setSupportPool] = useState<
    { id: number; email: string; telegram_user_id: string | null }[]
  >([]);
  const [addCrmId, setAddCrmId] = useState<string>('');
  const [addLabel, setAddLabel] = useState('A');
  const [supportSaving, setSupportSaving] = useState(false);

  const loadSupportAdmins = useCallback(async () => {
    if (!room) return;
    setSupportLoading(true);
    setSupportErr(null);
    try {
      const res = await fetch(`/api/support/anonymous-chats/${room.id}/support-admins`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Ошибка загрузки');
      setSupportAssigned(data.assigned || []);
      setSupportPool(data.support_users || []);
    } catch (e) {
      setSupportErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setSupportLoading(false);
    }
  }, [room]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (isOpen && room) void loadSupportAdmins();
  }, [isOpen, room, loadSupportAdmins]);

  const addSupportAdmin = async () => {
    if (!room) return;
    const crm = parseInt(addCrmId, 10);
    if (!Number.isFinite(crm)) {
      setSupportErr('Выберите саппорта');
      return;
    }
    setSupportSaving(true);
    setSupportErr(null);
    try {
      const res = await fetch(`/api/support/anonymous-chats/${room.id}/support-admins`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ crm_user_id: crm, label: addLabel }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Не сохранено');
      await loadSupportAdmins();
      setAddCrmId('');
    } catch (e) {
      setSupportErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setSupportSaving(false);
    }
  };

  const removeSupportAdmin = async (crmUserId: number) => {
    if (!room) return;
    if (!window.confirm('Снять этого саппорта с комнаты?')) return;
    setSupportSaving(true);
    setSupportErr(null);
    try {
      const res = await fetch(
        `/api/support/anonymous-chats/${room.id}/support-admins?crm_user_id=${crmUserId}`,
        { method: 'DELETE' }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Ошибка');
      await loadSupportAdmins();
    } catch (e) {
      setSupportErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setSupportSaving(false);
    }
  };

  const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');
  const availableSupport = supportPool.filter(
    (u) => u.telegram_user_id && !supportAssigned.some((a) => a.crm_user_id === u.id)
  );

  if (!isOpen || !room) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="anon-room-modal-title"
        className="bg-gray-800 border border-gray-600 rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] flex flex-col overflow-hidden"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 p-4 border-b border-gray-700 shrink-0">
          <div className="min-w-0">
            <h2 id="anon-room-modal-title" className="text-lg font-semibold text-white truncate">
              Настройки комнаты #{room.id}
            </h2>
            <p className="text-sm text-gray-400 mt-0.5 truncate">{room.title || 'Без названия'}</p>
            <p className="text-xs text-gray-500 mt-1">
              участников: {room.member_count} · {formatTime(room.created_at)}
              {!room.is_active && <span className="ml-2 text-amber-500/90">неактивна</span>}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg shrink-0"
            aria-label="Закрыть"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-4 overflow-y-auto flex-1 min-h-0 space-y-5">
          <section className="p-3 rounded-lg bg-gray-900/60 border border-gray-700 space-y-2">
            <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-wide">Ссылка-приглашение</h3>
            <p className="text-xs text-gray-400">
              Создайте ссылку для входа в эту комнату. Если подключён отдельный бот — ссылка ведёт на него.
            </p>
            <button
              type="button"
              disabled={!room.is_active || mintingInvite}
              onClick={onMintInvite}
              className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-emerald-800/80 hover:bg-emerald-700/90 disabled:opacity-40 rounded-lg text-sm text-emerald-50 w-full sm:w-auto"
            >
              {mintingInvite ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Создание…
                </>
              ) : (
                <>
                  <Link2 className="h-4 w-4" />
                  Получить ссылку
                </>
              )}
            </button>
            {inviteText && (
              <div className="rounded-lg border border-emerald-800/40 bg-emerald-950/25 p-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-emerald-300/90">Текст для отправки пользователю</span>
                  <button
                    type="button"
                    onClick={onCopyInvite}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-emerald-900/50 hover:bg-emerald-900/70 rounded-lg text-xs text-emerald-100"
                  >
                    <Copy className="h-3.5 w-3.5" />
                    Копировать
                  </button>
                </div>
                <pre className="text-xs text-gray-200 whitespace-pre-wrap break-all font-sans bg-gray-900/80 rounded p-2 border border-gray-700 max-h-40 overflow-y-auto">
                  {inviteText}
                </pre>
              </div>
            )}
          </section>

          <section className="p-3 rounded-lg bg-gray-900/60 border border-gray-700 space-y-2">
            <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-wide">
              Группа проверяющих для /п
            </h3>
            <p className="text-xs text-gray-400">
              ID группы Telegram (как в связках на главной). Пустое поле и «Сохранить» — отвязать.
            </p>
            <div className="flex flex-col sm:flex-row gap-2">
              <input
                type="text"
                inputMode="numeric"
                name="anon-verifier-group-id"
                value={verifierGroupDraft}
                onChange={(e) => onVerifierGroupDraftChange(e.target.value)}
                placeholder="Например -1001234567890"
                autoComplete="off"
                className="flex-1 px-3 py-2 rounded-lg bg-gray-900 border border-gray-600 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-sky-500 font-mono"
              />
              <button
                type="button"
                disabled={savingVerifier}
                onClick={onSaveVerifier}
                className="inline-flex items-center justify-center px-4 py-2 bg-sky-700 hover:bg-sky-600 disabled:opacity-40 rounded-lg text-sm font-medium shrink-0"
              >
                {savingVerifier ? 'Сохранение…' : 'Сохранить'}
              </button>
            </div>
          </section>

          <section className="p-3 rounded-lg bg-gray-900/60 border border-gray-700 space-y-2">
            <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-wide flex items-center gap-2">
              <UserCog className="h-3.5 w-3.5 text-violet-300" />
              Саппорты в чате
            </h3>
            <p className="text-xs text-gray-400">
              Назначьте саппортов из CRM: в личке с ботом у них будет имя «👁‍🗨 Саппорт A» и т.д., они могут
              удалять любые чеки в этой комнате, как админ бота. У саппорта в профиле CRM должен быть указан
              Telegram user id.
            </p>
            {supportErr && (
              <p className="text-xs text-red-300">{supportErr}</p>
            )}
            {supportLoading ? (
              <p className="text-xs text-gray-500">Загрузка…</p>
            ) : (
              <>
                {supportAssigned.length > 0 && (
                  <ul className="space-y-1.5">
                    {supportAssigned.map((a) => (
                      <li
                        key={a.crm_user_id}
                        className="flex items-center justify-between gap-2 text-xs bg-gray-900/80 rounded-lg px-2 py-1.5 border border-gray-700"
                      >
                        <span className="text-gray-200 truncate">
                          👁‍🗨 Саппорт {a.label} · {a.email}
                          {a.telegram_user_id ? (
                            <span className="text-gray-500 ml-1 font-mono">tg:{a.telegram_user_id}</span>
                          ) : null}
                        </span>
                        <button
                          type="button"
                          disabled={supportSaving}
                          onClick={() => void removeSupportAdmin(a.crm_user_id)}
                          className="p-1.5 text-red-400 hover:bg-red-900/40 rounded shrink-0"
                          aria-label="Снять"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="flex flex-col sm:flex-row gap-2 items-stretch sm:items-end">
                  <div className="flex-1 min-w-0">
                    <label className="text-[10px] text-gray-500 uppercase block mb-0.5">Саппорт</label>
                    <select
                      value={addCrmId}
                      onChange={(e) => setAddCrmId(e.target.value)}
                      className="w-full px-2 py-2 rounded-lg bg-gray-900 border border-gray-600 text-sm text-white"
                    >
                      <option value="">— выберите —</option>
                      {availableSupport.map((u) => (
                        <option key={u.id} value={u.id}>
                          {u.email}
                          {!u.telegram_user_id ? ' (нет Telegram id)' : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="w-full sm:w-20">
                    <label className="text-[10px] text-gray-500 uppercase block mb-0.5">Буква</label>
                    <select
                      value={addLabel}
                      onChange={(e) => setAddLabel(e.target.value)}
                      className="w-full px-2 py-2 rounded-lg bg-gray-900 border border-gray-600 text-sm text-white font-mono"
                    >
                      {letters.map((L) => (
                        <option key={L} value={L}>
                          {L}
                        </option>
                      ))}
                    </select>
                  </div>
                  <button
                    type="button"
                    disabled={supportSaving || !addCrmId}
                    onClick={() => void addSupportAdmin()}
                    className="px-4 py-2 bg-violet-800/80 hover:bg-violet-700/90 disabled:opacity-40 rounded-lg text-sm text-white shrink-0"
                  >
                    {supportSaving ? '…' : 'Назначить'}
                  </button>
                </div>
                {availableSupport.length === 0 && supportPool.length > 0 && (
                  <p className="text-[11px] text-amber-400/90">
                    Все саппорты с Telegram уже назначены или добавьте user id в CRM.
                  </p>
                )}
              </>
            )}
          </section>

          <section className="p-3 rounded-lg bg-gray-900/60 border border-gray-700 space-y-2">
            <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-wide">Отдельный бот</h3>
            <p className="text-xs text-gray-400">
              {room.child_bot_username ? (
                <>
                  Подключён <span className="text-emerald-300">@{room.child_bot_username}</span>. Инвайты ведут на него.
                </>
              ) : (
                <>Комната на мастер-боте. Вставьте токен от @BotFather, чтобы вынести в отдельного бота.</>
              )}
            </p>
            <div className="flex flex-col sm:flex-row gap-2">
              <input
                type="password"
                autoComplete="off"
                value={botTokenDraft}
                onChange={(e) => onBotTokenDraftChange(e.target.value)}
                placeholder="Токен от BotFather"
                className="flex-1 px-3 py-2 rounded-lg bg-gray-900 border border-gray-600 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
              <button
                type="button"
                disabled={savingBotToken || !botTokenDraft.trim()}
                onClick={onSaveBotToken}
                className="inline-flex items-center justify-center px-4 py-2 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 rounded-lg text-sm font-medium shrink-0"
              >
                {savingBotToken ? 'Сохранение…' : 'Сохранить токен'}
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
