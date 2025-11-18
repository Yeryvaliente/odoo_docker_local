# 📦 Instalación de Dependencias para Product Search Embeddings

## 🚀 Opción 1: Instalación Rápida (Recomendado)

Instala las dependencias en el contenedor corriendo sin reconstruir:

```bash
cd /Users/yery/trabajo/odoo18-local/odoo-dev-env
./install-deps.sh
```

Este script:
- ✅ Instala `numpy>=1.24.0`
- ✅ Instala `google-generativeai>=0.3.0`
- ✅ Reinicia Odoo automáticamente
- ⏱️ Tiempo: ~2-3 minutos

## 🔨 Opción 2: Reconstrucción Completa

Si prefieres reconstruir el contenedor con las dependencias incluidas:

```bash
cd /Users/yery/trabajo/odoo18-local/odoo-dev-env
./rebuild.sh
```

Este script:
- 🛑 Detiene los contenedores
- 🏗️ Reconstruye la imagen de Docker
- 🚀 Levanta los contenedores
- 📋 Muestra los logs
- ⏱️ Tiempo: ~10-15 minutos

## 📋 Dependencias Instaladas

### Core
- `pyTelegramBotAPI==4.29.1`
- `packaging`
- `sentry-sdk==2.37.0`
- `pikepdf`

### Debugging
- `debugpy`
- `ipdb`
- `pudb`

### Development
- `watchdog`
- `pytest`
- `pytest-odoo`
- `coverage`

### Product Search Embeddings
- `numpy>=1.24.0` - Para operaciones matemáticas y vectores
- `google-generativeai>=0.3.0` - Para generar embeddings con Gemini

## 🧪 Verificar Instalación

Después de instalar, verifica que las dependencias estén disponibles:

```bash
# Entrar al contenedor
docker exec -it odoo-dev-env-odoo-1 bash

# Verificar numpy
python3 -c "import numpy; print(f'numpy {numpy.__version__}')"

# Verificar google-generativeai
python3 -c "import google.generativeai as genai; print('google-generativeai OK')"

# Salir del contenedor
exit
```

## 📦 Instalar Módulos en Odoo

Una vez instaladas las dependencias:

1. **Actualizar lista de apps**:
   - Ve a Apps → Update Apps List

2. **Instalar field_vector**:
   - Busca "field_vector"
   - Instala el módulo

3. **Instalar twonary_product_search_embeddings**:
   - Busca "Twonary Product Search Embeddings"
   - Instala el módulo

## 🔍 Troubleshooting

### Error: "Container not found"

Si obtienes un error de contenedor no encontrado:

```bash
# Verificar nombre del contenedor
docker ps

# Editar install-deps.sh y cambiar CONTAINER_NAME
nano install-deps.sh
```

### Error: "Permission denied"

Si tienes problemas de permisos:

```bash
# Dar permisos de ejecución
chmod +x install-deps.sh rebuild.sh
```

### Dependencias no se instalan

Si las dependencias no se instalan correctamente:

```bash
# Instalar manualmente
docker exec -u root odoo-dev-env-odoo-1 pip3 install --break-system-packages numpy google-generativeai
```

## 📝 Notas

- Las dependencias se instalan con `--break-system-packages` porque Odoo usa el Python del sistema
- Se recomienda usar `install-deps.sh` para desarrollo rápido
- Usa `rebuild.sh` para ambientes de producción o cuando actualices el Dockerfile

## 🆘 Soporte

Si tienes problemas, revisa:
- Los logs de Docker: `docker-compose logs -f odoo`
- Los logs de Odoo: `tail -f logs/odoo.log`
- El estado del contenedor: `docker ps -a`
