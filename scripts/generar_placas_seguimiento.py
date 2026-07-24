#!/usr/bin/env python3
"""
Genera las placas estáticas de seguimiento de pedidos y las sube a Cloudinary
con public_id determinístico (la URL nunca cambia).

NO corre en el pipeline diario. Es un script one-off: se corre a mano solo
cuando cambia el diseño de seguimiento.html.

Uso:
    # preview local, sin subir (deja los PNG en /tmp/placas_seguimiento/)
    python scripts/generar_placas_seguimiento.py --no-upload

    # generar y subir a Cloudinary
    python scripts/generar_placas_seguimiento.py

    # una sola placa (iterar diseño rápido)
    python scripts/generar_placas_seguimiento.py --solo moto_efec_prep --no-upload

Al terminar imprime la tabla template_whatsapp -> URL para pegar en el
resolver de n8n (workflow "MoraShop Seguimiento").
"""

import argparse
import base64
import mimetypes
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT / "clients" / "morashop" / "templates" / "seguimiento.html"

# Candidatos donde buscar el logo. El primero que exista se usa.
LOGO_CANDIDATOS = [
    ROOT / "clients" / "morashop" / "assets" / "logo.png",
    ROOT / "clients" / "morashop" / "assets" / "logo_morashop.png",
    ROOT / "clients" / "morashop" / "logo.png",
]
OUT_DIR = Path("/tmp/placas_seguimiento")
CLOUDINARY_FOLDER = "morashop-v2/seguimiento"

WIDTH, HEIGHT = 1200, 628

# ---------------------------------------------------------------------------
# Iconos (SVG inline: sin recursos externos, Playwright los renderiza siempre)
# ---------------------------------------------------------------------------
ICONS = {
    "check": '<path d="M20 6L9 17l-5-5"/>',
    "caja": '<path d="M21 8l-9-5-9 5v8l9 5 9-5V8z"/><path d="M3.3 7.5L12 12.5l8.7-5"/><path d="M12 12.5V21"/>',
    "moto": '<path d="M1 3h13v10H1z"/><path d="M14 8h4l3 3v2h-7z"/><circle cx="5.5" cy="17" r="2"/><circle cx="17.5" cy="17" r="2"/>',
    "casa": '<path d="M3 10.5L12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/>',
    "local": '<path d="M3 9l1.5-5h15L21 9"/><path d="M4.5 9V20h15V9"/><path d="M3 9h18"/><path d="M9.5 20v-6h5v6"/>',
    "reloj": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
    "billete": '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.6"/>',
}

STROKE = {"done": "#e8dec5", "active": "#ffffff", "pending": "#a99e82"}


def paso_html(estado: str, icono: str, label: str) -> str:
    """estado: done | active | pending"""
    ancho_icono = "54%" if estado == "active" else "52%"
    grosor = "3.2" if icono == "check" else ("2.2" if estado == "active" else "2")
    return (
        f'<div class="paso {estado}" style="width: {{col}}%;">'
        f'<div class="bullet">'
        f'<svg width="{ancho_icono}" height="{ancho_icono}" viewBox="0 0 24 24" fill="none" '
        f'stroke="{STROKE[estado]}" stroke-width="{grosor}" stroke-linecap="round" stroke-linejoin="round">'
        f"{ICONS[icono]}</svg></div>"
        f'<div class="label">{label}</div></div>'
    )


# ---------------------------------------------------------------------------
# Definición de las 12 placas
#   pasos: lista de (icono, label). El índice activo define el resto.
#   activo: índice (0-based) del paso actual
# ---------------------------------------------------------------------------
PLACAS = {
    # ---------- MOTO (envío propio CABA/GBA) ----------
    "moto_online_prep": {
        "subtitulo": "Envío en moto · CABA y GBA",
        "nota": "Entregas de lunes a sábado, de 14 a 22hs",
        "pasos": [("check", "Pago<br>realizado"), ("caja", "En<br>preparación"),
                  ("moto", "En<br>camino"), ("casa", "Entregado")],
        "activo": 1,
    },
    "moto_online_camino": {
        "subtitulo": "Envío en moto · CABA y GBA",
        "nota": "Entregas de lunes a sábado, de 14 a 22hs",
        "pasos": [("check", "Pago<br>realizado"), ("caja", "En<br>preparación"),
                  ("moto", "En<br>camino"), ("casa", "Entregado")],
        "activo": 2,
    },
    "moto_efec_prep": {
        "subtitulo": "Envío en moto · CABA y GBA · Efectivo",
        "nota": "Tené el efectivo listo para la entrega",
        "pasos": [("check", "Pedido<br>confirmado"), ("caja", "En<br>preparación"),
                  ("moto", "En camino<br>💵"), ("casa", "Entregado")],
        "activo": 1,
    },
    "moto_efec_camino": {
        "subtitulo": "Envío en moto · CABA y GBA · Efectivo",
        "nota": "Tené el efectivo listo para la entrega",
        "pasos": [("check", "Pedido<br>confirmado"), ("caja", "En<br>preparación"),
                  ("moto", "En camino<br>💵"), ("casa", "Entregado")],
        "activo": 2,
    },
    # ---------- CORREO a domicilio ----------
    "correo_prep": {
        "subtitulo": "Envío por correo a domicilio",
        "nota": "Los tiempos de entrega dependen del correo",
        "pasos": [("check", "Pago<br>realizado"), ("caja", "En<br>preparación"),
                  ("moto", "Despachado"), ("casa", "En tu casa")],
        "activo": 1,
    },
    "correo_despachado": {
        "subtitulo": "Envío por correo a domicilio",
        "nota": "Seguí tu envío con el código que te enviamos",
        "pasos": [("check", "Pago<br>realizado"), ("caja", "En<br>preparación"),
                  ("moto", "Despachado"), ("casa", "En tu casa")],
        "activo": 2,
    },
    # ---------- SUCURSAL de correo ----------
    "sucursal_prep": {
        "subtitulo": "Envío a sucursal de retiro",
        "nota": "Te avisamos cuando llegue a la sucursal",
        "pasos": [("check", "Pago<br>realizado"), ("caja", "En<br>preparación"),
                  ("moto", "Camino a<br>sucursal"), ("local", "Listo para<br>retirar")],
        "activo": 1,
    },
    "sucursal_camino": {
        "subtitulo": "Envío a sucursal de retiro",
        "nota": "Seguí tu envío con el código que te enviamos",
        "pasos": [("check", "Pago<br>realizado"), ("caja", "En<br>preparación"),
                  ("moto", "Camino a<br>sucursal"), ("local", "Listo para<br>retirar")],
        "activo": 2,
    },
    # ---------- RETIRO en el local ----------
    "retiro_online_prep": {
        "subtitulo": "Retiro en el local · Avellaneda",
        "nota": "Montes de Oca 589, Avellaneda",
        "pasos": [("check", "Pago<br>realizado"), ("caja", "En<br>preparación"),
                  ("local", "Listo para<br>retirar")],
        "activo": 1,
    },
    "retiro_efec_prep": {
        "subtitulo": "Retiro en el local · Avellaneda · Efectivo",
        "nota": "Lo abonás en efectivo al retirarlo",
        "pasos": [("check", "Pedido<br>reservado"), ("caja", "En<br>preparación"),
                  ("local", "Listo para<br>retirar 💵")],
        "activo": 1,
    },
    "retiro_listo": {
        "subtitulo": "Retiro en el local · Avellaneda",
        "nota": "Montes de Oca 589, Avellaneda",
        "pasos": [("check", "Pedido<br>confirmado"), ("caja", "En<br>preparación"),
                  ("local", "Listo para<br>retirar")],
        "activo": 2,
    },
    # ---------- PAGO PENDIENTE (transferencia sin acreditar) ----------
    "pago_pendiente": {
        "titulo": "Tu pedido está reservado",
        "subtitulo": "Esperando la acreditación del pago",
        "nota": "En cuanto se acredite, lo preparamos",
        "pasos": [("reloj", "Esperando<br>pago"), ("caja", "En<br>preparación"),
                  ("moto", "En<br>camino"), ("casa", "Entregado")],
        "activo": 0,
    },
}

# ---------------------------------------------------------------------------
# Mapeo template de WhatsApp -> placa. Es la tabla que consume el resolver n8n.
# ---------------------------------------------------------------------------
MAPEO_TEMPLATES = {
    "seg_conf_online_moto": "moto_online_prep",
    "seg_conf_efec_moto": "moto_efec_prep",
    "seg_conf_online_correo": "correo_prep",
    "seg_conf_online_retiro": "retiro_online_prep",
    "seg_conf_efec_retiro": "retiro_efec_prep",
    "seg_pago_pendiente": "pago_pendiente",
    "seg_pago_acreditado": "moto_online_prep",   # genérico "ya pagaste, preparando"
    "seg_camino_moto": "moto_online_camino",
    "seg_camino_moto_efec": "moto_efec_camino",
    "seg_despachado_correo": "correo_despachado",
    "seg_camino_sucursal": "sucursal_camino",
    "seg_listo_retiro": "retiro_listo",
    # seg_reconv_efec_correo: SIN placa a propósito (es un mensaje de problema)
}


def cargar_logo_html() -> str:
    """Devuelve el <img> del logo con la imagen empotrada en base64.

    Si no encuentra el archivo, cae al wordmark de texto para que el render
    nunca falle (y avisa por consola).
    """
    candidatos = list(LOGO_CANDIDATOS)
    # último recurso: cualquier archivo con "logo" en el nombre dentro del cliente
    base = ROOT / "clients" / "morashop"
    if base.exists():
        for ext in ("png", "jpg", "jpeg", "webp"):
            candidatos.extend(sorted(base.rglob(f"*logo*.{ext}")))

    for path in candidatos:
        if path.exists():
            mime = mimetypes.guess_type(path.name)[0] or "image/png"
            b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            print(f"  logo: {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")
            return f'<img class="logo" src="data:{mime};base64,{b64}" alt="MoraShop">'

    print("  ⚠ logo no encontrado, uso wordmark de texto.")
    print("     Subí el archivo a: clients/morashop/assets/logo.png")
    print("     (o cualquier archivo con 'logo' en el nombre dentro de clients/morashop/)")
    return '<div class="marca">MORASHOP</div>'


def construir_html(nombre: str, spec: dict, template: str, logo_html: str = "") -> str:
    pasos = spec["pasos"]
    activo = spec["activo"]
    n = len(pasos)
    col = 100 / n

    fragmentos = []
    for i, (icono, label) in enumerate(pasos):
        if i < activo:
            estado, icono_final = "done", "check"
        elif i == activo:
            estado, icono_final = "active", icono
        else:
            estado, icono_final = "pending", icono
        fragmentos.append(paso_html(estado, icono_final, label).replace("{col}", f"{col:.4f}"))

    # la barra nace en el centro del primer círculo y muere en el del último
    rail_inset = f"{col / 2:.4f}%"
    # progreso hasta el centro del paso activo
    rail_progress = f"{(activo / (n - 1) * 100):.2f}%" if n > 1 else "0%"

    return (
        template
        .replace("{logo_html}", logo_html)
        .replace("{titulo}", spec.get("titulo", "Tu pedido, paso a paso"))
        .replace("{subtitulo}", spec["subtitulo"])
        .replace("{nota}", spec.get("nota", ""))
        .replace("{pasos_html}", "\n            ".join(fragmentos))
        .replace("{rail_inset}", rail_inset)
        .replace("{rail_progress}", rail_progress)
    )


def render(placas: dict, template: str) -> dict:
    from playwright.sync_api import sync_playwright

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    generados = {}
    logo_html = cargar_logo_html()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT},
                                device_scale_factor=1)
        for nombre, spec in placas.items():
            html = construir_html(nombre, spec, template, logo_html)
            tmp_html = OUT_DIR / f"{nombre}.html"
            tmp_html.write_text(html, encoding="utf-8")
            page.goto(f"file://{tmp_html}")
            page.wait_for_timeout(600)  # que terminen de cargar las Google Fonts
            png = OUT_DIR / f"{nombre}.png"
            page.screenshot(path=str(png))
            generados[nombre] = png
            print(f"  ✓ {nombre}.png")
        browser.close()

    return generados


def subir(generados: dict) -> dict:
    import cloudinary
    import cloudinary.uploader

    if os.getenv("CLOUDINARY_URL"):
        cloudinary.config(secure=True)
    else:
        cloudinary.config(
            cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
            api_key=os.environ["CLOUDINARY_API_KEY"],
            api_secret=os.environ["CLOUDINARY_API_SECRET"],
            secure=True,
        )

    urls = {}
    for nombre, path in generados.items():
        res = cloudinary.uploader.upload(
            str(path),
            public_id=f"{CLOUDINARY_FOLDER}/{nombre}",
            overwrite=True,          # mismo public_id => misma URL siempre
            invalidate=True,         # purga la CDN al reemplazar el diseño
            resource_type="image",
        )
        urls[nombre] = res["secure_url"]
        print(f"  ↑ {nombre}: {res['secure_url']}")
    return urls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-upload", action="store_true", help="solo generar PNG local")
    ap.add_argument("--solo", default=None, help="generar una sola placa por nombre")
    args = ap.parse_args()

    if not TEMPLATE_PATH.exists():
        sys.exit(f"❌ No existe el template: {TEMPLATE_PATH}")
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    placas = PLACAS
    if args.solo:
        if args.solo not in PLACAS:
            sys.exit(f"❌ Placa desconocida: {args.solo}\nDisponibles: {', '.join(PLACAS)}")
        placas = {args.solo: PLACAS[args.solo]}

    print(f"Generando {len(placas)} placa(s) en {OUT_DIR} ...")
    generados = render(placas, template)

    if args.no_upload:
        print(f"\nListo. PNG en {OUT_DIR} (no se subió nada).")
        return

    print("\nSubiendo a Cloudinary ...")
    urls = subir(generados)

    print("\n" + "=" * 78)
    print("MAPEO PARA EL RESOLVER DE n8n (template de WhatsApp -> URL de placa)")
    print("=" * 78)
    print("const PLACAS = {")
    for tpl, placa in MAPEO_TEMPLATES.items():
        if placa in urls:
            print(f'  {tpl}: "{urls[placa]}",')
    print("};")
    print("=" * 78)


if __name__ == "__main__":
    main()
