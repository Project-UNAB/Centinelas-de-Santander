# Nuevos datos (descargados el 13/10/2026)

Conjuntos oficiales candidatos. Solo el catálogo del SGC de Santander se usa en el proyecto; el papel de cada uno está en `entrenamiento/docs/NUEVOS_DATOS.md`.
El detalle de cada descarga (dirección, tamaño y hora) está en `REGISTRO_DE_DESCARGAS.json`.

| Carpeta y archivo | Fuente | Contenido |
| :--- | :--- | :--- |
| `usgs_catalogo/sismos_usgs_santander_2006_2026.geojson` | USGS, catálogo ANSS | 1.010 sismos en el rectángulo de Santander desde 2006 (casi todos de magnitud 4 o mayor) |
| `sgc_fallas/fallas_activas_santander.geojson` | SGC, Fallas activas de Colombia | 18 fallas que cruzan el rectángulo de Santander, con sus atributos |
| `datos_gov_co/nido_actividad_sismica.geojson` | Gobernación de Santander (datos.gov.co `jvqc-zbnh`) | 13 polígonos del nido de actividad sísmica, repartidos en 11 municipios (Los Santos y diez vecinos), escala 1:100.000 |
| `datos_gov_co/integracion_amenazas.geojson` | Gobernación de Santander (datos.gov.co `grq5-aeu7`) | Amenaza integrada por remoción en masa, incendios e inundación (no sísmica) |
| `datos_gov_co/remocion_en_masa.geojson` | Gobernación de Santander (datos.gov.co `r724-fvfm`) | Amenaza por remoción en masa (no sísmica) |
| `danos_y_costos/gobernacion_santander/reporte_eventos_desastres_santander.csv` | Gobernación de Santander (datos.gov.co `a4bc-a9tq`) | Reporte histórico de eventos por desastres |

Los conjuntos para estimar daños y costos (emergencias de la UNGRD, viviendas y hogares del DANE) están en `danos_y_costos/`, con su propio `LEEME.md`.

El catálogo del SGC de todo Santander ya está en `sgc_catalogo/` y es el que usa el entrenamiento.

## No se pudieron descargar

- **Zonas de amenaza sísmica NSR-10 del SGC** (datos.gov.co `2ie9-7xta`). El servidor de mapas del SGC no respondió.
