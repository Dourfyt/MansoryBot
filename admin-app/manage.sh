#!/bin/bash

# Скрипт управления Mansory Admin Panel

case "$1" in
    start)
        echo "🚀 Starting Mansory Admin Panel..."
        systemctl start mansory-admin
        systemctl start nginx
        echo "✅ Service started"
        ;;
    stop)
        echo "🛑 Stopping Mansory Admin Panel..."
        systemctl stop mansory-admin
        systemctl stop nginx
        echo "✅ Service stopped"
        ;;
    restart)
        echo "🔄 Restarting Mansory Admin Panel..."
        systemctl restart mansory-admin
        systemctl restart nginx
        echo "✅ Service restarted"
        ;;
    status)
        echo "📊 Status of Mansory Admin Panel:"
        systemctl status mansory-admin
        systemctl status nginx
        ;;
    logs)
        echo "📋 Logs of Mansory Admin Panel:"
        journalctl -u mansory-admin -f
        ;;
    update)
        echo "🔄 Updating Mansory Admin Panel..."
        cd /opt/mansory-admin
        git pull 2>/dev/null || echo "⚠️  No git repository found"
        npm ci
        npm run build
        systemctl restart mansory-admin
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
        tar -czf /tmp/mansory-backup-$(date +%Y%m%d_%H%M%S).tar.gz /opt/mansory-admin
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
