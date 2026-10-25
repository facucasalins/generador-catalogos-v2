// Datos de ejemplo para PANEL_DEMO=1 (desarrollo local, sin credenciales).
// Son inventados: no salen de ninguna sheet real.
import type { Cliente } from "../config";
import type { Corrida, Placa, Producto, Seleccion } from "./tipos";

const catalogo: Record<string, [string, number, number | null, number][]> = {
  flint: [
    ["Creatina monohidratada ultramicronizada 300 g sabor neutro", 39999, 24999, 49],
    ["Whey protein vanilla but for real 1 kg", 59999, 53999, 7],
    ["Whey protein chocolate but for real 1 kg", 59999, 53999, 0],
    ["Combo power pack creatina + whey", 89999, 73499, 396],
    ["Pre entreno frutos rojos 300 g", 39999, null, 129],
    ["Colágeno hidrolizado 360 g", 29999, 23999, 170],
  ],
  morashop: [
    ["Proteína isolate sabor cookies & cream 2 lb", 64999, 57999, 22],
    ["Creatina 250 g", 27999, 22999, 80],
    ["Licuadora portátil recargable 600 ml", 34999, 29999, 15],
    ["Freidora de aire digital 5 litros", 159999, 129999, 6],
    ["Omega 3 x 60 cápsulas", 18999, null, 44],
  ],
  juanita: [
    ["Bota texana caña alta cuero negro", 189999, 151999, 12],
    ["Sandalia plataforma trenzada suela de yute", 89999, 71999, 30],
    ["Zapatilla urbana cuero blanco", 119999, null, 18],
    ["Mocasín gamuza camel", 109999, 87999, 0],
  ],
  antonia: [
    ["Stiletto charol nude taco 9 cm", 99999, 79999, 9],
    ["Bota corta gamuza chocolate", 149999, 119999, 14],
    ["Chatita punta redonda cuero negro", 79999, null, 26],
  ],
  shark: [
    ["Buzo oversize frisa gris melange", 54999, 43999, 60],
    ["Calza térmica compresión negra", 34999, 27999, 41],
    ["Remera dry fit manga corta", 21999, null, 120],
    ["Short training doble capa", 29999, 23999, 0],
  ],
};

function slugify(s: string) {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

// Imagen de producto genérica (SVG) para no depender de la red.
function imagenDemo(i: number) {
  const tonos = ["#cfd8dc", "#d7ccc8", "#c5cae9", "#c8e6c9", "#ffe0b2", "#f8bbd0"];
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 600 600'><rect width='600' height='600' fill='white'/><rect x='170' y='110' width='260' height='380' rx='36' fill='${tonos[i % tonos.length]}'/><rect x='215' y='70' width='170' height='60' rx='14' fill='#90a4ae'/><rect x='205' y='250' width='190' height='90' rx='10' fill='white' opacity='.8'/></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

export function demoProductos(cliente: Cliente): Producto[] {
  return (catalogo[cliente.slug] ?? []).map(([nombre, lista, promo, stock], i) => ({
    sku: slugify(nombre),
    nombre: nombre.toUpperCase(),
    precioLista: lista,
    precioPromocional: promo,
    stock,
    categoria: "",
    marca: cliente.nombre,
    imagenUrl: imagenDemo(i),
    urlProducto: "",
    cuotasNum: cliente.cuotasNum,
    publicado: true,
    tieneStock: stock > 0,
    actualizadoEn: "2026-10-25T06:40:00",
    tituloPlaca: nombre.split(" ").slice(0, 4).join(" "),
    tituloCorto: nombre.split(" ").slice(0, 6).join(" "),
    conPrecioEvento: false,
  }));
}

export function demoSeleccion(cliente: Cliente): Seleccion {
  const columnas = cliente.templates.flatMap((t) => [`Meta_${t.nombre}`]).concat(
    cliente.templates.map((t) => `TikTok_${t.nombre}`),
  );
  const productos = demoProductos(cliente);
  return {
    columnasTemplate: columnas,
    filas: productos.slice(0, Math.max(1, productos.length - 1)).map((p, i) => ({
      sku: p.sku,
      generar: true,
      templates: columnas.filter((_, j) => j % 3 === i % 3).slice(0, 2),
      prioridad: null,
      notas: "",
    })),
  };
}

export function demoPlacas(cliente: Cliente): Placa[] {
  return demoSeleccion(cliente).filas.flatMap((f) =>
    f.templates.map((t) => ({
      sku: f.sku,
      template: t,
      aspectRatio: "4:5",
      url: "",
      fecha: "2026-10-25 06:41:12",
      precioLista: null,
      precioPromo: null,
    })),
  );
}

export function demoCorridas(): Corrida[] {
  const dias = [25, 24, 23, 22, 21];
  return dias.map((d, i) => ({
    id: 1000 + i,
    estado: i === 2 ? "fallida" : "ok",
    disparadaPor: i === 1 ? "manual" : "programada",
    inicio: `2026-10-${d}T09:37:00Z`,
    fin: `2026-10-${d}T09:44:${10 + i}Z`,
    url: "#",
    intento: 1,
  }));
}
