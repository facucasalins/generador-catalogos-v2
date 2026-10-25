# Panel de catálogos

Panel web para operar el generador de catálogos sin tocar GitHub, YAML ni Sheets.
Vive en `catalogos.agencynusa.com` (Vercel, proyecto con *Root Directory* = `panel`).

Diseño completo y etapas: doc "Panel de Catálogos — Diseño v1".

## Qué hace hoy (Etapa 0, solo lectura)

- **Resumen**: estado de cada cliente, última corrida y alertas (SKUs que no van a salir,
  templates sin bloque META, columnas de Selección que apuntan a templates borrados).
- **Productos**: inventario con lo tildado en Selección, por plataforma.
- **Placas**: las placas vigentes (pestaña `Historial_Placas`), en mesa de luz.
- **Templates**: preview en vivo de cada template con productos reales, mismos precios
  que el pipeline. Detecta variables inexistentes.
- **Corridas**: historial del workflow del cliente en GitHub Actions.

## De dónde salen los datos

| Dato | Fuente |
| --- | --- |
| Clientes, config y templates | `clients/*/pipeline.yaml` y `clients/*/templates/*.html`, empaquetados en el build por `scripts/sync-clientes.mjs` |
| Inventario, enriquecimiento, historial | Sheet Inventario de cada cliente |
| Selección | Sheet Selección de cada cliente |
| Precios de evento | Planilla de `precios_override` (si el cliente la tiene) |
| Corridas | API de GitHub Actions |
| Usuarios | `PANEL_ADMIN_EMAILS` + pestaña `Usuarios` de la sheet *Panel de Catálogos* |

Todo pasa por `src/lib/datos/`: cuando se migre a Supabase se reescribe esa capa.

## Preview = render real

`src/lib/render/variables.ts` es un port 1:1 de `_construir_variables` en
`src/estilo/playwright_html.py`. `tests/variables.test.ts` corre los mismos casos por
las dos implementaciones (incluye el redondeo al par de Python) y en CI falla si difieren.
**Si cambiás la lógica de precios en Python, replicala acá.**

## Variables de entorno (Vercel)

| Variable | Para qué |
| --- | --- |
| `AUTH_SECRET` | Firma de la sesión (Auth.js) |
| `AUTH_GOOGLE_ID`, `AUTH_GOOGLE_SECRET` | Cliente OAuth de Google para el login |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | La misma cuenta de servicio del pipeline (`placas-bot`) |
| `GITHUB_TOKEN` | Token fine-grained: Actions (read) para corridas; más adelante Contents y Actions (write) |
| `PANEL_ADMIN_EMAILS` | Emails que siempre entran como admin, separados por coma |
| `PANEL_SHEET_ID` | ID de la sheet *Panel de Catálogos* (pestaña `Usuarios`) |

## Desarrollo local

```bash
cd panel
npm install
PANEL_DEMO=1 AUTH_SECRET=local npm run dev   # datos de ejemplo, sin login
npm test                                     # incluye paridad con Python
```
