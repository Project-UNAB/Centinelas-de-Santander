"""
API del Gemelo Digital Sísmico de Santander - Módulo Los Santos.

Sirve dos modelos ya entrenados:
  - /api/riesgo     clasificador de riesgo por zona: uno para Los Santos y otro para todo Santander
  - /api/simulador  sacudida esperada para un sismo hipotético, personas expuestas y viviendas afectadas

Ejecutar en local:  uvicorn app.main:app --reload --port 8000
Documentación interactiva:  http://localhost:8000/docs
"""

import gzip
import json
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Literal

import numpy as np
import pandas as pd
from fastapi import FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from . import modelo_de_danos, recursos, sintetico
from . import simulador as sim
from .config import (
    CORS_ORIGEN_REGEX,
    CORS_ORIGENES,
    MAGNITUD_MAX,
    MAGNITUD_MIN,
    PROFUNDIDAD_MAX_KM,
    PROFUNDIDAD_MIN_KM,
)
from .esquemas import (
    Escenario,
    EscenarioEnZona,
    MapaDeCalor,
    PrediccionDeRiesgo,
    ResultadoDeEscenario,
    VariablesDeCelda,
)


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    recursos.precargar()
    yield


app = FastAPI(
    title="Centinelas de Santander - API",
    description="Riesgo sísmico por zona en Los Santos y simulador de escenarios.",
    version="1.0.0",
    lifespan=ciclo_de_vida,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGENES,
    allow_origin_regex=CORS_ORIGEN_REGEX,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Datos que no cambian hasta el próximo despliegue: el navegador puede guardarlos
# y no volver a descargarlos (relieve, límites, sismos, grillas)
RUTAS_ESTABLES = ("/api/danos/", "/api/relieve/", "/api/municipios", "/api/sismos", "/api/riesgo/", "/api/simulador/grilla", "/api/simulador/modelo",
                  "/api/simulador/sismos-reales", "/api/poblacion")


@app.middleware("http")
async def guardar_en_el_navegador(request: Request, call_next):
    respuesta = await call_next(request)
    if request.method == "GET" and respuesta.status_code == 200 and request.url.path.startswith(RUTAS_ESTABLES):
        respuesta.headers["Cache-Control"] = "public, max-age=3600"
    return respuesta


@app.get("/api/salud", tags=["general"])
def salud():
    """Comprobación de que el servicio y los modelos están cargados."""
    return {
        "estado": "ok",
        "modelo_riesgo": recursos.modelo_riesgo()["nombre"],
        "modelo_sacudida": recursos.modelo_sacudida()["calibracion"]["tipo"],
    }


@app.get("/api/municipios", tags=["general"])
def municipios():
    """Límites de los 87 municipios de Santander (GeoJSON, fuente DANE)."""
    return recursos.municipios()


@app.get("/api/poblacion", tags=["general"])
def poblacion():
    """
    Habitantes de cada municipio de Santander (proyección del DANE) y el punto
    de su interior donde se evalúa la sacudida, en columnas.
    """
    datos = recursos.poblacion()
    return {
        "fuente": datos["fuente"],
        "anio": datos["anio"],
        "municipio": datos["municipio"],
        "habitantes": datos["habitantes"].astype(int).tolist(),
        "viviendas": datos["viviendas"].astype(int).tolist(),
        "lat": datos["lat"].tolist(),
        "lon": datos["lon"].tolist(),
    }


@app.get("/api/sismos", tags=["general"])
def sismos():
    """Hipocentros M>=2.5 desde 2010 (los que usa el modelo), en columnas."""
    return recursos.sismos()


@app.get("/api/relieve/{zona}", tags=["general"])
def relieve(zona: Literal["santander", "los_santos"]):
    """
    Elevación del terreno (m s. n. m.), fila por fila de norte a sur. Los
    puntos con -1 quedan fuera del departamento y no se dibujan.
    """
    return recursos.relieve(zona)


# ------------------------------------------------------------------------------
# Clasificador de riesgo por zona
# ------------------------------------------------------------------------------
ZonaDeRiesgo = Literal["los_santos", "santander"]


@app.get("/api/riesgo/celdas", tags=["riesgo"])
def celdas_de_riesgo(zona: ZonaDeRiesgo = "los_santos"):
    """Celdas de la zona con sus variables y el riesgo predicho por su modelo (GeoJSON)."""
    return recursos.grilla_riesgo(zona)


@app.get("/api/riesgo/modelo", tags=["riesgo"])
def informacion_del_clasificador(zona: ZonaDeRiesgo = "los_santos"):
    """Cómo se entrenó el clasificador de la zona y qué tan bien acierta."""
    paquete = recursos.modelo_riesgo(zona)
    return {
        "zona": zona,
        "celdas_con_modelo": len(paquete["celdas_activas"]),
        "ajustes": paquete.get("ajustes"),
        "nombre": paquete["nombre"],
        "variables": paquete["features"],
        "clases": paquete["clases"],
        "umbrales_sismos": paquete["umbrales_sismos"],
        "magnitud_minima": paquete["magnitud_minima"],
        "ventana_meses": paquete["ventana_meses"],
        **{clave: valor for clave, valor in recursos.metricas_clasificador(zona).items() if clave != "ajustes"},
    }


@app.get("/api/riesgo/historial", tags=["riesgo"])
def historial_de_riesgo(zona: ZonaDeRiesgo = "los_santos"):
    """
    Periodo de prueba, trimestre a trimestre: qué nivel predijo el modelo para
    cada celda (sin haber visto ese trimestre) y cuál ocurrió. Las listas van
    en el orden de cell_id y los niveles como posición en «niveles».
    """
    return recursos.historial_riesgo(zona)


@app.post("/api/riesgo/predecir", response_model=PrediccionDeRiesgo, tags=["riesgo"])
def predecir_riesgo(variables: VariablesDeCelda, zona: ZonaDeRiesgo = "los_santos"):
    """Nivel de riesgo para una celda descrita por sus 15 variables, con el modelo de la zona."""
    paquete = recursos.modelo_riesgo(zona)
    X = pd.DataFrame([variables.model_dump()])[paquete["features"]]
    probabilidades = paquete["modelo"].predict_proba(X)[0]
    return {
        "nivel": paquete["modelo"].predict(X)[0],
        "probabilidades": {clase: round(float(p), 4) for clase, p in zip(paquete["clases"], probabilidades)},
    }


# ------------------------------------------------------------------------------
# Simulador de escenarios
# ------------------------------------------------------------------------------
@app.get("/api/simulador/grilla", tags=["simulador"])
def grilla_del_simulador():
    """Centros de las celdas de Santander sobre las que se simula."""
    grilla = recursos.grilla_simulador()
    fuente = recursos.modelo_sacudida()["fuente"]
    return {
        "paso": grilla["paso"],
        "lat": grilla["lat"].tolist(),
        "lon": grilla["lon"].tolist(),
        "municipio": grilla["municipio"],
        "epicentro": {"lat": fuente["lat"], "lon": fuente["lon"]},
        "limites": {
            "magnitud": [MAGNITUD_MIN, MAGNITUD_MAX],
            "profundidad_km": [PROFUNDIDAD_MIN_KM, PROFUNDIDAD_MAX_KM],
        },
    }


@app.get("/api/simulador/modelo", tags=["simulador"])
def informacion_del_simulador():
    """Validación del modelo de sacudida contra intensidades observadas."""
    return recursos.metricas_sacudida()


@app.get("/api/simulador/sismos-reales", tags=["simulador"])
def sismos_reales():
    """
    Los sismos del nido con más reportes de la población (USGS, «Did You Feel
    It?»), con la intensidad observada en cada lugar y la que da el modelo
    calibrado sin ese sismo. Sirven para reproducirlos en el simulador.
    """
    return recursos.sismos_reales()


@app.get("/api/simulador/sismos", tags=["simulador"])
def sismos_simulados(
    anios: int = Query(17, ge=1, le=50, description="Años de sismicidad que se simulan"),
    semilla: int = Query(1, ge=0, le=100000, description="Cambiarla produce otra simulación"),
):
    """
    Catálogo sintético del nido: sismos que no ocurrieron, generados con la
    tasa, la distribución espacial y la ley de magnitudes del catálogo real.
    Mismo formato que /api/sismos.
    """
    return sintetico.generar(anios, semilla)


def _personas_expuestas(magnitud, profundidad_km, epicentro=None):
    """
    Habitantes de Santander según la sacudida de su municipio. Es una
    aproximación: a todo el municipio se le atribuye la intensidad calculada en
    un punto de su interior, sin distinguir dónde vive cada persona.
    """
    poblacion = recursos.poblacion()
    mmi = sim.calcular_intensidad(
        recursos.modelo_sacudida(), magnitud, profundidad_km, poblacion["lat"], poblacion["lon"], epicentro=epicentro)["mmi"]
    nivel = sim.clasificar_nivel(mmi)
    return {
        "viviendas": _viviendas_afectadas(magnitud, profundidad_km, epicentro),
        "personas_por_nivel": {n: int(poblacion["habitantes"][nivel == n].sum()) for n in sim.NIVELES},
        "municipios_por_nivel": {n: int((nivel == n).sum()) for n in sim.NIVELES},
        # Nivel con que cuenta cada municipio, en el orden de /api/poblacion
        "nivel_por_municipio": [str(n) for n in nivel],
        "anio_de_la_poblacion": poblacion["anio"],
    }


def _viviendas_afectadas(magnitud, profundidad_km, epicentro=None):
    """
    Viviendas afectadas y costo de atención en Santander, con el modelo
    aprendido de sismos colombianos reales. Se le da la intensidad del cálculo
    físico (sin la calibración del nido), que es con la que se entrenó. El
    error del modelo es grande: por eso cada cifra va con su rango.
    """
    poblacion, modelo = recursos.poblacion(), recursos.modelo_viviendas()
    fuente = recursos.modelo_sacudida()["fuente"]
    ep_lat, ep_lon = epicentro if epicentro is not None else (fuente["lat"], fuente["lon"])
    distancia = sim.distancia_epicentral_km(poblacion["lat"], poblacion["lon"], ep_lat, ep_lon)
    intensidad = sim.mmi_fisico(magnitud, sim.distancia_hipocentral_km(distancia, profundidad_km), profundidad_km)
    casos = pd.DataFrame({"intensidad_mmi": intensidad, "magnitud": magnitud, "prof_km": profundidad_km, "dist_epicentral_km": distancia})
    estimacion = modelo_de_danos.estimar(modelo, casos, poblacion["viviendas"])
    return {
        "total": int(poblacion["viviendas"].sum()),
        **{clave: float(round(valores.sum())) for clave, valores in estimacion.items()},
        # Viviendas afectadas (valor central) de cada municipio, en el orden de /api/poblacion
        "afectadas_por_municipio": np.round(estimacion["afectadas"], 1).tolist(),
        "intensidad_maxima": round(float(intensidad.max()), 2),
        "intensidad_validada": modelo["intensidad_validada"],
        "fuera_de_lo_observado": bool(intensidad.max() > modelo["intensidad_validada"][1]),
        "costo_por_vivienda_cop": {k: modelo["costo_por_vivienda_cop"][k] for k in ("bajo", "medio", "alto")},
    }


@app.get("/api/danos/modelo", tags=["simulador"])
def informacion_del_modelo_de_viviendas():
    """Cómo se validó el modelo de viviendas afectadas y de dónde sale el costo."""
    metricas = recursos.metricas_viviendas()
    return {clave: valor for clave, valor in metricas.items() if clave != "validacion_por_caso"}


@app.post("/api/simulador/mapa-de-calor", response_model=MapaDeCalor, tags=["simulador"])
def mapa_de_calor(escenario: EscenarioEnZona, request: Request):
    """
    Sacudida de un sismo hipotético en una malla fina, para pintarla como mapa
    de calor sobre el relieve. El resumen (info) se calcula con las celdas y
    los municipios de Santander, igual que en /api/simulador.
    """
    epicentro = None if escenario.epicentro_lat is None else (escenario.epicentro_lat, escenario.epicentro_lon)
    comprimido = _mapa_de_calor_json(
        round(escenario.magnitud, 2), round(escenario.profundidad_km, 1), escenario.zona, epicentro)
    if "gzip" in request.headers.get("accept-encoding", ""):
        return Response(content=comprimido, media_type="application/json",
                        headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding"})
    return Response(content=gzip.decompress(comprimido), media_type="application/json")


@lru_cache(maxsize=1024)
def _mapa_de_calor_json(magnitud: float, profundidad_km: float, zona: str, epicentro: tuple[float, float] | None) -> bytes:
    """
    Mapa de calor ya convertido a JSON y comprimido. Los controles solo
    producen unos cientos de escenarios distintos, así que se guardan: repetir
    uno (lo normal al arrastrar un control de ida y vuelta) no vuelve a
    calcular ni a comprimir nada.
    """
    modelo = recursos.modelo_sacudida()
    celdas = recursos.grilla_simulador()
    _, info = sim.simular_escenario(modelo, magnitud, profundidad_km, celdas["lat"], celdas["lon"], celdas["vs30"], epicentro)
    info = {**info, **_personas_expuestas(magnitud, profundidad_km, epicentro)}

    malla = recursos.malla_fina(zona)
    mmi = sim.calcular_intensidad(modelo, magnitud, profundidad_km, malla["lat"], malla["lon"], epicentro=epicentro)["mmi"]
    contenido = json.dumps({
        "info": info,
        "campo": {
            **{clave: malla[clave] for clave in ("oeste", "este", "sur", "norte", "filas", "columnas")},
            "mmi": mmi.round(2).tolist(),
        },
    }, separators=(",", ":")).encode()
    return gzip.compress(contenido, compresslevel=5)


@app.post("/api/simulador", response_model=ResultadoDeEscenario, tags=["simulador"])
def simular(escenario: Escenario):
    """Sacudida esperada en cada celda de Santander para un sismo hipotético."""
    grilla = recursos.grilla_simulador()
    resultado, info = sim.simular_escenario(
        recursos.modelo_sacudida(), escenario.magnitud, escenario.profundidad_km,
        grilla["lat"], grilla["lon"], grilla["vs30"])
    return {
        "info": {**info, **_personas_expuestas(escenario.magnitud, escenario.profundidad_km)},
        "mmi": resultado["mmi"].round(2).tolist(),
        "nivel": resultado["nivel"].tolist(),
        "pga_g": resultado["pga_g"].round(4).tolist(),
    }
