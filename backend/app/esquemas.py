"""Formas de los datos que entran y salen de la API."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .config import EPICENTRO_LAT, EPICENTRO_LON, MAGNITUD_MAX, MAGNITUD_MIN, PROFUNDIDAD_MAX_KM, PROFUNDIDAD_MIN_KM


class VariablesDeCelda(BaseModel):
    """Las 15 variables del clasificador, al cierre de un trimestre."""
    sismos_trimestre: float = Field(ge=0, description="Sismos M>=2.5 en la celda durante el trimestre")
    sismos_ultimo_anio: float = Field(ge=0, description="Sismos en los últimos cuatro trimestres")
    sismos_promedio_historico: float = Field(ge=0, description="Promedio trimestral desde 2010")
    tendencia_sismos: float = Field(description="Trimestre actual menos el promedio del último año")
    sismos_vecinos_ultimo_anio: float = Field(ge=0, description="Sismos del último año en las 8 celdas vecinas")
    mag_media_ultimo_anio: float = Field(ge=0, le=10)
    mag_max_ultimo_anio: float = Field(ge=0, le=10)
    log_energia_ultimo_anio: float = Field(ge=0)
    prop_moderados_ultimo_anio: float = Field(ge=0, le=1, description="Fracción de sismos con M>=3.5")
    trimestres_desde_sismo_fuerte: float = Field(ge=0, description="Trimestres desde el último M>=4")
    prof_media_ultimo_anio: float = Field(ge=0, description="Profundidad media (km)")
    prof_std_ultimo_anio: float = Field(ge=0, description="Dispersión de la profundidad (km)")
    dist_nido_km: float = Field(ge=0, description="Distancia al centro del nido")
    lat_center: float = Field(ge=-90, le=90)
    lon_center: float = Field(ge=-180, le=180)


class PrediccionDeRiesgo(BaseModel):
    nivel: str
    probabilidades: dict[str, float]


class Escenario(BaseModel):
    """Sismo hipotético para el simulador."""
    magnitud: float = Field(ge=MAGNITUD_MIN, le=MAGNITUD_MAX)
    profundidad_km: float = Field(ge=PROFUNDIDAD_MIN_KM, le=PROFUNDIDAD_MAX_KM)


class EscenarioEnZona(Escenario):
    """
    Sismo hipotético y zona sobre la que se quiere el mapa de calor. El
    epicentro es opcional: sin él se usa el centro del Nido de Bucaramanga.
    """
    zona: Literal["santander", "los_santos"] = "santander"
    epicentro_lat: float | None = Field(default=None, ge=EPICENTRO_LAT[0], le=EPICENTRO_LAT[1])
    epicentro_lon: float | None = Field(default=None, ge=EPICENTRO_LON[0], le=EPICENTRO_LON[1])

    @model_validator(mode="after")
    def epicentro_completo(self):
        if (self.epicentro_lat is None) != (self.epicentro_lon is None):
            raise ValueError("El epicentro necesita latitud y longitud")
        return self


class CampoDeSacudida(BaseModel):
    """Intensidad en una malla fina, fila por fila de norte a sur."""
    oeste: float
    este: float
    sur: float
    norte: float
    filas: int
    columnas: int
    mmi: list[float]


class MapaDeCalor(BaseModel):
    info: dict
    campo: CampoDeSacudida


class ResultadoDeEscenario(BaseModel):
    """Sacudida por celda, en el mismo orden que GET /api/simulador/grilla."""
    info: dict
    mmi: list[float]
    nivel: list[str]
    pga_g: list[float]
