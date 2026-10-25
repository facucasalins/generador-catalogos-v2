import type { Producto } from "../datos/tipos";
import type { ProductoRender } from "./variables";

export function aProductoRender(p: Producto): ProductoRender {
  return {
    sku: p.sku,
    nombre: p.nombre,
    precioLista: p.precioLista,
    precioPromocional: p.precioPromocional,
    cuotasNum: p.cuotasNum,
    marca: p.marca,
    categoria: p.categoria,
    imagenUrl: p.imagenUrl,
    tituloPlaca: p.tituloPlaca,
    tituloCorto: p.tituloCorto,
  };
}

/** Producto de muestra para una miniatura: el primero seleccionado con stock, si no el primero con stock. */
export function productoMuestra(productos: Producto[], seleccionados: Set<string>): Producto | undefined {
  return (
    productos.find((p) => seleccionados.has(p.sku) && p.tieneStock && p.imagenUrl) ??
    productos.find((p) => p.tieneStock && p.imagenUrl) ??
    productos[0]
  );
}
