import os

os.environ["OLLAMA_API_BASE"] = "http://localhost:11434"

from google.adk.agents.llm_agent import Agent
from google.adk.models.lite_llm import LiteLlm

from .instructions import INSTRUCCIONES
from .tools import (
    cargar_fuente,
    consultar_historial,
    ejecutar_sql,
    inspeccionar_esquema,
    listar_fuentes,
)

root_agent = Agent(
    model=LiteLlm("ollama_chat/qwen3:8b"),
    name="root_agent",
    description="Asistente que responde preguntas de negocio de Valhalla consultando sus datos de ventas.",
    instruction=INSTRUCCIONES,
    tools=[listar_fuentes, inspeccionar_esquema, ejecutar_sql, consultar_historial, cargar_fuente],
)