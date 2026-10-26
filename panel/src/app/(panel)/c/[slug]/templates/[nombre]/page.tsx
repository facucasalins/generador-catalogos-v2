import Link from "next/link";
import { notFound } from "next/navigation";
import { BotonRestaurar, EliminarTemplate } from "@/components/AccionesTemplate";
import { EditorPreview } from "@/components/EditorPreview";
import { AvisoError, intentar } from "@/components/Estados";
import { buscarCliente, modoDemo, repoGithub, separarTemplate } from "@/lib/config";
import { obtenerInventario, obtenerSeleccion } from "@/lib/datos";
import { buscarTemplate, rutaTemplate } from "@/lib/datos/templates";
import { fechaHora } from "@/lib/formato";
import { historialArchivo } from "@/lib/github";
import { opcionesDeProductos } from "@/lib/opciones";
import { filasActivas } from "@/lib/resumen";

export const dynamic = "force-dynamic";

export default async function TemplateDetalle({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string; nombre: string }>;
  searchParams: Promise<{ guardado?: string }>;
}) {
  const { slug, nombre: nombreCrudo } = await params;
  const { guardado } = await searchParams;
  const nombre = decodeURIComponent(nombreCrudo);
  const c = buscarCliente(slug);
  if (!c) notFound();
  const t = await buscarTemplate(c, nombre);
  if (!t) notFound();

  const r = await intentar(() => Promise.all([obtenerInventario(c), obtenerSeleccion(c)]));
  if (!r.ok) return <AvisoError error={r.error} que="los productos para la vista previa" />;
  const [inv, sel] = r.valor;
  const usanEste = filasActivas(sel.filas).filter((f) => f.templates.some((x) => separarTemplate(x).base === t.nombre));
  const productos = opcionesDeProductos(inv, sel, t.nombre);
  const historial = t.sha ? await historialArchivo(rutaTemplate(c, t.nombre), 8).catch(() => []) : [];
  const base = `/c/${c.slug}/templates`;

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
        <div>
          <Link href={base} className="suave" style={{ fontSize: "var(--texto-s)" }}>
            Templates de {c.nombre}
          </Link>
          <h2 style={{ fontSize: "var(--texto-xl)", marginTop: 2 }}>{t.nombre}</h2>
          <p className="suave" style={{ fontSize: "var(--texto-s)" }}>
            {t.descripcion || "Sin descripción"}. {t.aspect_ratio}, {t.width}×{t.height} px.{" "}
            {usanEste.length ? `Lo usan ${usanEste.length} productos seleccionados.` : "Ningún producto seleccionado lo usa."}
          </p>
        </div>
        <div className="filtros">
          <Link className="boton" href={`${base}/${encodeURIComponent(t.nombre)}/editar`}>
            Editar
          </Link>
          <Link className="boton boton-secundario" href={`${base}/nuevo?base=${encodeURIComponent(t.nombre)}`}>
            Duplicar
          </Link>
          {(t.sha || modoDemo) && <EliminarTemplate slug={c.slug} nombre={t.nombre} />}
        </div>
      </div>
      {guardado && (
        <div className="aviso aviso-info" role="status">
          <b>Publicado.</b> La próxima corrida regenera las placas que usan este template. Si no querés esperar al horario, usá «Generar ahora» en Corridas.
        </div>
      )}
      {!t.tieneMeta && (
        <div className="aviso aviso-alerta">
          <b>Este template no tiene bloque META.</b> El pipeline lo renderiza en 4:5 a 1080×1350 por defecto. Si no es su tamaño, la placa sale recortada.
        </div>
      )}
      <EditorPreview html={t.html} ancho={t.width} alto={t.height} nombre={t.nombre} productos={productos} estilo={c.estilo} />

      {historial.length > 0 && (
        <section className="hoja" style={{ marginTop: 20 }}>
          <div className="hoja-cabeza">
            <h2>Historial</h2>
            <a className="suave" href={`https://github.com/${repoGithub}/commits/main/${rutaTemplate(c, t.nombre)}`} target="_blank" rel="noreferrer">
              Ver en GitHub
            </a>
          </div>
          <table className="tabla">
            <tbody>
              {historial.map((h, i) => (
                <tr key={h.sha}>
                  <td className="num" style={{ whiteSpace: "nowrap" }}>{fechaHora(h.commit.author.date)}</td>
                  <td>{h.commit.message.split("\n")[0]}</td>
                  <td className="suave">{h.commit.author.name}</td>
                  <td className="der">
                    {i === 0 ? (
                      <span className="suave">Actual</span>
                    ) : (
                      <BotonRestaurar slug={c.slug} nombre={t.nombre} sha={h.sha} fecha={fechaHora(h.commit.author.date)} />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}
