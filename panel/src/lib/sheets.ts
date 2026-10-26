import "server-only";
import { tokenGoogle } from "./google";

export type Celda = string | number | boolean | null;
export type Filas = Celda[][];

// Caché corto en memoria. Panel y pipeline comparten la cuota de la API de
// Sheets (misma cuenta de servicio): 60 s evita que cada recarga del panel
// gaste lecturas y sigue mostrando datos frescos.
const TTL_MS = 60_000;
const cache = new Map<string, { vence: number; valor: Promise<Record<string, Filas>> }>();

export class ErrorSheets extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

/**
 * Lee varias pestañas de una misma sheet en una sola llamada.
 * Valores SIN formato (números como números): así "39999" no llega como
 * "$39.999" ni depende del idioma de la planilla.
 * Una pestaña que no existe vuelve como [] en lugar de fallar todo el lote.
 */
export async function leerPestanas(sheetId: string, pestanas: string[]): Promise<Record<string, Filas>> {
  const clave = `${sheetId}::${pestanas.join("|")}`;
  const ahora = Date.now();
  const enCache = cache.get(clave);
  if (enCache && enCache.vence > ahora) return enCache.valor;

  const valor = leerSinCache(sheetId, pestanas);
  cache.set(clave, { vence: ahora + TTL_MS, valor });
  valor.catch(() => cache.delete(clave));
  return valor;
}

async function leerSinCache(sheetId: string, pestanas: string[]): Promise<Record<string, Filas>> {
  const token = await tokenGoogle();
  const resultado: Record<string, Filas> = {};
  // batchGet falla entero si una pestaña no existe; primero averiguo cuáles hay.
  const existentes = await pestanasExistentes(sheetId, token);
  const aLeer = pestanas.filter((p) => existentes.has(p));
  for (const p of pestanas) resultado[p] = [];
  if (aLeer.length === 0) return resultado;

  const params = new URLSearchParams({ valueRenderOption: "UNFORMATTED_VALUE", majorDimension: "ROWS" });
  for (const p of aLeer) params.append("ranges", `'${p.replace(/'/g, "''")}'`);
  const resp = await fetch(
    `https://sheets.googleapis.com/v4/spreadsheets/${sheetId}/values:batchGet?${params}`,
    { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" },
  );
  if (!resp.ok) throw await errorDeRespuesta(resp, sheetId);
  const json = (await resp.json()) as { valueRanges?: { values?: Filas }[] };
  (json.valueRanges ?? []).forEach((vr, i) => {
    resultado[aLeer[i]] = vr.values ?? [];
  });
  return resultado;
}

/** Nombres de las pestañas de una sheet, en orden. */
export async function nombresPestanas(sheetId: string): Promise<string[]> {
  const token = await tokenGoogle();
  return [...(await pestanasExistentes(sheetId, token))];
}

async function pestanasExistentes(sheetId: string, token: string): Promise<Set<string>> {
  const resp = await fetch(
    `https://sheets.googleapis.com/v4/spreadsheets/${sheetId}?fields=sheets.properties.title`,
    { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" },
  );
  if (!resp.ok) throw await errorDeRespuesta(resp, sheetId);
  const json = (await resp.json()) as { sheets?: { properties: { title: string } }[] };
  return new Set((json.sheets ?? []).map((s) => s.properties.title));
}

async function errorDeRespuesta(resp: Response, sheetId: string): Promise<ErrorSheets> {
  if (resp.status === 403 || resp.status === 404) {
    return new ErrorSheets(
      `La cuenta de servicio no tiene acceso a la sheet ${sheetId}. Compartila con ella como lector o editor.`,
      resp.status,
    );
  }
  if (resp.status === 429) {
    return new ErrorSheets("Google Sheets limitó las lecturas por cuota. Probá de nuevo en un minuto.", 429);
  }
  const texto = await resp.text().catch(() => "");
  return new ErrorSheets(`Error ${resp.status} leyendo la sheet ${sheetId}: ${texto.slice(0, 200)}`, resp.status);
}

/** Descarta lo cacheado de una sheet: después de escribir, la próxima lectura va a Google. */
export function invalidarCache(sheetId: string): void {
  for (const clave of cache.keys()) if (clave.startsWith(`${sheetId}::`)) cache.delete(clave);
}

/** Lectura sin caché (para leer-modificar-escribir sin pisar cambios ajenos). */
export async function leerPestanasFresco(sheetId: string, pestanas: string[]): Promise<Record<string, Filas>> {
  invalidarCache(sheetId);
  return leerPestanas(sheetId, pestanas);
}

async function llamar<T>(sheetId: string, ruta: string, body: unknown): Promise<T> {
  const token = await tokenGoogle();
  const resp = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${sheetId}${ruta}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!resp.ok) throw await errorDeRespuesta(resp, sheetId);
  return (await resp.json()) as T;
}

const citar = (pestana: string) => `'${pestana.replace(/'/g, "''")}'`;

/** Escribe varios rangos de una vez. Los booleanos quedan como checkbox TRUE/FALSE. */
export async function escribirRangos(sheetId: string, datos: { rango: string; valores: Celda[][] }[]): Promise<void> {
  if (datos.length === 0) return;
  await llamar(sheetId, "/values:batchUpdate", {
    valueInputOption: "RAW",
    data: datos.map((d) => ({ range: d.rango, majorDimension: "ROWS", values: d.valores })),
  });
  invalidarCache(sheetId);
}

/** ID numérico de una pestaña (lo piden las operaciones de estructura). */
export async function idPestana(sheetId: string, pestana: string): Promise<number> {
  const token = await tokenGoogle();
  const resp = await fetch(
    `https://sheets.googleapis.com/v4/spreadsheets/${sheetId}?fields=sheets.properties(sheetId,title)`,
    { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" },
  );
  if (!resp.ok) throw await errorDeRespuesta(resp, sheetId);
  const json = (await resp.json()) as { sheets: { properties: { sheetId: number; title: string } }[] };
  const p = json.sheets.find((s) => s.properties.title === pestana);
  if (!p) throw new ErrorSheets(`La sheet ${sheetId} no tiene la pestaña «${pestana}».`, 404);
  return p.properties.sheetId;
}

/** Operaciones de estructura (insertar o borrar columnas, checkboxes). */
export async function actualizarEstructura(sheetId: string, requests: unknown[]): Promise<void> {
  if (requests.length === 0) return;
  await llamar(sheetId, ":batchUpdate", { requests });
  invalidarCache(sheetId);
}

/** Letra de columna A1 para un índice 0-based (0 → A, 26 → AA). */
export function letraColumna(indice: number): string {
  let n = indice + 1;
  let s = "";
  while (n > 0) {
    const r = (n - 1) % 26;
    s = String.fromCharCode(65 + r) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

export function rango(pestana: string, a1: string): string {
  return `${citar(pestana)}!${a1}`;
}

/** Convierte filas con header en objetos { columna: valor }. */
export function aObjetos(filas: Filas): Record<string, Celda>[] {
  if (filas.length < 2) return [];
  const header = filas[0].map((h) => String(h ?? "").trim());
  return filas.slice(1).map((fila) => {
    const obj: Record<string, Celda> = {};
    header.forEach((col, i) => {
      if (col) obj[col] = fila[i] ?? null;
    });
    return obj;
  });
}

export function texto(v: Celda | undefined): string {
  return v === null || v === undefined ? "" : String(v).trim();
}

export function numero(v: Celda | undefined): number | null {
  if (v === null || v === undefined || v === "") return null;
  if (typeof v === "number") return v;
  const n = Number(String(v).replace(",", "."));
  return Number.isFinite(n) ? n : null;
}

// Misma normalización que SeleccionManualSheet._es_si.
export function esSi(v: Celda | undefined): boolean {
  if (typeof v === "boolean") return v;
  if (typeof v === "number") return v !== 0;
  return ["TRUE", "SI", "YES", "X", "1"].includes(texto(v).toUpperCase());
}
