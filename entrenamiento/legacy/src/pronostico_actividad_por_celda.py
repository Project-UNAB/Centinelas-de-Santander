# ==============================================================================
# HACKATHON: UTSmart IA Challenge 2027
# PROYECTO: Gemelo Digital Sísmico de Santander - Módulo Los Santos
# SCRIPT: Entrenamiento de Modelo de Clasificación de Riesgo Sísmico Supervisado
# AUTOR: Equipo Data Science & Geoprocesamiento
# PYTHON: 3.11+
# ==============================================================================

import os
import sys
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    accuracy_score,
    recall_score,
    f1_score,
    confusion_matrix,
    classification_report
)
import matplotlib.pyplot as plt
import seaborn as sns

# Configuración visual
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')

print("=" * 80)
print("🚀 INICIANDO PIPELINE DE MACHINE LEARNING: RIESGO SÍSMICO EN LOS SANTOS")
print("=" * 80)

# ==============================================================================
# PASO 1: CARGA Y LIMPIEZA DE DATOS
# ==============================================================================
# Rutas relativas a la raíz del proyecto (funciona desde cualquier directorio)
BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed" / "legacy"
MODELS_DIR = BASE_DIR / "models" / "legacy"

# Ruta al archivo GeoJSON oficial
GEOJSON_PATH = RAW_DIR / "Los_santos - 01-01-2006 - 12-10-2026.geojson"

print(f"\n📂 1. Cargando catálogo sísmico desde: {GEOJSON_PATH}")
gdf_raw = gpd.read_file(GEOJSON_PATH)
print(f"   -> Total de sismos cargados: {len(gdf_raw):,}")

# Convertir tipos de datos y parsear fechas
print("   -> Limpiando y convirtiendo tipos de datos...")
numeric_cols = [
    'magnitude', 'magnitude_error', 'depth', 'depth_error',
    'latitude', 'latitude_error', 'longitude', 'longitude_error',
    'rms', 'gap', 'nst'
]

for col in numeric_cols:
    if col in gdf_raw.columns:
        gdf_raw[col] = pd.to_numeric(gdf_raw[col], errors='coerce').fillna(0.0)

# Parseo de fechas UTC y local
gdf_raw['local_time'] = pd.to_datetime(gdf_raw['local_time'], errors='coerce')
gdf_raw['year'] = gdf_raw['local_time'].dt.year

# Filtro de sanidad básica
gdf_clean = gdf_raw.dropna(subset=['latitude', 'longitude', 'magnitude', 'depth']).copy()

# Cálculo de energía sísmica liberada por fórmula de Gutenberg-Richter:
# log10(E) = 4.8 + 1.5 * M  =>  E (Joules) = 10^(4.8 + 1.5 * M)
gdf_clean['energy_joules'] = 10 ** (4.8 + 1.5 * gdf_clean['magnitude'])

min_year, max_year = gdf_clean['year'].min(), gdf_clean['year'].max()
n_years = max_year - min_year + 1
print(f"   -> Rango temporal: {min_year} a {max_year} ({n_years} años)")
print(f"   -> Magnitud mín/máx: {gdf_clean['magnitude'].min()} / {gdf_clean['magnitude'].max()}")
print(f"   -> Profundidad promedio: {gdf_clean['depth'].mean():.2f} km")

# ==============================================================================
# PASO 2: CREACIÓN DE LA GRILLA ESPACIAL (0.05° x 0.05°)
# ==============================================================================
print("\n🗺️ 2. Creando grilla espacial sobre el área de Los Santos...")

# Bounding Box focalizado en la zona sísmica de Los Santos
LAT_MIN, LAT_MAX = 6.70, 6.95
LON_MIN, LON_MAX = -73.25, -72.95
GRID_STEP = 0.05

lat_bins = np.arange(LAT_MIN, LAT_MAX + GRID_STEP, GRID_STEP)
lon_bins = np.arange(LON_MIN, LON_MAX + GRID_STEP, GRID_STEP)
n_lon_bins = len(lon_bins) - 1

# Generación de geometrías Poligonales para cada celda
grid_cells = []
for i in range(len(lat_bins) - 1):
    for j in range(len(lon_bins) - 1):
        cell_id = i * n_lon_bins + j
        c_lat_min, c_lat_max = lat_bins[i], lat_bins[i+1]
        c_lon_min, c_lon_max = lon_bins[j], lon_bins[j+1]
        c_lat_center = (c_lat_min + c_lat_max) / 2.0
        c_lon_center = (c_lon_min + c_lon_max) / 2.0
        
        poly = Polygon([
            (c_lon_min, c_lat_min),
            (c_lon_max, c_lat_min),
            (c_lon_max, c_lat_max),
            (c_lon_min, c_lat_max)
        ])
        
        grid_cells.append({
            'cell_id': cell_id,
            'lat_min': c_lat_min,
            'lat_max': c_lat_max,
            'lon_min': c_lon_min,
            'lon_max': c_lon_max,
            'lat_center': c_lat_center,
            'lon_center': c_lon_center,
            'geometry': poly
        })

gdf_grid = gpd.GeoDataFrame(grid_cells, crs="EPSG:4326")
print(f"   -> Grilla construida con {len(gdf_grid)} celdas de {GRID_STEP}° x {GRID_STEP}°")

# Indexación espacial rápida de los sismos a cada celda
gdf_clean['lat_idx'] = np.digitize(gdf_clean['latitude'], lat_bins) - 1
gdf_clean['lon_idx'] = np.digitize(gdf_clean['longitude'], lon_bins) - 1
gdf_clean['cell_id'] = gdf_clean['lat_idx'] * n_lon_bins + gdf_clean['lon_idx']

# Conservar solo sismos dentro de la grilla
mask_in_grid = gdf_clean['cell_id'].isin(gdf_grid['cell_id'])
gdf_sismos_grid = gdf_clean[mask_in_grid].copy()
print(f"   -> Sismos asignados exitosamente a celdas: {len(gdf_sismos_grid):,}")

# ==============================================================================
# PASO 3: INGENIERÍA DE VARIABLES (FEATURE ENGINEERING)
# ==============================================================================
print("\n⚙️ 3. Calculando variables geofísicas avanzadas...")

# Epicentro de referencia del Nido Sísmico de Bucaramanga
NIDO_LAT = 6.80
NIDO_LON = -73.10

# Añadir distancia al Nido en la grilla (1° ~ 111.12 km)
gdf_grid['dist_nido_km'] = np.sqrt(
    ((gdf_grid['lat_center'] - NIDO_LAT) * 111.12)**2 + 
    ((gdf_grid['lon_center'] - NIDO_LON) * 111.12)**2
)

# ------------------------------------------------------------------------------
# ENFOQUE PREDICTIVO SENIOR (Sin Data Leakage):
# Para que el modelo realmente "prediga" y no memorice una regla tautológica:
# Calculamos las variables en ventanas anuales 't' y predecimos el riesgo en 't+1'.
# Esto genera un dataset supervisado robusto de forecasting territorial.
# ------------------------------------------------------------------------------
years_list = sorted(gdf_sismos_grid['year'].unique())
samples_list = []

for cid, cell_row in gdf_grid.iterrows():
    c_id = cell_row['cell_id']
    dist_nido = cell_row['dist_nido_km']
    cell_sismos_all = gdf_sismos_grid[gdf_sismos_grid['cell_id'] == c_id]
    
    for y in years_list[:-1]:  # Hasta el penúltimo año
        # Datos del año actual (t)
        sismos_t = cell_sismos_all[cell_sismos_all['year'] == y]
        # Actividad del año siguiente (t + 1) -> ETIQUETA FUTURA
        sismos_next = cell_sismos_all[cell_sismos_all['year'] == (y + 1)]
        cnt_next = len(sismos_next)
        
        cnt_t = len(sismos_t)
        deep_t = sismos_t[sismos_t['depth'] > 100]
        shallow_t = sismos_t[sismos_t['depth'] < 40]
        
        # a) Tasa de sismos profundos (>100 km)
        tasa_profunda = len(deep_t)
        # b) Magnitud media de sismos profundos
        mag_media_prof = deep_t['magnitude'].mean() if len(deep_t) > 0 else 0.0
        # c) Log10 Energía acumulada profunda
        energia_prof = deep_t['energy_joules'].sum() if len(deep_t) > 0 else 0.0
        log_energia_prof = np.log10(energia_prof) if energia_prof > 0 else 0.0
        # d) Tasa de sismos someros (<40 km)
        tasa_somera = len(shallow_t)
        # e) Magnitud máxima somera
        mag_max_somera = shallow_t['magnitude'].max() if len(shallow_t) > 0 else 0.0
        # f) Proporción de sismos M >= 4
        prop_m4 = (sismos_t['magnitude'] >= 4.0).mean() if cnt_t > 0 else 0.0
        # g) Profundidad media y mínima
        prof_media = sismos_t['depth'].mean() if cnt_t > 0 else 0.0
        prof_min = sismos_t['depth'].min() if cnt_t > 0 else 0.0
        # h) Desviación estándar de magnitud
        std_mag = sismos_t['magnitude'].std() if cnt_t > 1 else 0.0
        std_mag = 0.0 if np.isnan(std_mag) else std_mag
        # i) Distancia al Nido de Bucaramanga
        # (ya calculada como dist_nido)
        # j) Frecuencia total del año
        frec_total = cnt_t
        # k) Magnitud máxima del año
        mag_max_anual = sismos_t['magnitude'].max() if cnt_t > 0 else 0.0
        
        samples_list.append({
            'cell_id': c_id,
            'year': y,
            'lat_center': cell_row['lat_center'],
            'lon_center': cell_row['lon_center'],
            'dist_nido_km': dist_nido,
            'frecuencia_total_t': frec_total,
            'tasa_anual_profunda': tasa_profunda,
            'mag_media_profunda': mag_media_prof,
            'log_energia_profunda': log_energia_prof,
            'tasa_anual_somera': tasa_somera,
            'mag_max_somera': mag_max_somera,
            'prop_m_mayor_4': prop_m4,
            'profundidad_media': prof_media,
            'profundidad_minima': prof_min,
            'std_magnitud': std_mag,
            'magnitud_maxima_t': mag_max_anual,
            # Variable objetivo pura
            'target_next_activity': cnt_next
        })

df_ml = pd.DataFrame(samples_list)
print(f"   -> Muestras temporales construidas para entrenamiento: {len(df_ml)}")

# ==============================================================================
# PASO 4: GENERACIÓN DE LA ETIQUETA (Y)
# ==============================================================================
print("\n🏷️ 4. Generación fundamentada de la Etiqueta (Y: Nivel de Riesgo)...")

# ------------------------------------------------------------------------------
# JUSTIFICACIÓN METODOLÓGICA DE LA ETIQUETA:
# 1. En sismología y gestión del riesgo, el riesgo es probabilístico y continuo.
# 2. Las celdas sin actividad futura (0 sismos en t+1) son naturalmente "Bajo".
# 3. Para las celdas con actividad sísmica real, usamos la mediana/percentiles
#    de los eventos activos para dividir equitativamente en "Medio" y "Alto".
# 4. Esto evita sesgos arbitrarios ("reglas fijas inventadas") y garantiza que
#    las tres clases representen niveles objetivos de exposición territorial.
# ------------------------------------------------------------------------------
active_counts = df_ml[df_ml['target_next_activity'] > 0]['target_next_activity']
p50_active = active_counts.median()

def clasificar_riesgo(actividad):
    if actividad == 0:
        return 'Bajo'
    elif actividad <= p50_active:
        return 'Medio'
    else:
        return 'Alto'

df_ml['nivel_riesgo'] = df_ml['target_next_activity'].apply(clasificar_riesgo)

print("   -> Umbrales de actividad futura:")
print(f"      - Bajo:  0 sismos en t+1")
print(f"      - Medio: 1 a {int(p50_active)} sismos en t+1")
print(f"      - Alto:  > {int(p50_active)} sismos en t+1")
print("\n   -> Distribución de clases generada:")
for cls_name, count in df_ml['nivel_riesgo'].value_counts().items():
    print(f"      [{cls_name:5s}]: {count:4d} muestras ({count/len(df_ml):.1%})")

# ==============================================================================
# PASO 5: ENTRENAMIENTO DEL MODELO Y EVALUACIÓN
# ==============================================================================
print("\n🤖 5. Entrenamiento y Validación de Modelos...")

# Lista de las 11 características geofísicas (sin data leakage del target)
FEATURES = [
    'tasa_anual_profunda',
    'mag_media_profunda',
    'log_energia_profunda',
    'tasa_anual_somera',
    'mag_max_somera',
    'prop_m_mayor_4',
    'profundidad_media',
    'profundidad_minima',
    'std_magnitud',
    'dist_nido_km',
    'magnitud_maxima_t'
]

X = df_ml[FEATURES]
y = df_ml['nivel_riesgo']

# División Estratificada 80% Train / 20% Test
X_train, X_test, y_train, y_test = train_test_split(
    X, y,
    test_size=0.20,
    random_state=42,
    stratify=y
)

print(f"   -> Muestras de entrenamiento: {len(X_train)}")
print(f"   -> Muestras de prueba:        {len(X_test)}")

# 1. MODELO BASE (BASELINE): Regresión Logística
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

lr_model = LogisticRegression(
    class_weight='balanced',
    max_iter=1000,
    random_state=42
)
lr_model.fit(X_train_scaled, y_train)
y_pred_lr = lr_model.predict(X_test_scaled)

# 2. MODELO PRINCIPAL: Random Forest Classifier
rf_model = RandomForestClassifier(
    n_estimators=150,
    max_depth=7,
    min_samples_split=4,
    class_weight='balanced',
    random_state=42
)
rf_model.fit(X_train, y_train)
y_pred_rf = rf_model.predict(X_test)

# Evaluaciones
acc_lr = accuracy_score(y_test, y_pred_lr)
acc_rf = accuracy_score(y_test, y_pred_rf)
recall_alto_rf = recall_score(y_test, y_pred_rf, labels=['Alto'], average='macro')
f1_macro_rf = f1_score(y_test, y_pred_rf, average='macro')

print("\n" + "=" * 80)
print("📊 RESULTADOS COMPARATIVOS DE EVALUACIÓN")
print("=" * 80)
print(f"1. BASELINE (Regresión Logística):  Accuracy = {acc_lr:.2%}")
print(f"2. RANDOM FOREST (Modelo Principal): Accuracy = {acc_rf:.2%}")
print(f"   -> RECALL Clase 'Alto':            {recall_alto_rf:.2%}  <-- [MÉTRICA CLAVE]")
print(f"   -> F1-Score Macro:                 {f1_macro_rf:.2%}")

print("\n📋 REPORTE DE CLASIFICACIÓN DETALLADO (RANDOM FOREST):")
print(classification_report(y_test, y_pred_rf, digits=4))

cm = confusion_matrix(y_test, y_pred_rf, labels=['Bajo', 'Medio', 'Alto'])
print("🔍 MATRIZ DE CONFUSIÓN (Filas: Real, Columnas: Predicho):")
cm_df = pd.DataFrame(cm, index=['Real_Bajo', 'Real_Medio', 'Real_Alto'], columns=['Pred_Bajo', 'Pred_Medio', 'Pred_Alto'])
print(cm_df)

print("\n🌟 IMPORTANCIA DE LAS VARIABLES (FEATURE IMPORTANCE):")
importances = pd.Series(rf_model.feature_importances_, index=FEATURES).sort_values(ascending=False)
for rank, (feat, imp) in enumerate(importances.items(), 1):
    bar = "█" * int(imp * 40)
    print(f"   {rank:2d}. {feat:25s}: {imp:6.2%} {bar}")

# ==============================================================================
# PASO 6: GUARDADO DE ARTEFACTOS PARA LA DEMO STREAMLIT
# ==============================================================================
print("\n💾 6. Exportando modelo y metadatos para la demo Streamlit...")

# Crear consolidado estático promedio por celda para cargar rápido en PyDeck/Streamlit
cell_summary = []
for cid, cell_row in gdf_grid.iterrows():
    c_sismos = gdf_sismos_grid[gdf_sismos_grid['cell_id'] == cid]
    cnt = len(c_sismos)
    deep = c_sismos[c_sismos['depth'] > 100]
    shallow = c_sismos[c_sismos['depth'] < 40]
    
    cell_summary.append({
        'cell_id': cid,
        'lat_center': cell_row['lat_center'],
        'lon_center': cell_row['lon_center'],
        'dist_nido_km': cell_row['dist_nido_km'],
        'total_sismos_historico': cnt,
        'tasa_anual_profunda': len(deep) / n_years,
        'mag_media_profunda': deep['magnitude'].mean() if len(deep) > 0 else 0.0,
        'log_energia_profunda': np.log10(deep['energy_joules'].sum()) if len(deep) > 0 and deep['energy_joules'].sum() > 0 else 0.0,
        'tasa_anual_somera': len(shallow) / n_years,
        'mag_max_somera': shallow['magnitude'].max() if len(shallow) > 0 else 0.0,
        'prop_m_mayor_4': (c_sismos['magnitude'] >= 4.0).mean() if cnt > 0 else 0.0,
        'profundidad_media': c_sismos['depth'].mean() if cnt > 0 else 0.0,
        'profundidad_minima': c_sismos['depth'].min() if cnt > 0 else 0.0,
        'std_magnitud': c_sismos['magnitude'].std() if cnt > 1 else 0.0,
        'magnitud_maxima_t': c_sismos['magnitude'].max() if cnt > 0 else 0.0,
        'geometry': cell_row['geometry']
    })

gdf_summary = gpd.GeoDataFrame(cell_summary, crs="EPSG:4326")
# Predicción estática del modelo sobre la grilla consolidada
X_grid = gdf_summary[FEATURES].fillna(0.0)
gdf_summary['riesgo_predicho'] = rf_model.predict(X_grid)

# Guardar archivos
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)
MODEL_OUTPUT_PKL = MODELS_DIR / "modelo_riesgo_sismico_los_santos.pkl"
GRID_OUTPUT_GEOJSON = PROCESSED_DIR / "grilla_riesgo_los_santos.geojson"
METADATA_PKL = MODELS_DIR / "metadata_gemelo_digital.pkl"

joblib.dump(rf_model, MODEL_OUTPUT_PKL)
gdf_summary.to_file(GRID_OUTPUT_GEOJSON, driver="GeoJSON")

metadata = {
    'features': FEATURES,
    'classes': list(rf_model.classes_),
    'accuracy': acc_rf,
    'recall_alto': recall_alto_rf,
    'n_cells': len(gdf_summary),
    'grid_step': GRID_STEP,
    'bbox': [LAT_MIN, LAT_MAX, LON_MIN, LON_MAX]
}
joblib.dump(metadata, METADATA_PKL)

print(f"   -> ✅ Modelo entrenado guardado en:      {MODEL_OUTPUT_PKL}")
print(f"   -> ✅ Grilla con geometrías guardada en: {GRID_OUTPUT_GEOJSON}")
print(f"   -> ✅ Metadatos guardados en:             {METADATA_PKL}")
print("=" * 80)
print("🎯 PIPELINE COMPLETADO EXITOSAMENTE. LISTO PARA LA DEMO EN STREAMLIT.")
print("=" * 80)
