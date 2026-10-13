// Vista principal: nivel de riesgo que el clasificador predice para cada celda. Cada zona tiene su
// modelo: el de Los Santos (30 celdas) y el de todo Santander. Al cambiar de zona cambia el modelo.
// El resultado se muestra
// pintado como mapa de calor sobre el relieve 3D. La línea de tiempo recorre el periodo de
// prueba y compara, trimestre a trimestre, lo que el modelo predijo con lo que ocurrió.

import DeckGL, { type DeckGLRef } from '@deck.gl/react';
import { useMemo, useRef, useState, type ReactNode } from 'react';
import { api, type Nivel, type PropiedadesDeCelda, type TrimestreDePrueba, type Zona } from '../api';
import { Bloque, COLOR_NIVEL, css, DENSIDAD_DE_PIXELES, Estado, EtiquetaDeNivel, LeyendaDeCalor, NIVELES, Nota, numero, PanelDesplegable, porcentaje, useDatos } from '../comun';
import { construirTextura, proyeccionDe, type CampoDeCalor, type Marco } from '../relieve';
import { AYUDA_DE_CAMARA, BotonCentrar, camaraOrbital, ControlDeExageracion, capaDelPunto, capaDeRelieve, CONTROL_ORBITAL, EXAGERACION_INICIAL, PuntoElegido, SelectorDeZona, useBrillo, useRelieve, VISTA_ORBITAL, zonaInicial, type Punto } from './Relieve3D';

type CeldaConLimites = PropiedadesDeCelda & Marco;

// Posición en el degradado: 0 si es seguro que será Bajo, 0,5 si Medio y 1 si Alto
const calorDeLaCelda = (c: PropiedadesDeCelda) => (c.con_sismicidad_registrada ? c.prob_medio * 0.5 + c.prob_alto : 0);

type Modo = 'predicho' | 'real';
const MODOS: { id: Modo; nombre: string }[] = [
  { id: 'predicho', nombre: 'Lo que predijo' },
  { id: 'real', nombre: 'Lo que ocurrió' },
];

const listaDeCeldas = (ids: number[]) => (ids.length === 1 ? `celda ${ids[0]}` : `celdas ${ids.join(', ')}`);

const MODELO_DE_ZONA: Record<Zona, { nombre: string; lugar: string }> = {
  los_santos: { nombre: 'Modelo de Los Santos', lugar: 'cada zona de Los Santos' },
  santander: { nombre: 'Modelo de todo Santander', lugar: 'cada zona de Santander' },
};

export default function VistaRiesgo({ encabezado }: { encabezado?: ReactNode }) {
  const [zona, setZona] = useState<Zona>(() => zonaInicial('los_santos'));
  // Las celdas y el historial son los del modelo de la zona que se está viendo
  const celdas = useDatos(() => api.celdasDeRiesgo(zona), zona);
  const municipios = useDatos(api.municipios);
  const poblacion = useDatos(api.poblacion);
  const { relieve, malla, error: errorDelRelieve } = useRelieve(zona);
  const [idSeleccionada, setIdSeleccionada] = useState<number | null>(null);

  // Línea de tiempo: sin trimestre elegido se muestra la predicción vigente (el próximo trimestre)
  const historial = useDatos(() => api.historialDeRiesgo(zona), zona);
  const [indice, setIndice] = useState<number | null>(null);
  const [modo, setModo] = useState<Modo>('predicho');
  const pasado = (indice !== null && historial.datos?.trimestres[indice]) || null;
  const [punto, setPunto] = useState<Punto | null>(null);
  const [exageracion, setExageracion] = useState(EXAGERACION_INICIAL);
  const deck = useRef<DeckGLRef>(null);

  const celdasConLimites = useMemo<CeldaConLimites[]>(() => {
    if (!celdas.datos) return [];
    return celdas.datos.features.map((f) => {
      const lons = f.geometry.coordinates[0].map((p) => p[0]);
      const lats = f.geometry.coordinates[0].map((p) => p[1]);
      return { ...f.properties, oeste: Math.min(...lons), este: Math.max(...lons), sur: Math.min(...lats), norte: Math.max(...lats) };
    });
  }, [celdas.datos]);

  // Un valor por celda, ordenado de norte a sur y de oeste a este: al pintarlo, el
  // navegador interpola entre los centros de las celdas y sale un degradado continuo
  const calor = useMemo<CampoDeCalor | null>(() => {
    if (celdasConLimites.length === 0) return null;
    const ordenadas = [...celdasConLimites].sort((a, b) => b.lat_center - a.lat_center || a.lon_center - b.lon_center);
    const columnas = new Set(ordenadas.map((c) => c.lon_center)).size;
    return {
      oeste: Math.min(...ordenadas.map((c) => c.oeste)),
      este: Math.max(...ordenadas.map((c) => c.este)),
      sur: Math.min(...ordenadas.map((c) => c.sur)),
      norte: Math.max(...ordenadas.map((c) => c.norte)),
      filas: ordenadas.length / columnas,
      columnas,
      // En un trimestre pasado se pinta el nivel de cada celda: 0 Bajo, 0,5 Medio y 1 Alto
      valores: ordenadas.map((c) => (pasado ? pasado[modo][c.cell_id] / 2 : calorDeLaCelda(c))),
    };
  }, [celdasConLimites, pasado, modo]);

  // Celdas en las que lo predicho y lo ocurrido no coinciden; se marcan en los dos modos
  const fallos = useMemo(
    () => (pasado ? celdasConLimites.filter((c) => c.en_el_departamento && pasado.predicho[c.cell_id] !== pasado.real[c.cell_id]) : null),
    [pasado, celdasConLimites],
  );

  const seleccion = celdasConLimites.find((c) => c.cell_id === idSeleccionada) ?? null;

  // La cuadrícula solo se ofrece en Los Santos: a escala de todo Santander las celdas no se distinguen
  const [verCeldas, setVerCeldas] = useState(false);
  const cuadricula = useMemo(
    () => (verCeldas && zona === 'los_santos' ? celdasConLimites.map((c) => ({ ...c, etiqueta: String(c.cell_id) })) : null),
    [verCeldas, zona, celdasConLimites],
  );

  const textura = useMemo(
    () =>
      relieve && municipios.datos && calor
        ? construirTextura(relieve, { calor, municipios: municipios.datos.features, marco: seleccion, cuadricula, fallos })
        : null,
    [relieve, municipios.datos, calor, seleccion, cuadricula, fallos],
  );

  // La cámara inicial solo cambia con el relieve: si cambiara en cada dibujo, la vista se reiniciaría
  const [centrados, setCentrados] = useState(0);
  const [brillo, setBrillo] = useBrillo();
  const camara = useMemo(() => (relieve ? camaraOrbital(relieve, centrados) : null), [relieve, centrados]);

  if (!celdas.datos || !municipios.datos || !relieve || !malla || !textura || !camara) {
    return <Estado error={celdas.error ?? municipios.error ?? errorDelRelieve} />;
  }

  const niveles = historial.datos?.niveles ?? NIVELES;
  const proximo = celdasConLimites[0].trimestre_predicho;
  // Nivel que se está pintando en cada celda
  const nivelDe = (c: PropiedadesDeCelda): Nivel => (pasado ? niveles[pasado[modo][c.cell_id]] : c.riesgo_predicho);
  // El acierto se cuenta sobre las celdas que pasan por el modelo, igual que la exactitud reportada
  const conModelo = historial.datos?.celdas_con_modelo ?? [];
  const tienenModelo = new Set(conModelo);
  const falladas = (fallos ?? []).map((c) => c.cell_id);
  const falladasConModelo = falladas.filter((id) => tienenModelo.has(id));
  const falladasSinModelo = falladas.filter((id) => !tienenModelo.has(id));
  // En Santander el rectángulo de celdas es mayor que el departamento: solo cuentan las de dentro
  const delDepartamento = celdasConLimites.filter((c) => c.en_el_departamento);
  const elegibles = zona === 'santander' ? delDepartamento.filter((c) => c.con_sismicidad_registrada) : delDepartamento;
  const aciertos = conModelo.length - falladasConModelo.length;

  // Un clic sobre la montaña se convierte en coordenadas reales y de ahí en la celda que las contiene
  const alHacerClic = (x: number, y: number) => {
    const tocado = deck.current?.pickObject({ x, y, unproject3D: true, layerIds: ['relieve'] })?.coordinate;
    if (!tocado) return;
    const [lon, lat] = proyeccionDe(relieve).aLonLat(tocado[0], tocado[1]);
    const celda = celdasConLimites.find((c) => lon >= c.oeste && lon < c.este && lat >= c.sur && lat < c.norte);
    setPunto([lon, lat]);
    setIdSeleccionada(celda?.cell_id ?? null);
  };

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
          layers={[capaDeRelieve(malla, textura, exageracion[zona], brillo), capaDelPunto(relieve, punto, exageracion[zona])]}
          onClick={({ x, y }) => alHacerClic(x, y)}
          getCursor={({ isDragging }) => (isDragging ? 'grabbing' : 'pointer')}
        />
        <BotonCentrar alPulsar={() => setCentrados(centrados + 1)} />
        <ControlDeExageracion
          valor={exageracion[zona]}
          alCambiar={(valor) => setExageracion({ ...exageracion, [zona]: valor })}
          brillo={brillo}
          alCambiarBrillo={setBrillo}
        />
        <LeyendaDeCalor
          titulo={pasado && modo === 'real' ? `Lo que ocurrió en ${pasado.trimestre}` : `Riesgo predicho para ${pasado?.trimestre ?? proximo}`}
          descripciones={{ Bajo: 'ningún sismo M≥2,5', Medio: '1 a 3 sismos', Alto: 'más de 3 sismos' }}
        />
      </div>

      <PanelDesplegable titulo="Riesgo y controles">
        {encabezado}
        <div className="panel-presentacion">
          <h2>Riesgo por zona · datos reales</h2>
          <p className="apoyo">
            Un modelo Random Forest, entrenado con el catálogo del SGC, predice el nivel de actividad sísmica de{' '}
            {MODELO_DE_ZONA[zona].lugar} durante el próximo trimestre.
          </p>
        </div>

        <Bloque icono="capas" titulo="Vista del mapa">
          <SelectorDeZona
            zona={zona}
            alCambiar={(nueva) => {
              // Cada zona tiene su modelo, con sus propias celdas: la selección anterior ya no vale
              setZona(nueva);
              setPunto(null);
              setIdSeleccionada(null);
            }}
          />
          <p className="modelo-activo">
            <strong>{MODELO_DE_ZONA[zona].nombre}</strong>
            <span>
              {numero(conModelo.length || elegibles.length)} celdas de 5,5 km con modelo
              {zona === 'santander' && ' · para Los Santos es más preciso su propio modelo'}
            </span>
          </p>
          {zona === 'los_santos' && (
            <label className="casilla">
              <input type="checkbox" checked={verCeldas} onChange={(e) => setVerCeldas(e.target.checked)} />
              <span>Mostrar las celdas del modelo (bordes y números)</span>
            </label>
          )}
          <Nota>{AYUDA_DE_CAMARA}</Nota>
        </Bloque>

        {historial.datos && (
          <Bloque icono="reloj" titulo="Línea de tiempo" fuente={pasado ? 'Periodo de prueba' : undefined}>
            <label className="control">
              <span>
                Trimestre <strong>{pasado ? pasado.trimestre : `${proximo} · predicción vigente`}</strong>
              </span>
              <input
                type="range"
                min={0}
                max={historial.datos.trimestres.length}
                step={1}
                value={indice ?? historial.datos.trimestres.length}
                onChange={(e) => {
                  const elegido = Number(e.target.value);
                  // La última posición es el próximo trimestre, que todavía no tiene con qué compararse
                  setIndice(elegido < historial.datos!.trimestres.length ? elegido : null);
                }}
              />
            </label>

            {pasado ? (
              <>
                <div className="selector" role="group" aria-label="Qué se muestra del trimestre">
                  {MODOS.map((m) => (
                    <button key={m.id} className={m.id === modo ? 'activa' : undefined} aria-pressed={m.id === modo} onClick={() => setModo(m.id)}>
                      {m.nombre}
                    </button>
                  ))}
                </div>
                <table className="tabla">
                  <tbody>
                    <tr className="destacada">
                      <td>Celdas acertadas en {pasado.trimestre}</td>
                      <td className="num">
                        {aciertos} de {conModelo.length} ({porcentaje(aciertos / conModelo.length)})
                      </td>
                    </tr>
                    <tr>
                      <td>Celdas falladas</td>
                      <td className="num">
                        {falladasConModelo.length === 0 ? 'ninguna' : falladasConModelo.length <= 8 ? falladasConModelo.join(', ') : `${falladasConModelo.length} celdas`}
                      </td>
                    </tr>
                  </tbody>
                </table>
                <Nota>
                  Las celdas falladas llevan un borde discontinuo y una equis. El modelo predijo este trimestre sin
                  haberlo visto: se entrenó solo con datos hasta 2021. El acierto se cuenta sobre las {conModelo.length}{' '}
                  celdas que pasan por el modelo.
                  {falladasSinModelo.length > 0 &&
                    (falladasSinModelo.length <= 4
                      ? ` Aparte, la ${listaDeCeldas(falladasSinModelo)}, que se reporta en Bajo sin modelo, tuvo sismos este trimestre.`
                      : ` Aparte, ${falladasSinModelo.length} celdas que se reportan en Bajo sin modelo tuvieron sismos este trimestre.`)}
                </Nota>
              </>
            ) : (
              <Nota>Mueve el control hacia la izquierda para comparar lo que el modelo predijo con lo que ocurrió, de 2022 a 2026.</Nota>
            )}
          </Bloque>
        )}
        {historial.error && <p className="aviso">No se pudo cargar la línea de tiempo: {historial.error}</p>}

        <Bloque
          icono="grafica"
          titulo={pasado && modo === 'real' ? `Lo que ocurrió · ${pasado.trimestre}` : `Riesgo predicho · ${pasado?.trimestre ?? proximo}`}
          fuente="SGC"
        >
          <div className="tarjetas">
            {NIVELES.map((nivel) => (
              <div className="tarjeta tarjeta-nivel" key={nivel} style={{ borderTopColor: css(COLOR_NIVEL[nivel]) }}>
                <div className="tarjeta-valor">{numero(delDepartamento.filter((c) => nivelDe(c) === nivel).length)}</div>
                <EtiquetaDeNivel nivel={nivel} />
                <span>celdas</span>
              </div>
            ))}
          </div>
          <label className="control">
            <span>Celda del modelo</span>
            <select
              value={idSeleccionada ?? ''}
              onChange={(e) => {
                // Al elegir de la lista no hay un punto concreto: solo la celda
                setPunto(null);
                setIdSeleccionada(e.target.value === '' ? null : Number(e.target.value));
              }}
            >
              <option value="">Elige una celda o haz clic en el relieve</option>
              {elegibles.map((c) => (
                <option key={c.cell_id} value={c.cell_id}>
                  Celda {c.cell_id} · {c.municipio} · {nivelDe(c)}
                </option>
              ))}
            </select>
          </label>
        </Bloque>

        {seleccion && pasado && (
          <CeldaEnElPasado celda={seleccion} trimestre={pasado} niveles={niveles} conModelo={conModelo.includes(seleccion.cell_id)} />
        )}
        {seleccion && !pasado && <DetalleDeCelda celda={seleccion} />}
        {punto && (
          <PuntoElegido punto={punto} relieve={relieve} municipios={municipios.datos.features} celda={seleccion} poblacion={poblacion.datos} />
        )}

        <Nota>
          El modelo predice por celdas de 5,5 km (las {numero(elegibles.length)} de la lista). El degradado suaviza el paso de una celda a otra
          para que se lea mejor; no añade precisión al modelo. Fuera de la zona del modelo el relieve se ve sin color.
        </Nota>
      </PanelDesplegable>
    </div>
  );
}

/** Lo predicho y lo ocurrido en una celda durante un trimestre del periodo de prueba. */
function CeldaEnElPasado({ celda, trimestre, niveles, conModelo }: { celda: PropiedadesDeCelda; trimestre: TrimestreDePrueba; niveles: Nivel[]; conModelo: boolean }) {
  const predicho = niveles[trimestre.predicho[celda.cell_id]];
  const real = niveles[trimestre.real[celda.cell_id]];
  return (
    <Bloque icono="celda" titulo={<>Celda {celda.cell_id} · {celda.municipio} · {trimestre.trimestre}</>}>
      <table className="tabla">
        <tbody>
          <tr>
            <td>El modelo predijo</td>
            <td className="num">
              <EtiquetaDeNivel nivel={predicho} />
            </td>
          </tr>
          <tr>
            <td>Ocurrió</td>
            <td className="num">
              <EtiquetaDeNivel nivel={real} />
            </td>
          </tr>
          <Fila nombre="Sismos M≥2,5 en el trimestre" valor={numero(trimestre.sismos[celda.cell_id])} />
          <tr className="destacada">
            <td>Resultado</td>
            <td className="num">{predicho === real ? 'Acierto' : 'Fallo'}</td>
          </tr>
        </tbody>
      </table>
      {!conModelo && (
        <p className="aviso">
          Esta celda no tuvo sismos de magnitud 2,5 o mayor en el periodo de entrenamiento. Se reporta como Bajo sin
          pasar por el modelo y no cuenta en el acierto.
        </p>
      )}
    </Bloque>
  );
}

function DetalleDeCelda({ celda }: { celda: PropiedadesDeCelda }) {
  const probabilidades: [Nivel, number][] = [
    ['Bajo', celda.prob_bajo],
    ['Medio', celda.prob_medio],
    ['Alto', celda.prob_alto],
  ];

  return (
    <Bloque icono="celda" titulo={<>Celda {celda.cell_id} · {celda.municipio}</>}>
      <div className="resultado">
        <span className="resultado-titulo">Nivel de riesgo para {celda.trimestre_predicho}</span>
        <span className="resultado-nivel" style={{ borderColor: css(COLOR_NIVEL[celda.riesgo_predicho]) }}>
          <EtiquetaDeNivel nivel={celda.riesgo_predicho} />
        </span>
      </div>

      {celda.con_sismicidad_registrada ? (
        <>
          <h4>Probabilidad de cada nivel</h4>
          {probabilidades.map(([nivel, p]) => (
            <div className="barra-fila" key={nivel} title={`${nivel}: ${porcentaje(p, 1)}`}>
              <span className="barra-nombre">{nivel}</span>
              <span className="barra-pista">
                <span className="barra-relleno" style={{ width: `${p * 100}%`, background: css(COLOR_NIVEL[nivel]) }} />
              </span>
              <span className="barra-valor">{porcentaje(p)}</span>
            </div>
          ))}
        </>
      ) : (
        <p className="aviso">
          Esta celda no ha tenido sismos de magnitud 2,5 o mayor desde 2010. Se reporta como Bajo sin pasar por el
          modelo.
        </p>
      )}

      <h4>Factores que más influyen</h4>
      <table className="tabla">
        <tbody>
          <Fila nombre="Sismos M≥2,5 en el último trimestre" valor={numero(celda.sismos_trimestre)} />
          <Fila nombre="Sismos en el último año" valor={numero(celda.sismos_ultimo_anio)} />
          <Fila nombre="Sismos en las celdas vecinas (último año)" valor={numero(celda.sismos_vecinos_ultimo_anio)} />
          <Fila nombre="Promedio trimestral desde 2010" valor={numero(celda.sismos_promedio_historico, 1)} />
          <Fila nombre="Distancia al centro del nido" valor={`${numero(celda.dist_nido_km, 1)} km`} />
          <Fila
            nombre="Mayor magnitud del último año"
            valor={celda.sismos_ultimo_anio > 0 ? numero(celda.mag_max_ultimo_anio, 1) : '—'}
          />
          <Fila
            nombre="Profundidad media"
            valor={celda.sismos_ultimo_anio > 0 ? `${numero(celda.prof_media_ultimo_anio)} km` : '—'}
          />
        </tbody>
      </table>
    </Bloque>
  );
}

function Fila({ nombre, valor }: { nombre: string; valor: string }) {
  return (
    <tr>
      <td>{nombre}</td>
      <td className="num">{valor}</td>
    </tr>
  );
}
