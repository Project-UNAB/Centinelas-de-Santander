# ==============================================================================
# HACKATHON: UTSmart IA Challenge 2027
# PROYECTO: Gemelo Digital Sísmico de Santander - Módulo Los Santos
# SCRIPT: Entrenamiento y validación del modelo de sacudida para el simulador
# PYTHON: 3.11+
# ==============================================================================
# El simulador recibe un escenario (magnitud, profundidad) y debe devolver la
# sacudida esperada en cada celda. Este script construye y valida ese modelo:
#
#   PASO 1. Modelo de fuente, a partir del catálogo del SGC de Los Santos:
#           dónde está el nido, a qué profundidad y cada cuánto ocurre un
#           sismo de cada magnitud (Gutenberg-Richter).
#   PASO 2. Validación del cálculo físico (Zhao 2006 + Worden 2012) contra
#           intensidades realmente observadas en sismos del nido (USGS).
#   PASO 3. ¿Aporta el Machine Learning? Se comparan el cálculo físico, sus
#           versiones calibradas (sesgo, regresión, Random Forest) y modelos
#           puramente estadísticos, validando por sismo completo.
#   PASO 4. Se entrena el modelo elegido con todos los datos y se exporta
#           junto con la grilla de Santander.
#
# Complemento del clasificador de riesgo (entrenar_modelo_sismico_los_santos.py):
# este modelo alimenta el simulador de escenarios de la demo.
#
# Uso:  python src/entrenar_modelo_sacudida.py
# ==============================================================================

import json
import sys

import geopandas as gpd
import joblib
import numpy as np
import pandas as pd
import sklearn
from shapely.geometry import box
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import LeaveOneGroupOut

import simulador as sim
from catalogo import CATALOGO_GEOJSON, MODELS_DIR, PROCESSED_DIR, RAW_DIR, cargar_catalogo

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

INTENSIDADES_CSV = RAW_DIR / "intensidades_dyfi_usgs.csv"
METRICAS_JSON = MODELS_DIR / "metricas_validacion.json"

# El catálogo solo es completo en todo el periodo para magnitudes altas: la red
# detecta cada vez más microsismos, pero los M>=4 se registran desde 2006
M_MIN_RECURRENCIA = 4.0
ANCHO_BIN_MAGNITUD = 0.1

# Rectángulo que contiene al departamento de Santander (la web lo recorta con
# el límite oficial) y tamaño de celda
SANTANDER_BBOX = {'lat_min': 5.70, 'lat_max': 8.15, 'lon_min': -74.55, 'lon_max': -72.40}
GRID_STEP = 0.05

# Un modelo más complejo solo se elige si reduce el error más que este margen
MARGEN_PARSIMONIA = 0.02
RANDOM_STATE = 42


# ==============================================================================
# PASO 1: MODELO DE FUENTE (CATÁLOGO SGC)
# ==============================================================================
def ajustar_modelo_de_fuente(cat):
    """Ubicación del nido y ley de recurrencia de Gutenberg-Richter."""
    nido = cat[(cat['magnitude'] >= M_MIN_RECURRENCIA) & (cat['depth'] >= sim.PROF_MIN_INTRAPLACA)]
    anios = (cat['utc_time'].max() - cat['utc_time'].min()).total_seconds() / (365.25 * 86400)

    # Valor b por máxima verosimilitud (Aki 1965, con la corrección de Utsu
    # por magnitudes redondeadas) y su error estándar
    mag_media = nido['magnitude'].mean()
    b = np.log10(np.e) / (mag_media - (M_MIN_RECURRENCIA - ANCHO_BIN_MAGNITUD / 2))
    recurrencia = {
        'm_min': M_MIN_RECURRENCIA,
        'b': float(b),
        'b_error': float(b / np.sqrt(len(nido))),
        'tasa_m_min': float(len(nido) / anios),
        'm_max_observada': float(nido['magnitude'].max()),
        'n_eventos': int(len(nido)),
        'anios': float(anios),
    }
    fuente = {
        'lat': float(nido['latitude'].median()),
        'lon': float(nido['longitude'].median()),
        'prof_mediana_km': float(nido['depth'].median()),
        'prof_p01': float(nido['depth'].quantile(0.01)),
        'prof_p99': float(nido['depth'].quantile(0.99)),
        'periodo': (int(cat['utc_time'].min().year), int(cat['utc_time'].max().year)),
        'recurrencia': recurrencia,
    }
    return fuente, nido


def comparar_recurrencia(fuente, nido):
    """Sismos por año observados frente a los que predice Gutenberg-Richter."""
    rec = fuente['recurrencia']
    filas = []
    for m in [4.0, 4.5, 5.0, 5.5, 6.0]:
        filas.append({
            'magnitud_min': m,
            'observados_por_anio': float((nido['magnitude'] >= m - 1e-9).sum() / rec['anios']),
            'modelo_por_anio': float(sim.tasa_anual_gutenberg_richter(rec, m)),
        })
    return pd.DataFrame(filas)


# ==============================================================================
# PASO 2: OBSERVACIONES DE SACUDIDA
# ==============================================================================
def cargar_observaciones(ruta):
    obs = pd.read_csv(ruta)
    obs['dist_epi_km'] = sim.distancia_epicentral_km(
        obs['obs_lat'], obs['obs_lon'], obs['ev_lat'], obs['ev_lon'])
    obs['dist_hipo_km'] = sim.distancia_hipocentral_km(obs['dist_epi_km'], obs['ev_prof_km'])
    obs['mmi_fisico'] = sim.mmi_fisico(obs['magnitud'], obs['dist_hipo_km'], obs['ev_prof_km'])
    obs['residuo'] = obs['intensidad_cdi'] - obs['mmi_fisico']
    # Una celda con muchas respuestas es una medida más fiable que una con una sola
    obs['peso'] = np.sqrt(obs['n_respuestas'])
    return obs


# ==============================================================================
# PASO 3: MODELOS CANDIDATOS Y VALIDACIÓN POR SISMO
# ==============================================================================
def nuevo_random_forest():
    return RandomForestRegressor(
        n_estimators=200,
        max_depth=6,
        min_samples_leaf=10,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )


# Cada candidato indica si parte del cálculo físico (y entonces aprende solo
# el residuo), qué estimador usa y con qué variables. Los 'elegibles' van de
# menor a mayor complejidad; los demás son solo referencias de comparación:
# sin física no saben qué pasa al cambiar la profundidad del escenario.
VARIABLES_FUENTE = ['magnitud', 'log_dist_hipo']
VARIABLES_ESPACIALES = ['magnitud', 'log_dist_hipo', 'lat', 'lon']
CANDIDATOS = {
    'fisico': {
        'descripcion': 'Cálculo físico sin ajustar (Zhao 2006 + Worden 2012)',
        'usa_fisica': True, 'estimador': None, 'features': [], 'elegible': True},
    'fisico_sesgo': {
        'descripcion': 'Físico + corrección constante del sesgo',
        'usa_fisica': True, 'estimador': 'sesgo', 'features': [], 'elegible': True},
    'fisico_lineal': {
        'descripcion': 'Físico + regresión lineal del residuo',
        'usa_fisica': True, 'estimador': LinearRegression, 'features': VARIABLES_FUENTE, 'elegible': True},
    'fisico_rf': {
        'descripcion': 'Físico + Random Forest del residuo',
        'usa_fisica': True, 'estimador': nuevo_random_forest, 'features': VARIABLES_FUENTE, 'elegible': True},
    'fisico_rf_espacial': {
        'descripcion': 'Físico + Random Forest del residuo con ubicación',
        'usa_fisica': True, 'estimador': nuevo_random_forest, 'features': VARIABLES_ESPACIALES, 'elegible': True},
    'lineal_puro': {
        'descripcion': 'Regresión lineal sin física (referencia)',
        'usa_fisica': False, 'estimador': LinearRegression, 'features': VARIABLES_FUENTE, 'elegible': False},
    'rf_puro': {
        'descripcion': 'Random Forest sin física (referencia)',
        'usa_fisica': False, 'estimador': nuevo_random_forest, 'features': VARIABLES_ESPACIALES, 'elegible': False},
}


def features_de(obs, columnas):
    return sim.construir_features(
        obs['magnitud'], obs['dist_hipo_km'], obs['obs_lat'], obs['obs_lon'], columnas)


def ajustar_candidato(candidato, obs):
    """Devuelve (sesgo, estimador) ajustados sobre las observaciones dadas."""
    if candidato['estimador'] is None:
        return 0.0, None
    objetivo = obs['residuo'] if candidato['usa_fisica'] else obs['intensidad_cdi']
    if candidato['estimador'] == 'sesgo':
        return float(np.average(objetivo, weights=obs['peso'])), None
    estimador = candidato['estimador']()
    estimador.fit(features_de(obs, candidato['features']), objetivo, sample_weight=obs['peso'])
    return 0.0, estimador


def predecir_candidato(candidato, sesgo, estimador, obs):
    mmi = obs['mmi_fisico'].to_numpy() if candidato['usa_fisica'] else np.zeros(len(obs))
    mmi = mmi + sesgo
    if estimador is not None:
        mmi = mmi + estimador.predict(features_de(obs, candidato['features']))
    return np.clip(mmi, 1.0, 10.0)


def validar_por_sismo(obs):
    """
    Validación dejando fuera un sismo completo cada vez: el modelo nunca ve
    observaciones del sismo que debe predecir, igual que en un escenario nuevo.
    """
    predicciones = {nombre: np.zeros(len(obs)) for nombre in CANDIDATOS}
    for idx_train, idx_test in LeaveOneGroupOut().split(obs, groups=obs['evento_id']):
        train, test = obs.iloc[idx_train], obs.iloc[idx_test]
        for nombre, candidato in CANDIDATOS.items():
            sesgo, estimador = ajustar_candidato(candidato, train)
            predicciones[nombre][idx_test] = predecir_candidato(candidato, sesgo, estimador, test)
    return predicciones


def calcular_metricas(observado, predicho):
    error = predicho - observado
    nivel_obs, nivel_pred = sim.clasificar_nivel(observado), sim.clasificar_nivel(predicho)
    return {
        'rmse': float(np.sqrt(np.mean(error ** 2))),
        'mae': float(np.mean(np.abs(error))),
        'sesgo': float(np.mean(error)),
        'dentro_de_1_grado': float(np.mean(np.abs(error) <= 1.0)),
        'exactitud_nivel': float(np.mean(nivel_obs == nivel_pred)),
    }


def elegir_modelo(metricas):
    """El más simple entre los elegibles cuyo error esté a un 2% del mejor."""
    elegibles = [n for n, c in CANDIDATOS.items() if c['elegible']]
    mejor_rmse = min(metricas[n]['rmse'] for n in elegibles)
    for nombre in elegibles:
        if metricas[nombre]['rmse'] <= mejor_rmse * (1 + MARGEN_PARSIMONIA):
            return nombre


# ==============================================================================
# PASO 4: GRILLA DE SANTANDER
# ==============================================================================
def crear_grilla(fuente):
    lats = np.arange(SANTANDER_BBOX['lat_min'], SANTANDER_BBOX['lat_max'] - 1e-9, GRID_STEP)
    lons = np.arange(SANTANDER_BBOX['lon_min'], SANTANDER_BBOX['lon_max'] - 1e-9, GRID_STEP)
    celdas = []
    for lat in lats:
        for lon in lons:
            celdas.append({
                'cell_id': len(celdas),
                'lat_center': lat + GRID_STEP / 2,
                'lon_center': lon + GRID_STEP / 2,
                'geometry': box(lon, lat, lon + GRID_STEP, lat + GRID_STEP),
            })
    grilla = gpd.GeoDataFrame(celdas, crs="EPSG:4326")
    grilla['dist_nido_km'] = sim.distancia_epicentral_km(
        grilla['lat_center'], grilla['lon_center'], fuente['lat'], fuente['lon'])
    grilla['vs30'] = sim.VS30_DEFECTO
    return grilla


def main():
    print("=" * 80)
    print("ENTRENAMIENTO DEL MODELO DE SACUDIDA - GEMELO DIGITAL SÍSMICO DE SANTANDER")
    print("=" * 80)

    # --------------------------------------------------------------------------
    print(f"\n1. Modelo de fuente a partir del catálogo SGC: {CATALOGO_GEOJSON.name}")
    cat = cargar_catalogo(CATALOGO_GEOJSON)
    fuente, nido = ajustar_modelo_de_fuente(cat)
    rec = fuente['recurrencia']
    print(f"   -> Sismos en el catálogo: {len(cat):,}  ({rec['anios']:.1f} años)")
    print(f"   -> Sismos M>={rec['m_min']} del nido usados: {rec['n_eventos']}")
    print(f"   -> Centro del nido: lat {fuente['lat']:.3f}, lon {fuente['lon']:.3f}, "
          f"profundidad {fuente['prof_mediana_km']:.0f} km "
          f"(99% entre {fuente['prof_p01']:.0f} y {fuente['prof_p99']:.0f} km)")
    print(f"   -> Gutenberg-Richter: b = {rec['b']:.2f} ± {rec['b_error']:.2f}, "
          f"{rec['tasa_m_min']:.1f} sismos M>={rec['m_min']} por año")
    tabla_recurrencia = comparar_recurrencia(fuente, nido)
    print("   -> Recurrencia observada frente al modelo (sismos por año):")
    for fila in tabla_recurrencia.itertuples():
        print(f"      M>={fila.magnitud_min:.1f}: observados {fila.observados_por_anio:6.2f}   "
              f"modelo {fila.modelo_por_anio:6.2f}")

    # --------------------------------------------------------------------------
    print(f"\n2. Observaciones de sacudida: {INTENSIDADES_CSV.name}")
    if not INTENSIDADES_CSV.exists():
        sys.exit("   Falta el archivo. Ejecuta primero: python src/descargar_intensidades_usgs.py")
    obs = cargar_observaciones(INTENSIDADES_CSV)
    rango_validado = {
        'magnitud': (float(obs['magnitud'].min()), float(obs['magnitud'].max())),
        'prof_km': (float(obs['ev_prof_km'].min()), float(obs['ev_prof_km'].max())),
        'dist_hipo_km': (float(obs['dist_hipo_km'].min()), float(obs['dist_hipo_km'].max())),
        'intensidad': (float(obs['intensidad_cdi'].min()), float(obs['intensidad_cdi'].max())),
    }
    print(f"   -> {len(obs)} observaciones de {obs['evento_id'].nunique()} sismos "
          f"({int(obs['n_respuestas'].sum()):,} respuestas de la población)")
    print(f"   -> Magnitud {rango_validado['magnitud'][0]:.1f} a {rango_validado['magnitud'][1]:.1f}, "
          f"profundidad {rango_validado['prof_km'][0]:.0f} a {rango_validado['prof_km'][1]:.0f} km, "
          f"distancia {rango_validado['dist_hipo_km'][0]:.0f} a {rango_validado['dist_hipo_km'][1]:.0f} km")
    print(f"   -> Intensidad observada: {rango_validado['intensidad'][0]:.1f} a "
          f"{rango_validado['intensidad'][1]:.1f}")
    print("   -> Niveles observados: "
          + ", ".join(f"{n} {c}" for n, c in
                      pd.Series(sim.clasificar_nivel(obs['intensidad_cdi'])).value_counts().items()))

    # --------------------------------------------------------------------------
    print("\n3. Validación dejando fuera un sismo completo cada vez...")
    predicciones = validar_por_sismo(obs)
    observado = obs['intensidad_cdi'].to_numpy()
    metricas = {n: calcular_metricas(observado, p) for n, p in predicciones.items()}

    print("\n" + "=" * 80)
    print("RESULTADOS (error en grados de intensidad Mercalli)")
    print("=" * 80)
    print(f"{'Modelo':52s} {'RMSE':>6s} {'MAE':>6s} {'Sesgo':>7s} {'±1 grado':>9s} {'Nivel':>7s}")
    for nombre, m in metricas.items():
        print(f"{CANDIDATOS[nombre]['descripcion']:52s} {m['rmse']:6.3f} {m['mae']:6.3f} "
              f"{m['sesgo']:+7.3f} {m['dentro_de_1_grado']:9.1%} {m['exactitud_nivel']:7.1%}")

    elegido = elegir_modelo(metricas)
    print(f"\n   -> Modelo elegido: {CANDIDATOS[elegido]['descripcion']}")
    mejora = 1 - metricas[elegido]['rmse'] / metricas['fisico']['rmse']
    print(f"   -> Reduce el error del cálculo físico sin ajustar en un {mejora:.1%}")

    print("\nMATRIZ DE CONFUSIÓN DEL MODELO ELEGIDO (Filas: Observado, Columnas: Predicho):")
    cm = confusion_matrix(sim.clasificar_nivel(observado),
                          sim.clasificar_nivel(predicciones[elegido]), labels=sim.NIVELES)
    print(pd.DataFrame(cm, index=[f'Obs_{n}' for n in sim.NIVELES],
                       columns=[f'Pred_{n}' for n in sim.NIVELES]))

    # --------------------------------------------------------------------------
    print("\n4. Entrenando el modelo elegido con todas las observaciones y exportando...")
    candidato = CANDIDATOS[elegido]
    sesgo, estimador = ajustar_candidato(candidato, obs)
    X_todo = features_de(obs, candidato['features'])
    modelo = {
        'gmpe': 'Zhao et al. (2006)',
        'gmice': 'Worden et al. (2012)',
        'vs30_defecto': sim.VS30_DEFECTO,
        'calibracion': {
            'tipo': elegido,
            'sesgo': sesgo,
            'estimador': estimador,
            'features': candidato['features'],
            # La corrección no se extrapola fuera de lo que se observó
            'limites': {c: (float(X_todo[c].min()), float(X_todo[c].max())) for c in X_todo.columns},
        },
        'rango_validado': rango_validado,
        'error_tipico_mmi': metricas[elegido]['rmse'],
        'fuente': fuente,
        'version_sklearn': sklearn.__version__ if estimador is not None else None,
    }

    grilla = crear_grilla(fuente)
    # Escenario de referencia: repetición del mayor sismo del catálogo
    m_ref, h_ref = rec['m_max_observada'], fuente['prof_mediana_km']
    referencia, info = sim.simular_escenario(
        modelo, m_ref, h_ref, grilla['lat_center'], grilla['lon_center'], grilla['vs30'])
    grilla['mmi_referencia'] = referencia['mmi'].round(2)
    grilla['nivel_referencia'] = referencia['nivel']

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(modelo, sim.MODELO_PKL)
    grilla.to_file(sim.GRILLA_GEOJSON, driver="GeoJSON")
    with open(METRICAS_JSON, 'w', encoding='utf-8') as f:
        json.dump({
            'modelo_elegido': elegido,
            'validacion': 'dejando fuera un sismo completo cada vez',
            'n_observaciones': len(obs),
            'n_sismos': int(obs['evento_id'].nunique()),
            'rango_validado': rango_validado,
            'candidatos': {n: {'descripcion': CANDIDATOS[n]['descripcion'], **m}
                           for n, m in metricas.items()},
            'fuente': fuente,
            'recurrencia_observada_vs_modelo': tabla_recurrencia.to_dict(orient='records'),
        }, f, ensure_ascii=False, indent=2)

    print(f"   -> Escenario de referencia M{m_ref} a {h_ref:.0f} km: intensidad máxima "
          f"{info['mmi_maxima']:.1f}, celdas por nivel {info['celdas_por_nivel']}")
    print(f"   -> Modelo guardado en:   {sim.MODELO_PKL}")
    print(f"   -> Grilla guardada en:   {sim.GRILLA_GEOJSON}  ({len(grilla)} celdas)")
    print(f"   -> Métricas guardadas en: {METRICAS_JSON}")
    print("=" * 80)
    print("PIPELINE COMPLETADO. La web solo necesita importar src/simulador.py")
    print("=" * 80)


if __name__ == "__main__":
    main()
