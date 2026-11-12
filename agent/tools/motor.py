"""Acceso compartido al motor de datos. Se crea la primera vez que una herramienta
lo necesita y después todas reutilizan el mismo (así los datos se cargan una sola vez).

Regla de fuentes: MISMO NOMBRE DE ARCHIVO = MISMOS DATOS = UNA SOLA TABLA. El formato
(.parquet, .csv, .json...) es solo cómo está guardado. Por eso:
- valhalla_ventas.parquet y valhalla_ventas.csv son la misma tabla "ventas"; si están
  los dos, se carga uno solo (el formato que esté primero en PREFERENCIA).
- Un archivo con otro nombre (por ejemplo metas_2025.csv) es otra fuente y se carga
  como otra tabla (metas_2025)."""
from pathlib import Path

from valhalla_datos import Historial, MotorDatos
from valhalla_datos.motor import EXTENSIONES, _nombre_tabla

RAIZ = Path(__file__).resolve().parent.parent.parent
CARPETA_DATOS = RAIZ / "data"
RUTA_DATOS = CARPETA_DATOS / "valhalla_ventas.parquet"   # su nombre ("valhalla_ventas") es la tabla "ventas"
RUTA_HISTORIAL = RAIZ / "historial.db"
TABLA_VENTAS = "ventas"
# Si un mismo dataset está en varios formatos, se carga el primero de esta lista.
PREFERENCIA = [".parquet", ".csv", ".tsv", ".json", ".jsonl", ".ndjson"]

_motor = None
_error_carga = None
avisos_carga: list[str] = []   # archivos de data/ que no se pudieron leer al iniciar


def archivos_soportados() -> list[Path]:
    """Archivos de data/ con una extensión que el motor sabe leer."""
    if not CARPETA_DATOS.is_dir():
        return []
    return sorted(p for p in CARPETA_DATOS.iterdir()
                  if p.is_file() and p.suffix.lower() in EXTENSIONES)


def _orden(archivo: Path) -> int:
    ext = archivo.suffix.lower()
    return PREFERENCIA.index(ext) if ext in PREFERENCIA else len(PREFERENCIA)


def fuentes_por_dataset() -> dict[str, list[Path]]:
    """Agrupa los archivos de data/ por nombre (sin extensión). Cada grupo es un mismo
    dataset en uno o más formatos, ordenado por PREFERENCIA."""
    grupos: dict[str, list[Path]] = {}
    for archivo in archivos_soportados():
        grupos.setdefault(archivo.stem.lower(), []).append(archivo)
    return {k: sorted(v, key=_orden) for k, v in grupos.items()}


def nombre_para(motor: MotorDatos, archivo: Path) -> str:
    """Nombre de tabla para un archivo.
    - Si se llama como el de ventas (valhalla_ventas.*), es la tabla "ventas".
    - Si ya hay una tabla cargada desde un archivo con el mismo nombre (en cualquier
      formato), es esa misma tabla: se reemplaza, no se duplica.
    - Si el nombre choca con otra tabla distinta (por ejemplo un ventas.csv), se le
      agrega un sufijo para no pisarla."""
    stem = archivo.stem.lower()
    if stem == RUTA_DATOS.stem.lower():
        return TABLA_VENTAS
    for tabla in motor.tablas():
        origen = motor.origen(tabla)
        if origen and Path(origen).stem.lower() == stem:
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
            grupos = fuentes_por_dataset()
            ventas = grupos.pop(RUTA_DATOS.stem.lower(), None)
            if not ventas:
                raise FileNotFoundError(f"No hay ningún archivo {RUTA_DATOS.stem}.* en {CARPETA_DATOS}")
            motor.agregar_fuente(str(ventas[0]), TABLA_VENTAS)
            avisos_carga.clear()
            for archivos in grupos.values():          # un archivo por dataset
                archivo = archivos[0]
                try:
                    motor.agregar_fuente(str(archivo), nombre_para(motor, archivo))
                except Exception as e:  # noqa: BLE001  un archivo roto no frena al resto
                    avisos_carga.append(f"{archivo.name}: {str(e)[:200]}")
            _motor = motor
        except Exception as e:  # noqa: BLE001
            _error_carga = f"No se pudieron cargar los datos: {e}"
    return _motor, _error_carga
