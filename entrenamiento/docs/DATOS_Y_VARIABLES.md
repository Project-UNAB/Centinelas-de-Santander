# Datos y variables

Documento de soporte para la categoría Básica del UTSmart IA Challenge 2027: de dónde salen los datos, cómo se limpian y por qué se incluye cada variable del modelo.

## 1. Fuentes de datos

### Fuente principal: catálogo sísmico del SGC

| | |
| :--- | :--- |
| **Entidad** | Servicio Geológico Colombiano (SGC) — Red Sismológica Nacional de Colombia |
| **Conjunto** | Catálogo de sismicidad |
| **Archivo** | `data/raw/Los_santos - 01-01-2006 - 12-10-2026.geojson` |
| **Fecha de descarga** | 12 de octubre de 2026 |
| **Filtros usados** | 1. Departamento: Santander. 2. Municipio: Los Santos. 3. Fechas: del 1 de enero de 2006 hasta la fecha de descarga (12/10/2026). 4. Formato de descarga: GeoJSON. Sin filtro de magnitud ni de profundidad. |
| **Contenido** | 103.546 sismos, 18 campos por sismo; el último evento es del 09/10/2026 |
| **Enlace de consulta** | _Por completar por el equipo: URL exacta del portal del SGC desde donde se descargó._ |

### Fuente complementaria: intensidades observadas del USGS

Solo la usa el simulador de escenarios (complemento de la demo), no el clasificador.

| | |
| :--- | :--- |
| **Entidad** | United States Geological Survey (USGS) — programa "Did You Feel It?" |
| **Archivo** | `data/raw/intensidades_dyfi_usgs.csv` |
| **Fecha de descarga** | 12 de octubre de 2026 |
| **Filtros usados** | Sismos del 01/01/2006 al 12/10/2026, a menos de 60 km del punto 6,80° N, 73,13° O, con profundidad mayor de 100 km y magnitud 4,5 o mayor, que tengan reportes de intensidad. Intensidades agregadas en celdas de 10 km. |
| **Contenido** | 598 observaciones de 86 sismos (1.831 respuestas de la población) |
| **Enlace de consulta** | `https://earthquake.usgs.gov/fdsnws/event/1/` (la consulta exacta está en `src/descargar_intensidades_usgs.py`) |

### Cartografía: límites municipales del DANE

Solo se usan para dibujar el mapa de la aplicación; no son variables del modelo.

| | |
| :--- | :--- |
| **Entidad** | Departamento Administrativo Nacional de Estadística (DANE), límites de 2020, distribuidos por geoBoundaries con licencia CC BY 4.0 |
| **Archivo** | `data/raw/limites_municipios_santander.geojson` |
| **Fecha de descarga** | 12 de octubre de 2026 |
| **Filtros usados** | Municipios de Colombia (nivel ADM2, geometría simplificada) cuyo punto interior cae dentro del departamento de Santander: 87 municipios |
| **Enlace de consulta** | `https://www.geoboundaries.org/api/current/gbOpen/COL/ADM2/` (ver `src/descargar_limites.py`) |

### Población municipal del DANE

No es una variable del modelo. Sirve para estimar cuántas personas viven en las zonas que se sacuden.

| | |
| :--- | :--- |
| **Entidad** | Departamento Administrativo Nacional de Estadística (DANE), proyecciones de población con base en el Censo Nacional de Población y Vivienda 2018 |
| **Conjunto** | Serie municipal de población por área, para el periodo 2018-2042 (publicada el 8 de agosto de 2025) |
| **Archivo** | `data/raw/poblacion_dane/PPED-AreaMun-2018-2042_VP.xlsx` |
| **Fecha de descarga** | 13 de octubre de 2026 |
| **Filtros usados** | Hoja `PobMunicipalxÁrea`; departamento 68 (Santander); año 2026 |
| **Contenido tras la limpieza** | `data/processed/poblacion_santander.csv`: 87 municipios con código DANE y población en cabecera, área rural y total. Total del departamento: 2.410.700 habitantes |
| **Enlace de consulta** | `https://www.dane.gov.co/index.php/estadisticas-por-tema/demografia-y-poblacion/proyecciones-de-poblacion` |

La limpieza está en `src/preparar_poblacion.py`: toma solo Santander y el año 2026, pasa de una fila por área a una fila por municipio, empareja cada municipio con el del mapa (comparando los nombres sin tildes ni mayúsculas) y comprueba que la cabecera más el área rural da el total. Son proyecciones, no un conteo: el último censo es de 2018.

### Cartografía: relieve de Los Santos y de Santander

Solo se usa para mostrar el relieve 3D en la aplicación; no es una variable del modelo.

| | |
| :--- | :--- |
| **Entidad** | Agencia Japonesa de Exploración Aeroespacial (JAXA), modelo de elevación ALOS World 3D 30 m (AW3D30 v4.1), exportado con TouchTerrain |
| **Archivos** | `data/raw/relieve_los_santos/` y `data/raw/relieve_santander/`: en cada una, modelo de elevación (`.tif`), modelo para impresión 3D (`.STL`) y registro de la exportación (`logfile.txt`) |
| **Fecha de descarga** | 13 de octubre de 2026 |
| **Filtros de Los Santos** | Rectángulo de 6,70° a 6,95° N y de 73,25° a 72,95° O (la misma zona que la grilla del modelo, unos 33 × 28 km), celdas de 66 m, sin exageración vertical. 502 × 420 celdas, de 256 a 2.420 m de altura |
| **Filtros de Santander** | Rectángulo de 5,70° a 8,15° N y de 74,53° a 72,47° O (todo el departamento, unos 228 × 271 km), celdas de 455 m, sin exageración vertical. 503 × 598 celdas, de 39 a 4.447 m de altura; en la aplicación se recorta con la silueta del departamento |

La aplicación usa el `.tif` y no el `.STL`: el `.tif` conserva las coordenadas de cada punto, que es lo que permite pintar sobre la montaña el riesgo de la celda en la que cae.

## 2. Campos del catálogo original

| Campo | Significado | Uso |
| :--- | :--- | :--- |
| `id` | Identificador del sismo en el SGC | Control de duplicados |
| `utc_time`, `local_time` | Fecha y hora del sismo | Asignar el trimestre |
| `latitude`, `longitude` | Epicentro | Asignar la celda |
| `depth` | Profundidad del hipocentro (km) | Variables de profundidad |
| `magnitude`, `mag_type` | Magnitud y escala en que se midió | Filtro, variables de magnitud y energía |
| `magnitude_error`, `latitude_error`, `longitude_error`, `depth_error` | Incertidumbre de cada medida | Exploración de calidad |
| `rms`, `gap`, `nst` | Calidad de la localización (ajuste, cobertura angular y número de estaciones) | Exploración de calidad |
| `status`, `agency`, `place` | Revisión manual o automática, agencia y municipio | Verificación del filtro |

## 3. Limpieza y transformación

Todo está en `src/catalogo.py` y `src/entrenar_modelo_sismico_los_santos.py`.

1. **Tipos.** Los campos numéricos vienen como texto; se convierten a número.
2. **Faltantes.** Vienen como cadenas vacías, no como nulos: `magnitude_error` está vacío en el 43 % de los registros y `depth_error` en el 0,1 %. Se dejan como faltantes, sin reemplazarlos por ceros. Ningún campo esencial (magnitud, profundidad, ubicación, fecha) tiene faltantes.
3. **Duplicados.** No hay identificadores repetidos.
4. **Catálogo homogéneo.** La red detecta cada vez más microsismos: el total anual pasa de unos 800 en 2007 a casi 10.000 en 2024 sin que cambie la sismicidad. Para que los conteos sean comparables se usan solo los sismos de magnitud 2,5 o mayor desde 2010, cuyo número anual es estable (entre 550 y 1.030). Quedan 11.964 sismos.
5. **Año incompleto.** El catálogo termina el 9 de octubre de 2026; el trimestre en curso se descarta.
6. **Energía.** Se calcula la energía liberada por cada sismo con la relación de Gutenberg-Richter, log₁₀(E) = 4,8 + 1,5·M.
7. **Grilla y tiempo.** Cada sismo se asigna a una celda de 0,05° × 0,05° (unos 5,5 km) y a un trimestre. Son 30 celdas y 67 trimestres (2010-T1 a 2026-T3).

El dataset resultante es `data/processed/dataset_entrenamiento_los_santos.csv`: 1.008 filas, una por celda y trimestre, con las 15 variables, el número de sismos del trimestre siguiente y la etiqueta.

## 4. Unidad de análisis y etiqueta

- **Zona:** una celda de la grilla. Se modelan las 16 celdas con sismicidad registrada; las otras 14 no han tenido ningún sismo M≥2,5 y se reportan como riesgo Bajo sin pasar por el modelo.
- **Pregunta:** con lo ocurrido hasta el trimestre *t*, ¿qué nivel de actividad tendrá la celda en el trimestre *t+1*?
- **Etiqueta:** número de sismos M≥2,5 del trimestre siguiente, repartido en tres niveles con los terciles del periodo de entrenamiento.

| Nivel | Sismos M≥2,5 en el trimestre siguiente |
| :--- | :--- |
| Bajo | Ninguno |
| Medio | De 1 a 3 |
| Alto | Más de 3 |

La etiqueta mide **actividad sísmica esperada**, que es el componente de amenaza del riesgo. No incluye población ni vulnerabilidad de las construcciones.

## 5. Las 15 variables del modelo

Todas se calculan con información disponible al cierre del trimestre *t*, de modo que el modelo nunca ve el futuro. La importancia es la del Random Forest.

| # | Variable | Qué mide | Por qué se incluye | Importancia |
| ---: | :--- | :--- | :--- | ---: |
| 1 | `sismos_trimestre` | Sismos M≥2,5 en la celda durante el trimestre | La sismicidad es persistente: lo más reciente es el mejor indicio de lo que sigue | 12,7 % |
| 2 | `sismos_ultimo_anio` | Sismos en los últimos cuatro trimestres | Suaviza el ruido de un solo trimestre | 14,4 % |
| 3 | `sismos_promedio_historico` | Promedio trimestral desde 2010 | Nivel de fondo de la celda a largo plazo | 4,6 % |
| 4 | `tendencia_sismos` | Trimestre actual menos el promedio del último año | Indica si la actividad sube o baja | 1,6 % |
| 5 | `sismos_vecinos_ultimo_anio` | Sismos del último año en las 8 celdas vecinas | Los sismos se agrupan en el espacio y el error de localización (2 a 5 km) reparte eventos entre celdas contiguas | 8,6 % |
| 6 | `mag_media_ultimo_anio` | Magnitud media del último año | Tamaño típico de los sismos de la celda | 3,8 % |
| 7 | `mag_max_ultimo_anio` | Mayor magnitud del último año | Un sismo grande suele ir seguido de réplicas | 7,6 % |
| 8 | `log_energia_ultimo_anio` | Logaritmo de la energía liberada en el último año | Resume en un número cuántos sismos hubo y de qué tamaño | 12,1 % |
| 9 | `prop_moderados_ultimo_anio` | Fracción de sismos con M≥3,5 | Distingue celdas con muchos sismos pequeños de celdas con sismos mayores | 3,7 % |
| 10 | `trimestres_desde_sismo_fuerte` | Tiempo desde el último M≥4 en la celda | Memoria de los eventos importantes | 4,8 % |
| 11 | `prof_media_ultimo_anio` | Profundidad media (km) | Ubica la celda respecto al núcleo del nido, entre 140 y 160 km | 2,9 % |
| 12 | `prof_std_ultimo_anio` | Dispersión de la profundidad (km) | Poca dispersión indica un foco concentrado | 6,6 % |
| 13 | `dist_nido_km` | Distancia del centro de la celda al centro del nido | La actividad decae al alejarse del núcleo | 14,2 % |
| 14 | `lat_center` | Latitud del centro de la celda | Posición: el nido no es simétrico | 0,8 % |
| 15 | `lon_center` | Longitud del centro de la celda | Posición: el nido no es simétrico | 1,5 % |

## 6. Validación

- **Partición temporal:** entrenamiento de 2011-T1 a 2021-T4 (704 muestras) y prueba de 2022-T1 a 2026-T3 (304 muestras). No se mezclan al azar, porque eso dejaría ver al modelo el futuro de cada celda.
- **Líneas base:** el modelo se compara con tres reglas sin aprendizaje: la clase más frecuente, repetir el nivel del trimestre anterior y usar el promedio del último año.
- **Métricas:** exactitud, F1 macro (pesa por igual las tres clases), recall de la clase Alto y matriz de confusión. Los resultados quedan en `models/metricas_clasificador.json`.
