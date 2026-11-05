from pathlib import Path

from .motor import obtener_motor


def listar_fuentes() -> dict:
    """Lista las fuentes de datos disponibles (tablas) y cuántas filas tiene cada una.

    Usala cuando necesites saber qué información hay disponible o cuando el usuario
    pregunte qué datos se pueden consultar.

    Returns:
        Un diccionario con estado "ok" y la lista de tablas, o estado "error".
    """
    motor, error = obtener_motor()
    if error:
        return {"estado": "error", "mensaje": error}
    esquema = motor.esquema()
    return {
        "estado": "ok",
        "tablas": [
            {"nombre": nombre, "filas": info["filas"], "origen": Path(info["origen"]).name}
            for nombre, info in esquema.items()
        ],
    }