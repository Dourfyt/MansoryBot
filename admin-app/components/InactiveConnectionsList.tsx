'use client';

import { useState, useMemo } from 'react';
import { ChevronDown, ChevronRight, Link, Trash2, RotateCcw, Loader2 } from 'lucide-react';

interface Connection {
  client_group_id: number;
  verifier_group_id: number;
  client_group_name: string | null;
  verifier_group_name: string | null;
  created_at: string;
  is_active: boolean;
}

interface InactiveConnectionsListProps {
  connections: Connection[];
  onRestore: (client_group_id: number, verifier_group_id: number) => void;
  onDelete: (client_group_id: number, verifier_group_id: number) => void;
  onBulkSuccess?: () => void;
}

function connectionKey(c: Connection): string {
  return `${c.client_group_id}-${c.verifier_group_id}`;
}

export function InactiveConnectionsList({ connections, onRestore, onDelete, onBulkSuccess }: InactiveConnectionsListProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState<'restore' | 'delete' | null>(null);

  const toggleExpanded = (groupId: string) => {
    setExpandedId(expandedId === groupId ? null : groupId);
  };

  const allKeys = useMemo(() => connections.map(connectionKey), [connections]);
  const selectedCount = useMemo(() => allKeys.filter((k) => selected.has(k)).length, [allKeys, selected]);

  const toggleOne = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedCount === allKeys.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(allKeys));
    }
  };

  const selectedConnections = useMemo(
    () => connections.filter((c) => selected.has(connectionKey(c))),
    [connections, selected]
  );

  const runBulk = async (action: 'restore' | 'delete') => {
    if (selectedConnections.length === 0) return;
    setLoading(action);
    try {
      const res = await fetch('/api/connections/bulk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          connections: selectedConnections.map((c) => ({
            client_group_id: c.client_group_id,
            verifier_group_id: c.verifier_group_id,
          })),
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setSelected(new Set());
        onBulkSuccess?.();
      } else {
        alert(data.error || 'Ошибка операции');
      }
    } catch (e) {
      alert('Ошибка запроса');
    } finally {
      setLoading(null);
    }
  };

  const handleBulkRestore = () => {
    runBulk('restore');
  };

  const handleBulkDelete = () => {
    if (!confirm(`Удалить выбранные связи (${selectedCount})? Это действие нельзя отменить.`)) return;
    runBulk('delete');
  };

  // Группируем связи по verifier_group_id
  const groupedConnections = connections.reduce((acc, connection) => {
    const verifierId = connection.verifier_group_id.toString();
    if (!acc[verifierId]) {
      acc[verifierId] = [];
    }
    acc[verifierId].push(connection);
    return acc;
  }, {} as Record<string, Connection[]>);

  if (connections.length === 0) {
    return (
      <div className="text-center py-8">
        <div className="p-4 bg-gray-500/10 rounded-lg inline-block mb-4">
          <Link className="h-8 w-8 text-gray-400" />
        </div>
        <p className="text-gray-400 text-sm">Нет неактивных связей</p>
      </div>
    );
  }

  return (
    <div className="space-y-4 w-full">
      {selectedCount > 0 && (
        <div className="flex flex-wrap items-center gap-2 p-3 rounded-lg bg-white/5 border border-border">
          <span className="text-sm text-gray-300">Выбрано: {selectedCount}</span>
          <label className="flex items-center gap-2 cursor-pointer text-sm text-white">
            <input
              type="checkbox"
              checked={selectedCount === allKeys.length}
              onChange={toggleAll}
              className="rounded border-border text-blue-500 focus:ring-blue-500"
            />
            {selectedCount === allKeys.length ? 'Снять выбор' : 'Выбрать все'}
          </label>
          <div className="flex items-center gap-2 ml-auto">
            <button
              onClick={handleBulkRestore}
              disabled={!!loading}
              className="px-3 py-1.5 rounded-lg bg-green-500/20 text-green-300 hover:bg-green-500/30 flex items-center gap-1.5 text-sm disabled:opacity-50"
            >
              {loading === 'restore' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
              Вернуть выбранные
            </button>
            <button
              onClick={handleBulkDelete}
              disabled={!!loading}
              className="px-3 py-1.5 rounded-lg bg-red-500/20 text-red-300 hover:bg-red-500/30 flex items-center gap-1.5 text-sm disabled:opacity-50"
            >
              {loading === 'delete' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
              Удалить выбранные
            </button>
          </div>
        </div>
      )}

      {Object.entries(groupedConnections).map(([verifierId, verifierConnections], groupIndex) => {
        const firstConnection = verifierConnections[0];
        const groupId = `inactive-verifier-${verifierId}`;
        const isExpanded = expandedId === groupId;

        return (
          <div
            key={groupId}
            className="mobile-card hover:shadow-lg transition-all duration-300 w-full glass-card border-l-4 border-red-400/50"
          >
            <div className="flex items-center justify-between w-full">
              <div className="flex items-center space-x-3 flex-1 min-w-0">
                <div className="p-2 bg-gradient-to-r from-red-500/20 to-orange-500/20 rounded-lg flex-shrink-0">
                  <Link className="h-5 w-5 text-red-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-medium truncate text-sm sm:text-base text-white">
                    {firstConnection.verifier_group_name || `Неактивная группа ${verifierId}`}
                  </h3>
                  <p className="text-xs sm:text-sm text-gray-300 truncate">
                    ID: {verifierId} • {verifierConnections.length} клиентов
                  </p>
                </div>
              </div>

              <div className="flex items-center space-x-1 sm:space-x-2 flex-shrink-0">
                <button
                  onClick={() => toggleExpanded(groupId)}
                  className="p-1.5 sm:p-2 text-gray-300 hover:bg-white/10 rounded-lg transition-colors"
                  title="Подробности"
                >
                  {isExpanded ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                </button>
              </div>
            </div>

            {isExpanded && (
              <div className="mt-4 pt-4 border-t border-white/10 w-full">
                <div className="space-y-3 w-full">
                  <div className="mb-3">
                    <h4 className="font-medium text-sm mb-2 text-white">Группа проверяющих</h4>
                    <div className="space-y-1">
                      <p className="text-sm text-gray-300">
                        <span className="text-gray-400">ID:</span> {verifierId}
                      </p>
                      <p className="text-sm text-gray-300">
                        <span className="text-gray-400">Название:</span> {firstConnection.verifier_group_name || 'Не указано'}
                      </p>
                      <p className="text-sm text-gray-300">
                        <span className="text-gray-400">Статус:</span> <span className="text-red-400">Неактивна</span>
                      </p>
                    </div>
                  </div>

                  <div className="w-full">
                    <h4 className="font-medium text-sm mb-2 text-white">Группы клиентов ({verifierConnections.length})</h4>
                    <div className="space-y-2 w-full">
                      {verifierConnections.map((connection) => {
                        const key = connectionKey(connection);
                        const isSelected = selected.has(key);
                        return (
                          <div
                            key={key}
                            className="flex items-center justify-between p-2 sm:p-3 bg-red-500/5 rounded-lg w-full glass-card"
                          >
                            <label className="flex items-center gap-2 flex-1 min-w-0 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={isSelected}
                                onChange={() => toggleOne(key)}
                                className="rounded border-border text-blue-500 focus:ring-blue-500 flex-shrink-0"
                              />
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium truncate text-white">
                                  {connection.client_group_name || `Клиент ${connection.client_group_id}`}
                                </p>
                                <p className="text-xs text-gray-300 truncate">
                                  ID: {connection.client_group_id}
                                </p>
                              </div>
                            </label>
                            <div className="flex items-center space-x-1 ml-2 flex-shrink-0">
                              <button
                                onClick={() => onRestore(connection.client_group_id, connection.verifier_group_id)}
                                className="p-1.5 text-green-400 hover:bg-green-500/20 rounded transition-colors"
                                title="Восстановить связь"
                              >
                                <RotateCcw className="h-3 w-3" />
                              </button>
                              <button
                                onClick={() => onDelete(connection.client_group_id, connection.verifier_group_id)}
                                className="p-1.5 text-red-400 hover:bg-red-500/20 rounded transition-colors"
                                title="Полностью удалить связь"
                              >
                                <Trash2 className="h-3 w-3" />
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
