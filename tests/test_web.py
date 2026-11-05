"""Tests de la interfaz web. No usan Ollama: el agente lleva un modelo simulado que
primero pide ejecutar una consulta y después redacta la respuesta con lo que devolvió."""
import json

import pytest
from fastapi.testclient import TestClient
from google.adk.agents.llm_agent import Agent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from valhalla_agent import tools
from valhalla_agent.tools import consultar_historial, ejecutar_sql, inspeccionar_esquema, listar_fuentes
from valhalla_web import crear_app


class ModeloSimulado(BaseLlm):
    """Pide ejecutar la consulta `sql`; cuando recibe el resultado, contesta `respuesta`."""
    sql: str = "SELECT categoria, SUM(total) AS ingresos FROM ventas GROUP BY categoria ORDER BY 2 DESC"
    respuesta: str = "Listo, acá tenés los ingresos por categoría."
    falla: bool = False

    async def generate_content_async(self, llm_request, stream=False):
        if self.falla:
            raise RuntimeError("401 Unauthorized")
        ultimo = llm_request.contents[-1]
        if any(p.function_response for p in ultimo.parts):
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=self.respuesta)]))
        else:
            llamada = types.FunctionCall(
                name="ejecutar_sql", args={"consulta": self.sql, "pregunta": "ingresos por categoría"})
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(function_call=llamada)]))


def _agente(**kw):
    return Agent(model=ModeloSimulado(model="simulado", **kw), name="root_agent",
                 instruction="test",
                 tools=[listar_fuentes, inspeccionar_esquema, ejecutar_sql, consultar_historial])


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    # historial temporal para no ensuciar el historial.db real
    monkeypatch.setattr(tools, "RUTA_HISTORIAL", tmp_path / "historial.db")
    monkeypatch.setattr(tools, "_motor", None)
    monkeypatch.setattr(tools, "_error_carga", None)
    return TestClient(crear_app(_agente()))


def _eventos(resp):
    return [json.loads(l) for l in resp.text.splitlines() if l.strip()]


def test_inicio_sirve_la_pagina(cliente):
    r = cliente.get("/")
    assert r.status_code == 200 and "Valhalla" in r.text


def test_archivos_estaticos(cliente):
    assert cliente.get("/static/styles.css").status_code == 200
    assert cliente.get("/static/app.js").status_code == 200
    assert cliente.get("/static/fonts/uncial-antiqua-latin-400-normal.woff2").status_code == 200


def test_estado_informa_tablas_y_fechas(cliente):
    d = cliente.get("/api/estado").json()
    assert d["estado"] == "ok"
    assert d["tablas"][0]["nombre"] == "ventas" and d["tablas"][0]["filas"] == 1_000_000
    assert "ventas.fecha" in d["rango_fechas"]


def test_chat_devuelve_paso_resultado_y_final(cliente):
    r = cliente.post("/api/chat", json={"mensaje": "ingresos por categoría", "sesion": "sesion-de-prueba-1"})
    assert r.status_code == 200
    ev = _eventos(r)
    assert [e["tipo"] for e in ev] == ["paso", "resultado", "final"]
    assert ev[0]["herramienta"] == "ejecutar_sql" and "SELECT" in ev[0]["args"]["consulta"]
    res = ev[1]["respuesta"]
    assert res["estado"] == "ok" and res["columnas"] == ["categoria", "ingresos"] and len(res["filas"]) == 7
    assert ev[2]["texto"].startswith("Listo")


def test_chat_registra_en_el_historial(cliente):
    cliente.post("/api/chat", json={"mensaje": "x", "sesion": "sesion-de-prueba-2"})
    h = cliente.get("/api/historial").json()
    assert h["estado"] == "ok" and h["consultas"][0]["pregunta"] == "ingresos por categoría"
    assert h["consultas"][0]["estado"] == "ok"


def test_consulta_de_escritura_queda_rechazada(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "RUTA_HISTORIAL", tmp_path / "historial.db")
    monkeypatch.setattr(tools, "_motor", None)
    monkeypatch.setattr(tools, "_error_carga", None)
    c = TestClient(crear_app(_agente(sql="DROP TABLE ventas")))
    ev = _eventos(c.post("/api/chat", json={"mensaje": "borrá todo", "sesion": "sesion-de-prueba-3"}))
    assert ev[1]["respuesta"]["estado"] == "rechazada"
    # y los datos siguen intactos
    assert c.get("/api/estado").json()["tablas"][0]["filas"] == 1_000_000


def test_error_del_modelo_se_informa_con_pista(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "RUTA_HISTORIAL", tmp_path / "historial.db")
    monkeypatch.setattr(tools, "_motor", None)
    monkeypatch.setattr(tools, "_error_carga", None)
    c = TestClient(crear_app(_agente(falla=True)))
    ev = _eventos(c.post("/api/chat", json={"mensaje": "hola", "sesion": "sesion-de-prueba-4"}))
    assert ev[-1]["tipo"] == "error" and "ollama signin" in ev[-1]["mensaje"]


@pytest.mark.parametrize("cuerpo", [
    {"mensaje": "", "sesion": "sesion-valida-1"},
    {"mensaje": "x" * 2001, "sesion": "sesion-valida-1"},
    {"mensaje": "hola", "sesion": "../../etc"},
    {"mensaje": "hola"},
])
def test_entradas_invalidas_se_rechazan(cliente, cuerpo):
    assert cliente.post("/api/chat", json=cuerpo).status_code == 422


def test_la_misma_sesion_mantiene_el_hilo(cliente):
    for _ in range(2):
        ev = _eventos(cliente.post("/api/chat", json={"mensaje": "otra", "sesion": "sesion-de-prueba-5"}))
        assert ev[-1]["tipo"] == "final"
