# ==============================================================================
# HACKATHON: UTSmart IA Challenge 2027
# PROYECTO: Gemelo Digital Sísmico de Santander - Módulo Los Santos
# SCRIPT: Exporta los modelos entrenados y sus datos a la carpeta del backend
# ==============================================================================
# El backend se despliega solo (Docker / Cloud Run) y no puede leer la carpeta
# de entrenamiento: aquí se le copia todo lo que necesita, ya en formatos
# livianos (JSON) para que la API no dependa de GeoPandas.
#
# Ejecutar después de entrenar:
#     python 1_sismos_los_santos/src/entrenar_modelo_sismico_los_santos.py
#     python comun/src/entrenar_modelo_sacudida.py
#     python comun/src/exportar_al_backend.py
# ==============================================================================

import json
import shutil
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject, transform

import simulador as sim
from catalogo import BASE_DIR, MODELS_DIR, PROCESSED_DIR, RAW_DIR, cargar_catalogo

sys.path.insert(0, str(BASE_DIR / "1_sismos_los_santos" / "src"))
sys.path.insert(0, str(BASE_DIR / "3_viviendas_y_costos" / "src"))
import preparar_danos  # noqa: E402

SANTANDER_DIR = BASE_DIR / "2_sismos_santander"
VIVIENDAS_DIR = BASE_DIR / "3_viviendas_y_costos"
from entrenar_modelo_sismico_los_santos import GRILLA_GEOJSON, HISTORIAL_JSON, METRICAS_JSON, MODELO_PKL, preparar_catalogo
import entrenar_modelo_sacudida as sacudida
from entrenar_modelo_sacudida import GRID_STEP as PASO_SIMULADOR

BACKEND_DIR = BASE_DIR.parent / "backend"
ARTEFACTOS_DIR = BACKEND_DIR / "artefactos"
LIMITES_GEOJSON = RAW_DIR / "limites_municipios_santander.geojson"
POBLACION_CSV = PROCESSED_DIR / "poblacion_santander.csv"   # lo genera preparar_poblacion.py
SISMOS_REALES = 5            # cuántos sismos reales se ofrecen para reproducir
SIN_RELIEVE = -1            # marca de los puntos que quedan fuera de la silueta
MARGEN_DE_SILUETA = 0.004   # grados (unos 450 m, el tamaño de un punto del relieve de Santander)
DECIMALES = 4   # unos 11 m: suficiente para dibujar y reduce el tamaño de los archivos


def guardar_json(nombre, contenido):
    ruta = ARTEFACTOS_DIR / nombre
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(contenido, f, ensure_ascii=False, separators=(',', ':'))
    print(f"   -> {nombre:32s} {ruta.stat().st_size / 1024:8.0f} KB")


def copiar(origen, nombre):
    shutil.copyfile(origen, ARTEFACTOS_DIR / nombre)
    print(f"   -> {nombre:32s} {Path(origen).stat().st_size / 1024:8.0f} KB")


def municipio_de_cada_celda(celdas, municipios):
    """Municipio en el que cae el centro de cada celda (o el más cercano)."""
    centros = gpd.GeoDataFrame(
        celdas[['cell_id']], geometry=gpd.points_from_xy(celdas['lon_center'], celdas['lat_center']), crs="EPSG:4326")
    # La distancia en grados basta para elegir el municipio más cercano
    cercano = gpd.sjoin_nearest(centros, municipios, how='left', distance_col='distancia')
    cercano = cercano.drop_duplicates('cell_id').set_index('cell_id')
    return cercano['municipio'].reindex(celdas['cell_id']).to_numpy(), cercano['distancia'].reindex(celdas['cell_id']).to_numpy()


def exportar_relieve(zona, silueta=None):
    """
    Convierte el modelo de elevación (UTM) de una zona en una malla regular en
    latitud y longitud: así el frontend ubica cada punto del relieve con una
    simple interpolación y sabe qué valor del modelo le corresponde.

    Si se da una silueta, los puntos que quedan fuera de ella se marcan con
    SIN_RELIEVE y el frontend no los dibuja.
    """
    # TouchTerrain nombra el archivo según la zona: se usa el .tif más reciente de la carpeta
    relieve_tif = max((RAW_DIR / f"relieve_{zona}").glob("*.tif"), key=lambda ruta: ruta.stat().st_mtime)
    print(f"   Relieve de {zona}: {relieve_tif.name}")
    with rasterio.open(relieve_tif) as dem:
        # Rectángulo en lat/lon contenido por completo dentro del ráster original
        esquinas_x = [dem.bounds.left, dem.bounds.right, dem.bounds.right, dem.bounds.left]
        esquinas_y = [dem.bounds.top, dem.bounds.top, dem.bounds.bottom, dem.bounds.bottom]
        lon, lat = transform(dem.crs, "EPSG:4326", esquinas_x, esquinas_y)
        oeste, este = max(lon[0], lon[3]), min(lon[1], lon[2])
        norte, sur = min(lat[0], lat[1]), max(lat[2], lat[3])

        filas, columnas = dem.shape
        malla = from_bounds(oeste, sur, este, norte, columnas, filas)
        elevacion = np.zeros((filas, columnas), dtype=np.float32)
        reproject(
            source=rasterio.band(dem, 1),
            destination=elevacion,
            dst_transform=malla,
            dst_crs="EPSG:4326",
            resampling=Resampling.bilinear,
        )

    # Los huecos del modelo de elevación (ríos, embalses) se dejan a nivel del mar
    elevacion = np.rint(np.maximum(elevacion, 0)).astype(int)
    dentro = np.ones(elevacion.shape, dtype=bool)
    if silueta is not None:
        dentro = geometry_mask([silueta], out_shape=elevacion.shape, transform=malla, invert=True)

    guardar_json(f"relieve_{zona}.json", {
        'fuente': 'JAXA ALOS World 3D 30 m (AW3D30 v4.1), vía TouchTerrain',
        'filas': filas,
        'columnas': columnas,
        'lon_oeste': round(oeste, 6),
        'lon_este': round(este, 6),
        'lat_sur': round(sur, 6),
        'lat_norte': round(norte, 6),
        'elevacion_min': int(elevacion[dentro].min()),
        'elevacion_max': int(elevacion[dentro].max()),
        # Metros sobre el nivel del mar, fila por fila de norte a sur
        'elevaciones': np.where(dentro, elevacion, SIN_RELIEVE).ravel().tolist(),
    })


def exportar_sismos_reales():
    """
    Los sismos del nido con más reportes de la población, con sus intensidades
    observadas, para reproducirlos en el simulador y compararlos con el modelo.

    La intensidad «del modelo» que acompaña a cada observación se calcula con
    el modelo calibrado SIN ese sismo, igual que en la validación: así el
    desvío que se muestra es el de un sismo que el modelo no había visto.
    """
    obs = sacudida.cargar_observaciones(sacudida.INTENSIDADES_CSV)
    elegido = json.loads((MODELS_DIR / "metricas_validacion.json").read_text(encoding="utf-8"))["modelo_elegido"]
    candidato = sacudida.CANDIDATOS[elegido]
    con_mas_reportes = obs.groupby('evento_id')['n_respuestas'].sum().nlargest(SISMOS_REALES).index

    sismos = []
    for evento_id in con_mas_reportes:
        suyas, resto = obs[obs['evento_id'] == evento_id], obs[obs['evento_id'] != evento_id]
        sesgo, estimador = sacudida.ajustar_candidato(candidato, resto)
        del_modelo = sacudida.predecir_candidato(candidato, sesgo, estimador, suyas)
        error = del_modelo - suyas['intensidad_cdi'].to_numpy()
        primera = suyas.iloc[0]
        sismos.append({
            'id': evento_id,
            'fecha_utc': primera['fecha_utc'],
            'magnitud': float(primera['magnitud']),
            'tipo_magnitud': primera['tipo_magnitud'],
            'profundidad_km': round(float(primera['ev_prof_km']), 1),
            'lat': round(float(primera['ev_lat']), DECIMALES),
            'lon': round(float(primera['ev_lon']), DECIMALES),
            'respuestas': int(suyas['n_respuestas'].sum()),
            'desvio': {
                'sesgo': round(float(error.mean()), 2),
                'error_absoluto_medio': round(float(np.abs(error).mean()), 2),
                'dentro_de_1_grado': round(float((np.abs(error) <= 1).mean()), 3),
            },
            'observaciones': {
                'lat': suyas['obs_lat'].round(DECIMALES).tolist(),
                'lon': suyas['obs_lon'].round(DECIMALES).tolist(),
                'intensidad': suyas['intensidad_cdi'].round(1).tolist(),
                'intensidad_del_modelo': np.round(del_modelo, 1).tolist(),
                'respuestas': suyas['n_respuestas'].astype(int).tolist(),
            },
        })
    guardar_json("sismos_reales.json", sismos)


def exportar_poblacion(municipios):
    """
    Habitantes de cada municipio (proyección del DANE) con un punto interior
    que lo representa: en ese punto se calcula la sacudida que se le atribuye
    a todo el municipio para contar las personas expuestas.
    """
    poblacion = pd.read_csv(POBLACION_CSV)
    unido = municipios.merge(poblacion, on='municipio', how='left', validate='one_to_one')
    assert unido['poblacion_total'].notna().all(), "Hay municipios del mapa sin población"
    # Viviendas de cada municipio en el mismo año (proyección del DANE), para estimar las afectadas
    anio = int(poblacion['anio'].iloc[0])
    viviendas = preparar_danos.cargar_viviendas()
    viviendas = viviendas[viviendas['anio'] == anio].assign(codigo_dane=lambda v: v['codigo_dane'].astype(int))
    unido = unido.merge(viviendas[['codigo_dane', 'viviendas']], on='codigo_dane', how='left', validate='one_to_one')
    assert unido['viviendas'].notna().all(), "Hay municipios sin viviendas del DANE"
    puntos = unido.geometry.representative_point()
    guardar_json("poblacion.json", {
        'fuente': 'DANE, proyecciones de población municipal con base en el censo de 2018',
        'anio': int(poblacion['anio'].iloc[0]),
        'municipio': unido['municipio'].tolist(),
        'habitantes': unido['poblacion_total'].astype(int).tolist(),
        'viviendas': unido['viviendas'].astype(int).tolist(),
        'lat': puntos.y.round(DECIMALES).tolist(),
        'lon': puntos.x.round(DECIMALES).tolist(),
    })


def main():
    ARTEFACTOS_DIR.mkdir(parents=True, exist_ok=True)
    municipios = gpd.read_file(LIMITES_GEOJSON)
    print(f"Exportando a {ARTEFACTOS_DIR}")

    # Modelos y métricas
    copiar(MODELO_PKL, "modelo_riesgo.pkl")
    copiar(sim.MODELO_PKL, "modelo_sacudida.pkl")
    copiar(METRICAS_JSON, "metricas_clasificador.json")
    copiar(HISTORIAL_JSON, "historial_riesgo.json")
    copiar(MODELS_DIR / "metricas_validacion.json", "metricas_sacudida.json")

    # Grilla del clasificador, con el municipio de cada celda
    riesgo = gpd.read_file(GRILLA_GEOJSON)
    riesgo['municipio'], distancia = municipio_de_cada_celda(riesgo, municipios)
    riesgo['en_el_departamento'] = distancia == 0
    guardar_json("grilla_riesgo.geojson", json.loads(riesgo.to_json(drop_id=True)))

    # Modelo 2: el mismo clasificador para todo Santander. La grilla es el rectángulo completo
    # (para pintarla como mapa de calor); las celdas de fuera del departamento se marcan
    copiar(SANTANDER_DIR / "models" / "modelo_riesgo_sismico_santander.pkl", "modelo_riesgo_santander.pkl")
    copiar(SANTANDER_DIR / "models" / "metricas_clasificador_santander.json", "metricas_clasificador_santander.json")
    copiar(SANTANDER_DIR / "models" / "historial_prueba_santander.json", "historial_riesgo_santander.json")
    riesgo = gpd.read_file(SANTANDER_DIR / "data" / "processed" / "grilla_riesgo_santander.geojson")
    riesgo['municipio'], distancia = municipio_de_cada_celda(riesgo, municipios)
    riesgo['en_el_departamento'] = distancia == 0
    riesgo['geometry'] = riesgo.geometry.set_precision(10 ** -DECIMALES)
    for columna in riesgo.select_dtypes('float').columns:
        riesgo[columna] = riesgo[columna].round(3)
    guardar_json("grilla_riesgo_santander.geojson", json.loads(riesgo.to_json(drop_id=True)))

    # Modelo 3: viviendas afectadas y costo. El backend usa el mismo módulo que el entrenamiento
    copiar(VIVIENDAS_DIR / "models" / "modelo_viviendas_afectadas.pkl", "modelo_viviendas.pkl")
    copiar(VIVIENDAS_DIR / "models" / "metricas_viviendas.json", "metricas_viviendas.json")
    shutil.copyfile(VIVIENDAS_DIR / "src" / "modelo_de_danos.py", BACKEND_DIR / "app" / "modelo_de_danos.py")

    # Grilla del simulador: solo las celdas cuyo centro está en Santander
    santander = gpd.read_file(sim.GRILLA_GEOJSON)
    santander['municipio'], distancia = municipio_de_cada_celda(santander, municipios)
    santander = santander[distancia == 0]
    guardar_json("grilla_simulador.json", {
        'paso': PASO_SIMULADOR,
        'lat': santander['lat_center'].round(DECIMALES).tolist(),
        'lon': santander['lon_center'].round(DECIMALES).tolist(),
        'vs30': santander['vs30'].tolist(),
        'municipio': santander['municipio'].tolist(),
    })

    # Límites municipales con menos decimales
    limites = municipios.copy()
    limites['geometry'] = limites.geometry.set_precision(10 ** -DECIMALES)
    guardar_json("municipios.geojson", json.loads(limites.to_json(drop_id=True)))

    # Hipocentros del catálogo homogéneo, para la vista 3D del nido
    cat = preparar_catalogo(cargar_catalogo())
    guardar_json("sismos.json", {
        'lon': cat['longitude'].round(DECIMALES).tolist(),
        'lat': cat['latitude'].round(DECIMALES).tolist(),
        'profundidad_km': cat['depth'].round(0).astype(int).tolist(),
        'magnitud': cat['magnitude'].round(1).tolist(),
        'anio': cat['utc_time'].dt.year.tolist(),
    })

    exportar_sismos_reales()
    exportar_poblacion(municipios)

    # Relieve fino de la zona del modelo y relieve de todo el departamento, recortado
    # con su silueta (con un pequeño margen para no dejar huecos en el borde)
    exportar_relieve("los_santos")
    exportar_relieve("santander", silueta=municipios.union_all().buffer(MARGEN_DE_SILUETA))
    relieve_antiguo = ARTEFACTOS_DIR / "relieve.json"
    if relieve_antiguo.exists():
        relieve_antiguo.unlink()

    # El motor del simulador es el mismo archivo que usa el entrenamiento
    shutil.copyfile(Path(sim.__file__), BACKEND_DIR / "app" / "simulador.py")
    print("   -> app/simulador.py (copia del motor de simulación)")
    print(f"Celdas del simulador dentro de Santander: {len(santander)}")


if __name__ == "__main__":
    main()
