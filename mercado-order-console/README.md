# Consola de órdenes — Mercado v1_6

UI para **crear y editar órdenes Mercado v1_6** contra un Odoo de test, sin armar
curls a mano.

Implementa el contrato documentado en
`Odoocker/extra-addons/twonary_mercado/notes/v1_6/` (espejado en Confluence, space
**MAR**):

| Método | Ruta | Doc |
|---|---|---|
| `POST` | `/api/mercado/v1_6/combined-orders` | [create-order.md](https://persintel.atlassian.net/wiki/spaces/MAR/pages/5809733633) |
| `GET` | `/api/mercado/v1_6/combined-orders/{id}/edit` | [edit.md](https://persintel.atlassian.net/wiki/spaces/MAR/pages/5809766401) |
| `PATCH` | `/api/mercado/v1_6/combined-orders/{id}/edit` | idem |

## Qué hace

- **Crear**: arma el payload con desplegables poblados desde la BD — recipients,
  almacenes espejo de Comercial Progreso (bloque *esquina*), coverages de pymes
  (`businesses[]`) — y buscador con autocompletar sobre los productos publicados en
  Mercado (`product_template.two_mercado_ok`). Soporta los tres shapes del contrato:
  solo esquina, solo pymes (N negocios) y mixto.
- **Editar**: `GET` de las líneas editables en una tabla que agrega el parent RD y el
  child Comercial Progreso (la columna `SO` dice dónde vive cada línea), con `new_qty`
  y `return_destination` por línea. El `PATCH` manda **solo las líneas que cambiaste**.
- Muestra el **request y el response completos** con el código HTTP, así que también
  sirve para leer el contrato.
- **Historial de la sesión** con lo que fuiste mandando.

## Levantarlo

```bash
cd mercado-order-console
cp .env.example .env    # completá ODOO_API_KEY y DATABASE_URL
```

Con docker-compose, desde `odoo-dev-env/`:

```bash
docker compose --profile tools up -d mercado-console
# http://127.0.0.1:8900
```

En local, sin docker:

```bash
npm install
npm run build && npm start        # http://127.0.0.1:8900
npm run dev                       # Vite con hot reload en :5180, proxy en :8900
```

## Decisiones de diseño

**El token nunca baja al navegador.** El frontend habla con el proxy local y el proxy
pone el `Authorization: Bearer`. Por eso el compose publica el puerto solo en
`127.0.0.1`.

**Allowlist explícita de hosts** en `server/config.ts`. Esta consola **crea y edita
órdenes reales**: un host nuevo tiene que agregarse a mano, no alcanza con cambiar el
`.env`. Producción no está en la lista y no debe estarlo.

**La BD se lee en `SET TRANSACTION READ ONLY`.** Los cambios de negocio van por la API
HTTP, que corre las validaciones, la reserva y la contabilidad. Nunca por SQL.

**Sin librería de componentes.** CSS propio con variables y soporte de tema claro/oscuro.
Para 2 pantallas, una librería agrega peso al build y superficie de mantenimiento sin
mejorar el resultado.

## Gotchas del contrato

- **`order_id` es la clave de idempotencia** (`origin = MER-<order_id>`). Repetir uno
  devuelve `200` con `already_created: true` y solo re-chequea la reserva — no crea nada.
  Para una orden nueva, `order_id` nuevo.
- **La Esquina Caliente va por `mercado_warehouse_id`, no por `businesses[]`.** El
  controller rechaza una pyme mandada como esquina y viceversa. Por eso la consola
  excluye a la Esquina de los coverages de pymes.
- **`final_price` salió del contrato** en `18.0.0.28.0`: no se manda ni se valida.
- **`reason` es obligatorio en el PATCH.**
- Una orden v1_6 se edita **por esta API**, no por el wizard del backend: la UI de Odoo
  no pone el flag `mercado_v1_6` y caería en el parent-sync dropship de v1.
- `CP_COMPANY_ID` cambia por base: **472** en Odoocker test, 44 en las locales, 425 en el
  server de contabilidad. Va en el `.env`.
