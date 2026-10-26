import "server-only";
// Capa única de acceso a datos. Las pantallas solo llaman a estas funciones;
// cuando pasemos a Supabase se reescribe este archivo, no el panel.
import { modoDemo, type Cliente } from "../config";
import { ErrorGithub, FaltaTokenGithub, listarRuns, pasosDeRun, type RunGithub } from "../github";
import { aObjetos, esSi, leerPestanas, leerPestanasFresco, numero, texto } from "../sheets";
import { construirMapaPrecios } from "./precios";
import { demoCorridas, demoPlacas, demoProductos, demoSeleccion } from "./demo";
import type { Corrida, FilaSeleccion, Placa, Producto, Seleccion } from "./tipos";

export type { Corrida, Placa, Producto, Seleccion, FilaSeleccion } from "./tipos";

// Nombres de pestañas definidos por el pipeline (sheet Inventario de cada cliente).
const PESTANA_HISTORIAL = "Historial_Placas"; // src/distribucion/historial.py
const PESTANA_ENRIQUECIMIENTO = "Enriquecimiento"; // src/enriquecimiento/sheet_cache.py

export type Inventario = { productos: Producto[]; placas: Placa[] };

export async function obtenerInventario(cliente: Cliente, { fresco = false } = {}): Promise<Inventario> {
  if (modoDemo) return { productos: demoProductos(cliente), placas: demoPlacas(cliente) };
  if (!cliente.inventarioSheetId) return { productos: [], placas: [] };

  const leer = fresco ? leerPestanasFresco : leerPestanas;
  const pestanas = await leer(cliente.inventarioSheetId, [
    cliente.inventarioPestana,
    PESTANA_ENRIQUECIMIENTO,
    PESTANA_HISTORIAL,
  ]);

  const enriquecimiento = new Map<string, { titulo_placa: string; titulo_corto: string }>();
  for (const f of aObjetos(pestanas[PESTANA_ENRIQUECIMIENTO])) {
    const sku = texto(f.sku);
    if (sku && !texto(f.error)) {
      enriquecimiento.set(sku, { titulo_placa: texto(f.titulo_placa), titulo_corto: texto(f.titulo_corto) });
    }
  }

  // Precios de evento: el pipeline los aplica después de escribir Inventario,
  // así que la placa y el feed usan estos y no los de Tiendanube.
  let preciosEvento = new Map<string, [number, number]>();
  if (cliente.preciosOverride) {
    const o = cliente.preciosOverride;
    const filas = await leerPestanas(o.sheetId, [o.pestana]);
    preciosEvento = construirMapaPrecios(filas[o.pestana], o);
  }

  const productos: Producto[] = aObjetos(pestanas[cliente.inventarioPestana])
    .filter((f) => texto(f.sku))
    .map((f) => {
      const sku = texto(f.sku);
      const enr = enriquecimiento.get(sku);
      const evento = preciosEvento.get(sku);
      return {
        sku,
        nombre: texto(f.nombre),
        precioLista: evento ? evento[0] : (numero(f.precio_lista) ?? 0),
        precioPromocional: evento ? evento[1] : numero(f.precio_promocional),
        stock: numero(f.stock),
        categoria: texto(f.categoria),
        marca: texto(f.marca),
        imagenUrl: texto(f.imagen_url),
        urlProducto: texto(f.url_producto),
        cuotasNum: numero(f.cuotas_num) ?? cliente.cuotasNum,
        publicado: esSi(f.tn_published),
        tieneStock: esSi(f.tn_has_stock),
        actualizadoEn: texto(f.actualizado_en),
        tituloPlaca: enr?.titulo_placa ?? "",
        tituloCorto: enr?.titulo_corto ?? "",
        conPrecioEvento: Boolean(evento),
      };
    });

  const placas: Placa[] = aObjetos(pestanas[PESTANA_HISTORIAL])
    .filter((f) => texto(f.sku) && texto(f.template))
    .map((f) => ({
      sku: texto(f.sku),
      template: texto(f.template),
      aspectRatio: texto(f.aspect_ratio) || "4:5",
      url: texto(f.url_cloudinary),
      fecha: texto(f.fecha_render),
      precioLista: numero(f.precio_lista),
      precioPromo: numero(f.precio_promo),
    }));

  return { productos, placas };
}

// Misma lectura que src/seleccion/sheet_manual.py: columnas fijas + una por template.
const COLUMNAS_FIJAS = new Set(["sku", "generar", "prioridad", "notas"]);

export async function obtenerSeleccion(cliente: Cliente): Promise<Seleccion> {
  if (modoDemo) return demoSeleccion(cliente);
  if (!cliente.seleccionSheetId) return { columnasTemplate: [], filas: [] };
  const pestanas = await leerPestanas(cliente.seleccionSheetId, [cliente.seleccionPestana]);
  const filasCrudas = pestanas[cliente.seleccionPestana];
  if (filasCrudas.length === 0) return { columnasTemplate: [], filas: [] };
  const header = filasCrudas[0].map((h) => texto(h));
  const columnasTemplate = header.filter((h) => h && !COLUMNAS_FIJAS.has(h));
  const filas: FilaSeleccion[] = aObjetos(filasCrudas)
    .filter((f) => texto(f.sku))
    .map((f) => ({
      sku: texto(f.sku),
      generar: esSi(f.generar),
      templates: columnasTemplate.filter((c) => esSi(f[c])),
      prioridad: numero(f.prioridad),
      notas: texto(f.notas),
    }));
  return { columnasTemplate, filas };
}

export type ResultadoCorridas = { corridas: Corrida[]; aviso: string | null };

export function aCorrida(r: RunGithub): Corrida {
  return {
    id: r.id,
    estado:
      r.status === "queued" || r.status === "waiting" || r.status === "pending" || r.status === "requested"
        ? "en_cola"
        : r.status === "in_progress"
          ? "corriendo"
          : r.conclusion === "success"
            ? "ok"
            : r.conclusion === "failure" || r.conclusion === "timed_out"
              ? "fallida"
              : r.conclusion === "cancelled"
                ? "cancelada"
                : "otra",
    disparadaPor: r.event === "schedule" ? "programada" : r.event === "workflow_dispatch" ? "manual" : r.event,
    inicio: r.run_started_at || r.created_at,
    fin: r.status === "completed" ? r.updated_at : null,
    url: r.html_url,
    intento: r.run_attempt,
  };
}

export async function obtenerCorridas(cliente: Cliente, cantidad = 10): Promise<ResultadoCorridas> {
  if (modoDemo) return { corridas: demoCorridas().slice(0, cantidad), aviso: null };
  if (!cliente.workflow) return { corridas: [], aviso: "Este cliente no tiene workflow de pipeline en el repo." };
  try {
    return { corridas: (await listarRuns(cliente.workflow.archivo, cantidad)).map(aCorrida), aviso: null };
  } catch (e) {
    if (e instanceof FaltaTokenGithub || e instanceof ErrorGithub) return { corridas: [], aviso: e.message };
    throw e;
  }
}

export type CorridaEnVivo = Corrida & { pasos: { nombre: string; estado: string; conclusion: string | null }[] };

/** La última corrida del cliente con sus pasos, para mostrar el progreso. */
export async function corridaActual(cliente: Cliente): Promise<CorridaEnVivo | null> {
  if (!cliente.workflow) return null;
  const [ultima] = await listarRuns(cliente.workflow.archivo, 1);
  if (!ultima) return null;
  const pasos = ultima.status === "completed" ? [] : await pasosDeRun(ultima.id).catch(() => []);
  return {
    ...aCorrida(ultima),
    pasos: pasos
      .filter((p) => !/^(Set up job|Complete job|Post )/.test(p.name))
      .map((p) => ({ nombre: p.name, estado: p.status, conclusion: p.conclusion })),
  };
}
