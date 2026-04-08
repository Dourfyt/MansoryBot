'use client';

import { useState, useEffect } from 'react';
import { X, Wallet, Save } from 'lucide-react';

interface WalletAddressModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export function WalletAddressModal({ isOpen, onClose, onSuccess }: WalletAddressModalProps) {
  const [walletAddress, setWalletAddress] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadWalletAddress();
    }
  }, [isOpen]);

  const loadWalletAddress = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/wallet-address`);
      const data = await response.json();
      
      if (response.ok) {
        setWalletAddress(data.wallet_address || '');
      } else {
        setError(data.error || 'Ошибка при загрузке адреса');
      }
    } catch (err) {
      setError('Ошибка при загрузке адреса кошелька');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const response = await fetch('/api/wallet-address', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          wallet_address: walletAddress.trim() || null,
        }),
      });

      const data = await response.json();

      if (response.ok) {
        if (onSuccess) {
          onSuccess();
        }
        onClose();
      } else {
        setError(data.error || 'Ошибка при сохранении адреса');
      }
    } catch (err) {
      setError('Ошибка при сохранении адреса кошелька');
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-card border border-border rounded-lg shadow-xl w-full max-w-md glass-card">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center space-x-2">
            <Wallet className="h-5 w-5 text-blue-400" />
            <h2 className="text-lg font-semibold text-white">Адрес кошелька</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Глобальный адрес кошелька Tron
            </label>
            <input
              type="text"
              value={walletAddress}
              onChange={(e) => setWalletAddress(e.target.value)}
              placeholder="Введите адрес кошелька (например: TQFq...)"
              className="w-full px-3 py-2 bg-background border border-border rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={loading || saving}
            />
            <p className="mt-2 text-xs text-gray-400">
              Общий адрес кошелька для всех групп. Транзакции будут приниматься только если они содержат этот адрес как отправитель или получатель.
            </p>
          </div>

          {error && (
            <div className="p-3 bg-red-500/20 border border-red-500/30 rounded-lg text-red-100 text-sm">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end space-x-2 p-4 border-t border-border">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-300 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
            disabled={saving}
          >
            Отмена
          </button>
          <button
            onClick={handleSave}
            disabled={loading || saving}
            className="px-4 py-2 bg-gradient-to-r from-blue-500 to-purple-600 text-white rounded-lg hover:from-blue-600 hover:to-purple-700 transition-all duration-300 flex items-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Save className="h-4 w-4" />
            <span>{saving ? 'Сохранение...' : 'Сохранить'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

