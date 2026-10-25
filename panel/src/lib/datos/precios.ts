// Port de src/inventario/precios_override.py: parsear_precio y construir_mapa.
import type { Celda } from "../sheets";

export function parsearPrecio(valor: Celda | undefined): number | null {
  if (valor === null || valor === undefined) return null;
  if (typeof valor === "number") return valor;
  if (typeof valor === "boolean") return null;
  let s = String(valor).replace(/[^0-9.,]/g, "");
  if (!s) return null;
  if (s.includes(".") && s.includes(",")) {
    s = s.lastIndexOf(",") > s.lastIndexOf(".") ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, "");
  } else if (s.includes(",") || s.includes(".")) {
    const sep = s.includes(",") ? "," : ".";
    const partes = s.split(sep);
    s = partes.length > 2 || partes[partes.length - 1].length === 3 ? s.split(sep).join("") : s.split(sep).join(".");
  }
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

export function construirMapaPrecios(
  filas: Celda[][],
  cols: { colSku: string; colPrecioLista: string; colPrecioPromo: string },
): Map<string, [number, number]> {
  const mapa = new Map<string, [number, number]>();
  if (filas.length === 0) return mapa;
  const headers = filas[0].map((h) => String(h ?? "").trim());
  const iSku = headers.indexOf(cols.colSku);
  const iLista = headers.indexOf(cols.colPrecioLista);
  const iPromo = headers.indexOf(cols.colPrecioPromo);
  if (iSku < 0 || iLista < 0 || iPromo < 0) return mapa;
  for (const fila of filas.slice(1)) {
    const sku = String(fila[iSku] ?? "").trim();
    if (!sku) continue;
    const lista = parsearPrecio(fila[iLista]);
    const promo = parsearPrecio(fila[iPromo]);
    if (!lista || !promo || lista <= 0 || promo <= 0 || promo > lista) continue;
    mapa.set(sku, [lista, promo]);
  }
  return mapa;
}
