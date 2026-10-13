# ==============================================================================
# HACKATHON: UTSmart IA Challenge 2027
# PROYECTO: Gemelo Digital Sísmico de Santander - Módulo Los Santos
# MÓDULO: Carga y limpieza del catálogo sísmico del SGC
# ==============================================================================

import json
from pathlib import Path

import pandas as pd

# entrenamiento/: los datos originales son comunes a todos los modelos
BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data" / "raw"
# entrenamiento/comun/: datos limpios y modelos que usan varios modelos o la aplicación.
# Cada modelo guarda lo suyo en su propia carpeta (1_sismos_los_santos, 2_sismos_santander, 3_viviendas_y_costos)
COMUN_DIR = Path(__file__).resolve().parents[1]
PROCESSED_DIR = COMUN_DIR / "data" / "processed"
MODELS_DIR = COMUN_DIR / "models"

# Catálogo del SGC para todo el departamento: con él se entrena el clasificador. El de solo
# Los Santos dejaba fuera los sismos del nido que el SGC asigna a los municipios vecinos.
CATALOGO_SANTANDER_CSV = RAW_DIR / "Santander - 01-01-2006 - 13-10-2026.csv"
# Catálogo filtrado por el municipio de Los Santos: lo sigue usando el modelo de sacudida
CATALOGO_GEOJSON = RAW_DIR / "Los_santos - 01-01-2006 - 12-10-2026.geojson"

COLUMNAS_NUMERICAS = [
    'magnitude', 'magnitude_error', 'depth', 'depth_error',
    'latitude', 'latitude_error', 'longitude', 'longitude_error',
    'rms', 'gap', 'nst',
]
COLUMNAS_ESENCIALES = ['magnitude', 'depth', 'latitude', 'longitude', 'utc_time']


def leer_catalogo_crudo(ruta=CATALOGO_SANTANDER_CSV):
    """Catálogo tal como viene en el archivo (CSV o GeoJSON del SGC): todos los campos se leen como texto."""
    if Path(ruta).suffix == '.geojson':
        with open(ruta, encoding='utf-8') as f:
            features = json.load(f)['features']
        return pd.DataFrame([ft['properties'] for ft in features])
    return pd.read_csv(ruta, dtype=str, keep_default_na=False, encoding='utf-8-sig')


def cargar_catalogo(ruta=CATALOGO_SANTANDER_CSV):
    """
    Catálogo limpio: tipos numéricos, fechas en UTC y energía liberada.
    Los faltantes vienen como cadenas vacías y se dejan como NaN (no como
    ceros); solo se descartan las filas sin magnitud, ubicación o fecha.
    """
    cat = leer_catalogo_crudo(ruta)
    for col in COLUMNAS_NUMERICAS:
        cat[col] = pd.to_numeric(cat[col], errors='coerce')
    cat['utc_time'] = pd.to_datetime(cat['utc_time'], errors='coerce', utc=True)
    cat = cat.dropna(subset=COLUMNAS_ESENCIALES).drop_duplicates(subset='id')

    # Energía sísmica liberada (Gutenberg-Richter): log10(E) = 4.8 + 1.5 * M
    cat['energy_joules'] = 10 ** (4.8 + 1.5 * cat['magnitude'])
    return cat.sort_values('utc_time').reset_index(drop=True)


CATALOGO_LIMPIO_CSV = PROCESSED_DIR / "catalogo_limpio_santander.csv"


def guardar_catalogo_limpio(cat, ruta=CATALOGO_LIMPIO_CSV):
    """Deja en disco el catálogo ya limpio, junto al original de data/raw, que no se modifica."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    cat.to_csv(ruta, index=False, encoding='utf-8')
    return ruta
