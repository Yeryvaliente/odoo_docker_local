# Entorno de Desarrollo Odoo 18

Este es tu entorno de desarrollo personal de Odoo 18, completamente separado del repositorio principal. Incluye debugging, herramientas de desarrollo y configuraciones optimizadas.

## 🚀 Inicio Rápido

```bash
# Construir e iniciar el entorno
./dev.sh build
./dev.sh start

# Verificar que todo está funcionando
./dev.sh status
```

## 📋 Requisitos Previos

- Docker Desktop para Mac
- VS Code con las extensiones:
  - Python Debugger
  - Odoo (opcional)
  - XML Tools

## 🛠️ Comandos Disponibles

El script `dev.sh` incluye todos los comandos necesarios:

```bash
./dev.sh start           # Iniciar entorno completo
./dev.sh stop            # Detener entorno
./dev.sh restart         # Reiniciar servicios
./dev.sh build           # Construir/reconstruir contenedor Odoo
./dev.sh logs [servicio] # Ver logs (sin parámetro = todos)
./dev.sh shell           # Abrir shell en contenedor Odoo
./dev.sh odoo-shell      # Abrir shell de Odoo para BD
./dev.sh psql            # Conectar a PostgreSQL
./dev.sh debug           # Iniciar en modo debug (puerto 5678)
./dev.sh test [módulo]   # Ejecutar tests
./dev.sh clean           # Limpiar contenedores y volúmenes
./dev.sh status          # Ver estado de servicios
./dev.sh tools           # Iniciar con herramientas adicionales (pgAdmin)
```

## 🌐 Puntos de Acceso

Una vez iniciado el entorno:

- **Odoo**: http://odoo-dev.localhost o http://localhost:8069
- **Traefik Dashboard**: http://localhost:8080
- **PostgreSQL**: localhost:5432 (usuario: odoo, password: odoo)
- **pgAdmin** (con --tools): http://localhost:5050 (admin@localhost.com / admin)

## 🐛 Debugging con VS Code

### 1. Configuración Automática
El entorno incluye configuración predefinida de VS Code para debugging.

### 2. Iniciar en Modo Debug
```bash
./dev.sh debug
```

### 3. Conectar desde VS Code
1. Abre VS Code en esta carpeta
2. Ve a la pestaña "Run and Debug" (Ctrl+Shift+D)
3. Selecciona "Odoo: Attach to Container"
4. Haz clic en "Start Debugging" (F5)

### 4. Establecer Breakpoints
- Abre cualquier archivo Python de tus módulos
- Haz clic en el margen izquierdo para establecer breakpoints
- El debugger se detendrá cuando el código llegue a esos puntos

## 📁 Estructura de Directorios

```
odoo-dev-env/
├── docker-compose.yml      # Configuración principal
├── Dockerfile              # Imagen Odoo personalizada
├── odoo.conf               # Configuración Odoo optimizada para desarrollo
├── entrypoint.sh           # Script de inicio personalizado
├── wait-for-psql.py        # Utilidad para esperar PostgreSQL
├── dev.sh                  # Script principal de gestión
├── extra-addons/           # Tus módulos personales aquí
├── logs/                   # Logs de Odoo
├── init-scripts/           # Scripts de inicialización de BD
└── .vscode/                # Configuración VS Code
    ├── launch.json         # Configuración de debugging
    └── settings.json       # Configuración del workspace
```

## 🔧 Desarrollo de Módulos

### Crear un Nuevo Módulo
```bash
# Entrar al contenedor
./dev.sh shell

# Crear scaffold del módulo
odoo scaffold mi_modulo /mnt/extra-addons

# O desde fuera del contenedor
./dev.sh odoo-shell scaffold mi_modulo /mnt/extra-addons
```

### Instalar/Actualizar Módulos
```bash
# Método 1: Desde interfaz web
# Ve a Apps > Update Apps List > Buscar e instalar

# Método 2: Desde línea de comandos
./dev.sh shell
odoo -d odoo_dev -i mi_modulo                    # Instalar
odoo -d odoo_dev -u mi_modulo                    # Actualizar
odoo -d odoo_dev -i mi_modulo --dev=reload       # Con recarga automática
```

### Ejecutar Tests
```bash
./dev.sh test mi_modulo                          # Tests de un módulo específico
./dev.sh test                                    # Todos los tests
```

## 📊 Base de Datos

### Conectar a PostgreSQL
```bash
./dev.sh psql
```

### Crear Nueva Base de Datos
```bash
# Desde el shell de PostgreSQL
CREATE DATABASE mi_nueva_bd OWNER odoo;

# O usar pgAdmin (iniciando con ./dev.sh tools)
```

### Backup y Restore
```bash
# Backup
docker-compose exec postgres pg_dump -U odoo odoo_dev > backup.sql

# Restore
docker-compose exec -T postgres psql -U odoo -d nueva_bd < backup.sql
```

## 🔧 Configuraciones Especiales

### Variables de Entorno
Puedes modificar `docker-compose.yml` para añadir variables:

```yaml
environment:
  - ODOO_SESSION_REDIS=redis://redis:6379/1
  - CUSTOM_VAR=valor
```

### Módulos del Repositorio Principal
Los módulos del repositorio Odoocker están disponibles de solo lectura en `/mnt/repo-addons`.

### Configuración de Email
Por defecto configurado para desarrollo local. Para usar SMTP real, edita `odoo.conf`:

```ini
smtp_server = smtp.gmail.com
smtp_port = 587
smtp_ssl = True
smtp_user = tu_email@gmail.com
smtp_password = tu_app_password
```

## 🌐 Ngrok - Exposición a Internet

Ngrok permite exponer tu entorno de desarrollo local a internet de forma segura, útil para:

- Testing de webhooks
- Compartir demos con clientes
- Desarrollo de integraciones con servicios externos
- Testing desde dispositivos móviles

### Configuración

1. **Crear cuenta gratuita en ngrok:**
   - Ve a https://ngrok.com
   - Regístrate y obtén tu token de autenticación

2. **Configurar token:**
   ```bash
   # Copiar archivo de ejemplo
   cp .env.example .env

   # Editar .env y agregar tu token
   echo "NGROK_AUTH_TOKEN=tu_token_aqui" >> .env
   ```

3. **Iniciar con ngrok:**
   ```bash
   # Iniciar entorno con ngrok
   docker-compose --profile tools up ngrok

   # O usando el script
   ./dev.sh tools-ngrok
   ```

### Acceder a tu Odoo desde Internet

- **URL pública:** ngrok te dará una URL como `https://abc123.ngrok.io`
- **Dashboard ngrok:** http://localhost:4040 (para ver logs y métricas)
- **Odoo expuesto:** `https://abc123.ngrok.io` (apuntará a tu Odoo local)

### Comandos Útiles

```bash
# Ver logs de ngrok
docker-compose logs ngrok

# Reiniciar solo ngrok
docker-compose restart ngrok

# Detener ngrok
docker-compose stop ngrok
```

### ⚠️ Consideraciones de Seguridad

- **Desarrollo únicamente:** No uses ngrok en producción
- **Token seguro:** Nunca commits tu token de ngrok al repositorio
- **URLs temporales:** Las URLs gratuitas cambian cada reinicio
- **Rate limiting:** La versión gratuita tiene límites de uso

## 🚨 Troubleshooting

### Puerto ya en uso
```bash
# Verificar qué está usando el puerto
lsof -i :8069

# Detener otros servicios o cambiar puerto en docker-compose.yml
```

### Problemas de permisos
```bash
# Arreglar permisos de archivos
sudo chown -R $(id -u):$(id -g) ./extra-addons ./logs
```

### Limpiar entorno completamente
```bash
./dev.sh clean
docker system prune -a -f
```

### Logs detallados
```bash
./dev.sh logs odoo                               # Solo Odoo
./dev.sh logs postgres                           # Solo PostgreSQL
./dev.sh logs                                    # Todos los servicios
```

## 📝 Notas Adicionales

### Rendimiento
- El entorno está configurado para una sola instancia (workers=0) para facilitar debugging
- Para producción o testing de rendimiento, cambiar `workers` en `odoo.conf`

### Seguridad
- Usar solo para desarrollo local
- Cambiar passwords por defecto para cualquier uso no local

### Extensiones Recomendadas para VS Code
- Python Debugger
- Python
- XML Tools
- Docker
- GitLens
- Odoo Snippets

## 🆘 Soporte

Para problemas específicos:
1. Revisa los logs: `./dev.sh logs`
2. Verifica el estado: `./dev.sh status`
3. Reinicia servicios: `./dev.sh restart`
4. En último caso: `./dev.sh clean` y volver a construir

¡Happy coding! 🎉