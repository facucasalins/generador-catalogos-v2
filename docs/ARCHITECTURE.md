# Generador de Catálogos — Arquitectura v2

> Documento de diseño. Versión inicial. Última actualización: 15-may-2026.

---

## 1. Para qué existe este sistema

Generar automáticamente **placas publicitarias** (imágenes de producto con precio, descuento y branding) para los catálogos de Meta Ads y TikTok Ads de los clientes de Agency Nusa, leyendo datos de sus tiendas y publicando feeds actualizados sin intervención humana diaria.

**No es** un sistema de gestión de inventario, ni un panel de analytics, ni un CRM. Es un **pipeline de transformación**: entra info de productos, sale feed de ads con creatividades listas.

---

## 2. Principios de diseño (las decisiones que NO se negocian)

Estos principios guían toda decisión técnica del proyecto. Cuando dudemos en el futuro, volvemos acá.

### 2.1 Modular por bloques de negocio, no por tablas
El sistema modela un **proceso de marketing**, no la estructura del Sheet de Mora. Cualquier cliente — independiente de qué tienda use, qué CRM tenga, qué red social use — pasa por los mismos 4 bloques: **Inventario → Selección → Estilo → Distribución**.

### 2.2 Configurable sin tocar código
Sumar un cliente, cambiar un diseño, agregar TikTok a un cliente que solo tenía Meta: todo se hace editando un archivo de configuración. **Cero código nuevo en el día a día.**

### 2.3 Cada cliente tiene su propio espacio
Datos, configuración, sheets, todo separado. Romper un cliente no rompe a los otros. Migrar un cliente es portable.

### 2.4 Diseños no son únicos por cliente
Un cliente puede tener **N diseños** según categoría, línea de producto, evento (Hot Sale, Navidad), etc. El sistema soporta esto desde el día 1.

### 2.5 Los datos del producto se pueden enriquecer con IA antes de renderizar
El sistema reconoce que los datos crudos de la tienda muchas veces no son ideales para una placa publicitaria (títulos largos, descripciones que no se leen, ausencia de bullets/beneficios). Existe un bloque dedicado a transformar/enriquecer datos con LLM **antes** de pasarlos al renderizado. Cada cliente decide si lo usa y con qué proveedor.

### 2.6 Si algo se hace 2 veces, se automatiza. Si se hace 1 vez, se documenta.
No metemos automatización prematura. Pero documentar es obligatorio.

### 2.7 Red de seguridad obligatoria
Cada cambio importante convive con la versión anterior durante al menos 1 semana antes de apagar la vieja. Mora-v1 sigue corriendo cuando arranque Mora-v2.

### 2.8 El cliente final no debería necesitar saber que existe Agency Nusa
Si en el futuro queremos vender el servicio "as a product" o entregar autoservicio a un cliente, el sistema debe permitirlo sin reescribirse.

---

## 3. Los 5 bloques de negocio

Cada bloque tiene una **función única y bien definida**. Los bloques son intercambiables: cada cliente combina los suyos según necesite. El bloque 3 (Enriquecimiento) es opcional.

### Bloque 1 — Inventario
**Pregunta que responde**: ¿qué productos existen en la tienda del cliente y cuáles son sus datos básicos?

**Datos**: SKU, nombre, precio, precio promo, stock, imágenes, categoría, descripción, URL del producto.

**Fuentes posibles** (módulos):
- `tiendanube`: trae de la API de Tiendanube con OAuth (lo que ya hace Mora)
- `shopify`: trae de la API de Shopify (futuro)
- `mercadolibre`: trae de la API de MeLi (futuro)
- `csv_manual`: el cliente pega un CSV o llena un Sheet a mano
- `tiendanube_csv_export`: para clientes que no quieren dar acceso OAuth

**Salida estándar**: un Sheet `Inventario` del cliente con columnas normalizadas (ver §6 Modelo de Datos Estándar).

### Bloque 2 — Selección
**Pregunta que responde**: de todos los productos del inventario, ¿cuáles quiero promocionar HOY?

**Datos**: una decisión por SKU sobre si va o no al feed de placas, qué diseño usa, qué categoría tiene.

**Fuentes posibles** (módulos):
- `manual`: cliente edita columna SI/NO en un Sheet (caso simple)
- `por_top_ventas`: top N SKUs por ventas en últimos X días (lo que hace Mora hoy)
- `por_categoria`: todos los productos de la categoría X
- `por_stock`: productos con stock > Y o stock < Z (liquidación)
- `combinado`: top ventas + manual override (Mora real)
- `por_etiqueta`: productos con tag/etiqueta específica en la tienda

**Salida estándar**: Sheet `Seleccion` con columnas: SKU, generar (SI/NO), diseño (qué template usar), prioridad opcional.

### Bloque 3 — Enriquecimiento (OPCIONAL)
**Pregunta que responde**: ¿cómo mejoro los datos crudos del producto para que la placa publicitaria sea más efectiva?

**Datos**: toma productos seleccionados y agrega campos derivados — tips/beneficios, título acortado, descripción acortada, slogan, etc.

**Por qué existe este bloque**: los datos que vienen de la tienda están pensados para una página web, no para una placa de 1080×1350. Un título de 90 caracteres no entra. Una descripción de 5 párrafos no se lee. Faltan los 3 beneficios concretos que el usuario quiere ver de un vistazo. Este bloque resuelve esa brecha.

**Fuentes posibles** (módulos):
- `llm_gemini`: usa Google Gemini (recomendado, integrado al stack actual)
- `llm_openai`: usa GPT
- `llm_claude`: usa Anthropic Claude
- `reglas_simples`: transformaciones sin LLM (truncar, capitalizar, regex) — siempre disponible como fallback
- `combinado`: pipeline de reglas + LLM (ej: primero trunca, después le pide al LLM que reescriba)

**Enriquecedores disponibles** (qué se puede generar):
- `tips_producto`: extraer N beneficios concretos en M palabras cada uno
- `titulo_corto`: reescribir el título en ≤ N caracteres
- `descripcion_corta`: resumir la descripción en ≤ N caracteres
- `slogan`: frase de venta corta
- `categoria_inferida`: detectar categoría si no está cargada
- `publico_objetivo`: deducir target demográfico (para campañas)

Cada enriquecedor se configura por cliente: cuáles se aplican, con qué parámetros.

**Requisitos del bloque** (no negociables):

1. **Cache obligatorio**: 1 llamada al LLM por SKU + hash del input. Si el input no cambió, no se vuelve a llamar al LLM. Cache configurable por TTL (default 30 días).
2. **Fallback de errores**: si el LLM falla o devuelve algo mal formado para un SKU, el sistema usa los datos crudos (con reglas simples) y continúa. NUNCA rompe el pipeline.
3. **Output cacheable y auditable**: los resultados del LLM se escriben en un Sheet `Enriquecimiento` del cliente, no en memoria volátil. Esto permite revisarlos y forzar regeneración si la calidad no es buena.
4. **Prompts versionados**: los prompts viven en archivos (no inline en código) y se pueden iterar sin redeploy.

**Salida estándar**: los productos seleccionados con campos extra:
```
sku, ..., tips: ["Resiste lluvia", "Suela antideslizante", "Ultra liviano"],
       ..., titulo_corto: "Zapatilla Trail Pro 2026",
       ..., descripcion_corta: "Trail running impermeable con suela Vibram"
```

Estos campos pasan al Bloque 4 (Estilo) y están disponibles como variables en el template HTML: `{tip_1}`, `{tip_2}`, `{tip_3}`, `{titulo_corto}`, `{descripcion_corta}`.

### Bloque 4 — Estilo
**Pregunta que responde**: ¿cómo se ve la placa de este producto?

**Datos**: un template HTML + variables a reemplazar (precio, imagen, etc.) → imagen PNG renderizada.

**Fuentes posibles** (módulos):
- `playwright_html`: render HTML + CSS con Playwright (lo que tenemos)
- `figma_api`: render desde un archivo de Figma con variables (futuro, premium)
- `canva_api`: render desde Canva (futuro)
- `ia_generativa`: render con modelos generativos (futuro experimental)

**Clave**: cada cliente puede tener **N templates** identificados por nombre (`hot_sale`, `cuotas_sin_interes`, `liquidacion`, etc.). La Selección decide cuál usar por cada SKU.

**Salida estándar**: archivos PNG locales (temporales).

### Bloque 5 — Distribución
**Pregunta que responde**: ¿dónde van las imágenes y los feeds finales?

**Datos**: una URL pública por placa + un feed estructurado por destino.

**Sub-bloques**:
- **Storage** (donde viven las imágenes):
  - `cloudinary`: lo que usamos hoy
  - `s3`: futuro
  - `google_drive`: futuro para clientes muy chicos
- **Destinos** (donde se publica el feed):
  - `meta_catalog`: Sheet con formato Meta (lo que tenemos)
  - `tiktok_catalog`: Sheet con formato TikTok (lo que tenemos)
  - `google_shopping`: Sheet con formato Google Merchant Center
  - `email`: mandar el feed a un mail con CSV adjunto (cliente lo sube manual)

**Salida**: nada (efecto: los feeds quedan actualizados, los catálogos de Meta/TikTok los leen).

---

## 4. Flujo end-to-end

```
┌─────────────────────────────────────────────────────────────────┐
│                       CRON DEL CLIENTE                          │
│                  (GitHub Actions, 1 por cliente)                │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │   Cargar pipeline.yaml       │
              │   del cliente                │
              └──────────────┬───────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌───────────────┐    ┌───────────────┐    ┌──────────────────┐
│  INVENTARIO   │    │   SELECCIÓN   │    │ ENRIQUECIMIENTO  │
│  (qué hay)    │───▶│  (qué va)     │───▶│ (mejorar datos)  │
│               │    │               │    │   [OPCIONAL]     │
│ → Sheet       │    │ → Sheet       │    │ → Sheet          │
│  Inventario   │    │  Selección    │    │  Enriquecimiento │
└───────────────┘    └───────────────┘    └────────┬─────────┘
                                                   │
                                                   ▼
                                          ┌──────────────────┐
                                          │     ESTILO       │
                                          │  (cómo se ve)    │
                                          │                  │
                                          │ → PNGs           │
                                          │  generados       │
                                          └────────┬─────────┘
                                                   │
                                                   ▼
                                  ┌────────────────────────────┐
                                  │      DISTRIBUCIÓN          │
                                  ├────────────────────────────┤
                                  │  Storage: subir PNG        │
                                  │  → URLs públicas           │
                                  ├────────────────────────────┤
                                  │  Destino Meta: escribir    │
                                  │  feed con URLs             │
                                  ├────────────────────────────┤
                                  │  Destino TikTok: escribir  │
                                  │  feed con URLs             │
                                  ├────────────────────────────┤
                                  │  (otros destinos…)         │
                                  └────────────┬───────────────┘
                                               │
                                               ▼
                                ┌────────────────────────────┐
                                │  Notificar resultado       │
                                │  (Slack/email/log)         │
                                └────────────────────────────┘
```

---

## 5. Estructura del repositorio

```
generador-catalogos-v2/
│
├── src/
│   ├── inventario/              ← Bloque 1
│   │   ├── base.py              (interfaz común: clase abstracta)
│   │   ├── tiendanube.py
│   │   ├── shopify.py
│   │   ├── csv_manual.py
│   │   └── registry.py          (mapea nombre → clase)
│   │
│   ├── seleccion/               ← Bloque 2
│   │   ├── base.py
│   │   ├── manual.py
│   │   ├── por_top_ventas.py
│   │   ├── por_categoria.py
│   │   ├── combinado.py
│   │   └── registry.py
│   │
│   ├── enriquecimiento/         ← Bloque 3 (OPCIONAL)
│   │   ├── base.py
│   │   ├── llm_gemini.py
│   │   ├── llm_openai.py
│   │   ├── llm_claude.py
│   │   ├── reglas_simples.py
│   │   ├── combinado.py
│   │   ├── cache.py             (cache key: sku + hash(input))
│   │   ├── enriquecedores/      (qué se puede generar)
│   │   │   ├── tips_producto.py
│   │   │   ├── titulo_corto.py
│   │   │   ├── descripcion_corta.py
│   │   │   ├── slogan.py
│   │   │   └── categoria_inferida.py
│   │   ├── prompts/             (prompts en archivos, no inline)
│   │   │   ├── tips_v1.txt
│   │   │   ├── titulo_corto_v1.txt
│   │   │   └── ...
│   │   └── registry.py
│   │
│   ├── estilo/                  ← Bloque 4
│   │   ├── base.py
│   │   ├── playwright_html.py
│   │   └── registry.py
│   │
│   ├── distribucion/            ← Bloque 5
│   │   ├── storage/
│   │   │   ├── base.py
│   │   │   ├── cloudinary.py
│   │   │   └── registry.py
│   │   ├── destinos/
│   │   │   ├── base.py
│   │   │   ├── meta_catalog.py
│   │   │   ├── tiktok_catalog.py
│   │   │   └── registry.py
│   │   └── registry.py
│   │
│   ├── core/
│   │   ├── pipeline.py          (orquestador: carga config y corre bloques)
│   │   ├── config_loader.py     (lee pipeline.yaml)
│   │   ├── sheets_client.py     (cliente Google Sheets compartido)
│   │   ├── modelo_datos.py      (dataclasses: Producto, Seleccion, Placa)
│   │   ├── logger.py            (logging estructurado)
│   │   └── notificador.py       (Slack/email para alertas)
│   │
│   └── cli.py                   (entrypoint: python -m src --cliente=X)
│
├── clients/
│   ├── morashop/
│   │   ├── pipeline.yaml        ← config principal
│   │   ├── templates/
│   │   │   ├── default.html
│   │   │   ├── hot_sale.html
│   │   │   ├── creatinas.html
│   │   │   └── suplementos.html
│   │   └── README.md            (cosas específicas del cliente)
│   │
│   └── _template/               ← plantilla para nuevos clientes
│       ├── pipeline.yaml.example
│       └── templates/
│           └── default.html
│
├── .github/workflows/
│   ├── morashop.yml             ← cron + dispatch
│   └── _template.yml.example
│
├── tests/
│   ├── test_inventario_tiendanube.py
│   ├── test_seleccion_top_ventas.py
│   └── test_estilo_playwright.py
│
├── docs/
│   ├── ARCHITECTURE.md          ← este documento
│   ├── ONBOARDING.md            ← cómo sumar cliente
│   ├── MODELO_DATOS.md          ← contrato de columnas
│   └── DECISIONES.md            ← log de decisiones y por qué
│
├── requirements.txt
├── README.md
└── .gitignore
```

### Convención clave: `base.py` y `registry.py` en cada bloque

Cada módulo de cada bloque hereda de una **clase abstracta** (`base.py`) que define qué métodos debe implementar. El `registry.py` mapea nombre del YAML → clase Python. Esto permite agregar fuentes nuevas **sin tocar el resto del código**.

Ejemplo simplificado:

```python
# src/inventario/base.py
from abc import ABC, abstractmethod

class FuenteInventario(ABC):
    @abstractmethod
    def traer_productos(self) -> list[Producto]:
        """Devuelve lista de productos en el formato estándar."""
        ...

# src/inventario/tiendanube.py
class TiendanubeInventario(FuenteInventario):
    def traer_productos(self) -> list[Producto]:
        # llama a API de TN, devuelve lista normalizada
        ...

# src/inventario/registry.py
FUENTES_INVENTARIO = {
    "tiendanube": TiendanubeInventario,
    "shopify": ShopifyInventario,
    "csv_manual": CSVManualInventario,
}
```

El orquestador hace:
```python
config = yaml.load("clients/morashop/pipeline.yaml")
clase = FUENTES_INVENTARIO[config["inventario"]["fuente"]]
fuente = clase(**config["inventario"]["config"])
productos = fuente.traer_productos()
```

Para sumar Shopify: creo `src/inventario/shopify.py`, lo agrego al registry, listo. **Cero cambios en el orquestador**.

---

## 6. Modelo de datos estándar

Esta es **la convención compartida** entre módulos. Cualquier fuente de inventario (TN, Shopify, CSV) debe devolver datos en este formato. Si una fuente nueva no tiene algún campo, lo deja vacío — pero la estructura es siempre la misma.

### 6.1 Sheet `Inventario` (output de Bloque 1)

| Columna | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `sku` | string | ✅ | Identificador único del producto |
| `nombre` | string | ✅ | Nombre comercial del producto |
| `descripcion` | string | ⚪ | Descripción larga, sin HTML |
| `precio_lista` | number | ✅ | Precio sin descuento (el "tachado") |
| `precio_promocional` | number | ⚪ | Precio con descuento. Vacío = no en promo |
| `cuotas_num` | integer | ⚪ | Cuántas cuotas (default: 3 si no aplica) |
| `stock` | integer | ⚪ | Stock actual |
| `categoria` | string | ⚪ | Categoría principal del producto |
| `marca` | string | ⚪ | Marca del producto |
| `imagen_url` | string | ✅ | URL pública de la imagen original |
| `url_producto` | string | ✅ | URL del producto en la tienda (para link en Meta/TikTok) |
| `actualizado_en` | datetime | ✅ | Cuándo se hizo el último sync |

### 6.2 Sheet `Seleccion` (output de Bloque 2)

| Columna | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `sku` | string | ✅ | Debe existir en Inventario |
| `generar` | "SI" / "NO" | ✅ | Si se procesa hoy o no |
| `template` | string | ⚪ | Nombre del template a usar. Vacío = `default` |
| `prioridad` | integer | ⚪ | 1=alta. Para ordenar el feed |
| `notas` | string | ⚪ | Para comentarios humanos |

### 6.3 Sheet `Enriquecimiento` (output del Bloque 3, opcional)

Solo existe si el cliente tiene Enriquecimiento habilitado. Es **el cache visible y editable** de los outputs del LLM. Vladimir/cliente puede revisarlo y forzar regeneración.

| Columna | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `sku` | string | ✅ | Debe existir en Inventario |
| `hash_input` | string | ✅ | Hash del input usado (descripcion+titulo). Si cambia → invalida cache |
| `tips_1`, `tips_2`, `tips_3` | string | ⚪ | Beneficios extraídos por LLM |
| `titulo_corto` | string | ⚪ | Título reescrito a ≤ N chars |
| `descripcion_corta` | string | ⚪ | Descripción reescrita a ≤ N chars |
| `slogan` | string | ⚪ | Slogan de venta opcional |
| `generado_en` | datetime | ✅ | Cuándo se generó este enriquecimiento |
| `proveedor` | string | ✅ | `llm_gemini`, `llm_openai`, etc. |
| `forzar_regenerar` | "SI"/"NO" | ⚪ | Si Vladimir lo pone en SI, próximo run ignora cache |

### 6.4 Sheet `Feed-Output` (output de Bloque 5, leído por Meta/TikTok)

**1 pestaña por destino**. Cada destino sabe qué columnas necesita.

**Pestaña `Meta`** (formato Facebook Catalog):
```
id, title, description, availability, condition, price, link, image_link, brand
```

**Pestaña `TikTok`** (formato TikTok Catalog):
```
sku_id, title, description, availability, condition, price, link, image_link, brand
```

Notar: misma data, distinto header. El módulo de distribución sabe traducir.

---

## 7. Anatomía del `pipeline.yaml`

Es el corazón del sistema. Define **qué módulos usa cada cliente y con qué parámetros**.

### 7.1 Ejemplo completo (MoraShop)

```yaml
# clients/morashop/pipeline.yaml
cliente:
  nombre: morashop
  brand_name: MORASHOP
  zona_horaria: America/Argentina/Buenos_Aires

# ============ BLOQUE 1: INVENTARIO ============
inventario:
  fuente: tiendanube
  config:
    # ID de la tienda en Tiendanube (del OAuth)
    store_id_secret: MORASHOP_TIENDANUBE_STORE_ID
    access_token_secret: MORASHOP_TIENDANUBE_TOKEN
    sheet_destino:
      id: 1AbC...
      pestaña: Inventario
    # campos opcionales:
    filtros:
      solo_publicados: true
      solo_con_stock: false

# ============ BLOQUE 2: SELECCIÓN ============
seleccion:
  fuente: combinado
  config:
    # Combina top ventas con override manual del cliente
    base:
      fuente: por_top_ventas
      top_n: 100
      periodo_dias: 60
    override:
      fuente: manual
      sheet:
        id: 1AbC...
        pestaña: Seleccion_Manual
      # En este sheet vladimir puede forzar SKUs en SI o NO
    sheet_destino:
      id: 1AbC...
      pestaña: Seleccion
    # Regla por defecto para asignar diseño según categoría:
    asignacion_diseño:
      por_columna: categoria
      mapeo:
        creatinas: creatinas
        proteinas: suplementos
        gomitas: suplementos
      default: default

# ============ BLOQUE 3: ENRIQUECIMIENTO (opcional) ============
enriquecimiento:
  habilitado: true
  proveedor: llm_gemini
  config:
    api_key_secret: GEMINI_API_KEY
    modelo: gemini-2.0-flash
    sheet_cache:
      id: 1AbC...
      pestaña: Enriquecimiento
    cache_ttl_dias: 30
    # Qué enriquecimientos correr y con qué parámetros:
    enriquecedores:
      - tipo: tips_producto
        cantidad: 3
        max_palabras_por_tip: 3
        idioma: es-AR
        prompt_version: tips_v1
      - tipo: titulo_corto
        max_caracteres: 40
        prompt_version: titulo_corto_v1
      - tipo: descripcion_corta
        max_caracteres: 120
        prompt_version: descripcion_corta_v1
    # Si el LLM falla, qué hacer:
    fallback:
      modo: reglas_simples   # nunca rompe el pipeline
      titulo_corto_fallback: truncar
      tips_fallback: dejar_vacio

# ============ BLOQUE 4: ESTILO ============
estilo:
  motor: playwright_html
  config:
    templates_dir: clients/morashop/templates/
    placa_width: 1080
    placa_height: 1350
    # Variables globales accesibles en todos los templates:
    variables_globales:
      logo_url: https://...
      brand_name: MORASHOP

# ============ BLOQUE 5: DISTRIBUCIÓN ============
distribucion:
  storage:
    backend: cloudinary
    config:
      cloud_name_secret: CLOUDINARY_CLOUD_NAME
      api_key_secret: CLOUDINARY_API_KEY
      api_secret_secret: CLOUDINARY_API_SECRET
      folder: morashop

  destinos:
    - tipo: meta_catalog
      config:
        sheet:
          id: 1XyZ...
          pestaña: Meta
        # Cómo formatear precio:
        formato_precio: "{precio}.00 ARS"
        # Si querés sobrescribir factor de descuento solo para este destino:
        hotsale_discount_factor: 1.0

    - tipo: tiktok_catalog
      config:
        sheet:
          id: 1XyZ...
          pestaña: TikTok
        formato_precio: "{precio}.00 ARS"

# ============ OBSERVABILIDAD ============
notificaciones:
  on_success:
    canal: slack
    webhook_secret: SLACK_WEBHOOK_AGENCY
    mensaje: "✅ MoraShop: {n_placas} placas generadas en {duracion}s"
  on_error:
    canal: slack
    webhook_secret: SLACK_WEBHOOK_AGENCY
    mensaje: "❌ MoraShop falló: {error}"
```

### 7.2 Lectura del YAML por el orquestador

El orquestador hace algo equivalente a:

```python
def correr_pipeline(cliente: str):
    config = cargar_yaml(f"clients/{cliente}/pipeline.yaml")

    # Bloque 1
    fuente_inv = FUENTES_INVENTARIO[config.inventario.fuente]
    productos = fuente_inv(config.inventario.config).traer_productos()
    escribir_sheet(config.inventario.sheet_destino, productos)

    # Bloque 2
    selector = SELECTORES[config.seleccion.fuente]
    seleccion = selector(config.seleccion.config).seleccionar(productos)
    escribir_sheet(config.seleccion.sheet_destino, seleccion)

    # Bloque 3 (opcional)
    if config.enriquecimiento and config.enriquecimiento.habilitado:
        enriquecedor = ENRIQUECEDORES[config.enriquecimiento.proveedor]
        productos_enriquecidos = enriquecedor(config.enriquecimiento.config).enriquecer(
            productos=[p for p in productos if seleccion[p.sku].generar == "SI"],
            usar_cache=True,
        )
        # Mergeamos los campos extra en productos:
        productos = merge_enriquecimiento(productos, productos_enriquecidos)

    # Bloque 4
    estilo = MOTORES_ESTILO[config.estilo.motor](config.estilo.config)
    placas = []
    for item in seleccion:
        if item.generar == "SI":
            producto = encontrar(productos, item.sku)
            png = estilo.renderizar(producto, item.template)
            placas.append(png)

    # Bloque 5
    storage = STORAGES[config.distribucion.storage.backend]
    urls = {p.sku: storage.subir(p.path) for p in placas}

    for destino_config in config.distribucion.destinos:
        destino = DESTINOS[destino_config.tipo](destino_config.config)
        destino.publicar(productos, seleccion, urls)

    notificar_exito(config.notificaciones)
```

---

## 8. Estrategia de migración desde Mora-v1

Esto es lo más delicado. Hay que migrar **sin romper** lo que funciona.

### 8.1 Decisión central: convivencia, no reemplazo

Mora-v1 sigue corriendo todo el tiempo. Mora-v2 corre en paralelo, escribiendo a:
- Cloudinary folder: `morashop_v2/` (no `morashop/`)
- Sheets: nuevos sheets, prefijados `MoraShop V2 - Inventario`, etc.
- Catálogo Meta: uno nuevo (no toca el productivo de Mora)

Después de validar 1 semana mínimo, se hace el switch.

### 8.2 Fases

**Fase A — Setup de infraestructura nueva (semana 1)**
1. Crear los 3 sheets nuevos en el Drive de Agency Nusa o de Mora
2. Conectar el OAuth de Tiendanube nuevo a Mora-v2
3. Estructura básica del repo `generador-catalogos-v2`
4. CI corre, no falla

**Fase B — Migración del Bloque 1 (semana 1-2)**
1. Implementar módulo `inventario/tiendanube.py`
2. Probar que llena el Sheet Inventario v2 igual o mejor que `Datos TN` actual
3. Schedule: cron 06:00 ART (mismo horario)

**Fase C — Migración del Bloque 2 (semana 2)**
1. Implementar `seleccion/por_top_ventas.py` + `seleccion/manual.py` + `seleccion/combinado.py`
2. Vladimir/vos puede editar el sheet `Seleccion_Manual` para override
3. Comparar resultados con el CRUCE actual

**Fase D — Migración del Bloque 4 (Estilo) (semana 2-3)**
1. Implementar `estilo/playwright_html.py` (porteo limpio de lo que ya hay)
2. Crear templates: `default.html`, `creatinas.html` (los que ya existen)
3. Validar que las placas generadas son visualmente iguales o mejores

**Fase E — Migración del Bloque 5 (Distribución) (semana 3)**
1. Implementar `storage/cloudinary.py`, `destinos/meta_catalog.py`, `destinos/tiktok_catalog.py`
2. Crear catálogos nuevos en Meta y TikTok (`MoraShop V2`)
3. Validar que los feeds quedan bien estructurados

**Fase F — Validación en producción paralela (semana 4)**
1. Ambos sistemas corren 7 días
2. Comparar diariamente
3. Documentar diferencias

**Fase G — Switch (cuando esté validado)**
1. Mover catálogos productivos de Meta/TikTok a apuntar al nuevo feed
2. Apagar workflow viejo
3. Mantener sheets viejos 30 días por las dudas
4. Borrar todo lo viejo

### 8.3 Criterios de éxito para considerar migrado

- [ ] Mora-v2 corre 7 días consecutivos sin intervención
- [ ] Genera la misma cantidad o más de placas que Mora-v1
- [ ] No tiene SKUs sin imagen ni con datos faltantes
- [ ] Las placas son visualmente equivalentes (o mejores)
- [ ] El tiempo de procesamiento es ≤ al de Mora-v1
- [ ] Vladimir confirma que la usabilidad del Sheet `Seleccion_Manual` es mejor o igual

---

## 9. Onboarding de un cliente nuevo (objetivo: 30 min)

Esta es **la prueba real de la modularidad**. Si suma cliente nuevo cuesta más de 30 min, algo está mal.

### Pasos

1. **Crear carpeta del cliente** en el repo (`clients/clienteX/`) copiando de `_template/`
2. **Crear 3 Sheets** en Drive: Inventario, Selección, Feed-Output
3. **Compartir Sheets con la service account** (Editor)
4. **Editar `pipeline.yaml`** con los IDs de Sheets y la fuente correcta
5. **Subir templates HTML** del cliente a `clients/clienteX/templates/`
6. **Configurar secrets específicos** del cliente en GitHub Secrets (si aplica)
7. **Crear workflow** `.github/workflows/clienteX.yml` desde el template
8. **Run workflow** manual y verificar

Detalle paso a paso en `ONBOARDING.md` (a redactar).

---

## 10. Decisiones pendientes (a resolver antes de implementar)

Esta lista se va a actualizar. Cuando algo se decide, se mueve a `DECISIONES.md`.

| # | Decisión | Opciones | Estado |
|---|---|---|---|
| 1 | ¿1 repo único o 1 repo por cliente? | (a) único multi-cliente, (b) template repo | **a** (decidido en v1) |
| 2 | ¿Cuenta Cloudinary compartida o por cliente? | (a) compartida, (b) por cliente | **a** (decidido) |
| 3 | ¿Cómo manejamos secrets específicos por cliente? | (a) prefijo en GH Secrets, (b) Vault, (c) cifrado en repo | **a** prefijo (`MORASHOP_*`) |
| 4 | ¿Notificaciones por dónde? | Slack, Discord, Telegram, Email | **a confirmar con Faco** |
| 5 | ¿Logs centralizados? | (a) GitHub Actions logs, (b) Sheet, (c) Logflare/Better Stack | **postergar** |
| 6 | ¿Para el Bloque Inventario, cómo manejar productos con N variantes y N imágenes? | (a) 1 fila por variante, (b) 1 fila por producto con variantes anidadas | **a** (consistente con TN) |
| 7 | ¿El sheet de Selección debería tener auto-fill o ser solo manual? | (a) solo manual, (b) lógica de auto-fill por reglas | **b** con override manual |
| 8 | ¿Cómo se actualiza el listado `Img Url` actual de Mora? | TBD | **investigar antes de migrar** |
| 9 | ¿Bloqueo en concurrencia? | Si corren 2 workflows del mismo cliente al mismo tiempo, ¿qué pasa? | **a definir** |
| 10 | ¿Versionado de placas? | ¿Guardamos historial o sobreescribimos? | **sobreescribir (lo que hace v1)** |
| 11 | ¿Cómo se sincroniza el catálogo de Meta/TikTok cuando un SKU sale del feed? | Replace vs Update | **Replace (lo que decidimos en v1)** |
| 12 | ¿Quién es dueño del Sheet maestro de cada cliente: Agency Nusa o el cliente? | TBD | **discutir caso por caso** |
| 13 | ¿Proveedor LLM default para Enriquecimiento? | Gemini, OpenAI, Claude | **Gemini Flash** (ya en stack, costo bajo) |
| 14 | ¿El Enriquecimiento corre antes o después del Bloque Selección? | (a) sobre todo el inventario, (b) sobre solo seleccionados | **b** (más barato, lo seleccionado es lo único que se renderiza) |
| 15 | ¿Quién revisa la calidad de los outputs del LLM? | (a) nadie, va directo, (b) Vladimir revisa Sheet Enriquecimiento, (c) checklist semanal | **b**: Vladimir puede marcar `forzar_regenerar=SI` por SKU |
| 16 | ¿Versionado de prompts? | (a) archivos `prompts/tips_v1.txt`, `tips_v2.txt`, (b) base de datos | **a** simple, en repo |
| 17 | ¿Si el LLM da output ofensivo o inadecuado, cómo lo detectamos? | (a) revisión humana, (b) filtros automáticos, (c) ambos | **a** por ahora (volumen bajo). Si escalamos a 10+ clientes, sumar **b** |

---

## 11. Roadmap a 6 meses

| Mes | Hito |
|---|---|
| 1 | Mora-v2 corriendo en paralelo a v1 |
| 1 | Switch productivo: Mora 100% v2 |
| 2 | Onboarding de 1 cliente nuevo con la arquitectura (testeo real) |
| 2 | Notificaciones Slack/email integradas |
| 2 | Bloque Enriquecimiento con Gemini (tips, título corto, descripción corta) |
| 3 | Soporte para Shopify (módulo `inventario/shopify.py`) |
| 3 | Módulo `seleccion/por_stock` (liquidación) |
| 4 | Dashboard mínimo: ver status de últimos runs por cliente |
| 5 | Módulo `destinos/google_shopping` |
| 6 | Reevaluación: ¿hace falta una UI propia o seguimos con YAML+Sheets? |

---

## 12. Glosario

- **Placa**: imagen publicitaria generada (PNG 1080x1350).
- **Feed**: archivo (CSV o Sheet) leído por Meta/TikTok para alimentar catálogos.
- **Catálogo**: entidad en Meta/TikTok que agrupa productos y permite armar campañas.
- **Catalog Ads / Dynamic Product Ads**: campañas que muestran productos del catálogo a usuarios según comportamiento.
- **Service Account**: cuenta de Google no-humana usada por el código para acceder a Sheets.
- **Pipeline**: secuencia de transformaciones que va de datos crudos a feed publicado.
- **Módulo**: pieza de código intercambiable que implementa una interfaz (ej: `tiendanube` y `shopify` son módulos del bloque Inventario).
- **Registry**: diccionario que mapea nombre del YAML → clase Python.
- **`pipeline.yaml`**: archivo de configuración por cliente que define qué módulos usa.
- **Enriquecedor**: función que aplica una transformación específica con LLM al producto (tips, título corto, etc.). Hay N enriquecedores que se combinan según necesidad del cliente.
- **Cache de Enriquecimiento**: tabla persistente donde se guardan outputs del LLM por SKU+hash_input. Evita llamar al LLM si el input no cambió.

---

## 13. Anexo: lo que NO está en este sistema (out of scope)

Para que quede claro qué hace y qué NO hace:

- ❌ Generar campañas de Meta/TikTok automáticamente (eso es otro proyecto)
- ❌ Optimizar bids o presupuestos
- ❌ Editar productos en la tienda (es solo lectura del inventario)
- ❌ CRM o seguimiento de clientes finales
- ❌ Reporting de performance de ads (eso lo hace Meta/TikTok directamente)
- ❌ A/B testing automático de placas (futuro, otro sistema)
- ❌ Gestión de stock

---

## 14. Cómo evolucionar este documento

Este documento es **vivo**. Reglas:

1. Cualquier cambio importante de arquitectura → editar este doc en el mismo PR.
2. Cualquier decisión técnica importante → agregarla a `DECISIONES.md` con fecha y contexto.
3. Si el código se aleja del diseño, **el código está mal**, no el diseño. (Salvo que el diseño esté demostrado equivocado, ahí actualizamos el diseño primero).
4. Lectura obligatoria antes de hacer cambios grandes al sistema.
