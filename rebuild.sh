#!/bin/bash

# Script para reconstruir el contenedor de Odoo con las nuevas dependencias

echo "🔨 Rebuilding Odoo container with new dependencies..."

# Detener contenedores si están corriendo
echo "📦 Stopping containers..."
docker-compose -f docker-compose.yml down

# Reconstruir imagen sin cache
echo "🏗️  Building new image (this may take a while)..."
docker-compose -f docker-compose.yml build --no-cache odoo

# Levantar contenedores
echo "🚀 Starting containers..."
docker-compose -f docker-compose.yml up -d

# Mostrar logs
echo "📋 Showing logs (Ctrl+C to exit)..."
docker-compose -f docker-compose.yml logs -f odoo

echo "✅ Done!"
