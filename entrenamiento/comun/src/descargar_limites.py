# ==============================================================================
# HACKATHON: UTSmart IA Challenge 2027
# PROYECTO: Gemelo Digital Sísmico de Santander - Módulo Los Santos
# SCRIPT: Descarga de los límites municipales de Santander
# ==============================================================================
# Los límites solo se usan para dibujar el mapa y recortar la grilla; no son
# variables del modelo. Los municipios provienen del DANE (2020), distribuidos
# por geoBoundaries con licencia CC BY 4.0. El contorno del departamento
# (OpenStreetMap) se usa únicamente para elegir qué municipios son de Santander.
#
# Uso:  python src/descargar_limites.py
# ==============================================================================

import json
import urllib.request

import geopandas as gpd

from catalogo import RAW_DIR

API = "https://www.geoboundaries.org/api/current/gbOpen/COL/{nivel}/"
SALIDA_GEOJSON = RAW_DIR / "limites_municipios_santander.geojson"
MUNICIPIOS_ESPERADOS = 87


def descargar_nivel(nivel):
    with urllib.request.urlopen(API.format(nivel=nivel), timeout=60) as respuesta:
        metadatos = json.load(respuesta)
    print(f"   {nivel}: fuente {metadatos['boundarySource']} ({metadatos['boundaryYearRepresented']})")
    return gpd.read_file(metadatos['simplifiedGeometryGeoJSON'])


def main():
    print("Descargando límites de Colombia desde geoBoundaries...")
    departamentos = descargar_nivel("ADM1")
    municipios = descargar_nivel("ADM2")

    santander = departamentos[departamentos['shapeName'] == 'Santander'].geometry.iloc[0]
    dentro = municipios.geometry.representative_point().within(santander)
    resultado = municipios.loc[dentro, ['shapeName', 'geometry']].rename(columns={'shapeName': 'municipio'})
    resultado = resultado.sort_values('municipio').reset_index(drop=True)

    resultado.to_file(SALIDA_GEOJSON, driver="GeoJSON")
    print(f"Municipios de Santander: {len(resultado)} (esperados: {MUNICIPIOS_ESPERADOS})")
    print(f"¿Incluye Los Santos? {'Los Santos' in set(resultado['municipio'])}")
    print(f"Archivo: {SALIDA_GEOJSON}")


if __name__ == "__main__":
    main()
