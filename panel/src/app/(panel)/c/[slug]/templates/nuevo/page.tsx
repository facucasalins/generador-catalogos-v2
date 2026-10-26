import Link from "next/link";
import { notFound } from "next/navigation";
import { EditorTemplate } from "@/components/EditorTemplate";
import { AvisoError, intentar } from "@/components/Estados";
import { buscarCliente } from "@/lib/config";
import { obtenerInventario, obtenerSeleccion } from "@/lib/datos";
import { listarTemplates } from "@/lib/datos/templates";
import { opcionesDeProductos } from "@/lib/opciones";
import { htmlBase } from "@/lib/render/meta";

export const dynamic = "force-dynamic";

const formatos: Record<string, [number, number]> = { "4x5": [1080, 1350], "9x16": [1080, 1920], "1x1": [1080, 1080] };

export default async function NuevoTemplate({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ base?: string; formato?: string }>;
}) {
  const { slug } = await params;
  const { base, formato } = await searchParams;
  const c = buscarCliente(slug);
  if (!c) notFound();
  const r = await intentar(() => Promise.all([obtenerInventario(c), obtenerSeleccion(c), listarTemplates(c)]));
  if (!r.ok) return <AvisoError error={r.error} que="los datos para el editor" />;
  const [inv, sel, todos] = r.valor;

  const origen = base ? todos.find((t) => t.nombre === base) : undefined;
  if (!origen && !formato) {
    // Paso 1: elegir de dónde partir.
    return (
      <section className="hoja" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
        <h2>Nuevo template para {c.nombre}</h2>
        <div>
          <p className="suave" style={{ marginBottom: 8 }}>Desde cero, con lo mínimo que necesita el pipeline:</p>
          <div className="filtros">
            {Object.keys(formatos).map((f) => (
              <Link key={f} className="boton boton-secundario" href={`?formato=${f}`}>
                {f.replace("x", ":")}
              </Link>
            ))}
          </div>
        </div>
        <div>
          <p className="suave" style={{ marginBottom: 8 }}>O duplicando uno existente:</p>
          <div className="filtros">
            {todos.map((t) => (
              <Link key={t.nombre} className="boton boton-secundario" href={`?base=${encodeURIComponent(t.nombre)}`}>
                {t.nombre}
              </Link>
            ))}
          </div>
        </div>
      </section>
    );
  }

  const nombreSugerido = origen ? `${origen.nombre}_copia` : `nuevo_${formato}`;
  const [w, h] = formatos[formato ?? "4x5"] ?? formatos["4x5"];
  const html = origen ? origen.html : htmlBase(nombreSugerido, w, h);

  return (
    <EditorTemplate
      slug={c.slug}
      nombreInicial={nombreSugerido}
      htmlInicial={html}
      sha={null}
      esNuevo
      existentes={todos.map((t) => t.nombre)}
      productos={opcionesDeProductos(inv, sel)}
      estilo={c.estilo}
    />
  );
}
