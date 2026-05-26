# 01 - Quickstart: agregar un cliente nuevo

> **Audiencia**: alguien NO técnico siguiendo paso a paso. Si algo no se entiende, decímelo y lo corrijo.
>
> **Tiempo estimado**: 60-90 minutos la primera vez. ~30 minutos cuando ya lo hayas hecho 2-3 veces.

---

## Antes de empezar

Asegurate de tener:

- [ ] Acceso al repo de GitHub (`generador-catalogos-v2`)
- [ ] Acceso a la cuenta de Cloudinary que usamos
- [ ] Acceso a la cuenta de Google Drive donde están los sheets
- [ ] El cliente tiene tienda en **Tiendanube** (si no, este flujo no aplica)
- [ ] El cliente te dio acceso de admin a su Tiendanube (más abajo)

> **[SCREENSHOT: dashboard de GitHub mostrando el repo]**

---

## Paso 1: pedir acceso a Tiendanube del cliente

Antes que nada, tenés que **conseguir las credenciales** de Tiendanube del cliente. Sin esto, el sistema no puede leer sus productos.

### Cómo pedírselo al cliente

Mandale este mensaje (copy/paste y reemplazá `[CLIENTE]`):

> Hola [CLIENTE], para conectar tu Tiendanube con nuestro sistema necesito que me autorices como **Developer**. Es lo siguiente:
>
> 1. Entrá a tu Tiendanube
> 2. Andá a Configuración → Permisos
> 3. Buscá la opción "Invitar desarrollador" o "Agregar developer"
> 4. Poné este mail: `tu_email@dominio.com`
> 5. Confirmá
>
> Te llega un mail a vos? Cuando lo veas, aceptás. Listo, ya tengo acceso.

### Qué hacer cuando el cliente acepte

1. Vas a recibir un mail de Tiendanube tipo "[CLIENTE] te invitó a ser developer"
2. Click en aceptar
3. Ahora tenés acceso al panel de developer de ese cliente

### Cómo obtener `STORE_ID` y `ACCESS_TOKEN`

> **[SCREENSHOT: panel de developer de Tiendanube]**

1. Entrá a https://partners.tiendanube.com/apps con tu cuenta de developer
2. Buscá la app "Agency Nusa Analytics" (es la app que tenemos para acceder a clientes)
3. En "Tiendas autorizadas", buscás al cliente nuevo
4. Vas a ver dos valores:
   - **Store ID**: un número como `1234567`
   - **Access Token**: un string largo tipo `abc123def456ghi789...`

Anotá los dos valores en un lugar seguro (Notion, 1Password, etc). Los vas a usar en el Paso 4.

> **NOTA**: el `ACCESS_TOKEN` es secreto. NO lo subas a GitHub directamente. Solo lo vas a poner como "secret" de GitHub Actions (Paso 4).

---

## Paso 2: crear los Google Sheets

El sistema usa **3 sheets por cliente**:

| Sheet | Para qué sirve | Ejemplo Mora |
|---|---|---|
| **Inventario** | Donde se vuelca el inventario crudo de TN + historial de placas + cache de enriquecimiento | `1902u_7of...` |
| **Selección** | Donde marcás qué SKUs querés generar y con qué template | `1NOG91buD9c...` |
| **Feed-Output** | Donde se escriben los feeds finales (pestañas Meta_default, TikTok_default, etc) | `1oDOXmgeVg...` |

### Cómo crearlos

> **[SCREENSHOT: Google Drive mostrando estructura de carpetas]**

1. En Google Drive, andá a la carpeta del cliente (creala si no existe: ej. "Clientes Agency Nusa / Shark")
2. Adentro, creá los 3 sheets con estos nombres exactos:
   - `Shark - Inventario`
   - `Shark - Selección`
   - `Shark - Feed-Output`
3. Abrí cada uno y copiá su **ID** (está en la URL, entre `/d/` y `/edit`)
   - Ejemplo: `https://docs.google.com/spreadsheets/d/1ABC...XYZ/edit` → ID es `1ABC...XYZ`
4. Anotá los 3 IDs

### Compartir con la service account

Cada sheet tiene que estar compartido con la **service account** del sistema (es como un email).

1. En cada sheet, click en "Compartir" (arriba a la derecha)
2. Pegá este email: `[email-de-la-service-account].iam.gserviceaccount.com`
3. Dale permisos de **Editor**
4. Desmarcá "Notificar" (es un robot, no le importa)
5. Compartir

> **NOTA**: el email exacto de la service account lo tengo guardado en mis credenciales personales. Si lo necesitás, pedímelo. Es el mismo para todos los clientes.

### Inicializar las pestañas

En el sheet de **Selección**, creá una pestaña llamada exactamente `Seleccion` (sin tilde) con esta primera fila:

```
sku  |  generar  |  template  |  prioridad  |  notas
```

Los otros dos sheets quedan vacíos: el sistema los va a llenar solo cuando corra el workflow por primera vez.

---

## Paso 3: estructura del cliente en el repo

Toda la configuración del cliente vive en `clients/<cliente>/`. La estructura es:

```
clients/
└── shark/                    ← carpeta nueva del cliente
    ├── pipeline.yaml         ← configuración (sheets, secrets, templates)
    └── templates/
        ├── default.html      ← template 4:5 (para Meta) - 1080x1350
        └── default_tiktok.html  ← template 9:16 (para TikTok) - 1080x1920
```

### 3.a) Crear la carpeta y el `pipeline.yaml`

En GitHub:

1. Click en "Add file" → "Create new file"
2. En el nombre del archivo, poné: `clients/shark/pipeline.yaml`
3. Pegá esto y reemplazá los `[VALORES]`:

```yaml
# ====================================================================
# Pipeline de SHARK
# ====================================================================

cliente:
  nombre: shark
  brand_name: SHARK
  zona_horaria: America/Argentina/Buenos_Aires

# ============ BLOQUE 1: INVENTARIO ============
inventario:
  fuente: tiendanube
  config:
    store_id_secret: SHARK_TIENDANUBE_STORE_ID
    access_token_secret: SHARK_TIENDANUBE_TOKEN
    sheet_destino:
      id: "[ID_DEL_SHEET_INVENTARIO]"
      pestaña: Inventario

# ============ BLOQUE 2: SELECCIÓN ============
seleccion:
  fuente: sheet_manual
  config:
    sheet:
      id: "[ID_DEL_SHEET_SELECCION]"
      pestaña: Seleccion
    template_default: default

# ============ BLOQUE 3: ENRIQUECIMIENTO ============
enriquecimiento:
  proveedor: gemini
  config:
    api_key_secret: GEMINI_API_KEY
    modelo: gemini-2.5-flash
    max_chars_titulo: 60
    max_chars_descripcion: 200
    cantidad_tips: 3
    max_chars_tip: 40
    tono: "Argentino. Usa voseo cuando corresponda. Lenguaje natural."

# ============ BLOQUE 4: ESTILO ============
estilo:
  motor: playwright_html
  config:
    placa_width: 1080
    placa_height: 1350
    hotsale_discount_factor: 1.0

    aspect_ratios:
      - label: "4:5"
        width: 1080
        height: 1350
        template_suffix: ""
      - label: "9:16"
        width: 1080
        height: 1920
        template_suffix: "_tiktok"

    variables_globales:
      brand_name: SHARK
      logo_url: "[URL_DEL_LOGO_DEL_CLIENTE]"
      evento_legal: "Promoción válida por tiempo limitado."

# ============ BLOQUE 5: DISTRIBUCIÓN ============
distribucion:
  storage:
    backend: cloudinary
    config:
      cloud_name_secret: CLOUDINARY_CLOUD_NAME
      api_key_secret: CLOUDINARY_API_KEY
      api_secret_secret: CLOUDINARY_API_SECRET
      folder: shark

  destinos:
    - tipo: meta_catalog
      config:
        sheet_id: "[ID_DEL_SHEET_FEED_OUTPUT]"
        moneda: ARS
        calcular_availability_por_stock: true

    - tipo: tiktok_catalog
      config:
        sheet_id: "[ID_DEL_SHEET_FEED_OUTPUT]"
        moneda: ARS
        calcular_availability_por_stock: true
```

4. **Reemplazá**:
   - `[ID_DEL_SHEET_INVENTARIO]` → ID del sheet Inventario (Paso 2)
   - `[ID_DEL_SHEET_SELECCION]` → ID del sheet Selección (Paso 2)
   - `[ID_DEL_SHEET_FEED_OUTPUT]` → ID del sheet Feed-Output (Paso 2, aparece 2 veces)
   - `[URL_DEL_LOGO_DEL_CLIENTE]` → URL pública del logo del cliente (sacala de su web)
   - Cambiá `shark` y `SHARK` por el nombre del cliente real (lowercase y MAYÚS respectivamente)

5. Commit directo a `main`

### 3.b) Templates HTML

Por ahora, **dejá la carpeta `templates/` vacía**. La vas a llenar en el Paso 6.

---

## Paso 4: agregar los secrets de GitHub

Los **secrets** son variables sensibles (tokens, passwords) que GitHub guarda cifradas. El workflow los lee al correr.

### Secrets nuevos a agregar

Para cada cliente nuevo, agregás **2 secrets** (los demás se comparten entre clientes):

| Nombre del secret | Valor | De dónde sale |
|---|---|---|
| `<CLIENTE>_TIENDANUBE_STORE_ID` | número del store | Paso 1 |
| `<CLIENTE>_TIENDANUBE_TOKEN` | el access token | Paso 1 |

Donde `<CLIENTE>` es el nombre del cliente en MAYÚSCULAS. Ejemplos:
- `SHARK_TIENDANUBE_STORE_ID`
- `SHARK_TIENDANUBE_TOKEN`
- `JUANITA_TIENDANUBE_STORE_ID`
- `JUANITA_TIENDANUBE_TOKEN`

### Cómo agregarlos

> **[SCREENSHOT: pestaña Settings → Secrets and variables → Actions]**

1. En el repo de GitHub, andá a **Settings** (arriba a la derecha)
2. Menú lateral: **Secrets and variables → Actions**
3. Click en **"New repository secret"** (botón verde arriba a la derecha)
4. Pegá el **Name** (ej: `SHARK_TIENDANUBE_STORE_ID`)
5. Pegá el **Secret** (el valor que copiaste del Paso 1)
6. Click "Add secret"
7. Repetí para el segundo secret

### Secrets compartidos (NO los crees de nuevo)

Estos secrets son los mismos para todos los clientes. **YA están creados**, no los toques:

- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `GEMINI_API_KEY`

---

## Paso 5: crear el workflow de GitHub Actions

El workflow es el que dispara el pipeline cada día (cron) o cuando vos quieras (manual).

### Cómo crearlo

> **[SCREENSHOT: archivo .github/workflows/morashop-v2.yml]**

1. En GitHub, click en "Add file" → "Create new file"
2. Path: `.github/workflows/shark.yml`
3. Pegá esto y reemplazá las menciones de "shark"/"SHARK" por el nombre del cliente:

```yaml
name: SHARK - Pipeline completo

on:
  workflow_dispatch:
  schedule:
    # 06:00 ART = 09:00 UTC. Si querés otro horario, ajustá acá.
    - cron: '0 9 * * *'

jobs:
  pipeline:
    runs-on: ubuntu-latest
    timeout-minutes: 45
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Instalar dependencias Python
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Cache de browsers Playwright
        id: playwright-cache
        uses: actions/cache@v4
        with:
          path: ~/.cache/ms-playwright
          key: playwright-${{ runner.os }}-${{ hashFiles('requirements.txt') }}

      - name: Instalar Chromium para Playwright
        run: |
          if [ "${{ steps.playwright-cache.outputs.cache-hit }}" = "true" ]; then
            playwright install-deps chromium
          else
            playwright install --with-deps chromium
          fi

      - name: Correr pipeline
        env:
          SHARK_TIENDANUBE_STORE_ID: ${{ secrets.SHARK_TIENDANUBE_STORE_ID }}
          SHARK_TIENDANUBE_TOKEN: ${{ secrets.SHARK_TIENDANUBE_TOKEN }}
          GOOGLE_SERVICE_ACCOUNT_JSON: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}
          CLOUDINARY_CLOUD_NAME: ${{ secrets.CLOUDINARY_CLOUD_NAME }}
          CLOUDINARY_API_KEY: ${{ secrets.CLOUDINARY_API_KEY }}
          CLOUDINARY_API_SECRET: ${{ secrets.CLOUDINARY_API_SECRET }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          OUTPUT_DIR: ${{ github.workspace }}/placas_output
        run: |
          python -m src.cli --cliente=shark --output-dir=$OUTPUT_DIR

      - name: Subir placas como artifact
        if: success()
        uses: actions/upload-artifact@v4
        with:
          name: placas-shark
          path: ${{ github.workspace }}/placas_output/*.png
          retention-days: 7
```

4. **Reemplazá** todos los `SHARK` / `shark` por el nombre real del cliente
5. Commit directo a `main`

> **¿Querés que corra a otro horario?** Cambiá `cron: '0 9 * * *'`. Por ejemplo, `'0 12 * * *'` corre a las 09:00 ART (12:00 UTC). [Generador de cron](https://crontab.guru/)

---

## Paso 6: diseñar los templates HTML

Los templates son los HTML que se renderizan como placas. Cada cliente tiene los suyos en `clients/<cliente>/templates/`.

**Por ahora, podés copiar los de Mora como base** mientras diseñás los propios. Después los reemplazás.

### Opción rápida: copiar templates de Mora

1. En GitHub, andá a `clients/morashop/templates/`
2. Abrí `default.html` → copiá todo el contenido
3. En `clients/shark/templates/`, creá un archivo nuevo `default.html` con ese contenido
4. Cambiá los colores, fuentes y logos para que matchee con la identidad de Shark
5. Repetí para `default_tiktok.html`, `electro.html`, `electro_tiktok.html` (los que apliquen)

### Opción mejor: diseñar desde cero con Claude

Para esto leé el doc **`02-diseno-templates.md`**.

### Probar el template localmente

Para no esperar al workflow entero cada vez que iterás, usá el script de preview:

```bash
python scripts/preview_template.py --cliente=shark --template=default --aspect=4:5
```

Esto te genera un PNG con datos mock y te lo abre automáticamente. Iterás HTML → preview → HTML hasta que esté bien. Más detalles en `02-diseno-templates.md`.

---

## Paso 7: primera corrida y validación

Llegamos al momento de la verdad.

### 7.a) Marcar SKUs en Selección

> **[SCREENSHOT: sheet de Selección con SKUs marcados]**

1. Abrí el sheet "Shark - Selección"
2. En la pestaña `Seleccion`, agregá unas filas:

| sku | generar | template | prioridad | notas |
|---|---|---|---|---|
| SKU-001 | TRUE | default | 1 | |
| SKU-002 | TRUE | default | 2 | |
| SKU-003 | TRUE | default | 3 | |

> **Valores válidos para `generar`**: `TRUE`, `SI`, `YES`, `X`, `1`. Cualquier otro valor (vacío, `FALSE`, `NO`) marca el SKU como "no generar".

Empezá con **5-10 SKUs** para la primera prueba. No marques 80 de una.

### 7.b) Disparar el workflow manual

1. En GitHub, andá a **Actions**
2. Menú izquierdo: click en "SHARK - Pipeline completo"
3. Click en "Run workflow" (botón gris arriba a la derecha)
4. Branch: `main`
5. Click "Run workflow" (botón verde)

### 7.c) Mirar el resultado

El workflow va a tardar **3-15 minutos** (depende de cuántos SKUs marcaste).

Cuando termine:

1. Vas a recibir una notificación en Telegram (si ya configuraste el bot para este cliente)
2. En el run del workflow, scrolleá hasta abajo → "Artifacts" → bajá `placas-shark.zip`
3. Descomprimí y revisá las PNG visualmente
4. Andá al sheet "Shark - Feed-Output" y verificá que las pestañas `Meta_default`, `Meta_electro` (si aplica), `TikTok_default`, `TikTok_electro` tengan filas con URLs de Cloudinary

> **NOTA sobre Telegram**: el bot actual notifica al chat de Morashop. Para que notifique también a Shark, hay que setear un chat distinto. Esto es **opcional**. Si lo querés, hablamos.

### 7.d) ¿Falló algo?

- ❌ **Workflow rojo (error)**: andá al log del run y buscá el mensaje de error. Pasámelo y lo vemos.
- ⚠️ **Workflow verde pero pestañas vacías**: probablemente sea un problema de templates o de matching entre SKUs marcados y SKUs del inventario. Mirá el doc `04-troubleshooting.md`.
- ✅ **Workflow verde y pestañas con datos**: ¡listo! El cliente quedó conectado al sistema.

---

## Paso 8: conectar Meta y TikTok (opcional, cuando esté validado)

Cuando hayas validado visualmente las placas y los feeds en las pestañas, podés conectar:

### Meta Business Manager

1. Entrá a Meta Business Manager
2. Catalog Manager → Crear catálogo → "Productos"
3. Source: "Data feed" → "Schedule a Recurring Feed"
4. URL del feed: publicá las pestañas `Meta_default` y `Meta_electro` como CSV
   - En el sheet, File → Share → Publish to web → seleccioná la pestaña → format CSV
   - Copiá la URL pública
5. Schedule: diario, después de las 06:00 ART (cuando el workflow ya terminó)

### TikTok Catalog Manager

Mismo flujo que Meta pero con las pestañas `TikTok_default` y `TikTok_electro`.

> **NOTA**: este paso lleva ~30 minutos por plataforma. Tenés guías de Meta/TikTok que cubren la parte de "cómo conectar un feed CSV". El sistema solo genera el feed; conectarlo a la plataforma es trabajo manual de una vez.

---

## Checklist final

- [ ] Acceso a Tiendanube del cliente conseguido (Paso 1)
- [ ] 3 sheets creados y compartidos con la service account (Paso 2)
- [ ] `clients/<cliente>/pipeline.yaml` creado con todos los IDs correctos (Paso 3)
- [ ] Carpeta `clients/<cliente>/templates/` creada (Paso 3)
- [ ] Secrets `<CLIENTE>_TIENDANUBE_STORE_ID` y `<CLIENTE>_TIENDANUBE_TOKEN` cargados en GitHub (Paso 4)
- [ ] Workflow `.github/workflows/<cliente>.yml` creado (Paso 5)
- [ ] Al menos un template HTML diseñado y subido (Paso 6)
- [ ] Primera corrida exitosa con 5-10 SKUs (Paso 7)
- [ ] Feeds Meta/TikTok conectados (Paso 8, opcional)

---

## Próximos pasos

- **Diseñar templates a medida del cliente**: ver `02-diseno-templates.md`
- **Entender cómo funciona el sistema por dentro**: ver `03-arquitectura.md`
- **Algo no funciona**: ver `04-troubleshooting.md`
