"""Carga de modelos y datos. Cada recurso se lee una sola vez y queda en memoria."""

import json
from functools import lru_cache

import joblib
import numpy as np

from .config import ARTEFACTOS_DIR, LIMITES_DE_LOS_SANTOS, PASO_DE_MALLA_FINA, ZONAS, ZONAS_DE_RIESGO


def _leer_json(nombre):
    with open(ARTEFACTOS_DIR / nombre, encoding="utf-8") as f:
        return json.load(f)


@lru_cache
def modelo_riesgo(zona="los_santos"):
    """Clasificador de riesgo por zona: modelo, variables, clases y umbrales."""
    return joblib.load(ARTEFACTOS_DIR / f"modelo_riesgo{ZONAS_DE_RIESGO[zona]}.pkl")


@lru_cache
def modelo_viviendas():
    """Modelo de viviendas afectadas por un sismo y costo de atención por vivienda."""
    return joblib.load(ARTEFACTOS_DIR / "modelo_viviendas.pkl")


@lru_cache
def metricas_viviendas():
    return _leer_json("metricas_viviendas.json")


@lru_cache
def modelo_sacudida():
    """Modelo de sacudida que usa el simulador de escenarios."""
    return joblib.load(ARTEFACTOS_DIR / "modelo_sacudida.pkl")


@lru_cache
def grilla_riesgo(zona="los_santos"):
    return _leer_json(f"grilla_riesgo{ZONAS_DE_RIESGO[zona]}.geojson")


@lru_cache
def grilla_simulador():
    grilla = _leer_json("grilla_simulador.json")
    for columna in ("lat", "lon", "vs30"):
        grilla[columna] = np.asarray(grilla[columna], dtype=float)
    return grilla


@lru_cache
def municipios():
    return _leer_json("municipios.geojson")


@lru_cache
def sismos():
    """Sismos de Los Santos y su margen: con ellos se genera el catálogo sintético."""
    return _leer_json("sismos.json")


@lru_cache
def sismos_de_zona(zona):
    """Sismos reales que se dibujan en cada zona: todo Santander, o solo los que caen en Los Santos."""
    catalogo = _leer_json("sismos_santander.json")
    if zona == "santander":
        return catalogo
    sur, norte, oeste, este = LIMITES_DE_LOS_SANTOS
    lat, lon = np.asarray(catalogo["lat"]), np.asarray(catalogo["lon"])
    dentro = (lat >= sur) & (lat < norte) & (lon >= oeste) & (lon < este)
    return {columna: np.asarray(valores)[dentro].tolist() for columna, valores in catalogo.items()}


@lru_cache
def sismos_reales():
    """Sismos del nido con más reportes de la población y sus intensidades observadas."""
    return _leer_json("sismos_reales.json")


@lru_cache
def poblacion():
    """Habitantes de cada municipio de Santander y el punto donde se evalúa su sacudida."""
    datos = _leer_json("poblacion.json")
    for columna in ("lat", "lon", "habitantes", "viviendas"):
        datos[columna] = np.asarray(datos[columna], dtype=float)
    return datos


@lru_cache
def relieve(zona):
    """Modelo de elevación de una zona en una malla regular de latitud y longitud."""
    return _leer_json(f"relieve_{zona}.json")


@lru_cache
def malla_fina(zona):
    """
    Puntos sobre los que se calcula la sacudida para el mapa de calor: una
    malla mucho más fina que las celdas del simulador, con los mismos límites
    que el relieve de la zona para que encaje exactamente sobre él.
    """
    r = relieve(zona)
    paso = PASO_DE_MALLA_FINA[zona]
    columnas = round((r["lon_este"] - r["lon_oeste"]) / paso)
    filas = round((r["lat_norte"] - r["lat_sur"]) / paso)
    # Centros de cada punto; la primera fila es la más al norte
    lon = r["lon_oeste"] + (np.arange(columnas) + 0.5) * (r["lon_este"] - r["lon_oeste"]) / columnas
    lat = r["lat_norte"] - (np.arange(filas) + 0.5) * (r["lat_norte"] - r["lat_sur"]) / filas
    lon_2d, lat_2d = np.meshgrid(lon, lat)
    return {
        "oeste": r["lon_oeste"], "este": r["lon_este"], "sur": r["lat_sur"], "norte": r["lat_norte"],
        "filas": filas, "columnas": columnas,
        "lat": lat_2d.ravel(), "lon": lon_2d.ravel(),
    }


@lru_cache
def metricas_clasificador(zona="los_santos"):
    return _leer_json(f"metricas_clasificador{ZONAS_DE_RIESGO[zona]}.json")


@lru_cache
def historial_riesgo(zona="los_santos"):
    """Predicho y ocurrido en cada trimestre del periodo de prueba del clasificador."""
    return _leer_json(f"historial_riesgo{ZONAS_DE_RIESGO[zona]}.json")


@lru_cache
def metricas_sacudida():
    return _leer_json("metricas_sacudida.json")


def precargar():
    """Carga todo al arrancar, para que la primera petición no pague la espera."""
    for recurso in (modelo_riesgo, modelo_sacudida, grilla_riesgo, grilla_simulador,
                    municipios, sismos, sismos_reales, poblacion, metricas_clasificador, historial_riesgo, metricas_sacudida,
                    modelo_viviendas, metricas_viviendas):
        recurso()
    for zona in ZONAS_DE_RIESGO:
        modelo_riesgo(zona), grilla_riesgo(zona), metricas_clasificador(zona), historial_riesgo(zona)
    for zona in ZONAS:
        malla_fina(zona), sismos_de_zona(zona)
