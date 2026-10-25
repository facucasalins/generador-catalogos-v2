// Genera panel/generated/clientes.json a partir del repo:
//   - clients/<cliente>/pipeline.yaml   (config del cliente)
//   - clients/<cliente>/templates/*.html (templates y su bloque META)
//   - .github/workflows/*.yml           (qué workflow corre el pipeline de cada cliente)
//
// Corre antes de `next dev` y `next build`. Así el panel muestra exactamente
// lo que hay en `main`: cada push al repo redespliega el panel con los
// templates y la config actualizados, sin duplicar datos en otro lado.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import yaml from "js-yaml";

const aqui = path.dirname(fileURLToPath(import.meta.url));
const raizRepo = path.resolve(aqui, "..", "..");
const dirClientes = path.join(raizRepo, "clients");
const dirWorkflows = path.join(raizRepo, ".github", "workflows");
const salida = path.resolve(aqui, "..", "generated", "clientes.json");

// Misma lógica que src/seleccion/sync.py: parsear_metadata_template.
// Si falta el bloque META, el pipeline usa 4:5 1080x1350; acá también.
export function parsearMeta(html) {
  const meta = { aspect_ratio: "4:5", width: 1080, height: 1350, descripcion: "", tieneMeta: false };
  const m = html.match(/<!--\s*META\s*([\s\S]+?)\s*-->/);
  if (!m) {
    const d = html.match(/<!--\s*DESC:\s*([\s\S]+?)\s*-->/);
    if (d) meta.descripcion = d[1].trim();
    return meta;
  }
  meta.tieneMeta = true;
  for (const lineaCruda of m[1].split("\n")) {
    const linea = lineaCruda.trim();
    if (!linea || !linea.includes(":")) continue;
    const i = linea.indexOf(":");
    const clave = linea.slice(0, i).trim().toLowerCase();
    const valor = linea.slice(i + 1).trim();
    if (clave === "aspect_ratio") meta.aspect_ratio = valor;
    else if (clave === "width" && /^-?\d+$/.test(valor)) meta.width = parseInt(valor, 10);
    else if (clave === "height" && /^-?\d+$/.test(valor)) meta.height = parseInt(valor, 10);
    else if (["descripcion", "descripción", "desc"].includes(clave)) meta.descripcion = valor;
  }
  return meta;
}

function leerWorkflows() {
  const porCliente = {};
  if (!fs.existsSync(dirWorkflows)) return porCliente;
  for (const archivo of fs.readdirSync(dirWorkflows).sort()) {
    if (!/\.ya?ml$/.test(archivo)) continue;
    const texto = fs.readFileSync(path.join(dirWorkflows, archivo), "utf8");
    // El workflow "completo" de cada cliente es el que corre el CLI con --output-dir
    // (los de seguimiento o dumps usan otros flags o scripts).
    const m = texto.match(/python -m src\.cli --cliente=([a-z0-9_-]+) --output-dir/);
    if (!m) continue;
    const nombre = (texto.match(/^name:\s*(.+)$/m) || [])[1]?.trim() ?? archivo;
    const cron = (texto.match(/cron:\s*['"]([^'"]+)['"]/) || [])[1] ?? null;
    porCliente[m[1]] = { archivo, nombre, cron };
  }
  return porCliente;
}

function leerCliente(slug, workflows) {
  const dir = path.join(dirClientes, slug);
  const pipeline = yaml.load(fs.readFileSync(path.join(dir, "pipeline.yaml"), "utf8"));
  const dirTemplates = path.join(dir, "templates");
  const templates = fs.existsSync(dirTemplates)
    ? fs.readdirSync(dirTemplates)
        .filter((f) => f.endsWith(".html"))
        .sort()
        .map((f) => {
          const html = fs.readFileSync(path.join(dirTemplates, f), "utf8");
          return { nombre: f.replace(/\.html$/, ""), html, ...parsearMeta(html) };
        })
    : [];

  const inv = pipeline.inventario?.config ?? {};
  const estilo = pipeline.estilo?.config ?? {};
  const destinos = pipeline.distribucion?.destinos ?? [];
  const override = pipeline.inventario?.precios_override;

  return {
    slug,
    nombre: pipeline.cliente?.brand_name ?? slug,
    inventarioSheetId: inv.sheet_destino?.id ?? null,
    inventarioPestana: inv.sheet_destino?.["pestaña"] ?? "Inventario",
    seleccionSheetId: pipeline.seleccion?.config?.sheet?.id ?? null,
    seleccionPestana: pipeline.seleccion?.config?.sheet?.["pestaña"] ?? "Seleccion",
    feedSheetId: destinos.find((d) => d.tipo === "meta_catalog")?.config?.sheet_id ?? null,
    agruparPorProducto: Boolean(inv.agrupar_por_producto),
    cuotasNum: inv.cuotas_num ?? 3,
    preciosOverride: override
      ? {
          sheetId: override.sheet_id,
          pestana: override["pestaña"],
          colSku: override.col_sku ?? "URL (handle TN)",
          colPrecioLista: override.col_precio_lista ?? "Precio full",
          colPrecioPromo: override.col_precio_promo ?? "Precio Cyber",
        }
      : null,
    estilo: {
      hotsaleDiscountFactor: estilo.hotsale_discount_factor ?? 1.0,
      descuentoEfectivoFactor: estilo.descuento_efectivo_factor ?? null,
      cuotasSobrePromocional: Boolean(estilo.cuotas_sobre_promocional),
      variablesGlobales: estilo.variables_globales ?? {},
    },
    cloudinaryFolder: pipeline.distribucion?.storage?.config?.folder ?? slug,
    workflow: workflows[slug] ?? null,
    templates,
  };
}

const workflows = leerWorkflows();
const clientes = fs
  .readdirSync(dirClientes, { withFileTypes: true })
  .filter((d) => d.isDirectory() && !d.name.startsWith("_"))
  .filter((d) => fs.existsSync(path.join(dirClientes, d.name, "pipeline.yaml")))
  .map((d) => leerCliente(d.name, workflows));

fs.mkdirSync(path.dirname(salida), { recursive: true });
fs.writeFileSync(salida, JSON.stringify({ generadoEn: new Date().toISOString(), clientes }, null, 2));
console.log(
  `[sync] ${clientes.length} clientes: ` +
    clientes.map((c) => `${c.slug} (${c.templates.length} templates)`).join(", "),
);
