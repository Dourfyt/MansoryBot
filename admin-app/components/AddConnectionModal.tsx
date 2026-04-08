'use client';

import { useState } from 'react';
import { X, Plus, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

interface AddConnectionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: { client_group_id: number; verifier_group_id: number }) => void;
}

export function AddConnectionModal({ isOpen, onClose, onSubmit }: AddConnectionModalProps) {
  const [formData, setFormData] = useState({
    client_group_id: '',
    verifier_group_id: ''
  });
  const [errors, setErrors] = useState<Record<string, string>>({});

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});

    // Валидация
    const newErrors: Record<string, string> = {};

    if (!formData.client_group_id.trim()) {
      newErrors.client_group_id = 'ID группы клиентов обязателен';
    } else if (isNaN(Number(formData.client_group_id))) {
      newErrors.client_group_id = 'ID должен быть числом';
    }

    if (!formData.verifier_group_id.trim()) {
      newErrors.verifier_group_id = 'ID группы проверяющих обязателен';
    } else if (isNaN(Number(formData.verifier_group_id))) {
      newErrors.verifier_group_id = 'ID должен быть числом';
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    // Отправка данных
    onSubmit({
      client_group_id: Number(formData.client_group_id),
      verifier_group_id: Number(formData.verifier_group_id)
    });

    // Сброс формы
    setFormData({
      client_group_id: '',
      verifier_group_id: ''
    });
    setErrors({});
    onClose();
  };

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: '' }));
    }
  };

  if (!isOpen) return null;

  return (
    <div className="mobile-modal">
      <div className="mobile-modal-content">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Добавить связь</h2>
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2 text-gray-300">
              ID группы клиентов *
            </label>
            <input
              type="text"
              value={formData.client_group_id}
              onChange={(e) => handleInputChange('client_group_id', e.target.value)}
              className={cn(
                "mobile-input text-white placeholder-gray-400",
                errors.client_group_id ? "border-red-500" : ""
              )}
              placeholder="Например: -1001234567890"
            />
            {errors.client_group_id && (
              <p className="text-red-300 text-sm mt-1 flex items-center">
                <AlertCircle className="h-4 w-4 mr-1" />
                {errors.client_group_id}
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium mb-2 text-gray-300">
              ID группы проверяющих *
            </label>
            <input
              type="text"
              value={formData.verifier_group_id}
              onChange={(e) => handleInputChange('verifier_group_id', e.target.value)}
              className={cn(
                "mobile-input text-white placeholder-gray-400",
                errors.verifier_group_id ? "border-red-500" : ""
              )}
              placeholder="Например: -1001234567890"
            />
            {errors.verifier_group_id && (
              <p className="text-red-300 text-sm mt-1 flex items-center">
                <AlertCircle className="h-4 w-4 mr-1" />
                {errors.verifier_group_id}
              </p>
            )}
          </div>

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
              className="flex-1 mobile-button bg-gradient-to-r from-blue-500 to-purple-600 text-white hover:from-blue-600 hover:to-purple-700 transition-all duration-300 flex items-center justify-center"
            >
              <Plus className="h-4 w-4 mr-2" />
              Добавить
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
