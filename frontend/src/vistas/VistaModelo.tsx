// Cómo se entrenó cada uno de los tres modelos y qué tan bien acierta.

import { useState } from 'react';
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

type Modelo = Zona | 'viviendas';
const MODELOS: { id: Modelo; nombre: string }[] = [
  { id: 'los_santos', nombre: 'Sismos · Los Santos' },
  { id: 'santander', nombre: 'Sismos · Santander' },
  { id: 'viviendas', nombre: 'Viviendas y costos' },
];

export default function VistaModelo() {
  const [modelo, setModelo] = useState<Modelo>('los_santos');
  return (
    <div className="documento">
      <h2>Los modelos</h2>
      <p>La aplicación usa tres modelos de aprendizaje supervisado, cada uno entrenado y validado por separado.</p>
      <div className="selector selector-de-modelo" role="group" aria-label="Modelo">
        {MODELOS.map((m) => (
          <button key={m.id} className={m.id === modelo ? 'activa' : undefined} aria-pressed={m.id === modelo} onClick={() => setModelo(m.id)}>
            {m.nombre}
          </button>
        ))}
      </div>
      {modelo === 'viviendas' ? <ModeloDeViviendas /> : <ModeloDeSismos zona={modelo} />}
    </div>
  );
}

function ModeloDeSismos({ zona }: { zona: Zona }) {
  const { datos, error } = useDatos(() => api.infoDelClasificador(zona), zona);
  if (!datos) return <Estado error={error} />;

  const importancias = Object.entries(datos.importancia_variables);
  const maxima = Math.max(...importancias.map(([, v]) => v));
  const elegido = datos.metricas[datos.nombre];
  const { etiquetas, valores } = datos.matriz_confusion;

  return (
    <>
      <h3>{zona === 'los_santos' ? 'Riesgo sísmico por zona en Los Santos' : 'Riesgo sísmico por zona en todo Santander'}</h3>
      <p>
        Clasificador supervisado <strong>{datos.nombre}</strong> con {datos.variables.length} variables calculadas del
        catálogo oficial del Servicio Geológico Colombiano, para {numero(datos.celdas_con_modelo)} celdas. Usa los
        sismos de magnitud {numero(datos.magnitud_minima, 1)} o mayor desde 2010. Cada caso es una celda de 5,5 km en un trimestre, y la respuesta es el número de sismos del
        trimestre siguiente: <strong>Bajo</strong> (ninguno), <strong>Medio</strong> (1 a {datos.umbrales_sismos[1]}) o{' '}
        <strong>Alto</strong> (más de {datos.umbrales_sismos[1]}).
      </p>

      <div className="tarjetas tarjetas-anchas">
        <div className="tarjeta">
          <div className="tarjeta-valor">{porcentaje(elegido.accuracy, 1)}</div>
          <span>exactitud en datos que no vio</span>
        </div>
        <div className="tarjeta">
          <div className="tarjeta-valor">{porcentaje(elegido.f1_macro, 1)}</div>
          <span>F1 macro</span>
        </div>
        <div className="tarjeta">
          <div className="tarjeta-valor">{numero(datos.muestras_entrenamiento)}</div>
          <span>casos de entrenamiento ({datos.periodo_entrenamiento.join(' a ')})</span>
        </div>
        <div className="tarjeta">
          <div className="tarjeta-valor">{numero(datos.muestras_prueba)}</div>
          <span>casos de prueba ({datos.periodo_prueba.join(' a ')})</span>
        </div>
      </div>

      <h3>Comparación con reglas sin aprendizaje</h3>
      <table className="tabla tabla-completa">
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
              <td>{nombre}</td>
              <td className="num">{porcentaje(m.accuracy, 1)}</td>
              <td className="num">{porcentaje(m.f1_macro, 1)}</td>
              <td className="num">{porcentaje(m.recall_alto, 1)}</td>
            </tr>
          ))}
          <tr className="referencia">
            <td>Techo de referencia (oráculo que conoce la tasa real)</td>
            <td className="num">{porcentaje(datos.techo_del_problema.accuracy, 1)}</td>
            <td className="num">{porcentaje(datos.techo_del_problema.f1_macro, 1)}</td>
            <td className="num">{porcentaje(datos.techo_del_problema.recall_alto, 1)}</td>
          </tr>
        </tbody>
      </table>
      <p className="apoyo">
        El modelo no llega al 100 % porque los sismos tienen un componente de azar: ni conociendo la tasa real de cada
        celda se supera el techo de referencia.
      </p>

      <div className="columnas">
        <section>
          <h3>Importancia de las variables</h3>
          {importancias.map(([variable, valor]) => (
            <div className="barra-fila barra-ancha" key={variable} title={`${NOMBRE_VARIABLE[variable]}: ${porcentaje(valor, 1)}`}>
              <span className="barra-nombre">{NOMBRE_VARIABLE[variable] ?? variable}</span>
              <span className="barra-pista">
                <span className="barra-relleno barra-azul" style={{ width: `${(valor / maxima) * 100}%` }} />
              </span>
              <span className="barra-valor">{porcentaje(valor, 1)}</span>
            </div>
          ))}
        </section>

        <section>
          <h3>Matriz de confusión</h3>
          <table className="tabla tabla-completa matriz">
            <thead>
              <tr>
                <th>Real ↓ / Predicho →</th>
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
          <p className="apoyo">En la diagonal están los aciertos. La clase Medio es la más difícil de separar.</p>

          <h3>Alcance</h3>
          <p className="apoyo">
            El nivel mide la actividad sísmica esperada en cada zona (amenaza). No incluye población ni vulnerabilidad
            de las construcciones, y no predice cuándo ocurrirá un sismo concreto.
          </p>
        </section>
      </div>
      {zona === 'santander' && (
        <p className="apoyo">
          En todo Santander más del 90 % de los casos son de nivel Bajo, así que la exactitud sola dice poco: lo que
          cuenta es el F1 macro y que el modelo supere a las reglas sin aprendizaje. Para las celdas de Los Santos
          predice mejor su propio modelo.
        </p>
      )}
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
      <h3>Viviendas afectadas por un sismo y costo de atención</h3>
      <p>
        Modelo de regresión que aprende, de sismos colombianos reales, qué proporción de las viviendas de un municipio
        resulta averiada o destruida según la intensidad con que le llega el sismo. Los daños son los que reportó la
        UNGRD entre 2019 y 2025; las viviendas de cada municipio, las del DANE; y la intensidad se calcula con el
        catálogo del USGS.
      </p>

      <div className="tarjetas tarjetas-anchas">
        <div className="tarjeta">
          <div className="tarjeta-valor">{numero(datos.casos)}</div>
          <span>casos (un municipio en un sismo), de {datos.sismos} sismos</span>
        </div>
        <div className="tarjeta">
          <div className="tarjeta-valor">{porcentaje(elegido.dentro_de_un_factor_10)}</div>
          <span>de los casos, dentro de un factor de diez</span>
        </div>
        <div className="tarjeta">
          <div className="tarjeta-valor">{porcentaje(1 - elegido.error_tipico_log10 / referencia.error_tipico_log10)}</div>
          <span>menos error que la referencia sin aprendizaje</span>
        </div>
        <div className="tarjeta">
          <div className="tarjeta-valor">{numero(datos.intensidad_validada[1], 1)}</div>
          <span>intensidad máxima en los datos; más arriba es extrapolación</span>
        </div>
      </div>

      <h3>Candidatos, validados dejando fuera un sismo completo cada vez</h3>
      <table className="tabla tabla-completa">
        <thead>
          <tr>
            <th>Modelo</th>
            <th className="num">Error típico</th>
            <th className="num">Dentro de un factor 10</th>
            <th className="num">Orden correcto</th>
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
      <p className="apoyo">
        Error típico: por cuánto se equivoca normalmente el modelo (× 10 es diez veces más o diez veces menos). Orden
        correcto: correlación de rangos entre lo predicho y lo observado; 1 es perfecto y 0 es azar.
      </p>

      <div className="columnas">
        <section>
          <h3>Costo de atención por vivienda afectada</h3>
          <table className="tabla tabla-completa">
            <tbody>
              <tr>
                <td>Bajo (el 25 % de las emergencias gasta menos)</td>
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
          <p className="apoyo">
            De {numero(costo.emergencias)} emergencias de todo tipo con valor registrado por la UNGRD; solo{' '}
            {costo.de_sismos} son sismos. Es gasto de atención del Estado, no indemnización ni costo de reconstrucción.
          </p>
        </section>

        <section>
          <h3>Alcance</h3>
          <p className="apoyo">
            Es un modelo de primera aproximación. Con la misma intensidad, el daño real cambia mucho según cómo estén
            construidas las viviendas, y ese dato no se tiene. Por eso la aplicación muestra siempre un rango y pide
            leerlo como orden de magnitud. De las viviendas afectadas, se estima destruida el{' '}
            {porcentaje(datos.proporcion_destruida.moderada)} (el {porcentaje(datos.proporcion_destruida.fuerte)} desde
            intensidad VI, con solo {datos.proporcion_destruida.casos_fuertes} casos).
          </p>
        </section>
      </div>
    </>
  );
}
