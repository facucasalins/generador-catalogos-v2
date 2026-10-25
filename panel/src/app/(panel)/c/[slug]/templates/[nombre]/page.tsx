import Link from "next/link";
import { notFound } from "next/navigation";
import { EditorPreview, type OpcionProducto } from "@/components/EditorPreview";
import { AvisoError, intentar } from "@/components/Estados";
import { buscarCliente, repoGithub, separarTemplate } from "@/lib/config";
import { obtenerInventario, obtenerSeleccion } from "@/lib/datos";
import { aProductoRender } from "@/lib/render/preparar";
import { filasActivas } from "@/lib/resumen";

export const dynamic = "force-dynamic";

export default async function TemplateDetalle({ params }: { params: Promise<{ slug: string; nombre: string }> }) {
  const { slug, nombre: nombreCrudo } = await params;
  const nombre = decodeURIComponent(nombreCrudo);
  const c = buscarCliente(slug);
  const t = c?.templates.find((x) => x.nombre === nombre);
  if (!c || !t) notFound();

  const r = await intentar(() => Promise.all([obtenerInventario(c), obtenerSeleccion(c)]));
  if (!r.ok) return <AvisoError error={r.error} que="los productos para la vista previa" />;
  const [inv, sel] = r.valor;

  const activas = filasActivas(sel.filas);
  const usanEste = activas.filter((f) => f.templates.some((x) => separarTemplate(x).base === t.nombre));
  const seleccionados = new Set(usanEste.length ? usanEste.map((f) => f.sku) : activas.map((f) => f.sku));
  const productos: OpcionProducto[] = inv.productos
    .filter((p) => p.imagenUrl)
    .map((p) => ({ ...aProductoRender(p), seleccionado: seleccionados.has(p.sku), tieneStock: p.tieneStock }));

  const enGithub = `https://github.com/${repoGithub}/blob/main/clients/${c.slug}/templates/${t.nombre}.html`;

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
        <div>
          <Link href={`/c/${c.slug}/templates`} className="suave" style={{ fontSize: "var(--texto-s)" }}>
            Templates de {c.nombre}
          </Link>
          <h2 style={{ fontSize: "var(--texto-xl)", marginTop: 2 }}>{t.nombre}</h2>
          <p className="suave" style={{ fontSize: "var(--texto-s)" }}>
            {t.descripcion || "Sin descripción"}. {t.aspect_ratio}, {t.width}×{t.height} px.{" "}
            {usanEste.length ? `Lo usan ${usanEste.length} SKUs seleccionados.` : "Ningún SKU seleccionado lo usa."}
          </p>
        </div>
        <a className="boton boton-secundario" href={enGithub} target="_blank" rel="noreferrer">
          Ver el HTML en GitHub
        </a>
      </div>
      {!t.tieneMeta && (
        <div className="aviso aviso-alerta">
          <b>Este template no tiene bloque META.</b> El pipeline lo renderiza en 4:5 a 1080×1350 por defecto. Si no es su tamaño, la placa sale recortada.
        </div>
      )}
      <EditorPreview html={t.html} ancho={t.width} alto={t.height} nombre={t.nombre} productos={productos} estilo={c.estilo} />
    </>
  );
}
