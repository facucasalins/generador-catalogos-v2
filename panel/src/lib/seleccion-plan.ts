// Planifica cómo escribir cambios en la pestaña Seleccion sin romper su formato:
//   sku | generar | <Meta_x, TikTok_x… ordenados> | prioridad | notas
// Es el mismo orden que mantiene el Apps Script de la sheet
// (clients/_template/sheet_apps_script.gs) y que lee sheet_manual.py.
import type { Celda } from "./sheets";

export const FIJAS = ["sku", "generar", "prioridad", "notas"];

export type Cambio = {
  sku: string;
  // Conjunto FINAL de templates tildados (con prefijo de plataforma). [] = quitar.
  templates: string[];
};

export type Plan = {
  // Columnas a insertar, en orden, justo antes de "prioridad".
  columnasNuevas: string[];
  indiceInsercion: number; // 0-based, en el header original
  // Escrituras de filas sobre el header YA con las columnas nuevas.
  filas: { fila: number; desde: number; valores: Celda[] }[]; // fila 1-based; desde = col 0-based
};

const texto = (v: Celda | undefined) => (v === null || v === undefined ? "" : String(v).trim());

export function planificar(header: string[], filas: Celda[][], cambios: Cambio[]): Plan {
  const hdr = header.map((h) => h.trim());
  if (hdr[0] !== "sku" || hdr[1] !== "generar") {
    throw new Error("La pestaña Seleccion no tiene el formato esperado (sku | generar | …). No la modifico.");
  }
  const existentes = new Set(hdr.filter((h) => h && !FIJAS.includes(h)));
  const pedidas = new Set(cambios.flatMap((c) => c.templates));
  const columnasNuevas = [...pedidas].filter((t) => !existentes.has(t)).sort();

  let indiceInsercion = hdr.indexOf("prioridad");
  if (indiceInsercion < 0) indiceInsercion = hdr.length;

  // Header final, tal como queda después de insertar.
  const final = [...hdr.slice(0, indiceInsercion), ...columnasNuevas, ...hdr.slice(indiceInsercion)];
  const colsTemplate = final.map((h, i) => [h, i] as const).filter(([h]) => h && !FIJAS.includes(h));
  const ultimaTemplate = colsTemplate.length ? colsTemplate[colsTemplate.length - 1][1] : 1;

  // Filas existentes por SKU (fila de sheet 1-based; la 1 es el header).
  const filaDeSku = new Map<string, number>();
  const libres: number[] = [];
  filas.forEach((f, i) => {
    const sku = texto(f[0]);
    const nro = i + 2;
    if (sku) {
      if (!filaDeSku.has(sku)) filaDeSku.set(sku, nro);
    } else libres.push(nro);
  });
  let siguienteNueva = filas.length + 2;

  const escrituras: Plan["filas"] = [];
  for (const c of cambios) {
    const marcadas = new Set(c.templates);
    // Desde la columna B (generar) hasta la última de templates.
    const valores: Celda[] = [];
    for (let col = 1; col <= ultimaTemplate; col++) {
      const h = final[col];
      valores.push(col === 1 ? marcadas.size > 0 : FIJAS.includes(h) ? null : marcadas.has(h));
    }
    let fila = filaDeSku.get(c.sku);
    if (fila) {
      escrituras.push({ fila, desde: 1, valores });
    } else {
      if (marcadas.size === 0) continue; // quitar algo que no está: nada que hacer
      fila = libres.shift() ?? siguienteNueva++;
      filaDeSku.set(c.sku, fila);
      escrituras.push({ fila, desde: 0, valores: [c.sku, ...valores] });
    }
  }
  return { columnasNuevas, indiceInsercion, filas: escrituras };
}
