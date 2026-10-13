// Piezas del simulador compartidas por la vista de mapa y la vista 3D.

import { useEffect, useState } from 'react';
import { api, type CampoDeSacudida, type Epicentro, type GrillaDelSimulador, type InfoDeEscenario, type MapaDeCalor, type Nivel, type Zona } from '../api';
import { Bloque, COLOR_NIVEL, css, EtiquetaDeNivel, NIVELES, Nota, numero, pesos } from '../comun';
import type { CampoDeCalor } from '../relieve';

const ROMANOS = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'];
export const enRomanos = (mmi: number) => ROMANOS[Math.min(10, Math.max(1, Math.round(mmi))) - 1];

// Mientras se arrastra un control solo se pide el escenario donde el control se detiene un instante
const ESPERA_AL_ARRASTRAR_MS = 70;

export const MAGNITUD_INICIAL = 6.0;
export const PROFUNDIDAD_INICIAL_KM = 150;

// La intensidad se convierte en una posición del degradado: verde hasta 3,5, amarillo en
// 5,5 y rojo desde 7,5. Así los cambios de nivel (4,5 y 6,5) quedan a mitad de cada transición.
const MMI_VERDE = 3.5;
const MMI_ROJO = 7.5;
export const posicionEnElDegradado = (mmi: number) => Math.min(1, Math.max(0, (mmi - MMI_VERDE) / (MMI_ROJO - MMI_VERDE)));

export const nivelDeIntensidad = (mmi: number): Nivel => (mmi >= 6.5 ? 'Alto' : mmi >= 4.5 ? 'Medio' : 'Bajo');

/**
 * Pide al backend el mapa de calor de la zona cada vez que cambian los
 * controles, con una pequeña espera para no saturarlo al arrastrar. Sin
 * epicentro, el sismo ocurre en el centro del nido.
 */
export function useEscenario(magnitud: number, profundidad: number, zona: Zona, activo = true, epicentro?: Epicentro) {
  const [recibido, setRecibido] = useState<{ mapa: MapaDeCalor; zona: Zona } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [lat, lon] = [epicentro?.lat, epicentro?.lon];
  useEffect(() => {
    if (!activo) return;
    const donde = lat !== undefined && lon !== undefined ? { lat, lon } : undefined;
    // Un escenario ya visto se muestra al instante, sin esperar ni pedirlo de nuevo
    const guardado = api.mapaDeCalorGuardado(magnitud, profundidad, zona, donde);
    if (guardado) {
      setRecibido({ mapa: guardado, zona });
      return;
    }
    const control = new AbortController();
    const espera = setTimeout(() => {
      api
        .mapaDeCalor(magnitud, profundidad, zona, control.signal, donde)
        .then((mapa) => setRecibido({ mapa, zona }))
        .catch((e: Error) => e.name !== 'AbortError' && setError(e.message));
    }, ESPERA_AL_ARRASTRAR_MS);
    return () => {
      clearTimeout(espera);
      control.abort();
    };
  }, [magnitud, profundidad, zona, activo, lat, lon]);

  // Al cambiar de zona, el mapa anterior no encaja con el relieve nuevo: se espera al que llega
  return { mapa: recibido?.zona === zona ? recibido.mapa : null, error };
}

/** El mapa de calor de la simulación, listo para pintarlo sobre el relieve. */
export function calorDeLaSacudida(campo: CampoDeSacudida): CampoDeCalor {
  return { ...campo, valores: campo.mmi.map(posicionEnElDegradado) };
}

interface PropsDeControles {
  limites: GrillaDelSimulador['limites'];
  magnitud: number;
  profundidad: number;
  alCambiarMagnitud: (valor: number) => void;
  alCambiarProfundidad: (valor: number) => void;
}

export function ControlesDeEscenario({ limites, magnitud, profundidad, alCambiarMagnitud, alCambiarProfundidad }: PropsDeControles) {
  return (
    <>
      <label className="control">
        <span>
          Magnitud <strong>{numero(magnitud, 1)}</strong>
        </span>
        <input
          type="range"
          min={limites.magnitud[0]}
          max={limites.magnitud[1]}
          step={0.1}
          value={magnitud}
          onChange={(e) => alCambiarMagnitud(Number(e.target.value))}
        />
      </label>
      <label className="control">
        <span>
          Profundidad <strong>{profundidad} km</strong>
        </span>
        <input
          type="range"
          min={limites.profundidad_km[0]}
          max={limites.profundidad_km[1]}
          step={5}
          value={profundidad}
          onChange={(e) => alCambiarProfundidad(Number(e.target.value))}
        />
      </label>
    </>
  );
}

/** Cifra de personas abreviada para que quepa en una tarjeta: 2,41 M, 839 mil, 17,3 mil, 850. */
function personas(cantidad: number) {
  if (cantidad >= 1e6) return `${numero(cantidad / 1e6, 2)} M`;
  if (cantidad >= 1e3) return `${numero(cantidad / 1e3, cantidad >= 1e5 ? 0 : 1)} mil`;
  return numero(cantidad);
}

/** Resumen del escenario en dos bloques: a quién alcanza la sacudida y cómo es. */
export function ResumenDeEscenario({ info }: { info: InfoDeEscenario }) {
  return (
    <>
      <Bloque icono="personas" titulo="Personas expuestas" fuente={`DANE · ${info.anio_de_la_poblacion}`}>
        <div className="reparto" role="img" aria-label="Reparto de la población de Santander entre los tres niveles de sacudida">
          {NIVELES.map((nivel) => (
            <span key={nivel} style={{ flexGrow: info.personas_por_nivel[nivel], background: css(COLOR_NIVEL[nivel]) }} />
          ))}
        </div>
        <div className="tarjetas">
          {NIVELES.map((nivel) => (
            <div
              className="tarjeta tarjeta-nivel"
              key={nivel}
              style={{ borderTopColor: css(COLOR_NIVEL[nivel]) }}
              title={`${numero(info.personas_por_nivel[nivel])} personas en ${info.municipios_por_nivel[nivel]} municipios`}
            >
              <div className="tarjeta-valor">{personas(info.personas_por_nivel[nivel])}</div>
              <EtiquetaDeNivel nivel={nivel} />
              <span>
                {info.municipios_por_nivel[nivel]} {info.municipios_por_nivel[nivel] === 1 ? 'municipio' : 'municipios'}
              </span>
            </div>
          ))}
        </div>
        <Nota>
          Habitantes de Santander según la sacudida de su municipio. Es una aproximación: cada uno de los 87 municipios
          cuenta completo, con la sacudida calculada en un punto de su interior; no distingue en qué parte vive cada
          persona.
        </Nota>
      </Bloque>

      <ViviendasDelEscenario viviendas={info.viviendas} />

      <Bloque icono="grafica" titulo="Sacudida calculada">
        <table className="tabla">
          <tbody>
            <tr>
              <td>Intensidad máxima</td>
              <td className="num">
                {enRomanos(info.mmi_maxima)} ({numero(info.mmi_maxima, 1)})
              </td>
            </tr>
            <tr>
              <td>Tipo de sismo</td>
              <td className="num">{info.tipo_fuente === 'intraplaca' ? 'Profundo (intraplaca)' : 'Superficial (cortical)'}</td>
            </tr>
            {info.periodo_retorno_anios !== undefined && (
              <tr>
                <td>Frecuencia en el nido</td>
                <td className="num">{frecuencia(info.periodo_retorno_anios)}</td>
              </tr>
            )}
            {info.error_tipico_mmi !== null && (
              <tr>
                <td>Error típico</td>
                <td className="num">± {numero(info.error_tipico_mmi, 1)} grados</td>
              </tr>
            )}
          </tbody>
        </table>

        {info.advertencias.length > 0 && (
          <div className="advertencias" role="note">
            <strong>Escenario fuera de lo validado</strong>
            <ul>
              {info.advertencias.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </div>
        )}
      </Bloque>
    </>
  );
}

/** Posición (0 a 1) de una cantidad de viviendas en una escala logarítmica de 1 al total. */
const enLaEscala = (valor: number, total: number) => Math.min(1, Math.log10(Math.max(valor, 1)) / Math.log10(total));

/** Viviendas afectadas y costo de atención: siempre con su rango, porque el error del modelo es grande. */
function ViviendasDelEscenario({ viviendas: v }: { viviendas: InfoDeEscenario['viviendas'] }) {
  const [desde, centro, hasta] = [v.afectadas_bajo, v.afectadas, v.afectadas_alto].map((x) => enLaEscala(x, v.total));
  return (
    <Bloque icono="casa" titulo="Viviendas afectadas" fuente="UNGRD · DANE">
      <div className="estimacion">
        <strong>≈ {numero(v.afectadas)}</strong>
        <span>
          viviendas averiadas o destruidas
          <br />
          entre {numero(v.afectadas_bajo)} y {numero(v.afectadas_alto)}, de {numero(v.total)}
        </span>
      </div>
      <div className="rango" role="img" aria-label={`Entre ${numero(v.afectadas_bajo)} y ${numero(v.afectadas_alto)} viviendas, en escala logarítmica`}>
        <span className="rango-tramo" style={{ left: `${desde * 100}%`, width: `${Math.max(hasta - desde, 0.01) * 100}%` }} />
        <span className="rango-centro" style={{ left: `${centro * 100}%` }} />
      </div>
      <div className="rango-escala">
        <span>1</span>
        <span>100</span>
        <span>10 mil</span>
        <span>{numero(v.total / 1000)} mil</span>
      </div>
      <table className="tabla">
        <tbody>
          <tr>
            <td>De ellas, destruidas</td>
            <td className="num">≈ {numero(v.destruidas)}</td>
          </tr>
          <tr className="destacada">
            <td>Costo de atención</td>
            <td className="num">≈ {pesos(v.costo)}</td>
          </tr>
          <tr>
            <td>Rango del costo</td>
            <td className="num">
              {pesos(v.costo_bajo)} a {pesos(v.costo_alto)}
            </td>
          </tr>
        </tbody>
      </table>
      {v.fuera_de_lo_observado && (
        <div className="advertencias" role="note">
          <strong>Sacudida mayor que la de los datos</strong>
          <ul>
            <li>
              El modelo aprendió de sismos con intensidad hasta {numero(v.intensidad_validada[1], 1)}; aquí llega a{' '}
              {numero(v.intensidad_maxima, 1)}. La cifra es una extrapolación.
            </li>
          </ul>
        </div>
      )}
      <Nota>
        Estimación de un modelo entrenado con los daños de sismos colombianos reales (2019 a 2025). Puede equivocarse
        por un factor de diez: léase como orden de magnitud. El costo es lo que el Estado ha gastado en atención por
        vivienda afectada ({pesos(v.costo_por_vivienda_cop.bajo)} a {pesos(v.costo_por_vivienda_cop.alto)}); no es una
        indemnización ni el costo de reconstruir.
      </Nota>
    </Bloque>
  );
}

function frecuencia(anios: number) {
  if (anios < 1) return `unos ${numero(1 / anios)} por año`;
  return `uno cada ${numero(anios, anios < 10 ? 1 : 0)} años`;
}
