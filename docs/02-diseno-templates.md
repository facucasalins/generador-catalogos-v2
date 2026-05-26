# 02 - Diseño de templates HTML

> Cómo diseñar las placas para un cliente nuevo desde cero, iterando rápido con preview local.

---

## Conceptos básicos

### ¿Qué es un template?

Un template es **un archivo HTML** que define cómo se ve la placa de un producto. Lleva variables tipo `{nombre}` o `{precio_hotsale_formateado}` que el sistema reemplaza con los datos reales del producto antes de renderizar el PNG.

Vos lo escribís como HTML normal (con CSS dentro), el sistema lo abre con un Chromium headless, le saca una captura de 1080×1350 (Meta) o 1080×1920 (TikTok), y la sube a Cloudinary.

### ¿Dónde van?

```
clients/<cliente>/templates/
├── default.html              ← 4:5 (1080x1350) - para Meta
├── default_tiktok.html       ← 9:16 (1080x1920) - para TikTok
├── electro.html              ← otro estilo para electrohogar (opcional)
└── electro_tiktok.html       ← versión TikTok del de electrohogar
```

**Convención clave**: si tu template se llama `algo.html`, el equivalente 9:16 tiene que llamarse `algo_tiktok.html`. El sistema le agrega el sufijo `_tiktok` automáticamente cuando renderiza la versión 9:16.

### ¿Cuántos templates necesita un cliente?

Mínimo **dos** (`default.html` + `default_tiktok.html`). Si tiene categorías visualmente distintas (ej: Mora tiene suplementos y electrohogar con diseños diferentes), creás más:
- `default.html` / `default_tiktok.html` (suplementos)
- `electro.html` / `electro_tiktok.html` (electrohogar)

En el sheet de Selección, cada SKU puede tener su template asignado en la columna `template`.

---

## Variables disponibles

Todas las variables que podés usar en tu HTML. El sistema reemplaza `{nombre_variable}` por el valor real al renderizar.

### Identificación del producto

| Variable | Ejemplo | Notas |
|---|---|---|
| `{sku}` | `STARNU0_MUTANT_5KG_CHOCO` | El código del producto |
| `{nombre}` | `Mutant Whey 5kg Sabor Chocolate` | Nombre del producto |
| `{marca}` | `Star Nutrition` | Marca (puede estar vacío) |
| `{categoria}` | `Suplementos` | Categoría (puede estar vacío) |

### Precios

| Variable | Ejemplo | Notas |
|---|---|---|
| `{precio_original_formateado}` | `$12.500` | Precio de lista. Es el que se muestra tachado |
| `{precio_hotsale_formateado}` | `$9.999` | Precio efectivo (promoción si hay, lista si no) |
| `{cuota_formateada}` | `$4.166` | Valor de cada cuota (precio_lista / cuotas_num) |
| `{cuotas_num}` | `3` | Cantidad de cuotas |
| `{precio_lista}` | `12500.0` | Precio crudo sin formato (raramente lo necesitás) |
| `{precio_promocional}` | `9999.0` | Precio promo crudo sin formato |

> **NOTA**: `precio_hotsale_formateado` se calcula así:
> - Si el producto tiene `precio_promocional` > 0 → usa el promocional
> - Si NO tiene → usa `precio_lista * hotsale_discount_factor` (en Mora `factor=1.0`, o sea queda igual al lista)

### Imágenes

| Variable | Cómo se usa | Notas |
|---|---|---|
| `{imagen_b64}` | `<img src="{imagen_b64}">` | Foto del producto, viene embebida en base64 |
| `{logo_b64}` | `<img src="{logo_b64}">` | Logo del cliente, embebido en base64 |

> **¿Por qué base64?** Porque Playwright renderiza HTML en un browser headless con `file://`. Los recursos externos pueden no cargar a tiempo, generar placas con imágenes rotas. Embebiendo las imágenes en el HTML como base64, garantizamos que estén ahí cuando se hace el screenshot.

### Variables globales del cliente

Las defines en el `pipeline.yaml` del cliente bajo `estilo.config.variables_globales`. Después las usás en el HTML como cualquier variable normal.

| Variable | De dónde sale | Ejemplo |
|---|---|---|
| `{brand_name}` | yaml | `MORASHOP` |
| `{logo_url}` | yaml | URL del logo (después convertida a `logo_b64`) |
| `{evento_legal}` | yaml | `"Válido durante Mora Hot."` |

Podés agregar más en el yaml y van a estar disponibles en todos los templates del cliente.

---

## Dimensiones

### 4:5 (Meta)
- **1080 × 1350 píxeles**
- El template tiene que tener `body { width: 1080px; height: 1350px; }` exacto
- Es el formato standard de Instagram Feed

### 9:16 (TikTok)
- **1080 × 1920 píxeles**
- El template tiene que tener `body { width: 1080px; height: 1920px; }` exacto
- Es el formato vertical típico de TikTok/Reels/Stories

**Importante**: Playwright captura con esas dimensiones exactas. Si tu HTML tiene contenido que se sale del viewport, queda cortado. Si tiene menos altura que el viewport, queda con espacio en blanco abajo.

---

## Workflow de diseño

Este es el loop ideal para diseñar un template:

### 1. Setup inicial (una vez por máquina)

Asegurate de tener Python y Playwright instalados localmente:

```bash
# En la raíz del repo
pip install -r requirements.txt
playwright install chromium
```

### 2. Loop de iteración

```
┌─────────────────────────────────────────┐
│ 1. Editás clients/shark/templates/      │
│    default.html en VSCode/Cursor        │
│                                         │
│ 2. Corrés:                              │
│    python scripts/preview_template.py \ │
│      --cliente=shark --template=default │
│                                         │
│ 3. Se abre el PNG. Mirás. ¿Está bien?   │
│                                         │
│    SÍ → próximo template / commit       │
│    NO → volvés al paso 1                │
└─────────────────────────────────────────┘
```

### 3. Probar las dos variantes (4:5 y 9:16)

```bash
# Versión 4:5 (Meta)
python scripts/preview_template.py --cliente=shark --template=default --aspect=4:5

# Versión 9:16 (TikTok). Renderiza el archivo default_tiktok.html
python scripts/preview_template.py --cliente=shark --template=default --aspect=9:16
```

### 4. Probar con datos diferentes

Por default, el script usa datos mock. Pero podés pasarle datos custom para ver el template con productos reales:

```bash
# Producto con nombre largo (para ver si rompe el layout)
python scripts/preview_template.py \
  --template=default \
  --nombre="Whey Protein Isolate Premium Sabor Chocolate Belga 5kg edición limitada"

# Precios muy altos
python scripts/preview_template.py --template=default --precio-lista=999999 --precio-promo=799999

# Producto sin promo (precio_lista == precio_hotsale)
python scripts/preview_template.py --template=default --precio-lista=12500 --precio-promo=12500

# Imagen del cliente real
python scripts/preview_template.py \
  --template=default \
  --imagen=https://tu-cliente.com/producto.jpg

# Logo del cliente real (mientras estás probando)
python scripts/preview_template.py \
  --template=default \
  --logo-url=https://tu-cliente.com/logo.png
```

### 5. Cuando esté listo, commit

```bash
git add clients/shark/templates/default.html
git commit -m "Shark: template default 4:5"
git push
```

---

## Diseñar templates con Claude

Como ahora vos sos el diseñador, podés pedirle a Claude que te genere el HTML inicial o que itere sobre uno existente.

### Prompt sugerido para Claude

> "Diseñá un template HTML 1080×1350 para una placa de e-commerce. El producto va centrado en una zona blanca de 700×800px. Arriba va el logo de la marca (URL: `{logo_b64}`). Abajo, una banda de precios mostrando precio tachado (`{precio_original_formateado}`), precio principal grande (`{precio_hotsale_formateado}`) y la opción de cuotas (`{cuotas_num} CUOTAS de {cuota_formateada}`). Usá estos colores: primario #FF5733, secundario #1A1A2E. Tipografía Archivo de Google Fonts. Estética moderna y limpia. Tiene que tener `body { width: 1080px; height: 1350px; }` exacto y `overflow: hidden`."

### Buenas prácticas para los prompts

- Pasale **un template existente** como referencia visual + el estilo que querés
- Especificá **paleta de colores hex** del cliente
- Mostrále **fotos del producto típico** del cliente (logos, packshots) para que entienda escala
- Pedile que use **Google Fonts** (`@import url(...)`) que ya están disponibles en Playwright
- Pedile que **NO use recursos externos** (imágenes/videos/fonts hospedados en otro lugar) — esos pueden fallar al renderizar

### Limitaciones a tener en cuenta

- **Fonts custom**: si la marca usa una tipografía custom no estándar, hay que subir el `.woff2` y referenciarlo con `@font-face`. Es más fácil usar Google Fonts.
- **JavaScript**: Playwright SÍ ejecuta JS, pero **no esperes a que termine**. Si tu template depende de JS para renderizar (ej: animaciones, carga async), va a salir mal. Mantenelo todo HTML+CSS puro.
- **Video o GIFs animados**: solo se captura el primer frame. No tiene sentido usarlos.

---

## Anatomía de un template (ejemplo comentado)

Mirá `clients/morashop/templates/default.html` como referencia. Te marco las partes importantes:

```html
<!DOCTYPE html>
<html>
<head>
<style>
  /* IMPORT de Google Fonts - funciona, los carga Playwright */
  @import url('https://fonts.googleapis.com/css2?family=Archivo:wght@400;700&display=swap');

  * { margin: 0; padding: 0; box-sizing: border-box; }

  /* CLAVE: dimensiones exactas */
  body {
    width: 1080px;
    height: 1350px;
    background: #0a1f3d;
    font-family: 'Archivo', sans-serif;
    position: relative;
    overflow: hidden;  /* no scroll, lo que se sale del viewport se corta */
  }

  /* TODO el layout va con position: absolute y top/left/right/bottom específicos.
     Es el patrón que mejor funciona para placas con dimensiones fijas. */
  .logo {
    position: absolute;
    top: 40px;
    left: 50%;
    transform: translateX(-50%);
    width: 150px;
  }

  .product-zone {
    position: absolute;
    top: 230px;
    left: 80px;
    right: 80px;
    height: 700px;
    background: white;
    /* ... */
  }
</style>
</head>
<body>
  <!-- Logo: el HTML inyecta el base64 -->
  <img class="logo" src="{logo_b64}" alt="logo">

  <!-- Imagen del producto -->
  <div class="product-zone">
    <img src="{imagen_b64}" alt="producto" class="product-image">
  </div>

  <!-- Banda de precios -->
  <div class="price-band">
    <div class="precio-tachado">{precio_original_formateado}</div>
    <div class="precio-principal">{precio_hotsale_formateado}</div>
    <div class="cuotas">{cuotas_num} CUOTAS de {cuota_formateada}</div>
  </div>

  <!-- Legal -->
  <div class="banner-legal">{evento_legal}</div>
</body>
</html>
```

---

## Bugs visuales conocidos

Estos son problemas que **vamos a arreglar después**, pero por ahora viven:

### Producto sin promo
Cuando `precio_lista == precio_promocional`, el precio tachado queda igual al grande y queda visualmente raro (dos precios iguales, uno tachado). Solución futura: si son iguales, no mostrar el tachado.

### Cuotas redondeo
v1 (Colab) truncaba al cálculo de cuotas, v2 redondea. Diferencia de $1 a veces. Cosmético.

---

## FAQ

### ¿Puedo previsualizar el HTML sin Playwright?
Abrir el `.html` en Chrome directamente NO te muestra cómo va a quedar realmente, porque:
- Las variables `{imagen_b64}` quedan literales (no se reemplazan)
- El viewport del navegador no es 1080×1350

**Workaround manual**: en Chrome, abrí DevTools (F12) → Toggle device toolbar (Cmd+Shift+M) → "Responsive" → poné dimensiones 1080×1350. Te da una idea pero no es preciso. Mejor usá el script de preview.

### ¿Cómo agrego una variable nueva?
Las variables disponibles las define el código (`src/estilo/playwright_html.py` → `_construir_variables`). Si necesitás una nueva (ej: un disclaimer que dependa del producto), avísame y la agregamos.

Las variables globales del yaml SÍ las podés agregar libremente: editás el `pipeline.yaml` del cliente y la usás en el template como `{nueva_variable}`.

### ¿Puedo usar Tailwind / Bootstrap / framework CSS?
**Sí**, pero embebido. Tres formas:
- Copy/paste del CSS de la librería dentro del `<style>`
- Importar desde CDN: `<link rel="stylesheet" href="https://cdn.tailwindcss.com">` — funciona porque Playwright tiene internet
- Tailwind compilado a CSS estático

Recomiendo lo primero o lo tercero. El CDN es lento (segundos extra por placa).

### ¿Y si quiero animaciones?
No tiene sentido — Playwright captura un frame estático. Tu placa se ve como el "tiempo 0" de la animación. Si querés un efecto visual, hacelo con CSS estático (gradientes, transforms, etc.).

---

## Próximos pasos

- **Empezar a iterar**: corré `python scripts/preview_template.py --cliente=morashop --template=default` para ver el sistema funcionando
- **Entender la arquitectura**: leé `03-arquitectura.md`
- **Algo no anda**: leé `04-troubleshooting.md`
