# ==============================================================================
# HACKATHON: UTSmart IA Challenge 2027
# PROYECTO: Gemelo Digital Sísmico de Santander
# SCRIPT: Modelo de viviendas afectadas por un sismo y rango de costo
# ==============================================================================
# Aprende, de sismos colombianos reales (UNGRD, 2019 a 2025), qué proporción de
# las viviendas de un municipio resulta afectada según la intensidad con que le
# llega el sismo. Con las viviendas de cada municipio (DANE) eso se convierte en
# un número de viviendas, y con el gasto de atención por vivienda (UNGRD), en un
# rango de costo.
#
#   - Caso:      un municipio en un sismo (ver preparar_danos.py).
#   - Objetivo:  proporción de viviendas afectadas (averiadas + destruidas).
#   - Validación: se deja fuera un sismo completo cada vez, de modo que el
#                modelo nunca ve el sismo que debe predecir.
#   - Salida:    un valor central y un rango, porque el daño real varía mucho
#                entre municipios con la misma intensidad.
#
# Uso:  python 3_viviendas_y_costos/src/entrenar_modelo_viviendas.py
# ==============================================================================

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.model_selection import LeaveOneGroupOut

CARPETA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CARPETA / "src"))
import modelo_de_danos as md  # noqa: E402

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

DANOS_CSV = CARPETA / "data" / "processed" / "danos_por_sismo.csv"
EMERGENCIAS_CSV = CARPETA / "data" / "processed" / "emergencias_ungrd.csv"
MODELO_PKL = CARPETA / "models" / "modelo_viviendas_afectadas.pkl"
METRICAS_JSON = CARPETA / "models" / "metricas_viviendas.json"

RANDOM_STATE = 42
VARIABLES_DE_FUENTE = ['intensidad_mmi', 'magnitud', 'prof_km', 'dist_epicentral_km']


# ==============================================================================
# CANDIDATOS
# ==============================================================================
# Todos predicen el logaritmo de la proporción afectada (ver modelo_de_danos.a_log)
class Constante:
    """Referencia sin aprendizaje: siempre la mediana de lo visto."""
    def fit(self, X, y):
        self.valor = float(np.median(y))
        return self

    def predict(self, X):
        return np.full(len(X), self.valor)


class CurvaLogistica:
    """
    Curva en S clásica de daño: la proporción afectada crece con la intensidad
    entre 0 y 1. Se ajusta como una regresión logística sobre proporciones.
    """
    def fit(self, X, y):
        proporcion = np.clip(md.de_log(y), 0, 1)
        # Cada caso cuenta como «afectada» con peso p y como «no afectada» con peso 1 - p
        self.modelo = LogisticRegression(C=1e6, max_iter=5000).fit(
            np.vstack([X, X]), np.r_[np.ones(len(X)), np.zeros(len(X))], sample_weight=np.r_[proporcion, 1 - proporcion])
        return self

    def predict(self, X):
        return md.a_log(self.modelo.predict_proba(X)[:, 1])


CANDIDATOS = {
    'constante': ('Referencia: siempre la mediana', ['intensidad_mmi'], Constante),
    'lineal': ('Recta sobre el logaritmo de la proporción, según la intensidad', ['intensidad_mmi'], LinearRegression),
    'logistica': ('Curva logística según la intensidad', ['intensidad_mmi'], CurvaLogistica),
    'bosque': ('Random Forest con intensidad, magnitud, profundidad y distancia', VARIABLES_DE_FUENTE,
               lambda: RandomForestRegressor(300, max_depth=4, min_samples_leaf=5, random_state=RANDOM_STATE, n_jobs=-1)),
}


def validar_por_sismo(datos):
    """Predicción de cada caso con un modelo que no vio su sismo."""
    y = md.a_log(datos['proporcion_afectada'])
    predicciones = {}
    for nombre, (_, columnas, crear) in CANDIDATOS.items():
        X = datos[columnas].to_numpy()
        pred = np.zeros(len(datos))
        for entrena, prueba in LeaveOneGroupOut().split(X, y, datos['sismo_id']):
            pred[prueba] = crear().fit(X[entrena], y[entrena]).predict(X[prueba])
        predicciones[nombre] = pred
    return y, predicciones


def calcular_metricas(datos, y, pred):
    error = pred - y
    viviendas = datos['viviendas'].to_numpy()
    return {
        'error_tipico_log10': float(np.sqrt(np.mean(error ** 2))),
        'error_absoluto_log10': float(np.mean(np.abs(error))),
        'dentro_de_un_factor_10': float(np.mean(np.abs(error) <= 1)),
        'correlacion_de_rangos': float(pd.Series(pred).corr(pd.Series(y), method='spearman')) if np.std(pred) > 0 else 0.0,
        'viviendas_predichas': float((md.de_log(pred) * viviendas).sum()),
        'viviendas_reales': float(datos['viviendas_afectadas'].sum()),
    }


def costo_por_vivienda(emergencias):
    """Gasto de atención por vivienda afectada, en las emergencias que registran valor (de cualquier tipo)."""
    afectadas = emergencias['viviendas_averiadas'] + emergencias['viviendas_destruidas']
    con_valor = emergencias[(emergencias['apoyo_total_cop'] > 0) & (afectadas > 0)]
    por_vivienda = con_valor['apoyo_total_cop'] / afectadas[con_valor.index]
    return {
        'bajo': float(por_vivienda.quantile(0.25)), 'medio': float(por_vivienda.median()), 'alto': float(por_vivienda.quantile(0.75)),
        'emergencias': int(len(con_valor)), 'de_sismos': int(con_valor['evento'].str.contains('SISMO').sum()),
    }


def main():
    print("=" * 80)
    print("MODELO DE VIVIENDAS AFECTADAS POR UN SISMO")
    print("=" * 80)
    datos = pd.read_csv(DANOS_CSV)
    print(f"\n1. Datos: {len(datos)} casos (municipio y sismo) de {datos['sismo_id'].nunique()} sismos; "
          f"{int((datos['viviendas_afectadas'] > 0).sum())} con viviendas afectadas")
    print(f"   -> Intensidad de {datos['intensidad_mmi'].min():.1f} a {datos['intensidad_mmi'].max():.1f}; "
          f"proporción afectada de 0 a {datos['proporcion_afectada'].max():.1%}")

    print("\n2. Validación dejando fuera un sismo completo cada vez...")
    y, predicciones = validar_por_sismo(datos)
    metricas = {nombre: calcular_metricas(datos, y, pred) for nombre, pred in predicciones.items()}
    print(f"\n{'Candidato':66s} {'Error':>6s} {'Factor 10':>10s} {'Rangos':>7s} {'Viviendas':>10s}")
    for nombre, m in metricas.items():
        print(f"{CANDIDATOS[nombre][0]:66s} {m['error_tipico_log10']:6.2f} {m['dentro_de_un_factor_10']:10.0%} "
              f"{m['correlacion_de_rangos']:7.2f} {m['viviendas_predichas']:10,.0f}")
    print(f"{'(viviendas afectadas reales)':66s} {'':6s} {'':10s} {'':7s} {metricas['constante']['viviendas_reales']:10,.0f}")
    print("   Error: error típico en órdenes de magnitud (0,5 = equivocarse por un factor 3). Menos es mejor.")

    # Se elige el de menor error típico; a igualdad práctica, el más simple
    elegido = min((n for n in CANDIDATOS if n != 'constante'), key=lambda n: metricas[n]['error_tipico_log10'])
    mejora = 1 - metricas[elegido]['error_tipico_log10'] / metricas['constante']['error_tipico_log10']
    print(f"\n   -> Modelo elegido: {CANDIDATOS[elegido][0]}")
    print(f"      Reduce el error de la referencia en un {mejora:.0%}")

    print("\n3. Modelo final con todos los casos...")
    _, columnas, crear = CANDIDATOS[elegido]
    estimador = crear().fit(datos[columnas].to_numpy(), y)
    # El rango sale de cuánto se equivocó el modelo con sismos que no había visto
    residuo = y - predicciones[elegido]
    rango = {'bajo': float(np.quantile(residuo, 0.25)), 'alto': float(np.quantile(residuo, 0.75))}
    # Parte de las viviendas afectadas que queda destruida, según la intensidad
    con_dano = datos[datos['viviendas_afectadas'] > 0]
    fuertes = con_dano['intensidad_mmi'] >= md.INTENSIDAD_FUERTE
    destruidas = {
        'moderada': float(con_dano.loc[~fuertes, 'viviendas_destruidas'].sum() / con_dano.loc[~fuertes, 'viviendas_afectadas'].sum()),
        'fuerte': float(con_dano.loc[fuertes, 'viviendas_destruidas'].sum() / con_dano.loc[fuertes, 'viviendas_afectadas'].sum()),
        'casos_fuertes': int(fuertes.sum()),
    }
    costos = costo_por_vivienda(pd.read_csv(EMERGENCIAS_CSV))

    modelo = {
        'nombre': elegido, 'descripcion': CANDIDATOS[elegido][0], 'variables': columnas, 'estimador': estimador,
        'rango_log10': rango, 'proporcion_destruida': destruidas, 'costo_por_vivienda_cop': costos,
        'intensidad_validada': [float(datos['intensidad_mmi'].min()), float(datos['intensidad_mmi'].max())],
        'tipo_de_intensidad': 'cálculo físico sin calibrar (simulador.mmi_fisico)',
        'version_sklearn': sklearn.__version__,
    }
    MODELO_PKL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(modelo, MODELO_PKL)

    print(f"   -> Rango (del 25 % al 75 % de los casos): de x{10 ** rango['bajo']:.2f} a x{10 ** rango['alto']:.1f} el valor central")
    print(f"   -> Viviendas destruidas entre las afectadas: {destruidas['moderada']:.0%} por debajo de intensidad {md.INTENSIDAD_FUERTE:.0f} "
          f"y {destruidas['fuerte']:.0%} por encima ({destruidas['casos_fuertes']} casos)")
    print(f"   -> Gasto de atención por vivienda (COP): bajo {costos['bajo']:,.0f}, medio {costos['medio']:,.0f}, alto {costos['alto']:,.0f} "
          f"({costos['emergencias']} emergencias, {costos['de_sismos']} de sismos)")
    print("\n   Curva del modelo (un municipio de 10.000 viviendas):")
    for mmi in (3, 4, 5, 6, 6.5, 7, 8):
        e = md.estimar(modelo, pd.DataFrame({'intensidad_mmi': [mmi], 'magnitud': [6.0], 'prof_km': [30.0], 'dist_epicentral_km': [30.0]}), [10000])
        fuera = '' if mmi <= modelo['intensidad_validada'][1] else '   (fuera de lo observado)'
        print(f"      intensidad {mmi:>3}: {e['afectadas'][0]:7,.0f} viviendas (de {e['afectadas_bajo'][0]:,.0f} a {e['afectadas_alto'][0]:,.0f}){fuera}")

    with open(METRICAS_JSON, 'w', encoding='utf-8') as f:
        json.dump({
            'modelo_elegido': elegido, 'validacion': 'dejando fuera un sismo completo cada vez',
            'casos': len(datos), 'sismos': int(datos['sismo_id'].nunique()), 'casos_con_dano': int((datos['viviendas_afectadas'] > 0).sum()),
            'intensidad_validada': modelo['intensidad_validada'],
            'candidatos': {n: {'descripcion': CANDIDATOS[n][0], **m} for n, m in metricas.items()},
            'rango_log10': rango, 'proporcion_destruida': destruidas, 'costo_por_vivienda_cop': costos,
            'validacion_por_caso': {'observado_log10': np.round(y, 3).tolist(), 'predicho_log10': np.round(predicciones[elegido], 3).tolist(),
                                    'intensidad_mmi': datos['intensidad_mmi'].tolist()},
        }, f, ensure_ascii=False, indent=2)
    print(f"\n   -> Modelo:   {MODELO_PKL}")
    print(f"   -> Métricas: {METRICAS_JSON}")
    print("=" * 80)


if __name__ == "__main__":
    main()
