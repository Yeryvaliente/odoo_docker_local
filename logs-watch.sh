#!/bin/bash

# Script para ver logs de Odoo en tiempo real

echo "=== Logs de Odoo en tiempo real ==="
echo "Presiona Ctrl+C para salir"
echo ""

# Función para limpiar al salir
cleanup() {
    echo ""
    echo "=== Cerrando visualización de logs ==="
    exit 0
}

trap cleanup SIGINT

# Mostrar logs en tiempo real
docker-compose logs -f odoo