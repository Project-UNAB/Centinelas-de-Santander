// Simulador: sacudida esperada para un sismo hipotético de magnitud y profundidad dadas,
// pintada como mapa de calor sobre el relieve 3D. Aquí todo es simulado: no se muestran datos reales.

import { COORDINATE_SYSTEM } from '@deck.gl/core';
import { ScatterplotLayer } from '@deck.gl/layers';
import DeckGL, { type DeckGLRef } from '@deck.gl/react';
import { useMemo, useRef, useState, type ReactNode } from 'react';
import { api, type Zona } from '../api';
import { Bloque, DENSIDAD_DE_PIXELES, Estado, EtiquetaDeNivel, LeyendaDeCalor, Nota, numero, PanelDesplegable, useDatos } from '../comun';
import { construirTextura, proyeccionDe } from '../relieve';
import {
  calorDeLaSacudida,
  ControlesDeEscenario,
  enRomanos,
  MAGNITUD_INICIAL,
  nivelDeIntensidad,
  PROFUNDIDAD_INICIAL_KM,
  ResumenDeEscenario,
  useEscenario,
} from './Escenario';
import { AYUDA_DE_CAMARA, BotonCentrar, camaraOrbital, ControlDeExageracion, capaDeRelieve, CONTROL_ORBITAL, EXAGERACION_INICIAL, posicionEnEscena, PuntoElegido, SelectorDeZona, useBrillo, useRelieve, VISTA_ORBITAL, zonaInicial, type Punto } from './Relieve3D';

export default function VistaSimulador({ encabezado }: { encabezado?: ReactNode }) {
  const grilla = useDatos(api.grillaDelSimulador);
  const municipios = useDatos(api.municipios);
  const celdas = useDatos(api.celdasDeRiesgo);
  const poblacion = useDatos(api.poblacion);
  const [zona, setZona] = useState<Zona>(() => zonaInicial('santander'));
  const { relieve, malla, error: errorDelRelieve } = useRelieve(zona);
  const [magnitud, setMagnitud] = useState(MAGNITUD_INICIAL);
  const [profundidad, setProfundidad] = useState(PROFUNDIDAD_INICIAL_KM);
  const { mapa, error } = useEscenario(magnitud, profundidad, zona, true);
  const [punto, setPunto] = useState<Punto | null>(null);
  const [exageracion, setExageracion] = useState(EXAGERACION_INICIAL);
  const deck = useRef<DeckGLRef>(null);

  const campo = mapa?.campo ?? null;

  // Celdas del modelo de riesgo, como referencia: la sacudida no se calcula por celda, sino en
  // una malla más fina. Solo se ofrecen en Los Santos; en todo Santander no se distinguirían
  const [verCeldas, setVerCeldas] = useState(false);
  const cuadricula = useMemo(() => {
    if (!verCeldas || zona !== 'los_santos' || !celdas.datos) return null;
    return celdas.datos.features.map((f) => {
      const lons = f.geometry.coordinates[0].map((p) => p[0]);
      const lats = f.geometry.coordinates[0].map((p) => p[1]);
      return { oeste: Math.min(...lons), este: Math.max(...lons), sur: Math.min(...lats), norte: Math.max(...lats), etiqueta: String(f.properties.cell_id) };
    });
  }, [verCeldas, zona, celdas.datos]);

  const textura = useMemo(
    () =>
      relieve && municipios.datos && campo
        ? construirTextura(relieve, { calor: calorDeLaSacudida(campo), municipios: municipios.datos.features, cuadricula })
        : null,
    [relieve, municipios.datos, campo, cuadricula],
  );

  // La cámara inicial solo cambia con el relieve: si cambiara en cada dibujo, la vista se reiniciaría
  const [centrados, setCentrados] = useState(0);
  const [brillo, setBrillo] = useBrillo();
  const camara = useMemo(() => (relieve ? camaraOrbital(relieve, centrados) : null), [relieve, centrados]);

  if (!grilla.datos || !municipios.datos || !mapa || !campo || !relieve || !malla || !textura || !camara) {
    return <Estado error={grilla.error ?? municipios.error ?? errorDelRelieve ?? error} />;
  }
  const { aLonLat } = proyeccionDe(relieve);

  // Intensidad en el punto elegido, leída de la malla fina
  const intensidadEn = ([lon, lat]: [number, number]) => {
    const columna = Math.floor(((lon - campo.oeste) / (campo.este - campo.oeste)) * campo.columnas);
    const fila = Math.floor(((campo.norte - lat) / (campo.norte - campo.sur)) * campo.filas);
    if (columna < 0 || columna >= campo.columnas || fila < 0 || fila >= campo.filas) return null;
    return campo.mmi[fila * campo.columnas + columna];
  };
  const intensidadDelPunto = punto ? intensidadEn(punto) : null;

  // Celda del modelo de riesgo que contiene el punto, si cae dentro de su zona
  const celdaDelPunto =
    (punto &&
      celdas.datos?.features.find((f) => {
        const lons = f.geometry.coordinates[0].map((p) => p[0]);
        const lats = f.geometry.coordinates[0].map((p) => p[1]);
        return punto[0] >= Math.min(...lons) && punto[0] < Math.max(...lons) && punto[1] >= Math.min(...lats) && punto[1] < Math.max(...lats);
      })?.properties) ??
    null;

  const capas = [
    capaDeRelieve(malla, textura, exageracion[zona], brillo),
    new ScatterplotLayer<{ lon: number; lat: number; epicentro: boolean }>({
      id: 'marcas',
      data: [
        { lon: grilla.datos.epicentro.lon, lat: grilla.datos.epicentro.lat, epicentro: true },
        ...(punto && intensidadDelPunto !== null ? [{ lon: punto[0], lat: punto[1], epicentro: false }] : []),
      ],
      // Sin prueba de profundidad, para que el relieve no las tape
      parameters: { depthCompare: 'always' },
      coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
      billboard: true,
      getPosition: (d) => posicionEnEscena(relieve, [d.lon, d.lat], exageracion[zona]),
      updateTriggers: { getPosition: [exageracion[zona]] },
      radiusUnits: 'pixels',
      getRadius: (d) => (d.epicentro ? 8 : 5),
      getFillColor: (d) => (d.epicentro ? [11, 11, 11] : [252, 252, 251]),
      stroked: true,
      lineWidthUnits: 'pixels',
      getLineWidth: 2.5,
      getLineColor: (d) => (d.epicentro ? [252, 252, 251] : [11, 11, 11]),
    }),
  ];

  return (
    <div className="vista">
      {/* El clic derecho gira el relieve: se evita que además abra el menú del navegador */}
      <div className="mapa mapa-3d" onContextMenu={(e) => e.preventDefault()}>
        <DeckGL
          ref={deck}
          views={VISTA_ORBITAL}
          initialViewState={camara}
          controller={CONTROL_ORBITAL}
          useDevicePixels={DENSIDAD_DE_PIXELES}
          layers={capas}
          onClick={({ x, y }) => {
            const coordenada = deck.current?.pickObject({ x, y, unproject3D: true, layerIds: ['relieve'] })?.coordinate;
            setPunto(coordenada ? aLonLat(coordenada[0], coordenada[1]) : null);
          }}
          getCursor={({ isDragging }) => (isDragging ? 'grabbing' : 'crosshair')}
        />
        <BotonCentrar alPulsar={() => setCentrados(centrados + 1)} />
        <ControlDeExageracion
          valor={exageracion[zona]}
          alCambiar={(valor) => setExageracion({ ...exageracion, [zona]: valor })}
          brillo={brillo}
          alCambiarBrillo={setBrillo}
        />
        <LeyendaDeCalor
          titulo="Sacudida esperada (intensidad Mercalli)"
          descripciones={{ Bajo: 'hasta IV: se siente', Medio: 'V a VI: daños leves', Alto: 'VII o más: daños' }}
        />
      </div>

      <PanelDesplegable titulo="Simulación y controles">
        {encabezado}
        <div className="panel-presentacion">
          <h2>Riesgo por zona · sismo simulado</h2>
          <p className="apoyo">
            ¿Qué pasaría si ocurriera un sismo en el Nido de Bucaramanga? No predice cuándo ocurrirá: calcula la
            sacudida que produciría en cada punto.
          </p>
        </div>

        <Bloque icono="capas" titulo="Vista del mapa">
          <SelectorDeZona
            zona={zona}
            alCambiar={(nueva) => {
              setZona(nueva);
              setPunto(null);
            }}
          />
          {zona === 'los_santos' && (
            <label className="casilla">
              <input type="checkbox" checked={verCeldas} onChange={(e) => setVerCeldas(e.target.checked)} />
              <span>Mostrar las celdas del modelo (bordes y números)</span>
            </label>
          )}
          <Nota>{AYUDA_DE_CAMARA} El punto negro es el epicentro.</Nota>
        </Bloque>

        <Bloque icono="sismo" titulo="Sismo hipotético">
          <ControlesDeEscenario
            limites={grilla.datos.limites}
            magnitud={magnitud}
            profundidad={profundidad}
            alCambiarMagnitud={setMagnitud}
            alCambiarProfundidad={setProfundidad}
          />
        </Bloque>

        <ResumenDeEscenario info={mapa.info} />

        {punto && intensidadDelPunto !== null ? (
          <PuntoElegido
            punto={punto}
            relieve={relieve}
            municipios={municipios.datos.features}
            celda={celdaDelPunto}
            poblacion={poblacion.datos}
            nivelPorMunicipio={mapa.info.nivel_por_municipio}
            viviendasAfectadas={mapa.info.viviendas.afectadas_por_municipio}
          >
            <tr>
              <td>Intensidad simulada</td>
              <td className="num">
                {enRomanos(intensidadDelPunto)} ({numero(intensidadDelPunto, 1)})
              </td>
            </tr>
            <tr>
              <td>Nivel de sacudida</td>
              <td className="num">
                <EtiquetaDeNivel nivel={nivelDeIntensidad(intensidadDelPunto)} />
              </td>
            </tr>
          </PuntoElegido>
        ) : (
          <p className="aviso">
            Haz clic en cualquier punto del relieve para ver sus coordenadas, su intensidad y las personas que viven en
            su municipio.
          </p>
        )}

        <Nota>
          El mapa de calor se calcula en un punto cada {zona === 'santander' ? '1,1 km' : '220 m'}. Las personas
          expuestas y las viviendas afectadas cuentan todo Santander, aunque solo se vea Los Santos. Método: Zhao et al. (2006) y
          Worden et al. (2012), calibrado con 598 intensidades observadas por el USGS.
        </Nota>
      </PanelDesplegable>
    </div>
  );
}
