'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import NextLink from 'next/link';
import {
  Plus,
  RefreshCw,
  Settings,
  BarChart3,
  Users,
  Link,
  AlertCircle,
  CheckCircle,
  Database,
  Shield,
  Wallet,
  Send,
  MessageCircle,
  Headphones,
  Menu,
  X,
  FolderX,
} from 'lucide-react';
import { AnonymousChatsPanel } from '@/components/AnonymousChatsPanel';
import { ConnectionList } from '@/components/ConnectionList';
import { AddConnectionModal } from '@/components/AddConnectionModal';
import { UpdateGroupIdModal } from '@/components/UpdateGroupIdModal';
import { AddClientToVerifierModal } from '@/components/AddClientToVerifierModal';
import { InactiveConnectionsList } from '@/components/InactiveConnectionsList';
import { WalletAddressModal } from '@/components/WalletAddressModal';
import { BroadcastModal } from '@/components/BroadcastModal';
import { WelcomeModal } from '@/components/WelcomeModal';
import type { SupportPermissions } from '@/lib/support-permissions-core';

interface Connection {
  client_group_id: number;
  verifier_group_id: number;
  client_group_name: string | null;
  verifier_group_name: string | null;
  created_at: string;
  is_active: boolean;
}

interface Stats {
  total: number;
  active: number;
  inactive: number;
  unique_verifiers: number;
  unique_clients: number;
}

export default function AdminPanel() {
  const router = useRouter();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [inactiveConnections, setInactiveConnections] = useState<Connection[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showUpdateModal, setShowUpdateModal] = useState(false);
  const [showAddClientModal, setShowAddClientModal] = useState(false);
  const [showWalletModal, setShowWalletModal] = useState(false);
  const [showBroadcastModal, setShowBroadcastModal] = useState(false);
  const [showWelcomeModal, setShowWelcomeModal] = useState(false);
  const [selectedVerifierId, setSelectedVerifierId] = useState<number | null>(null);
  const [selectedOldGroupId, setSelectedOldGroupId] = useState<number | null>(null);
  const [showInactiveConnections, setShowInactiveConnections] = useState(false);
  const [notification, setNotification] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);
  const [supportUnreadTotal, setSupportUnreadTotal] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [sessionReady, setSessionReady] = useState(false);
  const [panelRole, setPanelRole] = useState<'admin' | 'support' | null>(null);
  const [panelPerms, setPanelPerms] = useState<SupportPermissions | null>(null);
  const [headerRefreshing, setHeaderRefreshing] = useState(false);
  /** Вкладка под статистикой: связки CRM vs анонимные чаты */
  const [mainTab, setMainTab] = useState<'connections' | 'anonymous'>('connections');

  const canPanel = (key: keyof SupportPermissions) => {
    if (panelRole === 'admin') return true;
    return !!(panelPerms && panelPerms[key]);
  };

  const showMainTabs = canPanel('connections') && canPanel('anonymous');

  const setMainTabAndUrl = (tab: 'connections' | 'anonymous') => {
    setMainTab(tab);
    if (tab === 'anonymous') {
      router.replace('/?tab=anonymous', { scroll: false });
    } else {
      router.replace('/', { scroll: false });
    }
  };

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/api/auth/session');
        if (!res.ok) {
          setSessionReady(true);
          return;
        }
        const d = await res.json();
        setPanelRole(d.role === 'admin' ? 'admin' : 'support');
        setPanelPerms(d.permissions ?? null);
        setIsAdmin(d.role === 'admin');
      } catch {
        setIsAdmin(false);
        setPanelRole(null);
        setPanelPerms(null);
      } finally {
        setSessionReady(true);
      }
    })();
  }, []);

  useEffect(() => {
    if (!sessionReady) return;
    if (typeof window === 'undefined') return;
    const p = new URLSearchParams(window.location.search);
    if (p.get('tab') !== 'anonymous') return;
    const anonOk = panelRole === 'admin' || !!panelPerms?.anonymous;
    if (anonOk) setMainTab('anonymous');
  }, [sessionReady, panelRole, panelPerms]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [menuOpen]);

  const loadSupportUnreadOnly = async () => {
    try {
      const unreadRes = await fetch('/api/support/unread-summary');
      if (unreadRes.ok) {
        const u = await unreadRes.json();
        setSupportUnreadTotal(typeof u.total === 'number' ? u.total : 0);
      } else {
        setSupportUnreadTotal(0);
      }
    } catch {
      setSupportUnreadTotal(0);
    }
  };

  // Загрузка данных (связки и статистика — только при праве connections)
  const loadData = async (opts?: { silent?: boolean }) => {
    const silent = opts?.silent ?? false;
    try {
      if (!silent) setLoading(true);

      // Загружаем активные связи
      const connectionsResponse = await fetch('/api/connections');
      const connectionsData = await connectionsResponse.json();
      
      if (!connectionsResponse.ok) {
        throw new Error(connectionsData.error || 'Ошибка при загрузке связей');
      }
      
      // Загружаем неактивные связи
      const inactiveResponse = await fetch('/api/connections?inactive=true');
      const inactiveData = await inactiveResponse.json();
      
      if (!inactiveResponse.ok) {
        throw new Error(inactiveData.error || 'Ошибка при загрузке неактивных связей');
      }
      
      // Загружаем статистику
      const statsResponse = await fetch('/api/stats');
      const statsData = await statsResponse.json();
      
      if (!statsResponse.ok) {
        throw new Error(statsData.error || 'Ошибка при загрузке статистики');
      }
      
      setConnections(connectionsData);
      setInactiveConnections(inactiveData);
      setStats(statsData);
      await loadSupportUnreadOnly();
    } catch (error) {
      console.error('Ошибка при загрузке данных:', error);
      showNotification('error', error instanceof Error ? error.message : 'Ошибка при загрузке данных');
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const handleHeaderRefresh = async () => {
    setHeaderRefreshing(true);
    try {
      if (canPanel('connections')) {
        await loadData({ silent: true });
      } else {
        await loadSupportUnreadOnly();
      }
    } finally {
      setHeaderRefreshing(false);
    }
  };

  useEffect(() => {
    if (!sessionReady) return;
    if (panelRole === 'admin' || (panelPerms && panelPerms.connections)) {
      loadData();
    } else {
      setLoading(false);
      setConnections([]);
      setInactiveConnections([]);
      setStats(null);
      loadSupportUnreadOnly();
    }
  }, [sessionReady, panelRole, panelPerms]);

  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const r = await fetch('/api/support/unread-summary');
        if (r.ok) {
          const d = await r.json();
          setSupportUnreadTotal(typeof d.total === 'number' ? d.total : 0);
        }
      } catch {
        /* ignore */
      }
    }, 45000);
    return () => clearInterval(id);
  }, []);

  // Показать уведомление
  const showNotification = (type: 'success' | 'error', message: string) => {
    setNotification({ type, message });
    setTimeout(() => setNotification(null), 5000);
  };

  // Добавить связь
  const handleAddConnection = async (data: {
    client_group_id: number;
    verifier_group_id: number;
  }) => {
    try {
      const response = await fetch('/api/connections', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });

      const result = await response.json();

      if (response.ok) {
        showNotification('success', 'Связь успешно добавлена');
        loadData();
      } else {
        showNotification('error', result.error || 'Ошибка при добавлении связи');
      }
    } catch (error) {
      showNotification('error', 'Ошибка при добавлении связи');
    }
  };

  // Добавить клиента к существующей группе проверяющих
  const handleAddClientToVerifier = async (data: {
    client_group_id: number;
    verifier_group_id: number;
  }) => {
    try {
      const response = await fetch('/api/connections', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });

      const result = await response.json();

      if (response.ok) {
        showNotification('success', 'Клиент успешно добавлен к группе проверяющих');
        loadData();
      } else {
        showNotification('error', result.error || 'Ошибка при добавлении клиента');
      }
    } catch (error) {
      showNotification('error', 'Ошибка при добавлении клиента');
    }
  };

  // Открыть модальное окно добавления клиента
  const handleOpenAddClientModal = (verifierId: number) => {
    setSelectedVerifierId(verifierId);
    setShowAddClientModal(true);
  };

  // Удалить все связи группы проверяющих
  const handleDeleteAllFromVerifier = async (verifierId: number) => {
    const connectionsForVerifier = connections.filter(c => c.verifier_group_id === verifierId);
    
    if (!confirm(`Вы уверены, что хотите удалить все связи группы проверяющих ${verifierId}? Это удалит ${connectionsForVerifier.length} связей!`)) return;

    try {
      // Удаляем все связи для данной группы проверяющих
      const deletePromises = connectionsForVerifier.map(connection =>
        fetch('/api/connections', {
          method: 'DELETE',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ 
            client_group_id: connection.client_group_id, 
            verifier_group_id: connection.verifier_group_id 
          })
        })
      );

      const results = await Promise.all(deletePromises);
      const successCount = results.filter(r => r.ok).length;

      if (successCount === connectionsForVerifier.length) {
        showNotification('success', `Удалено ${successCount} связей группы проверяющих`);
        loadData();
      } else {
        showNotification('error', `Удалено ${successCount} из ${connectionsForVerifier.length} связей`);
        loadData();
      }
    } catch (error) {
      console.error('Ошибка при удалении связей:', error);
      showNotification('error', 'Ошибка при удалении связей');
    }
  };

  // Редактировать ID группы
  const handleEditGroupId = (oldId: number, newId: number) => {
    // Открываем модальное окно с предзаполненным старым ID
    setSelectedOldGroupId(oldId);
    setShowUpdateModal(true);
  };

  // Деактивировать связь
  const handleDeactivateConnection = async (clientId: number, verifierId: number) => {
    if (!confirm('Вы уверены, что хотите деактивировать эту связь?')) return;

    try {
      const response = await fetch('/api/connections', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ client_group_id: clientId, verifier_group_id: verifierId })
      });

      const result = await response.json();

      if (response.ok) {
        showNotification('success', result.message);
        loadData();
      } else {
        showNotification('error', result.error || 'Ошибка при деактивации связи');
      }
    } catch (error) {
      showNotification('error', 'Ошибка при деактивации связи');
    }
  };

  // Удалить связь
  const handleDeleteConnection = async (clientId: number, verifierId: number) => {
    if (!confirm('Вы уверены, что хотите ПОЛНОСТЬЮ удалить эту связь? Это действие нельзя отменить!')) return;

    try {
      const response = await fetch('/api/connections', {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ client_group_id: clientId, verifier_group_id: verifierId })
      });

      const result = await response.json();

      if (response.ok) {
        showNotification('success', result.message);
        loadData();
      } else {
        showNotification('error', result.error || 'Ошибка при удалении связи');
      }
    } catch (error) {
      showNotification('error', 'Ошибка при удалении связи');
    }
  };

  // Проверить связь
  const handleTestConnection = async (clientId: number, verifierId: number) => {
    try {
      const response = await fetch('/api/test-connection', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ client_group_id: clientId, verifier_group_id: verifierId })
      });

      const result = await response.json();

      if (result.success) {
        showNotification('success', result.message);
      } else {
        showNotification('error', result.message);
      }
    } catch (error) {
      showNotification('error', 'Ошибка при проверке связи');
    }
  };

  // Обновить названия групп
  const handleUpdateNames = async () => {
    try {
      const response = await fetch('/api/update-names', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json'
        }
      });

      const result = await response.json();

      if (response.ok) {
        showNotification('success', result.message);
        loadData(); // Перезагружаем данные для отображения обновленных названий
      } else {
        showNotification('error', result.error || 'Ошибка при обновлении названий');
      }
    } catch (error) {
      console.error('Ошибка при обновлении названий:', error);
      showNotification('error', 'Ошибка при обновлении названий групп');
    }
  };

  // Восстановить связь
  const handleRestoreConnection = async (client_group_id: number, verifier_group_id: number) => {
    try {
      const response = await fetch('/api/connections', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ client_group_id, verifier_group_id })
      });

      const data = await response.json();

      if (response.ok) {
        showNotification('success', 'Связь успешно восстановлена');
        loadData(); // Перезагружаем данные
      } else {
        showNotification('error', data.error || 'Ошибка при восстановлении связи');
      }
    } catch (error) {
      console.error('Ошибка при восстановлении связи:', error);
      showNotification('error', 'Ошибка при восстановлении связи');
    }
  };

  // Полностью удалить неактивную связь
  const handleDeleteInactiveConnection = async (client_group_id: number, verifier_group_id: number) => {
    if (!confirm('Вы уверены, что хотите полностью удалить эту связь? Это действие нельзя отменить.')) return;

    try {
      const response = await fetch('/api/connections', {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ client_group_id, verifier_group_id })
      });

      const data = await response.json();

      if (response.ok) {
        showNotification('success', data.message);
        loadData();
      } else {
        showNotification('error', data.error);
      }
    } catch (error) {
      console.error('Ошибка при удалении связи:', error);
      showNotification('error', 'Ошибка при удалении связи');
    }
  };

  // Обновить ID группы
  const handleUpdateGroupId = async (data: { old_group_id: number; new_group_id: number }) => {
    try {
      const response = await fetch('/api/update-group-id', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });

      const result = await response.json();

      if (response.ok) {
        showNotification('success', 'ID группы успешно обновлен');
        loadData();
      } else {
        showNotification('error', result.error || 'Ошибка при обновлении ID группы');
      }
    } catch (error) {
      showNotification('error', 'Ошибка при обновлении ID группы');
    }
  };

  // Выйти из системы
  const handleLogout = async () => {
    try {
      const response = await fetch('/api/auth/logout', {
        method: 'POST'
      });

      if (response.ok) {
        router.push('/login');
      } else {
        showNotification('error', 'Ошибка при выходе');
      }
    } catch (error) {
      console.error('Logout error:', error);
      showNotification('error', 'Ошибка при выходе');
    }
  };

  if (!sessionReady) {
    return (
      <div className="min-h-screen flex items-center justify-center animated-bg">
        <div className="text-center">
          <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-4 text-blue-400" />
          <p className="text-gray-300">Загрузка сессии…</p>
        </div>
      </div>
    );
  }
  if (loading && canPanel('connections')) {
    return (
      <div className="min-h-screen flex items-center justify-center animated-bg">
        <div className="text-center">
          <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-4 text-blue-400" />
          <p className="text-gray-300">Загрузка данных…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background w-full overflow-x-hidden animated-bg">
      {/* Уведомления */}
      {notification && (
        <div className="fixed top-4 right-4 z-50">
          <div className={`
            p-4 rounded-lg shadow-lg border flex items-center space-x-2 glass-card
            ${notification.type === 'success' 
              ? 'bg-green-500/20 border-green-400/30 text-green-100' 
              : 'bg-red-500/20 border-red-400/30 text-red-100'
            }
          `}>
            {notification.type === 'success' ? (
              <CheckCircle className="h-5 w-5" />
            ) : (
              <AlertCircle className="h-5 w-5" />
            )}
            <span>{notification.message}</span>
          </div>
        </div>
      )}

      {/* Заголовок */}
      <header className="mobile-header border-b border-border bg-card">
        <div className="mobile-container py-4 sm:py-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3 min-w-0 flex-1">
              <div className="p-2 bg-primary/10 rounded-lg flex-shrink-0">
                <Link className="h-6 w-6 text-primary" />
              </div>
              <div className="min-w-0 flex-1">
                <h1 className="text-xl sm:text-2xl font-bold truncate text-white">Balenciaga Bot Admin</h1>
                <p className="text-sm text-gray-300 truncate">Панель управления</p>
              </div>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                type="button"
                onClick={handleHeaderRefresh}
                disabled={headerRefreshing}
                className="p-2.5 rounded-lg text-gray-200 hover:text-white hover:bg-white/10 border border-border transition-colors disabled:opacity-60"
                aria-label="Обновить данные"
              >
                <RefreshCw
                  className={`h-6 w-6 ${headerRefreshing ? 'animate-spin' : ''}`}
                />
              </button>
              {(panelRole === 'admin' || panelRole === 'support') && (
                <NextLink
                  href="/support"
                  className="relative p-2.5 rounded-lg text-gray-200 hover:text-white hover:bg-white/10 border border-border transition-colors"
                  aria-label="Поддержка (тикеты)"
                  title="Поддержка (тикеты)"
                >
                  <Headphones className="h-6 w-6" />
                  {supportUnreadTotal > 0 && (
                    <span className="absolute -top-0.5 -right-0.5 min-w-[1.125rem] h-[1.125rem] px-0.5 flex items-center justify-center rounded-full bg-cyan-500 text-[10px] font-bold leading-none text-gray-950">
                      {supportUnreadTotal > 99 ? '99+' : supportUnreadTotal}
                    </span>
                  )}
                </NextLink>
              )}
              <button
                type="button"
                onClick={() => setMenuOpen(true)}
                className="p-2.5 rounded-lg text-gray-200 hover:text-white hover:bg-white/10 border border-border transition-colors"
                aria-label="Открыть меню"
              >
                <Menu className="h-6 w-6" />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Статистика */}
      {canPanel('connections') && stats && (
        <section className="mobile-section border-b border-border bg-card/50">
          <div className="mobile-container py-4 sm:py-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg sm:text-xl font-semibold flex items-center text-white">
                <BarChart3 className="h-5 w-5 mr-2 text-blue-400" />
                Статистика
              </h2>
            </div>
            
            <div className="mobile-stats-grid">
              <div className="mobile-stats-item glass-card col-span-2">
                <div className="flex items-center justify-center w-6 h-6 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 mb-1">
                  <Database className="h-3 w-3 text-white" />
                </div>
                <div className="mobile-stats-value text-blue-400">{stats.total}</div>
                <div className="mobile-stats-label text-gray-300">Всего связей</div>
              </div>
              
              <div className="mobile-stats-item glass-card col-span-2">
                <div className="flex items-center justify-center w-6 h-6 rounded-full bg-gradient-to-br from-green-500 to-green-600 mb-1">
                  <CheckCircle className="h-3 w-3 text-white" />
                </div>
                <div className="mobile-stats-value text-green-400">{stats.active}</div>
                <div className="mobile-stats-label text-gray-300">Активных</div>
              </div>
              
              <div className="mobile-stats-item glass-card col-span-2">
                <div className="flex items-center justify-center w-6 h-6 rounded-full bg-gradient-to-br from-red-500 to-red-600 mb-1">
                  <AlertCircle className="h-3 w-3 text-white" />
                </div>
                <div className="mobile-stats-value text-red-400">{stats.inactive}</div>
                <div className="mobile-stats-label text-gray-300">Неактивных</div>
              </div>
              
              <div className="mobile-stats-item glass-card col-span-3">
                <div className="flex items-center justify-center w-6 h-6 rounded-full bg-gradient-to-br from-purple-500 to-purple-600 mb-1">
                  <Users className="h-3 w-3 text-white" />
                </div>
                <div className="mobile-stats-value text-purple-400">{stats.unique_clients}</div>
                <div className="mobile-stats-label text-gray-300">Групп клиентов</div>
              </div>
              
              <div className="mobile-stats-item glass-card col-span-3">
                <div className="flex items-center justify-center w-6 h-6 rounded-full bg-gradient-to-br from-yellow-500 to-yellow-600 mb-1">
                  <Shield className="h-3 w-3 text-white" />
                </div>
                <div className="mobile-stats-value text-yellow-400">{stats.unique_verifiers}</div>
                <div className="mobile-stats-label text-gray-300">Групп проверяющих</div>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Вкладки: связки CRM ↔ анонимные чаты */}
      {showMainTabs && (
        <section className="mobile-section border-b border-border bg-card/50">
          <div className="mobile-container py-3 sm:py-4">
            <div className="flex rounded-xl border border-border p-1 bg-black/25 gap-1 max-w-2xl">
              <button
                type="button"
                onClick={() => setMainTabAndUrl('connections')}
                className={`flex-1 flex items-center justify-center gap-2 px-3 sm:px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  mainTab === 'connections'
                    ? 'bg-primary/20 text-white border border-primary/30 shadow-sm'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
                }`}
              >
                <Users className="h-4 w-4 shrink-0" />
                <span className="truncate">Связки групп</span>
              </button>
              <button
                type="button"
                onClick={() => setMainTabAndUrl('anonymous')}
                className={`flex-1 flex items-center justify-center gap-2 px-3 sm:px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  mainTab === 'anonymous'
                    ? 'bg-primary/20 text-white border border-primary/30 shadow-sm'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
                }`}
              >
                <MessageCircle className="h-4 w-4 shrink-0" />
                <span className="truncate">Анонимные чаты</span>
              </button>
            </div>
          </div>
        </section>
      )}

      {/* Анонимные чаты (вкладка или только это право) */}
      {canPanel('anonymous') && (!canPanel('connections') || mainTab === 'anonymous') && (
        <main className="mobile-main mobile-container py-4 sm:py-6">
          <AnonymousChatsPanel enabled />
        </main>
      )}

      {/* Основной контент: связки — только с правом connections */}
      {canPanel('connections') && (!showMainTabs || mainTab === 'connections') ? (
        <main className="mobile-main mobile-container py-4 sm:py-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-6 gap-4">
            <h2 className="text-lg sm:text-xl font-semibold flex items-center min-w-0 text-white">
              <Users className="h-5 w-5 mr-2 flex-shrink-0" />
              <span className="truncate">Активные связи</span>
            </h2>
            <button
              onClick={() => setShowAddModal(true)}
              className="mobile-button bg-gradient-to-r from-blue-500 to-purple-600 text-white hover:from-blue-600 hover:to-purple-700 transition-all duration-300 flex items-center justify-center shadow-lg"
            >
              <Plus className="h-4 w-4 mr-2" />
              Добавить связь
            </button>
          </div>

          <ConnectionList
            connections={connections}
            onDeactivate={handleDeactivateConnection}
            onDelete={handleDeleteConnection}
            onTest={handleTestConnection}
            onAddClient={handleOpenAddClientModal}
            onEditGroupId={handleEditGroupId}
            onDeleteAllFromVerifier={handleDeleteAllFromVerifier}
            onBulkSuccess={loadData}
          />

          {inactiveConnections.length > 0 && (
            <div className="mt-8">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-lg font-semibold text-white flex items-center">
                  <Link className="h-5 w-5 mr-2 text-red-400" />
                  Неактивные связи ({inactiveConnections.length})
                </h3>
                <button
                  onClick={() => setShowInactiveConnections(!showInactiveConnections)}
                  className="mobile-button bg-gradient-to-r from-red-500 to-orange-600 text-white hover:from-red-600 hover:to-orange-700 transition-all duration-300 flex items-center justify-center shadow-lg"
                >
                  {showInactiveConnections ? 'Скрыть' : 'Показать'} неактивные
                </button>
              </div>

              {showInactiveConnections && (
                <InactiveConnectionsList
                  connections={inactiveConnections}
                  onRestore={handleRestoreConnection}
                  onDelete={handleDeleteInactiveConnection}
                  onBulkSuccess={loadData}
                />
              )}
            </div>
          )}
        </main>
      ) : !canPanel('anonymous') ? (
        <main className="mobile-main mobile-container py-8 sm:py-12">
          <p className="text-gray-400 text-center max-w-md mx-auto">
            У вас нет доступа к связкам групп. Откройте меню (☰) и выберите доступный раздел — например,
            поддержку тикетов.
          </p>
        </main>
      ) : null}

      {/* Модальные окна */}
      <AddConnectionModal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        onSubmit={handleAddConnection}
      />

      <UpdateGroupIdModal
        isOpen={showUpdateModal}
        onClose={() => {
          setShowUpdateModal(false);
          setSelectedOldGroupId(null);
        }}
        onSubmit={handleUpdateGroupId}
        prefillOldId={selectedOldGroupId || undefined}
      />

      <AddClientToVerifierModal
        isOpen={showAddClientModal}
        onClose={() => {
          setShowAddClientModal(false);
          setSelectedVerifierId(null);
        }}
        verifierGroupId={selectedVerifierId || 0}
        onSubmit={handleAddClientToVerifier}
      />

      <WalletAddressModal
        isOpen={showWalletModal}
        onClose={() => setShowWalletModal(false)}
      />

      <BroadcastModal
        isOpen={showBroadcastModal}
        onClose={() => setShowBroadcastModal(false)}
      />

      <WelcomeModal
        isOpen={showWelcomeModal}
        onClose={() => setShowWelcomeModal(false)}
      />

      <div
        className={`fixed inset-0 z-[100] bg-black/60 transition-opacity duration-300 ${
          menuOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        }`}
        onClick={() => setMenuOpen(false)}
        aria-hidden={!menuOpen}
      />
      <aside
        className={`fixed top-0 left-0 z-[101] h-full w-[min(20rem,92vw)] bg-card border-r border-border shadow-xl transition-transform duration-300 ease-out flex flex-col ${
          menuOpen ? 'translate-x-0' : '-translate-x-full pointer-events-none'
        }`}
      >
        <div className="flex items-center justify-between p-4 border-b border-border shrink-0">
          <span className="font-semibold text-white">Меню</span>
          <button
            type="button"
            onClick={() => setMenuOpen(false)}
            className="p-2 rounded-lg hover:bg-white/10 text-gray-300"
            aria-label="Закрыть меню"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <nav className="p-2 flex flex-col gap-1 overflow-y-auto flex-1 pb-6">
          {canPanel('wallet') && (
            <button
              type="button"
              onClick={() => {
                setShowWalletModal(true);
                setMenuOpen(false);
              }}
              className="flex items-center gap-3 w-full px-3 py-3 rounded-lg text-left text-gray-200 hover:bg-white/10 transition-colors"
            >
              <Wallet className="h-5 w-5 text-purple-300 shrink-0" />
              <span>Адрес кошелька Tron</span>
            </button>
          )}
          {canPanel('broadcast') && (
            <button
              type="button"
              onClick={() => {
                setShowBroadcastModal(true);
                setMenuOpen(false);
              }}
              className="flex items-center gap-3 w-full px-3 py-3 rounded-lg text-left text-gray-200 hover:bg-white/10 transition-colors"
            >
              <Send className="h-5 w-5 text-green-300 shrink-0" />
              <span>Ручная рассылка</span>
            </button>
          )}
          {canPanel('welcome') && (
            <button
              type="button"
              onClick={() => {
                setShowWelcomeModal(true);
                setMenuOpen(false);
              }}
              className="flex items-center gap-3 w-full px-3 py-3 rounded-lg text-left text-gray-200 hover:bg-white/10 transition-colors"
            >
              <MessageCircle className="h-5 w-5 text-amber-300 shrink-0" />
              <span>Приветствие и ссылки</span>
            </button>
          )}
          {isAdmin && (
            <NextLink
              href="/admin/chats"
              onClick={() => setMenuOpen(false)}
              className="flex items-center gap-3 w-full px-3 py-3 rounded-lg text-gray-200 hover:bg-white/10 transition-colors"
            >
              <FolderX className="h-5 w-5 text-rose-300 shrink-0" />
              <span>Чаты и рассылка</span>
            </NextLink>
          )}
          {isAdmin && (
            <NextLink
              href="/crm-settings"
              onClick={() => setMenuOpen(false)}
              className="flex items-center gap-3 w-full px-3 py-3 rounded-lg text-gray-200 hover:bg-white/10 transition-colors"
            >
              <Settings className="h-5 w-5 text-orange-300 shrink-0" />
              <span>Настройки CRM</span>
            </NextLink>
          )}
        </nav>
      </aside>
    </div>
  );
}
