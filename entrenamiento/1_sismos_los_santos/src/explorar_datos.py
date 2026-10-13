# ==============================================================================
# HACKATHON: UTSmart IA Challenge 2027 - Categoría Básica
# PROYECTO: Gemelo Digital Sísmico de Santander - Módulo Los Santos
# SCRIPT: Carga y exploración básica del catálogo sísmico del SGC
# ==============================================================================
# Responde las preguntas previas al modelo: qué trae el archivo, qué le falta,
# cómo se reparten los sismos en magnitud, profundidad, espacio y tiempo, y
# desde cuándo el catálogo es comparable consigo mismo.
#
# Uso:  python src/explorar_datos.py     (las figuras quedan en reports/figures)
# ==============================================================================

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

# Carpeta de este modelo; el código compartido (catálogo, simulador) está en entrenamiento/comun
CARPETA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CARPETA.parent / "comun" / "src"))
from catalogo import CATALOGO_SANTANDER_CSV as CATALOGO_GEOJSON, COLUMNAS_NUMERICAS, cargar_catalogo, leer_catalogo_crudo  # noqa: E402

FIGURES_DIR = CARPETA / "reports" / "figures"
from entrenar_modelo_sismico_los_santos import (
    ANIO_INICIO, GRID_STEP, LAT_MIN, LON_MIN, MAGNITUD_MINIMA, N_COLUMNAS, N_FILAS,
)

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Estilo de las figuras: un solo tono para magnitudes, ejes y rejilla discretos
AZUL, AZUL_CLARO = '#2a78d6', '#9ec5f4'
FONDO, TINTA, TINTA_SUAVE, REJILLA, EJE = '#fcfcfb', '#0b0b0b', '#52514e', '#e1e0d9', '#c3c2b7'
ESCALA_AZUL = LinearSegmentedColormap.from_list('azul', ['#cde2fb', '#6da7ec', '#2a78d6', '#0d366b'])
plt.rcParams.update({
    'font.family': 'sans-serif', 'font.sans-serif': ['Segoe UI', 'DejaVu Sans'], 'font.size': 10,
    'figure.facecolor': FONDO, 'axes.facecolor': FONDO, 'savefig.facecolor': FONDO,
    'axes.edgecolor': EJE, 'axes.labelcolor': TINTA_SUAVE, 'text.color': TINTA,
    'xtick.color': TINTA_SUAVE, 'ytick.color': TINTA_SUAVE,
    'axes.spines.top': False, 'axes.spines.right': False,
    'axes.grid': True, 'grid.color': REJILLA, 'grid.linewidth': 0.8, 'axes.axisbelow': True,
    'axes.titlelocation': 'left', 'axes.titlesize': 12, 'axes.titleweight': 'bold',
})


def seccion(titulo):
    print("\n" + "=" * 80)
    print(titulo)
    print("=" * 80)


def guardar(fig, nombre):
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES_DIR / nombre, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"   -> Figura: reports/figures/{nombre}")


def explorar_estructura(crudo):
    seccion("1. ESTRUCTURA DEL ARCHIVO")
    print(f"Archivo: {CATALOGO_GEOJSON.name}")
    print(f"Registros: {len(crudo):,}   Columnas: {crudo.shape[1]}")
    vacios = crudo.astype(str).apply(lambda s: s.str.strip() == '').sum()
    resumen = pd.DataFrame({
        'tipo_en_archivo': crudo.dtypes.astype(str),
        'vacios': vacios,
        '%_vacios': (100 * vacios / len(crudo)).round(2),
        'valores_distintos': crudo.nunique(),
        'ejemplo': crudo.iloc[0].astype(str),
    })
    print(resumen.to_string())
    print("\nLos números vienen como texto y los faltantes como cadenas vacías: por eso")
    print("un conteo de nulos convencional daría cero.")
    print(f"IDs duplicados: {crudo['id'].duplicated().sum()}")
    for col in ['status', 'agency', 'place']:
        print(f"{col}: {crudo[col].value_counts().to_dict()}")


def explorar_variables(cat):
    seccion("2. VARIABLES NUMÉRICAS (catálogo limpio)")
    print(f"Registros tras la limpieza: {len(cat):,}")
    print(f"Periodo: {cat['utc_time'].min():%d/%m/%Y} a {cat['utc_time'].max():%d/%m/%Y}")
    print(cat[COLUMNAS_NUMERICAS].describe().T.round(3).to_string())

    seccion("3. MAGNITUD")
    rangos = pd.cut(cat['magnitude'], bins=[0, 1, 2, 3, 4, 5, 10], right=False)
    tabla = rangos.value_counts().sort_index().to_frame('sismos')
    tabla['%'] = (100 * tabla['sismos'] / len(cat)).round(2)
    print(tabla.to_string())
    print("\nLos cinco mayores:")
    print(cat.nlargest(5, 'magnitude')[['utc_time', 'magnitude', 'mag_type', 'depth']].to_string(index=False))
    print("\nTipo de magnitud (cambia de escala en 2018):")
    print(cat['mag_type'].value_counts().head(5).to_string())

    seccion("4. PROFUNDIDAD")
    prof = cat['depth']
    print(f"Media {prof.mean():.1f} km, mediana {prof.median():.0f} km, desviación {prof.std():.1f} km")
    print(f"Entre 140 y 160 km:  {prof.between(140, 160).mean():.1%}")
    print(f"A más de 100 km:     {(prof > 100).mean():.2%}")
    print(f"A menos de 40 km:    {(prof < 40).sum()} sismos ({(prof < 40).mean():.2%})")

    seccion("5. EVOLUCIÓN EN EL TIEMPO")
    cat = cat.assign(anio=cat['utc_time'].dt.year)
    por_anio = cat.groupby('anio').agg(
        sismos=('id', 'size'),
        magnitud_mediana=('magnitude', 'median'),
        magnitud_minima=('magnitude', 'min'),
        estaciones_mediana=('nst', 'median'),
    )
    por_anio[f'sismos_M>={MAGNITUD_MINIMA}'] = cat[cat['magnitude'] >= MAGNITUD_MINIMA].groupby('anio').size()
    print(por_anio.to_string())
    print("\nEl total anual crece porque la red detecta sismos cada vez más pequeños, no")
    print(f"porque haya más sismicidad: el conteo de M>={MAGNITUD_MINIMA} es estable desde {ANIO_INICIO}.")
    print(f"Por eso el modelo usa solo sismos M>={MAGNITUD_MINIMA} desde {ANIO_INICIO}. El último año está incompleto.")
    return por_anio


def figura_por_anio(por_anio):
    fig, ejes = plt.subplots(2, 1, figsize=(9, 5.6), sharex=True)
    series = [('sismos', 'Todos los sismos registrados por año'),
              (f'sismos_M>={MAGNITUD_MINIMA}', f'Sismos de magnitud {MAGNITUD_MINIMA} o mayor por año')]
    for eje, (columna, titulo) in zip(ejes, series):
        eje.bar(por_anio.index, por_anio[columna], width=0.7, color=AZUL)
        eje.set_title(titulo)
        eje.grid(axis='x', visible=False)
        eje.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}".replace(',', '.'))
    ejes[1].axvline(ANIO_INICIO - 0.5, color=TINTA_SUAVE, linewidth=1, linestyle='--')
    ejes[1].text(ANIO_INICIO - 0.65, ejes[1].get_ylim()[1] * 0.97, f'el modelo usa desde {ANIO_INICIO} →',
                 color=TINTA_SUAVE, fontsize=9, va='top', ha='right')
    ejes[1].set_xticks(por_anio.index[::2])
    ejes[1].set_xlabel('Año (2026 incompleto: hasta el 9 de octubre)')
    fig.tight_layout()
    guardar(fig, '01_sismos_por_anio.png')


def figura_magnitud(cat):
    bordes = np.arange(0.05, 6.6, 0.1)
    fig, eje = plt.subplots(figsize=(9, 4))
    eje.hist(cat['magnitude'], bins=bordes, color=AZUL, edgecolor=FONDO, linewidth=0.6)
    eje.set_yscale('log')
    eje.axvline(MAGNITUD_MINIMA - 0.05, color=TINTA_SUAVE, linewidth=1, linestyle='--')
    eje.text(MAGNITUD_MINIMA + 0.03, eje.get_ylim()[1] * 0.5, f'el modelo usa M ≥ {MAGNITUD_MINIMA}',
             color=TINTA_SUAVE, fontsize=9, va='top')
    eje.set_title('Distribución de magnitudes (escala logarítmica)')
    eje.set_xlabel('Magnitud')
    eje.set_ylabel('Número de sismos')
    eje.grid(axis='x', visible=False)
    fig.tight_layout()
    guardar(fig, '02_distribucion_magnitud.png')


def figura_profundidad(cat):
    fig, eje = plt.subplots(figsize=(9, 4))
    eje.hist(cat['depth'], bins=np.arange(0, 216, 2), color=AZUL, edgecolor=FONDO, linewidth=0.4)
    eje.set_title('Distribución de profundidades: casi todo ocurre entre 140 y 160 km')
    eje.set_xlabel('Profundidad (km)')
    eje.set_ylabel('Número de sismos')
    eje.grid(axis='x', visible=False)
    eje.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}".replace(',', '.'))
    fig.tight_layout()
    guardar(fig, '03_distribucion_profundidad.png')


def figura_mapa(cat):
    homogeneo = cat[(cat['utc_time'].dt.year >= ANIO_INICIO) & (cat['magnitude'] >= MAGNITUD_MINIMA)]
    lat_max, lon_max = LAT_MIN + N_FILAS * GRID_STEP, LON_MIN + N_COLUMNAS * GRID_STEP
    fig, eje = plt.subplots(figsize=(8, 6))
    densidad = eje.hexbin(homogeneo['longitude'], homogeneo['latitude'], gridsize=45, mincnt=1,
                          cmap=ESCALA_AZUL, linewidths=0.2, edgecolors=FONDO,
                          extent=(LON_MIN, lon_max, LAT_MIN, lat_max))
    # Celdas de la grilla que usa el clasificador
    for i in range(N_FILAS + 1):
        eje.axhline(LAT_MIN + i * GRID_STEP, color=EJE, linewidth=0.8)
    for j in range(N_COLUMNAS + 1):
        eje.axvline(LON_MIN + j * GRID_STEP, color=EJE, linewidth=0.8)
    eje.set_xlim(LON_MIN, lon_max)
    eje.set_ylim(LAT_MIN, lat_max)
    eje.set_aspect(1 / np.cos(np.radians(LAT_MIN + N_FILAS * GRID_STEP / 2)))
    eje.grid(False)
    eje.set_title(f'Epicentros M ≥ {MAGNITUD_MINIMA} desde {ANIO_INICIO} y grilla de {GRID_STEP}° del modelo')
    eje.set_xlabel('Longitud')
    eje.set_ylabel('Latitud')
    barra = fig.colorbar(densidad, ax=eje, shrink=0.8, pad=0.02)
    barra.set_label('Sismos por hexágono')
    barra.outline.set_visible(False)
    fig.tight_layout()
    guardar(fig, '04_mapa_epicentros.png')


def main():
    crudo = leer_catalogo_crudo()
    explorar_estructura(crudo)
    cat = cargar_catalogo()
    por_anio = explorar_variables(cat)

    seccion("6. FIGURAS")
    figura_por_anio(por_anio)
    figura_magnitud(cat)
    figura_profundidad(cat)
    figura_mapa(cat)


if __name__ == "__main__":
    main()
