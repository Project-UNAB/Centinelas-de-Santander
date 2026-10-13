"""
Catálogo sintético del Nido de Bucaramanga: sismos que no ocurrieron, generados
con las mismas propiedades estadísticas que el catálogo real del SGC.

  - Cuántos:   proceso de Poisson con la tasa anual observada.
  - Dónde:     se toma al azar el hipocentro de un sismo real y se desplaza un
               poco (remuestreo suavizado), así la nube conserva la forma del nido.
  - Magnitud:  se toma al azar la magnitud de otro sismo real. Una sola ley de
               Gutenberg-Richter exageraba los sismos grandes (unas cuatro veces
               más M>=5 que en el catálogo), porque en el nido la proporción de
               sismos grandes cae más rápido de lo que esa ley predice.

Sirve para comparar visualmente lo simulado con lo real; no es un pronóstico.
"""

from functools import lru_cache

import numpy as np

from . import recursos

# Desplazamiento que se añade a cada hipocentro remuestreado, del orden del error
# de localización del catálogo
DISPERSION_HORIZONTAL_GRADOS = 0.012   # unos 1.3 km
DISPERSION_PROFUNDIDAD_KM = 3.0


@lru_cache
def modelo_estadistico():
    """Tasa anual y rango de magnitudes del catálogo que usa el modelo."""
    catalogo = recursos.sismos()
    magnitud = np.asarray(catalogo["magnitud"], dtype=float)
    anio = np.asarray(catalogo["anio"])
    # El último año del catálogo está incompleto: la tasa se estima con los años completos
    completos = anio < anio.max()
    return {
        "tasa_anual": float(completos.sum() / len(np.unique(anio[completos]))),
        "m_min": float(magnitud.min()),
        "m_max": float(magnitud.max()),
        "sismos_reales": int(len(magnitud)),
    }


@lru_cache(maxsize=64)
def generar(anios: int, semilla: int):
    """Catálogo sintético de `anios` años, en el mismo formato que /api/sismos."""
    catalogo = recursos.sismos()
    modelo = modelo_estadistico()
    azar = np.random.default_rng(semilla)
    reales = len(catalogo["lon"])

    n = int(azar.poisson(modelo["tasa_anual"] * anios))
    origen = azar.integers(0, reales, size=n)
    lon = np.asarray(catalogo["lon"])[origen] + azar.normal(0, DISPERSION_HORIZONTAL_GRADOS, n)
    lat = np.asarray(catalogo["lat"])[origen] + azar.normal(0, DISPERSION_HORIZONTAL_GRADOS, n)
    profundidad = np.asarray(catalogo["profundidad_km"])[origen] + azar.normal(0, DISPERSION_PROFUNDIDAD_KM, n)
    # La magnitud se toma de otro sismo, sin relación con el lugar
    magnitud = np.asarray(catalogo["magnitud"])[azar.integers(0, reales, size=n)]

    return {
        "lon": lon.round(4).tolist(),
        "lat": lat.round(4).tolist(),
        "profundidad_km": np.maximum(profundidad, 1).round(0).astype(int).tolist(),
        "magnitud": magnitud.tolist(),
        "anio": azar.integers(1, anios + 1, size=n).tolist(),
        "modelo": {**modelo, "anios": anios, "semilla": semilla},
    }
