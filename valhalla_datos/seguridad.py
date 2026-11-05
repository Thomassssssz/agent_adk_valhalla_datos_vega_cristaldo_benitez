"""Validación del SQL generado por el modelo: solo se permiten consultas de lectura."""
import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

MAX_LARGO_SQL = 10_000

# Nodos que nunca pueden aparecer en la consulta.
_NOMBRES_PROHIBIDOS = [
    "Insert", "Update", "Delete", "Drop", "Create", "Alter", "Command", "Copy",
    "Attach", "Detach", "Pragma", "Set", "Use", "Merge", "TruncateTable",
    "Transaction", "Into", "Lock", "Export", "Describe", "Show",
]
NODOS_PROHIBIDOS = tuple(getattr(exp, n) for n in _NOMBRES_PROHIBIDOS if hasattr(exp, n))

# Funciones que leen archivos, el entorno o la configuración del motor.
PREFIJOS_FUNCIONES_PROHIBIDAS = (
    "read_", "write_", "duckdb_", "pragma_", "sniff_", "glob", "query",
    "getenv", "current_setting", "parquet_", "which_secret", "list_secrets",
)


def validar_sql(sql: str, tablas_permitidas: list[str]) -> tuple[str | None, str | None]:
    """Devuelve (sql_validado, error). Si hay error, sql_validado es None.

    El SQL que se devuelve se regenera desde el AST, de modo que lo que se
    ejecuta es exactamente lo que se validó.
    """
    if not sql or not sql.strip():
        return None, "La consulta está vacía."
    if len(sql) > MAX_LARGO_SQL:
        return None, "La consulta es demasiado larga."

    try:
        sentencias = sqlglot.parse(sql, read="duckdb")
    except SqlglotError as e:
        return None, f"SQL inválido: {str(e)[:200]}"

    sentencias = [s for s in sentencias if s is not None and not isinstance(s, exp.Semicolon)]
    if not sentencias:
        return None, "La consulta está vacía."
    if len(sentencias) != 1:
        return None, "Solo se permite una consulta por vez."
    raiz = sentencias[0]

    if not isinstance(raiz, exp.Query):
        return None, "Solo se permiten consultas de lectura (SELECT)."

    for nodo in raiz.walk():
        if isinstance(nodo, NODOS_PROHIBIDOS):
            return None, f"Operación no permitida: {type(nodo).__name__.upper()}."

    permitidas = {t.lower() for t in tablas_permitidas}
    ctes = {c.alias_or_name.lower() for c in raiz.find_all(exp.CTE)}
    for tabla in raiz.find_all(exp.Table):
        if not isinstance(tabla.this, exp.Identifier):
            return None, "No se permiten funciones ni archivos en el FROM."
        if tabla.args.get("db") or tabla.args.get("catalog"):
            return None, "No se permite acceder a esquemas del sistema."
        nombre = tabla.name.lower()
        if nombre not in permitidas and nombre not in ctes:
            return None, (f"La tabla '{tabla.name}' no existe. "
                          f"Tablas disponibles: {', '.join(sorted(permitidas))}.")

    for fn in raiz.find_all(exp.Func):
        nombre_fn = (fn.name if isinstance(fn, exp.Anonymous) else fn.sql_name()).lower()
        if nombre_fn.startswith(PREFIJOS_FUNCIONES_PROHIBIDAS):
            return None, f"Función no permitida: {nombre_fn}."

    return raiz.sql(dialect="duckdb"), None