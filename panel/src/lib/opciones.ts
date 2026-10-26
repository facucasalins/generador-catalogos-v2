import "server-only";
import type { OpcionProducto } from "@/components/EditorPreview";
import { separarTemplate } from "./config";
import type { Inventario, Seleccion } from "./datos";
import { aProductoRender } from "./render/preparar";
import { filasActivas } from "./resumen";

/** Productos para probar un template: marca como "seleccionados" los que lo usan (o, si ninguno, los seleccionados en general). */
export function opcionesDeProductos(inv: Inventario, sel: Seleccion, template?: string): OpcionProducto[] {
  const activas = filasActivas(sel.filas);
  const usan = template ? activas.filter((f) => f.templates.some((x) => separarTemplate(x).base === template)) : [];
  const marcados = new Set((usan.length ? usan : activas).map((f) => f.sku));
  return inv.productos
    .filter((p) => p.imagenUrl)
    .map((p) => ({ ...aProductoRender(p), seleccionado: marcados.has(p.sku), tieneStock: p.tieneStock }));
}
