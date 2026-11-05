"""Historial y trazabilidad de consultas (SQLite)."""
import json
import sqlite3
import threading
from datetime import datetime


class Historial:
    def __init__(self, ruta: str = "historial.db"):
        self._con = sqlite3.connect(ruta, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._con.execute("""
                CREATE TABLE IF NOT EXISTS consultas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha_hora TEXT NOT NULL,
                    pregunta TEXT,
                    tablas TEXT,
                    sql TEXT,
                    estado TEXT,
                    filas INTEGER,
                    duracion_ms INTEGER,
                    error TEXT,
                    respuesta TEXT
                )""")
            self._con.commit()

    def registrar(self, *, pregunta=None, tablas=None, sql=None, estado=None,
                  filas=None, duracion_ms=None, error=None) -> int:
        with self._lock:
            cur = self._con.execute(
                "INSERT INTO consultas (fecha_hora, pregunta, tablas, sql, estado, filas, duracion_ms, error)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (datetime.now().isoformat(timespec="seconds"), pregunta,
                 json.dumps(tablas or []), sql, estado, filas, duracion_ms, error),
            )
            self._con.commit()
            return cur.lastrowid

    def guardar_respuesta(self, id_consulta: int, respuesta: str) -> None:
        with self._lock:
            self._con.execute("UPDATE consultas SET respuesta = ? WHERE id = ?", (respuesta, id_consulta))
            self._con.commit()

    def listar(self, limite: int = 20) -> list[dict]:
        with self._lock:
            cur = self._con.execute("SELECT * FROM consultas ORDER BY id DESC LIMIT ?", (limite,))
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, fila)) for fila in cur.fetchall()]

    def obtener(self, id_consulta: int) -> dict | None:
        with self._lock:
            cur = self._con.execute("SELECT * FROM consultas WHERE id = ?", (id_consulta,))
            cols = [c[0] for c in cur.description]
            fila = cur.fetchone()
            return dict(zip(cols, fila)) if fila else None