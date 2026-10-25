import Link from "next/link";
import { signOut } from "@/auth";
import { LinkRiel } from "@/components/Navegacion";
import { clientes, modoDemo } from "@/lib/config";
import { exigirSesion } from "@/lib/sesion";

export default async function PanelLayout({ children }: { children: React.ReactNode }) {
  const sesion = await exigirSesion();
  return (
    <div className="marco">
      <aside className="riel">
        <Link href="/" className="riel-marca">
          <strong>Catálogos</strong>
          <span>Nusa Agency</span>
        </Link>
        <nav className="riel-grupo" aria-label="General">
          <LinkRiel href="/" exacto>
            Resumen
          </LinkRiel>
        </nav>
        <nav className="riel-grupo" aria-label="Clientes">
          <span className="riel-titulo">Clientes</span>
          {clientes.map((c) => (
            <LinkRiel key={c.slug} href={`/c/${c.slug}`}>
              {c.nombre}
            </LinkRiel>
          ))}
        </nav>
        <div className="riel-pie">
          <span>{sesion.email}</span>
          {modoDemo ? (
            <span>Modo demo: datos de ejemplo</span>
          ) : (
            <form
              action={async () => {
                "use server";
                await signOut({ redirectTo: "/login" });
              }}
            >
              <button type="submit">Cerrar sesión</button>
            </form>
          )}
        </div>
      </aside>
      <main className="contenido">
        {modoDemo && (
          <div className="aviso aviso-info">
            <b>Modo demo.</b> Los productos, placas y corridas son de ejemplo; los templates sí son los del repo.
          </div>
        )}
        {children}
      </main>
    </div>
  );
}
