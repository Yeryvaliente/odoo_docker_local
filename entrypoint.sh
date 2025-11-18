#!/bin/bash

set -e

echo "=== Odoo Development Environment Entrypoint ==="

if [ -v PASSWORD_FILE ]; then
    PASSWORD="$(< $PASSWORD_FILE)"
fi

# Set the postgres database host, port, user and password according to the environment
: ${HOST:=${DB_PORT_5432_TCP_ADDR:='postgres'}}
: ${PORT:=${DB_PORT_5432_TCP_PORT:=5432}}
: ${USER:=${DB_ENV_POSTGRES_USER:=${POSTGRES_USER:='odoo'}}}
: ${PASSWORD:=${DB_ENV_POSTGRES_PASSWORD:=${POSTGRES_PASSWORD:='odoo'}}}

DB_ARGS=()
function check_config() {
    param="$1"
    value="$2"
    if grep -q -E "^\s*\b${param}\b\s*=" "$ODOO_RC" ; then       
        value=$(grep -E "^\s*\b${param}\b\s*=" "$ODOO_RC" | cut -d "=" -f2- | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
    fi;
    DB_ARGS+=("--${param}")
    DB_ARGS+=("${value}")
}

check_config "db_host" "$HOST"
check_config "db_port" "$PORT"
check_config "db_user" "$USER"
check_config "db_password" "$PASSWORD"

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
wait-for-psql.py ${DB_ARGS[@]} --timeout=60

# Create logs directory if it doesn't exist
mkdir -p /var/log/odoo
touch /var/log/odoo/odoo.log

echo "Database connection arguments: ${DB_ARGS[*]}"
echo "Starting Odoo with config: $ODOO_RC"

case "$1" in
    -- | odoo)
        shift
        if [[ "$1" == "scaffold" ]] ; then
            echo "Running Odoo scaffold command..."
            exec odoo scaffold "$@"
        elif [[ "$1" == "shell" ]] ; then
            echo "Starting Odoo shell..."
            exec odoo shell "$@" "${DB_ARGS[@]}"
        elif [[ "$1" == "debug" ]] ; then
            echo "Starting Odoo in debug mode with debugpy..."
            shift
            exec python3 -m debugpy --listen 0.0.0.0:5678 /usr/bin/odoo "$@" "${DB_ARGS[@]}"
        elif [[ "$1" == "debug-wait" ]] ; then
            echo "Starting Odoo in debug mode with debugpy (waiting for client)..."
            shift
            exec python3 -m debugpy --listen 0.0.0.0:5678 --wait-for-client /usr/bin/odoo "$@" "${DB_ARGS[@]}"
        else
            echo "Starting Odoo server..."
            exec odoo "$@" "${DB_ARGS[@]}"
        fi
        ;;
    -*)
        echo "Starting Odoo with custom arguments..."
        exec odoo "$@" "${DB_ARGS[@]}"
        ;;
    bash | sh)
        echo "Starting interactive shell..."
        exec "$@"
        ;;
    *)
        echo "Executing command: $@"
        exec "$@"
esac

echo "Entrypoint execution failed"
exit 1