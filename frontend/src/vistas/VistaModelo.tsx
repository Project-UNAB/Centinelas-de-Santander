// Cómo se entrenó cada uno de los tres modelos y qué tan bien acierta. Cada pestaña es un
// tablero que cabe en una pantalla: cifras arriba y, debajo, la comparación y el detalle.

import { useState, type ReactNode } from 'react';
import { api, type Zona } from '../api';
import { Estado, numero, pesos, porcentaje, useDatos } from '../comun';

const NOMBRE_VARIABLE: Record<string, string> = {
  sismos_trimestre: 'Sismos del trimestre',
  sismos_ultimo_anio: 'Sismos del último año',
  sismos_promedio_historico: 'Promedio histórico',
  tendencia_sismos: 'Tendencia',
  sismos_vecinos_ultimo_anio: 'Sismos en celdas vecinas',
  mag_media_ultimo_anio: 'Magnitud media',
  mag_max_ultimo_anio: 'Magnitud máxima',
  log_energia_ultimo_anio: 'Energía liberada',
  prop_moderados_ultimo_anio: 'Proporción de sismos M≥3,5',
  trimestres_desde_sismo_fuerte: 'Tiempo desde un sismo fuerte',
  prof_media_ultimo_anio: 'Profundidad media',
  prof_std_ultimo_anio: 'Dispersión de la profundidad',
  dist_nido_km: 'Distancia al nido',
  lat_center: 'Latitud',
  lon_center: 'Longitud',
};

// Nombres cortos de las reglas sin aprendizaje, para que la tabla quepa sin partir líneas
const NOMBRE_DE_REGLA: Record<string, string> = {
  'Base: clase más frecuente': 'Regla: siempre la clase más frecuente',
  'Base: igual al trimestre anterior': 'Regla: igual al trimestre anterior',
  'Base: promedio del último año': 'Regla: promedio del último año',
};

// Variables que se muestran en la gráfica de importancia; el resto se resume en una línea
const VARIABLES_VISIBLES = 9;

type Modelo = Zona | 'viviendas';
const MODELOS: { id: Modelo; nombre: string }[] = [
  { id: 'los_santos', nombre: '1 · Sismos de Los Santos' },
  { id: 'santander', nombre: '2 · Sismos de Santander' },
  { id: 'viviendas', nombre: '3 · Viviendas y costos' },
];

export default function VistaModelo() {
  const [modelo, setModelo] = useState<Modelo>('los_santos');
  return (
    <div className="modelos">
      <header className="modelos-cabecera">
        <div>
          <h2>Los modelos</h2>
          <span>Tres modelos de aprendizaje supervisado, entrenados y validados por separado</span>
        </div>
        <div className="selector" role="group" aria-label="Modelo">
          {MODELOS.map((m) => (
            <button key={m.id} className={m.id === modelo ? 'activa' : undefined} aria-pressed={m.id === modelo} onClick={() => setModelo(m.id)}>
              {m.nombre}
            </button>
          ))}
        </div>
      </header>
      {modelo === 'viviendas' ? <ModeloDeViviendas /> : <ModeloDeSismos zona={modelo} />}
    </div>
  );
}

function Cifra({ valor, rotulo, destacada }: { valor: string; rotulo: string; destacada?: boolean }) {
  return (
    <div className={`cifra ${destacada ? 'cifra-destacada' : ''}`}>
      <strong>{valor}</strong>
      <span>{rotulo}</span>
    </div>
  );
}

function Cuadro({ titulo, children, nota }: { titulo: string; children: ReactNode; nota?: ReactNode }) {
  return (
    <section className="cuadro">
      <h3>{titulo}</h3>
      {children}
      {nota && <p className="cuadro-nota">{nota}</p>}
    </section>
  );
}

function ModeloDeSismos({ zona }: { zona: Zona }) {
  const { datos, error } = useDatos(() => api.infoDelClasificador(zona), zona);
  if (!datos) return <Estado error={error} />;

  const importancias = Object.entries(datos.importancia_variables);
  const maxima = Math.max(...importancias.map(([, v]) => v));
  const elegido = datos.metricas[datos.nombre];
  const persistencia = datos.metricas['Base: igual al trimestre anterior'];
  const { etiquetas, valores } = datos.matriz_confusion;

  return (
    <>
      <p className="modelos-resumen">
        <strong>{zona === 'los_santos' ? 'Riesgo sísmico por zona en Los Santos.' : 'Riesgo sísmico por zona en todo Santander.'}</strong>{' '}
        {datos.nombre} con {datos.variables.length} variables del catálogo del SGC (magnitud {numero(datos.magnitud_minima, 1)} o
        mayor, desde 2010), para {numero(datos.celdas_con_modelo)} celdas de 5,5 km. Predice los sismos del trimestre
        siguiente: <strong>Bajo</strong> (ninguno), <strong>Medio</strong> (1 a {datos.umbrales_sismos[1]}) o <strong>Alto</strong>{' '}
        (más de {datos.umbrales_sismos[1]}).
      </p>

      <div className="cifras">
        <Cifra valor={porcentaje(elegido.accuracy, 1)} rotulo="exactitud en datos que no vio" destacada />
        <Cifra valor={porcentaje(elegido.f1_macro, 1)} rotulo="F1 macro (pesa igual los tres niveles)" destacada />
        <Cifra valor={porcentaje(elegido.recall_alto, 1)} rotulo="de los casos de nivel Alto, detectados" />
        <Cifra valor={numero(datos.muestras_entrenamiento)} rotulo={`casos de entrenamiento · ${datos.periodo_entrenamiento.join(' a ')}`} />
        <Cifra valor={numero(datos.muestras_prueba)} rotulo={`casos de prueba · ${datos.periodo_prueba.join(' a ')}`} />
      </div>

      <div className="cuadros cuadros-de-sismos">
        <Cuadro
          titulo="Comparación con reglas sin aprendizaje"
          nota={
            zona === 'santander'
              ? 'Aquí la exactitud sola engaña: más del 90 % de los casos son de nivel Bajo. Lo que cuenta es el F1 macro.'
              : 'El modelo no llega al 100 % porque los sismos tienen azar: ni conociendo la tasa real de cada celda se supera el techo.'
          }
        >
          <table className="tabla tabla-compacta">
            <thead>
              <tr>
                <th>Modelo</th>
                <th className="num">Exactitud</th>
                <th className="num">F1 macro</th>
                <th className="num">Recall Alto</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(datos.metricas).map(([nombre, m]) => (
                <tr key={nombre} className={nombre === datos.nombre ? 'destacada' : undefined}>
                  <td>{nombre === datos.nombre ? `${nombre} (elegido)` : (NOMBRE_DE_REGLA[nombre] ?? nombre)}</td>
                  <td className="num">{porcentaje(m.accuracy, 1)}</td>
                  <td className="num">{porcentaje(m.f1_macro, 1)}</td>
                  <td className="num">{porcentaje(m.recall_alto, 1)}</td>
                </tr>
              ))}
              <tr className="referencia">
                <td>Techo de referencia (oráculo)</td>
                <td className="num">{porcentaje(datos.techo_del_problema.accuracy, 1)}</td>
                <td className="num">{porcentaje(datos.techo_del_problema.f1_macro, 1)}</td>
                <td className="num">{porcentaje(datos.techo_del_problema.recall_alto, 1)}</td>
              </tr>
            </tbody>
          </table>
          <p className="veredicto">
            Supera a la regla «igual al trimestre anterior» por {numero((elegido.accuracy - persistencia.accuracy) * 100, 1)}{' '}
            puntos de exactitud y {numero((elegido.f1_macro - persistencia.f1_macro) * 100, 1)} de F1, y llega al{' '}
            {porcentaje(elegido.accuracy / datos.techo_del_problema.accuracy)} del techo.
          </p>
        </Cuadro>

        <Cuadro
          titulo="Qué variables pesan más"
          nota={`Y ${importancias.length - VARIABLES_VISIBLES} variables más, cada una con menos del ${porcentaje(importancias[VARIABLES_VISIBLES - 1][1])}.`}
        >
          {importancias.slice(0, VARIABLES_VISIBLES).map(([variable, valor]) => (
            <div className="barra-fila barra-de-modelo" key={variable} title={`${NOMBRE_VARIABLE[variable]}: ${porcentaje(valor, 1)}`}>
              <span className="barra-nombre">{NOMBRE_VARIABLE[variable] ?? variable}</span>
              <span className="barra-pista">
                <span className="barra-relleno barra-azul" style={{ width: `${(valor / maxima) * 100}%` }} />
              </span>
              <span className="barra-valor">{porcentaje(valor, 1)}</span>
            </div>
          ))}
        </Cuadro>

        <Cuadro titulo="Dónde acierta y dónde falla" nota="En la diagonal están los aciertos. Casi nunca confunde Bajo con Alto; el nivel Medio es el más difícil.">
          <table className="tabla tabla-compacta matriz">
            <thead>
              <tr>
                <th>Real ↓ · Predicho →</th>
                {etiquetas.map((e) => (
                  <th className="num" key={e}>
                    {e}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {valores.map((fila, i) => (
                <tr key={etiquetas[i]}>
                  <td>{etiquetas[i]}</td>
                  {fila.map((valor, j) => (
                    <td className={`num ${i === j ? 'acierto' : ''}`} key={etiquetas[j]}>
                      {numero(valor)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <h4>Alcance</h4>
          <p className="cuadro-texto">
            Mide la actividad sísmica esperada en cada zona (amenaza). No predice cuándo ocurrirá un sismo concreto.
            {zona === 'santander' && ' Para las celdas de Los Santos predice mejor su propio modelo.'}
          </p>
        </Cuadro>
      </div>
    </>
  );
}

function ModeloDeViviendas() {
  const { datos, error } = useDatos(api.infoDelModeloDeViviendas);
  if (!datos) return <Estado error={error} />;
  const elegido = datos.candidatos[datos.modelo_elegido];
  const referencia = datos.candidatos.constante;
  const costo = datos.costo_por_vivienda_cop;

  return (
    <>
      <p className="modelos-resumen">
        <strong>Viviendas afectadas por un sismo y costo de atención.</strong> Regresión que aprende, de sismos colombianos
        reales, qué proporción de las viviendas de un municipio resulta averiada o destruida según la intensidad con que
        le llega el sismo. Daños: UNGRD (2019 a 2025). Viviendas: DANE. Sismos: catálogo del USGS.
      </p>

      <div className="cifras">
        <Cifra valor={numero(datos.casos)} rotulo={`casos (un municipio en un sismo), de ${datos.sismos} sismos`} destacada />
        <Cifra valor={porcentaje(elegido.dentro_de_un_factor_10)} rotulo="de los casos, dentro de un factor de diez" destacada />
        <Cifra valor={porcentaje(1 - elegido.error_tipico_log10 / referencia.error_tipico_log10)} rotulo="menos error que la referencia sin aprendizaje" />
        <Cifra valor={numero(elegido.correlacion_de_rangos, 2)} rotulo="orden correcto (1 es perfecto, 0 es azar)" />
        <Cifra valor={numero(datos.intensidad_validada[1], 1)} rotulo="intensidad máxima en los datos" />
      </div>

      <div className="cuadros cuadros-de-viviendas">
        <Cuadro
          titulo="Candidatos, validados dejando fuera un sismo completo cada vez"
          nota="Error típico: por cuánto se equivoca normalmente (× 10 es diez veces más o diez veces menos). Gana el más simple."
        >
          <table className="tabla tabla-compacta">
            <thead>
              <tr>
                <th>Modelo</th>
                <th className="num">Error típico</th>
                <th className="num">Factor 10</th>
                <th className="num">Orden</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(datos.candidatos).map(([nombre, c]) => (
                <tr key={nombre} className={nombre === datos.modelo_elegido ? 'destacada' : undefined}>
                  <td>{c.descripcion}</td>
                  <td className="num">× {numero(10 ** c.error_tipico_log10, 0)}</td>
                  <td className="num">{porcentaje(c.dentro_de_un_factor_10)}</td>
                  <td className="num">{numero(c.correlacion_de_rangos, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Cuadro>

        <Cuadro
          titulo="Costo de atención por vivienda afectada"
          nota={`De ${numero(costo.emergencias)} emergencias de todo tipo con valor registrado por la UNGRD; solo ${costo.de_sismos} son sismos. Es gasto de atención del Estado, no indemnización.`}
        >
          <table className="tabla tabla-compacta">
            <tbody>
              <tr>
                <td>Bajo (el 25 % gasta menos)</td>
                <td className="num">{pesos(costo.bajo)}</td>
              </tr>
              <tr className="destacada">
                <td>Medio (mediana)</td>
                <td className="num">{pesos(costo.medio)}</td>
              </tr>
              <tr>
                <td>Alto (el 25 % gasta más)</td>
                <td className="num">{pesos(costo.alto)}</td>
              </tr>
            </tbody>
          </table>
        </Cuadro>

        <Cuadro titulo="Alcance">
          <p className="cuadro-texto">
            <strong>Es una primera aproximación.</strong> Con la misma intensidad, el daño real cambia mucho según cómo estén
            construidas las viviendas, y ese dato no se tiene.
          </p>
          <p className="cuadro-texto">
            Por eso la aplicación muestra siempre un <strong>rango</strong> y pide leerlo como orden de magnitud.
          </p>
          <p className="cuadro-texto">
            De las viviendas afectadas se estima destruida el {porcentaje(datos.proporcion_destruida.moderada)}, o el{' '}
            {porcentaje(datos.proporcion_destruida.fuerte)} desde intensidad VI (solo {datos.proporcion_destruida.casos_fuertes}{' '}
            casos).
          </p>
        </Cuadro>
      </div>
    </>
  );
}
