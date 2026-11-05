"""Acceso compartido al motor de datos. Se crea la primera vez que una herramienta
lo necesita y después todas reutilizan el mismo (así los datos se cargan una sola vez)."""
from pathlib import Path

from valhalla_datos import Historial, MotorDatos

RAIZ = Path(__file__).resolve().parent.parent.parent
RUTA_DATOS = RAIZ / "data" / "valhalla_ventas.parquet"
RUTA_HISTORIAL = RAIZ / "historial.db"

_motor = None
_error_carga = None


def obtener_motor():
    """Devuelve (motor, error). Si los datos no se pudieron cargar, motor es None."""
    global _motor, _error_carga
    if _motor is None and _error_carga is None:
        try:
            motor = MotorDatos(historial=Historial(str(RUTA_HISTORIAL)), max_filas=50)
            motor.agregar_fuente(str(RUTA_DATOS), "ventas")
            _motor = motor
        except Exception as e:  # noqa: BLE001
            _error_carga = f"No se pudieron cargar los datos: {e}"
    return _motor, _error_carga