# ==============================================================================
# HACKATHON: UTSmart IA Challenge 2027
# PROYECTO: Gemelo Digital Sísmico de Santander - Módulo Los Santos
# SCRIPT: Descarga de intensidades observadas (USGS "Did You Feel It?")
# ==============================================================================
# El catálogo del SGC dice dónde y con qué magnitud ocurrieron los sismos, pero
# no cuánto se sacudió el suelo. Para validar el simulador se necesitan
# observaciones reales de sacudida: aquí se descargan las intensidades
# reportadas por la población al USGS para los sismos del Nido de Bucaramanga,
# agregadas en celdas de 10 km.
#
# Uso:  python src/descargar_intensidades_usgs.py
# ==============================================================================

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
SALIDA_CSV = BASE_DIR / "data" / "raw" / "intensidades_dyfi_usgs.csv"

# Sismos del nido: intermedios (>100 km) a menos de 60 km de Los Santos
CONSULTA = (
    "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson"
    "&starttime=2006-01-01&endtime=2026-10-12"
    "&latitude=6.80&longitude=-73.13&maxradiuskm=60"
    "&mindepth=100&minmagnitude=4.5&producttype=dyfi&orderby=time"
)
ARCHIVO_DYFI = "dyfi_geo_10km.geojson"


def descargar_json(url, intentos=3):
    for intento in range(intentos):
        try:
            with urllib.request.urlopen(url, timeout=60) as respuesta:
                return json.load(respuesta)
        except (urllib.error.URLError, TimeoutError):
            if intento == intentos - 1:
                raise
            time.sleep(2 * (intento + 1))


def centro_de_celda(geometria):
    """Centro de la celda DYFI (polígono rectangular o punto)."""
    if geometria["type"] == "Point":
        return geometria["coordinates"][1], geometria["coordinates"][0]
    anillo = geometria["coordinates"][0][:-1]
    lon = sum(p[0] for p in anillo) / len(anillo)
    lat = sum(p[1] for p in anillo) / len(anillo)
    return lat, lon


def main():
    eventos = descargar_json(CONSULTA)["features"]
    print(f"Sismos del nido con reportes de intensidad: {len(eventos)}")

    filas, sin_datos = [], []
    for i, evento in enumerate(eventos, 1):
        prop = evento["properties"]
        ev_lon, ev_lat, ev_prof = evento["geometry"]["coordinates"]
        detalle = descargar_json(prop["detail"])
        contenidos = detalle["properties"]["products"]["dyfi"][0]["contents"]
        if ARCHIVO_DYFI not in contenidos:
            sin_datos.append(evento["id"])
            continue

        celdas = descargar_json(contenidos[ARCHIVO_DYFI]["url"])["features"]
        for celda in celdas:
            obs_lat, obs_lon = centro_de_celda(celda["geometry"])
            filas.append({
                "evento_id": evento["id"],
                "fecha_utc": pd.to_datetime(prop["time"], unit="ms", utc=True).isoformat(),
                "magnitud": prop["mag"],
                "tipo_magnitud": prop["magType"],
                "ev_lat": ev_lat,
                "ev_lon": ev_lon,
                "ev_prof_km": ev_prof,
                "obs_lat": round(obs_lat, 4),
                "obs_lon": round(obs_lon, 4),
                "intensidad_cdi": celda["properties"]["cdi"],
                "n_respuestas": celda["properties"]["nresp"],
            })
        print(f"   [{i:3d}/{len(eventos)}] {evento['id']}  M{prop['mag']:.1f}  -> {len(celdas)} celdas")

    df = pd.DataFrame(filas)
    SALIDA_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(SALIDA_CSV, index=False, encoding="utf-8")

    print(f"\nObservaciones guardadas: {len(df):,} de {df['evento_id'].nunique()} sismos")
    print(f"Respuestas individuales:  {int(df['n_respuestas'].sum()):,}")
    if sin_datos:
        print(f"Sismos sin archivo {ARCHIVO_DYFI}: {len(sin_datos)}")
    print(f"Archivo: {SALIDA_CSV}")


if __name__ == "__main__":
    main()
