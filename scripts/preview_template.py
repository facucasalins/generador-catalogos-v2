"""
Preview local de templates - Generador de catálogos v2
========================================================

Renderiza UNA placa con datos de prueba para que puedas iterar visualmente
sin correr el pipeline completo (que demora ~10 min y necesita TN, Cloudinary, etc).

USO:
    # Default: renderiza template "default" de morashop en 4:5 (1080x1350)
    python scripts/preview_template.py

    # Especificar cliente y template
    python scripts/preview_template.py --cliente=morashop --template=electro

    # Probar el template 9:16 (TikTok)
    python scripts/preview_template.py --template=default --aspect=9:16

    # Usar datos de prueba customizados
    python scripts/preview_template.py --template=default --imagen=https://ejemplo.com/foto.png

    # Output personalizado
    python scripts/preview_template.py --output=/tmp/mi_preview.png

QUÉ HACE:
    1. Lee el HTML del template desde clients/<cliente>/templates/
    2. Inyecta datos mock (precios, imagen de producto, logo, etc.)
    3. Llama a Playwright para renderizar en PNG
    4. Abre el PNG en tu visor de imágenes default

REQUIERE:
    - Playwright instalado (pip install playwright && playwright install chromium)
    - Que exista el archivo del template en clients/<cliente>/templates/<template>.html

NO REQUIERE:
    - Credenciales (TN, Cloudinary, etc.) — todo es local con datos mock
    - Internet (a menos que uses imágenes externas)
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Hacks de path para que `from src.X` funcione cuando lo corrés desde la raíz
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.core.modelo_datos import Producto, DecisionSeleccion
from src.estilo.playwright_html import PlaywrightHtmlEstilo, ConfigPlaywrightHtml


# ============ DATOS MOCK DE PRUEBA ============
# Estos son los valores con los que se renderiza la placa de prueba.
# Cambialos si querés ver tu template con otros datos.

PRODUCTO_DEMO = Producto(
    sku="DEMO_SKU_123",
    nombre="Producto de prueba para preview de template",
    descripcion="Este es un producto demo para iterar diseños visualmente",
    precio_lista=12500.0,
    precio_promocional=9999.0,
    cuotas_num=3,
    stock=50,
    categoria="Demo",
    marca="MARCA DEMO",
    imagen_url="https://acdn-us.mitiendanube.com/stores/002/268/228/products/whey-cookies-1-d10dd2d8eb7e93651b17170418200002-640-0.png",
    url_producto="https://example.com/producto",
)

# Aspect ratios soportados
ASPECT_RATIOS = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
}

# Variables globales por defecto. Si el cliente tiene un logo distinto en su
# pipeline.yaml, pasalo con --logo-url
LOGO_MORASHOP = "https://acdn-us.mitiendanube.com/stores/002/268/228/themes/toluca/img-479084497-1715570316-13b884ee9ca022bcfa337bfec6db35451715570316.png?3248503917"

VARIABLES_GLOBALES_DEFAULT = {
    "brand_name": "MORASHOP",
    "logo_url": LOGO_MORASHOP,
    "evento_legal": "Preview local - datos mock",
}


def abrir_imagen(path: Path) -> None:
    """Abre la imagen con el viewer default del SO. Best-effort, no rompe si falla."""
    try:
        if sys.platform == "darwin":  # macOS
            subprocess.run(["open", str(path)], check=False)
        elif sys.platform == "win32":
            os.startfile(str(path))  # type: ignore
        else:  # Linux
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception as e:
        print(f"⚠️  No pude abrir el visor automáticamente: {e}")
        print(f"   Abrí manualmente: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview local de templates HTML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--cliente", default="morashop",
                        help="Nombre del cliente (carpeta en clients/). Default: morashop")
    parser.add_argument("--template", default="default",
                        help="Nombre del template SIN .html ni sufijo. Default: default")
    parser.add_argument("--aspect", default="4:5", choices=list(ASPECT_RATIOS.keys()),
                        help="Aspect ratio. 4:5 = Meta (1080x1350), 9:16 = TikTok (1080x1920)")
    parser.add_argument("--imagen", default=None,
                        help="URL de imagen de producto custom (default: imagen de prueba)")
    parser.add_argument("--nombre", default=None,
                        help="Nombre del producto custom")
    parser.add_argument("--precio-lista", type=float, default=None,
                        help="Precio lista custom (default: 12500)")
    parser.add_argument("--precio-promo", type=float, default=None,
                        help="Precio promo custom (default: 9999)")
    parser.add_argument("--logo-url", default=None,
                        help="URL del logo custom (default: logo de MoraShop)")
    parser.add_argument("--output", default=None,
                        help="Path del PNG de salida (default: /tmp/preview_<template>_<aspect>.png)")
    parser.add_argument("--no-abrir", action="store_true",
                        help="No abrir la imagen al terminar (útil para CI/scripts)")
    args = parser.parse_args()

    # Construir el nombre del template real (con sufijo de aspect_ratio si aplica)
    if args.aspect == "9:16":
        template_real = f"{args.template}_tiktok"
    else:
        template_real = args.template

    # Validar paths
    templates_dir = ROOT / "clients" / args.cliente / "templates"
    template_file = templates_dir / f"{template_real}.html"

    if not templates_dir.exists():
        print(f"❌ No existe la carpeta: {templates_dir}")
        print(f"   ¿Está bien el nombre del cliente '{args.cliente}'?")
        return 1

    if not template_file.exists():
        print(f"❌ No existe el template: {template_file}")
        print(f"   Templates disponibles en {templates_dir}:")
        for f in sorted(templates_dir.glob("*.html")):
            print(f"     - {f.stem}")
        return 1

    # Construir producto demo (puede pisarse con args CLI)
    producto = PRODUCTO_DEMO
    if args.nombre:
        producto.nombre = args.nombre
    if args.imagen:
        producto.imagen_url = args.imagen
    if args.precio_lista:
        producto.precio_lista = args.precio_lista
    if args.precio_promo:
        producto.precio_promocional = args.precio_promo

    # Variables globales
    variables = dict(VARIABLES_GLOBALES_DEFAULT)
    if args.logo_url:
        variables["logo_url"] = args.logo_url

    # Output path
    if args.output:
        output_path = Path(args.output)
    else:
        aspect_safe = args.aspect.replace(":", "x")
        output_path = Path("/tmp") / f"preview_{args.cliente}_{template_real}_{aspect_safe}.png"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Dimensiones
    width, height = ASPECT_RATIOS[args.aspect]

    # Configurar motor de render
    motor_config = ConfigPlaywrightHtml(
        templates_dir=templates_dir,
        output_dir=output_path.parent,
        placa_width=width,
        placa_height=height,
        variables_globales=variables,
        hotsale_discount_factor=1.0,
    )

    decision = DecisionSeleccion(
        sku=producto.sku,
        generar=True,
        template=template_real,
        prioridad=1,
    )

    print(f"🎨 Renderizando preview:")
    print(f"   Cliente:  {args.cliente}")
    print(f"   Template: {template_real} ({args.aspect}, {width}x{height})")
    print(f"   Producto: {producto.nombre[:50]}...")
    print(f"   Precio:   ${producto.precio_lista:.0f} → ${producto.precio_promocional:.0f}")
    print(f"   Output:   {output_path}")
    print()

    try:
        with PlaywrightHtmlEstilo(motor_config) as motor:
            placa = motor.renderizar(producto, decision)
        # El motor escribe en output_dir/<sku>.png o <sku>_9x16.png
        # Movemos al output_path solicitado (si difiere)
        placa_generada = Path(placa.path_local)
        if placa_generada != output_path:
            placa_generada.replace(output_path)
        print(f"✅ Listo: {output_path}")
        print(f"   Tamaño: {output_path.stat().st_size / 1024:.1f} KB")
    except Exception as e:
        print(f"❌ Falló render: {e}")
        import traceback
        traceback.print_exc()
        return 1

    if not args.no_abrir:
        abrir_imagen(output_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
