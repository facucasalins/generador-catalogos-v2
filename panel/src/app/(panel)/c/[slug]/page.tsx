import Link from "next/link";
import { notFound } from "next/navigation";
import { AvisoError, intentar } from "@/components/Estados";
import { buscarCliente, separarTemplate } from "@/lib/config";
import { obtenerInventario, obtenerSeleccion } from "@/lib/datos";
import { pesos } from "@/lib/formato";
import { filasActivas, motivoDescarte } from "@/lib/resumen";

export const dynamic = "force-dynamic";

type Filtro = "seleccionados" | "todos" | "problemas";

export default async function Productos({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ f?: string; q?: string }>;
}) {
  const { slug } = await params;
  const { f, q } = await searchParams;
  const c = buscarCliente(slug);
  if (!c) notFound();
  const filtro: Filtro = f === "todos" || f === "problemas" ? f : "seleccionados";
  const busqueda = (q ?? "").trim().toLowerCase();

  const r = await intentar(() => Promise.all([obtenerInventario(c), obtenerSeleccion(c)]));
  if (!r.ok) return <AvisoError error={r.error} que="el inventario o la selección" />;
  const [inv, sel] = r.valor;

  const seleccion = new Map(filasActivas(sel.filas).map((f) => [f.sku, f]));
  const placasPorSku = new Map<string, number>();
  for (const p of inv.placas) placasPorSku.set(p.sku, (placasPorSku.get(p.sku) ?? 0) + 1);

  // SKUs tildados en Selección que no están en el inventario también se listan.
  const porSku = new Map(inv.productos.map((p) => [p.sku, p]));
  const fantasmas = [...seleccion.keys()].filter((s) => !porSku.has(s));

  let filas = inv.productos.map((p) => ({ p, sel: seleccion.get(p.sku), problema: seleccion.has(p.sku) ? motivoDescarte(p) : null }));
  if (filtro === "seleccionados") filas = filas.filter((x) => x.sel);
  if (filtro === "problemas") filas = filas.filter((x) => x.problema);
  if (busqueda) filas = filas.filter((x) => x.p.sku.toLowerCase().includes(busqueda) || x.p.nombre.toLowerCase().includes(busqueda));
  filas.sort((a, b) => Number(Boolean(b.sel)) - Number(Boolean(a.sel)) || a.p.nombre.localeCompare(b.p.nombre));

  const nProblemas = [...seleccion.values()].filter((s) => motivoDescarte(porSku.get(s.sku))).length;
  const url = (nuevo: Filtro) => `/c/${c.slug}?f=${nuevo}${busqueda ? `&q=${encodeURIComponent(busqueda)}` : ""}`;

  return (
    <section className="hoja">
      <div className="hoja-cabeza">
        <div className="segmentos" role="group" aria-label="Filtrar productos">
          <Link href={url("seleccionados")} aria-current={filtro === "seleccionados"}>
            Seleccionados <span className="num">{seleccion.size}</span>
          </Link>
          <Link href={url("problemas")} aria-current={filtro === "problemas"}>
            No van a salir <span className="num">{nProblemas}</span>
          </Link>
          <Link href={url("todos")} aria-current={filtro === "todos"}>
            Todo el inventario <span className="num">{inv.productos.length}</span>
          </Link>
        </div>
        <form className="filtros" method="get">
          <input type="hidden" name="f" value={filtro} />
          <input type="search" name="q" defaultValue={busqueda} placeholder="Buscar por nombre o SKU" aria-label="Buscar producto" />
        </form>
      </div>

      {fantasmas.length > 0 && filtro !== "todos" && (
        <div className="aviso aviso-alerta" style={{ margin: 16 }}>
          <b>{fantasmas.length} SKU tildados en la Selección no están en el inventario:</b> {fantasmas.join(", ")}. El pipeline los ignora.
        </div>
      )}

      {filas.length === 0 ? (
        <div className="vacio">
          <b>{filtro === "problemas" ? "Todos los seleccionados van a salir." : "No hay productos para mostrar."}</b>
          {filtro === "seleccionados" && <span>Todavía no hay SKUs tildados en la Selección de este cliente.</span>}
        </div>
      ) : (
        <div className="tabla-envoltura">
          <table className="tabla">
            <thead>
              <tr>
                <th style={{ width: 60 }} />
                <th>Producto</th>
                <th className="der">Precio</th>
                <th className="der">Stock</th>
                <th>Templates tildados</th>
                <th className="der">Placas</th>
              </tr>
            </thead>
            <tbody>
              {filas.map(({ p, sel: s, problema }) => (
                <tr key={p.sku}>
                  <td>
                    {p.imagenUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img className="miniatura" src={p.imagenUrl} alt="" loading="lazy" />
                    ) : (
                      <div className="miniatura" />
                    )}
                  </td>
                  <td>
                    <div className="nombre-prod">{p.tituloPlaca || p.nombre}</div>
                    <div className="sku">{p.sku}</div>
                    {problema && <span className="etiqueta etq-alerta" style={{ marginTop: 4 }}>No sale: {problema}</span>}
                  </td>
                  <td className="der num">
                    {p.precioPromocional && p.precioPromocional < p.precioLista ? (
                      <>
                        <div className="tachado">{pesos(p.precioLista)}</div>
                        <div>{pesos(p.precioPromocional)}</div>
                      </>
                    ) : (
                      pesos(p.precioLista)
                    )}
                    {p.conPrecioEvento && <div className="sku">precio de evento</div>}
                  </td>
                  <td className="der num">{p.stock ?? ""}</td>
                  <td>
                    <div className="plataformas">
                      {(s?.templates ?? []).map((t) => {
                        const { plataforma, base } = separarTemplate(t);
                        return (
                          <span key={t} className={`chip ${plataforma === "TikTok" ? "chip-tiktok" : "chip-meta"}`} title={t}>
                            {plataforma} {base}
                          </span>
                        );
                      })}
                    </div>
                  </td>
                  <td className="der num">{placasPorSku.get(p.sku) ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
