import { notFound } from "next/navigation";
import { AvisoError, intentar } from "@/components/Estados";
import { Prueba } from "@/components/Prueba";
import { buscarCliente, separarTemplate } from "@/lib/config";
import { obtenerInventario } from "@/lib/datos";
import { fechaHora } from "@/lib/formato";

export const dynamic = "force-dynamic";

const dimensiones: Record<string, [number, number]> = { "4:5": [4, 5], "9:16": [9, 16], "1:1": [1, 1] };

export default async function Placas({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ t?: string }>;
}) {
  const { slug } = await params;
  const { t } = await searchParams;
  const c = buscarCliente(slug);
  if (!c) notFound();

  const r = await intentar(() => obtenerInventario(c));
  if (!r.ok) return <AvisoError error={r.error} que="el historial de placas" />;
  const { placas, productos } = r.valor;
  const nombres = new Map(productos.map((p) => [p.sku, p.tituloPlaca || p.nombre]));
  const templates = [...new Set(placas.map((p) => p.template))].sort();
  const elegido = t && templates.includes(t) ? t : "";
  const visibles = (elegido ? placas.filter((p) => p.template === elegido) : placas).sort(
    (a, b) => b.fecha.localeCompare(a.fecha) || a.sku.localeCompare(b.sku),
  );

  return (
    <section className="mesa">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>
        <p>
          <b className="num">{visibles.length}</b> <span className="suave">placas vigentes, las que hoy están en el feed</span>
        </p>
        <form method="get" className="filtros">
          <select name="t" defaultValue={elegido} className="selector" aria-label="Filtrar por template">
            <option value="">Todos los templates</option>
            {templates.map((tp) => (
              <option key={tp} value={tp}>
                {tp}
              </option>
            ))}
          </select>
          <button className="boton boton-secundario" type="submit">
            Filtrar
          </button>
        </form>
      </div>

      {visibles.length === 0 ? (
        <div className="vacio" style={{ color: "#9aa6b2" }}>
          <b style={{ color: "#fff" }}>Todavía no hay placas generadas.</b>
          <span>Aparecen acá después de la primera corrida con SKUs seleccionados.</span>
        </div>
      ) : (
        <div className="grilla-placas">
          {visibles.map((p) => {
            const [w, h] = dimensiones[p.aspectRatio] ?? [4, 5];
            const { plataforma, base } = separarTemplate(p.template);
            return (
              <figure key={`${p.sku}__${p.template}`} style={{ margin: 0 }}>
                <Prueba ancho={w} alto={h}>
                  {p.url ? (
                    <a href={p.url} target="_blank" rel="noreferrer" title="Abrir la placa en tamaño real">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={p.url.replace("/upload/", "/upload/w_480,q_auto,f_auto/")} alt={`Placa ${base} de ${p.sku}`} loading="lazy" />
                    </a>
                  ) : (
                    <div className="prueba-vacia">Sin imagen en modo demo</div>
                  )}
                </Prueba>
                <figcaption className="pie-prueba">
                  <span>{nombres.get(p.sku) ?? p.sku}</span>
                  <span className="sku">
                    {plataforma} {base}, {fechaHora(p.fecha)}
                  </span>
                </figcaption>
              </figure>
            );
          })}
        </div>
      )}
    </section>
  );
}
