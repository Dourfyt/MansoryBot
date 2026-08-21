#!/bin/bash

# Простой скрипт деплоя Mansory Bot Admin Panel
# Domain: jsanfasfnkajfkasjkf.ru

set -e  # Останавливаем выполнение при ошибке

echo "🚀 Starting deployment of Mansory Bot Admin Panel..."

# Проверяем, что запускаем от root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root (use sudo)"
    exit 1
fi

# Проверяем, что мы в правильной директории
if [ ! -f "package.json" ]; then
    echo "❌ Error: package.json not found. Please run this script from the admin-app directory"
    exit 1
fi

echo "📦 Updating system packages..."
apt update && apt upgrade -y

echo "🔧 Installing Node.js..."
# Устанавливаем Node.js 18
curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
apt install -y nodejs

echo "🌐 Installing nginx and certbot..."
apt install -y nginx certbot python3-certbot-nginx

echo "📦 Installing dependencies..."
npm ci

echo "🏗️ Building application..."
npm run build

echo "🔧 Creating systemd service..."
cat > /etc/systemd/system/mansory-admin.service << 'EOF'
[Unit]
Description=Mansory Bot Admin Panel
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/mansory-admin
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=10
Environment=NODE_ENV=production
Environment=DATABASE_PATH=/opt/databases/group_connections.db

[Install]
WantedBy=multi-user.target
EOF

echo "📁 Moving application to /opt/mansory-admin..."
# Создаем директорию и копируем файлы
mkdir -p /opt/mansory-admin
cp -r . /opt/mansory-admin/
chown -R www-data:www-data /opt/mansory-admin

echo "🌐 Configuring nginx..."
cat > /etc/nginx/sites-available/mansory-admin << 'EOF'
server {
    listen 80;
    server_name jsanfasfnkajfkasjkf.ru www.jsanfasfnkajfkasjkf.ru;

    access_log /var/log/nginx/mansory-admin.access.log;
    error_log /var/log/nginx/mansory-admin.error.log;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }

    location /_next/static/ {
        proxy_pass http://localhost:3000;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
EOF

# Включаем сайт
ln -sf /etc/nginx/sites-available/mansory-admin /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

echo "🚀 Starting services..."
systemctl daemon-reload
systemctl enable mansory-admin
systemctl start mansory-admin
systemctl restart nginx

echo "🔒 Obtaining SSL certificate..."
certbot --nginx -d jsanfasfnkajfkasjkf.ru -d www.jsanfasfnkajfkasjkf.ru --non-interactive --agree-tos --email admin@jsanfasfnkajfkasjkf.ru

echo "🔄 Setting up SSL renewal..."
(crontab -l 2>/dev/null; echo "0 12 * * * /usr/bin/certbot renew --quiet") | crontab -

echo "✅ Deployment completed successfully!"
echo ""
echo "🌍 Your admin panel is now available at: https://jsanfasfnkajfkasjkf.ru"
echo ""
echo "🔧 Management commands:"
echo "  sudo systemctl status mansory-admin    # Check status"
echo "  sudo systemctl restart mansory-admin  # Restart service"
echo "  sudo journalctl -u mansory-admin -f   # View logs"
echo ""
echo "📊 Current status:"
systemctl status mansory-admin --no-pager -l
