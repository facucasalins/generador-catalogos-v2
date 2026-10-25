export type Producto = {
  sku: string;
  nombre: string;
  precioLista: number;
  precioPromocional: number | null;
  stock: number | null;
  categoria: string;
  marca: string;
  imagenUrl: string;
  urlProducto: string;
  cuotasNum: number;
  publicado: boolean;
  tieneStock: boolean;
  actualizadoEn: string;
  tituloPlaca: string;
  tituloCorto: string;
  // true si el precio viene de la planilla de evento (Cyber, Hot Sale…)
  conPrecioEvento: boolean;
};

export type Placa = {
  sku: string;
  template: string; // con prefijo de plataforma: Meta_default_4x5
  aspectRatio: string;
  url: string;
  fecha: string;
  precioLista: number | null;
  precioPromo: number | null;
};

export type FilaSeleccion = {
  sku: string;
  generar: boolean;
  templates: string[]; // tildados, con prefijo de plataforma
  prioridad: number | null;
  notas: string;
};

export type Seleccion = {
  columnasTemplate: string[];
  filas: FilaSeleccion[];
};

export type Corrida = {
  id: number;
  estado: "en_cola" | "corriendo" | "ok" | "fallida" | "cancelada" | "otra";
  disparadaPor: string;
  inicio: string;
  fin: string | null;
  url: string;
  intento: number;
};
