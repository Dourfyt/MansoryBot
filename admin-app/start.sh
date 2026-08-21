#!/bin/bash

# Скрипт для запуска админ-панели Mansory Bot

echo "🚀 Запуск админ-панели Mansory Bot..."

# Проверяем, что мы в правильной директории
if [ ! -f "package.json" ]; then
    echo "❌ Ошибка: package.json не найден. Убедитесь, что вы находитесь в папке admin-app"
    exit 1
fi

# Проверяем, что база данных существует
if [ ! -f "../databases/group_connections.db" ]; then
    echo "⚠️  Предупреждение: База данных ../databases/group_connections.db не найдена"
    echo "   Убедитесь, что бот был запущен хотя бы один раз"
fi

# Устанавливаем зависимости, если node_modules не существует
if [ ! -d "node_modules" ]; then
    echo "📦 Установка зависимостей..."
    npm install
fi

# Запускаем приложение
echo "🌐 Запуск приложения на http://localhost:3000"
echo "Нажмите Ctrl+C для остановки"

npm run dev
