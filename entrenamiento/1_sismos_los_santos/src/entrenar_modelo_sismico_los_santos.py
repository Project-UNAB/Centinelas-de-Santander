# ==============================================================================
# HACKATHON: UTSmart IA Challenge 2027 - Categoría Básica
# PROYECTO: Gemelo Digital Sísmico de Santander - Módulo Los Santos
# SCRIPT: Entrenamiento del clasificador supervisado de riesgo sísmico por zona
# PYTHON: 3.11+
# ==============================================================================
# Reto: determinar un nivel de riesgo (Bajo, Medio, Alto) para cada zona de
# Los Santos a partir del catálogo sísmico oficial del SGC.
#
#   - Datos:     catálogo del SGC de todo Santander. Se predice solo la zona de
#                Los Santos, pero sus variables se calculan con todos los sismos
#                que la rodean, sin importar a qué municipio los asigne el SGC.
#   - Zona:      celda de 0.05° x 0.05° (unos 5.5 km de lado).
#   - Momento:   trimestre. Con lo ocurrido hasta el trimestre t se predice
#                el trimestre t+1, así que el modelo nunca ve el futuro.
#   - Etiqueta:  nivel de actividad sísmica del trimestre siguiente: Bajo
#                (ningún sismo), Medio (de 1 a 3) o Alto (más de 3).
#   - Variables: 15, todas calculadas del catálogo (ver docs/DATOS_Y_VARIABLES.md).
#   - Modelos:   Regresión Logística y Random Forest, comparados contra tres
#                líneas base sin aprendizaje.
#
# Uso:  python 1_sismos_los_santos/src/entrenar_modelo_sismico_los_santos.py
# ==============================================================================

import json
import sys
from pathlib import Path

import geopandas as gpd
import joblib
import numpy as np
import pandas as pd
import sklearn
from scipy.stats import poisson
from shapely.geometry import box
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    recall_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

# Carpeta de este modelo; el código compartido (catálogo, simulador) está en entrenamiento/comun
CARPETA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CARPETA.parent / "comun" / "src"))
from catalogo import cargar_catalogo  # noqa: E402

PROCESSED_DIR = CARPETA / "data" / "processed"
MODELS_DIR = CARPETA / "models"

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

DATASET_CSV = PROCESSED_DIR / "dataset_entrenamiento_los_santos.csv"
GRILLA_GEOJSON = PROCESSED_DIR / "grilla_riesgo_los_santos.geojson"
MODELO_PKL = MODELS_DIR / "modelo_riesgo_sismico_los_santos.pkl"
METRICAS_JSON = MODELS_DIR / "metricas_clasificador.json"
HISTORIAL_JSON = MODELS_DIR / "historial_prueba.json"

# ------------------------------------------------------------------------------
# Catálogo homogéneo: la red sísmica detecta cada vez más microsismos, así que
# contar todos los eventos mediría la mejora de la red y no la sismicidad.
# Desde 2010 los sismos de magnitud >= 2.5 se registran de forma estable.
# ------------------------------------------------------------------------------
ANIO_INICIO = 2010
MAGNITUD_MINIMA = 2.5

# Grilla sobre la zona sísmica de Los Santos: las celdas para las que se predice
LAT_MIN, LON_MIN = 6.70, -73.25
N_FILAS, N_COLUMNAS = 5, 6
GRID_STEP = 0.05
# Celdas que se añaden alrededor de la zona solo para calcular las variables: así las
# celdas del borde también conocen la actividad de sus vecinas (unos 28 km a cada lado)
MARGEN_CELDAS = 5

# Sismos M>=2.5 por trimestre que separan los niveles: Bajo si no hay ninguno, Medio
# hasta 3 (uno por mes en promedio) y Alto si hay más
UMBRALES_SISMOS = [0.0, 3.0]

VENTANA_MESES = 3            # cada ventana es un trimestre
VENTANAS_POR_ANIO = 12 // VENTANA_MESES
MAGNITUD_FUERTE = 4.0        # sismo sentido con claridad en superficie
MAGNITUD_MODERADA = 3.5

# Partición temporal: se entrena con el pasado y se prueba con lo más reciente
FECHA_INICIO_PRUEBA = pd.Timestamp('2022-01-01', tz='UTC')

NIVELES = ['Bajo', 'Medio', 'Alto']

# Ajustes del Random Forest que se eligen con validación dentro del entrenamiento.
# Balanceo: cuánto se compensa que haya pocos casos de nivel Medio y Alto. Con 1 las
# tres clases pesan igual (el modelo avisa más, pero da más falsas alarmas); con 0 no
# se compensa nada. Profundidad: cuántas preguntas seguidas puede hacer cada árbol.
BALANCEOS = [1.0, 0.75, 0.5, 0.25, 0.0]
PROFUNDIDADES = [6, 10]
ANIOS_DE_VALIDACION = range(2017, 2022)
# Si se indica, solo se modelan estas celdas (lo usa el modelo de todo Santander para quedarse con las del departamento)
CELDAS_PERMITIDAS = None
TITULO = "CLASIFICADOR DE RIESGO SÍSMICO POR ZONA - LOS SANTOS, SANTANDER"
RANDOM_STATE = 42

# Las 15 variables del modelo. Todas describen la celda con información
# disponible al cierre del trimestre t (sin fuga de información del futuro).
FEATURES = [
    'sismos_trimestre',
    'sismos_ultimo_anio',
    'sismos_promedio_historico',
    'tendencia_sismos',
    'sismos_vecinos_ultimo_anio',
    'mag_media_ultimo_anio',
    'mag_max_ultimo_anio',
    'log_energia_ultimo_anio',
    'prop_moderados_ultimo_anio',
    'trimestres_desde_sismo_fuerte',
    'prof_media_ultimo_anio',
    'prof_std_ultimo_anio',
    'dist_nido_km',
    'lat_center',
    'lon_center',
]


# ==============================================================================
# PASO 1: CATÁLOGO HOMOGÉNEO, GRILLA Y VENTANAS DE TIEMPO
# ==============================================================================
def preparar_catalogo(cat):
    """
    Filtra el catálogo y asigna a cada sismo su celda y su trimestre. Se conservan
    los sismos de la zona y los de su margen; fila y columna se cuentan desde la
    esquina de la grilla ampliada (la zona empieza en MARGEN_CELDAS).
    """
    cat = cat[(cat['utc_time'].dt.year >= ANIO_INICIO) & (cat['magnitude'] >= MAGNITUD_MINIMA)].copy()
    cat['fila'] = np.floor((cat['latitude'] - LAT_MIN) / GRID_STEP).astype(int) + MARGEN_CELDAS
    cat['columna'] = np.floor((cat['longitude'] - LON_MIN) / GRID_STEP).astype(int) + MARGEN_CELDAS
    cat = cat[cat['fila'].between(0, N_FILAS + 2 * MARGEN_CELDAS - 1)
              & cat['columna'].between(0, N_COLUMNAS + 2 * MARGEN_CELDAS - 1)]

    meses = (cat['utc_time'].dt.year - ANIO_INICIO) * 12 + cat['utc_time'].dt.month - 1
    cat['ventana'] = meses // VENTANA_MESES
    # El último trimestre del catálogo está incompleto y no se usa
    return cat[cat['ventana'] < cat['ventana'].max()]


def en_la_zona(cat):
    """Sismos que caen dentro de las celdas para las que se predice (sin el margen)."""
    return (cat['fila'].between(MARGEN_CELDAS, MARGEN_CELDAS + N_FILAS - 1)
            & cat['columna'].between(MARGEN_CELDAS, MARGEN_CELDAS + N_COLUMNAS - 1))


def inicio_de_ventana(ventana):
    meses = int(ventana) * VENTANA_MESES
    return pd.Timestamp(year=ANIO_INICIO + meses // 12, month=meses % 12 + 1, day=1, tz='UTC')


def etiqueta_de_ventana(ventana):
    inicio = inicio_de_ventana(ventana)
    return f"{inicio.year}-T{(inicio.month - 1) // VENTANA_MESES + 1}"


def crear_grilla(cat):
    """Celdas de la grilla con su geometría y su distancia al centro del nido."""
    nido_lat, nido_lon = cat['latitude'].median(), cat['longitude'].median()
    celdas = []
    for fila in range(N_FILAS):
        for columna in range(N_COLUMNAS):
            lat, lon = LAT_MIN + fila * GRID_STEP, LON_MIN + columna * GRID_STEP
            celdas.append({
                'cell_id': fila * N_COLUMNAS + columna,
                'fila': fila,
                'columna': columna,
                'lat_center': lat + GRID_STEP / 2,
                'lon_center': lon + GRID_STEP / 2,
                'geometry': box(lon, lat, lon + GRID_STEP, lat + GRID_STEP),
            })
    grilla = gpd.GeoDataFrame(celdas, crs="EPSG:4326")
    # 1° ~ 111.12 km; a esta latitud la diferencia entre meridianos es mínima
    grilla['dist_nido_km'] = 111.12 * np.hypot(
        grilla['lat_center'] - nido_lat,
        (grilla['lon_center'] - nido_lon) * np.cos(np.radians(nido_lat)))
    return grilla


# ==============================================================================
# PASO 2: INGENIERÍA DE VARIABLES
# ==============================================================================
def acumular(cat, n_ventanas, valores=None, filtro=None):
    """Suma por (fila, columna, trimestre) de un valor por sismo (o conteo), en la grilla ampliada."""
    cubo = np.zeros((N_FILAS + 2 * MARGEN_CELDAS, N_COLUMNAS + 2 * MARGEN_CELDAS, n_ventanas))
    datos = cat if filtro is None else cat[filtro]
    pesos = 1.0 if valores is None else datos[valores].to_numpy()
    np.add.at(cubo, (datos['fila'].to_numpy(), datos['columna'].to_numpy(), datos['ventana'].to_numpy()), pesos)
    return cubo


def suma_ultimo_anio(cubo):
    """Suma de cada trimestre con los tres anteriores."""
    acumulado = np.cumsum(cubo, axis=2)
    resultado = acumulado.copy()
    resultado[:, :, VENTANAS_POR_ANIO:] -= acumulado[:, :, :-VENTANAS_POR_ANIO]
    return resultado


def dividir(numerador, denominador):
    """División que devuelve 0 donde no hubo sismos."""
    return np.divide(numerador, denominador, out=np.zeros_like(numerador), where=denominador > 0)


def calcular_variables(cat, grilla, n_ventanas):
    """
    Devuelve un diccionario {variable: cubo (fila, columna, trimestre)} con las
    celdas de la zona. Todo se calcula en la grilla ampliada y al final se
    recorta el margen.
    """
    n = acumular(cat, n_ventanas)
    n_anio = suma_ultimo_anio(n)

    # Magnitud máxima del último año
    mag_max = np.zeros_like(n)
    np.maximum.at(mag_max, (cat['fila'].to_numpy(), cat['columna'].to_numpy(), cat['ventana'].to_numpy()),
                  cat['magnitude'].to_numpy())
    mag_max_anio = mag_max.copy()
    for atras in range(1, VENTANAS_POR_ANIO):
        mag_max_anio[:, :, atras:] = np.maximum(mag_max_anio[:, :, atras:], mag_max[:, :, :-atras])

    # Actividad de las 8 celdas vecinas: la sismicidad se agrupa en el espacio
    filas, columnas = n.shape[:2]
    relleno = np.pad(n_anio, ((1, 1), (1, 1), (0, 0)))
    vecinos = sum(relleno[1 + df:1 + df + filas, 1 + dc:1 + dc + columnas]
                  for df in (-1, 0, 1) for dc in (-1, 0, 1) if (df, dc) != (0, 0))

    # Trimestres transcurridos desde el último sismo fuerte de la celda
    hubo_fuerte = acumular(cat, n_ventanas, filtro=cat['magnitude'] >= MAGNITUD_FUERTE) > 0
    desde_fuerte = np.zeros_like(n)
    contador = np.full((filas, columnas), float(n_ventanas))   # "nunca" al empezar
    for t in range(n_ventanas):
        contador = np.where(hubo_fuerte[:, :, t], 0.0, contador + 1)
        desde_fuerte[:, :, t] = np.minimum(contador, n_ventanas)

    cat = cat.assign(depth2=cat['depth'] ** 2)
    prof_media = dividir(suma_ultimo_anio(acumular(cat, n_ventanas, 'depth')), n_anio)
    prof_media2 = dividir(suma_ultimo_anio(acumular(cat, n_ventanas, 'depth2')), n_anio)
    energia_anio = suma_ultimo_anio(acumular(cat, n_ventanas, 'energy_joules'))
    moderados_anio = suma_ultimo_anio(acumular(cat, n_ventanas, filtro=cat['magnitude'] >= MAGNITUD_MODERADA))

    forma = (N_FILAS, N_COLUMNAS, 1)
    def estatica(columna):
        return np.broadcast_to(grilla[columna].to_numpy().reshape(forma), (N_FILAS, N_COLUMNAS, n_ventanas))

    def zona(cubo):
        return cubo[MARGEN_CELDAS:MARGEN_CELDAS + N_FILAS, MARGEN_CELDAS:MARGEN_CELDAS + N_COLUMNAS]

    variables = {
        'sismos_trimestre': n,
        'sismos_ultimo_anio': n_anio,
        'sismos_promedio_historico': np.cumsum(n, axis=2) / np.arange(1, n_ventanas + 1),
        'tendencia_sismos': n - n_anio / VENTANAS_POR_ANIO,
        'sismos_vecinos_ultimo_anio': vecinos,
        'mag_media_ultimo_anio': dividir(suma_ultimo_anio(acumular(cat, n_ventanas, 'magnitude')), n_anio),
        'mag_max_ultimo_anio': mag_max_anio,
        'log_energia_ultimo_anio': np.log10(np.maximum(energia_anio, 1.0)),
        'prop_moderados_ultimo_anio': dividir(moderados_anio, n_anio),
        'trimestres_desde_sismo_fuerte': desde_fuerte,
        'prof_media_ultimo_anio': prof_media,
        'prof_std_ultimo_anio': np.sqrt(np.maximum(prof_media2 - prof_media ** 2, 0.0)),
    }
    variables = {nombre: zona(cubo) for nombre, cubo in variables.items()}
    variables.update({nombre: estatica(nombre) for nombre in ('dist_nido_km', 'lat_center', 'lon_center')})
    return variables


def tabla_de_celdas(variables, grilla, ventana):
    """Una fila por celda con las variables al cierre del trimestre dado."""
    tabla = grilla[['cell_id']].copy()
    tabla['ventana'] = ventana
    for nombre in FEATURES:
        tabla[nombre] = variables[nombre][:, :, ventana].ravel()
    return tabla


def construir_dataset(variables, grilla, n_ventanas):
    """Muestras (celda, trimestre t) con la actividad del trimestre t+1 como objetivo."""
    muestras = []
    # Se empieza cuando ya hay un año completo de historia
    for t in range(VENTANAS_POR_ANIO - 1, n_ventanas - 1):
        tabla = tabla_de_celdas(variables, grilla, t)
        tabla['trimestre'] = etiqueta_de_ventana(t)
        tabla['trimestre_objetivo'] = etiqueta_de_ventana(t + 1)
        tabla['inicio_objetivo'] = inicio_de_ventana(t + 1)
        tabla['sismos_trimestre_siguiente'] = variables['sismos_trimestre'][:, :, t + 1].ravel()
        muestras.append(tabla)
    return pd.concat(muestras, ignore_index=True)


# ==============================================================================
# PASO 3: ETIQUETA (Y)
# ==============================================================================
def clasificar(sismos, umbrales):
    """Nivel según el número de sismos: Bajo <= umbral 1 < Medio <= umbral 2 < Alto."""
    sismos = np.asarray(sismos, dtype=float)
    return np.select([sismos > umbrales[1], sismos > umbrales[0]], ['Alto', 'Medio'], default='Bajo')


# ==============================================================================
# PASO 4: MODELOS Y EVALUACIÓN
# ==============================================================================
def pesos_de_clase(y, balanceo):
    """Peso de cada nivel: (casos / (3 * casos del nivel)) ** balanceo. Con balanceo 1 es el peso «balanced» de scikit-learn."""
    y = np.asarray(y)
    return {nivel: float((len(y) / (len(NIVELES) * max((y == nivel).sum(), 1))) ** balanceo) for nivel in NIVELES}


def crear_modelos(y=None, balanceo=1.0, profundidad=6):
    """Los dos modelos que se comparan. «y» son las etiquetas con las que se va a entrenar (para calcular los pesos)."""
    return {
        'Regresión Logística': make_pipeline(
            StandardScaler(),
            LogisticRegression(class_weight='balanced', max_iter=2000, random_state=RANDOM_STATE)),
        'Random Forest': RandomForestClassifier(
            n_estimators=300,
            max_depth=profundidad,
            min_samples_leaf=5,
            class_weight='balanced' if y is None else pesos_de_clase(y, balanceo),
            random_state=RANDOM_STATE,
            n_jobs=-1),
    }


def elegir_ajustes(train):
    """
    Elige el balanceo y la profundidad del Random Forest sin mirar el periodo de
    prueba: para cada año de validación se entrena con los años anteriores y se
    predice ese año. Gana la combinación con mejor F1 macro promedio.
    """
    anio = train['inicio_objetivo'].dt.year
    filas = []
    for balanceo in BALANCEOS:
        for profundidad in PROFUNDIDADES:
            resultados = []
            for a in ANIOS_DE_VALIDACION:
                antes, ese = train[anio < a], train[anio == a]
                modelo = crear_modelos(antes['nivel_riesgo'], balanceo, profundidad)['Random Forest']
                resultados.append(evaluar(ese['nivel_riesgo'], modelo.fit(antes[FEATURES], antes['nivel_riesgo']).predict(ese[FEATURES])))
            filas.append({'balanceo': balanceo, 'profundidad': profundidad,
                          **{clave: float(np.mean([r[clave] for r in resultados])) for clave in resultados[0]}})
    tabla = pd.DataFrame(filas).sort_values('f1_macro', ascending=False).reset_index(drop=True)
    return float(tabla.loc[0, 'balanceo']), int(tabla.loc[0, 'profundidad']), tabla


def evaluar(y_real, y_pred):
    return {
        'accuracy': float(accuracy_score(y_real, y_pred)),
        'f1_macro': float(f1_score(y_real, y_pred, average='macro', zero_division=0)),
        'recall_alto': float(recall_score(y_real, y_pred, labels=['Alto'], average='macro', zero_division=0)),
    }


def techo_del_problema(conteos, muestras, umbrales):
    """
    ¿Hasta dónde se puede acertar? Los sismos tienen un componente de azar: una
    celda con dos sismos por trimestre en promedio unas veces tendrá cero y
    otras cinco. Se simula un "oráculo" que conoce la tasa real de cada celda
    (promedio de los 9 trimestres alrededor del que se predice, incluyendo los
    posteriores) y elige el nivel más probable según la distribución de Poisson.
    Es una referencia, no un límite matemático: sirve para saber cuánto del
    error se debe al azar y cuánto podría corregir un modelo mejor.
    """
    n_ventanas = conteos.shape[2]
    filas, columnas = muestras['cell_id'] // N_COLUMNAS, muestras['cell_id'] % N_COLUMNAS
    tasas = np.array([conteos[f, c, max(0, t - 3):min(n_ventanas, t + 6)].mean()
                      for f, c, t in zip(filas, columnas, muestras['ventana'])])
    p_bajo = poisson.cdf(umbrales[0], tasas)
    p_hasta_medio = poisson.cdf(umbrales[1], tasas)
    probabilidades = np.column_stack([p_bajo, p_hasta_medio - p_bajo, 1 - p_hasta_medio])
    return np.array(NIVELES)[probabilidades.argmax(axis=1)]


def historial_de_prueba(test, prediccion, conteos, umbrales):
    """
    Lo que el modelo predijo y lo que ocurrió en cada trimestre del periodo de
    prueba, celda por celda (en el orden de cell_id). Las predicciones son las
    del modelo entrenado solo con el periodo de entrenamiento: las mismas con
    las que se calculan las métricas. Las celdas sin modelo se reportan en Bajo.
    Los niveles van como posición en NIVELES (0 Bajo, 1 Medio, 2 Alto).
    """
    test = test.assign(predicho=prediccion)
    trimestres = []
    for (ventana, etiqueta), grupo in test.groupby(['ventana', 'trimestre_objetivo'], sort=True):
        sismos = conteos[:, :, ventana + 1].ravel()
        predicho = np.full(len(sismos), 'Bajo', dtype=object)
        predicho[grupo['cell_id'].to_numpy()] = grupo['predicho'].to_numpy()
        trimestres.append({
            'trimestre': etiqueta,
            'sismos': sismos.astype(int).tolist(),
            'predicho': [NIVELES.index(nivel) for nivel in predicho],
            'real': [NIVELES.index(nivel) for nivel in clasificar(sismos, umbrales)],
        })
    return trimestres


def main():
    print("=" * 80)
    print(TITULO)
    print("=" * 80)

    # --------------------------------------------------------------------------
    print("\n1. Carga y limpieza del catálogo del SGC...")
    crudo = cargar_catalogo()
    cat = preparar_catalogo(crudo)
    n_ventanas = int(cat['ventana'].max()) + 1
    print(f"   -> Sismos en el catálogo:                 {len(crudo):,}")
    print(f"   -> Sismos M>={MAGNITUD_MINIMA} desde {ANIO_INICIO} (homogéneo):   {len(cat):,} "
          f"({int(en_la_zona(cat).sum()):,} en la zona y el resto en su margen)")
    print(f"   -> Trimestres completos: {n_ventanas} "
          f"({etiqueta_de_ventana(0)} a {etiqueta_de_ventana(n_ventanas - 1)})")

    # --------------------------------------------------------------------------
    print("\n2. Grilla e ingeniería de variables...")
    grilla = crear_grilla(cat)
    variables = calcular_variables(cat, grilla, n_ventanas)
    dataset = construir_dataset(variables, grilla, n_ventanas)

    es_prueba = dataset['inicio_objetivo'] >= FECHA_INICIO_PRUEBA
    # Zona de estudio: celdas con sismicidad registrada en el periodo de entrenamiento.
    # Las demás nunca tuvieron sismos y no necesitan modelo: su nivel es Bajo.
    actividad_train = dataset[~es_prueba].groupby('cell_id')['sismos_trimestre'].sum()
    celdas_activas = actividad_train[actividad_train > 0].index
    if CELDAS_PERMITIDAS is not None:
        celdas_activas = celdas_activas.intersection(CELDAS_PERMITIDAS)
    dataset = dataset[dataset['cell_id'].isin(celdas_activas)].reset_index(drop=True)
    es_prueba = dataset['inicio_objetivo'] >= FECHA_INICIO_PRUEBA
    print(f"   -> Celdas de {GRID_STEP}°: {len(grilla)} en la grilla, {len(celdas_activas)} con sismicidad")
    print(f"   -> Muestras (celda, trimestre): {len(dataset):,} con {len(FEATURES)} variables")

    # --------------------------------------------------------------------------
    print("\n3. Etiqueta: nivel de actividad del trimestre siguiente...")
    umbrales = UMBRALES_SISMOS
    dataset['nivel_riesgo'] = clasificar(dataset['sismos_trimestre_siguiente'], umbrales)
    print(f"   -> Bajo:  hasta {umbrales[0]:.0f} sismos M>={MAGNITUD_MINIMA} en el trimestre")
    print(f"   -> Medio: más de {umbrales[0]:.0f} y hasta {umbrales[1]:.0f}")
    print(f"   -> Alto:  más de {umbrales[1]:.0f}")

    train, test = dataset[~es_prueba], dataset[es_prueba]
    X_train, y_train = train[FEATURES], train['nivel_riesgo']
    X_test, y_test = test[FEATURES], test['nivel_riesgo']
    for nombre, parte in [('Entrenamiento', train), ('Prueba', test)]:
        conteo = parte['nivel_riesgo'].value_counts().reindex(NIVELES, fill_value=0)
        print(f"   -> {nombre:13s} {parte['trimestre_objetivo'].iloc[0]} a {parte['trimestre_objetivo'].iloc[-1]}: "
              f"{len(parte):4d} muestras  " + "  ".join(f"{n} {c}" for n, c in conteo.items()))

    # --------------------------------------------------------------------------
    print("\n4. Entrenamiento y evaluación en el periodo de prueba...")
    predicciones = {
        # Líneas base: reglas sin aprendizaje que cualquier modelo debe superar
        'Base: clase más frecuente': np.full(len(test), y_train.value_counts().idxmax()),
        'Base: igual al trimestre anterior': clasificar(test['sismos_trimestre'], umbrales),
        'Base: promedio del último año': clasificar(test['sismos_ultimo_anio'] / VENTANAS_POR_ANIO, umbrales),
    }
    balanceo, profundidad, validacion = elegir_ajustes(train)
    print(f"   -> Ajustes del Random Forest elegidos con validación interna ({ANIOS_DE_VALIDACION[0]} a {ANIOS_DE_VALIDACION[-1]}): "
          f"balanceo {balanceo}, profundidad {profundidad}")
    for fila in validacion.head(4).itertuples():
        print(f"      balanceo {fila.balanceo:4.2f}  profundidad {fila.profundidad:2d}  ->  F1 macro {fila.f1_macro:.2%}  exactitud {fila.accuracy:.2%}")
    modelos = crear_modelos(y_train, balanceo, profundidad)
    for nombre, modelo in modelos.items():
        modelo.fit(X_train, y_train)
        predicciones[nombre] = modelo.predict(X_test)
    metricas = {nombre: evaluar(y_test, pred) for nombre, pred in predicciones.items()}

    print("\n" + "=" * 80)
    print("RESULTADOS EN EL PERIODO DE PRUEBA")
    print("=" * 80)
    print(f"{'Modelo':36s} {'Accuracy':>9s} {'F1 macro':>9s} {'Recall Alto':>12s}")
    for nombre, m in metricas.items():
        print(f"{nombre:36s} {m['accuracy']:9.2%} {m['f1_macro']:9.2%} {m['recall_alto']:12.2%}")

    # El modelo final es el de mejor F1 macro: pesa por igual las tres clases
    elegido = max(modelos, key=lambda nombre: metricas[nombre]['f1_macro'])
    print(f"\n   -> Modelo elegido: {elegido}")

    techo = evaluar(y_test, techo_del_problema(variables['sismos_trimestre'], test, umbrales))
    print("\n   -> Techo de referencia (oráculo que conoce la tasa real de cada celda):")
    print(f"      Accuracy {techo['accuracy']:.2%}, F1 macro {techo['f1_macro']:.2%}")
    print(f"      El modelo alcanza el {metricas[elegido]['accuracy'] / techo['accuracy']:.0%} "
          f"de esa exactitud; el error restante es sobre todo azar de los sismos.")

    print(f"\nREPORTE DE CLASIFICACIÓN ({elegido}):")
    print(classification_report(y_test, predicciones[elegido], labels=NIVELES, digits=4, zero_division=0))
    cm = confusion_matrix(y_test, predicciones[elegido], labels=NIVELES)
    print("MATRIZ DE CONFUSIÓN (Filas: Real, Columnas: Predicho):")
    print(pd.DataFrame(cm, index=[f'Real_{n}' for n in NIVELES], columns=[f'Pred_{n}' for n in NIVELES]))

    importancias = pd.Series(
        modelos['Random Forest'].feature_importances_, index=FEATURES).sort_values(ascending=False)
    print("\nIMPORTANCIA DE LAS VARIABLES (Random Forest):")
    for puesto, (variable, valor) in enumerate(importancias.items(), 1):
        print(f"   {puesto:2d}. {variable:32s}: {valor:6.2%} {'█' * int(valor * 40)}")

    # --------------------------------------------------------------------------
    print("\n5. Modelo final con todos los datos y predicción del próximo trimestre...")
    modelo_final = crear_modelos(dataset['nivel_riesgo'], balanceo, profundidad)[elegido]
    modelo_final.fit(dataset[FEATURES], dataset['nivel_riesgo'])

    ultima = n_ventanas - 1
    actual = tabla_de_celdas(variables, grilla, ultima)
    activas = actual['cell_id'].isin(celdas_activas)
    probabilidades = modelo_final.predict_proba(actual.loc[activas, FEATURES])
    for i, nivel in enumerate(modelo_final.classes_):
        actual[f'prob_{nivel.lower()}'] = 0.0
        actual.loc[activas, f'prob_{nivel.lower()}'] = probabilidades[:, i].round(3)
    actual['riesgo_predicho'] = 'Bajo'
    actual.loc[activas, 'riesgo_predicho'] = modelo_final.predict(actual.loc[activas, FEATURES])
    actual['con_sismicidad_registrada'] = activas
    actual['trimestre_predicho'] = etiqueta_de_ventana(ultima + 1)
    grilla_riesgo = grilla.merge(
        actual.drop(columns=['ventana', 'dist_nido_km', 'lat_center', 'lon_center']), on='cell_id')

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    dataset.drop(columns=['ventana', 'inicio_objetivo']).to_csv(DATASET_CSV, index=False, encoding='utf-8')
    grilla_riesgo.to_file(GRILLA_GEOJSON, driver="GeoJSON")
    joblib.dump({
        'modelo': modelo_final,
        'nombre': elegido,
        'features': FEATURES,
        'clases': list(modelo_final.classes_),
        'umbrales_sismos': umbrales,
        'magnitud_minima': MAGNITUD_MINIMA,
        'ventana_meses': VENTANA_MESES,
        'celdas_activas': [int(c) for c in celdas_activas],
        'ajustes': {'balanceo': balanceo, 'profundidad': profundidad},
        'metricas_prueba': metricas[elegido],
        'version_sklearn': sklearn.__version__,
    }, MODELO_PKL)
    with open(METRICAS_JSON, 'w', encoding='utf-8') as f:
        json.dump({
            'modelo_elegido': elegido,
            'periodo_entrenamiento': [train['trimestre_objetivo'].iloc[0], train['trimestre_objetivo'].iloc[-1]],
            'periodo_prueba': [test['trimestre_objetivo'].iloc[0], test['trimestre_objetivo'].iloc[-1]],
            'muestras_entrenamiento': len(train),
            'muestras_prueba': len(test),
            'umbrales_sismos': umbrales,
            'ajustes': {'balanceo': balanceo, 'profundidad': profundidad,
                        'validacion_interna': validacion.round(4).to_dict('records')},
            'metricas': metricas,
            'techo_del_problema': techo,
            'matriz_confusion': {'etiquetas': NIVELES, 'valores': cm.tolist()},
            'importancia_variables': importancias.round(4).to_dict(),
        }, f, ensure_ascii=False, indent=2)

    with open(HISTORIAL_JSON, 'w', encoding='utf-8') as f:
        json.dump({
            'modelo': elegido,
            'niveles': NIVELES,
            'celdas_con_modelo': [int(c) for c in celdas_activas],
            'trimestres': historial_de_prueba(test, predicciones[elegido], variables['sismos_trimestre'], umbrales),
        }, f, ensure_ascii=False, separators=(',', ':'))

    conteo = grilla_riesgo['riesgo_predicho'].value_counts().reindex(NIVELES, fill_value=0)
    print(f"   -> Riesgo predicho para {etiqueta_de_ventana(ultima + 1)}: "
          + ", ".join(f"{c} celdas en {n}" for n, c in conteo.items()))
    print(f"   -> Dataset de entrenamiento: {DATASET_CSV}")
    print(f"   -> Grilla con el riesgo:     {GRILLA_GEOJSON}")
    print(f"   -> Modelo:                   {MODELO_PKL}")
    print(f"   -> Métricas:                 {METRICAS_JSON}")
    print(f"   -> Historial de la prueba:   {HISTORIAL_JSON}")
    print("=" * 80)
    print("PIPELINE COMPLETADO.")
    print("=" * 80)


if __name__ == "__main__":
    main()
