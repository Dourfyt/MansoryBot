'use client';

import { useState } from 'react';
import { X, Plus, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

interface AddClientToVerifierModalProps {
  isOpen: boolean;
  onClose: () => void;
  verifierGroupId: number;
  onSubmit: (data: { client_group_id: number; verifier_group_id: number }) => void;
}

export function AddClientToVerifierModal({ 
  isOpen, 
  onClose, 
  verifierGroupId, 
  onSubmit 
}: AddClientToVerifierModalProps) {
  const [clientGroupId, setClientGroupId] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!clientGroupId.trim()) {
      setError('ID группы клиентов обязателен');
      return;
    }

    if (isNaN(Number(clientGroupId))) {
      setError('ID должен быть числом');
      return;
    }

    onSubmit({
      client_group_id: Number(clientGroupId),
      verifier_group_id: verifierGroupId
    });

    setClientGroupId('');
    setError('');
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="mobile-modal">
      <div className="mobile-modal-content">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Добавить клиента к проверяющему</h2>
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="p-3 bg-blue-500/10 border border-blue-400/30 rounded-lg">
            <p className="text-sm text-blue-300">
              <strong>Группа проверяющих:</strong> {verifierGroupId}
            </p>
          </div>

          <div>
            <label htmlFor="clientGroupId" className="block text-sm font-medium mb-2 text-gray-300">
              ID группы клиентов *
            </label>
            <input
              type="text"
              id="clientGroupId"
              value={clientGroupId}
              onChange={(e) => setClientGroupId(e.target.value)}
              className="mobile-input text-white placeholder-gray-400"
              placeholder="Например: -1001234567890"
              required
            />
          </div>

          {error && (
            <div className="p-3 bg-red-500/20 border border-red-400/30 rounded-lg">
              <p className="text-red-300 text-sm flex items-center">
                <AlertCircle className="h-4 w-4 mr-1" />
                {error}
              </p>
            </div>
          )}

          <div className="flex space-x-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 mobile-button bg-gray-600 text-white hover:bg-gray-700 transition-colors"
            >
              Отмена
            </button>
            <button
              type="submit"
              className="flex-1 mobile-button bg-gradient-to-r from-green-500 to-emerald-600 text-white hover:from-green-600 hover:to-emerald-700 transition-all duration-300 flex items-center justify-center"
            >
              <Plus className="h-4 w-4 mr-2" />
              Добавить клиента
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
