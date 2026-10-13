# Nuevos datos: qué sirve para entrenar y qué sirve para la plataforma

Conjuntos descargados el 13/10/2026 en la carpeta `nuevos datos/` (la dirección y la hora de cada descarga están en su `REGISTRO_DE_DESCARGAS.json`). Todos provienen de fuentes que el reto admite: SGC, USGS y datos.gov.co.

## Clasificación

| Conjunto | Fuente | Para entrenar | Para la plataforma | Estado |
| :--- | :--- | :--- | :--- | :--- |
| Catálogo de sismicidad de **todo Santander**, 2006-2026 (184.723 sismos) | SGC | **Sí. Es el único conjunto con el que se entrena el clasificador** | Sismos de la vista Nido 3D | **En uso** (`data/raw/Santander - 01-01-2006 - 13-10-2026.csv`) |
| Fallas activas (18 que cruzan el rectángulo de Santander) | SGC | No. Se probó la distancia a la falla más cercana y no aporta (importancia del 0,6 % al 1,5 %, sin mejora). El nido está a 150 km de profundidad, no en fallas superficiales | Capa de contexto sobre el relieve | Disponible, sin usar |
| Nido de actividad sísmica (13 polígonos en 11 municipios) | Gobernación de Santander, datos.gov.co | No como variable. Es la evidencia oficial de que el nido abarca municipios vecinos | Contorno oficial del nido sobre el relieve; filtro por municipio | Disponible, sin usar |
| Catálogo del USGS para Santander (1.010 sismos) | USGS | No. Casi todos son de magnitud 4 o mayor; el modelo cuenta sismos desde 2,5 | Contraste de magnitudes con el SGC | Disponible, sin usar |
| Remoción en masa (276 zonas) | Gobernación de Santander | No. No es sísmico | Capa de amenaza por deslizamientos | Disponible, sin usar |
| Integración de amenazas (1.986 zonas) | Gobernación de Santander | No. Combina remoción en masa, incendios e inundación | Capa multiamenaza | Disponible, sin usar |
| Reporte de eventos por desastres (1.628 registros) | Gobernación de Santander | No. No es sísmico | Contexto para la presentación | Disponible, sin usar |

## Por qué se pasó al catálogo de todo Santander

El primer modelo se entrenó con el catálogo filtrado por el **municipio** de Los Santos. Pero el SGC asigna cada sismo al municipio de su epicentro, y la grilla de 30 celdas cubre también partes de municipios vecinos. De los 13.741 sismos de magnitud 2,5 o mayor que caen en la grilla desde 2010, **1.777 (el 12,9 %) están asignados a otros municipios** (Zapatoca 1.407, Cepitá 135, Villanueva 130 y otros) y no estaban en los datos.

Consecuencias de ese hueco, ya corregidas:

- 14 de las 30 celdas parecían no tener sismos y se reportaban en Bajo sin pasar por el modelo. Con el catálogo completo las 30 tienen sismos y las 30 pasan por el modelo.
- 25 de las 304 etiquetas del periodo de prueba estaban mal (el nivel real era otro).
- La actividad de las celdas vecinas quedaba incompleta en los bordes. Ahora las variables se calculan en una grilla ampliada cinco celdas a cada lado.

## Qué se probó y qué resultó

Todas las alternativas se evaluaron en las mismas 30 celdas de Los Santos y los mismos 19 trimestres de prueba (570 casos), con las etiquetas del catálogo completo.

| Alternativa | Exactitud | F1 macro |
| :--- | ---: | ---: |
| Regla: igual al trimestre anterior | 80,18 % | 70,85 % |
| **Random Forest, entrenado con las 30 celdas (elegido, con el balanceo ajustado por validación interna)** | **80,70 %** | **71,92 %** |
| El mismo, con las tres clases pesando igual (primera versión) | 79,30 % | 72,88 % |
| Random Forest, entrenado además con las celdas vecinas del nido (130 celdas) | 66,14 % | 64,50 % |
| Random Forest, entrenado con todo Santander (371 celdas) | 62,81 % | 61,24 % |
| Lo anterior más la distancia a fallas | sin mejora | sin mejora |
| Techo de referencia (oráculo) | 82,81 % | 72,25 % |

Conclusiones:

- **Más celdas de entrenamiento no mejora el modelo: lo empeora.** Fuera del nido casi todas las celdas están vacías, y el modelo aprende de ellas un comportamiento distinto al de Los Santos. Lo que mejora es usar **todos los sismos** para describir bien las 30 celdas.
- Se probaron ocho configuraciones de modelo en cuatro zonas de entrenamiento, eligiendo con validación dentro del periodo de entrenamiento (2017-2021). Ninguna supera de forma consistente a la configuración actual.
- Con las tres clases pesando igual, la regla de persistencia acertaba algo más en exactitud (80,2 % frente a 79,3 %). Al ajustar el balanceo de clases con validación interna, el Random Forest la supera en las dos métricas: 80,7 % de exactitud y 71,9 % de F1 macro, frente a 80,2 % y 70,9 %.
- Los modelos 2 (todo Santander) y 3 (viviendas y costos) tienen su propia carpeta; sus resultados están en `entrenamiento/README.md`.

El modelo anterior y sus métricas se conservan en `models/legacy/solo_los_santos/`.
