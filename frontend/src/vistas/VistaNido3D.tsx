// Vista 3D del Nido de Bucaramanga: cada punto azul es un sismo a su profundidad bajo el relieve.
//   - modo "reales":    los sismos del catálogo del SGC.
//   - modo "simulados": un catálogo sintético generado por el backend, más el sismo
//                       hipotético que se configura y la sacudida que produciría.

import { COORDINATE_SYSTEM, OrbitView } from '@deck.gl/core';
import { LineLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import { SimpleMeshLayer } from '@deck.gl/mesh-layers';
import DeckGL from '@deck.gl/react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, type Sismos, type SismosSimulados, type Zona } from '../api';
import { colorDeCalor, construirTextura } from '../relieve';
import { Bloque, css, DENSIDAD_DE_PIXELES, Estado, NIVELES, Nota, numero, useDatos } from '../comun';
import { calorDeLaSacudida, ControlesDeEscenario, MAGNITUD_INICIAL, PROFUNDIDAD_INICIAL_KM, ResumenDeEscenario, useEscenario } from './Escenario';
import { BotonCentrar, ControlDeExageracion, materialDelRelieve, SelectorDeZona, useBrillo, useRelieve, zonaInicial } from './Relieve3D';

// Centro del nido: origen del sistema de coordenadas en kilómetros
const LAT0 = 6.808;
const LON0 = -73.14;
const KM_POR_GRADO_LAT = 110.57;
const KM_POR_GRADO_LON = 111.32 * Math.cos((LAT0 * Math.PI) / 180);
const MARCAS_DE_PROFUNDIDAD = [50, 100, 150, 200];

// Las etiquetas y el sismo configurado se dibujan sin que otros objetos los tapen
const SIEMPRE_ENCIMA = { depthCompare: 'always' } as const;

// Frente a 150 km de profundidad las montañas casi no se notan: se exageran para que se vean
const EXAGERACION_DEL_RELIEVE: Record<Zona, number> = { santander: 5, los_santos: 3 };

// Por defecto se simulan tantos años como cubre el catálogo real, para que las nubes sean comparables
const ANIOS_SIMULADOS_INICIALES = 17;
const ESPERA_AL_ARRASTRAR_MS = 180;

type Posicion = [number, number, number];

// Se crea una sola vez: si se creara en cada dibujo, el visor la trataría como una vista nueva
const VISTA_ORBITAL = new OrbitView({ orbitAxis: 'Z' });

const CAMARA: Record<Zona, { target: Posicion; rotationX: number; rotationOrbit: number; zoom: number }> = {
  santander: { target: [0, 0, -70], rotationX: 22, rotationOrbit: 30, zoom: 1.1 },
  los_santos: { target: [0, 0, -75], rotationX: 14, rotationOrbit: 30, zoom: 1.6 },
};

const aKm = (lon: number, lat: number, profundidad = 0): Posicion => [
  (lon - LON0) * KM_POR_GRADO_LON,
  (lat - LAT0) * KM_POR_GRADO_LAT,
  -profundidad,
];

// Un solo tono, de claro a oscuro según la magnitud
function colorPorMagnitud(magnitud: number): [number, number, number, number] {
  if (magnitud >= 5) return [13, 54, 107, 255];
  if (magnitud >= 4) return [28, 92, 171, 235];
  if (magnitud >= 3) return [57, 135, 229, 190];
  return [134, 182, 239, 140];
}

const TRAMOS_DE_MAGNITUD: [string, number][] = [
  ['2,5 a 3', 2.5],
  ['3 a 4', 3],
  ['4 a 5', 4],
  ['5 o más', 5],
];

interface Punto {
  posicion: Posicion;
  magnitud: number;
  profundidad: number;
  anio: number;
}

interface Props {
  modo: 'reales' | 'simulados';
  encabezado?: ReactNode;
}

export default function VistaNido3D({ modo, encabezado }: Props) {
  const simulando = modo === 'simulados';
  const municipios = useDatos(api.municipios);
  const grilla = useDatos(api.grillaDelSimulador);
  const [zona, setZona] = useState<Zona>(() => zonaInicial('santander'));
  const { relieve, malla, error: errorDelRelieve } = useRelieve(zona);
  const [magnitudMinima, setMagnitudMinima] = useState(2.5);
  const [magnitud, setMagnitud] = useState(MAGNITUD_INICIAL);
  const [profundidad, setProfundidad] = useState(PROFUNDIDAD_INICIAL_KM);
  const [anios, setAnios] = useState(ANIOS_SIMULADOS_INICIALES);
  const [semilla, setSemilla] = useState(1);
  const escenario = useEscenario(magnitud, profundidad, zona, simulando);
  // Cada pulsación de "Centrar vista" cambia la vista inicial y el visor recoloca la cámara
  const [centrados, setCentrados] = useState(0);
  const [brillo, setBrillo] = useBrillo();
  const [exageracion, setExageracion] = useState(EXAGERACION_DEL_RELIEVE);
  const camara = useMemo(() => ({ ...CAMARA[zona], centrados }), [zona, centrados]);

  // Sismos que se muestran: los reales, o el catálogo sintético para los años y la semilla elegidos
  const [sismos, setSismos] = useState<Sismos | SismosSimulados | null>(null);
  const [errorDeSismos, setErrorDeSismos] = useState<string | null>(null);
  useEffect(() => {
    const control = new AbortController();
    const alFallar = (e: Error) => e.name !== 'AbortError' && setErrorDeSismos(e.message);
    if (!simulando) {
      api.sismos().then((s) => !control.signal.aborted && setSismos(s)).catch(alFallar);
      return () => control.abort();
    }
    // Al arrastrar el control de años solo se pide la simulación donde se detiene
    const espera = setTimeout(() => {
      api.sismosSimulados(anios, semilla, control.signal).then(setSismos).catch(alFallar);
    }, ESPERA_AL_ARRASTRAR_MS);
    return () => {
      clearTimeout(espera);
      control.abort();
    };
  }, [simulando, anios, semilla]);

  const puntos = useMemo<Punto[]>(() => {
    if (!sismos) return [];
    return sismos.lon
      .map((lon, i) => ({
        posicion: aKm(lon, sismos.lat[i], sismos.profundidad_km[i]),
        magnitud: sismos.magnitud[i],
        profundidad: sismos.profundidad_km[i],
        anio: sismos.anio[i],
      }))
      .sort((a, b) => a.magnitud - b.magnitud); // los mayores se dibujan encima
  }, [sismos]);

  const visibles = useMemo(() => puntos.filter((p) => p.magnitud >= magnitudMinima), [puntos, magnitudMinima]);

  const mapa = simulando ? escenario.mapa : null;

  // Sobre el relieve va la sacudida simulada o, con datos reales, su color natural por altura
  const textura = useMemo(() => {
    if (!relieve || !municipios.datos) return null;
    return construirTextura(relieve, { calor: mapa ? calorDeLaSacudida(mapa.campo) : null, municipios: municipios.datos.features });
  }, [relieve, municipios.datos, mapa]);

  if (!sismos || !municipios.datos || !grilla.datos || !malla || !textura) {
    return <Estado error={errorDeSismos ?? municipios.error ?? grilla.error ?? errorDelRelieve} />;
  }

  const hipocentro = aKm(grilla.datos.epicentro.lon, grilla.datos.epicentro.lat, profundidad);
  const mayor = visibles.length > 0 ? visibles[visibles.length - 1].magnitud : null;

  const capas = [
    // Relieve: la malla está en metros y la escena en kilómetros
    new SimpleMeshLayer({
      id: 'relieve',
      data: [aKm(malla.centro[0], malla.centro[1])],
      coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
      mesh: malla as never,
      texture: textura as never,
      getPosition: (d: Posicion) => d,
      sizeScale: 0.001,
      getScale: [1, 1, exageracion[zona]],
      updateTriggers: { getScale: [exageracion[zona]] },
      material: materialDelRelieve(brillo),
    }),
    new LineLayer({
      id: 'eje',
      data: [0],
      coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
      getSourcePosition: () => [0, 0, 0],
      getTargetPosition: () => [0, 0, -200],
      getColor: [195, 194, 183],
      getWidth: 1.5,
    }),
    new ScatterplotLayer<Punto>({
      id: 'sismos',
      data: visibles,
      coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
      billboard: true,
      pickable: true,
      radiusUnits: 'pixels',
      getPosition: (d) => d.posicion,
      getRadius: (d) => 1.2 + Math.max(0, d.magnitud - 2.5) * 2.4,
      getFillColor: (d) => colorPorMagnitud(d.magnitud),
    }),
    // Las marcas van después de los puntos para que no las tapen
    new TextLayer({
      id: 'marcas',
      parameters: SIEMPRE_ENCIMA,
      data: MARCAS_DE_PROFUNDIDAD,
      coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
      getPosition: (d: number) => [0, 0, -d],
      getText: (d: number) => `${d} km`,
      getSize: 13,
      getColor: [82, 81, 78],
      getTextAnchor: 'start',
      getPixelOffset: [34, 0],
      fontFamily: 'system-ui, sans-serif',
      background: true,
      getBackgroundColor: [252, 252, 251, 215],
      backgroundPadding: [4, 2],
    }),
    simulando &&
      new ScatterplotLayer<Posicion>({
        id: 'hipocentro',
        parameters: SIEMPRE_ENCIMA,
        data: [hipocentro],
        coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
        billboard: true,
        pickable: true,
        radiusUnits: 'pixels',
        getPosition: (d) => d,
        getRadius: 7 + (magnitud - 4) * 4,
        getFillColor: [11, 11, 11, 235],
        stroked: true,
        lineWidthUnits: 'pixels',
        getLineWidth: 2.5,
        getLineColor: [252, 252, 251],
        updateTriggers: { getRadius: [magnitud] },
      }),
    simulando &&
      new TextLayer<Posicion>({
        id: 'hipocentro-etiqueta',
        parameters: SIEMPRE_ENCIMA,
        data: [hipocentro],
        coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
        getPosition: (d) => d,
        getText: () => `Sismo configurado · M ${numero(magnitud, 1)}`,
        getSize: 13,
        getColor: [11, 11, 11],
        getTextAnchor: 'end',
        getPixelOffset: [-26, 0],
        fontFamily: 'system-ui, sans-serif',
        fontWeight: 600,
        characterSet: 'auto',
        background: true,
        getBackgroundColor: [252, 252, 251, 230],
        backgroundPadding: [5, 3],
        updateTriggers: { getText: [magnitud] },
      }),
  ];

  const profundidades = visibles.map((p) => p.profundidad).sort((a, b) => a - b);
  const mediana = profundidades[Math.floor(profundidades.length / 2)];

  return (
    <div className="vista">
      {/* El clic derecho gira el relieve: se evita que además abra el menú del navegador */}
      <div className="mapa mapa-3d" onContextMenu={(e) => e.preventDefault()}>
        <DeckGL
          views={VISTA_ORBITAL}
          initialViewState={camara}
          controller
          useDevicePixels={DENSIDAD_DE_PIXELES}
          layers={capas}
          getTooltip={({ object, layer }) => {
            if (layer?.id === 'sismos' && object) {
              const p = object as Punto;
              const cuando = simulando ? `año simulado ${p.anio}` : `${p.anio}`;
              return `Sismo ${simulando ? 'simulado' : 'real'} · magnitud ${numero(p.magnitud, 1)} · ${p.profundidad} km de profundidad · ${cuando}`;
            }
            if (layer?.id === 'hipocentro') {
              return `Sismo configurado · magnitud ${numero(magnitud, 1)} · ${profundidad} km de profundidad`;
            }
            return null;
          }}
        />
        <BotonCentrar alPulsar={() => setCentrados(centrados + 1)} />
        <ControlDeExageracion
          valor={exageracion[zona]}
          alCambiar={(valor) => setExageracion({ ...exageracion, [zona]: valor })}
          brillo={brillo}
          alCambiarBrillo={setBrillo}
        />
        <div className="leyenda">
          <div className="leyenda-titulo">Magnitud de los sismos {simulando ? 'simulados' : 'reales'}</div>
          {TRAMOS_DE_MAGNITUD.map(([texto, tramo]) => {
            const [r, g, b] = colorPorMagnitud(tramo);
            return (
              <div className="leyenda-fila" key={texto}>
                <span className="muestra muestra-punto" style={{ background: `rgb(${r}, ${g}, ${b})` }} />
                <span>{texto}</span>
              </div>
            );
          })}
          {simulando && (
            <>
              <div className="leyenda-titulo leyenda-separada">Sacudida del sismo configurado</div>
              {NIVELES.map((nivel, i) => (
                <div className="leyenda-fila" key={nivel}>
                  <span className="muestra" style={{ background: css(colorDeCalor(i / 2)) }} />
                  <strong>{nivel}</strong>
                </div>
              ))}
            </>
          )}
        </div>
      </div>

      <aside className="panel">
        {encabezado}
        <div className="panel-presentacion">
          <h2>Nido 3D · {simulando ? 'sismos simulados' : 'datos reales'}</h2>
          <p className="apoyo">
            {simulando
              ? 'Cada punto azul es un sismo simulado: no ocurrió, pero sigue la misma tasa, ubicación y magnitudes que el catálogo real.'
              : 'Cada punto azul es un sismo real del catálogo del SGC, a su profundidad.'}
          </p>
        </div>

        <Bloque icono="capas" titulo="Vista del mapa">
          <SelectorDeZona zona={zona} alCambiar={setZona} />
          <Nota>
            El relieve se muestra exagerado para que las montañas se noten frente a la profundidad. Arrastra para girar
            y usa la rueda para acercar.
          </Nota>
        </Bloque>

        <Bloque icono="sismo" titulo={simulando ? 'Sismos simulados' : 'Sismos reales'} fuente={simulando ? 'Catálogo sintético' : 'SGC'}>
          {simulando && (
            <>
              <label className="control">
                <span>
                  Años simulados <strong>{anios}</strong>
                </span>
                <input type="range" min={1} max={50} step={1} value={anios} onChange={(e) => setAnios(Number(e.target.value))} />
              </label>
              <button className="boton" onClick={() => setSemilla(semilla + 1)}>
                Generar otra simulación
              </button>
            </>
          )}
          <label className="control">
            <span>
              Magnitud mínima <strong>{numero(magnitudMinima, 1)}</strong>
            </span>
            <input type="range" min={2.5} max={5} step={0.1} value={magnitudMinima} onChange={(e) => setMagnitudMinima(Number(e.target.value))} />
          </label>
          <div className="tarjetas">
            <div className="tarjeta">
              <div className="tarjeta-valor">{numero(visibles.length)}</div>
              <span>sismos visibles</span>
            </div>
            <div className="tarjeta">
              <div className="tarjeta-valor">{mediana ?? '—'} km</div>
              <span>profundidad mediana</span>
            </div>
            <div className="tarjeta">
              <div className="tarjeta-valor">{mayor !== null ? numero(mayor, 1) : '—'}</div>
              <span>magnitud mayor</span>
            </div>
          </div>
        </Bloque>

        {simulando && (
          <>
            <Bloque icono="diana" titulo="Sismo configurado">
              <ControlesDeEscenario
                limites={grilla.datos.limites}
                magnitud={magnitud}
                profundidad={profundidad}
                alCambiarMagnitud={setMagnitud}
                alCambiarProfundidad={setProfundidad}
              />
              <Nota>
                El punto negro es el sismo que configuras, y el color del relieve es la sacudida que produciría. Al
                subirlo hacia la superficie la sacudida se concentra y aparecen zonas en rojo.
              </Nota>
            </Bloque>
            {mapa ? <ResumenDeEscenario info={mapa.info} /> : <Estado error={escenario.error} />}
          </>
        )}
      </aside>
    </div>
  );
}
