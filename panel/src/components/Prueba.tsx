"use client";
import { useEffect, useRef, useState } from "react";

/** Marco de "prueba de imprenta": la placa con marcas de corte en las esquinas. */
export function Prueba({ ancho, alto, children }: { ancho: number; alto: number; children: React.ReactNode }) {
  return (
    <div className="prueba">
      <span className="corte-a" aria-hidden />
      <span className="corte-b" aria-hidden />
      <div className="prueba-lienzo" style={{ aspectRatio: `${ancho} / ${alto}` }}>
        {children}
      </div>
    </div>
  );
}

/**
 * Renderiza el HTML final del template al tamaño real (ancho × alto px) dentro
 * de un iframe y lo escala para que entre en el contenedor.
 *
 * Varios templates traen JavaScript que ajusta el layout (achicar el título
 * hasta que entre, ocultar el tachado si no hay promo) y Playwright lo ejecuta,
 * así que la preview también. El sandbox permite scripts pero NO
 * allow-same-origin: el template corre en un origen opaco y no puede leer
 * cookies, la sesión ni el DOM del panel.
 */
export function HtmlEscalado({ html, ancho, alto, titulo }: { html: string; ancho: number; alto: number; titulo: string }) {
  const caja = useRef<HTMLDivElement>(null);
  const [escala, setEscala] = useState(0);

  useEffect(() => {
    const el = caja.current;
    if (!el) return;
    const medir = () => setEscala(el.clientWidth / ancho);
    medir();
    const obs = new ResizeObserver(medir);
    obs.observe(el);
    return () => obs.disconnect();
  }, [ancho]);

  return (
    <div ref={caja} style={{ position: "absolute", inset: 0 }}>
      {escala > 0 && (
        <iframe
          title={titulo}
          srcDoc={html}
          sandbox="allow-scripts"
          width={ancho}
          height={alto}
          style={{ width: ancho, height: alto, transform: `scale(${escala})` }}
        />
      )}
    </div>
  );
}
