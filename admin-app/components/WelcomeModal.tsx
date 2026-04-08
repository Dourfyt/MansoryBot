'use client';

import { useState, useEffect } from 'react';
import { X, Save, Plus, Trash2 } from 'lucide-react';

interface WelcomeLink {
  label: string;
  url: string;
}

interface WelcomeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export function WelcomeModal({ isOpen, onClose, onSuccess }: WelcomeModalProps) {
  const [welcomeMessage, setWelcomeMessage] = useState('');
  const [links, setLinks] = useState<WelcomeLink[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setError(null);
      loadWelcome();
    }
  }, [isOpen]);

  const loadWelcome = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/welcome');
      const data = await res.json();
      if (res.ok) {
        setWelcomeMessage(data.welcome_message || '');
        setLinks(Array.isArray(data.welcome_links) ? data.welcome_links : []);
      } else {
        setError(data.error || 'Ошибка загрузки');
      }
    } catch {
      setError('Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  };

  const addLink = () => {
    setLinks((prev) => [...prev, { label: '', url: '' }]);
  };

  const removeLink = (index: number) => {
    setLinks((prev) => prev.filter((_, i) => i !== index));
  };

  const updateLink = (index: number, field: 'label' | 'url', value: string) => {
    setLinks((prev) =>
      prev.map((item, i) => (i === index ? { ...item, [field]: value } : item))
    );
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch('/api/welcome', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          welcome_message: welcomeMessage,
          welcome_links: links.filter((l) => l.url.trim()),
        }),
      });
      const data = await res.json();
      if (res.ok) {
        onSuccess?.();
        onClose();
      } else {
        setError(data.error || 'Ошибка сохранения');
      }
    } catch {
      setError('Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-card border border-border rounded-lg shadow-xl w-full max-w-lg max-h-[90vh] flex flex-col glass-card">
        <div className="flex items-center justify-between p-4 border-b border-border flex-shrink-0">
          <h2 className="text-lg font-semibold text-white">Приветствие и актуальные ссылки</h2>
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-4 space-y-4 overflow-y-auto flex-1 min-h-0">
          <p className="text-xs text-gray-400">
            Это сообщение и ссылки видны всем, кто открывает бота в личке и не является администратором. Если пусто — показывается «У вас нет прав».
          </p>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Текст приветствия</label>
            <textarea
              value={welcomeMessage}
              onChange={(e) => setWelcomeMessage(e.target.value)}
              placeholder="Например: 👋 Добро пожаловать! Ниже актуальные ссылки."
              rows={3}
              className="w-full px-3 py-2 bg-background border border-border rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
              disabled={loading || saving}
            />
          </div>
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-gray-300">Актуальные ссылки</label>
              <button
                type="button"
                onClick={addLink}
                className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1"
              >
                <Plus className="h-4 w-4" />
                Добавить ссылку
              </button>
            </div>
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {links.map((link, index) => (
                <div
                  key={index}
                  className="flex gap-2 items-start p-2 rounded-lg bg-background/50 border border-border"
                >
                  <input
                    type="text"
                    value={link.label}
                    onChange={(e) => updateLink(index, 'label', e.target.value)}
                    placeholder="Текст кнопки"
                    className="flex-1 min-w-0 px-2 py-1.5 rounded bg-background border border-border text-white text-sm placeholder-gray-500"
                    disabled={loading || saving}
                  />
                  <input
                    type="url"
                    value={link.url}
                    onChange={(e) => updateLink(index, 'url', e.target.value)}
                    placeholder="https://..."
                    className="flex-1 min-w-0 px-2 py-1.5 rounded bg-background border border-border text-white text-sm placeholder-gray-500"
                    disabled={loading || saving}
                  />
                  <button
                    type="button"
                    onClick={() => removeLink(index)}
                    className="p-1.5 text-red-400 hover:bg-red-500/20 rounded"
                    title="Удалить"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          </div>
          {error && (
            <div className="p-3 bg-red-500/20 border border-red-500/30 rounded-lg text-red-100 text-sm">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 p-4 border-t border-border flex-shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-300 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
            disabled={saving}
          >
            Закрыть
          </button>
          <button
            onClick={handleSave}
            disabled={loading || saving}
            className="px-4 py-2 bg-gradient-to-r from-blue-500 to-purple-600 text-white rounded-lg hover:from-blue-600 hover:to-purple-700 transition-all duration-300 flex items-center gap-2 disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            Сохранить
          </button>
        </div>
      </div>
    </div>
  );
}
