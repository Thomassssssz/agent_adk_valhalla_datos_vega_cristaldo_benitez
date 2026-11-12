"""Motor de datos: carga fuentes, describe su estructura y ejecuta SQL de solo lectura."""
import re
import threading
import time
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb

from .historial import Historial
from .seguridad import validar_sql

EXTENSIONES = {
    ".csv": "read_csv_auto", ".tsv": "read_csv_auto",
    ".parquet": "read_parquet",
    ".json": "read_json_auto", ".jsonl": "read_json_auto", ".ndjson": "read_json_auto",
}


def _nombre_tabla(ruta: Path) -> str:
    base = unicodedata.normalize("NFKD", ruta.stem).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "_", base.lower()).strip("_")
    return base if base and not base[0].isdigit() else f"t_{base}"


def _json_seguro(valor):
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, float) and valor != valor:  # NaN
        return None
    return valor


class MotorDatos:
    def __init__(self, historial: Historial | None = None, max_filas: int = 200,
                 timeout_s: float = 30, memoria: str = "2GB"):
        self.historial = historial
        self.max_filas = max_filas
        self.timeout_s = timeout_s
        # Conexión "cargadora": lee los archivos. Nunca ejecuta SQL del modelo.
        self._cargador = duckdb.connect()
        # Conexión "consultas": sin acceso a archivos, red ni extensiones.
        self._con = duckdb.connect(config={"enable_external_access": False, "memory_limit": memoria})
        self._lock = threading.Lock()
        self._fuentes: dict[str, str] = {}   # tabla -> ruta de origen

    # ---------- RF01: incorporar fuentes ----------
    def agregar_fuente(self, ruta: str, nombre: str | None = None) -> str:
        ruta_p = Path(ruta)
        if not ruta_p.is_file():
            raise FileNotFoundError(f"No existe el archivo: {ruta}")
        lector = EXTENSIONES.get(ruta_p.suffix.lower())
        if lector is None:
            raise ValueError(f"Formato no soportado: {ruta_p.suffix}. Usar: {', '.join(EXTENSIONES)}")
        tabla = nombre or _nombre_tabla(ruta_p)
        ruta_sql = str(ruta_p).replace("'", "''")
        datos = self._cargador.sql(f"SELECT * FROM {lector}('{ruta_sql}')").to_arrow_table()
        with self._lock:
            self._con.unregister(tabla)
            self._con.register(tabla, datos)
        self._fuentes[tabla] = str(ruta_p)
        return tabla

    def tablas(self) -> list[str]:
        return sorted(self._fuentes)

    def origen(self, tabla: str) -> str | None:
        """Ruta del archivo del que se cargó una tabla (None si no existe)."""
        return self._fuentes.get(tabla)

    def contar_filas(self, tabla: str) -> int:
        """Cantidad de filas de una tabla cargada (no pasa por el historial)."""
        if tabla not in self._fuentes:
            raise KeyError(f"No existe la tabla: {tabla}")
        with self._lock:
            return self._con.execute(f'SELECT count(*) FROM "{tabla}"').fetchone()[0]

    # ---------- RF02: inspección ----------
    def esquema(self, max_valores: int = 25) -> dict:
        """Estructura de cada tabla: columnas, tipos, nulos, rangos y valores posibles."""
        resultado = {}
        with self._lock:
            for tabla in self.tablas():
                filas = self._con.execute(f'SELECT count(*) FROM "{tabla}"').fetchone()[0]
                info = self._con.execute(f'DESCRIBE "{tabla}"').fetchall()
                columnas = []
                for nombre, tipo, *_ in info:
                    c = f'"{nombre}"'
                    nulos, distintos = self._con.execute(
                        f'SELECT count(*) - count({c}), approx_count_distinct({c}) FROM "{tabla}"').fetchone()
                    col = {"nombre": nombre, "tipo": tipo, "nulos": nulos, "distintos": distintos}
                    if tipo == "VARCHAR" and distintos <= max_valores:
                        col["valores"] = [v[0] for v in self._con.execute(
                            f'SELECT DISTINCT {c} FROM "{tabla}" WHERE {c} IS NOT NULL ORDER BY 1').fetchall()]
                    elif tipo != "VARCHAR" and tipo != "BOOLEAN":
                        mn, mx = self._con.execute(f'SELECT min({c}), max({c}) FROM "{tabla}"').fetchone()
                        col["min"], col["max"] = _json_seguro(mn), _json_seguro(mx)
                    columnas.append(col)
                resultado[tabla] = {"origen": self._fuentes[tabla], "filas": filas, "columnas": columnas}
        return resultado

    def esquema_texto(self) -> str:
        """Descripción compacta del esquema, pensada para pegar en el prompt del modelo."""
        lineas = []
        for tabla, info in self.esquema().items():
            lineas.append(f"Tabla {tabla} ({info['filas']:,} filas):")
            for c in info["columnas"]:
                extra = ""
                if "valores" in c:
                    extra = f" valores: {c['valores']}"
                elif "min" in c:
                    extra = f" rango: {c['min']} a {c['max']}"
                lineas.append(f"  - {c['nombre']} {c['tipo']}{extra}")
        return "\n".join(lineas)

    # ---------- RF05/RF06: ejecución segura ----------
    def ejecutar_sql(self, sql: str, pregunta: str | None = None) -> dict:
        inicio = time.perf_counter()
        sql_ok, error = validar_sql(sql, self.tablas())
        if error is None:
            # Segunda barrera: el parser propio de DuckDB debe ver una sola sentencia SELECT.
            sentencias = self._con.extract_statements(sql_ok)
            if len(sentencias) != 1 or sentencias[0].type != duckdb.StatementType.SELECT:
                error = "Solo se permite una consulta SELECT."

        if error is not None:
            return self._cerrar("rechazada", sql, error, pregunta, inicio)

        temporizador = threading.Timer(self.timeout_s, self._con.interrupt)
        try:
            with self._lock:
                temporizador.start()
                cur = self._con.execute(f"SELECT * FROM ({sql_ok}) AS _q LIMIT {self.max_filas + 1}")
                columnas = [d[0] for d in cur.description]
                filas = cur.fetchall()
        except duckdb.InterruptException:
            return self._cerrar("timeout", sql_ok,
                                f"La consulta superó el límite de {self.timeout_s:.0f} segundos.", pregunta, inicio)
        except duckdb.Error as e:
            return self._cerrar("error", sql_ok, str(e)[:300], pregunta, inicio)
        finally:
            temporizador.cancel()

        truncado = len(filas) > self.max_filas
        filas = [[_json_seguro(v) for v in f] for f in filas[: self.max_filas]]
        estado = "vacio" if not filas else "ok"
        mensaje = ("La consulta se ejecutó pero no devolvió filas. Revisá filtros, fechas y valores exactos."
                   if estado == "vacio" else None)
        return self._cerrar(estado, sql_ok, None, pregunta, inicio,
                            columnas=columnas, filas=filas, truncado=truncado, mensaje=mensaje)

    def _cerrar(self, estado, sql, error, pregunta, inicio, columnas=None, filas=None,
                truncado=False, mensaje=None) -> dict:
        duracion = int((time.perf_counter() - inicio) * 1000)
        id_historial = None
        if self.historial:
            id_historial = self.historial.registrar(
                pregunta=pregunta, tablas=self.tablas(), sql=sql, estado=estado,
                filas=len(filas) if filas else 0, duracion_ms=duracion, error=error)
        return {
            "ok": estado in ("ok", "vacio"), "estado": estado, "sql": sql,
            "columnas": columnas or [], "filas": filas or [], "truncado": truncado,
            "error": error, "mensaje": mensaje or error, "duracion_ms": duracion,
            "id_historial": id_historial,
        }