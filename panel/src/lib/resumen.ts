import "server-only";
import { separarTemplate, type Cliente } from "./config";
import { obtenerCorridas, obtenerInventario, obtenerSeleccion, type Corrida, type Producto } from "./datos";

export type Alerta = { tipo: "error" | "alerta"; texto: string };

export type ResumenCliente = {
  cliente: Cliente;
  productos: number;
  skusSeleccionados: number;
  placasPedidas: number;
  placasVigentes: number;
  ultimaCorrida: Corrida | null;
  alertas: Alerta[];
  error: unknown | null;
};

/** Filas que el pipeline realmente procesa: generar=SI y al menos un template tildado. */
export function filasActivas<T extends { generar: boolean; templates: string[] }>(filas: T[]): T[] {
  return filas.filter((f) => f.generar && f.templates.length > 0);
}

/** Por qué un SKU seleccionado no va a generar placa (mismo filtro que sheet_manual.py). */
export function motivoDescarte(p: Producto | undefined): string | null {
  if (!p) return "no está en el inventario";
  if (!p.tieneStock) return "sin stock";
  if (!p.publicado) return "no publicado";
  return null;
}

export async function resumirCliente(cliente: Cliente): Promise<ResumenCliente> {
  const alertas: Alerta[] = [];
  const sinMeta = cliente.templates.filter((t) => !t.tieneMeta).map((t) => t.nombre);
  if (sinMeta.length) {
    alertas.push({
      tipo: "alerta",
      texto: `${sinMeta.length === 1 ? "1 template sin" : `${sinMeta.length} templates sin`} bloque META (se renderiza${sinMeta.length === 1 ? "" : "n"} 1080×1350): ${sinMeta.join(", ")}`,
    });
  }
  try {
    const [inv, sel, cor] = await Promise.all([
      obtenerInventario(cliente),
      obtenerSeleccion(cliente),
      obtenerCorridas(cliente, 1),
    ]);
    const porSku = new Map(inv.productos.map((p) => [p.sku, p]));
    const activas = filasActivas(sel.filas);
    const descartadas = activas.filter((f) => motivoDescarte(porSku.get(f.sku)));
    if (descartadas.length) {
      alertas.push({
        tipo: "alerta",
        texto: `${descartadas.length} ${descartadas.length === 1 ? "SKU seleccionado no va" : "SKUs seleccionados no van"} a salir: sin stock, sin publicar o fuera del inventario`,
      });
    }
    const repo = new Set(cliente.templates.map((t) => t.nombre));
    const huerfanas = sel.columnasTemplate.filter((c) => !repo.has(separarTemplate(c).base));
    if (huerfanas.length) {
      alertas.push({ tipo: "alerta", texto: `La Selección tiene columnas de templates que ya no existen: ${huerfanas.join(", ")}` });
    }
    const ultima = cor.corridas[0] ?? null;
    if (ultima?.estado === "fallida") alertas.unshift({ tipo: "error", texto: "La última corrida falló" });
    if (cor.aviso) alertas.push({ tipo: "alerta", texto: cor.aviso });

    return {
      cliente,
      productos: inv.productos.length,
      skusSeleccionados: activas.length,
      placasPedidas: activas.reduce((n, f) => n + f.templates.length, 0),
      placasVigentes: inv.placas.length,
      ultimaCorrida: ultima,
      alertas,
      error: null,
    };
  } catch (error) {
    console.error(`[resumen] ${cliente.slug}:`, error);
    return {
      cliente,
      productos: 0,
      skusSeleccionados: 0,
      placasPedidas: 0,
      placasVigentes: 0,
      ultimaCorrida: null,
      alertas,
      error,
    };
  }
}
