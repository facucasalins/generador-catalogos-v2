// Port 1:1 de src/estilo/playwright_html.py (_construir_variables y
// _reemplazar_variables). La preview del panel tiene que mostrar EXACTAMENTE
// lo que va a renderizar Playwright, así que cualquier cambio en el Python
// se replica acá. tests/variables.test.ts compara ambos contra los mismos casos.

export type ProductoRender = {
  sku: string;
  nombre: string;
  precioLista: number;
  precioPromocional: number | null;
  cuotasNum: number;
  marca: string;
  categoria: string;
  imagenUrl: string;
  tituloPlaca?: string;
  tituloCorto?: string;
};

export type EstiloCliente = {
  hotsaleDiscountFactor: number;
  descuentoEfectivoFactor: number | null;
  cuotasSobrePromocional: boolean;
  variablesGlobales: Record<string, unknown>;
};

// Python: round() redondea al par en los .5 exactos (round(2.5) == 2).
// Math.round de JS redondea hacia arriba. Sin esto, un precio que termina en
// ,5 se vería un peso distinto en la preview que en la placa real.
export function redondearComoPython(valor: number): number {
  const piso = Math.floor(valor);
  const diferencia = valor - piso;
  if (diferencia > 0.5) return piso + 1;
  if (diferencia < 0.5) return piso;
  return piso % 2 === 0 ? piso : piso + 1;
}

// Python: formatear_precio_ars → "$" + entero con puntos de miles.
export function formatearPrecioArs(valor: number): string {
  const entero = redondearComoPython(valor);
  const signo = entero < 0 ? "-" : "";
  const conPuntos = Math.abs(entero).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `$${signo}${conPuntos}`;
}

// Python: str(float). 39999.0 → "39999.0"; 22499.100000000002 queda igual.
export function strFloatPython(valor: number): string {
  if (Number.isInteger(valor)) return `${valor}.0`;
  return String(valor);
}

export function calcularCuota(precioBase: number, cuotasNum: number): number {
  if (cuotasNum <= 0) return precioBase;
  return precioBase / cuotasNum;
}

export type OpcionesVariables = {
  // En la preview las imágenes van por URL; el pipeline las incrusta en base64.
  // El HTML usa src="{imagen_b64}", que acepta las dos formas.
  imagenSrc?: string;
  logoSrc?: string;
};

export function construirVariables(
  producto: ProductoRender,
  estilo: EstiloCliente,
  opciones: OpcionesVariables = {},
): Record<string, string> {
  const precioOriginal = producto.precioLista;
  const precioHotsale =
    producto.precioPromocional !== null && producto.precioPromocional > 0
      ? producto.precioPromocional
      : precioOriginal * estilo.hotsaleDiscountFactor;

  const precioEfectivo =
    estilo.descuentoEfectivoFactor !== null && estilo.descuentoEfectivoFactor !== undefined
      ? precioHotsale * estilo.descuentoEfectivoFactor
      : null;

  const baseCuota = estilo.cuotasSobrePromocional ? precioHotsale : precioOriginal;
  const cuota = calcularCuota(baseCuota, producto.cuotasNum);

  const logoUrl = String(estilo.variablesGlobales["logo_url"] ?? "");

  const variables: Record<string, string> = {
    sku: producto.sku,
    nombre: producto.nombre,
    titulo_placa: producto.tituloPlaca || producto.tituloCorto || producto.nombre,
    marca: producto.marca,
    categoria: producto.categoria,
    imagen_b64: opciones.imagenSrc ?? producto.imagenUrl,
    logo_b64: opciones.logoSrc ?? logoUrl,
    precio_lista: strFloatPython(precioOriginal),
    precio_promocional: strFloatPython(precioHotsale),
    precio_original_formateado: formatearPrecioArs(precioOriginal),
    precio_hotsale_formateado: formatearPrecioArs(precioHotsale),
    cuota_formateada: formatearPrecioArs(cuota),
    cuotas_num: String(producto.cuotasNum),
  };
  if (precioEfectivo !== null) {
    variables.precio_efectivo = strFloatPython(precioEfectivo);
    variables.precio_efectivo_formateado = formatearPrecioArs(precioEfectivo);
  }

  for (const [clave, valor] of Object.entries(estilo.variablesGlobales)) {
    if (!(clave in variables)) variables[clave] = valorPython(valor);
  }
  return variables;
}

// str() de Python sobre lo que trae el YAML (strings, números, booleanos).
function valorPython(valor: unknown): string {
  if (valor === null || valor === undefined) return "None";
  if (typeof valor === "boolean") return valor ? "True" : "False";
  if (typeof valor === "number") return Number.isInteger(valor) ? String(valor) : String(valor);
  return String(valor);
}

export type ResultadoReemplazo = {
  html: string;
  sinReemplazar: string[];
};

// Python: _reemplazar_variables. Reemplazo literal de "{nombre}" y aviso de
// los placeholders que quedaron (mismo regex: [a-z_]+).
export function reemplazarVariables(html: string, variables: Record<string, string>): ResultadoReemplazo {
  let resultado = html;
  for (const [nombre, valor] of Object.entries(variables)) {
    resultado = resultado.split(`{${nombre}}`).join(valor);
  }
  const sinReemplazar = [...new Set([...resultado.matchAll(/\{([a-z_]+)\}/g)].map((m) => m[1]))];
  return { html: resultado, sinReemplazar };
}
