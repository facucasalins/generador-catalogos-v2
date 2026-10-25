import { notFound } from "next/navigation";
import { Pestanas } from "@/components/Navegacion";
import { buscarCliente } from "@/lib/config";
import { cronLegible } from "@/lib/formato";

const sheet = (id: string | null) => (id ? `https://docs.google.com/spreadsheets/d/${id}/edit` : null);

export default async function ClienteLayout({ children, params }: { children: React.ReactNode; params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const c = buscarCliente(slug);
  if (!c) notFound();
  const base = `/c/${c.slug}`;
  const efectivo = c.estilo.descuentoEfectivoFactor;
  const enlaces = [
    ["Selección", sheet(c.seleccionSheetId)],
    ["Inventario", sheet(c.inventarioSheetId)],
    ["Feed", sheet(c.feedSheetId)],
  ].filter(([, url]) => url) as [string, string][];

  return (
    <>
      <header className="cabecera">
        <h1>{c.nombre}</h1>
        <div className="datos-cliente">
          <span>
            Corre <b>{cronLegible(c.workflow?.cron ?? null)}</b>
          </span>
          <span>
            <b>{c.cuotasNum}</b> cuotas{c.estilo.cuotasSobrePromocional ? " sobre el precio promo" : " sobre el precio de lista"}
          </span>
          {efectivo !== null && (
            <span>
              Transferencia <b>{Math.round((1 - efectivo) * 100)}% off</b>
            </span>
          )}
          <span>{c.agruparPorProducto ? "Una placa por producto" : "Una placa por variante"}</span>
          {c.preciosOverride && <span>Precios de evento desde «{c.preciosOverride.pestana}»</span>}
          {enlaces.map(([texto, url]) => (
            <a key={texto} href={url} target="_blank" rel="noreferrer">
              Sheet {texto}
            </a>
          ))}
        </div>
      </header>
      <Pestanas
        items={[
          { href: base, texto: "Productos", exacto: true },
          { href: `${base}/placas`, texto: "Placas" },
          { href: `${base}/templates`, texto: "Templates", cuenta: c.templates.length },
          { href: `${base}/corridas`, texto: "Corridas" },
        ]}
      />
      {children}
    </>
  );
}
