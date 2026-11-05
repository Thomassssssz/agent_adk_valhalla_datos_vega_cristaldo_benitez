from .motor import obtener_motor


def consultar_historial(limite: int = 5) -> dict:
    """Devuelve las últimas consultas realizadas (pregunta, SQL, estado y fecha).

    Usala cuando el usuario pregunte por consultas o preguntas anteriores.

    Args:
        limite: Cantidad de consultas a devolver, entre 1 y 20.

    Returns:
        Un diccionario con estado "ok" y la lista de consultas, "vacio" si todavía
        no hay ninguna, o "error" si el argumento es inválido.
    """
    if isinstance(limite, bool) or not isinstance(limite, int) or not 1 <= limite <= 20:
        return {"estado": "error", "mensaje": "El límite debe ser un número entero entre 1 y 20."}
    motor, error = obtener_motor()
    if error:
        return {"estado": "error", "mensaje": error}
    consultas = motor.historial.listar(limite)
    if not consultas:
        return {"estado": "vacio", "mensaje": "Todavía no hay consultas en el historial."}
    return {
        "estado": "ok",
        "consultas": [
            {k: c[k] for k in ("id", "fecha_hora", "pregunta", "sql", "estado", "filas")}
            for c in consultas
        ],
    }