'use client';

import { useState, useMemo } from 'react';
import { Plus, Trash2, Edit, TestTube, Users, Link, ChevronDown, ChevronRight, Power, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Connection {
  client_group_id: number;
  verifier_group_id: number;
  client_group_name: string | null;
  verifier_group_name: string | null;
  created_at: string;
  is_active: boolean;
}

function connectionKey(c: Connection): string {
  return `${c.client_group_id}-${c.verifier_group_id}`;
}

interface ConnectionListProps {
  connections: Connection[];
  onDeactivate: (clientId: number, verifierId: number) => void;
  onDelete: (clientId: number, verifierId: number) => void;
  onTest: (clientId: number, verifierId: number) => void;
  onAddClient: (verifierId: number) => void;
  onEditGroupId: (oldId: number, newId: number) => void;
  onDeleteAllFromVerifier: (verifierId: number) => void;
  onBulkSuccess?: () => void;
}

export function ConnectionList({ connections, onDeactivate, onDelete, onTest, onAddClient, onEditGroupId, onDeleteAllFromVerifier, onBulkSuccess }: ConnectionListProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState<'deactivate' | 'delete' | null>(null);

  const toggleExpanded = (id: string) => {
    setExpandedId(expandedId === id ? null : id);
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

  const runBulk = async (action: 'deactivate' | 'delete') => {
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

  const handleBulkDeactivate = () => {
    runBulk('deactivate');
  };

  const handleBulkDelete = () => {
    if (!confirm(`Удалить выбранные связи (${selectedCount})? Это действие нельзя отменить.`)) return;
    runBulk('delete');
  };

  // Группируем связи по группам проверяющих
  const groupedConnections = connections.reduce((acc, connection) => {
    const verifierId = connection.verifier_group_id;
    if (!acc[verifierId]) {
      acc[verifierId] = [];
    }
    acc[verifierId].push(connection);
    return acc;
  }, {} as Record<number, Connection[]>);

  if (connections.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Users className="mx-auto h-12 w-12 mb-4 opacity-50" />
        <p>Связи между группами не найдены</p>
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
              onClick={handleBulkDeactivate}
              disabled={!!loading}
              className="px-3 py-1.5 rounded-lg bg-orange-500/20 text-orange-300 hover:bg-orange-500/30 flex items-center gap-1.5 text-sm disabled:opacity-50"
            >
              {loading === 'deactivate' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Power className="h-3.5 w-3.5" />}
              Деактивировать выбранные
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
        const verifierIdNum = parseInt(verifierId);
        const firstConnection = verifierConnections[0];
        const groupId = `verifier-${verifierId}`;
        const isExpanded = expandedId === groupId;

        return (
          <div
            key={groupId}
            className="mobile-card hover:shadow-lg transition-all duration-300 w-full glass-card"
          >
            <div className="flex items-center justify-between w-full">
              <div 
                className="flex items-center space-x-3 flex-1 min-w-0 cursor-pointer"
                onClick={() => toggleExpanded(groupId)}
              >
                <div className="p-2 bg-gradient-to-r from-blue-500/20 to-purple-500/20 rounded-lg flex-shrink-0">
                  <Link className="h-5 w-5 text-blue-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-medium truncate text-sm sm:text-base text-white">
                    {firstConnection.verifier_group_name || `Группа проверяющих ${verifierId}`}
                  </h3>
                  <p className="text-xs sm:text-sm text-gray-300 truncate">
                    ID: {verifierId} • {verifierConnections.length} клиентов
                  </p>
                </div>
              </div>
              
              <div className="flex items-center space-x-1 sm:space-x-2 flex-shrink-0">
                <button
                  onClick={() => onAddClient(verifierIdNum)}
                  className="p-1.5 sm:p-2 text-green-400 hover:bg-green-500/20 rounded-lg transition-colors"
                  title="Добавить клиента"
                >
                  <Plus className="h-4 w-4" />
                </button>
                <button
                  onClick={() => onDeleteAllFromVerifier(verifierIdNum)}
                  className="p-1.5 sm:p-2 text-red-400 hover:bg-red-500/20 rounded-lg transition-colors"
                  title="Удалить все связи группы"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
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
                        <button
                          onClick={() => onEditGroupId(parseInt(verifierId), 0)}
                          className="ml-2 p-1 text-blue-400 hover:bg-blue-500/20 rounded transition-colors"
                          title="Редактировать ID группы проверяющих"
                        >
                          <Edit className="h-3 w-3" />
                        </button>
                      </p>
                      <p className="text-sm text-gray-300">
                        <span className="text-gray-400">Название:</span> {firstConnection.verifier_group_name || 'Не указано'}
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
                          <div key={key} className="flex items-center justify-between p-2 sm:p-3 bg-white/5 rounded-lg w-full glass-card">
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
                                  <button
                                    type="button"
                                    onClick={(e) => { e.preventDefault(); e.stopPropagation(); onEditGroupId(connection.client_group_id, 0); }}
                                    className="ml-2 p-1 text-blue-400 hover:bg-blue-500/20 rounded transition-colors"
                                    title="Редактировать ID группы клиентов"
                                  >
                                    <Edit className="h-3 w-3" />
                                  </button>
                                </p>
                              </div>
                            </label>
                            <div className="flex items-center space-x-1 ml-2 flex-shrink-0">
                              <button
                                onClick={() => onTest(connection.client_group_id, connection.verifier_group_id)}
                                className="p-1.5 text-blue-400 hover:bg-blue-500/20 rounded transition-colors"
                                title="Проверить связь"
                              >
                                <TestTube className="h-3 w-3" />
                              </button>
                              <button
                                onClick={() => onDeactivate(connection.client_group_id, connection.verifier_group_id)}
                                className="p-1.5 text-orange-400 hover:bg-orange-500/20 rounded transition-colors"
                                title="Деактивировать связь"
                              >
                                <Power className="h-3 w-3" />
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
