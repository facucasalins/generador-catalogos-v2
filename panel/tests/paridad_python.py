"""Calcula las variables de render con el código REAL del pipeline.

Lo usa tests/variables.test.ts para comparar la preview del panel (TypeScript)
contra src/estilo/playwright_html.py. Lee casos JSON por stdin y escribe
{caso_id: variables} por stdout. Las imágenes no se descargan: se devuelve la
URL tal cual, igual que hace la preview.

Uso (desde la raíz del repo):
    python panel/tests/paridad_python.py < casos.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.core.modelo_datos import Producto, DecisionSeleccion  # noqa: E402
from src.estilo.playwright_html import (  # noqa: E402
    ConfigPlaywrightHtml,
    PlaywrightHtmlEstilo,
)


def main() -> None:
    casos = json.load(sys.stdin)
    salida = {}
    for caso in casos:
        p, e = caso["producto"], caso["estilo"]
        motor = PlaywrightHtmlEstilo.__new__(PlaywrightHtmlEstilo)
        motor.cfg = ConfigPlaywrightHtml(
            templates_dir=Path("."),
            output_dir=Path("."),
            variables_globales=e["variablesGlobales"],
            hotsale_discount_factor=e["hotsaleDiscountFactor"],
            descuento_efectivo_factor=e["descuentoEfectivoFactor"],
            cuotas_sobre_promocional=e["cuotasSobrePromocional"],
        )
        motor._cache_imagenes = {}
        motor._descargar_imagen_a_base64 = lambda url: url
        producto = Producto(
            sku=p["sku"],
            nombre=p["nombre"],
            # Tiendanube y override siempre entregan float (_a_float / parsear_precio).
            precio_lista=float(p["precioLista"]),
            precio_promocional=None if p["precioPromocional"] is None else float(p["precioPromocional"]),
            cuotas_num=p["cuotasNum"],
            marca=p["marca"],
            categoria=p["categoria"],
            imagen_url=p["imagenUrl"],
            enriquecimiento={
                k: v
                for k, v in (("titulo_placa", p.get("tituloPlaca")), ("titulo_corto", p.get("tituloCorto")))
                if v
            },
        )
        decision = DecisionSeleccion(sku=p["sku"], generar=True, template="Meta_x")
        salida[caso["id"]] = motor._construir_variables(producto, decision)
    json.dump(salida, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
