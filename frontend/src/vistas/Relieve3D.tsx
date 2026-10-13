// Relieve 3D compartido por las vistas: carga por zona, capa y selector de zona.

import { COORDINATE_SYSTEM, OrbitView } from '@deck.gl/core';
import { ScatterplotLayer } from '@deck.gl/layers';
import { SimpleMeshLayer } from '@deck.gl/mesh-layers';
import { useEffect, useState, type ReactNode } from 'react';
import { api, type Municipio, type Nivel, type Poblacion, type Relieve, type Zona } from '../api';
import { construirMalla, proyeccionDe, type Malla } from '../relieve';
import { Bloque, EtiquetaDeNivel, Icono, Nota } from '../comun';

export const ZONAS: { id: Zona; nombre: string }[] = [
  { id: 'santander', nombre: 'Santander completo' },
  { id: 'los_santos', nombre: 'Solo Los Santos' },
];

// El relieve de Santander abarca 250 km: sin exagerarlo más, las montañas no se notarían
export const EXAGERACION_INICIAL: Record<Zona, number> = { santander: 4, los_santos: 1.5 };

// Material del relieve: solo luz ambiente, sin luz direccional ni reflejos. El sombreado de
// las montañas ya va pintado en la textura; así no aparece ningún brillo al girar la cámara,
// tampoco en las tarjetas gráficas que no respetan el apagado completo de la iluminación
export const SIN_BRILLO = { ambient: 1, diffuse: 0, shininess: 1, specularColor: [0, 0, 0] as [number, number, number] };

// Con brillo: las luces del visor iluminan las laderas y dejan un reflejo que cambia al girar
const CON_BRILLO = { ambient: 0.7, diffuse: 0.45, shininess: 24, specularColor: [70, 70, 70] as [number, number, number] };

// La cámara gira alrededor del relieve, que queda siempre en el centro de la pantalla
export const VISTA_ORBITAL = new OrbitView({ orbitAxis: 'Z' });

// Arrastrar gira en cualquier dirección; con clic derecho (o Mayús) se desplaza la
// cámara, y la rueda acerca
export const CONTROL_ORBITAL = { dragPan: true, dragRotate: true, scrollZoom: true, doubleClickZoom: true, touchZoom: true, touchRotate: true };

export const AYUDA_DE_CAMARA = 'Arrastra para girar, usa clic derecho (o Mayús + arrastrar) para mover la cámara y la rueda para acercar.';

const ANCHO_EN_PANTALLA_PX = 540;   // tamaño aproximado del relieve al abrir la vista
const INCLINACION_INICIAL = 38;     // grados sobre el horizonte
const GIRO_INICIAL = -15;

/**
 * Cámara inicial para un relieve. La inclinación va de 0° (de frente, a ras del
 * suelo) a 90° (desde arriba): no se puede bajar más, así nunca se ve por debajo.
 */
export function camaraOrbital(relieve: Relieve, centrados = 0) {
  const { ancho, alto } = proyeccionDe(relieve);
  const zoom = Math.log2(ANCHO_EN_PANTALLA_PX / Math.max(ancho, alto));
  return {
    // El visor solo recoloca la cámara si la vista inicial cambia: este contador,
    // que sube con cada pulsación de "Centrar vista", es lo que la hace cambiar
    centrados,
    target: [0, 0, 0] as [number, number, number],
    rotationX: INCLINACION_INICIAL,
    rotationOrbit: GIRO_INICIAL,
    zoom,
    minRotationX: 0,
    maxRotationX: 90,
    minZoom: zoom - 1.5,
    maxZoom: zoom + 4,
  };
}

/** Zona indicada en la dirección (#simulados/zona/los_santos) o, si no hay, la que la vista prefiera. */
export function zonaInicial(porDefecto: Zona): Zona {
  const pedida = window.location.hash.split('/')[2];
  return ZONAS.find((z) => z.id === pedida)?.id ?? porDefecto;
}

interface RelieveListo {
  relieve: Relieve;
  malla: Malla;
}

// Cada relieve se descarga y se convierte en malla una sola vez, aunque lo pidan varias vistas
const cargados = new Map<Zona, Promise<RelieveListo>>();

function cargar(zona: Zona) {
  if (!cargados.has(zona)) {
    const promesa = api.relieve(zona).then((relieve) => ({ relieve, malla: construirMalla(relieve) }));
    promesa.catch(() => cargados.delete(zona));
    cargados.set(zona, promesa);
  }
  return cargados.get(zona)!;
}

/** Relieve y malla de la zona elegida; mientras carga devuelve null. */
export function useRelieve(zona: Zona) {
  const [listo, setListo] = useState<(RelieveListo & { zona: Zona }) | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let vigente = true;
    cargar(zona)
      .then((r) => vigente && setListo({ ...r, zona }))
      .catch((e: Error) => vigente && setError(e.message));
    return () => {
      vigente = false;
    };
  }, [zona]);

  // Al cambiar de zona, lo anterior deja de valer hasta que llegue lo nuevo
  const vigente = listo?.zona === zona ? listo : null;
  return { relieve: vigente?.relieve ?? null, malla: vigente?.malla ?? null, error };
}

/** Capa del relieve, en metros alrededor de su centro (el origen de la escena). */
export function capaDeRelieve(malla: Malla, textura: HTMLCanvasElement, exageracion: number, brillo: boolean) {
  return new SimpleMeshLayer({
    id: 'relieve',
    data: [0],
    coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
    mesh: malla as never,
    texture: textura as never,
    pickable: true,
    getPosition: () => [0, 0, 0],
    // La exageración vertical solo estira la altura
    getScale: [1, 1, exageracion],
    material: materialDelRelieve(brillo),
    updateTriggers: { getScale: [exageracion] },
  });
}

/** Sin brillo, los colores se ven tal cual; con brillo, las luces del visor añaden reflejos. */
export const materialDelRelieve = (brillo: boolean) => (brillo ? CON_BRILLO : SIN_BRILLO);

// La elección se recuerda al cambiar de vista o de sección
let brilloElegido = true;

/** Si el relieve se dibuja con brillo, y cómo cambiarlo. */
export function useBrillo(): [boolean, (brillo: boolean) => void] {
  const [brillo, setBrillo] = useState(brilloElegido);
  return [
    brillo,
    (nuevo) => {
      brilloElegido = nuevo;
      setBrillo(nuevo);
    },
  ];
}

/** Punto elegido sobre el relieve, en coordenadas geográficas reales. */
export type Punto = [lon: number, lat: number];

/**
 * Posición de un punto geográfico en la escena 3D, apoyado sobre el terreno
 * (con la misma exageración vertical que el relieve).
 */
export function posicionEnEscena(relieve: Relieve, punto: Punto, exageracion: number): [number, number, number] {
  const altura = alturaEn(relieve, punto) ?? relieve.elevacion_min;
  return [...proyeccionDe(relieve).aMetros(punto[0], punto[1]), (altura - relieve.elevacion_min) * exageracion];
}

/** Marca del punto elegido: un círculo claro con borde oscuro, siempre visible sobre el relieve. */
export function capaDelPunto(relieve: Relieve, punto: Punto | null, exageracion: number) {
  return new ScatterplotLayer<Punto>({
    id: 'punto-elegido',
    data: punto ? [punto] : [],
    parameters: { depthCompare: 'always' },
    coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
    billboard: true,
    getPosition: (p) => posicionEnEscena(relieve, p, exageracion),
    updateTriggers: { getPosition: [exageracion] },
    radiusUnits: 'pixels',
    getRadius: 5,
    getFillColor: [252, 252, 251],
    stroked: true,
    lineWidthUnits: 'pixels',
    getLineWidth: 2.5,
    getLineColor: [11, 11, 11],
  });
}

/** Altura del terreno (m s. n. m.) en un punto, leída del modelo de elevación. */
export function alturaEn(relieve: Relieve, [lon, lat]: Punto) {
  const columna = Math.round(((lon - relieve.lon_oeste) / (relieve.lon_este - relieve.lon_oeste)) * (relieve.columnas - 1));
  const fila = Math.round(((relieve.lat_norte - lat) / (relieve.lat_norte - relieve.lat_sur)) * (relieve.filas - 1));
  if (columna < 0 || columna >= relieve.columnas || fila < 0 || fila >= relieve.filas) return null;
  const altura = relieve.elevaciones[fila * relieve.columnas + columna];
  return altura >= 0 ? altura : null;
}

/** Municipio que contiene el punto (se cuenta cuántas veces una línea hacia el este cruza su contorno). */
function municipioEn(municipios: Municipio[], [lon, lat]: Punto) {
  const dentroDe = (anillo: number[][]) => {
    let dentro = false;
    for (let i = 0, j = anillo.length - 1; i < anillo.length; j = i++) {
      const [xi, yi] = anillo[i];
      const [xj, yj] = anillo[j];
      if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) dentro = !dentro;
    }
    return dentro;
  };
  for (const m of municipios) {
    const poligonos = m.geometry.type === 'Polygon' ? [m.geometry.coordinates] : m.geometry.coordinates;
    if (poligonos.some((poligono) => dentroDe(poligono[0]))) return m.properties.municipio;
  }
  return null;
}

const grados = (valor: number) => Math.abs(valor).toLocaleString('es-CO', { minimumFractionDigits: 5, maximumFractionDigits: 5 });

interface PropsDePunto {
  punto: Punto;
  relieve: Relieve;
  municipios: Municipio[];
  /** Celda del modelo que contiene el punto, si cae dentro de la zona del modelo */
  celda: { cell_id: number } | null;
  /** Población por municipio; si se da, la ficha dice cuántas personas viven en el municipio del punto */
  poblacion?: Poblacion | null;
  /** Nivel de sacudida con que cuenta cada municipio en el sismo simulado, en el orden de la población */
  nivelPorMunicipio?: Nivel[];
  /** Viviendas afectadas (valor central) que el modelo estima para cada municipio, en el orden de la población */
  viviendasAfectadas?: number[];
  /** Filas adicionales propias de cada vista (por ejemplo, la intensidad simulada) */
  children?: ReactNode;
}

/** Ficha del punto elegido: coordenadas reales, municipio, altura y celda del modelo. */
export function PuntoElegido({ punto, relieve, municipios, celda, poblacion, nivelPorMunicipio, viviendasAfectadas, children }: PropsDePunto) {
  const [lon, lat] = punto;
  const altura = alturaEn(relieve, punto);
  const municipio = municipioEn(municipios, punto);
  // El DANE publica la población por municipio, no por punto: se muestra la del municipio completo
  const posicion = municipio && poblacion ? poblacion.municipio.indexOf(municipio) : -1;
  const habitantes = posicion >= 0 ? poblacion!.habitantes[posicion] : null;
  const nivelDelMunicipio = posicion >= 0 ? nivelPorMunicipio?.[posicion] : undefined;
  const afectadasDelMunicipio = posicion >= 0 ? viviendasAfectadas?.[posicion] : undefined;
  return (
    <Bloque icono="punto" titulo="Punto elegido">
      <table className="tabla">
        <tbody>
          <tr>
            <td>Latitud</td>
            <td className="num">
              {grados(lat)}° {lat >= 0 ? 'N' : 'S'}
            </td>
          </tr>
          <tr>
            <td>Longitud</td>
            <td className="num">
              {grados(lon)}° {lon >= 0 ? 'E' : 'O'}
            </td>
          </tr>
          <tr>
            <td>En decimales (lat, lon)</td>
            <td className="num">
              {lat.toFixed(5)}, {lon.toFixed(5)}
            </td>
          </tr>
          <tr>
            <td>Municipio</td>
            <td className="num">{municipio ?? '—'}</td>
          </tr>
          <tr>
            <td>Altura del terreno</td>
            <td className="num">{altura !== null ? `${altura.toLocaleString('es-CO')} m` : '—'}</td>
          </tr>
          <tr>
            <td>Celda del modelo</td>
            <td className="num">{celda ? `Celda ${celda.cell_id}` : 'Fuera de la zona del modelo'}</td>
          </tr>
          {children}
        </tbody>
      </table>

      {habitantes !== null && (
        <>
          <div className="personas-del-punto">
            <span className="bloque-icono">
              <Icono nombre="personas" />
            </span>
            <div>
              <strong>{habitantes.toLocaleString('es-CO')} personas</strong>
              <span>
                viven en {municipio}
                {nivelDelMunicipio && (
                  <>
                    {' '}
                    · con este sismo cuentan en <EtiquetaDeNivel nivel={nivelDelMunicipio} />
                  </>
                )}
              </span>
            </div>
            <span className="fuente">DANE · {poblacion!.anio}</span>
          </div>
          {afectadasDelMunicipio !== undefined && (
            <div className="personas-del-punto">
              <span className="bloque-icono">
                <Icono nombre="casa" />
              </span>
              <div>
                <strong>≈ {Math.round(afectadasDelMunicipio).toLocaleString('es-CO')} viviendas afectadas</strong>
                <span>
                  de las {poblacion!.viviendas[posicion].toLocaleString('es-CO')} de {municipio}, como orden de magnitud
                </span>
              </div>
            </div>
          )}
          <Nota>
            Es la población de todo el municipio, no la de este punto: el DANE no publica cuántas personas viven en
            cada lugar.{nivelDelMunicipio && ' El nivel es el del municipio completo y puede diferir del de este punto.'}
          </Nota>
        </>
      )}
    </Bloque>
  );
}

const EXAGERACION_MAXIMA = 8;

interface PropsDeAjustes {
  valor: number;
  alCambiar: (valor: number) => void;
  brillo: boolean;
  alCambiarBrillo: (brillo: boolean) => void;
}

/** Recuadro sobre el visor, a la izquierda: altura del relieve y brillo. */
export function ControlDeExageracion({ valor, alCambiar, brillo, alCambiarBrillo }: PropsDeAjustes) {
  return (
    <div className="control-sobre-mapa">
      <label className="control">
        <span>
          Exageración vertical del relieve <strong>× {valor.toLocaleString('es-CO', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</strong>
        </span>
        <input type="range" min={1} max={EXAGERACION_MAXIMA} step={0.1} value={valor} onChange={(e) => alCambiar(Number(e.target.value))} />
      </label>
      <label className="casilla">
        <input type="checkbox" checked={brillo} onChange={(e) => alCambiarBrillo(e.target.checked)} />
        <span>Brillo en el relieve</span>
      </label>
    </div>
  );
}

/** Botón sobre el visor que devuelve la cámara a su posición inicial. */
export function BotonCentrar({ alPulsar }: { alPulsar: () => void }) {
  return (
    <button className="boton boton-sobre-mapa" onClick={alPulsar} title="Volver a la posición inicial de la cámara">
      Centrar vista
    </button>
  );
}

export function SelectorDeZona({ zona, alCambiar }: { zona: Zona; alCambiar: (zona: Zona) => void }) {
  return (
    <div className="selector" role="group" aria-label="Zona que se muestra">
      {ZONAS.map((z) => (
        <button key={z.id} className={z.id === zona ? 'activa' : undefined} aria-pressed={z.id === zona} onClick={() => alCambiar(z.id)}>
          {z.nombre}
        </button>
      ))}
    </div>
  );
}
