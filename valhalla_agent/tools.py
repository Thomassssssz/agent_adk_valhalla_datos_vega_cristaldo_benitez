"""Herramientas del agente. Cada una envuelve una parte de la capa de datos
(valhalla_datos) y devuelve siempre un diccionario con un campo "estado"."""
from pathlib import Path

from valhalla_datos import Historial, MotorDatos

RAIZ = Path(__file__).resolve().parent.parent
RUTA_DATOS = RAIZ / "data" / "valhalla_ventas.parquet"
RUTA_HISTORIAL = RAIZ / "historial.db"

_motor = None
_error_carga = None


def _obtener_motor():
    """Crea el motor la primera vez que se necesita y lo reutiliza después."""
    global _motor, _error_carga
    if _motor is None and _error_carga is None:
        try:
            motor = MotorDatos(historial=Historial(str(RUTA_HISTORIAL)), max_filas=50)
            motor.agregar_fuente(str(RUTA_DATOS), "ventas")
            _motor = motor
        except Exception as e: 
            _error_carga = f"No se pudieron cargar los datos: {e}"
    return _motor, _error_carga


def listar_fuentes() -> dict:
    """Lista las fuentes de datos disponibles (tablas) y cuántas filas tiene cada una.

    Usala cuando necesites saber qué información hay disponible o cuando el usuario
    pregunte qué datos se pueden consultar.

    Returns:
        Un diccionario con estado "ok" y la lista de tablas, o estado "error".
    """
    motor, error = _obtener_motor()
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


def inspeccionar_esquema() -> dict:
    """Describe la estructura de los datos: tablas, columnas, tipos, valores posibles
    de las columnas de texto y rangos de números y fechas.

    Usala SIEMPRE antes de escribir una consulta SQL, para conocer los nombres exactos
    de las columnas y los valores válidos (por ejemplo, nombres de sucursales o categorías).
    También informa el rango de fechas de los datos, necesario para períodos relativos
    como "último trimestre".

    Returns:
        Un diccionario con estado "ok", el esquema en texto y el rango de fechas,
        o estado "error".
    """
    motor, error = _obtener_motor()
    if error:
        return {"estado": "error", "mensaje": error}
    rango_fechas = {}
    for tabla, info in motor.esquema().items():
        for col in info["columnas"]:
            if col["tipo"].startswith(("DATE", "TIMESTAMP")):
                rango_fechas[f"{tabla}.{col['nombre']}"] = {"desde": col["min"], "hasta": col["max"]}
    return {"estado": "ok", "esquema": motor.esquema_texto(), "rango_fechas": rango_fechas}


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
    motor, error = _obtener_motor()
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
    motor, error = _obtener_motor()
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