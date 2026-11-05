from .motor import obtener_motor


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
    motor, error = obtener_motor()
    if error:
        return {"estado": "error", "mensaje": error}
    rango_fechas = {}
    for tabla, info in motor.esquema().items():
        for col in info["columnas"]:
            if col["tipo"].startswith(("DATE", "TIMESTAMP")):
                rango_fechas[f"{tabla}.{col['nombre']}"] = {"desde": col["min"], "hasta": col["max"]}
    return {"estado": "ok", "esquema": motor.esquema_texto(), "rango_fechas": rango_fechas}