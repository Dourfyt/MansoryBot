'use client';

import { useState, useEffect, useMemo, useCallback } from 'react';
import { X, Send, Loader2, ShieldCheck, Search, UserX, UserPlus } from 'lucide-react';

interface BroadcastGroup {
  chat_id: number;
  name: string | null;
  role: 'client' | 'verifier' | 'group';
}

interface BroadcastModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

type ExcludeTab = 'session' | 'always';

export function BroadcastModal({ isOpen, onClose, onSuccess }: BroadcastModalProps) {
  const [text, setText] = useState('');
  const [excludeChatIds, setExcludeChatIds] = useState<Set<number>>(new Set());
  const [alwaysExcludeIds, setAlwaysExcludeIds] = useState<Set<number>>(new Set());
  const [alwaysSaving, setAlwaysSaving] = useState(false);
  const [excludeTab, setExcludeTab] = useState<ExcludeTab>('session');
  const [groups, setGroups] = useState<BroadcastGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ sent: number; failed: number; total: number; message: string } | null>(null);
  const [checkResult, setCheckResult] = useState<string | null>(null);
  const [excludeSearch, setExcludeSearch] = useState('');
  const [alwaysSearch, setAlwaysSearch] = useState('');
  const [excludingInactive, setExcludingInactive] = useState(false);
  /** Последний список неактивных с сервера — для переключения «исключить» ↔ «добавить обратно». */
  const [inactiveSnapshot, setInactiveSnapshot] = useState<number[] | null>(null);
  const [showMarkedOnly, setShowMarkedOnly] = useState(false);
  const [alwaysShowMarkedOnly, setAlwaysShowMarkedOnly] = useState(false);

  const loadAlwaysExclude = useCallback(async () => {
    try {
      const res = await fetch('/api/broadcast/always-exclude');
      const data = await res.json();
      if (res.ok && Array.isArray(data.chat_ids)) {
        setAlwaysExcludeIds(new Set(data.chat_ids.map((x: number) => Number(x))));
      }
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      setResult(null);
      setCheckResult(null);
      setError(null);
      setInactiveSnapshot(null);
      loadGroups();
      void loadAlwaysExclude();
    }
  }, [isOpen, loadAlwaysExclude]);

  const loadGroups = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/broadcast/groups');
      const data = await response.json();
      if (response.ok) {
        setGroups(data);
      } else {
        setError(data.error || 'Ошибка загрузки групп');
      }
    } catch {
      setError('Ошибка загрузки групп');
    } finally {
      setLoading(false);
    }
  };

  const persistAlwaysExclude = async (next: Set<number>) => {
    setAlwaysSaving(true);
    setError(null);
    try {
      const res = await fetch('/api/broadcast/always-exclude', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_ids: Array.from(next) }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || 'Не удалось сохранить постоянные исключения');
        await loadAlwaysExclude();
        return;
      }
      if (Array.isArray(data.chat_ids)) {
        setAlwaysExcludeIds(new Set(data.chat_ids.map((x: number) => Number(x))));
      }
    } catch {
      setError('Ошибка сохранения постоянных исключений');
      await loadAlwaysExclude();
    } finally {
      setAlwaysSaving(false);
    }
  };

  const handleCheckAvailability = async () => {
    setChecking(true);
    setError(null);
    setCheckResult(null);
    try {
      const response = await fetch('/api/broadcast/check-availability', { method: 'POST' });
      const data = await response.json();
      if (response.ok) {
        setCheckResult(data.message ?? 'Проверка завершена');
        await loadGroups();
      } else {
        setError(data.error || 'Ошибка проверки доступности');
      }
    } catch {
      setError('Ошибка при проверке (бот может быть не запущен)');
    } finally {
      setChecking(false);
    }
  };

  const toggleExclude = (chatId: number) => {
    if (alwaysExcludeIds.has(chatId)) return;
    setExcludeChatIds((prev) => {
      const next = new Set(prev);
      if (next.has(chatId)) next.delete(chatId);
      else next.add(chatId);
      return next;
    });
  };

  const toggleSelectAllExcludes = () => {
    setExcludeChatIds((prev) => {
      const allSessionSelected =
        groups.length > 0 && groups.every((g) => prev.has(g.chat_id));
      if (allSessionSelected) return new Set();
      return new Set(groups.map((g) => g.chat_id));
    });
  };

  const toggleAlwaysExclude = (chatId: number) => {
    const next = new Set(alwaysExcludeIds);
    if (next.has(chatId)) next.delete(chatId);
    else next.add(chatId);
    setAlwaysExcludeIds(next);
    void persistAlwaysExclude(next);
  };

  const toggleSelectAllAlways = () => {
    const allInListSelected =
      groups.length > 0 && groups.every((g) => alwaysExcludeIds.has(g.chat_id));
    let next: Set<number>;
    if (allInListSelected) {
      const groupIds = new Set(groups.map((g) => g.chat_id));
      next = new Set([...alwaysExcludeIds].filter((id) => !groupIds.has(id)));
    } else {
      next = new Set([...alwaysExcludeIds, ...groups.map((g) => g.chat_id)]);
    }
    setAlwaysExcludeIds(next);
    void persistAlwaysExclude(next);
  };

  const inactiveBatchFullyExcluded = useMemo(() => {
    if (!inactiveSnapshot || inactiveSnapshot.length === 0) return false;
    return inactiveSnapshot.every((id) => excludeChatIds.has(id));
  }, [inactiveSnapshot, excludeChatIds]);

  const handleInactiveExcludeOrRestore = async () => {
    if (inactiveBatchFullyExcluded && inactiveSnapshot) {
      setExcludeChatIds((prev) => {
        const next = new Set(prev);
        for (const id of inactiveSnapshot) next.delete(id);
        return next;
      });
      setInactiveSnapshot(null);
      setCheckResult('Неактивные группы снова участвуют в этой рассылке (если не в «Всегда исключать»).');
      return;
    }

    setExcludingInactive(true);
    setError(null);
    try {
      const response = await fetch('/api/broadcast/inactive-groups');
      const data = await response.json();
      if (response.ok && Array.isArray(data.chat_ids)) {
        const ids = data.chat_ids.map((x: number) => Number(x));
        if (ids.length > 0) {
          setInactiveSnapshot(ids);
          setExcludeChatIds((prev) => new Set([...prev, ...ids]));
          setCheckResult(
            `Исключено неактивных групп: ${ids.length} (без чеков за сегодня)`
          );
        } else {
          setInactiveSnapshot(null);
          setCheckResult('Нет неактивных групп без чеков за сегодня');
        }
      } else {
        setError(data.error || 'Ошибка загрузки списка неактивных');
      }
    } catch {
      setError('Ошибка при запросе (бот может быть не запущен)');
    } finally {
      setExcludingInactive(false);
    }
  };

  const handleSubmit = async () => {
    const trimmed = text.trim();
    if (!trimmed) {
      setError('Введите текст сообщения');
      return;
    }
    setSending(true);
    setError(null);
    setResult(null);
    try {
      const response = await fetch('/api/broadcast', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: trimmed,
          exclude_chat_ids: Array.from(excludeChatIds),
        }),
      });
      const data = await response.json();
      if (response.ok) {
        setResult({
          sent: data.sent ?? 0,
          failed: data.failed ?? 0,
          total: data.total ?? 0,
          message: data.message ?? 'Готово',
        });
        setText('');
        setExcludeChatIds(new Set());
        setInactiveSnapshot(null);
        if (onSuccess) onSuccess();
      } else {
        setError(data.error || 'Ошибка рассылки');
      }
    } catch {
      setError('Ошибка при отправке');
    } finally {
      setSending(false);
    }
  };

  const effectiveExcludedIds = useMemo(
    () => new Set([...excludeChatIds, ...alwaysExcludeIds]),
    [excludeChatIds, alwaysExcludeIds]
  );

  const excludeSearchLower = excludeSearch.trim().toLowerCase();
  const filteredGroups = useMemo(() => {
    const bySearch =
      excludeSearchLower === ''
        ? groups
        : groups.filter(
            (g) =>
              (g.name && g.name.toLowerCase().includes(excludeSearchLower)) ||
              String(g.chat_id).includes(excludeSearchLower)
          );
    if (!showMarkedOnly) return bySearch;
    return bySearch.filter((g) => effectiveExcludedIds.has(g.chat_id));
  }, [groups, excludeSearchLower, showMarkedOnly, effectiveExcludedIds]);

  const alwaysDisplayGroups = useMemo(() => {
    const map = new Map<number, BroadcastGroup>();
    for (const g of groups) map.set(g.chat_id, g);
    for (const id of alwaysExcludeIds) {
      if (!map.has(id)) {
        map.set(id, { chat_id: id, name: null, role: 'group' });
      }
    }
    return [...map.values()].sort((a, b) => a.chat_id - b.chat_id);
  }, [groups, alwaysExcludeIds]);

  const alwaysSearchLower = alwaysSearch.trim().toLowerCase();
  const filteredAlwaysGroups = useMemo(() => {
    const bySearch =
      alwaysSearchLower === ''
        ? alwaysDisplayGroups
        : alwaysDisplayGroups.filter(
            (g) =>
              (g.name && g.name.toLowerCase().includes(alwaysSearchLower)) ||
              String(g.chat_id).includes(alwaysSearchLower)
          );
    if (!alwaysShowMarkedOnly) return bySearch;
    return bySearch.filter((g) => alwaysExcludeIds.has(g.chat_id));
  }, [alwaysDisplayGroups, alwaysSearchLower, alwaysShowMarkedOnly, alwaysExcludeIds]);

  const allGroupsExcluded = useMemo(
    () => groups.length > 0 && groups.every((g) => excludeChatIds.has(g.chat_id)),
    [groups, excludeChatIds]
  );

  const allGroupsAlwaysExcluded = useMemo(
    () => groups.length > 0 && groups.every((g) => alwaysExcludeIds.has(g.chat_id)),
    [groups, alwaysExcludeIds]
  );

  const toSendCount = useMemo(
    () => groups.filter((g) => !effectiveExcludedIds.has(g.chat_id)).length,
    [groups, effectiveExcludedIds]
  );

  if (!isOpen) return null;

  const tabBtn = (active: boolean) =>
    `flex-1 px-3 py-2 text-sm font-medium rounded-md transition-colors ${
      active
        ? 'bg-blue-500/25 text-white border border-blue-500/40'
        : 'text-gray-400 hover:text-gray-200 border border-transparent'
    }`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-card border border-border rounded-lg shadow-xl w-full max-w-lg max-h-[90vh] flex flex-col glass-card">
        <div className="flex items-center justify-between p-4 border-b border-border flex-shrink-0">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Send className="h-5 w-5 text-blue-400" />
            Ручная рассылка
          </h2>
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-4 space-y-4 overflow-y-auto flex-1 min-h-0">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Текст сообщения</label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Введите текст для рассылки..."
              rows={4}
              className="w-full px-3 py-2 bg-background border border-border rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
              disabled={loading || sending}
            />
          </div>

          <div>
            <div className="flex rounded-lg border border-border p-0.5 gap-0.5 bg-background/40 mb-3">
              <button type="button" className={tabBtn(excludeTab === 'session')} onClick={() => setExcludeTab('session')}>
                Эта рассылка
              </button>
              <button type="button" className={tabBtn(excludeTab === 'always')} onClick={() => setExcludeTab('always')}>
                Всегда исключать
              </button>
            </div>

            {excludeTab === 'session' && (
              <>
                <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
                  <label className="block text-sm font-medium text-gray-300">
                    Исключить только сейчас ({excludeChatIds.size} выбрано)
                  </label>
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={handleInactiveExcludeOrRestore}
                      disabled={
                        loading ||
                        excludingInactive ||
                        (!inactiveBatchFullyExcluded && groups.length === 0)
                      }
                      className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-gray-600/30 text-gray-300 hover:bg-gray-500/40 border border-gray-500/50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      title={
                        inactiveBatchFullyExcluded
                          ? 'Вернуть в эту рассылку группы, исключённые как неактивные (без чеков за сегодня)'
                          : 'Добавить в исключения группы, в которых за сегодня не было чеков'
                      }
                    >
                      {excludingInactive ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : inactiveBatchFullyExcluded ? (
                        <UserPlus className="h-3.5 w-3.5" />
                      ) : (
                        <UserX className="h-3.5 w-3.5" />
                      )}
                      {excludingInactive
                        ? 'Загрузка...'
                        : inactiveBatchFullyExcluded
                          ? 'Добавить неактивные'
                          : 'Исключить неактивные'}
                    </button>
                    <button
                      type="button"
                      onClick={handleCheckAvailability}
                      disabled={loading || checking}
                      className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 border border-amber-500/40 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      title="Проверить доступность групп и обновить названия (рекомендуется перед рассылкой)"
                    >
                      {checking ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <ShieldCheck className="h-3.5 w-3.5" />
                      )}
                      {checking ? 'Проверка...' : 'Проверить доступность'}
                    </button>
                  </div>
                </div>
                {loading ? (
                  <p className="text-gray-400 text-sm">Загрузка групп...</p>
                ) : groups.length === 0 ? (
                  <p className="text-gray-400 text-sm">
                    Нет групп. Запустите «Проверить доступность» после того, как бот обновил список из папки databases.
                  </p>
                ) : (
                  <>
                    <div className="flex flex-col gap-2 mb-2">
                      <div className="relative">
                        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500 pointer-events-none" />
                        <input
                          type="text"
                          value={excludeSearch}
                          onChange={(e) => setExcludeSearch(e.target.value)}
                          placeholder="Поиск по названию или ID..."
                          className="w-full px-3 py-2 pl-9 bg-background border border-border rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                        />
                      </div>
                      <div className="flex flex-wrap items-center gap-3">
                        <button
                          type="button"
                          onClick={toggleSelectAllExcludes}
                          disabled={loading || groups.length === 0}
                          className="text-sm font-medium text-blue-400 hover:text-blue-300 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {allGroupsExcluded ? 'Снять выделение' : 'Выбрать все'}
                        </button>
                        <label className="flex items-center gap-2 cursor-pointer text-sm text-gray-300 select-none">
                          <input
                            type="checkbox"
                            checked={showMarkedOnly}
                            onChange={(e) => setShowMarkedOnly(e.target.checked)}
                            className="rounded border-border text-blue-500 focus:ring-blue-500"
                          />
                          Показать отмеченные
                        </label>
                      </div>
                    </div>
                    <div className="max-h-48 overflow-y-auto space-y-2 rounded-lg border border-border bg-background/50 p-2">
                      {filteredGroups.length === 0 ? (
                        <p className="text-gray-400 text-sm py-2">
                          {showMarkedOnly && effectiveExcludedIds.size === 0
                            ? 'Нет отмеченных групп — отметьте чекбоксы выше'
                            : 'Ничего не найдено'}
                        </p>
                      ) : (
                        filteredGroups.map((g) => {
                          const lockedByAlways = alwaysExcludeIds.has(g.chat_id);
                          const checked = excludeChatIds.has(g.chat_id) || lockedByAlways;
                          return (
                            <label
                              key={g.chat_id}
                              className={`flex items-center gap-2 rounded px-2 py-1.5 ${
                                lockedByAlways ? 'opacity-90' : 'cursor-pointer hover:bg-white/5'
                              }`}
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                disabled={lockedByAlways}
                                onChange={() => toggleExclude(g.chat_id)}
                                title={
                                  lockedByAlways
                                    ? 'Снять постоянное исключение во вкладке «Всегда исключать»'
                                    : undefined
                                }
                                className="rounded border-border text-blue-500 focus:ring-blue-500 disabled:cursor-not-allowed"
                              />
                              <span className="text-sm text-white truncate">
                                {g.name || `ID ${g.chat_id}`}
                                <span className="text-gray-500 ml-1">({g.chat_id})</span>
                                {lockedByAlways && (
                                  <span className="text-amber-400/90 text-xs ml-1">· всегда</span>
                                )}
                              </span>
                              <span className="text-xs text-gray-400">
                                {g.role === 'client' ? 'клиенты' : g.role === 'verifier' ? 'проверяющие' : 'группа'}
                              </span>
                            </label>
                          );
                        })
                      )}
                    </div>
                  </>
                )}
              </>
            )}

            {excludeTab === 'always' && (
              <>
                <div className="mb-2">
                  <label className="block text-sm font-medium text-gray-300">
                    Постоянный список ({alwaysExcludeIds.size}{alwaysSaving ? ' · сохранение…' : ''})
                  </label>
                  <p className="text-xs text-gray-500 mt-1">
                    Эти группы не получат рассылку, пока вы не снимете отметку здесь. Настройка хранится в базе.
                  </p>
                </div>
                {loading ? (
                  <p className="text-gray-400 text-sm">Загрузка групп...</p>
                ) : groups.length === 0 ? (
                  <p className="text-gray-400 text-sm">
                    Нет групп. Запустите «Проверить доступность» на вкладке «Эта рассылка».
                  </p>
                ) : (
                  <>
                    <div className="flex flex-col gap-2 mb-2">
                      <div className="relative">
                        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500 pointer-events-none" />
                        <input
                          type="text"
                          value={alwaysSearch}
                          onChange={(e) => setAlwaysSearch(e.target.value)}
                          placeholder="Поиск по названию или ID..."
                          className="w-full px-3 py-2 pl-9 bg-background border border-border rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                          disabled={alwaysSaving}
                        />
                      </div>
                      <div className="flex flex-wrap items-center gap-3">
                        <button
                          type="button"
                          onClick={toggleSelectAllAlways}
                          disabled={loading || groups.length === 0 || alwaysSaving}
                          className="text-sm font-medium text-blue-400 hover:text-blue-300 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {allGroupsAlwaysExcluded ? 'Снять выделение' : 'Выбрать все'}
                        </button>
                        <label className="flex items-center gap-2 cursor-pointer text-sm text-gray-300 select-none">
                          <input
                            type="checkbox"
                            checked={alwaysShowMarkedOnly}
                            onChange={(e) => setAlwaysShowMarkedOnly(e.target.checked)}
                            disabled={alwaysSaving}
                            className="rounded border-border text-blue-500 focus:ring-blue-500"
                          />
                          Показать отмеченные
                        </label>
                      </div>
                    </div>
                    <div className="max-h-48 overflow-y-auto space-y-2 rounded-lg border border-border bg-background/50 p-2">
                      {filteredAlwaysGroups.length === 0 ? (
                        <p className="text-gray-400 text-sm py-2">
                          {alwaysShowMarkedOnly && alwaysExcludeIds.size === 0
                            ? 'Нет отмеченных групп'
                            : 'Ничего не найдено'}
                        </p>
                      ) : (
                        filteredAlwaysGroups.map((g) => (
                          <label
                            key={g.chat_id}
                            className="flex items-center gap-2 cursor-pointer hover:bg-white/5 rounded px-2 py-1.5"
                          >
                            <input
                              type="checkbox"
                              checked={alwaysExcludeIds.has(g.chat_id)}
                              onChange={() => toggleAlwaysExclude(g.chat_id)}
                              disabled={alwaysSaving}
                              className="rounded border-border text-blue-500 focus:ring-blue-500"
                            />
                            <span className="text-sm text-white truncate">
                              {g.name || `ID ${g.chat_id}`}
                              <span className="text-gray-500 ml-1">({g.chat_id})</span>
                            </span>
                            <span className="text-xs text-gray-400">
                              {g.role === 'client' ? 'клиенты' : g.role === 'verifier' ? 'проверяющие' : 'группа'}
                            </span>
                          </label>
                        ))
                      )}
                    </div>
                  </>
                )}
              </>
            )}

            {!loading && groups.length > 0 && (
              <p className="mt-2 text-xs text-gray-400">
                Будет отправлено в {toSendCount} из {groups.length} групп
                {alwaysExcludeIds.size > 0 && (
                  <span className="text-gray-500"> (постоянно исключено: {alwaysExcludeIds.size})</span>
                )}
                .
              </p>
            )}
          </div>

          {error && (
            <div className="p-3 bg-red-500/20 border border-red-500/30 rounded-lg text-red-100 text-sm">
              {error}
            </div>
          )}
          {checkResult && (
            <div className="p-3 bg-amber-500/20 border border-amber-500/30 rounded-lg text-amber-100 text-sm">
              {checkResult}
            </div>
          )}
          {result && (
            <div className="p-3 bg-green-500/20 border border-green-500/30 rounded-lg text-green-100 text-sm">
              {result.message}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 p-4 border-t border-border flex-shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-300 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
            disabled={sending}
          >
            Закрыть
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading || sending || !text.trim() || toSendCount <= 0}
            className="px-4 py-2 bg-gradient-to-r from-blue-500 to-purple-600 text-white rounded-lg hover:from-blue-600 hover:to-purple-700 transition-all duration-300 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {sending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Отправка...
              </>
            ) : (
              <>
                <Send className="h-4 w-4" />
                Отправить в {toSendCount} групп
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
