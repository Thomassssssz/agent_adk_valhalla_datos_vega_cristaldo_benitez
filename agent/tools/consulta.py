from .motor import obtener_motor


def ejecutar_sql(consulta: str, pregunta: str = "") -> dict:
    """Ejecuta una consulta SQL de SOLO LECTURA (dialecto DuckDB) sobre los datos.

    Solo se aceptan consultas SELECT sobre las tablas disponibles. Cualquier intento
    de modificar, borrar o crear datos es rechazado. Devuelve como máximo 50 filas:
    para resultados grandes, usá agregaciones (SUM, COUNT, AVG), GROUP BY y LIMIT.

    Args:
        consulta: La consulta SQL a ejecutar. Ejemplo:
            SELECT categoria, SUM(total) AS ingresos FROM ventas GROUP BY categoria
        pregunta: La pregunta original del usuario, para guardarla en el historial.

    Returns:
        Un diccionario con "estado" ("ok", "vacio", "rechazada", "error" o "timeout"),
        las columnas, las filas, el SQL ejecutado y un mensaje explicativo.
    """
    if not isinstance(consulta, str) or not consulta.strip():
        return {"estado": "error", "mensaje": "Falta la consulta SQL."}
    motor, error = obtener_motor()
    if error:
        return {"estado": "error", "mensaje": error}
    r = motor.ejecutar_sql(consulta, pregunta=pregunta if isinstance(pregunta, str) else "")
    resultado = {
        "estado": r["estado"],
        "sql": r["sql"],
        "columnas": r["columnas"],
        "filas": r["filas"],
        "mensaje": r["mensaje"],
    }
    if r["truncado"]:
        resultado["mensaje"] = ("El resultado se cortó en 50 filas. "
                                "Usá agregaciones, filtros o LIMIT para reducirlo.")
    return resultado