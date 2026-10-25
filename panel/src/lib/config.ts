import datos from "../../generated/clientes.json";
import type { EstiloCliente } from "./render/variables";

export type TemplateRepo = {
  nombre: string;
  html: string;
  aspect_ratio: string;
  width: number;
  height: number;
  descripcion: string;
  tieneMeta: boolean;
};

export type Cliente = {
  slug: string;
  nombre: string;
  inventarioSheetId: string | null;
  inventarioPestana: string;
  seleccionSheetId: string | null;
  seleccionPestana: string;
  feedSheetId: string | null;
  agruparPorProducto: boolean;
  cuotasNum: number;
  preciosOverride: {
    sheetId: string;
    pestana: string;
    colSku: string;
    colPrecioLista: string;
    colPrecioPromo: string;
  } | null;
  estilo: EstiloCliente;
  cloudinaryFolder: string;
  workflow: { archivo: string; nombre: string; cron: string | null } | null;
  templates: TemplateRepo[];
};

export const clientes = datos.clientes as unknown as Cliente[];
export const generadoEn = datos.generadoEn as string;

export function buscarCliente(slug: string): Cliente | undefined {
  return clientes.find((c) => c.slug === slug);
}

export const PLATAFORMAS = ["Meta", "TikTok"] as const;
export type Plataforma = (typeof PLATAFORMAS)[number];

// "Meta_default_4x5" → { plataforma: "Meta", base: "default_4x5" }
// Misma regla que src/core/templates.py: nombre_base_template.
export function separarTemplate(nombre: string): { plataforma: Plataforma | null; base: string } {
  for (const p of PLATAFORMAS) {
    if (nombre.startsWith(`${p}_`)) return { plataforma: p, base: nombre.slice(p.length + 1) };
  }
  return { plataforma: null, base: nombre };
}

export const repoGithub = process.env.GITHUB_REPO ?? "facucasalins/generador-catalogos-v2";

// Modo demo: datos de ejemplo, sin Google ni GitHub. Solo para desarrollo local
// y para ver el panel antes de cargar las credenciales. Nunca en producción.
export const modoDemo = process.env.PANEL_DEMO === "1";
