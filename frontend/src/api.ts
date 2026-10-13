// Cliente de la API del backend y tipos de sus respuestas.

const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

export type Nivel = 'Bajo' | 'Medio' | 'Alto';

export interface PropiedadesDeCelda {
  cell_id: number;
  municipio: string;
  lat_center: number;
  lon_center: number;
  dist_nido_km: number;
  riesgo_predicho: Nivel;
  prob_bajo: number;
  prob_medio: number;
  prob_alto: number;
  con_sismicidad_registrada: boolean;
  /** Falso en las celdas del rectángulo de Santander que quedan fuera del departamento */
  en_el_departamento: boolean;
  trimestre_predicho: string;
  sismos_trimestre: number;
  sismos_ultimo_anio: number;
  sismos_promedio_historico: number;
  sismos_vecinos_ultimo_anio: number;
  mag_max_ultimo_anio: number;
  prof_media_ultimo_anio: number;
  trimestres_desde_sismo_fuerte: number;
}

export interface Celda {
  type: 'Feature';
  properties: PropiedadesDeCelda;
  geometry: { type: 'Polygon'; coordinates: number[][][] };
}

export interface Municipio {
  type: 'Feature';
  properties: { municipio: string };
  geometry:
    | { type: 'Polygon'; coordinates: number[][][] }
    | { type: 'MultiPolygon'; coordinates: number[][][][] };
}

export interface Coleccion<T> {
  type: 'FeatureCollection';
  features: T[];
}

export interface Metricas {
  accuracy: number;
  f1_macro: number;
  recall_alto: number;
}

export interface InfoDelClasificador {
  zona: Zona;
  celdas_con_modelo: number;
  ajustes: { balanceo: number; profundidad: number } | null;
  nombre: string;
  variables: string[];
  umbrales_sismos: [number, number];
  magnitud_minima: number;
  periodo_entrenamiento: [string, string];
  periodo_prueba: [string, string];
  muestras_entrenamiento: number;
  muestras_prueba: number;
  metricas: Record<string, Metricas>;
  techo_del_problema: Metricas;
  matriz_confusion: { etiquetas: Nivel[]; valores: number[][] };
  importancia_variables: Record<string, number>;
}

/** Un trimestre del periodo de prueba; las listas van en el orden de cell_id. */
export interface TrimestreDePrueba {
  trimestre: string;
  /** Sismos M≥2,5 que ocurrieron en cada celda */
  sismos: number[];
  /** Nivel como posición en «niveles» (0 Bajo, 1 Medio, 2 Alto) */
  predicho: number[];
  real: number[];
}

export interface HistorialDeRiesgo {
  modelo: string;
  niveles: Nivel[];
  celdas_con_modelo: number[];
  trimestres: TrimestreDePrueba[];
}

export interface GrillaDelSimulador {
  paso: number;
  lat: number[];
  lon: number[];
  municipio: string[];
  epicentro: { lat: number; lon: number };
  limites: { magnitud: [number, number]; profundidad_km: [number, number] };
}

/** Estimación del modelo de viviendas: valor central y rango, porque su error es grande. */
export interface ViviendasAfectadas {
  total: number;
  afectadas_bajo: number;
  afectadas: number;
  afectadas_alto: number;
  destruidas: number;
  costo_bajo: number;
  costo: number;
  costo_alto: number;
  /** Valor central de cada municipio, en el orden de la población */
  afectadas_por_municipio: number[];
  intensidad_maxima: number;
  intensidad_validada: [number, number];
  fuera_de_lo_observado: boolean;
  costo_por_vivienda_cop: { bajo: number; medio: number; alto: number };
}

export interface CandidatoDeViviendas {
  descripcion: string;
  error_tipico_log10: number;
  dentro_de_un_factor_10: number;
  correlacion_de_rangos: number;
  viviendas_predichas: number;
  viviendas_reales: number;
}

export interface InfoDelModeloDeViviendas {
  modelo_elegido: string;
  validacion: string;
  casos: number;
  sismos: number;
  casos_con_dano: number;
  intensidad_validada: [number, number];
  candidatos: Record<string, CandidatoDeViviendas>;
  proporcion_destruida: { moderada: number; fuerte: number; casos_fuertes: number };
  costo_por_vivienda_cop: { bajo: number; medio: number; alto: number; emergencias: number; de_sismos: number };
}

export interface InfoDeEscenario {
  tipo_fuente: 'intraplaca' | 'cortical';
  mmi_maxima: number;
  celdas_por_nivel: Record<Nivel, number>;
  /** Habitantes de Santander según la sacudida de su municipio (aproximación por municipio completo) */
  personas_por_nivel: Record<Nivel, number>;
  municipios_por_nivel: Record<Nivel, number>;
  /** Nivel con que cuenta cada municipio, en el orden de la población */
  nivel_por_municipio: Nivel[];
  viviendas: ViviendasAfectadas;
  anio_de_la_poblacion: number;
  error_tipico_mmi: number | null;
  profundidad_tipica_del_nido: boolean;
  advertencias: string[];
  periodo_retorno_anios?: number;
}

/** Zonas con relieve 3D. */
export type Zona = 'santander' | 'los_santos';

/** Intensidad en una malla fina, fila por fila de norte a sur. */
export interface CampoDeSacudida {
  oeste: number;
  este: number;
  sur: number;
  norte: number;
  filas: number;
  columnas: number;
  mmi: number[];
}

export interface MapaDeCalor {
  info: InfoDeEscenario;
  campo: CampoDeSacudida;
}

/** Epicentro de un escenario; sin él, el backend usa el centro del nido. */
export interface Epicentro {
  lat: number;
  lon: number;
}

/** Sismo real del nido con lo que la población reportó en cada lugar (USGS, «Did You Feel It?»). */
export interface SismoReal extends Epicentro {
  id: string;
  fecha_utc: string;
  magnitud: number;
  tipo_magnitud: string;
  profundidad_km: number;
  respuestas: number;
  /** Modelo menos observado, con el modelo calibrado sin este sismo */
  desvio: { sesgo: number; error_absoluto_medio: number; dentro_de_1_grado: number };
  /** Una posición por lugar con reportes */
  observaciones: { lat: number[]; lon: number[]; intensidad: number[]; intensidad_del_modelo: number[]; respuestas: number[] };
}

/** Habitantes de cada municipio de Santander (proyección del DANE), en columnas. */
export interface Poblacion {
  fuente: string;
  anio: number;
  municipio: string[];
  habitantes: number[];
  viviendas: number[];
}

export interface Sismos {
  lon: number[];
  lat: number[];
  profundidad_km: number[];
  magnitud: number[];
  anio: number[];
}

/** Sismos generados por el backend con las propiedades estadísticas del catálogo real. */
export interface SismosSimulados extends Sismos {
  modelo: { tasa_anual: number; m_min: number; m_max: number; sismos_reales: number; anios: number; semilla: number };
}

export interface Relieve {
  fuente: string;
  filas: number;
  columnas: number;
  lon_oeste: number;
  lon_este: number;
  lat_sur: number;
  lat_norte: number;
  elevacion_min: number;
  elevacion_max: number;
  /** Metros sobre el nivel del mar, fila por fila de norte a sur; -1 fuera del departamento */
  elevaciones: number[];
}

async function pedir<T>(ruta: string, opciones?: RequestInit): Promise<T> {
  const respuesta = await fetch(`${API_URL}${ruta}`, opciones);
  if (!respuesta.ok) {
    throw new Error(`La API respondió ${respuesta.status} en ${ruta}`);
  }
  return respuesta.json() as Promise<T>;
}

// Los datos fijos (límites, sismos, relieve, celdas) se piden una sola vez por sesión:
// al cambiar de pestaña se reutilizan en vez de volver a descargarse
const yaPedidos = new Map<string, Promise<unknown>>();

function pedirUnaVez<T>(ruta: string): Promise<T> {
  if (!yaPedidos.has(ruta)) {
    const promesa = pedir<T>(ruta);
    promesa.catch(() => yaPedidos.delete(ruta));
    yaPedidos.set(ruta, promesa);
  }
  return yaPedidos.get(ruta) as Promise<T>;
}

// Últimos mapas de calor recibidos: volver a un escenario ya visto es instantáneo
const MAPAS_GUARDADOS = 80;
const mapasDeCalor = new Map<string, MapaDeCalor>();
const claveDelMapa = (magnitud: number, profundidad_km: number, zona: Zona, epicentro?: Epicentro) =>
  `${zona}|${magnitud.toFixed(2)}|${profundidad_km}|${epicentro ? `${epicentro.lat},${epicentro.lon}` : 'nido'}`;

export const api = {
  // Cada zona tiene su propio clasificador: el de Los Santos (30 celdas) y el de todo Santander
  celdasDeRiesgo: (zona: Zona = 'los_santos') => pedirUnaVez<Coleccion<Celda>>(`/api/riesgo/celdas?zona=${zona}`),
  infoDelClasificador: (zona: Zona = 'los_santos') => pedirUnaVez<InfoDelClasificador>(`/api/riesgo/modelo?zona=${zona}`),
  historialDeRiesgo: (zona: Zona = 'los_santos') => pedirUnaVez<HistorialDeRiesgo>(`/api/riesgo/historial?zona=${zona}`),
  infoDelModeloDeViviendas: () => pedirUnaVez<InfoDelModeloDeViviendas>('/api/danos/modelo'),
  municipios: () => pedirUnaVez<Coleccion<Municipio>>('/api/municipios'),
  sismos: () => pedirUnaVez<Sismos>('/api/sismos'),
  poblacion: () => pedirUnaVez<Poblacion>('/api/poblacion'),
  /** Catálogo sintético. No se guarda en el navegador: hay muchas combinaciones y el backend ya las recuerda. */
  sismosSimulados: (anios: number, semilla: number, signal?: AbortSignal) =>
    pedir<SismosSimulados>(`/api/simulador/sismos?anios=${anios}&semilla=${semilla}`, { signal }),
  relieve: (zona: Zona) => pedirUnaVez<Relieve>(`/api/relieve/${zona}`),
  grillaDelSimulador: () => pedirUnaVez<GrillaDelSimulador>('/api/simulador/grilla'),
  sismosReales: () => pedirUnaVez<SismoReal[]>('/api/simulador/sismos-reales'),

  /** Mapa de calor ya recibido antes para ese escenario, si lo hay. */
  mapaDeCalorGuardado: (magnitud: number, profundidad_km: number, zona: Zona, epicentro?: Epicentro) =>
    mapasDeCalor.get(claveDelMapa(magnitud, profundidad_km, zona, epicentro)) ?? null,

  mapaDeCalor: async (magnitud: number, profundidad_km: number, zona: Zona, signal?: AbortSignal, epicentro?: Epicentro) => {
    const mapa = await pedir<MapaDeCalor>('/api/simulador/mapa-de-calor', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ magnitud, profundidad_km, zona, epicentro_lat: epicentro?.lat, epicentro_lon: epicentro?.lon }),
      signal,
    });
    mapasDeCalor.set(claveDelMapa(magnitud, profundidad_km, zona, epicentro), mapa);
    // Al llenarse se descarta el más antiguo
    if (mapasDeCalor.size > MAPAS_GUARDADOS) mapasDeCalor.delete(mapasDeCalor.keys().next().value!);
    return mapa;
  },
};
