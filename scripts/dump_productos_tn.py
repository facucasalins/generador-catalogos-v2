#!/usr/bin/env python3
"""
Dump completo de productos de Tiendanube -> Google Sheet.

Una fila por VARIANTE, con los campos de producto denormalizados (repetidos en
cada variante) + categorias, atributos, imagenes y tags expandidos.

Config via env / GitHub Secrets:
  TN_TOKEN                     (requerido) access token de la API
  SHEET_ID                     (requerido) ID del Google Sheet destino
  GOOGLE_SERVICE_ACCOUNT_JSON  (requerido) JSON de la service account (string)
  TN_STORE_ID                  (opcional, default 2268228)
  SHEET_TAB                    (opcional, default "Productos_TN")
  TN_PER_PAGE                  (opcional, default 200)
"""
import os
import re
import json
import time
import requests
import gspread
from google.oauth2.service_account import Credentials

# ----------------------------- Config -----------------------------
STORE_ID = os.environ.get("TN_STORE_ID", "2268228")
TOKEN = os.environ["TN_TOKEN"]
SHEET_ID = os.environ["SHEET_ID"]
SHEET_TAB = os.environ.get("SHEET_TAB", "Productos_TN")
PER_PAGE = int(os.environ.get("TN_PER_PAGE", "200"))

BASE_URL = f"https://api.tiendanube.com/v1/{STORE_ID}"
HEADERS = {
    # OJO: header no estandar, validado en produccion. NO cambiar a "Authorization".
    "Authentication": f"bearer {TOKEN}",
    "User-Agent": "Agency Nusa Analytics (permutas.dev@gmail.com)",
    "Content-Type": "application/json",
}
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

COLUMNS = [
    "product_id", "variant_id", "nombre", "sku", "barcode", "mpn",
    "precio", "precio_promocional", "costo", "stock", "stock_management",
    "peso", "alto", "ancho", "profundidad",
    "variante_valores", "posicion_variante",
    "publicado", "envio_gratis", "requiere_envio",
    "marca", "categorias", "categorias_ids", "atributos", "tags",
    "handle", "url_canonica", "descripcion",
    "seo_titulo", "seo_descripcion",
    "imagen_principal", "imagenes_todas", "cantidad_imagenes", "video_url",
    "genero", "rango_edad",
    "creado", "actualizado", "publicado_en",
]

# ----------------------------- Helpers -----------------------------
def lang(value, prefer="es"):
    """Texto de un campo multi-idioma ({es: ..}) o el valor crudo."""
    if isinstance(value, dict):
        if value.get(prefer):
            return value[prefer]
        for v in value.values():
            if v:
                return v
        return ""
    return value if value is not None else ""


def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(text))
    return re.sub(r"\s+", " ", text).strip()


def join_multilang(items, sep=" / ", prefer="es"):
    """Listas donde cada item ES un dict multi-idioma (attributes, values)."""
    return sep.join(lang(it, prefer) for it in (items or []) if lang(it, prefer))


def join_categories(cats, sep=" | ", prefer="es"):
    return sep.join(
        lang(c.get("name"), prefer) for c in (cats or []) if lang(c.get("name"), prefer)
    )


def to_num(val):
    """Convierte a numero real si se puede (para que en la Sheet no quede texto)."""
    if val in (None, ""):
        return ""
    try:
        f = float(val)
        return int(f) if f.is_integer() else f
    except (ValueError, TypeError):
        return val


def cell(val):
    return "" if val is None else val


# --------------------------- Extraccion ---------------------------
def parse_next(link_header):
    """Devuelve la URL de la pagina siguiente del header Link, o None."""
    if not link_header:
        return None
    for part in link_header.split(","):
        segs = part.split(";")
        if len(segs) < 2:
            continue
        url = segs[0].strip().lstrip("<").rstrip(">")
        if segs[1].strip() == 'rel="next"':
            return url
    return None


def request_with_retry(session, url, max_retries=6):
    for attempt in range(max_retries):
        resp = session.get(url, timeout=60)
        if resp.status_code == 429:
            reset_ms = resp.headers.get("X-Rate-Limit-Reset")
            wait = (int(reset_ms) / 1000) if reset_ms else (2 ** attempt)
            wait = min(wait, 30)
            print(f"  429 rate limit -> espero {wait:.1f}s")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError(f"Demasiados 429 en {url}")


def fetch_all_products():
    products = []
    url = f"{BASE_URL}/products?per_page={PER_PAGE}&page=1"
    session = requests.Session()
    session.headers.update(HEADERS)
    while url:
        resp = request_with_retry(session, url)
        batch = resp.json()
        if not batch:
            break
        products.extend(batch)
        print(f"  + {len(batch)} productos (acumulado {len(products)})")
        url = parse_next(resp.headers.get("Link"))
        time.sleep(0.5)  # respeta leaky bucket (2 req/s)
    return products


# --------------------------- Aplanado ---------------------------
def flatten(products):
    rows = []
    for p in products:
        images = p.get("images") or []
        img_srcs = [img.get("src") for img in images if img.get("src")]
        base = {
            "product_id": p.get("id"),
            "nombre": lang(p.get("name")),
            "publicado": p.get("published"),
            "envio_gratis": p.get("free_shipping"),
            "requiere_envio": p.get("requires_shipping"),
            "marca": p.get("brand") or "",
            "categorias": join_categories(p.get("categories")),
            "categorias_ids": " | ".join(
                str(c.get("id")) for c in (p.get("categories") or []) if c.get("id")
            ),
            "atributos": join_multilang(p.get("attributes")),
            "tags": p.get("tags") or "",
            "handle": lang(p.get("handle")),
            "url_canonica": p.get("canonical_url") or "",
            "descripcion": strip_html(lang(p.get("description"))),
            "seo_titulo": lang(p.get("seo_title")),
            "seo_descripcion": lang(p.get("seo_description")),
            "imagen_principal": img_srcs[0] if img_srcs else "",
            "imagenes_todas": " | ".join(img_srcs),
            "cantidad_imagenes": len(img_srcs),
            "video_url": p.get("video_url") or "",
            "creado": p.get("created_at"),
            "actualizado": p.get("updated_at"),
            "publicado_en": p.get("published_at"),
        }
        for v in (p.get("variants") or [{}]):
            row = dict(base)
            row.update({
                "variant_id": v.get("id"),
                "sku": v.get("sku") or "",
                "barcode": v.get("barcode") or "",
                "mpn": v.get("mpn") or "",
                "precio": to_num(v.get("price")),
                "precio_promocional": to_num(v.get("promotional_price")),
                "costo": to_num(v.get("cost")),
                "stock": to_num(v.get("stock")),
                "stock_management": v.get("stock_management"),
                "peso": to_num(v.get("weight")),
                "alto": to_num(v.get("height")),
                "ancho": to_num(v.get("width")),
                "profundidad": to_num(v.get("depth")),
                "variante_valores": join_multilang(v.get("values")),
                "posicion_variante": v.get("position"),
                "genero": v.get("gender") or "",
                "rango_edad": v.get("age_group") or "",
            })
            rows.append([cell(row.get(col)) for col in COLUMNS])
    return rows


# --------------------------- Google Sheet ---------------------------
def write_to_sheet(header, rows):
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    try:
        ws = sh.worksheet(SHEET_TAB)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=SHEET_TAB, rows=len(rows) + 10, cols=len(header) + 2)

    values = [header] + rows
    ws.clear()
    ws.resize(rows=max(len(values) + 10, 100), cols=max(len(header) + 2, 26))
    # value_input_option RAW: numeros van como numero (ya casteados), SKU/barcode quedan texto.
    ws.update(range_name="A1", values=values, value_input_option="RAW")
    print(f"Escritas {len(rows)} filas en la pestania '{SHEET_TAB}'")


# --------------------------- Main ---------------------------
def main():
    print(f"Extrayendo productos de la tienda {STORE_ID} ...")
    products = fetch_all_products()
    print(f"Total productos: {len(products)}")
    rows = flatten(products)
    print(f"Total filas (variantes): {len(rows)}")
    write_to_sheet(COLUMNS, rows)
    print("Listo.")


if __name__ == "__main__":
    main()
