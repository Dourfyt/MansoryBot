'use client';

import { useState, useEffect } from 'react';
import { X, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

interface UpdateGroupIdModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: { old_group_id: number; new_group_id: number }) => void;
  prefillOldId?: number;
}

export function UpdateGroupIdModal({ isOpen, onClose, onSubmit, prefillOldId }: UpdateGroupIdModalProps) {
  const [formData, setFormData] = useState({
    old_group_id: prefillOldId ? prefillOldId.toString() : '',
    new_group_id: ''
  });
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Обновляем форму при изменении prefillOldId
  useEffect(() => {
    if (prefillOldId) {
      setFormData(prev => ({
        ...prev,
        old_group_id: prefillOldId.toString()
      }));
    }
  }, [prefillOldId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});

    // Валидация
    const newErrors: Record<string, string> = {};

    if (!formData.old_group_id.trim()) {
      newErrors.old_group_id = 'Старый ID группы обязателен';
    } else if (isNaN(Number(formData.old_group_id))) {
      newErrors.old_group_id = 'ID должен быть числом';
    }

    if (!formData.new_group_id.trim()) {
      newErrors.new_group_id = 'Новый ID группы обязателен';
    } else if (isNaN(Number(formData.new_group_id))) {
      newErrors.new_group_id = 'ID должен быть числом';
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    // Отправка данных
    onSubmit({
      old_group_id: Number(formData.old_group_id),
      new_group_id: Number(formData.new_group_id)
    });

    // Сброс формы
    setFormData({
      old_group_id: '',
      new_group_id: ''
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
          <h2 className="text-lg font-semibold text-white">Обновить ID группы</h2>
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
              Старый ID группы *
            </label>
            <input
              type="text"
              value={formData.old_group_id}
              onChange={(e) => handleInputChange('old_group_id', e.target.value)}
              className={cn(
                "mobile-input text-white placeholder-gray-400",
                errors.old_group_id ? "border-red-500" : ""
              )}
              placeholder="Например: -1001234567890"
            />
            {errors.old_group_id && (
              <p className="text-red-300 text-sm mt-1 flex items-center">
                <AlertCircle className="h-4 w-4 mr-1" />
                {errors.old_group_id}
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium mb-2 text-gray-300">
              Новый ID группы *
            </label>
            <input
              type="text"
              value={formData.new_group_id}
              onChange={(e) => handleInputChange('new_group_id', e.target.value)}
              className={cn(
                "mobile-input text-white placeholder-gray-400",
                errors.new_group_id ? "border-red-500" : ""
              )}
              placeholder="Например: -1001234567890"
            />
            {errors.new_group_id && (
              <p className="text-red-300 text-sm mt-1 flex items-center">
                <AlertCircle className="h-4 w-4 mr-1" />
                {errors.new_group_id}
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
              className="flex-1 mobile-button bg-gradient-to-r from-orange-500 to-red-600 text-white hover:from-orange-600 hover:to-red-700 transition-all duration-300"
            >
              Обновить
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
