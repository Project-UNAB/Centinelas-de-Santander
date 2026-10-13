"""Pruebas de la API.  Ejecutar desde backend/:  pytest"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def cliente():
    with TestClient(app) as c:
        yield c


def test_salud(cliente):
    respuesta = cliente.get("/api/salud")
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "ok"


def test_celdas_de_riesgo(cliente):
    celdas = cliente.get("/api/riesgo/celdas").json()["features"]
    assert len(celdas) == 30
    assert {c["properties"]["riesgo_predicho"] for c in celdas} <= {"Bajo", "Medio", "Alto"}


def test_predecir_coincide_con_la_grilla(cliente):
    """Enviar las variables de una celda debe devolver el riesgo que ya trae la grilla."""
    variables = cliente.get("/api/riesgo/modelo").json()["variables"]
    celdas = cliente.get("/api/riesgo/celdas").json()["features"]
    activas = [c["properties"] for c in celdas if c["properties"]["con_sismicidad_registrada"]]
    for celda in activas:
        respuesta = cliente.post("/api/riesgo/predecir", json={v: celda[v] for v in variables})
        assert respuesta.status_code == 200
        assert respuesta.json()["nivel"] == celda["riesgo_predicho"]
        assert abs(sum(respuesta.json()["probabilidades"].values()) - 1) < 0.01


def test_el_historial_reproduce_la_exactitud_del_modelo(cliente):
    """Los aciertos del historial, sumados, deben dar la exactitud que se reporta."""
    historial = cliente.get("/api/riesgo/historial").json()
    info = cliente.get("/api/riesgo/modelo").json()
    con_modelo = historial["celdas_con_modelo"]
    aciertos = sum(t["predicho"][c] == t["real"][c] for t in historial["trimestres"] for c in con_modelo)
    muestras = len(historial["trimestres"]) * len(con_modelo)
    assert muestras == info["muestras_prueba"]
    assert abs(aciertos / muestras - info["metricas"][historial["modelo"]]["accuracy"]) < 1e-9
    assert [historial["trimestres"][0]["trimestre"], historial["trimestres"][-1]["trimestre"]] == info["periodo_prueba"]
    assert all(len(t["sismos"]) == 30 for t in historial["trimestres"])


def test_el_modelo_de_santander_es_otro_modelo(cliente):
    """Cada zona tiene su clasificador, su grilla y su historial."""
    info = cliente.get("/api/riesgo/modelo", params={"zona": "santander"}).json()
    celdas = cliente.get("/api/riesgo/celdas", params={"zona": "santander"}).json()["features"]
    historial = cliente.get("/api/riesgo/historial", params={"zona": "santander"}).json()
    assert info["zona"] == "santander" and info["celdas_con_modelo"] > 300
    assert info["muestras_prueba"] > cliente.get("/api/riesgo/modelo").json()["muestras_prueba"]
    assert sum(c["properties"]["con_sismicidad_registrada"] for c in celdas) == info["celdas_con_modelo"] == len(historial["celdas_con_modelo"])
    assert sum(c["properties"]["en_el_departamento"] for c in celdas) == 997
    assert all(len(t["predicho"]) == len(celdas) for t in historial["trimestres"])
    con_modelo = historial["celdas_con_modelo"]
    aciertos = sum(t["predicho"][c] == t["real"][c] for t in historial["trimestres"] for c in con_modelo)
    assert abs(aciertos / info["muestras_prueba"] - info["metricas"][historial["modelo"]]["accuracy"]) < 1e-9
    assert cliente.get("/api/riesgo/celdas", params={"zona": "otra"}).status_code == 422


def test_viviendas_afectadas(cliente):
    """El daño crece con la sacudida, el rango contiene al valor central y los municipios suman el total."""
    pedir = lambda m, p: cliente.post("/api/simulador", json={"magnitud": m, "profundidad_km": p}).json()["info"]["viviendas"]
    profundo, somero = pedir(6.0, 150), pedir(6.5, 20)
    for v in (profundo, somero):
        assert v["afectadas_bajo"] <= v["afectadas"] <= v["afectadas_alto"] <= v["total"]
        assert v["costo_bajo"] <= v["costo"] <= v["costo_alto"]
        assert len(v["afectadas_por_municipio"]) == 87
        assert abs(sum(v["afectadas_por_municipio"]) - v["afectadas"]) < 50
        assert v["destruidas"] <= v["afectadas"]
    assert somero["afectadas"] > profundo["afectadas"]
    assert pedir(7.0, 10)["fuera_de_lo_observado"]
    modelo = cliente.get("/api/danos/modelo").json()
    assert modelo["casos"] > 100 and modelo["modelo_elegido"] in modelo["candidatos"]


def test_predecir_rechaza_valores_invalidos(cliente):
    assert cliente.post("/api/riesgo/predecir", json={"sismos_trimestre": -1}).status_code == 422


def test_simulador(cliente):
    grilla = cliente.get("/api/simulador/grilla").json()
    respuesta = cliente.post("/api/simulador", json={"magnitud": 6.0, "profundidad_km": 150})
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert len(datos["mmi"]) == len(datos["nivel"]) == len(grilla["lat"])
    assert datos["info"]["tipo_fuente"] == "intraplaca"


def test_un_sismo_somero_sacude_mas_que_uno_profundo(cliente):
    somero = cliente.post("/api/simulador", json={"magnitud": 6.5, "profundidad_km": 10}).json()
    profundo = cliente.post("/api/simulador", json={"magnitud": 6.5, "profundidad_km": 150}).json()
    assert max(somero["mmi"]) > max(profundo["mmi"])
    assert somero["info"]["advertencias"]


def test_simulador_rechaza_escenarios_fuera_de_rango(cliente):
    assert cliente.post("/api/simulador", json={"magnitud": 9.0, "profundidad_km": 150}).status_code == 422
    assert cliente.post("/api/simulador", json={"magnitud": 6.0, "profundidad_km": 500}).status_code == 422


@pytest.mark.parametrize("zona", ["santander", "los_santos"])
def test_relieve(cliente, zona):
    relieve = cliente.get(f"/api/relieve/{zona}").json()
    assert len(relieve["elevaciones"]) == relieve["filas"] * relieve["columnas"]
    assert relieve["lat_sur"] < relieve["lat_norte"] and relieve["lon_oeste"] < relieve["lon_este"]
    assert 0 < relieve["elevacion_min"] < relieve["elevacion_max"] < 6000


def test_el_relieve_de_santander_viene_recortado(cliente):
    """Fuera del departamento los puntos se marcan con -1; Los Santos es un rectángulo completo."""
    assert min(cliente.get("/api/relieve/santander").json()["elevaciones"]) == -1
    assert min(cliente.get("/api/relieve/los_santos").json()["elevaciones"]) > 0
    assert cliente.get("/api/relieve/otra").status_code == 422


@pytest.mark.parametrize("zona", ["santander", "los_santos"])
def test_mapa_de_calor(cliente, zona):
    respuesta = cliente.post("/api/simulador/mapa-de-calor", json={"magnitud": 6.5, "profundidad_km": 20, "zona": zona})
    assert respuesta.status_code == 200
    campo = respuesta.json()["campo"]
    assert len(campo["mmi"]) == campo["filas"] * campo["columnas"] > 10000
    assert 1 <= min(campo["mmi"]) < max(campo["mmi"]) <= 10


def test_el_mapa_de_calor_coincide_con_las_celdas(cliente):
    """La malla fina y las celdas deben dar la misma intensidad máxima, salvo por la resolución."""
    escenario = {"magnitud": 6.0, "profundidad_km": 150}
    celdas = cliente.post("/api/simulador", json=escenario).json()
    calor = cliente.post("/api/simulador/mapa-de-calor", json={**escenario, "zona": "santander"}).json()
    assert abs(max(celdas["mmi"]) - max(calor["campo"]["mmi"])) < 0.1
    assert calor["info"]["celdas_por_nivel"] == celdas["info"]["celdas_por_nivel"]


def test_personas_expuestas(cliente):
    """Toda la población de Santander queda en algún nivel, y un sismo mayor expone a más gente."""
    pedir = lambda magnitud: cliente.post("/api/simulador", json={"magnitud": magnitud, "profundidad_km": 150}).json()["info"]
    menor, mayor = pedir(4.5), pedir(7.0)
    for info in (menor, mayor):
        assert sum(info["personas_por_nivel"].values()) == 2_410_700
        assert sum(info["municipios_por_nivel"].values()) == 87
    assert mayor["personas_por_nivel"]["Bajo"] < menor["personas_por_nivel"]["Bajo"]
    calor = cliente.post("/api/simulador/mapa-de-calor", json={"magnitud": 7.0, "profundidad_km": 150}).json()["info"]
    assert calor["personas_por_nivel"] == mayor["personas_por_nivel"]

    # El nivel de cada municipio, con su población, debe dar las mismas sumas
    poblacion = cliente.get("/api/poblacion").json()
    somero = cliente.post("/api/simulador", json={"magnitud": 6.5, "profundidad_km": 20}).json()["info"]
    assert len(poblacion["municipio"]) == len(somero["nivel_por_municipio"]) == 87
    for nivel, personas in somero["personas_por_nivel"].items():
        assert sum(h for h, n in zip(poblacion["habitantes"], somero["nivel_por_municipio"]) if n == nivel) == personas


def test_sismos_reales(cliente):
    sismos = cliente.get("/api/simulador/sismos-reales").json()
    assert len(sismos) == 5
    assert any(s["fecha_utc"].startswith("2015-03-10") for s in sismos)
    for sismo in sismos:
        observaciones = sismo["observaciones"]
        assert len({len(columna) for columna in observaciones.values()}) == 1
        assert sum(observaciones["respuestas"]) == sismo["respuestas"]
        assert 0 <= sismo["desvio"]["dentro_de_1_grado"] <= 1
        # Cada sismo real debe poder reproducirse en el simulador
        escenario = {"magnitud": sismo["magnitud"], "profundidad_km": sismo["profundidad_km"],
                     "epicentro_lat": sismo["lat"], "epicentro_lon": sismo["lon"]}
        assert cliente.post("/api/simulador/mapa-de-calor", json=escenario).status_code == 200


def test_el_epicentro_mueve_la_sacudida(cliente):
    """Con el epicentro al norte de Santander, la mayor intensidad ya no cae en el nido."""
    escenario = {"magnitud": 6.0, "profundidad_km": 150, "zona": "santander"}
    pedir = lambda extra: cliente.post("/api/simulador/mapa-de-calor", json={**escenario, **extra})
    fila_del_maximo = lambda campo: campo["mmi"].index(max(campo["mmi"])) // campo["columnas"]
    en_el_nido = pedir({}).json()["campo"]
    al_norte = pedir({"epicentro_lat": 8.0, "epicentro_lon": -73.4}).json()["campo"]
    assert fila_del_maximo(al_norte) < fila_del_maximo(en_el_nido)
    assert pedir({"epicentro_lat": 8.0}).status_code == 422
    assert pedir({"epicentro_lat": 40.0, "epicentro_lon": -73.4}).status_code == 422


def test_sismos_simulados_se_parecen_a_los_reales(cliente):
    reales = cliente.get("/api/sismos", params={"zona": "los_santos"}).json()
    simulados = cliente.get("/api/simulador/sismos", params={"anios": 17, "semilla": 3}).json()
    modelo = simulados["modelo"]

    # Cantidad acorde con la tasa anual, y magnitudes dentro de los límites del modelo
    assert 0.8 < len(simulados["lon"]) / (modelo["tasa_anual"] * 17) < 1.2
    assert modelo["m_min"] <= min(simulados["magnitud"]) and max(simulados["magnitud"]) <= modelo["m_max"]

    # La nube simulada queda en el mismo sitio que la real
    media = lambda valores: sum(valores) / len(valores)
    assert abs(media(simulados["profundidad_km"]) - media(reales["profundidad_km"])) < 2
    assert abs(media(simulados["lon"]) - media(reales["lon"])) < 0.01
    assert abs(media(simulados["magnitud"]) - media(reales["magnitud"])) < 0.1


def test_la_simulacion_es_repetible_y_cambia_con_la_semilla(cliente):
    pedir = lambda semilla: cliente.get("/api/simulador/sismos", params={"anios": 5, "semilla": semilla}).json()
    assert pedir(1)["magnitud"] == pedir(1)["magnitud"]
    assert pedir(1)["magnitud"] != pedir(2)["magnitud"]
    assert cliente.get("/api/simulador/sismos", params={"anios": 500}).status_code == 422


def test_datos_del_mapa(cliente):
    assert len(cliente.get("/api/municipios").json()["features"]) == 87
    sismos = cliente.get("/api/sismos").json()
    assert len(sismos["lon"]) == len(sismos["profundidad_km"]) > 10000


def test_sismos_de_cada_zona(cliente):
    santander = cliente.get("/api/sismos", params={"zona": "santander"}).json()
    los_santos = cliente.get("/api/sismos", params={"zona": "los_santos"}).json()
    # En Los Santos solo quedan los sismos que caen dentro de sus 30 celdas
    assert 10000 < len(los_santos["lon"]) < len(santander["lon"])
    assert all(6.70 <= lat < 6.95 for lat in los_santos["lat"])
    assert all(-73.25 <= lon < -72.95 for lon in los_santos["lon"])
    assert min(santander["lat"]) < 6.0 and max(santander["lat"]) > 7.5
    assert cliente.get("/api/sismos", params={"zona": "otra"}).status_code == 422
