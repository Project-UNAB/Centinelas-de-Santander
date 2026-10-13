# Imagen del backend, lista para Google Cloud Run
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY artefactos ./artefactos

# Sin privilegios de administrador dentro del contenedor
RUN useradd --create-home api
USER api

# Cloud Run indica el puerto en la variable PORT
ENV PORT=8080
EXPOSE 8080
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
