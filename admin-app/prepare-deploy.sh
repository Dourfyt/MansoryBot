#!/bin/bash

# Script to prepare files for deployment
# Run this locally to create a deployment package

echo "📦 Preparing deployment package..."

# Create deployment directory
mkdir -p deployment-package

# Copy only necessary files
echo "📋 Copying application files..."
cp -r app deployment-package/
cp -r components deployment-package/
cp -r lib deployment-package/
cp middleware.ts deployment-package/
cp package.json deployment-package/
cp package-lock.json deployment-package/
cp tailwind.config.js deployment-package/
cp next.config.js deployment-package/
cp Dockerfile deployment-package/
cp docker-compose.yml deployment-package/
cp nginx.conf deployment-package/
cp deploy.sh deployment-package/
cp DEPLOY.md deployment-package/
cp .dockerignore deployment-package/

# Create archive
echo "🗜️ Creating deployment archive..."
tar -czf mansory-admin-deploy.tar.gz deployment-package/

# Cleanup
rm -rf deployment-package/

echo "✅ Deployment package created: mansory-admin-deploy.tar.gz"
echo "📤 Upload this file to your server and extract it"
echo "🚀 Then run: sudo ./deploy.sh"
