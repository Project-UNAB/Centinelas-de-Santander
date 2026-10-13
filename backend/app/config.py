"""Configuración del backend. Todo lo que cambia entre local y la nube llega por variables de entorno."""

import os
from pathlib import Path

# Carpeta con los modelos y datos exportados por entrenamiento/src/exportar_al_backend.py
ARTEFACTOS_DIR = Path(os.getenv("ARTEFACTOS_DIR", Path(__file__).resolve().parent.parent / "artefactos"))

# Orígenes que pueden llamar a la API desde el navegador, separados por comas.
# En producción: la URL del frontend en Vercel.
CORS_ORIGENES = [o.strip() for o in os.getenv("CORS_ORIGENES", "http://localhost:5173").split(",") if o.strip()]

# Opcional: expresión regular para aceptar también las vistas previas de Vercel,
# por ejemplo  https://centinelas-.*\.vercel\.app
CORS_ORIGEN_REGEX = os.getenv("CORS_ORIGEN_REGEX") or None

# Zonas con relieve 3D y separación (en grados) de los puntos del mapa de calor en
# cada una: unos 1.100 m para todo Santander y unos 220 m para Los Santos
ZONAS = ("santander", "los_santos")
PASO_DE_MALLA_FINA = {"santander": 0.01, "los_santos": 0.002}

# Zonas con clasificador de riesgo y sufijo de sus archivos: el de Los Santos (30 celdas)
# y el de todo Santander son dos modelos distintos
ZONAS_DE_RIESGO = {"los_santos": "", "santander": "_santander"}

# Límites de los controles del simulador
MAGNITUD_MIN, MAGNITUD_MAX = 4.0, 7.0
PROFUNDIDAD_MIN_KM, PROFUNDIDAD_MAX_KM = 10.0, 200.0
# Dónde puede estar el epicentro de un escenario: Santander y sus alrededores
EPICENTRO_LAT = (5.0, 9.0)
EPICENTRO_LON = (-75.0, -72.0)
