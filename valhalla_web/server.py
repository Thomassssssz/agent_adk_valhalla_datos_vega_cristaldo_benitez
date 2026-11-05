"""Servidor web (FastAPI) que conecta el navegador con el agente de Valhalla.

Flujo de una pregunta:
  navegador --POST /api/chat--> Runner de ADK --> agente --> herramientas --> DuckDB
El servidor devuelve la respuesta "en vivo", una línea JSON por evento:
  {"tipo": "paso",      "herramienta": ..., "args": ...}   el agente llamó a una herramienta
  {"tipo": "resultado", "herramienta": ..., "respuesta": ...}  lo que devolvió la herramienta
  {"tipo": "final",     "texto": ...}                      la respuesta escrita del agente
  {"tipo": "error",     "mensaje": ...}                    algo falló (por ejemplo, Ollama)
La tabla y el gráfico que ve el usuario salen del "resultado" de ejecutar_sql (datos
reales), no del texto que escribe el modelo.
"""
import json
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

APP_NAME = "valhalla_web"
USER_ID = "usuario_web"
CARPETA_ESTATICA = Path(__file__).resolve().parent / "static"
PATRON_SESION = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class PreguntaChat(BaseModel):
    mensaje: str = Field(min_length=1, max_length=2000)
    sesion: str = Field(pattern=PATRON_SESION.pattern)


def _linea(evento: dict) -> str:
    return json.dumps(evento, ensure_ascii=False, default=str) + "\n"


def _resumir(herramienta: str, respuesta: dict) -> dict:
    """ejecutar_sql viaja completo (la interfaz arma tabla y gráfico con eso).
    Las demás herramientas solo informan su estado, para no mandar el esquema entero."""
    if herramienta == "ejecutar_sql":
        return respuesta
    return {k: respuesta[k] for k in ("estado", "mensaje") if k in respuesta}


def _mensaje_de_error(exc: Exception) -> str:
    texto = f"{type(exc).__name__}: {exc}"
    pista = ""
    bajo = texto.lower()
    if any(p in bajo for p in ("unauthorized", "authentication", "401")):
        pista = " Iniciá sesión en Ollama con `ollama signin` y volvé a intentar."
    elif any(p in bajo for p in ("connection", "connect", "refused", "timeout")):
        pista = " Verificá que Ollama esté abierto (`ollama serve`)."
    return f"No se pudo obtener la respuesta del modelo.{pista} Detalle: {texto[:300]}"


def crear_app(agente=None) -> FastAPI:
    """Arma la aplicación web. `agente` permite inyectar otro agente (los tests usan
    uno con un modelo simulado); si es None se usa el root_agent real de valhalla_agent."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    app = FastAPI(title="Valhalla", docs_url=None, redoc_url=None)
    servicio_sesiones = InMemorySessionService()
    estado = {"runner": None, "agente": agente}

    def obtener_runner():
        if estado["runner"] is None:
            if estado["agente"] is None:
                from valhalla_agent.agent import root_agent  # importa el agente real
                estado["agente"] = root_agent
            estado["runner"] = Runner(
                app_name=APP_NAME, agent=estado["agente"], session_service=servicio_sesiones)
        return estado["runner"]

    async def asegurar_sesion(id_sesion: str) -> None:
        existente = await servicio_sesiones.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=id_sesion)
        if existente is None:
            await servicio_sesiones.create_session(
                app_name=APP_NAME, user_id=USER_ID, session_id=id_sesion)

    @app.get("/")
    def inicio():
        return FileResponse(CARPETA_ESTATICA / "index.html")

    @app.get("/api/estado")
    def api_estado():
        """Datos para el encabezado: tablas cargadas y rango de fechas."""
        from valhalla_agent import tools
        fuentes = tools.listar_fuentes()
        if fuentes["estado"] != "ok":
            return {"estado": "error", "mensaje": fuentes["mensaje"]}
        esquema = tools.inspeccionar_esquema()
        try:
            obtener_runner()  # carga el agente para poder informar qué modelo usa
        except Exception:  # noqa: BLE001
            pass
        modelo = getattr(estado["agente"], "model", None)
        return {
            "estado": "ok",
            "tablas": fuentes["tablas"],
            "rango_fechas": esquema.get("rango_fechas", {}),
            "modelo": getattr(modelo, "model", None) or (modelo if isinstance(modelo, str) else None),
        }

    @app.get("/api/historial")
    def api_historial():
        """Últimas consultas registradas por la capa de datos (las mismas que ve el agente)."""
        from valhalla_agent import tools
        motor, error = tools._obtener_motor()
        if error:
            return {"estado": "error", "mensaje": error, "consultas": []}
        consultas = [
            {k: c[k] for k in ("id", "fecha_hora", "pregunta", "sql", "estado", "filas")}
            for c in motor.historial.listar(30) if c.get("pregunta")
        ]
        return {"estado": "ok", "consultas": consultas}

    @app.post("/api/chat")
    async def api_chat(pregunta: PreguntaChat):
        async def generar():
            try:
                runner = obtener_runner()
                await asegurar_sesion(pregunta.sesion)
                contenido = types.Content(role="user", parts=[types.Part(text=pregunta.mensaje)])
                texto_final = []
                async for evento in runner.run_async(
                        user_id=USER_ID, session_id=pregunta.sesion, new_message=contenido):
                    for llamada in evento.get_function_calls():
                        yield _linea({"tipo": "paso", "herramienta": llamada.name,
                                      "args": dict(llamada.args or {})})
                    for resp in evento.get_function_responses():
                        yield _linea({"tipo": "resultado", "herramienta": resp.name,
                                      "respuesta": _resumir(resp.name, dict(resp.response or {}))})
                    if evento.is_final_response() and evento.content and evento.content.parts:
                        texto_final += [p.text for p in evento.content.parts
                                        if p.text and not getattr(p, "thought", False)]
                yield _linea({"tipo": "final", "texto": "\n".join(texto_final).strip()})
            except Exception as exc:  # noqa: BLE001
                yield _linea({"tipo": "error", "mensaje": _mensaje_de_error(exc)})

        return StreamingResponse(generar(), media_type="application/x-ndjson",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    app.mount("/static", StaticFiles(directory=CARPETA_ESTATICA), name="static")
    return app
