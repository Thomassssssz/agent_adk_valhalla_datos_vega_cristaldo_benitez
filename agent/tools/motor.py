"""Acceso compartido al motor de datos. Se crea la primera vez que una herramienta
lo necesita y después todas reutilizan el mismo (así los datos se cargan una sola vez).

Al iniciar se cargan TODOS los archivos soportados de la carpeta data/ (Parquet, CSV,
TSV, JSON y JSONL). El Parquet de ventas queda como la tabla "ventas"; los demás toman
el nombre del archivo (por ejemplo, metas_2025.csv -> tabla metas_2025)."""
from pathlib import Path

from valhalla_datos import Historial, MotorDatos
from valhalla_datos.motor import EXTENSIONES, _nombre_tabla

RAIZ = Path(__file__).resolve().parent.parent.parent
CARPETA_DATOS = RAIZ / "data"
RUTA_DATOS = CARPETA_DATOS / "valhalla_ventas.parquet"
RUTA_HISTORIAL = RAIZ / "historial.db"

_motor = None
_error_carga = None
avisos_carga: list[str] = []   # archivos de data/ que no se pudieron leer al iniciar


def archivos_soportados() -> list[Path]:
    """Archivos de data/ con una extensión que el motor sabe leer."""
    if not CARPETA_DATOS.is_dir():
        return []
    return sorted(p for p in CARPETA_DATOS.iterdir()
                  if p.is_file() and p.suffix.lower() in EXTENSIONES)


def nombre_para(motor: MotorDatos, archivo: Path) -> str:
    """Nombre de tabla para un archivo. Si ya estaba cargado, reutiliza su tabla; si el
    nombre choca con otra tabla (por ejemplo un ventas.csv), le agrega un sufijo para
    no pisar la tabla existente."""
    archivo = archivo.resolve()
    for tabla in motor.tablas():
        if Path(motor.origen(tabla)).resolve() == archivo:
            return tabla
    base = _nombre_tabla(archivo)
    nombre, n = base, 2
    while nombre in motor.tablas():
        nombre, n = f"{base}_{n}", n + 1
    return nombre


def obtener_motor():
    """Devuelve (motor, error). Si los datos no se pudieron cargar, motor es None."""
    global _motor, _error_carga
    if _motor is None and _error_carga is None:
        try:
            motor = MotorDatos(historial=Historial(str(RUTA_HISTORIAL)), max_filas=50)
            motor.agregar_fuente(str(RUTA_DATOS), "ventas")
            avisos_carga.clear()
            for archivo in archivos_soportados():
                if archivo.resolve() == RUTA_DATOS.resolve():
                    continue
                try:
                    motor.agregar_fuente(str(archivo), nombre_para(motor, archivo))
                except Exception as e:  # noqa: BLE001  un archivo roto no frena al resto
                    avisos_carga.append(f"{archivo.name}: {str(e)[:200]}")
            _motor = motor
        except Exception as e:  # noqa: BLE001
            _error_carga = f"No se pudieron cargar los datos: {e}"
    return _motor, _error_carga
