# ==============================================================================
# HACKATHON: UTSmart IA Challenge 2027
# PROYECTO: Gemelo Digital Sísmico de Santander - Módulo Los Santos
# SCRIPT: Limpieza de los datos de daños por sismo (UNGRD, DANE y USGS)
# ==============================================================================
# Deja listo el conjunto de datos del modelo de viviendas afectadas: una fila
# por municipio y sismo, con las viviendas que había, las que se averiaron o
# destruyeron y la intensidad con que llegó el sismo.
#
#   1. Une las emergencias de la UNGRD de 2019, 2020 y 2023 a 2025, que vienen
#      en archivos con columnas distintas.
#   2. A cada emergencia por sismo le añade las viviendas del municipio en ese
#      año (DANE) y sus coordenadas (DIVIPOLA).
#   3. La UNGRD no dice qué sismo fue ni con qué intensidad: se busca en el
#      catálogo del USGS el sismo de esos días que más sacudió al municipio y
#      se calcula su intensidad con el motor del simulador.
#
# Uso:  python 3_viviendas_y_costos/src/preparar_danos.py
# ==============================================================================

import json
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

# Carpeta de este modelo; el código compartido (catálogo, simulador) está en entrenamiento/comun
CARPETA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CARPETA.parent / "comun" / "src"))
import simulador as sim  # noqa: E402
from catalogo import RAW_DIR  # noqa: E402

PROCESSED_DIR = CARPETA / "data" / "processed"

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

DANOS_DIR = RAW_DIR / "danos_y_costos"
ARCHIVOS_UNGRD = sorted((DANOS_DIR / "ungrd_emergencias").glob("emergencias_ungrd_*.csv"))
VIVIENDAS_XLSX = DANOS_DIR / "dane_viviendas_y_hogares" / "proyecciones_viviendas_dptal_mpal_2018_2042.xlsx"
DIVIPOLA_CSV = DANOS_DIR / "dane_divipola" / "divipola_municipios.csv"
USGS_GEOJSON = DANOS_DIR / "usgs_catalogo_colombia" / "sismos_usgs_colombia_2019_2025.geojson"

EMERGENCIAS_CSV = PROCESSED_DIR / "emergencias_ungrd.csv"
DANOS_CSV = PROCESSED_DIR / "danos_por_sismo.csv"

HOJA_DE_VIVIENDAS = "Proye total viviendas mpio"
FILA_DE_ANIOS, PRIMERA_FILA_DE_DATOS = 9, 11

# Cada archivo de la UNGRD nombra distinto las mismas columnas
NOMBRES = {
    'divipola': ['divipola', 'codificacion_segun_divipola'],
    'fallecidos': ['fallecidos', 'muertos'],
    'heridos': ['heridos'],
    'personas': ['personas'],
    'familias': ['familias'],
    'viviendas_destruidas': ['viviendas_destruidas', 'viv_destru'],
    'viviendas_averiadas': ['viviendas_averiadas', 'vivivviendas_averiadas', 'vivivendas_averiadas', 'vivivienda_averiadas', 'viviviendas_averiadas', 'viv_aver'],
    'apoyo_total_cop': ['valor_total_apoyo_del_fngrd', 'apoyo_total_del_fngrd', 'valor_apoyo_total_del_fngrd', 'recursos_ejecutados'],
}
CONTEOS = ['fallecidos', 'heridos', 'personas', 'familias', 'viviendas_destruidas', 'viviendas_averiadas']

# El sismo de una emergencia se busca desde dos días antes de la fecha del reporte
DIAS_ANTES = 2
HORAS_DE_COLOMBIA = -5
# Municipios y departamentos que la UNGRD escribe distinto al DANE (ya sin tildes ni mayúsculas)
EQUIVALENCIAS = {
    'bogota d.c.': 'bogota, d.c.', 'bogota d.c': 'bogota, d.c.', 'bogota': 'bogota, d.c.',
    'archipielago de san andres': 'archipielago de san andres, providencia y santa catalina',
    'san andres': 'archipielago de san andres, providencia y santa catalina',
    'valle': 'valle del cauca', 'guajira': 'la guajira',
    'don matias': 'donmatias', 'mompos': 'santa cruz de mompox', 'canton de san pablo': 'el canton del san pablo',
    'san juan de rio seco': 'san juan de rioseco',
}


def normalizar(texto):
    """Sin tildes, en minúsculas y sin espacios repetidos, para comparar nombres."""
    sin_tildes = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    clave = " ".join(sin_tildes.lower().split())
    return EQUIVALENCIAS.get(clave, clave)


def nombre_de_columna(texto):
    return re.sub(r'[^a-z0-9]+', '_', normalizar(texto)).strip('_')


def a_numero(serie):
    """Conteos que llegan como texto ("1.234", "No Registra"): lo que no es número cuenta como cero."""
    return pd.to_numeric(serie.astype(str).str.replace(r'[^0-9]', '', regex=True), errors='coerce').fillna(0).astype(int)


def a_pesos(serie):
    """Valores en pesos que llegan como "$ 1,234,567.00", "$    - 0" o "No Registra"."""
    def uno(valor):
        valor = re.sub(r'[^0-9,.]', '', str(valor))
        if not re.search(r'\d', valor):
            return 0.0
        # Uno o dos dígitos tras el último separador son decimales; el resto, separadores de miles
        decimales = re.search(r'[.,](\d{1,2})$', valor)
        entero = valor[:decimales.start()] if decimales else valor
        return float(re.sub(r'[.,]', '', entero) or 0) + (float('0.' + decimales.group(1)) if decimales else 0.0)
    return serie.map(uno)


# ==============================================================================
# PASO 1: EMERGENCIAS DE LA UNGRD EN UN SOLO FORMATO
# ==============================================================================
def unir_emergencias():
    partes = []
    for ruta in ARCHIVOS_UNGRD:
        crudo = pd.read_csv(ruta, dtype=str)
        crudo.columns = [nombre_de_columna(c) for c in crudo.columns]
        limpio = pd.DataFrame({
            'archivo': ruta.name,
            'fecha': pd.to_datetime(crudo['fecha'], format='%m/%d/%Y %I:%M:%S %p', errors='coerce'),
            'departamento': crudo['departamento'].str.strip(),
            'municipio': crudo['municipio'].str.strip(),
            'evento': crudo['evento'].str.upper().str.strip(),
        })
        for destino, candidatos in NOMBRES.items():
            origen = next((c for c in candidatos if c in crudo.columns), None)
            if origen is None:
                raise KeyError(f"{ruta.name}: no se encontró la columna de «{destino}» entre {list(crudo.columns)[:25]}")
            limpio[destino] = crudo[origen]
        partes.append(limpio)
        print(f"   -> {ruta.name}: {len(crudo):,} emergencias")

    emergencias = pd.concat(partes, ignore_index=True)
    for columna in CONTEOS:
        emergencias[columna] = a_numero(emergencias[columna])
    emergencias['apoyo_total_cop'] = a_pesos(emergencias['apoyo_total_cop'])
    sin_fecha = int(emergencias['fecha'].isna().sum())
    emergencias = emergencias.dropna(subset=['fecha', 'municipio']).reset_index(drop=True)
    print(f"   -> Total: {len(emergencias):,} emergencias ({sin_fecha} sin fecha, descartadas)")
    return emergencias


# ==============================================================================
# PASO 2: VIVIENDAS Y COORDENADAS DE CADA MUNICIPIO
# ==============================================================================
def cargar_municipios():
    """Código, nombre y coordenadas de cada municipio (DIVIPOLA del DANE)."""
    municipios = pd.read_csv(DIVIPOLA_CSV, dtype=str)
    municipios.columns = ['cod_departamento', 'departamento_dane', 'codigo_dane', 'municipio_dane', 'tipo', 'lon', 'lat']
    for columna in ('lon', 'lat'):
        municipios[columna] = municipios[columna].str.replace(',', '.').astype(float)
    municipios['clave'] = municipios['departamento_dane'].map(normalizar) + '|' + municipios['municipio_dane'].map(normalizar)
    return municipios.drop_duplicates('clave')


def cargar_viviendas():
    """Total de viviendas por municipio y año (proyección del DANE), en formato largo."""
    crudo = pd.read_excel(VIVIENDAS_XLSX, sheet_name=HOJA_DE_VIVIENDAS, header=None, dtype=str)
    anios = [int(float(a)) for a in crudo.iloc[FILA_DE_ANIOS, 5:].dropna()]
    datos = crudo.iloc[PRIMERA_FILA_DE_DATOS:, :5 + len(anios)]
    datos.columns = ['cod_departamento', 'departamento', 'codigo_dane', 'municipio', 'area', *anios]
    datos = datos[datos['area'].str.strip() == 'Total'].dropna(subset=['codigo_dane'])
    largo = datos.melt(id_vars='codigo_dane', value_vars=anios, var_name='anio', value_name='viviendas')
    largo['viviendas'] = pd.to_numeric(largo['viviendas'], errors='coerce').round().astype('Int64')
    largo['anio'] = largo['anio'].astype(int)
    return largo.dropna(subset=['viviendas'])


# ==============================================================================
# PASO 3: QUÉ SISMO FUE Y CON QUÉ INTENSIDAD LLEGÓ
# ==============================================================================
def cargar_sismos_usgs():
    with open(USGS_GEOJSON, encoding='utf-8') as f:
        features = json.load(f)['features']
    sismos = pd.DataFrame([{
        'sismo_id': ft['id'],
        'hora_utc': pd.to_datetime(ft['properties']['time'], unit='ms', utc=True),
        'magnitud': ft['properties']['mag'],
        'lon': ft['geometry']['coordinates'][0],
        'lat': ft['geometry']['coordinates'][1],
        'prof_km': ft['geometry']['coordinates'][2],
    } for ft in features]).dropna(subset=['magnitud', 'prof_km'])
    # Las emergencias se fechan con la hora de Colombia
    sismos['fecha_local'] = (sismos['hora_utc'] + pd.Timedelta(hours=HORAS_DE_COLOMBIA)).dt.tz_localize(None).dt.normalize()
    sismos['prof_km'] = sismos['prof_km'].clip(lower=1.0)
    return sismos


def sismo_que_mas_sacudio(fila, sismos):
    """Entre los sismos de esos días, el que produjo la mayor intensidad calculada en el municipio."""
    candidatos = sismos[(sismos['fecha_local'] <= fila['fecha']) & (sismos['fecha_local'] >= fila['fecha'] - pd.Timedelta(days=DIAS_ANTES))]
    if candidatos.empty:
        return pd.Series({'sismo_id': None, 'magnitud': np.nan, 'prof_km': np.nan, 'dist_epicentral_km': np.nan, 'intensidad_mmi': np.nan})
    distancia = sim.distancia_epicentral_km(fila['lat'], fila['lon'], candidatos['lat'].to_numpy(), candidatos['lon'].to_numpy())
    # Cálculo físico sin la calibración del simulador, que solo vale para el Nido de Bucaramanga
    intensidad = sim.mmi_fisico(candidatos['magnitud'].to_numpy(), sim.distancia_hipocentral_km(distancia, candidatos['prof_km'].to_numpy()),
                                candidatos['prof_km'].to_numpy())
    mayor = int(np.argmax(intensidad))
    elegido = candidatos.iloc[mayor]
    return pd.Series({'sismo_id': elegido['sismo_id'], 'magnitud': elegido['magnitud'], 'prof_km': elegido['prof_km'],
                      'dist_epicentral_km': round(float(distancia[mayor]), 1), 'intensidad_mmi': round(float(intensidad[mayor]), 2)})


def main():
    print("=" * 80)
    print("DATOS DE DAÑOS POR SISMO: UNGRD + DANE + USGS")
    print("=" * 80)

    print("\n1. Emergencias de la UNGRD...")
    emergencias = unir_emergencias()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    emergencias.to_csv(EMERGENCIAS_CSV, index=False, encoding='utf-8')
    por_evento = emergencias['evento'].value_counts()
    print(f"   -> Tipos de evento más frecuentes: {', '.join(f'{e} ({n:,})' for e, n in por_evento.head(5).items())}")

    print("\n2. Emergencias por sismo, con viviendas y coordenadas del municipio...")
    sismos_ungrd = emergencias[emergencias['evento'].str.contains('SISMO', na=False)].copy()
    sismos_ungrd['clave'] = sismos_ungrd['departamento'].map(normalizar) + '|' + sismos_ungrd['municipio'].map(normalizar)
    sismos_ungrd['anio'] = sismos_ungrd['fecha'].dt.year
    con_municipio = sismos_ungrd.merge(cargar_municipios()[['clave', 'codigo_dane', 'lat', 'lon']], on='clave', how='left')
    sin_municipio = con_municipio[con_municipio['codigo_dane'].isna()]
    print(f"   -> Emergencias por sismo: {len(sismos_ungrd)}   Sin municipio reconocido: {len(sin_municipio)}"
          + (f" ({', '.join(sorted(set(sin_municipio['departamento'] + ' / ' + sin_municipio['municipio'])))})" if len(sin_municipio) else ""))
    danos = con_municipio.dropna(subset=['codigo_dane']).merge(cargar_viviendas(), on=['codigo_dane', 'anio'], how='left')
    print(f"   -> Sin viviendas del DANE para ese municipio y año: {int(danos['viviendas'].isna().sum())}")

    print("\n3. Sismo e intensidad de cada emergencia (catálogo del USGS)...")
    usgs = cargar_sismos_usgs()
    print(f"   -> Sismos de magnitud 4 o mayor en el catálogo: {len(usgs):,}")
    danos = pd.concat([danos, danos.apply(sismo_que_mas_sacudio, axis=1, sismos=usgs)], axis=1)
    print(f"   -> Emergencias sin ningún sismo del catálogo en esos días: {int(danos['sismo_id'].isna().sum())}")

    # Varias emergencias del mismo municipio por el mismo sismo son actualizaciones del mismo daño: se deja la mayor
    danos['viviendas_afectadas'] = danos['viviendas_averiadas'] + danos['viviendas_destruidas']
    danos = (danos.dropna(subset=['sismo_id', 'viviendas']).sort_values('viviendas_afectadas', ascending=False)
             .drop_duplicates(['codigo_dane', 'sismo_id']).sort_values(['fecha', 'departamento', 'municipio']))
    danos['proporcion_afectada'] = (danos['viviendas_afectadas'] / danos['viviendas'].astype(float)).round(6)
    columnas = ['fecha', 'departamento', 'municipio', 'codigo_dane', 'lat', 'lon', 'viviendas', 'viviendas_averiadas', 'viviendas_destruidas',
                'viviendas_afectadas', 'proporcion_afectada', 'personas', 'familias', 'heridos', 'fallecidos', 'apoyo_total_cop',
                'sismo_id', 'magnitud', 'prof_km', 'dist_epicentral_km', 'intensidad_mmi']
    danos[columnas].to_csv(DANOS_CSV, index=False, encoding='utf-8')

    print("\n" + "=" * 80)
    print("CONJUNTO DE DATOS LISTO")
    print("=" * 80)
    print(f"Casos (municipio y sismo): {len(danos)}   Con viviendas afectadas: {int((danos['viviendas_afectadas'] > 0).sum())}"
          f"   Sismos distintos: {danos['sismo_id'].nunique()}")
    print(f"Intensidad calculada: de {danos['intensidad_mmi'].min():.1f} a {danos['intensidad_mmi'].max():.1f}"
          f"   Magnitud: de {danos['magnitud'].min():.1f} a {danos['magnitud'].max():.1f}")
    tramos = pd.cut(danos['intensidad_mmi'], [0, 3, 4, 5, 6, 7, 10], labels=['hasta III', 'III-IV', 'IV-V', 'V-VI', 'VI-VII', 'más de VII'])
    resumen = danos.groupby(tramos, observed=True).agg(
        casos=('sismo_id', 'size'), con_dano=('viviendas_afectadas', lambda v: int((v > 0).sum())),
        viviendas_afectadas=('viviendas_afectadas', 'sum'), proporcion_mediana=('proporcion_afectada', 'median'))
    print("\nDaño según la intensidad calculada:")
    print(resumen.to_string())
    print(f"\nArchivos: {EMERGENCIAS_CSV.name} ({len(emergencias):,} filas) y {DANOS_CSV.name} ({len(danos)} filas), en data/processed")


if __name__ == "__main__":
    main()
