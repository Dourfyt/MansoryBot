'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import NextLink from 'next/link';
import { ArrowLeft, Users, KeyRound, Trash2, Save, LogOut, RefreshCw } from 'lucide-react';
import {
  type SupportPermissions,
  DEFAULT_SUPPORT_PERMISSIONS,
  SUPPORT_PERMISSION_KEYS,
  parsePermissions,
} from '@/lib/support-permissions-core';

const PERM_LABELS: Record<keyof SupportPermissions, string> = {
  connections: 'Связки и статистика',
  wallet: 'Адрес кошелька Tron',
  broadcast: 'Ручная рассылка',
  welcome: 'Приветствие и актуальные ссылки',
  anonymous: 'Анонимные чаты',
};

function formatPermissionSummary(p: SupportPermissions): string {
  const active = SUPPORT_PERMISSION_KEYS.filter((k) => p[k]);
  if (active.length === SUPPORT_PERMISSION_KEYS.length) return 'полный доступ';
  if (active.length === 0) return 'нет прав панели';
  return active.map((k) => PERM_LABELS[k]).join(', ');
}

function PermCheckboxes({
  value,
  onChange,
}: {
  value: SupportPermissions;
  onChange: (next: SupportPermissions) => void;
}) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {SUPPORT_PERMISSION_KEYS.map((key) => (
        <label
          key={key}
          className="flex items-start gap-2 text-sm text-gray-300 cursor-pointer"
        >
          <input
            type="checkbox"
            checked={value[key]}
            onChange={(e) => onChange({ ...value, [key]: e.target.checked })}
            className="mt-0.5 rounded border-gray-600"
          />
          <span>{PERM_LABELS[key]}</span>
        </label>
      ))}
    </div>
  );
}

interface CrmUser {
  id: number;
  email: string;
  role: string;
  created_at: string | null;
  telegram_user_id?: number | null;
  support_permissions?: unknown | null;
}

interface BotInstance {
  id: number;
  label: string;
  is_active: number;
  created_at: string;
  has_token: boolean;
}

export default function CrmSettingsPage() {
  const router = useRouter();
  const [users, setUsers] = useState<CrmUser[]>([]);
  const [instances, setInstances] = useState<BotInstance[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const [newEmail, setNewEmail] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newTelegramId, setNewTelegramId] = useState('');
  const [savingUser, setSavingUser] = useState(false);

  const [editId, setEditId] = useState<number | null>(null);
  const [editEmail, setEditEmail] = useState('');
  const [editPassword, setEditPassword] = useState('');
  const [editTelegramId, setEditTelegramId] = useState('');
  const [newPerms, setNewPerms] = useState<SupportPermissions>(() => ({
    ...DEFAULT_SUPPORT_PERMISSIONS,
  }));
  const [editPerms, setEditPerms] = useState<SupportPermissions>(() => ({
    ...DEFAULT_SUPPORT_PERMISSIONS,
  }));

  const [tokenById, setTokenById] = useState<Record<number, string>>({});
  const [savingToken, setSavingToken] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = async (opts?: { silent?: boolean }) => {
    const silent = opts?.silent ?? false;
    if (!silent) setLoading(true);
    setErr(null);
    try {
      const [uRes, bRes] = await Promise.all([
        fetch('/api/auth/users'),
        fetch('/api/bot-instances'),
      ]);
      const uData = await uRes.json();
      const bData = await bRes.json();
      if (!uRes.ok) throw new Error(uData.error || 'Ошибка загрузки пользователей');
      if (!bRes.ok) throw new Error(bData.error || 'Ошибка загрузки бота');
      setUsers(uData.users || []);
      setInstances(bData.instances || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await load({ silent: true });
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const createSupport = async () => {
    setSavingUser(true);
    setErr(null);
    try {
      const tg = parseInt(newTelegramId.trim(), 10);
      if (!Number.isFinite(tg) || tg < 1) {
        throw new Error('Укажите числовой Telegram ID');
      }
      const res = await fetch('/api/auth/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: newEmail.trim(),
          password: newPassword,
          telegram_user_id: tg,
          support_permissions: newPerms,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Не создано');
      setNewEmail('');
      setNewPassword('');
      setNewTelegramId('');
      setNewPerms({ ...DEFAULT_SUPPORT_PERMISSIONS });
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setSavingUser(false);
    }
  };

  const saveEdit = async (id: number) => {
    setSavingUser(true);
    setErr(null);
    try {
      const body: {
        email?: string;
        password?: string;
        telegram_user_id?: number | null;
        support_permissions: SupportPermissions;
      } = { support_permissions: editPerms };
      if (editEmail.trim()) body.email = editEmail.trim();
      if (editPassword.trim()) body.password = editPassword;
      if (editTelegramId.trim() === '') {
        body.telegram_user_id = null;
      } else {
        const tg = parseInt(editTelegramId.trim(), 10);
        if (!Number.isFinite(tg) || tg < 1) {
          throw new Error('Некорректный Telegram ID');
        }
        body.telegram_user_id = tg;
      }
      const res = await fetch(`/api/auth/users/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Не сохранено');
      setEditId(null);
      setEditEmail('');
      setEditPassword('');
      setEditTelegramId('');
      setEditPerms({ ...DEFAULT_SUPPORT_PERMISSIONS });
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setSavingUser(false);
    }
  };

  const removeUser = async (id: number, email: string) => {
    if (!confirm(`Удалить пользователя ${email}?`)) return;
    setErr(null);
    try {
      const res = await fetch(`/api/auth/users/${id}`, { method: 'DELETE' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Не удалено');
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    }
  };

  const saveToken = async (id: number) => {
    const token = (tokenById[id] || '').trim();
    if (!token) {
      setErr('Введите токен от @BotFather');
      return;
    }
    setSavingToken(true);
    setErr(null);
    try {
      const res = await fetch('/api/bot-instances', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, telegram_bot_token: token }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Не сохранено');
      setTokenById((prev) => ({ ...prev, [id]: '' }));
      await load();
      alert(data.message || 'Сохранено');
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setSavingToken(false);
    }
  };

  const logout = async () => {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.push('/login');
  };

  return (
    <div className="min-h-screen bg-background animated-bg text-white">
      <header className="border-b border-border bg-card/80">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <NextLink
              href="/"
              className="p-2 rounded-lg hover:bg-white/10 text-gray-300 hover:text-white"
            >
              <ArrowLeft className="h-5 w-5" />
            </NextLink>
            <div>
              <h1 className="text-xl font-bold">CRM: пользователи и бот</h1>
              <p className="text-sm text-gray-400">Только для главного администратора</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void handleRefresh()}
              disabled={refreshing}
              className="flex items-center gap-2 px-3 py-2 bg-gray-800 rounded-lg hover:bg-gray-700 text-sm disabled:opacity-60"
              aria-label="Обновить"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
              Обновить
            </button>
            <button
              type="button"
              onClick={logout}
              className="flex items-center gap-2 px-3 py-2 bg-gray-800 rounded-lg hover:bg-gray-700 text-sm"
            >
              <LogOut className="h-4 w-4" />
              Выход
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8 space-y-10">
        {err && (
          <div className="p-3 bg-red-900/30 border border-red-800 rounded text-red-200 text-sm">{err}</div>
        )}

        {loading ? (
          <p className="text-gray-400">Загрузка…</p>
        ) : (
          <>
            <section className="glass-card rounded-xl p-6 border border-border">
              <h2 className="text-lg font-semibold flex items-center gap-2 mb-4">
                <Users className="h-5 w-5 text-blue-400" />
                Пользователи поддержки (support)
              </h2>
              <p className="text-sm text-gray-400 mb-4">
                Учётку администратора с ролью admin не создаём и не меняем здесь — только операторы support. Для
                каждого support укажите его Telegram user id (число, например из @userinfobot) — на него придут
                уведомления о новых сообщениях в тикетах. Отметьте, к каким разделам панели у саппорта будет
                доступ: без галочки пункт в меню не показывается.
              </p>

              <div className="space-y-3 mb-6">
                {users.map((u) => (
                  <div
                    key={u.id}
                    className="flex flex-col sm:flex-row sm:items-center gap-2 p-3 border border-gray-700 rounded-lg bg-gray-900/40"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate">{u.email}</div>
                      <div className="text-xs text-gray-500">
                        {u.role} · id {u.id}
                        {typeof u.telegram_user_id === 'number' && u.telegram_user_id > 0
                          ? ` · TG ${u.telegram_user_id}`
                          : ''}
                        {u.created_at ? ` · ${new Date(u.created_at).toLocaleString('ru-RU')}` : ''}
                      </div>
                      {u.role === 'support' && (
                        <div className="text-xs text-gray-400 mt-1">
                          Панель: {formatPermissionSummary(parsePermissions(u.support_permissions))}
                        </div>
                      )}
                    </div>
                    {u.role === 'support' ? (
                      editId === u.id ? (
                        <div className="flex flex-col gap-2 w-full sm:w-auto">
                          <input
                            type="email"
                            placeholder="Email"
                            value={editEmail}
                            onChange={(e) => setEditEmail(e.target.value)}
                            className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm"
                          />
                          <input
                            type="password"
                            placeholder="Новый пароль (необязательно)"
                            value={editPassword}
                            onChange={(e) => setEditPassword(e.target.value)}
                            className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm"
                          />
                          <input
                            type="text"
                            inputMode="numeric"
                            placeholder="Telegram ID (число, для уведомлений)"
                            value={editTelegramId}
                            onChange={(e) => setEditTelegramId(e.target.value)}
                            className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm font-mono"
                          />
                          <div className="text-xs text-gray-500 mb-1">Права в панели</div>
                          <PermCheckboxes value={editPerms} onChange={setEditPerms} />
                          <div className="flex gap-2">
                            <button
                              type="button"
                              disabled={savingUser}
                              onClick={() => saveEdit(u.id)}
                              className="flex items-center gap-1 px-3 py-1 bg-blue-600 rounded text-sm"
                            >
                              <Save className="h-4 w-4" />
                              Сохранить
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setEditId(null);
                                setEditEmail('');
                                setEditPassword('');
                                setEditTelegramId('');
                                setEditPerms({ ...DEFAULT_SUPPORT_PERMISSIONS });
                              }}
                              className="px-3 py-1 bg-gray-700 rounded text-sm"
                            >
                              Отмена
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setEditId(u.id);
                              setEditEmail(u.email);
                              setEditPassword('');
                              setEditTelegramId(
                                typeof u.telegram_user_id === 'number' && u.telegram_user_id > 0
                                  ? String(u.telegram_user_id)
                                  : ''
                              );
                              setEditPerms(parsePermissions(u.support_permissions));
                            }}
                            className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm"
                          >
                            Изменить
                          </button>
                          <button
                            type="button"
                            onClick={() => removeUser(u.id, u.email)}
                            className="text-red-400 hover:text-red-300 p-2"
                            title="Удалить"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      )
                    ) : (
                      <span className="text-xs text-amber-400/90">admin — не редактируется здесь</span>
                    )}
                  </div>
                ))}
              </div>

              <div className="border-t border-gray-700 pt-4">
                <h3 className="text-sm font-medium text-gray-300 mb-2">Новый support</h3>
                <div className="flex flex-col gap-2">
                  <div className="text-xs text-gray-500 mb-1">Права в панели</div>
                  <PermCheckboxes value={newPerms} onChange={setNewPerms} />
                  <div className="flex flex-col sm:flex-row gap-2">
                    <input
                      type="email"
                      placeholder="Email"
                      value={newEmail}
                      onChange={(e) => setNewEmail(e.target.value)}
                      className="flex-1 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm"
                    />
                    <input
                      type="password"
                      placeholder="Пароль (8+ символов)"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      className="flex-1 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm"
                    />
                  </div>
                  <div className="flex flex-col sm:flex-row gap-2 sm:items-center">
                    <input
                      type="text"
                      inputMode="numeric"
                      placeholder="Telegram ID (обязательно)"
                      value={newTelegramId}
                      onChange={(e) => setNewTelegramId(e.target.value)}
                      className="flex-1 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm font-mono"
                    />
                    <button
                      type="button"
                      disabled={
                        savingUser ||
                        !newEmail.trim() ||
                        newPassword.length < 8 ||
                        !newTelegramId.trim()
                      }
                      onClick={createSupport}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg text-sm font-medium shrink-0"
                    >
                      Создать
                    </button>
                  </div>
                </div>
              </div>
            </section>

            <section className="glass-card rounded-xl p-6 border border-border">
              <h2 className="text-lg font-semibold flex items-center gap-2 mb-4">
                <KeyRound className="h-5 w-5 text-amber-400" />
                Токен Telegram-бота
              </h2>
              <p className="text-sm text-gray-400 mb-4">
                Сохраняется в базе. Процесс бота подхватывает новый токен автоматически (проверка ~12 с).
                Убедитесь, что в @BotFather отключён webhook для этого бота, если используете polling.
              </p>
              {instances.map((inst) => (
                <div key={inst.id} className="space-y-2">
                  <div className="text-sm text-gray-300">
                    {inst.label} (id={inst.id}){inst.has_token ? ' · токен задан' : ' · токен не задан'}
                  </div>
                  <input
                    type="password"
                    autoComplete="off"
                    placeholder="Новый токен от BotFather"
                    value={tokenById[inst.id] ?? ''}
                    onChange={(e) =>
                      setTokenById((prev) => ({ ...prev, [inst.id]: e.target.value }))
                    }
                    className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm font-mono"
                  />
                  <button
                    type="button"
                    disabled={savingToken}
                    onClick={() => saveToken(inst.id)}
                    className="px-4 py-2 bg-amber-700 hover:bg-amber-600 disabled:opacity-50 rounded-lg text-sm font-medium"
                  >
                    {savingToken ? 'Сохранение…' : 'Сохранить токен'}
                  </button>
                </div>
              ))}
              {instances.length === 0 && (
                <p className="text-gray-500 text-sm">Нет записей bot_instances (создайте через bootstrap).</p>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
