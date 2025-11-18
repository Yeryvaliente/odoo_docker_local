#!/bin/bash
set -e

# Script de inicialización de PostgreSQL para desarrollo de Odoo

echo "Inicializando base de datos PostgreSQL para desarrollo..."

# Crear base de datos de desarrollo si no existe
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE odoo_dev_test OWNER odoo'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'odoo_dev_test');
EOSQL

echo "✅ Base de datos de desarrollo inicializada correctamente"