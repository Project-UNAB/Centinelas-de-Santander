# ==============================================================================
# HACKATHON: UTSmart IA Challenge 2027
# PROYECTO: Gemelo Digital Sísmico de Santander
# MÓDULO: Uso del modelo de viviendas afectadas (entrenamiento y backend)
# ==============================================================================
# El modelo trabaja con el logaritmo de la proporción de viviendas afectadas,
# porque esa proporción va de una en cien mil a una de cada cinco.
# ==============================================================================

import numpy as np

# Proporción mínima que se distingue de cero: una vivienda de cada cien mil
PROPORCION_MINIMA = 1e-5
# Desde esta intensidad se usa la proporción de viviendas destruidas de los sismos fuertes
INTENSIDAD_FUERTE = 6.0


def a_log(proporcion):
    return np.log10(np.asarray(proporcion, dtype=float) + PROPORCION_MINIMA)


def de_log(valor):
    return np.clip(10 ** np.asarray(valor, dtype=float) - PROPORCION_MINIMA, 0.0, 1.0)


def estimar(modelo, casos, viviendas):
    """
    Viviendas afectadas y costo de atención para cada municipio.

    modelo:    diccionario guardado por entrenar_modelo_viviendas.py
    casos:     DataFrame con las columnas de modelo['variables'] (la intensidad
               debe ser la del cálculo físico, sin calibrar)
    viviendas: viviendas de cada municipio

    Devuelve un diccionario de arreglos: valor central y rango (bajo, alto) de
    viviendas afectadas, viviendas destruidas y costo en pesos.
    """
    viviendas = np.asarray(viviendas, dtype=float)
    centro = modelo['estimador'].predict(casos[modelo['variables']].to_numpy())
    rango = modelo['rango_log10']
    afectadas = {nombre: de_log(centro + desplazamiento) * viviendas
                 for nombre, desplazamiento in (('afectadas_bajo', rango['bajo']), ('afectadas', 0.0), ('afectadas_alto', rango['alto']))}
    parte = modelo['proporcion_destruida']
    destruida = np.where(casos['intensidad_mmi'].to_numpy() >= INTENSIDAD_FUERTE, parte['fuerte'], parte['moderada'])
    costo = modelo['costo_por_vivienda_cop']
    return {
        **afectadas,
        'destruidas': afectadas['afectadas'] * destruida,
        'costo_bajo': afectadas['afectadas_bajo'] * costo['bajo'],
        'costo': afectadas['afectadas'] * costo['medio'],
        'costo_alto': afectadas['afectadas_alto'] * costo['alto'],
    }
