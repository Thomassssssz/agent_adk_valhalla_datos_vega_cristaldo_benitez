"""Pruebas de la carga de fuentes: al iniciar se leen todos los archivos de data/ y
cargar_fuente incorpora archivos nuevos, solo desde esa carpeta."""
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from agent.tools import cargar_fuente, ejecutar_sql, listar_fuentes
from agent.tools import motor as modulo_motor


@pytest.fixture
def carpeta_datos(tmp_path, monkeypatch):
    """Carpeta data/ temporal con un Parquet de ventas chico, un CSV y un JSON."""
    datos = tmp_path / "data"
    datos.mkdir()
    pq.write_table(pa.table({"sucursal": ["Cordoba", "Posadas", "Cordoba"],
                             "total": [100.0, 50.0, 25.0]}),
                   datos / "valhalla_ventas.parquet")
    (datos / "metas_2025.csv").write_text("sucursal,meta\nCordoba,120\nPosadas,40\n", encoding="utf-8")
    (datos / "sucursales.json").write_text(
        json.dumps([{"sucursal": "Cordoba", "provincia": "Cordoba"},
                    {"sucursal": "Posadas", "provincia": "Misiones"}]), encoding="utf-8")
    (datos / "notas.txt").write_text("no es un formato de datos", encoding="utf-8")

    monkeypatch.setattr(modulo_motor, "CARPETA_DATOS", datos)
    monkeypatch.setattr(modulo_motor, "RUTA_DATOS", datos / "valhalla_ventas.parquet")
    monkeypatch.setattr(modulo_motor, "RUTA_HISTORIAL", tmp_path / "historial.db")
    monkeypatch.setattr(modulo_motor, "_motor", None)
    monkeypatch.setattr(modulo_motor, "_error_carga", None)
    yield datos
    modulo_motor._motor = None
    modulo_motor._error_carga = None


def _tablas():
    return {t["nombre"]: t for t in listar_fuentes()["tablas"]}


def test_al_iniciar_carga_parquet_csv_y_json(carpeta_datos):
    tablas = _tablas()
    assert set(tablas) == {"ventas", "metas_2025", "sucursales"}   # notas.txt se ignora
    assert tablas["ventas"]["filas"] == 3
    assert tablas["metas_2025"]["origen"] == "metas_2025.csv"
    assert tablas["sucursales"]["origen"] == "sucursales.json"


def test_se_puede_consultar_y_cruzar_fuentes_distintas(carpeta_datos):
    r = ejecutar_sql("SELECT v.sucursal, SUM(v.total) AS ventas, m.meta FROM ventas v "
                     "JOIN metas_2025 m USING (sucursal) GROUP BY v.sucursal, m.meta ORDER BY 1", "cruce")
    assert r["estado"] == "ok"
    assert r["filas"] == [["Cordoba", 125.0, 120], ["Posadas", 50.0, 40]]


def test_cargar_fuente_incorpora_un_csv_nuevo(carpeta_datos):
    listar_fuentes()  # el motor ya está iniciado antes de que aparezca el archivo
    (carpeta_datos / "devoluciones.csv").write_text("venta_id,motivo\n1,falla\n2,talle\n", encoding="utf-8")
    r = cargar_fuente("devoluciones.csv")
    assert r["estado"] == "ok" and r["tabla"] == "devoluciones" and r["filas"] == 2
    assert "devoluciones" in _tablas()
    assert ejecutar_sql("SELECT COUNT(*) FROM devoluciones")["filas"] == [[2]]


def test_volver_a_cargar_actualiza_la_misma_tabla(carpeta_datos):
    listar_fuentes()
    (carpeta_datos / "metas_2025.csv").write_text("sucursal,meta\nCordoba,1\n", encoding="utf-8")
    r = cargar_fuente("metas_2025.csv")
    assert r["estado"] == "ok" and r["tabla"] == "metas_2025" and r["filas"] == 1


def test_un_archivo_llamado_ventas_no_pisa_la_tabla_principal(carpeta_datos):
    (carpeta_datos / "ventas.csv").write_text("x\n1\n", encoding="utf-8")
    r = cargar_fuente("ventas.csv")
    assert r["estado"] == "ok" and r["tabla"] != "ventas"
    assert _tablas()["ventas"]["filas"] == 3


@pytest.mark.parametrize("nombre", [
    "../historial.db", "..\\historial.db", "C:\\Windows\\win.ini", "/etc/passwd",
    "..", ".", "sub/archivo.csv",
])
def test_rechaza_rutas_fuera_de_data(carpeta_datos, nombre):
    r = cargar_fuente(nombre)
    assert r["estado"] == "error" and "archivos_disponibles" in r


@pytest.mark.parametrize("nombre", ["", "   ", None, 123])
def test_rechaza_argumentos_invalidos(carpeta_datos, nombre):
    assert cargar_fuente(nombre)["estado"] == "error"


def test_rechaza_formato_no_soportado(carpeta_datos):
    r = cargar_fuente("notas.txt")
    assert r["estado"] == "error" and "Formato no soportado" in r["mensaje"]


def test_archivo_inexistente_lista_los_disponibles(carpeta_datos):
    r = cargar_fuente("no_existe.csv")
    assert r["estado"] == "error"
    assert "metas_2025.csv" in r["archivos_disponibles"]


def test_un_archivo_roto_no_impide_cargar_el_resto(carpeta_datos):
    (carpeta_datos / "roto.json").write_text("{esto no es json", encoding="utf-8")
    assert "ventas" in _tablas()
    assert any("roto.json" in a for a in modulo_motor.avisos_carga)
