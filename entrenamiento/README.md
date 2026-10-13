# Entrenamiento

Tres modelos, cada uno en su carpeta con su código, sus datos procesados, sus modelos, su notebook y su PDF de registro. Lo que comparten está en `comun/` y los datos originales en `data/raw/`.

```
entrenamiento/
├── 1_sismos_los_santos/     Riesgo sísmico por zona en Los Santos (30 celdas). Es el modelo de la aplicación
├── 2_sismos_santander/      El mismo clasificador para todo Santander (358 celdas)
├── 3_viviendas_y_costos/    Viviendas afectadas por un sismo y rango de costo
├── comun/                   Catálogo, simulador de sacudida, población y exportación al backend
├── data/raw/                Datos originales, sin modificar (SGC, USGS, DANE, UNGRD, relieve)
├── docs/                    Fuentes, variables y papel de cada conjunto de datos
└── legacy/                  Versiones anteriores, sin uso
```

Cada carpeta de modelo tiene la misma forma:

```
src/               Scripts de preparación y entrenamiento
notebooks/         registro_del_entrenamiento.ipynb: cada paso, con sus tablas y gráficas
data/processed/    Conjunto de datos limpio de ese modelo
models/            Modelo entrenado, métricas e historial
reports/           registro_del_entrenamiento.pdf (el notebook exportado) y figuras
```

## Estado de cada modelo

| Modelo | Datos | Resultado en la validación | En la aplicación |
| :--- | :--- | :--- | :--- |
| 1. Sismos de Los Santos | 1.890 casos, 30 celdas | 80,7 % de exactitud y 71,9 % de F1 macro en 570 casos de prueba (persistencia: 80,2 % y 70,9 %) | Sí |
| 2. Sismos de Santander | 22.554 casos, 358 celdas | 93,4 % de exactitud y 74,3 % de F1 macro en 6.802 casos de prueba (persistencia: 90,9 % y 70,0 %) | Todavía no |
| 3. Viviendas y costos | 120 casos de 27 sismos | Error típico de un orden de magnitud, 17 % menor que la referencia. Primera aproximación: se usa como rango | Todavía no |

## Cómo se ejecuta

Con Python 3.11, desde esta carpeta (`entrenamiento/`). Dependencias: `pip install -r requirements.txt`.

```powershell
# 1. Sismos de Los Santos
py -3.11 1_sismos_los_santos/src/explorar_datos.py
py -3.11 1_sismos_los_santos/src/entrenar_modelo_sismico_los_santos.py

# 2. Sismos de Santander (con --solo-datos prepara el conjunto de datos sin entrenar)
py -3.11 2_sismos_santander/src/entrenar_modelo_sismico_santander.py --solo-datos
py -3.11 2_sismos_santander/src/entrenar_modelo_sismico_santander.py

# 3. Viviendas y costos
py -3.11 3_viviendas_y_costos/src/preparar_danos.py                # limpia y cruza los datos
py -3.11 3_viviendas_y_costos/src/entrenar_modelo_viviendas.py     # entrena y valida

# Común
py -3.11 comun/src/entrenar_modelo_sacudida.py     # simulador de sacudida
py -3.11 comun/src/preparar_poblacion.py           # población del DANE
py -3.11 comun/src/exportar_al_backend.py          # copia modelos y datos a backend/artefactos
```

Los notebooks se abren y se ejecutan desde su carpeta `notebooks/`. Usan las mismas funciones que los scripts, así que lo que muestran es lo que de verdad se ejecuta.

## Qué hay en `comun/`

| Archivo | Para qué |
| :--- | :--- |
| `src/catalogo.py` | Lee y limpia el catálogo del SGC. Lo usan los modelos 1 y 2 |
| `src/simulador.py` | Motor de sacudida. Lo usan el modelo 3, el backend y el simulador de la aplicación |
| `src/entrenar_modelo_sacudida.py` | Valida y calibra el simulador con intensidades del USGS |
| `src/preparar_poblacion.py` | Limpia la población municipal del DANE |
| `src/exportar_al_backend.py` | Lleva al backend el modelo 1, el simulador, el relieve y los datos del mapa |
| `src/descargar_*.py` | Descarga de intensidades del USGS y de límites municipales |
| `data/processed/`, `models/` | Catálogo limpio, población, grilla y modelo del simulador |

## Documentos

- `docs/DATOS_Y_VARIABLES.md`: fuentes y variables del clasificador. **Está pendiente de actualizar** al catálogo de Santander y a esta estructura.
- `docs/NUEVOS_DATOS.md`: qué conjuntos sirven para entrenar y cuáles para la plataforma, y qué se probó.
