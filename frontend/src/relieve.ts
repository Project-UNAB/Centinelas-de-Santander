// Construcción del relieve 3D: la malla (geometría) y la textura (colores) que se pinta encima.

import type { Municipio, Relieve } from './api';

const M_POR_GRADO_LAT = 110_570;
const M_POR_GRADO_LON_ECUADOR = 111_320;
// Ancho aproximado de la textura en píxeles: suficiente para ver el detalle sin que pese
const ANCHO_DE_TEXTURA = 1024;
// Número aproximado de vértices de la malla 3D
const VERTICES_DE_LA_MALLA = 110_000;

/**
 * Valores entre 0 y 1 en una malla regular de lat/lon (fila por fila, de norte
 * a sur) que se pintan como mapa de calor: 0 es verde, 0,5 amarillo y 1 rojo.
 */
export interface CampoDeCalor {
  oeste: number;
  este: number;
  sur: number;
  norte: number;
  filas: number;
  columnas: number;
  valores: ArrayLike<number>;
}

/** Rectángulo en lat/lon. */
export interface Marco {
  oeste: number;
  este: number;
  sur: number;
  norte: number;
}

export interface Malla {
  centro: [number, number];
  attributes: {
    positions: { value: Float32Array; size: 3 };
    normals: { value: Float32Array; size: 3 };
    texCoords: { value: Float32Array; size: 2 };
  };
  indices: { value: Uint32Array; size: 1 };
}

// Verde, amarillo y rojo del mapa de calor (los mismos de los niveles Bajo, Medio y Alto)
const PARADAS_DE_CALOR: [number, number, number][] = [
  [12, 163, 12],
  [250, 178, 25],
  [208, 59, 59],
];

/** Color del mapa de calor para un valor entre 0 (verde) y 1 (rojo). */
export function colorDeCalor(valor: number): [number, number, number] {
  const t = Math.min(1, Math.max(0, valor)) * (PARADAS_DE_CALOR.length - 1);
  const i = Math.min(Math.floor(t), PARADAS_DE_CALOR.length - 2);
  const f = t - i;
  const [a, b] = [PARADAS_DE_CALOR[i], PARADAS_DE_CALOR[i + 1]];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

// El degradado completo, ya calculado en 256 tonos (tres valores por tono: rojo, verde y azul)
const TONOS_DE_CALOR = 256;
const TABLA_DE_CALOR = new Uint8ClampedArray(TONOS_DE_CALOR * 3);
for (let tono = 0; tono < TONOS_DE_CALOR; tono++) {
  TABLA_DE_CALOR.set(colorDeCalor(tono / (TONOS_DE_CALOR - 1)), tono * 3);
}

function metrosPorCelda(r: Relieve) {
  const latCentro = (r.lat_sur + r.lat_norte) / 2;
  const mPorGradoLon = M_POR_GRADO_LON_ECUADOR * Math.cos((latCentro * Math.PI) / 180);
  return {
    dx: ((r.lon_este - r.lon_oeste) / (r.columnas - 1)) * mPorGradoLon,
    dy: ((r.lat_norte - r.lat_sur) / (r.filas - 1)) * M_POR_GRADO_LAT,
  };
}

// Lo que solo depende del relieve se calcula una vez y se guarda: al mover un control
// únicamente cambia el mapa de calor, no las montañas ni los límites
const pendientesGuardadas = new WeakMap<Relieve, { haciaEste: Float32Array; haciaNorte: Float32Array }>();
const sombreadosGuardados = new WeakMap<Relieve, Map<boolean, HTMLCanvasElement>>();
const limitesGuardados = new WeakMap<Relieve, HTMLCanvasElement>();

/**
 * Paso entre lat/lon y la escena 3D, que está en metros alrededor del centro del
 * relieve (x al este, y al norte). Es la misma conversión que usa la malla.
 */
export function proyeccionDe(r: Relieve) {
  const lonCentro = (r.lon_oeste + r.lon_este) / 2;
  const latCentro = (r.lat_sur + r.lat_norte) / 2;
  const mPorGradoLon = M_POR_GRADO_LON_ECUADOR * Math.cos((latCentro * Math.PI) / 180);
  return {
    ancho: (r.lon_este - r.lon_oeste) * mPorGradoLon,
    alto: (r.lat_norte - r.lat_sur) * M_POR_GRADO_LAT,
    aMetros: (lon: number, lat: number): [number, number] => [(lon - lonCentro) * mPorGradoLon, (lat - latCentro) * M_POR_GRADO_LAT],
    aLonLat: (x: number, y: number): [number, number] => [lonCentro + x / mPorGradoLon, latCentro + y / M_POR_GRADO_LAT],
  };
}

/** Pendiente del terreno en cada punto (este y norte), por diferencias con los vecinos. */
function pendientes(r: Relieve) {
  const guardadas = pendientesGuardadas.get(r);
  if (guardadas) return guardadas;
  const calculadas = calcularPendientes(r);
  pendientesGuardadas.set(r, calculadas);
  return calculadas;
}

function calcularPendientes(r: Relieve) {
  const { filas, columnas, elevaciones: h } = r;
  const { dx, dy } = metrosPorCelda(r);
  const haciaEste = new Float32Array(filas * columnas);
  const haciaNorte = new Float32Array(filas * columnas);
  for (let i = 0; i < filas; i++) {
    const arriba = Math.max(i - 1, 0);
    const abajo = Math.min(i + 1, filas - 1);
    for (let j = 0; j < columnas; j++) {
      const k = i * columnas + j;
      if (h[k] < 0) continue;
      const izquierda = Math.max(j - 1, 0);
      const derecha = Math.min(j + 1, columnas - 1);
      // Un vecino fuera del departamento se toma a la misma altura: evita un falso acantilado en el borde
      const altura = (indice: number) => (h[indice] < 0 ? h[k] : h[indice]);
      haciaEste[k] = (altura(i * columnas + derecha) - altura(i * columnas + izquierda)) / ((derecha - izquierda) * dx);
      // La fila 0 es el norte, así que "arriba" está más al norte
      haciaNorte[k] = (altura(arriba * columnas + j) - altura(abajo * columnas + j)) / ((abajo - arriba) * dy);
    }
  }
  return { haciaEste, haciaNorte };
}

/**
 * Malla del terreno en metros alrededor de su centro: x al este, y al norte y
 * z hacia arriba, con la cota más baja en cero. Los puntos fuera del
 * departamento (altura negativa) no generan triángulos.
 */
export function construirMalla(r: Relieve): Malla {
  const { filas, columnas, elevaciones } = r;
  const { dx, dy } = metrosPorCelda(r);
  const inclinacion = pendientes(r);

  // La malla usa uno de cada `salto` puntos: el detalle fino de las montañas lo da
  // el sombreado de la textura, así que con menos triángulos se ve igual y gira fluido
  const salto = Math.max(1, Math.ceil(Math.sqrt((filas * columnas) / VERTICES_DE_LA_MALLA)));
  const muestras = (total: number) => {
    const indices: number[] = [];
    for (let k = 0; k < total - 1; k += salto) indices.push(k);
    indices.push(total - 1);
    return indices;
  };
  const filasUsadas = muestras(filas);
  const columnasUsadas = muestras(columnas);
  const nf = filasUsadas.length;
  const nc = columnasUsadas.length;

  const posiciones = new Float32Array(nf * nc * 3);
  const normales = new Float32Array(nf * nc * 3);
  const texturas = new Float32Array(nf * nc * 2);
  const dentro = new Uint8Array(nf * nc);

  filasUsadas.forEach((i, fi) => {
    columnasUsadas.forEach((j, cj) => {
      const k = fi * nc + cj;
      const altura = elevaciones[i * columnas + j];
      dentro[k] = altura >= 0 ? 1 : 0;
      posiciones[k * 3] = (j - (columnas - 1) / 2) * dx;
      posiciones[k * 3 + 1] = ((filas - 1) / 2 - i) * dy;
      posiciones[k * 3 + 2] = Math.max(0, altura - r.elevacion_min);
      // Hacia dónde mira el terreno en ese punto: solo se usa cuando se activa el brillo
      const haciaEste = inclinacion.haciaEste[i * columnas + j];
      const haciaNorte = inclinacion.haciaNorte[i * columnas + j];
      const largo = Math.hypot(haciaEste, haciaNorte, 1);
      normales[k * 3] = -haciaEste / largo;
      normales[k * 3 + 1] = -haciaNorte / largo;
      normales[k * 3 + 2] = 1 / largo;
      texturas[k * 2] = j / (columnas - 1);
      texturas[k * 2 + 1] = i / (filas - 1);
    });
  });

  // Dos triángulos por cada cuadro de la malla que esté completo dentro del departamento
  const indices = new Uint32Array((nf - 1) * (nc - 1) * 6);
  let p = 0;
  for (let fi = 0; fi < nf - 1; fi++) {
    for (let cj = 0; cj < nc - 1; cj++) {
      const a = fi * nc + cj;
      const b = a + 1;
      const c = a + nc;
      const d = c + 1;
      if (!dentro[a] || !dentro[b] || !dentro[c] || !dentro[d]) continue;
      indices.set([a, c, b, b, c, d], p);
      p += 6;
    }
  }

  return {
    centro: [(r.lon_oeste + r.lon_este) / 2, (r.lat_sur + r.lat_norte) / 2],
    attributes: {
      positions: { value: posiciones, size: 3 },
      normals: { value: normales, size: 3 },
      texCoords: { value: texturas, size: 2 },
    },
    indices: { value: indices.slice(0, p), size: 1 },
  };
}

// Tinte por altura para cuando no hay mapa de calor: de los valles (verde) a las cumbres (ocre)
const TINTE_POR_ALTURA: [number, [number, number, number]][] = [
  [0, [84, 130, 96]],
  [0.3, [170, 190, 130]],
  [0.6, [214, 198, 150]],
  [1, [176, 140, 110]],
];

function tinte(t: number): [number, number, number] {
  for (let s = 1; s < TINTE_POR_ALTURA.length; s++) {
    const [t0, c0] = TINTE_POR_ALTURA[s - 1];
    const [t1, c1] = TINTE_POR_ALTURA[s];
    if (t <= t1) {
      const f = (t - t0) / (t1 - t0);
      return [c0[0] + (c1[0] - c0[0]) * f, c0[1] + (c1[1] - c0[1]) * f, c0[2] + (c1[2] - c0[2]) * f];
    }
  }
  return TINTE_POR_ALTURA[TINTE_POR_ALTURA.length - 1][1];
}

/**
 * Sombreado del relieve (luz desde el noroeste), opcionalmente teñido por
 * altura. Es lo que hace que las montañas se lean aunque encima vaya un color.
 */
function sombreado(r: Relieve, conTinte: boolean): HTMLCanvasElement {
  let delRelieve = sombreadosGuardados.get(r);
  if (!delRelieve) {
    delRelieve = new Map();
    sombreadosGuardados.set(r, delRelieve);
  }
  let lienzo = delRelieve.get(conTinte);
  if (!lienzo) {
    lienzo = calcularSombreado(r, conTinte);
    delRelieve.set(conTinte, lienzo);
  }
  return lienzo;
}

function calcularSombreado(r: Relieve, conTinte: boolean): HTMLCanvasElement {
  const { filas, columnas, elevaciones } = r;
  const { haciaEste, haciaNorte } = pendientes(r);
  const { dx } = metrosPorCelda(r);
  // Con puntos más separados las pendientes salen más suaves: se realzan más
  const realce = dx > 200 ? 4 : 1.6;
  const LUZ = [-0.5, 0.5, 0.7071];
  const lienzo = document.createElement('canvas');
  lienzo.width = columnas;
  lienzo.height = filas;
  const contexto = lienzo.getContext('2d')!;
  const imagen = contexto.createImageData(columnas, filas);

  for (let k = 0; k < filas * columnas; k++) {
    const nx = -haciaEste[k] * realce;
    const ny = -haciaNorte[k] * realce;
    const luz = Math.max(0, (nx * LUZ[0] + ny * LUZ[1] + LUZ[2]) / Math.hypot(nx, ny, 1));
    // Bajo un color el sombreado es más suave, para que el amarillo no se vuelva ocre
    const gris = conTinte ? Math.min(255, 60 + 220 * luz) : Math.min(255, 160 + 135 * luz);
    const [red, verde, azul] = conTinte
      ? tinte((Math.max(elevaciones[k], r.elevacion_min) - r.elevacion_min) / (r.elevacion_max - r.elevacion_min))
      : [255, 255, 255];
    imagen.data[k * 4] = (red * gris) / 255;
    imagen.data[k * 4 + 1] = (verde * gris) / 255;
    imagen.data[k * 4 + 2] = (azul * gris) / 255;
    imagen.data[k * 4 + 3] = 255;
  }
  contexto.putImageData(imagen, 0, 0);
  return lienzo;
}

/** Imagen del mapa de calor a la resolución de sus datos; al ampliarla el navegador la suaviza. */
function imagenDeCalor(calor: CampoDeCalor): HTMLCanvasElement {
  const lienzo = document.createElement('canvas');
  lienzo.width = calor.columnas;
  lienzo.height = calor.filas;
  const contexto = lienzo.getContext('2d')!;
  const imagen = contexto.createImageData(calor.columnas, calor.filas);
  for (let k = 0; k < calor.filas * calor.columnas; k++) {
    // El color sale de una tabla ya calculada: sin operaciones ni memoria nueva por punto
    const t = Math.round(Math.min(1, Math.max(0, calor.valores[k])) * (TONOS_DE_CALOR - 1)) * 3;
    imagen.data[k * 4] = TABLA_DE_CALOR[t];
    imagen.data[k * 4 + 1] = TABLA_DE_CALOR[t + 1];
    imagen.data[k * 4 + 2] = TABLA_DE_CALOR[t + 2];
    imagen.data[k * 4 + 3] = 255;
  }
  contexto.putImageData(imagen, 0, 0);
  return lienzo;
}

/** Límites municipales sobre fondo transparente, al tamaño de la textura; Los Santos resaltado. */
function limites(r: Relieve, municipios: Municipio[], ancho: number, alto: number): HTMLCanvasElement {
  const guardados = limitesGuardados.get(r);
  if (guardados) return guardados;

  const lienzo = document.createElement('canvas');
  lienzo.width = ancho;
  lienzo.height = alto;
  const c = lienzo.getContext('2d')!;
  const x = (lon: number) => ((lon - r.lon_oeste) / (r.lon_este - r.lon_oeste)) * ancho;
  const y = (lat: number) => ((r.lat_norte - lat) / (r.lat_norte - r.lat_sur)) * alto;
  for (const m of municipios) {
    const principal = m.properties.municipio === 'Los Santos';
    c.strokeStyle = principal ? 'rgba(11, 11, 11, 0.95)' : 'rgba(11, 11, 11, 0.35)';
    c.lineWidth = principal ? 2.5 : 1;
    const poligonos = m.geometry.type === 'Polygon' ? [m.geometry.coordinates] : m.geometry.coordinates;
    for (const poligono of poligonos) {
      c.beginPath();
      poligono[0].forEach(([lon, lat], i) => (i === 0 ? c.moveTo(x(lon), y(lat)) : c.lineTo(x(lon), y(lat))));
      c.stroke();
    }
  }
  limitesGuardados.set(r, lienzo);
  return lienzo;
}

interface OpcionesDeTextura {
  /** Mapa de calor que se pinta encima; sin él, el relieve se tiñe por altura */
  calor: CampoDeCalor | null;
  municipios: Municipio[];
  /** Rectángulo que se resalta con un borde oscuro (la celda elegida) */
  marco?: Marco | null;
  /** Celdas del modelo: si se dan, se dibujan sus bordes y sus números sobre el mapa de calor */
  cuadricula?: (Marco & { etiqueta: string })[] | null;
  /** Celdas en las que el modelo falló: se marcan con un borde discontinuo y una equis */
  fallos?: Marco[] | null;
}

/**
 * Textura que se pinta sobre la malla: sombreado del relieve, mapa de calor y
 * límites municipales. Devuelve el lienzo, que el visor 3D sube tal cual a la
 * tarjeta gráfica (sin codificarlo como imagen, que sería más lento).
 */
export function construirTextura(r: Relieve, { calor, municipios, marco, cuadricula, fallos }: OpcionesDeTextura): HTMLCanvasElement {
  const pixelesPorCelda = Math.min(4, Math.max(1, Math.round(ANCHO_DE_TEXTURA / r.columnas)));
  const ancho = r.columnas * pixelesPorCelda;
  const alto = r.filas * pixelesPorCelda;
  const x = (lon: number) => ((lon - r.lon_oeste) / (r.lon_este - r.lon_oeste)) * ancho;
  const y = (lat: number) => ((r.lat_norte - lat) / (r.lat_norte - r.lat_sur)) * alto;

  const lienzo = document.createElement('canvas');
  lienzo.width = ancho;
  lienzo.height = alto;
  const c = lienzo.getContext('2d')!;
  c.imageSmoothingEnabled = true;
  c.imageSmoothingQuality = 'high';
  c.drawImage(sombreado(r, calor === null), 0, 0, ancho, alto);

  if (calor) {
    // El color se multiplica por el sombreado: tiñe sin borrar el relieve
    c.globalCompositeOperation = 'multiply';
    c.drawImage(imagenDeCalor(calor), x(calor.oeste), y(calor.norte), x(calor.este) - x(calor.oeste), y(calor.sur) - y(calor.norte));
    c.globalCompositeOperation = 'source-over';
  }

  c.drawImage(limites(r, municipios, ancho, alto), 0, 0);

  if (cuadricula) {
    c.font = '600 28px system-ui, sans-serif';
    c.textAlign = 'center';
    c.textBaseline = 'middle';
    for (const celda of cuadricula) {
      c.strokeStyle = 'rgba(252, 252, 251, 0.9)';
      c.lineWidth = 1.5;
      c.strokeRect(x(celda.oeste), y(celda.norte), x(celda.este) - x(celda.oeste), y(celda.sur) - y(celda.norte));
      // Número de la celda, con un borde claro para que se lea sobre cualquier color
      const cx = x((celda.oeste + celda.este) / 2);
      const cy = y((celda.sur + celda.norte) / 2);
      c.lineWidth = 4;
      c.strokeText(celda.etiqueta, cx, cy);
      c.fillStyle = '#0b0b0b';
      c.fillText(celda.etiqueta, cx, cy);
    }
  }

  if (fallos) {
    for (const fallo of fallos) {
      // Todo se mide con el lado de la celda, para que la marca sirva en las dos zonas
      const lado = x(fallo.este) - x(fallo.oeste);
      const grosor = Math.max(1.5, lado * 0.022);
      const margen = grosor * 1.5;
      const [izquierda, arriba] = [x(fallo.oeste) + margen, y(fallo.norte) + margen];
      const [anchoDelBorde, altoDelBorde] = [lado - margen * 2, y(fallo.sur) - y(fallo.norte) - margen * 2];
      const equis = lado * 0.11;
      const [ex, ey] = [x(fallo.este) - margen * 2.4 - equis, arriba + margen * 1.4 + equis];
      // Primero en claro y más grueso, luego en oscuro: se distingue sobre cualquier color
      for (const [color, ancho] of [['#fcfcfb', grosor * 2.4], ['#0b0b0b', grosor]] as const) {
        c.strokeStyle = color;
        c.lineWidth = ancho;
        c.setLineDash(color === '#0b0b0b' ? [grosor * 4, grosor * 3] : []);
        c.strokeRect(izquierda, arriba, anchoDelBorde, altoDelBorde);
        c.setLineDash([]);
        c.beginPath();
        c.moveTo(ex - equis, ey - equis);
        c.lineTo(ex + equis, ey + equis);
        c.moveTo(ex + equis, ey - equis);
        c.lineTo(ex - equis, ey + equis);
        c.stroke();
      }
    }
  }

  if (marco) {
    c.strokeStyle = '#fcfcfb';
    c.lineWidth = 7;
    c.strokeRect(x(marco.oeste), y(marco.norte), x(marco.este) - x(marco.oeste), y(marco.sur) - y(marco.norte));
    c.strokeStyle = '#0b0b0b';
    c.lineWidth = 3;
    c.strokeRect(x(marco.oeste), y(marco.norte), x(marco.este) - x(marco.oeste), y(marco.sur) - y(marco.norte));
  }

  return lienzo;
}
