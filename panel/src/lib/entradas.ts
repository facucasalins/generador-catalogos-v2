// Interpreta lo que se pega en "Agregar productos": URLs de la tienda o SKUs,
// uno por línea (o separados por coma), y los busca en el inventario.

export type ProductoBuscable = {
  sku: string;
  urlProducto: string;
  tieneStock: boolean;
  publicado: boolean;
};

export type EstadoEntrada = "ok" | "sin_stock" | "no_publicado" | "no_encontrado";

export type EntradaResuelta<P extends ProductoBuscable> = {
  entrada: string;
  handle: string;
  productos: P[]; // varias en clientes por variante (MoraShop)
  estado: EstadoEntrada;
};

/** Handle de una URL de producto de Tiendanube: /productos/<handle>/ (o el último tramo). */
export function handleDeUrl(texto: string): string | null {
  let url: URL;
  try {
    url = new URL(/^https?:\/\//i.test(texto) ? texto : `https://${texto}`);
  } catch {
    return null;
  }
  if (!url.hostname.includes(".")) return null;
  const tramos = url.pathname.split("/").filter(Boolean).map((t) => decodeURIComponent(t).toLowerCase());
  if (tramos.length === 0) return null;
  const i = tramos.findIndex((t) => t === "productos" || t === "products" || t === "produtos");
  return i >= 0 && tramos[i + 1] ? tramos[i + 1] : tramos[tramos.length - 1];
}

export function separarEntradas(texto: string): string[] {
  return [
    ...new Set(
      texto
        .split(/[\n,;\s]+/)
        .map((t) => t.trim())
        .filter(Boolean),
    ),
  ];
}

export function resolverEntradas<P extends ProductoBuscable>(texto: string, inventario: P[]): EntradaResuelta<P>[] {
  const porHandle = new Map<string, P[]>();
  for (const p of inventario) {
    const h = p.urlProducto ? handleDeUrl(p.urlProducto) : null;
    if (h) porHandle.set(h, [...(porHandle.get(h) ?? []), p]);
  }
  const porSku = new Map(inventario.map((p) => [p.sku.toLowerCase(), p]));

  return separarEntradas(texto).map((entrada) => {
    const pareceUrl = entrada.includes("/") || /^https?:/i.test(entrada);
    const handle = (pareceUrl ? handleDeUrl(entrada) : entrada.toLowerCase()) ?? entrada.toLowerCase();
    // 1) SKU exacto  2) handle de la URL de producto (todas sus variantes)  3) handle como SKU
    const exacto = !pareceUrl ? porSku.get(entrada.toLowerCase()) : undefined;
    const productos = exacto ? [exacto] : (porHandle.get(handle) ?? (porSku.get(handle) ? [porSku.get(handle)!] : []));
    let estado: EstadoEntrada = "ok";
    if (productos.length === 0) estado = "no_encontrado";
    else if (productos.every((p) => !p.publicado)) estado = "no_publicado";
    else if (productos.every((p) => !p.tieneStock)) estado = "sin_stock";
    return { entrada, handle, productos, estado };
  });
}
