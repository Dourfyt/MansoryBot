# Mansory Bot Admin Panel

Админ-панель для управления связями групп Telegram бота Mansory с безопасной авторизацией через Telegram Web App.

## 🔐 Безопасная авторизация

Приложение использует Telegram Web App init data для безопасной авторизации:
- **Проверка подписи** - все данные подписаны Telegram
- **Проверка админов** - доступ только для администраторов бота
- **Сессионные токены** - безопасные HTTP-only cookies
- **Автоматическая авторизация** - при открытии в Telegram

## 🤖 Настройка Telegram Bot

### 1. Создание Web App

В вашем Telegram боте добавьте команду для открытия админ-панели:

```python
from telegram import BotCommand, WebAppInfo
from telegram.ext import CommandHandler

async def admin_command(update, context):
    await update.message.reply_text(
        "Админ-панель Mansory Bot",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "Открыть админ-панель",
                web_app=WebAppInfo(url="https://jsanfasfnkajfkasjkf.ru")
            )
        ]])
    )

# Регистрация команды
application.add_handler(CommandHandler("admin", admin_command))
```

### 2. Настройка команд бота

```python
async def set_commands():
    commands = [
        BotCommand("admin", "Админ-панель управления связями"),
        # другие команды...
    ]
    await bot.set_my_commands(commands)

# Вызовите эту функцию при запуске бота
```

### 3. Проверка доступа

В боте добавьте проверку, что только админы могут использовать команду:

```python
ADMINS = [1234746517, 7606256823, 7756719528]

async def admin_command(update, context):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("У вас нет доступа к админ-панели")
        return
    
    await update.message.reply_text(
        "Админ-панель Mansory Bot",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "Открыть админ-панель",
                web_app=WebAppInfo(url="https://jsanfasfnkajfkasjkf.ru")
            )
        ]])
    )
```

## 🚀 Деплой на сервер

### Предварительные требования

1. **Сервер с Ubuntu 20.04+**
2. **Домен `jsanfasfnkajfkasjkf.ru`** настроенный на сервер
3. **Root доступ** к серверу
4. **Минимум 2GB RAM** (рекомендуется 4GB+)

### Быстрый деплой

1. **Скопируйте файлы на сервер:**
```bash
scp -r admin-app/* user@your-server:/tmp/mansory-admin/
```

2. **Подключитесь к серверу и запустите деплой:**
```bash
ssh user@your-server
sudo mv /tmp/mansory-admin /opt/
cd /opt/mansory-admin
sudo chmod +x deploy.sh
sudo ./deploy.sh
```

### Альтернативный способ (rsync):

```bash
# Прямая синхронизация с исключениями
rsync -av --exclude='node_modules' \
         --exclude='.next' \
         --exclude='.git' \
         --exclude='.env.local' \
         --exclude='.env.development' \
         --exclude='logs' \
         admin-app/ user@your-server:/opt/mansory-admin/

# Затем на сервере:
ssh user@your-server
cd /opt/mansory-admin
sudo chmod +x deploy.sh
sudo ./deploy.sh
```

## 🔧 Конфигурация

### Переменные окружения

В файле `lib/telegram-auth.ts` настройте:

```typescript
// Конфигурация бота
const BOT_TOKEN = "YOUR_BOT_TOKEN_HERE";

// Список админов
const ADMINS = [1234746517, 7606256823, 7756719528];
```

### Обновление конфигурации

После изменения конфигурации перезапустите приложение:

```bash
sudo systemctl restart mansory-admin
```

## 🔒 Безопасность

### Telegram Web App Security

- **Подпись данных** - все init data подписаны секретным ключом
- **Проверка хеша** - сервер проверяет подлинность данных
- **Временные метки** - данные содержат timestamp
- **Проверка пользователя** - доступ только для админов

### Сессионные токены

- **HTTP-only cookies** - недоступны для JavaScript
- **Secure флаг** - только HTTPS в продакшене
- **SameSite** - защита от CSRF атак
- **Автоистечение** - токены живут 7 дней

## 📱 Использование

### Открытие в Telegram

1. В боте выполните команду `/admin`
2. Нажмите кнопку "Открыть админ-панель"
3. Приложение откроется в Telegram Web App
4. Автоматическая авторизация через Telegram

### Функции админ-панели

- **Просмотр связей** - все активные и неактивные связи
- **Добавление связей** - создание новых связей групп
- **Редактирование** - изменение ID групп
- **Удаление** - деактивация или полное удаление
- **Проверка** - тестирование работоспособности связей
- **Статистика** - общая статистика по связям

## 🆘 Устранение неполадок

### Проблемы с авторизацией

1. **Проверьте токен бота** в `lib/telegram-auth.ts`
2. **Убедитесь, что пользователь в списке админов**
3. **Проверьте, что приложение открыто в Telegram**

### Проблемы с Web App

1. **Проверьте URL** в кнопке бота
2. **Убедитесь, что домен настроен правильно**
3. **Проверьте SSL сертификат**

### Логи и отладка

```bash
# Просмотр логов приложения
sudo journalctl -u mansory-admin -f

# Проверка статуса сервисов
sudo systemctl status nginx
sudo systemctl status mansory-admin
```

## 🌐 Доступ

После успешного деплоя админ-панель будет доступна:
- **В Telegram:** через команду `/admin` в боте
- **В браузере:** https://jsanfasfnkajfkasjkf.ru (только для авторизованных)

## 🔧 Управление после деплоя

```bash
# Запуск/остановка/перезапуск
sudo ./manage.sh start
sudo ./manage.sh stop
sudo ./manage.sh restart

# Просмотр статуса и логов
sudo ./manage.sh status
sudo ./manage.sh logs

# Обновление приложения
sudo ./manage.sh update

# Обновление SSL сертификата
sudo ./manage.sh ssl-renew

# Создание резервной копии
sudo ./manage.sh backup
```

## 📝 Лицензия

Этот проект разработан для внутреннего использования администраторами Mansory Bot.
