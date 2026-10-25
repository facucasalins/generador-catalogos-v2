"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

export function LinkRiel({ href, children, exacto = false }: { href: string; children: React.ReactNode; exacto?: boolean }) {
  const ruta = usePathname();
  const activo = exacto ? ruta === href : ruta === href || ruta.startsWith(href + "/");
  return (
    <Link href={href} className="riel-link" aria-current={activo ? "page" : undefined}>
      {children}
    </Link>
  );
}

export type Pestana = { href: string; texto: string; cuenta?: number; exacto?: boolean };

export function Pestanas({ items }: { items: Pestana[] }) {
  const ruta = usePathname();
  return (
    <nav className="pestanas" aria-label="Secciones del cliente">
      {items.map((p) => {
        const activo = p.exacto ? ruta === p.href : ruta === p.href || ruta.startsWith(p.href + "/");
        return (
          <Link key={p.href} href={p.href} className="pestana" aria-current={activo ? "page" : undefined}>
            {p.texto}
            {p.cuenta !== undefined && <span className="cuenta num">{p.cuenta}</span>}
          </Link>
        );
      })}
    </nav>
  );
}
