import Link from "next/link";
import { notFound } from "next/navigation";
import { AvisoError, intentar } from "@/components/Estados";
import { HtmlEscalado, Prueba } from "@/components/Prueba";
import { buscarCliente, separarTemplate } from "@/lib/config";
import { obtenerInventario, obtenerSeleccion } from "@/lib/datos";
import { aProductoRender, productoMuestra } from "@/lib/render/preparar";
import { construirVariables, reemplazarVariables } from "@/lib/render/variables";
import { filasActivas } from "@/lib/resumen";

export const dynamic = "force-dynamic";

export default async function Templates({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const c = buscarCliente(slug);
  if (!c) notFound();

  const r = await intentar(() => Promise.all([obtenerInventario(c), obtenerSeleccion(c)]));
  if (!r.ok) return <AvisoError error={r.error} que="los productos para la vista previa" />;
  const [inv, sel] = r.valor;

  const activas = filasActivas(sel.filas);
  const uso = new Map<string, { meta: number; tiktok: number }>();
  for (const f of activas) {
    for (const t of f.templates) {
      const { plataforma, base } = separarTemplate(t);
      const u = uso.get(base) ?? { meta: 0, tiktok: 0 };
      if (plataforma === "TikTok") u.tiktok++;
      else u.meta++;
      uso.set(base, u);
    }
  }
  const muestra = productoMuestra(inv.productos, new Set(activas.map((f) => f.sku)));
  const vars = muestra ? construirVariables(aProductoRender(muestra), c.estilo) : null;

  return (
    <section className="mesa">
      <p style={{ marginBottom: 24 }}>
        <span className="suave">Vista previa con </span>
        {muestra ? <b>{muestra.tituloPlaca || muestra.nombre}</b> : <b>ningún producto</b>}
        <span className="suave">. Abrí un template para probarlo con otros productos.</span>
      </p>
      <div className="grilla-templates">
        {c.templates.map((t) => {
          const render = vars ? reemplazarVariables(t.html, vars) : null;
          const u = uso.get(t.nombre);
          return (
            <figure key={t.nombre} style={{ margin: 0 }}>
              <Link href={`/c/${c.slug}/templates/${encodeURIComponent(t.nombre)}`} aria-label={`Abrir ${t.nombre}`}>
                <Prueba ancho={t.width} alto={t.height}>
                  {render ? (
                    <HtmlEscalado html={render.html} ancho={t.width} alto={t.height} titulo={`Vista previa de ${t.nombre}`} />
                  ) : (
                    <div className="prueba-vacia">Sin productos para mostrar</div>
                  )}
                </Prueba>
              </Link>
              <figcaption className="pie-prueba">
                <Link href={`/c/${c.slug}/templates/${encodeURIComponent(t.nombre)}`}>
                  <b>{t.nombre}</b>
                </Link>
                <span className="sku">
                  {t.aspect_ratio}, {u ? `${u.meta} SKUs en Meta y ${u.tiktok} en TikTok` : "sin usar"}
                </span>
                {!t.tieneMeta && <span style={{ color: "#f5c46b" }}>Sin bloque META</span>}
                {render && render.sinReemplazar.length > 0 && (
                  <span style={{ color: "#ff9d8f" }}>Variables inexistentes: {render.sinReemplazar.join(", ")}</span>
                )}
              </figcaption>
            </figure>
          );
        })}
      </div>
    </section>
  );
}
