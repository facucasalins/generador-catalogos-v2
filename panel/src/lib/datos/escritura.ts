import "server-only";
// Todo lo que el panel escribe en las sheets de un cliente.
import { PLATAFORMAS, type Cliente } from "../config";
import { planificar, type Cambio } from "../seleccion-plan";
import {
  actualizarEstructura,
  escribirRangos,
  idPestana,
  leerPestanasFresco,
  letraColumna,
  rango,
  texto,
  type Celda,
} from "../sheets";

const FILAS_CHECKBOX = 1000; // mismo valor que el Apps Script

function exigirSeleccion(c: Cliente): string {
  if (!c.seleccionSheetId) throw new Error(`${c.nombre} no tiene sheet de Selección configurada.`);
  return c.seleccionSheetId;
}

/** Aplica cambios a la Selección. Cada cambio trae el conjunto FINAL de templates del SKU. */
export async function aplicarCambiosSeleccion(c: Cliente, cambios: Cambio[]): Promise<{ filas: number; columnasNuevas: string[] }> {
  if (cambios.length === 0) return { filas: 0, columnasNuevas: [] };
  const sheetId = exigirSeleccion(c);
  const pestana = c.seleccionPestana;

  let filas = (await leerPestanasFresco(sheetId, [pestana]))[pestana];
  if (filas.length === 0) throw new Error("La pestaña Seleccion está vacía o no existe.");
  let header = filas[0].map((h) => texto(h));
  let plan = planificar(header, filas.slice(1), cambios);

  // 1) Columnas de templates que todavía no existen: se insertan antes de "prioridad",
  //    con checkbox, igual que lo haría el Apps Script.
  if (plan.columnasNuevas.length) {
    const gid = await idPestana(sheetId, pestana);
    const n = plan.columnasNuevas.length;
    const i0 = plan.indiceInsercion;
    await actualizarEstructura(sheetId, [
      { insertDimension: { range: { sheetId: gid, dimension: "COLUMNS", startIndex: i0, endIndex: i0 + n }, inheritFromBefore: true } },
      {
        setDataValidation: {
          range: { sheetId: gid, startRowIndex: 1, endRowIndex: FILAS_CHECKBOX + 1, startColumnIndex: i0, endColumnIndex: i0 + n },
          rule: { condition: { type: "BOOLEAN" } },
        },
      },
    ]);
    await escribirRangos(sheetId, [
      { rango: rango(pestana, `${letraColumna(i0)}1:${letraColumna(i0 + n - 1)}1`), valores: [plan.columnasNuevas] },
    ]);
    // Releo para escribir las filas sobre el layout nuevo.
    filas = (await leerPestanasFresco(sheetId, [pestana]))[pestana];
    header = filas[0].map((h) => texto(h));
    plan = planificar(header, filas.slice(1), cambios);
  }

  // 2) Filas.
  await escribirRangos(
    sheetId,
    plan.filas.map((f) => ({
      rango: rango(pestana, `${letraColumna(f.desde)}${f.fila}:${letraColumna(f.desde + f.valores.length - 1)}${f.fila}`),
      // null = columna fija en el medio (no debería pasar): se deja vacía.
      valores: [f.valores.map((v) => (v === null ? "" : v))],
    })),
  );
  return { filas: plan.filas.length, columnasNuevas: plan.columnasNuevas };
}

/** Lo tildado hoy para unos SKUs (para sumar templates sin perder los que ya tenían). */
export async function templatesActuales(c: Cliente, skus: string[]): Promise<Map<string, string[]>> {
  const sheetId = exigirSeleccion(c);
  const filas = (await leerPestanasFresco(sheetId, [c.seleccionPestana]))[c.seleccionPestana];
  const header = (filas[0] ?? []).map((h) => texto(h));
  const buscados = new Set(skus);
  const res = new Map<string, string[]>();
  for (const f of filas.slice(1)) {
    const sku = texto(f[0]);
    if (!buscados.has(sku) || res.has(sku)) continue;
    const generar = esVerdadero(f[1]);
    res.set(
      sku,
      generar ? header.filter((h, i) => i > 1 && !["prioridad", "notas"].includes(h) && esVerdadero(f[i])) : [],
    );
  }
  return res;
}

const esVerdadero = (v: Celda | undefined) => v === true || ["TRUE", "SI", "X", "1", "YES"].includes(texto(v).toUpperCase());

// ---------- Pestaña Templates (la usa el Apps Script para armar las columnas) ----------

const HEADERS_TEMPLATES = ["nombre_template", "descripcion", "aspect_ratio", "width", "height", "activo"];

/** Agrega (o actualiza) las filas Meta_x y TikTok_x de un template en la pestaña Templates. */
export async function registrarTemplateEnSheet(
  c: Cliente,
  t: { nombre: string; descripcion: string; aspect_ratio: string; width: number; height: number },
): Promise<void> {
  const sheetId = exigirSeleccion(c);
  const filas = (await leerPestanasFresco(sheetId, ["Templates"]))["Templates"];
  if (filas.length === 0) return; // la crea el pipeline en la próxima corrida
  const nombres = filas.map((f) => texto(f[0]));
  const escrituras: { rango: string; valores: Celda[][] }[] = [];
  let siguiente = filas.length + 1;
  for (const p of PLATAFORMAS) {
    const nombre = `${p}_${t.nombre}`;
    const fila = [nombre, t.descripcion ? `${p} · ${t.descripcion}` : p, t.aspect_ratio, t.width, t.height, "SI"];
    const existente = nombres.indexOf(nombre);
    const nro = existente >= 1 ? existente + 1 : siguiente++;
    escrituras.push({ rango: rango("Templates", `A${nro}:F${nro}`), valores: [fila] });
  }
  await escribirRangos(sheetId, escrituras);
}

/**
 * Elimina un template de la Selección: borra sus columnas Meta_x y TikTok_x
 * (con todas sus marcas) y sus filas de la pestaña Templates.
 */
export async function quitarTemplateDeSheets(c: Cliente, nombre: string): Promise<{ skusAfectados: number }> {
  const sheetId = exigirSeleccion(c);
  const pestana = c.seleccionPestana;
  const objetivo = new Set(PLATAFORMAS.map((p) => `${p}_${nombre}`));
  const leido = await leerPestanasFresco(sheetId, [pestana, "Templates"]);

  const sel = leido[pestana];
  const header = (sel[0] ?? []).map((h) => texto(h));
  const indices = header.map((h, i) => (objetivo.has(h) ? i : -1)).filter((i) => i >= 0);
  const skusAfectados = sel.slice(1).filter((f) => texto(f[0]) && indices.some((i) => esVerdadero(f[i]))).length;

  const requests: unknown[] = [];
  if (indices.length) {
    const gidSel = await idPestana(sheetId, pestana);
    // De derecha a izquierda para que los índices no se corran.
    for (const i of [...indices].sort((a, b) => b - a)) {
      requests.push({ deleteDimension: { range: { sheetId: gidSel, dimension: "COLUMNS", startIndex: i, endIndex: i + 1 } } });
    }
  }
  const tpl = leido["Templates"];
  const filasTpl = tpl.map((f, i) => (objetivo.has(texto(f[0])) ? i : -1)).filter((i) => i >= 1);
  if (filasTpl.length) {
    const gidTpl = await idPestana(sheetId, "Templates");
    for (const i of [...filasTpl].sort((a, b) => b - a)) {
      requests.push({ deleteDimension: { range: { sheetId: gidTpl, dimension: "ROWS", startIndex: i, endIndex: i + 1 } } });
    }
  }
  await actualizarEstructura(sheetId, requests);
  return { skusAfectados };
}

export { HEADERS_TEMPLATES };
