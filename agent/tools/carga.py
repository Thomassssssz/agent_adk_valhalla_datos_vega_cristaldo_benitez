from pathlib import Path

from valhalla_datos.motor import EXTENSIONES

from . import motor as modulo_motor


def _disponibles() -> list[str]:
    return [p.name for p in modulo_motor.archivos_soportados()]


def cargar_fuente(nombre_archivo: str) -> dict:
    """Incorpora un archivo de datos de la carpeta data/ como una tabla consultable.
    Formatos: CSV, TSV, Parquet, JSON y JSONL. Si el archivo tiene el mismo nombre que
    una fuente ya cargada (por ejemplo valhalla_ventas.csv y valhalla_ventas.parquet),
    son los mismos datos en otro formato: reemplaza esa tabla en lugar de duplicarla.

    Usala solo cuando el usuario pida cargar, agregar, incorporar o actualizar un
    archivo de datos. Por seguridad acepta únicamente el NOMBRE de un archivo que esté
    dentro de la carpeta data/, nunca rutas a otras carpetas. Después de cargarlo,
    usá inspeccionar_esquema para conocer sus columnas antes de consultarlo.

    Args:
        nombre_archivo: Nombre del archivo dentro de data/. Ejemplo: metas_2025.csv

    Returns:
        Un diccionario con estado "ok" (nombre de la tabla y cantidad de filas) o
        "error" con un mensaje y la lista de archivos disponibles.
    """
    if not isinstance(nombre_archivo, str) or not nombre_archivo.strip():
        return {"estado": "error", "mensaje": "Falta el nombre del archivo.",
                "archivos_disponibles": _disponibles()}
    nombre = nombre_archivo.strip()

    # Solo un nombre de archivo: nada de rutas, unidades ni ".." (no se sale de data/).
    if any(c in nombre for c in "/\\:") or nombre in (".", ".."):
        return {"estado": "error",
                "mensaje": "Solo se aceptan nombres de archivos de la carpeta data/, sin rutas.",
                "archivos_disponibles": _disponibles()}
    carpeta = modulo_motor.CARPETA_DATOS.resolve()
    ruta = (carpeta / nombre).resolve()
    if ruta.parent != carpeta:
        return {"estado": "error", "mensaje": "El archivo tiene que estar dentro de la carpeta data/.",
                "archivos_disponibles": _disponibles()}

    if ruta.suffix.lower() not in EXTENSIONES:
        return {"estado": "error",
                "mensaje": f"Formato no soportado: {ruta.suffix or '(sin extensión)'}. "
                           f"Se aceptan: {', '.join(EXTENSIONES)}.",
                "archivos_disponibles": _disponibles()}
    if not ruta.is_file():
        return {"estado": "error", "mensaje": f"No existe el archivo {nombre} en data/.",
                "archivos_disponibles": _disponibles()}

    motor, error = modulo_motor.obtener_motor()
    if error:
        return {"estado": "error", "mensaje": error}

    tabla = modulo_motor.nombre_para(motor, ruta)
    anterior = motor.origen(tabla)
    try:
        motor.agregar_fuente(str(ruta), tabla)
        filas = motor.contar_filas(tabla)
    except Exception as e:  # noqa: BLE001
        return {"estado": "error", "mensaje": f"No se pudo leer {nombre}: {str(e)[:300]}"}

    mensaje = f"Se cargó {nombre} como la tabla {tabla} ({filas} filas)."
    if anterior and Path(anterior).name != nombre:
        mensaje += (f" Es el mismo dataset que {Path(anterior).name} en otro formato, "
                    f"así que reemplazó a la tabla {tabla} en lugar de duplicarla.")
    return {
        "estado": "ok",
        "archivo": nombre,
        "tabla": tabla,
        "filas": filas,
        "reemplazo": Path(anterior).name if anterior else None,
        "mensaje": mensaje + " Usá inspeccionar_esquema para ver sus columnas.",
    }
