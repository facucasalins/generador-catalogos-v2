# Log de decisiones técnicas

Este archivo registra las decisiones importantes tomadas durante el diseño y desarrollo del sistema. **No es exhaustivo** — solo se registran las decisiones que afectan arquitectura, seguridad, o que en el futuro alguien va a preguntar "¿por qué se hizo así?".

Formato: una entrada por decisión. Fecha, contexto, opciones consideradas, decisión, racional.

---

## 2026-05-18 — Decisión #1: Cómo manejar imágenes de productos en v2

**Contexto**: en v1 había un flujo manual + Apps Script que llenaba una pestaña `Img Url` con URLs de imágenes, las expandía a 1 fila por SKU (`Img Url Expandido`), y las mergeaba a CRUCE vía BUSCARV. Investigando, descubrimos:

- La pestaña `Img Url` fue renombrada a `DEJAR DE USAR Img Url` hace tiempo
- El Apps Script `expandirSKUs()` está roto (busca una pestaña que ya no existe con ese nombre)
- Las imágenes en CRUCE se actualizan ocasionalmente de forma manual

**Opciones consideradas**:
- A) Reproducir el flujo manual en v2
- B) Arreglar el Apps Script y mantenerlo
- C) Eliminar todo el flujo, traer imágenes directo de la API de Tiendanube

**Decisión**: **C**. En v2 el módulo `inventario/tiendanube.py` trae las imágenes directamente de la API junto con el resto del producto.

**Racional**: La fuente de verdad de imágenes ES Tiendanube. Cualquier paso intermedio (sheets, scripts) es deuda técnica que se puede romper silenciosamente.

---

## 2026-05-18 — Decisión #2: Dónde viven los Sheets de cada cliente

**Contexto**: v2 propone que cada cliente tenga 3-4 Sheets (Inventario, Selección, Enriquecimiento, Feed-Output). Hay que decidir dónde se almacenan y quién es dueño.

**Opciones consideradas**:
- A) Todo en Drive de Agency Nusa, compartido con el cliente
- B) Todo en Drive del cliente, compartido con service account de Agency Nusa
- C) Híbrido

**Decisión**: **A — Drive de Agency Nusa**, estructura organizada en una carpeta "Generador de Catálogos" con subcarpetas por cliente.

**Racional**:
- Single source of truth bajo control de Agency Nusa
- Si el cliente se va, no se lleva los sheets
- Audit trail consistente bajo cuentas de Agency Nusa
- Permisos granulares: al cliente se le comparte solo SU carpeta

---

## 2026-05-18 — Decisión #3: Estrategia de migración Mora v1 → v2

**Contexto**: Mora v1 corre en producción y alimenta campañas activas. v2 es un sistema nuevo desde cero.

**Opciones consideradas**:
- A) Catálogos paralelos: crear catálogos Meta/TikTok nuevos para v2, correr ambos sistemas 7 días, validar, switch
- B) Migración en caliente: v2 escribe sobre los mismos catálogos que v1

**Decisión**: **A — Paralelo**.

**Detalles**:
- Cloudinary folder de v2: `morashop-v2/` (NO `morashop/`)
- Catálogos nuevos: `MoraShop V2 - *`
- Mantener todo lo viejo 30 días después del switch
- Solo después de 30 días limpios: borrar

**Racional**: las campañas activas no pueden sufrir downtime ni degradación de performance. Si v2 da peor resultado, switch reverso de 1 click.

---

## 2026-05-18 — Decisión #4: Estructura de bloques (5 en lugar de 4)

**Contexto**: durante el diseño se descubrió que el cliente necesita enriquecimiento de datos con LLM (tips, títulos cortos) antes de renderizar.

**Decisión**: agregar **Bloque 3: Enriquecimiento** como bloque opcional intermedio entre Selección y Estilo.

**Racional**: era necesario poder pasar productos por LLM con cache, fallback y prompts versionados. Hacerlo como bloque separado (en vez de embebido en Estilo) lo hace reusable, testeable, y opcional por cliente.

---

## Pendientes (decisiones aún no tomadas)

Ver `docs/ARCHITECTURE.md` sección 10. Cuando alguna se resuelve, se mueve acá.

Las más importantes pendientes:
- #4 Notificaciones (Slack/Discord/Email)
- #12 Dueño del Sheet maestro (Agency Nusa vs cliente) — resolver caso por caso
- #13-#17 Detalles del Bloque Enriquecimiento (cuando se llegue a implementarlo)
