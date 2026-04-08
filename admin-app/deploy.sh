#!/bin/bash

# Простой скрипт деплоя Balenciaga Bot Admin Panel
# Domain: jsanfasfnkajfkasjkf.ru

set -e  # Останавливаем выполнение при ошибке

echo "🚀 Starting deployment of Balenciaga Bot Admin Panel..."

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
cat > /etc/systemd/system/balenciaga-admin.service << 'EOF'
[Unit]
Description=Balenciaga Bot Admin Panel
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/balenciaga-admin
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=10
Environment=NODE_ENV=production
Environment=DATABASE_PATH=/opt/databases/group_connections.db

[Install]
WantedBy=multi-user.target
EOF

echo "📁 Moving application to /opt/balenciaga-admin..."
# Создаем директорию и копируем файлы
mkdir -p /opt/balenciaga-admin
cp -r . /opt/balenciaga-admin/
chown -R www-data:www-data /opt/balenciaga-admin

echo "🌐 Configuring nginx..."
cat > /etc/nginx/sites-available/balenciaga-admin << 'EOF'
server {
    listen 80;
    server_name jsanfasfnkajfkasjkf.ru www.jsanfasfnkajfkasjkf.ru;

    access_log /var/log/nginx/balenciaga-admin.access.log;
    error_log /var/log/nginx/balenciaga-admin.error.log;

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
ln -sf /etc/nginx/sites-available/balenciaga-admin /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

echo "🚀 Starting services..."
systemctl daemon-reload
systemctl enable balenciaga-admin
systemctl start balenciaga-admin
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
echo "  sudo systemctl status balenciaga-admin    # Check status"
echo "  sudo systemctl restart balenciaga-admin  # Restart service"
echo "  sudo journalctl -u balenciaga-admin -f   # View logs"
echo ""
echo "📊 Current status:"
systemctl status balenciaga-admin --no-pager -l
