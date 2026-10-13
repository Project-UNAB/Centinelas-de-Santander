# ==============================================================================
# HACKATHON: UTSmart IA Challenge 2027
# PROYECTO: Gemelo Digital Sísmico de Santander - Módulo Los Santos
# SCRIPT: Descarga y limpieza de la población municipal del DANE
# ==============================================================================
# La población no es una variable del modelo: sirve para pasar de "qué zonas se
# sacuden" a "cuántas personas viven en ellas". Se usa la proyección oficial
# del DANE para el año en curso, que es el dato más reciente que existe (el
# último censo es de 2018).
#
# Uso:  python src/preparar_poblacion.py
# ==============================================================================

import sys
import unicodedata
import urllib.request

import geopandas as gpd
import pandas as pd

from catalogo import PROCESSED_DIR, RAW_DIR

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

URL = "https://www.dane.gov.co/files/censo2018/proyecciones-de-poblacion/Municipal/PPED-AreaMun-2018-2042_VP.xlsx"
ARCHIVO_XLSX = RAW_DIR / "poblacion_dane" / "PPED-AreaMun-2018-2042_VP.xlsx"
LIMITES_GEOJSON = RAW_DIR / "limites_municipios_santander.geojson"
SALIDA_CSV = PROCESSED_DIR / "poblacion_santander.csv"

HOJA = "PobMunicipalxÁrea"
FILA_DE_ENCABEZADOS = 7
CODIGO_DE_SANTANDER = "68"
ANIO = 2026

# Nombre de cada área en el archivo y columna en la que queda
AREAS = {
    "Cabecera Municipal": "poblacion_cabecera",
    "Centros Poblados y Rural Disperso": "poblacion_rural",
    "Total": "poblacion_total",
}

# Municipios que el mapa nombra distinto al DANE (después de quitar tildes y mayúsculas)
NOMBRES_DISTINTOS = {"jordan sube": "jordan"}


def normalizar(nombre):
    """Sin tildes, en minúsculas y sin espacios repetidos, para comparar nombres."""
    sin_tildes = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    clave = " ".join(sin_tildes.lower().split())
    return NOMBRES_DISTINTOS.get(clave, clave)


def descargar():
    if ARCHIVO_XLSX.exists():
        return
    ARCHIVO_XLSX.parent.mkdir(parents=True, exist_ok=True)
    peticion = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(peticion, timeout=180) as respuesta:
        ARCHIVO_XLSX.write_bytes(respuesta.read())
    print(f"Descargado: {ARCHIVO_XLSX.name}")


def cargar_santander():
    """Población de los municipios de Santander en el año elegido, una fila por municipio."""
    crudo = pd.read_excel(ARCHIVO_XLSX, sheet_name=HOJA, header=FILA_DE_ENCABEZADOS, dtype=str)
    crudo.columns = ["cod_departamento", "departamento", "codigo_dane", "municipio_dane", "anio", "area", "poblacion"]
    crudo = crudo.dropna(subset=["codigo_dane", "anio", "poblacion"])

    santander = crudo[(crudo["cod_departamento"] == CODIGO_DE_SANTANDER) & (crudo["anio"].astype(int) == ANIO)].copy()
    santander["poblacion"] = santander["poblacion"].astype(float).round().astype(int)
    santander["area"] = santander["area"].str.strip()
    desconocidas = set(santander["area"]) - set(AREAS)
    if desconocidas:
        raise ValueError(f"Áreas no previstas en el archivo: {desconocidas}")

    tabla = santander.pivot(index=["codigo_dane", "municipio_dane"], columns="area", values="poblacion").rename(columns=AREAS)
    return tabla.reset_index()[["codigo_dane", "municipio_dane", *AREAS.values()]]


def main():
    descargar()
    poblacion = cargar_santander()

    # Emparejar con los municipios del mapa por nombre normalizado
    mapa = gpd.read_file(LIMITES_GEOJSON)[["municipio"]]
    mapa["clave"] = mapa["municipio"].map(normalizar)
    poblacion["clave"] = poblacion["municipio_dane"].map(normalizar)
    unido = mapa.merge(poblacion, on="clave", how="outer", indicator=True)

    solo_mapa = unido.loc[unido["_merge"] == "left_only", "municipio"].tolist()
    solo_dane = unido.loc[unido["_merge"] == "right_only", "municipio_dane"].tolist()
    if solo_mapa or solo_dane:
        raise ValueError(f"Municipios sin emparejar. Solo en el mapa: {solo_mapa}. Solo en el DANE: {solo_dane}")

    limpio = unido.drop(columns=["clave", "_merge"]).sort_values("municipio").reset_index(drop=True)
    limpio.insert(0, "anio", ANIO)
    for columna in AREAS.values():
        limpio[columna] = limpio[columna].astype(int)

    # Comprobaciones de coherencia antes de guardar
    assert len(limpio) == len(mapa), "Debe quedar una fila por municipio del mapa"
    assert limpio["codigo_dane"].is_unique and limpio["municipio"].is_unique
    assert (limpio["poblacion_cabecera"] + limpio["poblacion_rural"] == limpio["poblacion_total"]).all(), \
        "La cabecera más el área rural debe dar el total"
    assert (limpio["poblacion_total"] > 0).all()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    limpio.to_csv(SALIDA_CSV, index=False, encoding="utf-8")

    print(f"Municipios de Santander: {len(limpio)}   Año: {ANIO}")
    print(f"Población total: {limpio['poblacion_total'].sum():,}".replace(",", "."))
    print(f"   en cabeceras: {limpio['poblacion_cabecera'].sum():,}".replace(",", "."))
    print(f"   en área rural: {limpio['poblacion_rural'].sum():,}".replace(",", "."))
    print("Los cinco más poblados:")
    for fila in limpio.nlargest(5, "poblacion_total").itertuples():
        print(f"   {fila.municipio:20s} {fila.poblacion_total:>9,}".replace(",", "."))
    los_santos = limpio[limpio["municipio"] == "Los Santos"].iloc[0]
    print(f"Los Santos: {los_santos['poblacion_total']:,} habitantes "
          f"({los_santos['poblacion_cabecera']:,} en la cabecera)".replace(",", "."))
    print(f"Archivo: {SALIDA_CSV}")


if __name__ == "__main__":
    main()
