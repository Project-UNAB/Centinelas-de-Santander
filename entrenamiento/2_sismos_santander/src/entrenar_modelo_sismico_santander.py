# ==============================================================================
# HACKATHON: UTSmart IA Challenge 2027 - Categoría Básica
# PROYECTO: Gemelo Digital Sísmico de Santander
# SCRIPT: Clasificador de riesgo sísmico por zona para todo Santander
# ==============================================================================
# Es el mismo clasificador de Los Santos (mismas variables, misma etiqueta y
# misma validación), aplicado a una grilla que cubre todo el departamento. Va
# aparte porque un solo modelo para las dos zonas predice peor en Los Santos:
# fuera del nido casi todas las celdas están vacías y se comportan distinto.
#
# Uso:  python 2_sismos_santander/src/entrenar_modelo_sismico_santander.py --solo-datos   (prepara y guarda el conjunto de datos)
#       python 2_sismos_santander/src/entrenar_modelo_sismico_santander.py                (además entrena y evalúa)
# ==============================================================================

import sys
from pathlib import Path

import geopandas as gpd

# Carpeta de este modelo; el código compartido (catálogo, simulador) está en entrenamiento/comun
CARPETA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CARPETA.parent / "comun" / "src"))
# El clasificador es el de Los Santos: aquí solo cambian la grilla y los archivos
sys.path.insert(0, str(CARPETA.parent / "1_sismos_los_santos" / "src"))
import entrenar_modelo_sismico_los_santos as clasificador  # noqa: E402
from catalogo import RAW_DIR, cargar_catalogo  # noqa: E402

PROCESSED_DIR = CARPETA / "data" / "processed"
MODELS_DIR = CARPETA / "models"

LIMITES_GEOJSON = RAW_DIR / "limites_municipios_santander.geojson"

# Grilla sobre el rectángulo que contiene a Santander, alineada con la de Los Santos
LAT_MIN, LON_MIN = 5.70, -74.55
N_FILAS, N_COLUMNAS = 49, 43


def configurar():
    """Apunta el clasificador a la grilla y a los archivos de Santander."""
    clasificador.LAT_MIN, clasificador.LON_MIN = LAT_MIN, LON_MIN
    clasificador.N_FILAS, clasificador.N_COLUMNAS = N_FILAS, N_COLUMNAS
    clasificador.TITULO = "CLASIFICADOR DE RIESGO SÍSMICO POR ZONA - TODO SANTANDER"
    clasificador.DATASET_CSV = PROCESSED_DIR / "dataset_entrenamiento_santander.csv"
    clasificador.GRILLA_GEOJSON = PROCESSED_DIR / "grilla_riesgo_santander.geojson"
    clasificador.MODELO_PKL = MODELS_DIR / "modelo_riesgo_sismico_santander.pkl"
    clasificador.METRICAS_JSON = MODELS_DIR / "metricas_clasificador_santander.json"
    clasificador.HISTORIAL_JSON = MODELS_DIR / "historial_prueba_santander.json"

    # Solo las celdas cuyo centro cae dentro del departamento
    cat = clasificador.preparar_catalogo(cargar_catalogo())
    grilla = clasificador.crear_grilla(cat)
    santander = gpd.read_file(LIMITES_GEOJSON).union_all()
    centros = gpd.points_from_xy(grilla['lon_center'], grilla['lat_center'])
    clasificador.CELDAS_PERMITIDAS = grilla.loc[[santander.contains(p) for p in centros], 'cell_id']
    return cat, grilla


def preparar_datos(cat, grilla):
    """Construye y guarda el conjunto de datos, sin entrenar."""
    n_ventanas = int(cat['ventana'].max()) + 1
    variables = clasificador.calcular_variables(cat, grilla, n_ventanas)
    dataset = clasificador.construir_dataset(variables, grilla, n_ventanas)
    es_prueba = dataset['inicio_objetivo'] >= clasificador.FECHA_INICIO_PRUEBA
    actividad = dataset[~es_prueba].groupby('cell_id')['sismos_trimestre'].sum()
    activas = actividad[actividad > 0].index.intersection(clasificador.CELDAS_PERMITIDAS)
    dataset = dataset[dataset['cell_id'].isin(activas)].reset_index(drop=True)
    es_prueba = dataset['inicio_objetivo'] >= clasificador.FECHA_INICIO_PRUEBA
    dataset['nivel_riesgo'] = clasificador.clasificar(dataset['sismos_trimestre_siguiente'], clasificador.UMBRALES_SISMOS)
    dataset.drop(columns=['ventana', 'inicio_objetivo']).to_csv(clasificador.DATASET_CSV, index=False, encoding='utf-8')

    print(clasificador.TITULO + " · solo datos")
    print(f"   -> Sismos M>={clasificador.MAGNITUD_MINIMA} desde {clasificador.ANIO_INICIO}: {len(cat):,}")
    print(f"   -> Celdas en el rectángulo: {len(grilla):,}   Dentro de Santander: {len(clasificador.CELDAS_PERMITIDAS):,}"
          f"   Con sismos en el entrenamiento: {len(activas)}")
    print(f"   -> Casos (celda, trimestre): {len(dataset):,} con {len(clasificador.FEATURES)} variables")
    for nombre, parte in (('Entrenamiento', dataset[~es_prueba]), ('Prueba', dataset[es_prueba])):
        conteo = parte['nivel_riesgo'].value_counts().reindex(clasificador.NIVELES, fill_value=0)
        print(f"   -> {nombre:13s} {len(parte):6,} casos  " + "  ".join(f"{n} {c:,} ({c / len(parte):.0%})" for n, c in conteo.items()))
    print(f"   -> Conjunto de datos: {clasificador.DATASET_CSV}")


if __name__ == "__main__":
    catalogo_homogeneo, grilla_de_santander = configurar()
    if "--solo-datos" in sys.argv:
        preparar_datos(catalogo_homogeneo, grilla_de_santander)
    else:
        clasificador.main()
