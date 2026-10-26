// Misma lógica que src/seleccion/sync.py: parsear_metadata_template.
// Sin bloque META el pipeline usa 4:5 a 1080×1350; acá también.
export type MetaTemplate = {
  aspect_ratio: string;
  width: number;
  height: number;
  descripcion: string;
  tieneMeta: boolean;
};

export function parsearMeta(html: string): MetaTemplate {
  const meta: MetaTemplate = { aspect_ratio: "4:5", width: 1080, height: 1350, descripcion: "", tieneMeta: false };
  const m = html.match(/<!--\s*META\s*([\s\S]+?)\s*-->/);
  if (!m) {
    const d = html.match(/<!--\s*DESC:\s*([\s\S]+?)\s*-->/);
    if (d) meta.descripcion = d[1].trim();
    return meta;
  }
  meta.tieneMeta = true;
  for (const cruda of m[1].split("\n")) {
    const linea = cruda.trim();
    if (!linea || !linea.includes(":")) continue;
    const i = linea.indexOf(":");
    const clave = linea.slice(0, i).trim().toLowerCase();
    const valor = linea.slice(i + 1).trim();
    if (clave === "aspect_ratio") meta.aspect_ratio = valor;
    else if (clave === "width" && /^-?\d+$/.test(valor)) meta.width = parseInt(valor, 10);
    else if (clave === "height" && /^-?\d+$/.test(valor)) meta.height = parseInt(valor, 10);
    else if (["descripcion", "descripción", "desc"].includes(clave)) meta.descripcion = valor;
  }
  return meta;
}

/** Template nuevo de base: el mínimo que el pipeline acepta, con las variables más usadas. */
export function htmlBase(nombre: string, ancho = 1080, alto = 1350): string {
  const ratio = ancho === alto ? "1:1" : alto / ancho > 1.5 ? "9:16" : "4:5";
  return `<!-- META
nombre: ${nombre}
aspect_ratio: ${ratio}
width: ${ancho}
height: ${alto}
descripcion: Nuevo template
-->

<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { width: ${ancho}px; height: ${alto}px; background: #ffffff; font-family: Arial, sans-serif; position: relative; overflow: hidden; }
  .logo { position: absolute; top: 40px; left: 40px; width: 180px; }
  .foto { position: absolute; top: 140px; left: 80px; right: 80px; height: ${Math.round(alto * 0.5)}px; display: flex; align-items: center; justify-content: center; }
  .foto img { max-width: 100%; max-height: 100%; object-fit: contain; }
  .titulo { position: absolute; left: 60px; right: 60px; bottom: 260px; font-size: 44px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .precio { position: absolute; left: 60px; bottom: 120px; font-size: 110px; font-weight: 800; }
  .cuotas { position: absolute; left: 60px; bottom: 70px; font-size: 32px; }
</style>
</head>
<body>
  <img class="logo" src="{logo_b64}" alt="">
  <div class="foto"><img src="{imagen_b64}" alt=""></div>
  <div class="titulo">{titulo_placa}</div>
  <div class="precio">{precio_hotsale_formateado}</div>
  <div class="cuotas">{cuotas_num} cuotas de {cuota_formateada}</div>
</body>
</html>
`;
}
