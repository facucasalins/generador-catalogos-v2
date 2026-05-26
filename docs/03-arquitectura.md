# 03 - Arquitectura del sistema

> Cómo está construido el sistema por dentro. Útil para debug y para entender por qué algo hace lo que hace.

---

## Vista de 30.000 pies

El sistema es un **pipeline en 5 bloques** que corre 1 vez al día (cron) por cliente, en GitHub Actions, leyendo Tiendanube y escribiendo a Google Sheets:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Tiendanube  │     │   GitHub     │     │ Google Sheets│
│ (cliente)    │ ──> │  Actions     │ ──> │  - feed Meta │
│              │     │  (pipeline)  │     │  - feed TikT │
└──────────────┘     └──────────────┘     └──────────────┘
                            │
                            ├──> Cloudinary (placas PNG)
                            │
                            ├──> Gemini API (descripciones)
                            │
                            └──> Telegram (notificación)
```

Cada cliente tiene su propio pipeline corriendo en paralelo, independiente. Si Mora falla, Shark sigue corriendo.

---

## Los 5 bloques

Cada bloque hace una cosa y se la pasa al siguiente. Si uno falla, en general el pipeline falla y avisa por Telegram con el bloque culpable.

### Bloque 1 — Inventario

**Qué hace**: trae todos los productos del cliente desde Tiendanube y los vuelca al sheet "Inventario".

**Inputs**: credenciales TN del cliente (secrets de GitHub).

**Outputs**: pestaña "Inventario" del sheet con N filas (~4260 para Mora actualmente), una por producto.

**Detalles relevantes**:
- Reintento automático con 30s de espera si TN falla (Fase H). Si falla 2 veces, avisa por Telegram con bloque "Bloque 1 (Inventario - TN no responde)".
- Trae **todos** los productos del cliente, no solo los marcados.

**Código**: `src/inventario/tiendanube.py`

### Bloque 2 — Selección

**Qué hace**: lee la pestaña "Selección" del sheet para saber **qué SKUs hay que generar** y con qué template.

**Inputs**: sheet "Selección" del cliente, con columnas `sku | generar | template | prioridad | notas`.

**Outputs**: lista de `DecisionSeleccion` (objetos en memoria) con los SKUs marcados con `generar=TRUE`.

**Detalles relevantes**:
- Si un SKU está marcado pero no existe en el inventario (Bloque 1), se saltea con warning.
- La columna `template` decide qué archivo HTML usar para ese SKU.

**Código**: `src/seleccion/sheet_manual.py`

### Bloque 3 — Enriquecimiento (Gemini)

**Qué hace**: para cada SKU seleccionado, llama a **Gemini 2.5 Flash** y le pide que genere:
- Un título corto (60 chars max)
- Una descripción corta (200 chars max)
- 3 tips de uso (40 chars cada uno)

**Inputs**: lista de productos con nombre y descripción crudos.

**Outputs**: producto con `enriquecimiento` cargado, listo para usar en placas y feeds.

**Detalles relevantes**:
- Tiene **cache** en una pestaña del sheet de Inventario llamada "Enriquecimiento". Si un SKU ya tiene enriquecimiento generado en una corrida anterior con los mismos datos crudos, se reusa (sin volver a llamar a Gemini, que es caro y lento).
- Si Gemini falla en un SKU, **ese SKU no entra al feed**. El resto sigue.
- El prompt está en `src/enriquecimiento/gemini.py`. Tono argentino, voseo, sin clichés.

**Código**: `src/enriquecimiento/gemini.py` + `src/enriquecimiento/sheet_cache.py`

### Bloque 4 — Estilo (placas)

**Qué hace**: renderiza las placas PNG con Playwright + HTML.

**Inputs**: productos seleccionados + sus enriquecimientos.

**Outputs**: archivos PNG en `/tmp/placas/<cliente>/`.

**Detalles relevantes**:
- **Loop multi-aspect-ratio** (Fase H activada): por cada SKU se generan 2 placas:
  - **4:5** (1080×1350) usando `<template>.html` → para Meta
  - **9:16** (1080×1920) usando `<template>_tiktok.html` → para TikTok
- **Diff inteligente**: cada placa tiene un hash basado en (precio + nombre + descripción + URL imagen + template HTML + aspect_ratio). Si el hash matchea con el histórico → reusa la URL vieja sin renderizar. Si cambia algo → regenera solo esa placa.
- El diseño visual viene 100% del archivo `.html` (ver `02-diseno-templates.md`).

**Código**: `src/estilo/playwright_html.py`

### Bloque 5 — Distribución

Tiene 2 sub-bloques:

#### 5.1) Storage

**Qué hace**: sube las placas generadas a Cloudinary.

**Inputs**: archivos PNG locales.

**Outputs**: URLs públicas de Cloudinary (`https://res.cloudinary.com/.../folder/SKU.png`).

**Detalles relevantes**:
- Folder en Cloudinary configurable por cliente (`folder: morashop` en el yaml).
- La placa 9:16 lleva sufijo en el `public_id`: `morashop/SKU_9x16` (la 4:5 va sin sufijo, retrocompat).
- **Limpieza de huérfanos** (Fase H): SKUs que estaban en el historial pero ya no se generan → se borran de Cloudinary automáticamente.

**Código**: `src/distribucion/storage/cloudinary.py`

#### 5.2) Destinos (feeds)

**Qué hace**: escribe los feeds finales en las pestañas del sheet Feed-Output.

**Inputs**: productos + URLs de placas + decisiones de selección.

**Outputs**: pestañas `Meta_default`, `Meta_electro` (con URLs 4:5) + `TikTok_default`, `TikTok_electro` (con URLs 9:16).

**Detalles relevantes**:
- Cada destino **agrupa por template** (cada template genera su propia pestaña).
- Cada destino **filtra por aspect_ratio**: Meta usa solo placas 4:5, TikTok usa solo 9:16.
- El formato (columnas) lo define cada destino:
  - **Meta**: `id, title, description, availability, condition, price, link, image_link, brand`
  - **TikTok**: `sku_id, title, description, ...` (similar pero la primera columna se llama `sku_id`)

**Código**: `src/distribucion/destinos/meta_catalog.py`, `tiktok_catalog.py`, `_common.py`

---

## Estructura del repo

```
generador-catalogos-v2/
├── .github/
│   └── workflows/
│       ├── morashop-v2.yml          ← workflow de Mora (cron diario)
│       ├── shark.yml                ← workflow de Shark
│       ├── juanita.yml              ← workflow de Juanita
│       └── ci.yml                   ← CI: corre pytest en cada push
│
├── clients/                         ← CONFIGURACIÓN POR CLIENTE
│   ├── morashop/
│   │   ├── pipeline.yaml            ← qué hace el pipeline para este cliente
│   │   └── templates/               ← HTMLs de las placas
│   │       ├── default.html
│   │       ├── default_tiktok.html
│   │       ├── electro.html
│   │       └── electro_tiktok.html
│   │
│   ├── shark/                       ← (futuro) mismo formato
│   └── ...
│
├── src/                             ← CÓDIGO DEL SISTEMA (compartido entre clientes)
│   ├── cli.py                       ← punto de entrada: lee yaml, orquesta bloques
│   ├── core/
│   │   ├── modelo_datos.py          ← dataclasses: Producto, Placa, etc.
│   │   ├── sheets_client.py         ← wrapper de Google Sheets API
│   │   └── ...
│   ├── inventario/
│   │   └── tiendanube.py            ← Bloque 1
│   ├── seleccion/
│   │   └── sheet_manual.py          ← Bloque 2
│   ├── enriquecimiento/
│   │   ├── gemini.py                ← Bloque 3
│   │   └── sheet_cache.py
│   ├── estilo/
│   │   └── playwright_html.py       ← Bloque 4
│   └── distribucion/
│       ├── storage/
│       │   ├── base.py              ← interfaz abstracta
│       │   └── cloudinary.py        ← Bloque 5.1
│       ├── destinos/
│       │   ├── _common.py
│       │   ├── meta_catalog.py      ← Bloque 5.2 Meta
│       │   └── tiktok_catalog.py    ← Bloque 5.2 TikTok
│       ├── historial.py             ← diff inteligente
│       └── telegram_notifier.py
│
├── tests/                           ← tests automáticos (147 tests, 100% pass)
├── scripts/
│   └── preview_template.py          ← preview local de templates
├── docs/                            ← esta carpeta
├── requirements.txt
└── README.md
```

---

## Filosofía: lo único que cambia por cliente es `clients/`

**El código en `src/` es 100% reusado entre todos los clientes.** Lo único que cambia por cliente es:

1. Su carpeta `clients/<cliente>/` (pipeline.yaml + templates)
2. Su workflow YAML en `.github/workflows/<cliente>.yml`
3. Sus secrets en GitHub (`<CLIENTE>_TIENDANUBE_STORE_ID`, `_TOKEN`)
4. Sus sheets en Google Drive (Inventario / Selección / Feed-Output)
5. Su folder en Cloudinary (auto-creado)

Esto significa que **podés agregar 10 clientes sin tocar ni una línea de Python**. Si tenés que tocar `src/` para sumar un cliente, algo está mal pensado (probablemente el cliente tiene un requerimiento que no encaja con el sistema actual y hay que evolucionarlo, no parchearlo).

---

## Flujo de datos: tour por una corrida

Imaginá que un cliente "Shark" tiene 50 SKUs marcados. Esto pasa cuando corre el workflow a las 06:00 ART:

```
1. Workflow arranca, GitHub levanta runner Ubuntu
   ├─ Instala Python + dependencias
   ├─ Cachea/instala Chromium (Playwright)
   └─ Inyecta secrets como env vars

2. python -m src.cli --cliente=shark
   ├─ Lee clients/shark/pipeline.yaml
   ├─ Construye el pipeline según el yaml

3. BLOQUE 1: TN → sheet Inventario
   ├─ GET https://api.tiendanube.com/v1/{store_id}/products
   ├─ Convierte a lista de Producto
   └─ Escribe sheet "Inventario" (~2000 filas)

4. BLOQUE 2: sheet Selección → lista de SKUs
   ├─ Lee sheet "Selección"
   ├─ Filtra solo los marcados generar=TRUE
   └─ Lista de 50 DecisionSeleccion

5. BLOQUE 3: Gemini enriquece
   ├─ Lee cache "Enriquecimiento" del sheet Inventario
   ├─ Para los SKUs no cacheados: GEMINI API (50 calls paralelas)
   ├─ Escribe cache
   └─ Productos con enriquecimiento listo

6. BLOQUE 4: Estilo
   ├─ Para cada aspect_ratio (4:5 y 9:16):
   │  ├─ Lee historial: ¿qué cambió respecto a ayer?
   │  ├─ Solo los cambiados se mandan a Playwright
   │  ├─ Playwright renderiza HTML → PNG
   │  └─ ~100 PNGs en /tmp/placas/shark/ (50 × 2)

7. BLOQUE 5.1: Cloudinary
   ├─ Solo sube los PNGs nuevos
   ├─ Las URLs viejas se reusan del historial
   └─ Actualiza pestaña "Historial_Placas"
   └─ Limpia SKUs huérfanos (los que ya no están)

8. BLOQUE 5.2: Feeds → Sheet Feed-Output
   ├─ Agrupa por template
   ├─ Para cada destino (Meta, TikTok):
   │  └─ Para cada template:
   │     └─ Escribe pestaña (ej: "Meta_default" con 50 filas)

9. Telegram notifica
   └─ "✅ shark OK | 50 SKUs | 8 regen | 92 reus | 2m 14s"

10. Workflow termina
    └─ Upload artifact con todos los PNGs (para validación visual)
```

Total: 5-15 minutos según cantidad de SKUs nuevos.

---

## Diff inteligente: cómo decide qué regenerar

Una de las cosas más importantes del sistema es **no regenerar lo que no cambió**. Esto ahorra tiempo, plata de Cloudinary, y llamadas a Gemini.

### Cómo funciona

Para cada combinación (SKU, aspect_ratio), el sistema calcula un **hash SHA-256** sobre:
- `producto.sku`
- `template_a_usar` (incluye sufijo `_tiktok` si aplica)
- `aspect_ratio`
- `precio_lista`
- `precio_promocional`
- `producto.nombre`
- `producto.descripcion`
- `producto.marca`
- `producto.imagen_url`
- **El contenido HTML del template** (si cambiás el HTML, regenera)

Si el hash matchea con el histórico → reusa la URL vieja sin renderizar.

### Implicancias

- **Cambias el HTML del template**: todas las placas que usan ese template se regeneran al próximo run.
- **Cambia el precio de 1 SKU**: solo esa placa se regenera. El resto reusa.
- **Cliente agrega 10 productos nuevos**: solo esos 10 se renderizan (× 2 aspect_ratios).
- **Cliente cambia foto de 1 producto en TN**: esa placa se regenera al detectar el cambio.

### Dónde vive el historial

En cada cliente, en su sheet de **Inventario**, hay una pestaña llamada `Historial_Placas` con columnas:

```
sku | template | aspect_ratio | precio_lista | precio_promo | url_cloudinary | fecha_render | hash_render
```

Si querés **forzar regeneración total** de un cliente (ej: cambiaste el folder de Cloudinary), borrá las filas de esta pestaña (dejá solo el header). Próximo run regenera todo.

---

## Decisiones de diseño importantes

### ¿Por qué Google Sheets como destino final y no API directa de Meta?

Porque:
1. Es **visualmente auditable**: vos abrís el sheet y ves los feeds reales. Si está mal, lo ves al instante.
2. Meta/TikTok aceptan **CSV publicado vía URL** como source de catálogo. Sheets te da eso gratis (Publish to web → CSV).
3. Si Meta cambia su API, no rompe nada. El sheet sigue siendo el sheet.
4. Si necesitás otro destino mañana (Mercado Libre, Google Shopping), agregás otro `tipo: ` en el yaml. El sheet es polivalente.

### ¿Por qué Cloudinary y no S3 / Cloudflare R2 / etc.?

- **Free tier generoso** (25 créditos/mes, suficiente para Mora completa)
- **URLs públicas instantáneas** sin configurar
- Tiene **CDN global incluido**
- Si te quedás corto, **plan pago razonable** (USD 89/mes Plus)

Pero el código está abstracto detrás de `StorageBackend`. Si querés migrar a S3, se hace agregando un módulo nuevo, no reescribiendo todo.

### ¿Por qué Playwright + HTML y no Pillow / SVG / Figma API?

- **HTML+CSS es lo más expresivo y conocido**. Cualquier diseñador puede iterar templates sin aprender una API rara.
- **Iteración rápida**: editás HTML, le sacás screenshot, no hay compilación.
- **Versionable**: el HTML va en Git como cualquier código, podés ver historia de cambios.
- **Playwright** te da un Chromium real, sin sorpresas de "esto no se renderiza igual que en el browser".

Trade-off: cada placa pesa unos KBs más que SVG/Pillow porque es PNG generado vía screenshot. No es problema en la escala actual.

### ¿Por qué Gemini y no GPT / Claude API?

- **Free tier muy generoso** (varios miles de calls/día)
- **Gemini 2.5 Flash es rapidísimo** (~1s por call)
- **Calidad suficiente** para títulos cortos y descripciones de producto en español argentino

Igual que con storage, el código está abstracto. Si querés cambiar a Claude o GPT, se hace agregando otro módulo `src/enriquecimiento/<proveedor>.py`.

---

## Cosas que vienen / pendientes

- **Conectar Meta + TikTok a las pestañas** (manual, una vez por cliente)
- **Validación paralela v1 vs v2 por 7 días** (Mora) antes de switch
- **Templates 9:16 mejorados** (los actuales son portes 4:5)
- **Bug "sin promo"**: visualmente raro cuando precio_lista == precio_promo
- **Soporte Shopify** como fuente alternativa (no urgente)
- **Más destinos**: Google Shopping, Mercado Libre (no urgente)

---

## Tests

Hay **147 tests automáticos** (`tests/`). El CI los corre en cada push. Si rompés algo, GitHub te avisa antes de mergear.

Para correrlos local:

```bash
pytest tests/ -v
```

Para correr solo los de un módulo:

```bash
pytest tests/test_cloudinary.py -v
```

---

## Próximos pasos

- **Agregar un cliente nuevo**: `01-quickstart-nuevo-cliente.md`
- **Diseñar templates**: `02-diseno-templates.md`
- **Algo no anda**: `04-troubleshooting.md`
