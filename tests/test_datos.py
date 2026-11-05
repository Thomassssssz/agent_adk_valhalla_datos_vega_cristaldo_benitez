"""Pruebas de la capa de datos: seguridad del SQL y ejecución sobre el Parquet."""
from pathlib import Path

import pytest

from valhalla_datos import MotorDatos
from valhalla_datos.seguridad import validar_sql

TABLAS = ["ventas"]
PARQUET = Path("data/valhalla_ventas.parquet")


# ---------- Consultas permitidas ----------
@pytest.mark.parametrize("sql", [
    "SELECT COUNT(*) FROM ventas",
    "SELECT COUNT(*) FROM ventas;",
    "SELECT categoria, SUM(total) FROM ventas GROUP BY 1 ORDER BY 2 DESC",
    "WITH m AS (SELECT sucursal, SUM(total) t FROM ventas GROUP BY 1) SELECT * FROM m",
    "SELECT producto, SUM(cantidad) OVER (PARTITION BY categoria) FROM ventas",
    "FROM ventas SELECT COUNT(*)",
])
def test_consultas_de_lectura_permitidas(sql):
    sql_ok, error = validar_sql(sql, TABLAS)
    assert error is None and sql_ok


# ---------- Consultas que deben bloquearse ----------
@pytest.mark.parametrize("sql", [
    "DROP TABLE ventas",
    "DELETE FROM ventas",
    "UPDATE ventas SET total = 0",
    "INSERT INTO ventas SELECT * FROM ventas",
    "CREATE TABLE x AS SELECT 1",
    "SELECT 1; DROP TABLE ventas",
    "COPY ventas TO 'salida.csv'",
    "ATTACH 'otra.db'",
    "PRAGMA database_list",
    "SET memory_limit = '1MB'",
    "INSTALL httpfs",
    "SELECT * FROM read_csv('archivo.csv')",
    "SELECT * FROM 'archivo.csv'",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM duckdb_tables()",
    "SELECT getenv('HOME')",
    "SELECT * FROM tabla_inexistente",
    "",
    "   ",
])
def test_consultas_peligrosas_bloqueadas(sql):
    sql_ok, error = validar_sql(sql, TABLAS)
    assert sql_ok is None and error


# ---------- Motor sobre los datos reales ----------
@pytest.fixture(scope="module")
def motor():
    if not PARQUET.exists():
        pytest.skip("Falta data/valhalla_ventas.parquet")
    m = MotorDatos()
    m.agregar_fuente(str(PARQUET), "ventas")
    return m


def test_cuenta_filas(motor):
    r = motor.ejecutar_sql("SELECT COUNT(*) FROM ventas")
    assert r["ok"] and r["filas"][0][0] == 1_000_000


def test_resultado_vacio_se_informa(motor):
    r = motor.ejecutar_sql("SELECT * FROM ventas WHERE sucursal = 'Mendoza'")
    assert r["estado"] == "vacio" and r["ok"] and r["mensaje"]


def test_limite_de_filas(motor):
    r = motor.ejecutar_sql("SELECT * FROM ventas")
    assert len(r["filas"]) == motor.max_filas and r["truncado"]


def test_columna_inexistente_devuelve_error(motor):
    r = motor.ejecutar_sql("SELECT columna_falsa FROM ventas")
    assert r["estado"] == "error" and not r["ok"]


def test_ataque_no_modifica_datos(motor):
    for ataque in ["DELETE FROM ventas", "DROP TABLE ventas", "UPDATE ventas SET total = 0"]:
        assert motor.ejecutar_sql(ataque)["estado"] == "rechazada"
    assert motor.ejecutar_sql("SELECT COUNT(*) FROM ventas")["filas"][0][0] == 1_000_000


def test_el_esquema_describe_las_columnas(motor):
    columnas = {c["nombre"] for c in motor.esquema()["ventas"]["columnas"]}
    assert {"fecha", "producto", "categoria", "sucursal", "total"} <= columnas