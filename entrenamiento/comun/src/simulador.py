# ==============================================================================
# HACKATHON: UTSmart IA Challenge 2027
# PROYECTO: Gemelo Digital Sísmico de Santander - Módulo Los Santos
# MÓDULO: Motor de simulación de escenarios (lo que importa la aplicación web)
# ==============================================================================
# Dado un escenario hipotético (magnitud, profundidad) estima la sacudida
# esperada en cada punto del territorio:
#
#   1. Aceleración máxima del suelo (PGA) con la relación de movimiento del
#      suelo de Zhao et al. (2006, BSSA 96(3), 898-913).
#   2. Conversión de PGA a intensidad Mercalli (MMI) con Worden et al.
#      (2012, BSSA 102(1), 204-221).
#   3. Corrección calibrada con intensidades observadas en sismos reales del
#      nido (la calcula entrenar_modelo_sacudida.py).
#   4. Clasificación en Bajo / Medio / Alto según la intensidad.
#
# No predice cuándo ocurrirá un sismo: simula qué sacudida produciría uno.
#
# Uso desde la web:
#     from simulador import cargar_modelo, cargar_grilla, simular_escenario
#     modelo, grilla = cargar_modelo(), cargar_grilla()
#     resultado, info = simular_escenario(modelo, 6.0, 150,
#                                         grilla["lat_center"], grilla["lon_center"])
# ==============================================================================

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
MODELO_PKL = BASE_DIR / "models" / "modelo_sacudida_santander.pkl"
GRILLA_GEOJSON = BASE_DIR / "data" / "processed" / "grilla_santander.geojson"

# Coeficientes de Zhao et al. (2006) para PGA: tablas 4, 5 y 6 del artículo
ZHAO_PGA = {
    'a': 1.101, 'b': -0.00564, 'c': 0.0055, 'd': 1.080, 'e': 0.01412,
    'CH': 0.293, 'C1': 1.111, 'C2': 1.344, 'C3': 1.355, 'C4': 1.420,
    'SS': 2.607, 'SSL': -0.528, 'PS': 0.1392, 'QS': 0.1584, 'WS': -0.0529,
}
PROF_REFERENCIA_ZHAO = 15.0    # km, a partir de aquí actúa el término de profundidad
PROF_MAXIMA_ZHAO = 125.0       # km, el artículo satura la profundidad en este valor

# Por debajo de esta profundidad el escenario se trata como sismo cortical y,
# por encima, como sismo intraplaca (el caso del Nido de Bucaramanga)
PROF_MIN_INTRAPLACA = 50.0

# Sin mapa de suelos, todo el territorio se asume "suelo duro" (300-600 m/s)
VS30_DEFECTO = 450.0

# Coeficientes de Worden et al. (2012) para PGA en cm/s², con la extensión
# para intensidades bajas que usa ShakeMap del USGS
WORDEN_PGA = {'C1': 1.78, 'C2': 1.55, 'C3': -1.60, 'C4': 3.70, 'T1': 1.57,
              'C1_BAJO': 1.71, 'C2_BAJO': 2.08, 'T1_BAJO': 0.14}

# Niveles de sacudida según la intensidad Mercalli redondeada:
#   Bajo  (verde):    hasta IV  -> se siente, sin daños
#   Medio (amarillo): V a VI    -> fuerte, daños leves
#   Alto  (rojo):     VII o más -> muy fuerte, daños moderados a graves
UMBRAL_MEDIO = 4.5
UMBRAL_ALTO = 6.5
NIVELES = ['Bajo', 'Medio', 'Alto']
COLORES = {'Bajo': [46, 160, 67], 'Medio': [240, 200, 40], 'Alto': [215, 48, 39]}

RADIO_TIERRA_KM = 6371.0
G_CMS2 = 980.665


def distancia_epicentral_km(lat, lon, ep_lat, ep_lon):
    """Distancia sobre la superficie (haversine) entre cada punto y el epicentro."""
    lat, lon = np.radians(np.asarray(lat, dtype=float)), np.radians(np.asarray(lon, dtype=float))
    ep_lat, ep_lon = np.radians(ep_lat), np.radians(ep_lon)
    a = (np.sin((lat - ep_lat) / 2) ** 2
         + np.cos(lat) * np.cos(ep_lat) * np.sin((lon - ep_lon) / 2) ** 2)
    return 2 * RADIO_TIERRA_KM * np.arcsin(np.sqrt(a))


def distancia_hipocentral_km(dist_epi_km, prof_km):
    return np.sqrt(np.asarray(dist_epi_km, dtype=float) ** 2 + np.asarray(prof_km, dtype=float) ** 2)


def termino_sitio_zhao(vs30):
    """Clase de sitio de Zhao et al. (2006), tabla 2, a partir de Vs30 (m/s)."""
    vs30 = np.asarray(vs30, dtype=float)
    C = ZHAO_PGA
    return np.select(
        [vs30 > 1100, vs30 > 600, vs30 > 300, vs30 > 200],
        [C['CH'], C['C1'], C['C2'], C['C3']],
        default=C['C4'],
    )


def pga_zhao2006(magnitud, dist_hipo_km, prof_km, vs30=VS30_DEFECTO):
    """
    Mediana de la aceleración máxima del suelo en cm/s² (ecuaciones 1 y 5 de
    Zhao et al. 2006). La fuente se aproxima como un punto, así que la
    distancia a la ruptura es la distancia hipocentral.
    """
    C = ZHAO_PGA
    magnitud = np.asarray(magnitud, dtype=float)
    prof_km = np.asarray(prof_km, dtype=float)
    r = np.maximum(np.asarray(dist_hipo_km, dtype=float), 0.1)

    ln_pga = C['a'] * magnitud + C['b'] * r - np.log(r + C['c'] * np.exp(C['d'] * magnitud))

    h = np.minimum(prof_km, PROF_MAXIMA_ZHAO)
    ln_pga = ln_pga + np.where(h >= PROF_REFERENCIA_ZHAO, C['e'] * (h - PROF_REFERENCIA_ZHAO), 0.0)
    ln_pga = ln_pga + termino_sitio_zhao(vs30)

    # Términos exclusivos de los sismos intraplaca
    dm = magnitud - 6.5
    intraplaca = C['PS'] * dm + C['QS'] * dm ** 2 + C['WS'] + C['SS'] + C['SSL'] * np.log(r)
    ln_pga = ln_pga + np.where(prof_km >= PROF_MIN_INTRAPLACA, intraplaca, 0.0)

    return np.exp(ln_pga)


def mmi_worden2012(pga_cms2):
    """Intensidad Mercalli Modificada a partir de PGA en cm/s²."""
    W = WORDEN_PGA
    log_pga = np.log10(np.maximum(np.asarray(pga_cms2, dtype=float), 1e-6))
    mmi = np.where(
        log_pga <= W['T1_BAJO'], W['C1_BAJO'] + W['C2_BAJO'] * log_pga,
        np.where(log_pga <= W['T1'], W['C1'] + W['C2'] * log_pga, W['C3'] + W['C4'] * log_pga),
    )
    return np.clip(mmi, 1.0, 10.0)


def mmi_fisico(magnitud, dist_hipo_km, prof_km, vs30=VS30_DEFECTO):
    """Intensidad esperada solo con el cálculo físico (sin calibración)."""
    return mmi_worden2012(pga_zhao2006(magnitud, dist_hipo_km, prof_km, vs30))


def construir_features(magnitud, dist_hipo_km, lat, lon, columnas):
    """Variables de la corrección calibrada; las usan igual el entrenamiento y la web."""
    dist_hipo_km = np.asarray(dist_hipo_km, dtype=float)
    todas = {
        'magnitud': np.broadcast_to(np.asarray(magnitud, dtype=float), dist_hipo_km.shape),
        'log_dist_hipo': np.log10(np.maximum(dist_hipo_km, 0.1)),
        'lat': np.asarray(lat, dtype=float),
        'lon': np.asarray(lon, dtype=float),
    }
    return pd.DataFrame({c: todas[c] for c in columnas})


def clasificar_nivel(mmi):
    mmi = np.asarray(mmi, dtype=float)
    return np.select([mmi >= UMBRAL_ALTO, mmi >= UMBRAL_MEDIO], ['Alto', 'Medio'], default='Bajo')


def tasa_anual_gutenberg_richter(recurrencia, magnitud):
    """Sismos por año con magnitud mayor o igual a la dada, según el catálogo del nido."""
    return recurrencia['tasa_m_min'] * 10 ** (-recurrencia['b'] * (magnitud - recurrencia['m_min']))


def cargar_modelo(ruta=MODELO_PKL):
    return joblib.load(ruta)


def cargar_grilla(ruta=GRILLA_GEOJSON):
    import geopandas as gpd
    return gpd.read_file(ruta)


def calcular_intensidad(modelo, magnitud, profundidad_km, lat, lon, vs30=None, epicentro=None):
    """
    Núcleo del cálculo: intensidad esperada en cada punto, como arreglos de
    NumPy. Es lo que usa el mapa de calor, que evalúa decenas de miles de
    puntos y no necesita la tabla completa de simular_escenario().
    """
    lat, lon = np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)
    fuente = modelo['fuente']
    ep_lat, ep_lon = epicentro if epicentro is not None else (fuente['lat'], fuente['lon'])
    vs30 = modelo['vs30_defecto'] if vs30 is None else np.asarray(vs30, dtype=float)

    dist_epi = distancia_epicentral_km(lat, lon, ep_lat, ep_lon)
    dist_hipo = distancia_hipocentral_km(dist_epi, profundidad_km)
    pga = pga_zhao2006(magnitud, dist_hipo, profundidad_km, vs30)
    mmi_base = mmi_worden2012(pga)

    # La corrección se aprendió de sismos intraplaca del nido: no se aplica a
    # escenarios corticales, para los que no hay observaciones
    calibracion = modelo['calibracion']
    correccion = np.zeros(lat.shape)
    if profundidad_km >= PROF_MIN_INTRAPLACA:
        correccion = correccion + calibracion['sesgo']
        if calibracion['estimador'] is not None:
            X = construir_features(magnitud, dist_hipo, lat, lon, calibracion['features'])
            # Fuera de lo observado la corrección se mantiene en su valor del borde
            for col, (minimo, maximo) in calibracion['limites'].items():
                X[col] = X[col].clip(minimo, maximo)
            correccion = correccion + calibracion['estimador'].predict(X)

    return {
        'dist_epicentral_km': dist_epi,
        'dist_hipocentral_km': dist_hipo,
        'pga': pga,
        'mmi_fisico': mmi_base,
        'correccion_calibrada': correccion,
        'mmi': np.clip(mmi_base + correccion, 1.0, 10.0),
    }


def simular_escenario(modelo, magnitud, profundidad_km, lat, lon, vs30=None, epicentro=None):
    """
    Simula un sismo hipotético y devuelve la sacudida esperada en cada punto.

    modelo:         diccionario devuelto por cargar_modelo()
    magnitud:       magnitud de momento del escenario (Mw)
    profundidad_km: profundidad del hipocentro
    lat, lon:       coordenadas de los puntos a evaluar (centros de celda)
    vs30:           velocidad de onda de corte del suelo por punto (m/s); si
                    no se da, se asume suelo duro en todo el territorio
    epicentro:      (lat, lon); por defecto, el centro del Nido de Bucaramanga

    Devuelve (resultado, info): una tabla con una fila por punto y un
    diccionario con el contexto del escenario y sus advertencias.
    """
    lat, lon = np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)
    fuente = modelo['fuente']
    ep_lat, ep_lon = epicentro if epicentro is not None else (fuente['lat'], fuente['lon'])
    es_intraplaca = profundidad_km >= PROF_MIN_INTRAPLACA
    calibracion = modelo['calibracion']

    calculo = calcular_intensidad(modelo, magnitud, profundidad_km, lat, lon, vs30, epicentro)
    dist_epi, dist_hipo, pga = calculo['dist_epicentral_km'], calculo['dist_hipocentral_km'], calculo['pga']
    mmi_base, correccion, mmi = calculo['mmi_fisico'], calculo['correccion_calibrada'], calculo['mmi']

    nivel = clasificar_nivel(mmi)
    resultado = pd.DataFrame({
        'lat': lat,
        'lon': lon,
        'dist_epicentral_km': dist_epi,
        'dist_hipocentral_km': dist_hipo,
        'pga_g': pga / G_CMS2,
        'mmi_fisico': mmi_base,
        'correccion_calibrada': correccion,
        'mmi': mmi,
        'nivel': nivel,
        'color': [COLORES[n] for n in nivel],
    })

    rango = modelo['rango_validado']
    advertencias = []
    if not es_intraplaca:
        advertencias.append(
            "Escenario cortical (menos de %d km): se usa solo el cálculo físico, sin "
            "calibración con observaciones." % PROF_MIN_INTRAPLACA)
    elif not rango['prof_km'][0] <= profundidad_km <= rango['prof_km'][1]:
        advertencias.append(
            "Profundidad fuera del rango validado con observaciones (%.0f a %.0f km)." % tuple(rango['prof_km']))
    if not rango['magnitud'][0] <= magnitud <= rango['magnitud'][1]:
        advertencias.append(
            "Magnitud fuera del rango validado con observaciones (%.1f a %.1f)." % tuple(rango['magnitud']))
    if es_intraplaca and magnitud > fuente['recurrencia']['m_max_observada']:
        advertencias.append(
            "Magnitud mayor que la máxima registrada en el nido (%.1f) entre %d y %d."
            % (fuente['recurrencia']['m_max_observada'], *fuente['periodo']))

    info = {
        'magnitud': magnitud,
        'profundidad_km': profundidad_km,
        'epicentro': (ep_lat, ep_lon),
        'tipo_fuente': 'intraplaca' if es_intraplaca else 'cortical',
        'calibracion_aplicada': calibracion['tipo'] if es_intraplaca else 'ninguna',
        'mmi_maxima': float(mmi.max()),
        'celdas_por_nivel': {n: int((nivel == n).sum()) for n in NIVELES},
        'error_tipico_mmi': modelo['error_tipico_mmi'] if es_intraplaca else None,
        'profundidad_tipica_del_nido': bool(
            fuente['prof_p01'] <= profundidad_km <= fuente['prof_p99']),
        'advertencias': advertencias,
    }
    # La recurrencia solo tiene sentido para sismos como los del catálogo del nido
    if es_intraplaca:
        tasa = tasa_anual_gutenberg_richter(fuente['recurrencia'], magnitud)
        info['tasa_anual_en_el_nido'] = float(tasa)
        info['periodo_retorno_anios'] = float(1.0 / tasa)
    return resultado, info
