# Centinelas de Santander

Riesgo sísmico por zona en Los Santos, Santander, a partir del catálogo oficial del Servicio Geológico Colombiano. Proyecto para el **UTSmart IA Challenge 2027**, categoría Básica.

Usa tres modelos de aprendizaje supervisado, cada uno entrenado y validado por separado:

| Modelo | Qué hace | Resultado en datos que no vio |
| :--- | :--- | :--- |
| **1. Sismos de Los Santos** (principal) | Clasifica cada una de las 30 celdas de la zona en riesgo Bajo, Medio o Alto para el trimestre siguiente | 80,7 % de exactitud y 71,9 % de F1 macro (persistencia: 80,2 % y 70,9 %) |
| **2. Sismos de Santander** | El mismo clasificador para las 358 celdas con sismicidad del departamento | 93,4 % de exactitud y 74,3 % de F1 macro (persistencia: 90,9 % y 70,0 %) |
| **3. Viviendas y costos** | Estima las viviendas afectadas por un sismo y un rango de costo de atención | Primera aproximación: error típico de un factor de diez; siempre entrega un rango |

Los acompaña un simulador de sacudida, calibrado con intensidades reportadas por la población. El detalle está en el [documento técnico](docs/Centinelas_de_Santander_Documento_tecnico.docx) y la [presentación](docs/Centinelas_de_Santander_Sustentacion.pptx).

| Carpeta | Qué contiene | Tecnología | Destino |
| :--- | :--- | :--- | :--- |
| [`entrenamiento/`](entrenamiento) | Datos originales, limpieza y entrenamiento de los tres modelos, cada uno en su carpeta con su cuaderno de registro | Python, scikit-learn | Se ejecuta en local |
| [`backend/`](backend) | API que sirve los modelos entrenados | FastAPI, Docker | Google Cloud Run |
| [`frontend/`](frontend) | Aplicación web con mapas y vista 3D | React, Vite, deck.gl | Vercel |
| [`docs/`](docs) | Documento técnico y presentación de la sustentación | Word, PowerPoint | — |

```
entrenamiento ──(exportar_al_backend.py)──▶ backend/artefactos ──(API REST)──▶ frontend
```

El entrenamiento produce los modelos, un script los copia al backend, y el frontend solo habla con la API. Ninguna parte necesita a las otras para desplegarse.

## Ejecutar en local

Requisitos: Python 3.11 y Node 20 o superior.

**1. Backend** (queda en http://localhost:8000, documentación en `/docs`)

```powershell
cd backend
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**2. Frontend** (queda en http://localhost:5173)

```powershell
cd frontend
npm install
npm run dev
```

Los modelos ya están exportados en `backend/artefactos`, así que no hace falta entrenar para ver la aplicación. Para reentrenar, ver [`entrenamiento/README.md`](entrenamiento/README.md).

## La aplicación

Tiene tres secciones. Las dos primeras ofrecen las mismas dos vistas, que se eligen con un filtro:

| Sección | Vista "Riesgo por zona" | Vista "Nido 3D" |
| :--- | :--- | :--- |
| **Datos reales** | Nivel de riesgo (Bajo, Medio, Alto) que predice el clasificador de la zona elegida: el modelo 1 en «Solo Los Santos» y el modelo 2 en «Santander completo». Una línea de tiempo recorre el periodo de prueba (2022 a 2026) y compara lo que el modelo predijo con lo que ocurrió, marcando las celdas falladas. | Los sismos reales del catálogo, cada uno a su profundidad bajo el relieve. |
| **Simulados** | Sacudida de un sismo hipotético o de uno de cinco sismos reales (comparado con lo que reportó la población), con las personas expuestas, las viviendas afectadas y el costo de atención, siempre con su rango. Al hacer clic en un punto se ven sus coordenadas, su intensidad y los datos de su municipio. | Un catálogo sintético de sismos (no ocurrieron, pero siguen la tasa, la ubicación y las magnitudes del catálogo real), más el sismo configurado y su sacudida. Se eligen los años simulados y se puede generar otra simulación. |

La tercera sección, **Los modelos**, muestra en tres pestañas las métricas de cada modelo: comparación con reglas sin aprendizaje, matriz de confusión, importancia de variables y límites.

Todas las vistas con relieve se dibujan sobre el relieve 3D real, sin mapa de fondo, con los resultados pintados como mapa de calor continuo (verde, amarillo, rojo). En cada una hay un segundo filtro para ver **Santander completo** o **solo Los Santos**.

La sección, la vista y la zona se pueden indicar en la dirección, por ejemplo `#simulados/nido/los_santos` o `#reales/zona/santander`.

## La API

| Método y ruta | Devuelve |
| :--- | :--- |
| `GET /api/salud` | Estado del servicio y modelos cargados |
| `GET /api/riesgo/celdas?zona=` | Celdas de la zona con variables y riesgo predicho (GeoJSON). `zona` es `los_santos` (por defecto) o `santander`: cada una tiene su modelo |
| `GET /api/riesgo/modelo?zona=` | Métricas, ajustes, matriz de confusión e importancia de variables |
| `GET /api/riesgo/historial?zona=` | Nivel predicho y ocurrido en cada celda durante los 19 trimestres de prueba |
| `POST /api/riesgo/predecir?zona=` | Nivel y probabilidades para las 15 variables de una celda |
| `GET /api/simulador/grilla` | Celdas de Santander sobre las que se simula |
| `POST /api/simulador` | Sacudida por celda para `{magnitud, profundidad_km}`, con personas expuestas, viviendas afectadas y costo |
| `GET /api/simulador/sismos-reales` | Cinco sismos reales con la intensidad observada en cada lugar y el desvío del simulador |
| `GET /api/danos/modelo` | Validación del modelo de viviendas y costo por vivienda |
| `GET /api/poblacion` | Habitantes y viviendas de cada municipio |
| `GET /api/simulador/modelo` | Validación del modelo de sacudida |
| `GET /api/municipios` | Límites de los 87 municipios de Santander (GeoJSON) |
| `GET /api/sismos` | Hipocentros reales para la vista 3D |
| `GET /api/simulador/sismos?anios=&semilla=` | Catálogo sintético del nido, en el mismo formato que `/api/sismos` |
| `GET /api/relieve/{zona}` | Elevación del terreno de `santander` o `los_santos` en una malla regular |
| `POST /api/simulador/mapa-de-calor` | Sacudida en una malla fina (un punto cada 1,1 km en Santander o cada 220 m en Los Santos) para `{magnitud, profundidad_km, zona}` y, opcionalmente, un epicentro |

Pruebas (22): `pip install -r requirements-dev.txt` y luego `pytest` desde `backend/`.

## Despliegue

### Backend en Google Cloud Run

Requiere la [CLI de Google Cloud](https://cloud.google.com/sdk/docs/install) y un proyecto con facturación activa.

```powershell
cd backend
gcloud run deploy centinelas-api `
  --source . `
  --region southamerica-east1 `
  --allow-unauthenticated `
  --memory 1Gi `
  --set-env-vars "CORS_ORIGENES=https://TU-APP.vercel.app"
```

`--source .` construye la imagen con el `Dockerfile` de la carpeta. Al terminar, el comando muestra la URL del servicio.

| Variable | Para qué |
| :--- | :--- |
| `CORS_ORIGENES` | Direcciones del frontend que pueden llamar a la API, separadas por comas |
| `CORS_ORIGEN_REGEX` | Opcional: expresión regular para aceptar las vistas previas de Vercel |

### Frontend en Vercel

1. Importar el repositorio en Vercel y elegir `frontend` como **Root Directory**. Vercel detecta Vite sin más configuración.
2. Añadir la variable de entorno `VITE_API_URL` con la URL de Cloud Run.
3. Desplegar, y poner la dirección que entregue Vercel en `CORS_ORIGENES` del backend.

### Actualizar los modelos

```powershell
cd entrenamiento
py -3.11 1_sismos_los_santos/src/entrenar_modelo_sismico_los_santos.py
py -3.11 2_sismos_santander/src/entrenar_modelo_sismico_santander.py
py -3.11 3_viviendas_y_costos/src/preparar_danos.py
py -3.11 3_viviendas_y_costos/src/entrenar_modelo_viviendas.py
py -3.11 comun/src/exportar_al_backend.py
```

Después se vuelve a desplegar el backend. El frontend no cambia.

## Fuentes de datos

- **Servicio Geológico Colombiano:** catálogo sísmico de Santander, 2006 a 2026 (184.723 sismos). Es la única fuente con la que se entrenan los clasificadores. Se usan los sismos de magnitud 2,5 o mayor desde 2010, que la red registra de forma estable.
- **USGS:** intensidades observadas ("Did You Feel It?") para calibrar el simulador, y catálogo ANSS para identificar los sismos de las emergencias.
- **UNGRD** (datos.gov.co): emergencias de 2019 a 2025, para el modelo de viviendas y costos.
- **DANE:** proyecciones de población y de viviendas por municipio, DIVIPOLA y, vía geoBoundaries (CC BY 4.0), límites municipales.
- **JAXA** (ALOS World 3D 30 m), vía TouchTerrain: relieve de Los Santos, solo para la vista 3D.

Fechas de descarga y filtros: sección 6.1 del documento técnico. Papel de cada conjunto de datos: [`entrenamiento/docs/NUEVOS_DATOS.md`](entrenamiento/docs/NUEVOS_DATOS.md). Cómo se ejecuta cada modelo: [`entrenamiento/README.md`](entrenamiento/README.md).

Algunos archivos no están en el repositorio por su tamaño y porque se pueden regenerar o no se usan: el catálogo limpio (lo genera el cuaderno del modelo 1), los modelos `.STL` de TouchTerrain y las capas descargadas que no se usan.

## Cómo funciona el relieve 3D

El relieve sale del modelo de elevación (`.tif`) que TouchTerrain entrega junto al `.STL`. Se usa el `.tif` porque conserva las coordenadas; el `.STL` es un modelo para imprimir, sin coordenadas ni colores.

1. `entrenamiento/comun/src/exportar_al_backend.py` convierte cada `.tif` en una malla regular de latitud y longitud (`backend/artefactos/relieve_<zona>.json`).
2. El frontend construye con ella la geometría 3D ([`frontend/src/relieve.ts`](frontend/src/relieve.ts)).
3. Encima se pinta una textura: el sombreado de las montañas, el mapa de calor y los límites municipales.

Hay dos relieves:

| Zona | Carpeta en `entrenamiento/data/raw/` | Rectángulo | Detalle |
| :--- | :--- | :--- | :--- |
| Los Santos | `relieve_los_santos/` | 6,70° a 6,95° N, 73,25° a 72,95° O (la grilla del modelo) | 66 m |
| Santander | `relieve_santander/` | 5,70° a 8,15° N, 74,53° a 72,47° O | 455 m |

El de Santander se recorta con la silueta del departamento, para no mostrar los departamentos vecinos. Para cambiar una zona basta con exportar otro rectángulo desde TouchTerrain, copiar el `.tif` a su carpeta y volver a ejecutar la exportación; el script usa el `.tif` más reciente.

### Qué tan fino es el mapa de calor

- **Simulador y Nido 3D:** la sacudida se calcula de verdad en cada punto de una malla fina (cada 1,1 km en Santander, cada 220 m en Los Santos).
- **Riesgo por zona:** el modelo predice por celdas de 5,5 km. El degradado suaviza el paso entre celdas para que se lea mejor, pero no añade precisión.
