# Balenciaga Bot Admin Panel

Админ-панель для управления связями групп Telegram бота Balenciaga.

## 🚀 Деплой на сервер

### Предварительные требования

1. **Сервер с Ubuntu 20.04+**
2. **Домен `jsanfasfnkajfkasjkf.ru`** настроенный на сервер
3. **Root доступ** к серверу

### Быстрый деплой

1. **Скопируйте файлы на сервер:**
```bash
scp -r admin-app/* user@your-server:/tmp/balenciaga-admin/
```

2. **Подключитесь к серверу и запустите деплой:**
```bash
ssh user@your-server
sudo mv /tmp/balenciaga-admin /opt/
cd /opt/balenciaga-admin
sudo chmod +x deploy.sh
sudo ./deploy.sh
```

### Ручной деплой

1. **Установите зависимости:**
```bash
sudo apt update
sudo apt install -y docker.io docker-compose nginx certbot python3-certbot-nginx
```

2. **Настройте Docker:**
```bash
sudo systemctl start docker
sudo systemctl enable docker
```

3. **Скопируйте приложение:**
```bash
sudo mkdir -p /opt/balenciaga-admin
sudo cp -r ./* /opt/balenciaga-admin/
cd /opt/balenciaga-admin
```

4. **Запустите приложение:**
```bash
sudo docker-compose build
sudo docker-compose up -d
```

5. **Настройте nginx:**
```bash
sudo cp nginx.conf /etc/nginx/sites-available/balenciaga-admin
sudo ln -sf /etc/nginx/sites-available/balenciaga-admin /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo systemctl restart nginx
```

6. **Получите SSL сертификат:**
```bash
sudo certbot --nginx -d jsanfasfnkajfkasjkf.ru -d www.jsanfasfnkajfkasjkf.ru --non-interactive --agree-tos --email admin@jsanfasfnkajfkasjkf.ru
```

## 🔧 Управление

### Просмотр логов
```bash
cd /opt/balenciaga-admin
sudo docker-compose logs -f
```

### Перезапуск приложения
```bash
cd /opt/balenciaga-admin
sudo docker-compose restart
```

### Обновление приложения
```bash
cd /opt/balenciaga-admin
sudo docker-compose down
sudo docker-compose build --no-cache
sudo docker-compose up -d
```

## 🔒 Безопасность

- Приложение работает только по HTTPS
- Автоматическое обновление SSL сертификатов
- Безопасные заголовки nginx
- Изолированные Docker контейнеры

## 📊 Мониторинг

### Проверка статуса
```bash
sudo docker-compose ps
sudo systemctl status nginx
```

### Проверка SSL
```bash
sudo certbot certificates
```

## 🆘 Устранение неполадок

### Приложение не запускается
```bash
sudo docker-compose logs admin-app
```

### Проблемы с nginx
```bash
sudo nginx -t
sudo systemctl status nginx
```

### Проблемы с SSL
```bash
sudo certbot renew --dry-run
```

## 📝 Конфигурация

### Переменные окружения
- `NODE_ENV=production`
- `DATABASE_PATH=/app/databases/group_connections.db`

### Порт
- Приложение работает на порту 3000 внутри контейнера
- nginx проксирует с 80/443 на 3000

## 🌐 Доступ

После успешного деплоя админ-панель будет доступна по адресу:
**https://jsanfasfnkajfkasjkf.ru**
