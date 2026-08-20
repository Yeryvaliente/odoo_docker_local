#!/bin/bash

# Odoo Development Environment Manager

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ---- Selección de entorno --------------------------------------------------
# Prefijo "custom" → stack del repo odoo-custom-addons (docker-compose.custom.yml:
#   proyecto odoo-custom, puertos +100, BD odoo_custom, contenedores odoo-custom*).
# Sin prefijo      → stack principal (Odoocker, docker-compose.yml).
MODE="main"
CMD_PREFIX=""
DB_NAME="odoo_dev"
HTTP_PORT="8069"
PG_PORT="5432"
VALKEY_PORT="6379"
DEBUG_PORT="5678"
DEBUG_FILES="-f docker-compose.yml -f docker-compose.debug.yml"
DEBUG_WAIT_FILES="-f docker-compose.yml -f docker-compose.debug-wait.yml"

if [ "$1" == "custom" ]; then
    shift
    MODE="custom"
    CMD_PREFIX="custom "
    DB_NAME="odoo_custom"
    HTTP_PORT="8169"
    PG_PORT="5532"
    VALKEY_PORT="6479"
    DEBUG_PORT="5778"
    export COMPOSE_FILE="docker-compose.custom.yml"
    DEBUG_FILES="-f docker-compose.custom.yml -f docker-compose.custom.debug.yml"
    DEBUG_WAIT_FILES="-f docker-compose.custom.yml -f docker-compose.custom.debug-wait.yml"
fi

show_help() {
    echo -e "${BLUE}Odoo Development Environment Manager${NC}"
    echo
    echo "Usage: $0 [custom] [COMMAND] [OPTIONS]"
    echo
    echo "  Prefijo 'custom' → repo odoo-custom-addons (puertos +100, BD odoo_custom)."
    echo "  Sin prefijo      → stack principal (Odoocker)."
    echo
    echo "Commands:"
    echo "  start           Start the development environment"
    echo "  stop            Stop the development environment"
    echo "  restart         Restart the development environment"
    echo "  build           Build/rebuild the Odoo container"
    echo "  logs            Show logs (add service name for specific service)"
    echo "  shell           Open a shell in the Odoo container"
    echo "  odoo-shell      Open Odoo shell for database operations"
    echo "  psql            Connect to PostgreSQL"
    echo "  debug           Start Odoo in debug mode (with debugpy)"
    echo "  debug-wait      Start Odoo in debug mode waiting for client"
    echo "  test            Run tests"
    echo "  clean           Clean up containers and volumes"
    echo "  status          Show status of services"
    echo "  tools           Start with additional tools (pgAdmin)"
    echo "  ngrok           Start with ngrok tunnel to expose Odoo"
    echo
    echo "Examples:"
    echo "  $0 start                    # Start all services (Odoocker)"
    echo "  $0 custom start             # Start del entorno odoo-custom-addons"
    echo "  $0 custom debug             # Debug del entorno odoo-custom-addons"
    echo "  $0 logs odoo                # Show Odoo logs"
    echo "  $0 shell                    # Open bash shell in Odoo container"
    echo "  $0 odoo-shell -d odoo_dev   # Open Odoo shell for specific database"
    echo "  $0 debug                    # Start in debug mode for VS Code"
    echo "  $0 debug-wait               # Start in debug mode waiting for client"
    echo "  $0 tools                    # Start with pgAdmin included"
    echo "  $0 ngrok                    # Start with ngrok tunnel"
}

start_services() {
    echo -e "${GREEN}🚀 Starting Odoo development environment...${NC}"
    
    # Asegurar que estamos en modo normal (sin debug)
    docker-compose stop odoo 2>/dev/null || true
    if [ "$MODE" == "custom" ] && ! docker image inspect odoo-dev-env-odoo:latest >/dev/null 2>&1; then
        echo -e "${RED}⚠️  Falta la imagen base 'odoo-dev-env-odoo:latest'.${NC}"
        echo -e "${YELLOW}    Constrúyela primero con: ./dev.sh build${NC}"
        exit 1
    fi
    docker-compose up -d
    
    echo -e "${GREEN}✅ Environment started!${NC}"
    echo -e "${YELLOW}📍 Access points:${NC}"
    echo -e "  • Odoo: http://localhost:${HTTP_PORT}"
    echo -e "  • PostgreSQL: localhost:${PG_PORT}"
    echo -e "  • Valkey: localhost:${VALKEY_PORT}"
    if [ "$MODE" == "custom" ]; then
        echo -e "${YELLOW}📦 Entorno: odoo-custom-addons (BD ${DB_NAME})${NC}"
    else
        echo -e "${GREEN}⚡ Queue Jobs: ENABLED (async processing)${NC}"
    fi
    echo -e "${BLUE}💡 Para debug usa: ./dev.sh ${CMD_PREFIX}debug${NC}"
}

start_with_tools() {
    if [ "$MODE" == "custom" ]; then
        echo -e "${RED}❌ 'tools' (pgAdmin) solo está disponible en el stack principal, no en custom.${NC}"
        exit 1
    fi
    echo -e "${GREEN}🚀 Starting Odoo development environment with tools...${NC}"
    docker-compose --profile tools up -d
    echo -e "${GREEN}✅ Environment with tools started!${NC}"
    echo -e "${YELLOW}📍 Access points:${NC}"
    echo "  - Odoo: http://odoo-dev.localhost (or http://localhost:8069)"
    echo "  - Traefik Dashboard: http://localhost:8080"
    echo "  - pgAdmin: http://localhost:5050 (admin@localhost.com / admin)"
    echo "  - PostgreSQL: localhost:5432"
}

start_with_ngrok() {
    if [ "$MODE" == "custom" ]; then
        echo -e "${RED}❌ 'ngrok' solo está disponible en el stack principal, no en custom.${NC}"
        exit 1
    fi
    echo -e "${GREEN}🚀 Starting Odoo development environment with ngrok...${NC}"

    # Verificar si existe archivo .env con NGROK_AUTH_TOKEN
    if [ ! -f ".env" ] || ! grep -q "NGROK_AUTH_TOKEN" .env; then
        echo -e "${RED}❌ Error: NGROK_AUTH_TOKEN not found in .env file${NC}"
        echo -e "${YELLOW}💡 Please:${NC}"
        echo "  1. Copy .env.example to .env: cp .env.example .env"
        echo "  2. Add your ngrok token: echo 'NGROK_AUTH_TOKEN=your_token_here' >> .env"
        echo "  3. Get token from: https://ngrok.com"
        exit 1
    fi

    docker-compose --profile tools up -d ngrok
    echo -e "${GREEN}✅ Environment with ngrok started!${NC}"
    echo -e "${YELLOW}📍 Access points:${NC}"
    echo "  - Odoo Local: http://odoo-dev.localhost (or http://localhost:8069)"
    echo "  - Ngrok Dashboard: http://localhost:4040"
    echo "  - PostgreSQL: localhost:5432"
    echo -e "${BLUE}🌐 Ngrok will provide a public URL for external access${NC}"
    echo -e "${BLUE}💡 Check ngrok dashboard or logs to see the public URL${NC}"
}

stop_services() {
    echo -e "${YELLOW}🛑 Stopping Odoo development environment...${NC}"
    docker-compose down
    echo -e "${GREEN}✅ Environment stopped!${NC}"
}

restart_services() {
    echo -e "${YELLOW}🔄 Restarting Odoo development environment...${NC}"
    docker-compose restart
    echo -e "${GREEN}✅ Environment restarted!${NC}"
}

build_container() {
    if [ "$MODE" == "custom" ]; then
        echo -e "${YELLOW}ℹ️  El stack custom reutiliza la imagen del stack principal (odoo-dev-env-odoo).${NC}"
        echo -e "${BLUE}🔨 Construyendo la imagen del stack principal...${NC}"
        docker-compose -f docker-compose.yml build odoo
    else
        echo -e "${BLUE}🔨 Building Odoo container...${NC}"
        docker-compose build --no-cache odoo
    fi
    echo -e "${GREEN}✅ Container built!${NC}"
}

show_logs() {
    if [ -n "$1" ]; then
        echo -e "${BLUE}📋 Showing logs for $1...${NC}"
        docker-compose logs -f "$1"
    else
        echo -e "${BLUE}📋 Showing all logs...${NC}"
        docker-compose logs -f
    fi
}

open_shell() {
    echo -e "${BLUE}🐚 Opening shell in Odoo container...${NC}"
    docker-compose exec odoo bash
}

open_odoo_shell() {
    echo -e "${BLUE}🐍 Opening Odoo shell...${NC}"
    if [ -n "$1" ]; then
        docker-compose exec odoo odoo shell "$@"
    else
        docker-compose exec odoo odoo shell -d "$DB_NAME"
    fi
}

connect_psql() {
    echo -e "${BLUE}🗄️ Connecting to PostgreSQL...${NC}"
    docker-compose exec postgres psql -U odoo -d "$DB_NAME"
}

start_debug() {
    echo -e "${BLUE}🐛 Activando modo debug y reiniciando Odoo...${NC}"
    echo -e "${YELLOW}💡 Debug server escuchará en puerto ${DEBUG_PORT}${NC}"
    echo -e "${RED}🚫 Queue Jobs: DISABLED (sync processing for debugging)${NC}"
    
    # Parar Odoo actual
    docker-compose stop odoo
    
    # Iniciar con debug
    docker-compose $DEBUG_FILES up -d odoo
    
    echo -e "${GREEN}✅ Modo debug activado!${NC}"
    echo -e "${YELLOW}📍 Odoo: http://localhost:${HTTP_PORT}${NC}"
    echo -e "${YELLOW}🐛 Debugger: localhost:${DEBUG_PORT}${NC}"
    echo -e "${BLUE}💡 Conecta VS Code debugger cuando necesites${NC}"
    echo -e "${RED}⚠️  Jobs se ejecutarán síncronamente en modo debug${NC}"
}

start_debug_wait() {
    echo -e "${BLUE}🐛 Starting Odoo in debug mode (waiting for client)...${NC}"
    echo -e "${YELLOW}💡 Debug server will wait for client connection on port ${DEBUG_PORT}${NC}"
    echo -e "${YELLOW}💡 Connect your VS Code debugger to localhost:${DEBUG_PORT} to continue${NC}"
    echo -e "${RED}🚫 Queue Jobs: DISABLED (sync processing for debugging)${NC}"
    docker-compose $DEBUG_WAIT_FILES up -d
    echo -e "${GREEN}✅ Debug wait mode started!${NC}"
    echo -e "${YELLOW}🐛 Waiting for debugger connection on localhost:${DEBUG_PORT}${NC}"
    echo -e "${RED}⚠️  Jobs se ejecutarán síncronamente en modo debug${NC}"
}

run_tests() {
    echo -e "${BLUE}🧪 Running tests...${NC}"
    if [ -n "$1" ]; then
        docker-compose exec odoo odoo -d "$DB_NAME" --test-enable --stop-after-init -i "$1"
    else
        docker-compose exec odoo odoo -d "$DB_NAME" --test-enable --stop-after-init
    fi
}

clean_environment() {
    echo -e "${RED}🧹 Cleaning up environment...${NC}"
    read -p "This will remove all containers and volumes. Are you sure? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker-compose down -v --remove-orphans
        docker system prune -f
        echo -e "${GREEN}✅ Environment cleaned!${NC}"
    else
        echo -e "${YELLOW}❌ Cleanup cancelled${NC}"
    fi
}

show_status() {
    echo -e "${BLUE}📊 Service Status:${NC}"
    docker-compose ps
}

# Main command processing
case "$1" in
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    build)
        build_container
        ;;
    logs)
        shift
        show_logs "$@"
        ;;
    shell)
        open_shell
        ;;
    odoo-shell)
        shift
        open_odoo_shell "$@"
        ;;
    psql)
        connect_psql
        ;;
    debug)
        start_debug
        ;;
    debug-wait)
        start_debug_wait
        ;;
    test)
        shift
        run_tests "$@"
        ;;
    clean)
        clean_environment
        ;;
    status)
        show_status
        ;;
    tools)
        start_with_tools
        ;;
    ngrok)
        start_with_ngrok
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}❌ Unknown command: $1${NC}"
        echo
        show_help
        exit 1
        ;;
esac