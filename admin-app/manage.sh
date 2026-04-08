#!/bin/bash

# Скрипт управления Balenciaga Admin Panel

case "$1" in
    start)
        echo "🚀 Starting Balenciaga Admin Panel..."
        systemctl start balenciaga-admin
        systemctl start nginx
        echo "✅ Service started"
        ;;
    stop)
        echo "🛑 Stopping Balenciaga Admin Panel..."
        systemctl stop balenciaga-admin
        systemctl stop nginx
        echo "✅ Service stopped"
        ;;
    restart)
        echo "🔄 Restarting Balenciaga Admin Panel..."
        systemctl restart balenciaga-admin
        systemctl restart nginx
        echo "✅ Service restarted"
        ;;
    status)
        echo "📊 Status of Balenciaga Admin Panel:"
        systemctl status balenciaga-admin
        systemctl status nginx
        ;;
    logs)
        echo "📋 Logs of Balenciaga Admin Panel:"
        journalctl -u balenciaga-admin -f
        ;;
    update)
        echo "🔄 Updating Balenciaga Admin Panel..."
        cd /opt/balenciaga-admin
        git pull 2>/dev/null || echo "⚠️  No git repository found"
        npm ci
        npm run build
        systemctl restart balenciaga-admin
        echo "✅ Update completed"
        ;;
    ssl-renew)
        echo "🔒 Renewing SSL certificate..."
        certbot renew
        systemctl reload nginx
        echo "✅ SSL renewal completed"
        ;;
    backup)
        echo "💾 Creating backup..."
        tar -czf /tmp/balenciaga-backup-$(date +%Y%m%d_%H%M%S).tar.gz /opt/balenciaga-admin
        echo "✅ Backup created in /tmp/"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|update|ssl-renew|backup}"
        echo ""
        echo "Commands:"
        echo "  start      - Start the service"
        echo "  stop       - Stop the service"
        echo "  restart    - Restart the service"
        echo "  status     - Show service status"
        echo "  logs       - Show service logs"
        echo "  update     - Update application"
        echo "  ssl-renew  - Renew SSL certificate"
        echo "  backup     - Create backup"
        exit 1
        ;;
esac
