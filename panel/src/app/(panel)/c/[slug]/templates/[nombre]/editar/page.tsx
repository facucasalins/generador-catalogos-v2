import { notFound } from "next/navigation";
import { EditorTemplate } from "@/components/EditorTemplate";
import { AvisoError, intentar } from "@/components/Estados";
import { buscarCliente, modoDemo } from "@/lib/config";
import { obtenerInventario, obtenerSeleccion } from "@/lib/datos";
import { buscarTemplate, listarTemplates } from "@/lib/datos/templates";
import { opcionesDeProductos } from "@/lib/opciones";

export const dynamic = "force-dynamic";

export default async function EditarTemplate({ params }: { params: Promise<{ slug: string; nombre: string }> }) {
  const { slug, nombre: crudo } = await params;
  const nombre = decodeURIComponent(crudo);
  const c = buscarCliente(slug);
  if (!c) notFound();
  const t = await buscarTemplate(c, nombre);
  if (!t) notFound();
  const r = await intentar(() => Promise.all([obtenerInventario(c), obtenerSeleccion(c), listarTemplates(c)]));
  if (!r.ok) return <AvisoError error={r.error} que="los datos para el editor" />;
  const [inv, sel, todos] = r.valor;
  if (!t.sha && !modoDemo) {
    return (
      <div className="aviso aviso-alerta">
        <b>No se puede editar ahora.</b> El panel no está leyendo los templates desde GitHub; revisá GITHUB_TOKEN en Vercel.
      </div>
    );
  }
  return (
    <EditorTemplate
      slug={c.slug}
      nombreInicial={t.nombre}
      htmlInicial={t.html}
      sha={t.sha}
      esNuevo={false}
      existentes={todos.map((x) => x.nombre)}
      productos={opcionesDeProductos(inv, sel, t.nombre)}
      estilo={c.estilo}
    />
  );
}
