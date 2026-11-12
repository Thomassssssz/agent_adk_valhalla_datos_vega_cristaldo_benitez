# Valhalla Datos: asistente inteligente para consultar datos en lenguaje natural

Prototipo de un agente de IA (Python + Google ADK) que permite a responsables de negocio de **Valhalla S.A.** consultar los datos de ventas haciendo preguntas en español, sin saber SQL. Trabajo del seminario "Modelos y Aplicaciones de la IA" (Instituto Politécnico Formosa), basado en la _Problemática 02: Democratización del acceso a los datos mediante inteligencia artificial_ (el enunciado está en `docs/`).

**Integrantes:** Vega Tomas, Cristaldo Facundo, Benítez Franco.

## ¿Qué hace?

El usuario escribe una pregunta, por ejemplo _"¿Qué categoría generó mayores ingresos durante el último trimestre?"_. El agente:

1. Inspecciona la estructura de los datos (tablas, columnas, valores posibles, rango de fechas).
2. Genera una consulta SQL de solo lectura.
3. La ejecuta de forma segura sobre los datos.
4. Responde en lenguaje simple y **muestra el SQL utilizado**, para poder verificar de dónde salió cada cifra.

Si la pregunta es ambigua, pide una aclaración; si los datos no alcanzan (por ejemplo, margen de ganancia o stock), lo dice en lugar de inventar una respuesta.

## Herramientas del agente

Definidas en `agent/tools/` (un archivo por herramienta). Cada una tiene una responsabilidad distinta y valida sus argumentos.

| Herramienta                        | Qué hace                                                                                                                                                             |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `listar_fuentes()`                 | Lista las tablas disponibles y cuántas filas tiene cada una.                                                                                                         |
| `inspeccionar_esquema()`           | Devuelve columnas, tipos, valores posibles de las columnas de texto y rangos de números y fechas. Se usa siempre antes de escribir SQL.                              |
| `ejecutar_sql(consulta, pregunta)` | Ejecuta una consulta SQL de solo lectura (DuckDB). Devuelve estado (`ok`, `vacio`, `rechazada`, `error`, `timeout`), columnas, filas (máximo 50) y el SQL ejecutado. |
| `consultar_historial(limite)`      | Devuelve las últimas consultas realizadas (pregunta, SQL, estado y fecha). El límite debe estar entre 1 y 20.                                                        |
| `cargar_fuente(nombre_archivo)`    | Incorpora un archivo de la carpeta `data/` (CSV, TSV, Parquet, JSON o JSONL) como tabla nueva, o la actualiza. Por seguridad solo acepta nombres de archivos de `data/`, nunca rutas. |

## Seguridad

Las consultas no pueden modificar ni borrar información. Hay varias barreras independientes:

- **Instrucciones del agente:** nunca debe modificar, borrar ni crear datos.
- **Validación del SQL** (`valhalla_datos/seguridad.py`, con `sqlglot`): solo se acepta una sentencia `SELECT`, únicamente sobre las tablas cargadas, sin funciones que lean archivos o el entorno ni acceso a esquemas del sistema. El SQL que se ejecuta se regenera desde el árbol sintáctico validado.
- **Segunda verificación con el parser de DuckDB:** debe ser una única sentencia `SELECT`.
- **Conexión aislada:** la conexión que ejecuta las consultas no tiene acceso a archivos del disco, red ni extensiones.
- **Límites:** máximo de filas por resultado, tiempo máximo por consulta (30 s) y límite de memoria.
- **Trazabilidad:** cada consulta, incluso las rechazadas, se guarda en `historial.db` (pregunta, SQL, estado, filas y duración).

## Estructura del proyecto

```
├── README.md
├── requirements.txt
├── data/
│   └── valhalla_ventas.parquet    # dataset de ventas 2025 (1.000.000 de filas)
├── docs/                          # enunciado de la problemática
├── agent/                         # el agente (Google ADK)
│   ├── agent.py                   # modelo y herramientas registradas
│   ├── instructions.py            # instrucciones (prompt) del agente
│   └── tools/                     # una herramienta por archivo
│       ├── motor.py               # acceso compartido al motor de datos
│       ├── fuentes.py             # listar_fuentes
│       ├── esquema.py             # inspeccionar_esquema
│       ├── consulta.py            # ejecutar_sql
│       ├── historial_consultas.py # consultar_historial
│       └── carga.py               # cargar_fuente
├── valhalla_datos/                # capa de datos
│   ├── motor.py                   # carga de fuentes, esquema y ejecución segura
│   ├── seguridad.py               # validación del SQL
│   └── historial.py               # historial de consultas (SQLite)
├── valhalla_web/                  # interfaz web con temática Valhalla (opcional)
│   ├── server.py                  # servidor FastAPI que conecta el navegador con el agente
│   └── static/                    # página, estilos, JS y tipografías
└── tests/
    ├── test_datos.py              # 31 pruebas de la capa de datos
    ├── test_fuentes.py            # 19 pruebas de la carga de fuentes
    └── test_web.py                # 12 pruebas de la interfaz web
```

## Datos

El dataset `data/valhalla_ventas.parquet` tiene 1.000.000 de ventas del 01/01/2025 al 31/12/2025, con las columnas: `venta_id`, `fecha`, `cliente_id`, `producto_id`, `producto`, `categoria`, `sucursal`, `provincia`, `cantidad`, `precio_unitario`, `descuento`, `total`, `metodo_pago` y `canal`.

El mismo dataset existe también en CSV (129 MB), que **no se incluye en el repositorio** porque GitHub no admite archivos de más de 100 MB; el Parquet contiene los mismos datos.

El motor (`MotorDatos`) puede incorporar fuentes CSV, TSV, Parquet y JSON/JSONL con `agregar_fuente(ruta, nombre)`.

**Fuentes del agente:** al iniciar, el agente carga **todos los archivos soportados de la carpeta `data/`**. El Parquet de ventas queda como la tabla `ventas`; cada archivo adicional toma el nombre del archivo (por ejemplo, `data/valhalla_ventas.csv` → tabla `valhalla_ventas`, `data/metas_2025.csv` → tabla `metas_2025`). También se puede copiar un archivo a `data/` con el agente andando y pedirle en el chat: _"Cargá el archivo metas_2025.csv"_. Un archivo que no se pueda leer no impide cargar el resto, y un archivo cuyo nombre choque con una tabla existente recibe un sufijo para no pisarla.

## Requisitos

- Python 3.10 o superior (probado con 3.14).
- [Ollama](https://ollama.com) instalado. El modelo se ejecuta **localmente**: los datos no salen de la computadora.
- Modelo: `qwen3:8b` (vía LiteLLM).

## Instalación

Ejemplo para Windows (PowerShell), con `uv`:

```
python -m uv venv env
env\Scripts\activate
python -m uv pip install -r requirements.txt
```

Si `uv` está disponible como comando, alcanza con `uv venv env` y `uv pip install -r requirements.txt`. Con pip estándar:

```
python -m venv env
env\Scripts\activate
pip install -r requirements.txt
```

Si dentro del entorno activado aparece `No module named uv`, instalá llamando a `uv` desde el Python global:

```
C:\Python314\python.exe -m uv pip install --python env\Scripts\python.exe -r requirements.txt
```

## Cómo usarlo

1. Descargá el modelo (solo la primera vez) y comprobá que responde:

   ```
   ollama pull qwen3:8b
   ollama run qwen3:8b
   ```

2. Con el entorno activado, desde la carpeta del repositorio, levantá la interfaz web de ADK:

   ```
   adk web .
   ```

   Si Windows bloquea `adk.exe` (política de control de aplicaciones), usá:

   ```
   python -m google.adk.cli web .
   ```

3. Abrí `http://127.0.0.1:8000` y elegí **`agent`** en el selector.
4. Escribí tus preguntas. En las pestañas **Events** y **Trace** se ve qué herramientas usa el agente en cada respuesta.

En Windows la recarga automática no funciona: después de cambiar código, detené el servidor con `Ctrl+C` y volvé a iniciarlo.

### Interfaz web de Valhalla (opcional)

Además de `adk web`, el proyecto incluye una pantalla propia, pensada para quien no es técnico. Usa el mismo agente y muestra, junto con la respuesta, la tabla y el gráfico con los datos reales y el SQL ejecutado ("Cómo lo calculé"). Tiene además una barra lateral con la memoria de consultas.

```
python -m valhalla_web
```

Abrí `http://127.0.0.1:8080`. Es independiente de `adk web` (que usa el puerto 8000): no hace falta cambiar nada del agente.

### Ejemplos de preguntas

- ¿Qué datos tenés disponibles?
- ¿Cuál fue el producto más vendido durante septiembre?
- ¿Qué categoría generó mayores ingresos durante el último trimestre?
- ¿Cuánto se vendió en Córdoba durante el último trimestre?
- ¿Cuál fue el comportamiento de las ventas durante los últimos seis meses?
- ¿Qué clientes realizaron más compras?
- ¿Qué preguntas hice antes?

## Pruebas

Pruebas automáticas de la capa de datos (seguridad del SQL y ejecución sobre los datos reales) y de la interfaz web (con un modelo simulado, sin necesidad de Ollama):

```
python -m pytest -q
```

Además se probó el agente en `adk web` y se comparó con cálculos propios sobre el Parquet. Por ejemplo: total de ventas (1.000.000), producto más vendido en septiembre (Cargador USB-C 25W, 35.415 unidades), ventas en Córdoba en octubre-diciembre (21.712.028.100) e ingresos por categoría en el último trimestre (Informatica, 69.907.458.000). También se verificó que el agente informe cuando una pregunta no puede responderse con los datos (margen de ganancia) y que rechace pedidos de borrar datos.

## Criterios de aceptación

| Criterio                                   | Cómo se cumple                                                          |
| ------------------------------------------ | ----------------------------------------------------------------------- |
| Incorporar diferentes fuentes              | Carga automática de `data/` y herramienta `cargar_fuente` (CSV, TSV, Parquet, JSON) |
| Inspeccionar estructuras                   | `inspeccionar_esquema` y `listar_fuentes`                               |
| Interpretar lenguaje natural               | Agente ADK con modelo de lenguaje                                       |
| Generar y ejecutar consultas               | `ejecutar_sql`                                                          |
| Resultados comprensibles y respaldados     | Instrucciones del agente: responde solo con lo que devuelve la consulta |
| Visualizar las consultas                   | El SQL se muestra en la respuesta y queda en el historial               |
| Preguntas ambiguas o imposibles            | Instrucciones del agente y estado `vacio` en las consultas              |
| Impedir operaciones no autorizadas         | Validación del SQL, conexión aislada y tests                            |
| Distintas preguntas sobre un mismo dataset | En validación                                                           |

## Limitaciones conocidas

- El modelo es pequeño y **puede equivocarse al calcular de memoria** (por ejemplo, sumar totales). Para mitigarlo, las instrucciones le exigen que cualquier cifra salga de una consulta, y el SQL siempre es visible para poder verificarla.
- Los períodos relativos ("último trimestre", "últimos seis meses") se calculan a partir de la última fecha de los datos (31/12/2025), no de la fecha actual.
- Los datos no indican la moneda de los montos, por lo que el agente no la menciona.
- El historial guarda la pregunta, el SQL, el estado y la cantidad de filas, pero no el resultado completo.
- Todavía no se incorporaron bases de datos relacionales ni archivos `.sql` como fuente.
- El modelo (`qwen3:8b`, ~5 GB) corre en la computadora: necesita memoria suficiente y responde más lento que un modelo en la nube.
