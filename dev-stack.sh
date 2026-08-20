#!/bin/bash
# ============================================
# 🚀 dev-stack.sh - Levanta el stack completo de desarrollo
# ============================================
# Uso:
#   ./dev-stack.sh          → Levanta backend (Odoo + API + Valkey + PostgreSQL)
#   ./dev-stack.sh full     → Levanta todo incluyendo el frontend Next.js
#   ./dev-stack.sh down     → Baja todo
#   ./dev-stack.sh logs     → Muestra logs de todos los servicios
#   ./dev-stack.sh logs api → Muestra logs solo del API
#   ./dev-stack.sh rebuild  → Reconstruye la imagen del API (si cambiaste deps)
#   ./dev-stack.sh status   → Muestra estado de los contenedores
# ============================================

set -e

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$SCRIPT_DIR"
FRONTEND_DIR="$SCRIPT_DIR/../web-mercado/frontend_2"
COMPOSE_FILE="$COMPOSE_DIR/docker-compose.yml"

print_header() {
    echo -e "\n${CYAN}============================================${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}============================================${NC}\n"
}

print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Función para verificar que Docker está corriendo
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        echo -e "${RED}❌ Docker no está corriendo. Inicia Docker Desktop primero.${NC}"
        exit 1
    fi
}

# Comando por defecto: up
CMD=${1:-up}

case $CMD in
    up)
        check_docker
        print_header "🐳 Levantando Backend Stack"
        
        cd "$COMPOSE_DIR"
        docker compose -f "$COMPOSE_FILE" up -d postgres valkey odoo odoo-api
        
        echo ""
        print_status "PostgreSQL    → localhost:5432"
        print_status "Valkey/Redis  → localhost:6379"
        print_status "Odoo          → http://localhost:8069"
        print_status "odoo-api      → http://localhost:3000"
        echo ""
        print_info "Para ver logs: ./dev-stack.sh logs"
        print_info "Para levantar el frontend: cd ../web-mercado/frontend_2 && npm run dev:lint-odoo"
        print_info "O usa: ./dev-stack.sh full"
        ;;

    full)
        check_docker
        print_header "🚀 Levantando Stack Completo (Backend + Frontend)"
        
        # Levanta backend
        cd "$COMPOSE_DIR"
        docker compose -f "$COMPOSE_FILE" up -d postgres valkey odoo odoo-api
        
        echo ""
        print_status "PostgreSQL    → localhost:5432"
        print_status "Valkey/Redis  → localhost:6379"
        print_status "Odoo          → http://localhost:8069"
        print_status "odoo-api      → http://localhost:3000"
        echo ""

        # Espera a que el API esté listo
        print_info "Esperando a que odoo-api esté listo..."
        sleep 5

        # Levanta frontend en background
        if [ -d "$FRONTEND_DIR" ]; then
            print_info "Levantando Next.js (web-mercado)..."
            cd "$FRONTEND_DIR"
            npm run dev:lint-odoo &
            FRONTEND_PID=$!
            echo ""
            print_status "Next.js       → http://localhost:3001"
            print_info "Frontend PID: $FRONTEND_PID"
            print_warning "Usa Ctrl+C para detener el frontend. Los containers siguen corriendo."
            wait $FRONTEND_PID
        else
            print_warning "No se encontró el directorio del frontend: $FRONTEND_DIR"
        fi
        ;;

    down)
        check_docker
        print_header "🛑 Bajando todos los servicios"
        cd "$COMPOSE_DIR"
        docker compose -f "$COMPOSE_FILE" down
        print_status "Todos los contenedores detenidos"
        ;;

    logs)
        SERVICE=${2:-}
        if [ -n "$SERVICE" ]; then
            case $SERVICE in
                api)    docker compose -f "$COMPOSE_FILE" logs -f odoo-api ;;
                odoo)   docker compose -f "$COMPOSE_FILE" logs -f odoo ;;
                db|pg)  docker compose -f "$COMPOSE_FILE" logs -f postgres ;;
                redis)  docker compose -f "$COMPOSE_FILE" logs -f valkey ;;
                *)      docker compose -f "$COMPOSE_FILE" logs -f "$SERVICE" ;;
            esac
        else
            cd "$COMPOSE_DIR"
            docker compose -f "$COMPOSE_FILE" logs -f postgres valkey odoo odoo-api
        fi
        ;;

    rebuild)
        check_docker
        print_header "🔧 Reconstruyendo odoo-api"
        print_info "Esto es necesario si cambiaste package.json o el Dockerfile"
        cd "$COMPOSE_DIR"
        
        # Elimina el volumen de node_modules para reinstalar
        docker compose -f "$COMPOSE_FILE" stop odoo-api
        docker volume rm odoo-dev-env_api_node_modules 2>/dev/null || true
        docker compose -f "$COMPOSE_FILE" build --no-cache odoo-api
        docker compose -f "$COMPOSE_FILE" up -d odoo-api
        
        print_status "odoo-api reconstruido y levantado"
        ;;

    restart-api)
        check_docker
        print_header "🔄 Reiniciando odoo-api"
        cd "$COMPOSE_DIR"
        docker compose -f "$COMPOSE_FILE" restart odoo-api
        print_status "odoo-api reiniciado"
        ;;

    status)
        check_docker
        print_header "📊 Estado del Stack"
        cd "$COMPOSE_DIR"
        docker compose -f "$COMPOSE_FILE" ps
        ;;

    *)
        echo -e "${YELLOW}Uso: $0 {up|full|down|logs [servicio]|rebuild|restart-api|status}${NC}"
        echo ""
        echo "  up           Levanta el backend (Odoo + API + Valkey + PostgreSQL)"
        echo "  full         Levanta backend + frontend Next.js"
        echo "  down         Baja todos los contenedores"
        echo "  logs [srv]   Muestra logs (srv: api, odoo, db, redis)"
        echo "  rebuild      Reconstruye la imagen del API"
        echo "  restart-api  Reinicia solo odoo-api"
        echo "  status       Muestra estado de contenedores"
        exit 1
        ;;
esac
