"""Interfaz web de Valhalla: una pantalla de chat que habla con el mismo agente
que `adk web`, pero que además muestra de dónde salió cada dato (SQL, tabla, gráfico)."""
from .server import crear_app

__all__ = ["crear_app"]
