#!/bin/bash

# Script para instalar dependencias Python en el contenedor corriendo

echo "📦 Installing Python dependencies in running container..."

# Nombre del contenedor (ajusta si es necesario)
CONTAINER_NAME="odoo-dev"

# Verificar si el contenedor está corriendo
if ! docker ps | grep -q $CONTAINER_NAME; then
    echo "❌ Container $CONTAINER_NAME is not running!"
    echo "Starting container..."
    cd /Users/yery/trabajo/odoo18-local/odoo-dev-env
    docker-compose up -d odoo
    sleep 5
fi

echo "📥 Installing numpy..."
docker exec -u root $CONTAINER_NAME pip3 install --break-system-packages numpy>=1.24.0

echo "📥 Installing google-genai..."
docker exec -u root $CONTAINER_NAME pip3 install --break-system-packages google-genai>=0.3.0

echo "✅ Dependencies installed successfully!"
echo "🔄 Restarting Odoo..."
docker restart $CONTAINER_NAME

echo "✅ Done! Wait a few seconds for Odoo to start..."
