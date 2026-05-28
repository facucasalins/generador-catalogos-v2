# ONBOARDING JUANITA SHOES — Paso a paso

## Resumen
Cliente: Juanita Shoes (calzado / Tiendanube)
Promos vigentes:
- Envío gratis a partir de $100.000
- 9 cuotas sin interés a partir de $100.000
- 20% OFF pagando con transferencia

Diferencias vs MoraShop:
- 9 cuotas (no 6)
- Paleta beige/cuero (no naranja/blanco)
- 2 formatos: 4:5 (1080x1350) y 9:16 (1080x1920)
- Precio destacado = precio CON transferencia (no lista)

---

## 1. ESTRUCTURA EN GITHUB

Dentro de tu repo `agencia-nusa-feeds` (o como se llame), crear:

```
clients/
  juanita/
    config.json
    templates/
      juanita_4x5.html
      juanita_9x16.html
    .github/workflows/
      juanita-feed.yml   (copia adaptada del workflow de Mora)
```

Subí los 2 HTMLs que te paso (`juanita_4x5.html` y `juanita_9x16.html`) a `clients/juanita/templates/`.

### config.json

```json
{
  "client_name": "juanita",
  "display_name": "Juanita Shoes",
  "sheet_id": "PEGAR_ID_DEL_SHEET_DE_JUANITA",
  "cloudinary_folder": "juanita",
  "templates": {
    "4x5": {
      "path": "clients/juanita/templates/juanita_4x5.html",
      "width": 1080,
      "height": 1350
    },
    "9x16": {
      "path": "clients/juanita/templates/juanita_9x16.html",
      "width": 1080,
      "height": 1920
    }
  },
  "pricing": {
    "transferencia_factor": 0.8,
    "cuotas_count": 9,
    "cuotas_min_amount": 100000,
    "envio_gratis_min": 100000,
    "hotsale_discount_factor": 1.0
  },
  "feed_destinations": ["meta", "tiktok"]
}
```

> **Importante**: `hotsale_discount_factor: 1.0` para que NO le aplique descuento extra automático (mismo error que tuviste con Mora).

---

## 2. GOOGLE SHEET

Crear nuevo Sheet "Juanita - Feed Generator" con las mismas tabs que Mora:

| Tab | Contenido |
|-----|-----------|
| `Datos TN` | sync de Tiendanube vía n8n |
| `Img Url` | URL de imagen por SKU |
| `Img Url Expandido` | SKU base → variantes |
| `CRUCE` | join entre Datos TN + Img Url |
| `IMPORTRANGE` | espejo desde otro sheet si aplica |
| `Feed Meta` | feed final para Meta |
| `Feed TikTok` | feed final para TikTok |

### Fórmula clave: precio cuota (9 cuotas)

En la columna correspondiente del feed:

```
=SI(B2>=100000; ROUND(B2/9; 0); "")
```
Donde `B2` es el precio lista. Si querés que la cuota se calcule sobre el precio CON descuento de transferencia, sería `B2*0.8/9`.

### Fórmula precio transferencia:

```
=ROUND(B2*0.8; 0)
```

### Fórmula formato precio para placa (con punto miles):

```
="$"&TEXT(B2; "#,##0")
```

---

## 3. SCRIPT DE GENERACIÓN

En el notebook/script Python (adaptado del de Mora), las variables a parametrizar por cliente:

```python
CONFIG = json.load(open(f"clients/{CLIENT_NAME}/config.json"))

# rendering por formato
for formato, tpl_cfg in CONFIG["templates"].items():
    html = Path(tpl_cfg["path"]).read_text()
    # reemplazar placeholders por valores del row
    html = html.replace('id="precioTransferencia">$153.600',
                        f'id="precioTransferencia">{row["precio_transfer_fmt"]}')
    html = html.replace('id="precioLista">$192.000',
                        f'id="precioLista">{row["precio_lista_fmt"]}')
    html = html.replace('id="precioCuota">$21.333',
                        f'id="precioCuota">{row["precio_cuota_fmt"]}')
    html = html.replace('id="discountPct">35',
                        f'id="discountPct">{row["descuento_pct"]}')
    html = html.replace('id="productImg" src=""',
                        f'id="productImg" src="{row["img_url"]}"')

    # si NO hay descuento, ocultar badge
    if row["descuento_pct"] in (0, "", None):
        html = html.replace('id="discountBadge"', 'id="discountBadge" class="hidden"')
        html = html.replace('id="precioLista"', 'id="precioLista" class="hidden"')

    # render con playwright a tpl_cfg["width"] x tpl_cfg["height"]
    # subir a Cloudinary en carpeta CONFIG["cloudinary_folder"]/{formato}/{sku}.png
```

---

## 4. WORKFLOW GITHUB ACTIONS

Copiar `.github/workflows/morashop-feed.yml` como `.github/workflows/juanita-feed.yml`, cambiar:

- `name: Juanita Feed Generator`
- variable `CLIENT_NAME: juanita`
- el cron a un horario distinto al de Mora (ej: 5 AM en lugar de 4 AM) para no superponer cargas
- secrets: si Juanita usa otra cuenta de Cloudinary o Sheet diferente, crear nuevos secrets (`JUANITA_SHEET_ID`, `JUANITA_CLOUDINARY_URL`, etc)

---

## 5. CATÁLOGOS META + TIKTOK

- Crear catálogo NUEVO en Meta Business: "Juanita - Feed Placas" (separado del Tiendanube)
- Update mode: **Replace**
- Crear catálogo en TikTok Business
- En el feed TikTok asegurar columna `sku_id` (mediante fórmula del Sheet, igual que Mora)

---

## 6. CHECKLIST PRE-LANZAMIENTO

- [ ] Sheet creado con las 7 tabs
- [ ] n8n: workflow de sync TN → Sheet Juanita
- [ ] config.json subido con factor 0.8 y 9 cuotas
- [ ] HTMLs en `clients/juanita/templates/`
- [ ] Workflow GH Actions creado y testeado en push manual
- [ ] Cloudinary folder `juanita/` creado
- [ ] Catálogo Meta creado en modo Replace
- [ ] Catálogo TikTok creado con `sku_id`
- [ ] Verificar visualmente 3-5 placas generadas antes del primer run productivo

---

## NOTAS DE DISEÑO

La paleta:
- Fondo: `#F5EFE6` (crema cálido)
- Acento cuero: `#A67B5B` (badge descuento + highlights)
- Verde sobrio: `#7A8471` (label transferencia)
- Texto: `#1A1A1A` (negro carbón)

Si el cliente pide ajustes:
- Para hacer más oscura/premium: cambiar `background: #F5EFE6` → `#1A1A1A` y `color: #1A1A1A` → `#F5EFE6`
- Para versión sin badge descuento: ya está la clase `.hidden`
- Tipografía wordmark: Cormorant Garamond (Google Fonts, no requiere licencia)
