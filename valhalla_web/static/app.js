/* Valhalla S.A. — lógica de la interfaz.
   Habla con el servidor (POST /api/chat) y dibuja, en vivo, los pasos del agente,
   su respuesta y los datos reales que devolvió ejecutar_sql (tabla y gráfico).
   Todo el contenido se arma con textContent / nodos DOM: nunca se inserta HTML
   proveniente del modelo. */
(() => {
  "use strict";

  const $ = (sel, raiz = document) => raiz.querySelector(sel);

  function el(tag, props = {}, ...hijos) {
    const nodo = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (v === false || v == null) continue;
      if (k === "class") nodo.className = v;
      else if (k === "dataset") Object.assign(nodo.dataset, v);
      else if (k.startsWith("on")) nodo.addEventListener(k.slice(2), v);
      else nodo.setAttribute(k, v === true ? "" : v);
    }
    for (const h of hijos.flat()) if (h != null && h !== false) nodo.append(h);
    return nodo;
  }

  const SVG_NS = "http://www.w3.org/2000/svg";
  function runa(nombre) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", "runa");
    svg.setAttribute("viewBox", "0 0 24 32");
    svg.setAttribute("aria-hidden", "true");
    const uso = document.createElementNS(SVG_NS, "use");
    uso.setAttribute("href", `#r-${nombre}`);
    svg.append(uso);
    return svg;
  }

  /* ---------- Formatos (es-AR) ---------- */
  const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  const nf = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 2 });
  const nf1 = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 1 });
  const nf0 = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });
  // Versión corta para los rótulos del gráfico: 51.108.000 -> "51,1 M"; 12.300 -> "12 mil"
  function compacto(v) {
    const a = Math.abs(v);
    if (a >= 1e6) return `${(a >= 1e8 ? nf0 : nf1).format(v / 1e6)} M`;
    if (a >= 1e4) return `${nf0.format(v / 1e3)} mil`;
    return nf.format(v);
  }
  const RE_FECHA = /^(\d{4})-(\d{2})(?:-(\d{2}))?(?:[T ][\d:.]+)?$/;
  const esFecha = (v) => typeof v === "string" && RE_FECHA.test(v);
  const esColumnaPlana = (nombre) => /^(a[nñ]o|anio|year|id)$|_id$/i.test(nombre);
  const esColumnaTiempo = (nombre) => /^(mes|dia|semana|trimestre|a[nñ]o|anio|periodo)/i.test(nombre);

  function fmtFecha(v, soloMes = false) {
    const m = RE_FECHA.exec(v);
    if (!m) return String(v);
    if (soloMes || !m[3]) return `${MESES[+m[2] - 1]} ${m[1].slice(2)}`;
    return `${m[3]}/${m[2]}/${m[1]}`;
  }
  function fmtCelda(v, columna) {
    if (v === null || v === undefined) return "—";
    if (typeof v === "number") return esColumnaPlana(columna) ? String(v) : nf.format(v);
    if (esFecha(v)) return fmtFecha(v);
    return String(v);
  }
  function fmtHora(texto) {
    const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(texto || "");
    return m ? `${m[3]}/${m[2]} ${m[4]}:${m[5]}` : "";
  }

  /* ---------- Markdown mínimo (seguro: arma nodos, no HTML) ---------- */
  function inline(texto) {
    const frag = document.createDocumentFragment();
    const re = /(`[^`]+`|\*\*[^*]+\*\*)/g;
    let ultimo = 0, m;
    while ((m = re.exec(texto))) {
      if (m.index > ultimo) frag.append(texto.slice(ultimo, m.index));
      const t = m[0];
      frag.append(t[0] === "`" ? el("code", {}, t.slice(1, -1)) : el("strong", {}, t.slice(2, -2)));
      ultimo = m.index + t.length;
    }
    if (ultimo < texto.length) frag.append(texto.slice(ultimo));
    return frag;
  }

  const celdas = (linea) => linea.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((s) => s.trim());
  const esNumerica = (s) => /^[-+]?[\d.,]+\s*%?$/.test(s);
  const esInicioBloque = (l, sig) =>
    /^```/.test(l) || /^\s*#{1,6}\s+/.test(l) || /^\s*([-*•]|\d+[.)])\s+/.test(l) ||
    (/^\s*\|.*\|\s*$/.test(l) && sig !== undefined && /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(sig));

  function markdown(texto) {
    const cont = el("div", { class: "prosa" });
    const lineas = String(texto).replace(/\r/g, "").split("\n");
    let i = 0;
    while (i < lineas.length) {
      const l = lineas[i];
      if (/^\s*$/.test(l)) { i++; continue; }

      if (/^```/.test(l)) {
        const buf = [];
        i++;
        while (i < lineas.length && !/^```/.test(lineas[i])) buf.push(lineas[i++]);
        i++;
        cont.append(el("pre", {}, el("code", {}, buf.join("\n"))));
        continue;
      }

      if (/^\s*\|.*\|\s*$/.test(l) && /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(lineas[i + 1] ?? "")) {
        const cab = celdas(l);
        i += 2;
        const cuerpo = [];
        while (i < lineas.length && /^\s*\|.*\|\s*$/.test(lineas[i])) cuerpo.push(celdas(lineas[i++]));
        const numCol = cab.map((_, c) => cuerpo.length > 0 && cuerpo.every((f) => esNumerica(f[c] ?? "")));
        cont.append(el("div", { class: "tabla-scroll" }, el("table", {},
          el("thead", {}, el("tr", {}, cab.map((t, c) => el("th", { class: numCol[c] && "num" }, inline(t))))),
          el("tbody", {}, cuerpo.map((f) => el("tr", {}, cab.map((_, c) =>
            el("td", { class: numCol[c] && "num" }, inline(f[c] ?? ""))))))
        )));
        continue;
      }

      const enc = /^\s*#{1,6}\s+(.*)$/.exec(l);
      if (enc) { cont.append(el("h4", {}, inline(enc[1]))); i++; continue; }

      const lista = /^\s*([-*•]|\d+[.)])\s+/;
      if (lista.test(l)) {
        const ordenada = /^\s*\d/.test(l);
        const items = [];
        while (i < lineas.length && lista.test(lineas[i])) items.push(lineas[i++].replace(lista, ""));
        cont.append(el(ordenada ? "ol" : "ul", {}, items.map((t) => el("li", {}, inline(t)))));
        continue;
      }

      const parrafo = [];
      while (i < lineas.length && !/^\s*$/.test(lineas[i]) && !(parrafo.length && esInicioBloque(lineas[i], lineas[i + 1]))) {
        parrafo.push(lineas[i++]);
      }
      const p = el("p");
      parrafo.forEach((t, k) => { if (k) p.append(el("br")); p.append(inline(t)); });
      cont.append(p);
    }
    return cont;
  }

  /* ---------- Tabla y gráficos a partir de los datos reales ---------- */
  function tablaDatos(columnas, filas) {
    const numCol = columnas.map((_, c) => filas.every((f) => f[c] === null || typeof f[c] === "number"));
    return el("div", { class: "tabla-scroll" }, el("table", {},
      el("thead", {}, el("tr", {}, columnas.map((c, i) => el("th", { class: numCol[i] && "num" }, c)))),
      el("tbody", {}, filas.map((f) => el("tr", {}, f.map((v, i) =>
        el("td", { class: numCol[i] && "num" }, fmtCelda(v, columnas[i]))))))
    ));
  }

  /* Devuelve cómo graficar el resultado, o null si no tiene forma de gráfico:
     una columna de etiquetas (la primera) y columnas numéricas a continuación. */
  function planGrafico(columnas, filas) {
    if (filas.length < 2 || columnas.length < 2) return null;
    const numerica = (i) => filas.every((f) => f[i] === null || typeof f[i] === "number");
    for (let i = 1; i < columnas.length; i++) if (!numerica(i)) return null;
    if (numerica(0) && !esColumnaTiempo(columnas[0])) return null;
    let iv = -1;
    for (let i = 1; i < columnas.length; i++) if (!esColumnaPlana(columnas[i])) { iv = i; break; }
    if (iv < 0) return null;
    const tiempo = filas.every((f) => esFecha(f[0])) || esColumnaTiempo(columnas[0]);
    return { iv, tipo: tiempo ? "columnas" : "barras" };
  }

  function etiquetas(columnas, filas) {
    const fechas = filas.every((f) => esFecha(f[0]));
    const todoDia1 = fechas && filas.every((f) => (RE_FECHA.exec(f[0])[3] ?? "01") === "01");
    const unAnio = fechas && new Set(filas.map((f) => f[0].slice(0, 4))).size === 1;
    return filas.map((f) => {
      const v = f[0];
      if (fechas && todoDia1 && unAnio) return MESES[+RE_FECHA.exec(v)[2] - 1];
      if (fechas) return todoDia1 ? fmtFecha(v, true) : fmtFecha(v);
      if (typeof v === "number" && /^mes/i.test(columnas[0]) && v >= 1 && v <= 12) return MESES[v - 1];
      return fmtCelda(v, columnas[0]);
    });
  }

  function graficoBarras(columnas, filas, iv) {
    const ets = etiquetas(columnas, filas);
    const vals = filas.map((f) => Math.max(0, f[iv] ?? 0));
    const max = Math.max(...vals, 1);
    const mayor = vals.indexOf(Math.max(...vals));
    const rejilla = el("div", { class: "barras", role: "img",
      "aria-label": `Gráfico de barras de ${columnas[iv]} por ${columnas[0]}` });
    filas.forEach((f, i) => {
      rejilla.append(
        el("span", { class: "et", title: ets[i] }, ets[i]),
        el("div", { class: "pista" }, el("div", { class: "relleno" + (i === mayor ? " primero" : ""),
          style: `width:${(vals[i] / max) * 100}%` })),
        el("span", { class: "val" }, nf.format(f[iv] ?? 0)));
    });
    return rejilla;
  }

  function graficoColumnas(columnas, filas, iv) {
    const ets = etiquetas(columnas, filas);
    const vals = filas.map((f) => Math.max(0, f[iv] ?? 0));
    const max = Math.max(...vals, 1);
    const mayor = vals.indexOf(Math.max(...vals));
    const conValor = filas.length <= 12;
    const cada = Math.ceil(filas.length / 12);
    const cont = el("div", { role: "img", "aria-label": `Gráfico de columnas de ${columnas[iv]} por ${columnas[0]}` });
    cont.append(
      el("div", { class: "columnas" }, filas.map((f, i) => el("div", { class: "col" + (i === mayor ? " mayor" : ""),
        title: `${ets[i]}: ${nf.format(f[iv] ?? 0)}` },
        conValor && el("span", { class: "valc" }, compacto(f[iv] ?? 0)),
        el("div", { class: "barra", style: `height:${(vals[i] / max) * 85}%` })))),
      el("div", { class: "etiquetas-col" }, ets.map((t, i) => el("span", {}, i % cada === 0 ? t : ""))));
    return cont;
  }

  function anioUnico(filas) {
    if (!filas.every((f) => esFecha(f[0]))) return "";
    const anios = new Set(filas.map((f) => f[0].slice(0, 4)));
    return anios.size === 1 ? ` (${[...anios][0]})` : "";
  }

  function bloqueDatos(res) {
    const { columnas, filas } = res;
    const plan = planGrafico(columnas, filas);
    const panel = el("div", { class: "datos-panel" });
    const nota = `${nf.format(filas.length)} ${filas.length === 1 ? "fila" : "filas"}`;
    const cabeza = el("div", { class: "datos-cabeza" },
      el("div", {}, el("span", { class: "datos-titulo" }, "Datos del resultado "), el("span", { class: "datos-nota" }, nota)));

    const mostrar = (cual) => {
      panel.replaceChildren(cual === "grafico" && plan
        ? (plan.tipo === "barras" ? graficoBarras(columnas, filas, plan.iv) : graficoColumnas(columnas, filas, plan.iv))
        : tablaDatos(columnas, filas));
      pestanas.forEach((b) => b.setAttribute("aria-selected", String(b.dataset.vista === cual)));
    };
    const pestanas = [];
    if (plan) {
      const lista = el("div", { class: "pestanas", role: "tablist", "aria-label": "Vista de los datos" });
      for (const [vista, texto] of [["grafico", "Gráfico"], ["tabla", "Tabla"]]) {
        const b = el("button", { class: "pestana", type: "button", role: "tab", dataset: { vista },
          onclick: () => mostrar(vista) }, texto);
        pestanas.push(b);
        lista.append(b);
      }
      cabeza.append(lista);
    }
    const contenedor = el("div", { class: "datos" }, cabeza, panel);
    mostrar(plan ? "grafico" : "tabla");
    if (plan) contenedor.append(el("p", { class: "datos-nota", style: "margin-top:.5rem" },
      `Se grafica ${columnas[plan.iv]} según ${columnas[0]}${anioUnico(filas)}.`));
    return contenedor;
  }

  /* ---------- Trazabilidad (SQL) ---------- */
  const ETIQUETA_ESTADO = { ok: "ok", vacio: "sin filas", rechazada: "rechazada", error: "con error", timeout: "demoró de más" };

  function bloqueConsulta(n, res) {
    const clase = res.estado === "ok" ? "estado-ok" : res.estado === "vacio" ? "estado-neutro" : "estado-mal";
    const copiar = el("button", { class: "copiar", type: "button", onclick: async () => {
      try { await navigator.clipboard.writeText(res.sql || ""); copiar.textContent = "Copiado"; }
      catch { copiar.textContent = "No se pudo copiar"; }
      setTimeout(() => { copiar.textContent = "Copiar SQL"; }, 1600);
    } }, "Copiar SQL");
    const filasTxt = res.estado === "ok" ? `, ${nf.format(res.filas.length)} ${res.filas.length === 1 ? "fila" : "filas"}` : "";
    return el("div", { class: "consulta" },
      el("div", { class: "consulta-cabeza" },
        el("span", {}, `Consulta ${n}: `, el("span", { class: clase }, ETIQUETA_ESTADO[res.estado] ?? res.estado), filasTxt),
        copiar),
      el("pre", {}, el("code", {}, res.sql || "(sin SQL)")),
      res.estado !== "ok" && res.mensaje && el("p", { class: "otros-pasos", style: "margin-top:.4rem" }, res.mensaje));
  }

  const TEXTO_OTROS = {
    inspeccionar_esquema: "Revisó la estructura de los datos.",
    listar_fuentes: "Revisó las fuentes disponibles.",
    consultar_historial: "Consultó el historial de consultas.",
  };

  /* ---------- Estado de la conversación ---------- */
  const hilo = $("#hilo");
  const form = $("#form");
  const campo = $("#pregunta");
  const botonEnviar = $("#btn-enviar");
  const riel = $("#riel");
  let ocupado = false;

  function nuevaSesion() {
    const id = (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2) + Date.now()).replace(/[^A-Za-z0-9_-]/g, "");
    return id.padEnd(16, "0").slice(0, 40);
  }
  let sesion = nuevaSesion();

  function autoAjustar() {
    campo.style.height = "auto";
    campo.style.height = Math.min(campo.scrollHeight + 2, 144) + "px";
  }

  const PASOS = {
    inspeccionar_esquema: ["ansuz", "Revisando la estructura de los datos", "Revisó la estructura de los datos"],
    listar_fuentes: ["ansuz", "Viendo qué fuentes hay", "Revisó las fuentes disponibles"],
    ejecutar_sql: ["kenaz", "Ejecutando la consulta sobre los datos", "Ejecutó una consulta"],
    consultar_historial: ["laguz", "Mirando el historial", "Consultó el historial"],
  };

  function crearPaso(rn, texto, estado = "activo") {
    const p = el("div", { class: "paso", dataset: { estado } }, runa(rn), el("span", {}, texto));
    return p;
  }

  async function preguntar(texto) {
    if (ocupado || !texto.trim()) return;
    ocupado = true;
    botonEnviar.disabled = true;
    $("#bienvenida")?.remove();

    const pasos = el("div", { class: "pasos", "aria-label": "Avance del asistente" });
    const salida = el("div");
    const turno = el("article", { class: "turno" },
      el("p", { class: "pregunta-usuario" }, runa("dagaz"), el("span", {}, texto)),
      pasos, salida);
    hilo.append(turno);
    turno.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });

    let transitorio = crearPaso("fehu", "Pensando la consulta");
    pasos.append(transitorio);
    const consultas = [];          // resultados de ejecutar_sql, en orden
    const otros = new Set();       // herramientas auxiliares usadas
    const activos = [];            // pasos en curso por herramienta
    let recibioFinal = false;

    const quitarTransitorio = () => { transitorio?.remove(); transitorio = null; };

    const manejar = (ev) => {
      if (ev.tipo === "paso") {
        quitarTransitorio();
        const [rn, vivo] = PASOS[ev.herramienta] ?? ["isa", `Usando ${ev.herramienta}`];
        const p = crearPaso(rn, vivo);
        activos.push({ herramienta: ev.herramienta, nodo: p, hecho: (PASOS[ev.herramienta] ?? [])[2] ?? vivo });
        pasos.append(p);
      } else if (ev.tipo === "resultado") {
        const i = activos.findIndex((a) => a.herramienta === ev.herramienta);
        const mal = ["rechazada", "error", "timeout"].includes(ev.respuesta?.estado);
        if (i >= 0) {
          const [a] = activos.splice(i, 1);
          a.nodo.dataset.estado = mal ? "fallo" : "hecho";
          a.nodo.lastChild.textContent = mal ? `${a.hecho} (${ETIQUETA_ESTADO[ev.respuesta.estado]})` : a.hecho;
        }
        if (ev.herramienta === "ejecutar_sql") consultas.push(ev.respuesta);
        else otros.add(ev.herramienta);
        quitarTransitorio();
        transitorio = crearPaso("dagaz", "Redactando la respuesta");
        pasos.append(transitorio);
      } else if (ev.tipo === "final") {
        recibioFinal = true;
        pasos.remove();
        dibujarRespuesta(salida, ev.texto, consultas, otros);
      } else if (ev.tipo === "error") {
        recibioFinal = true;
        pasos.remove();
        salida.append(el("div", { class: "respuesta es-error" },
          el("p", { class: "aviso-error" }, el("strong", { class: "tipo-estado" }, "No pude responder."), ev.mensaje)));
      }
    };

    try {
      const resp = await fetch("/api/chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mensaje: texto.trim(), sesion }),
      });
      if (!resp.ok || !resp.body) throw new Error(`El servidor respondió ${resp.status}.`);
      const lector = resp.body.getReader();
      const decodificador = new TextDecoder();
      let resto = "";
      for (;;) {
        const { value, done } = await lector.read();
        if (done) break;
        resto += decodificador.decode(value, { stream: true });
        const lineas = resto.split("\n");
        resto = lineas.pop();
        for (const l of lineas) if (l.trim()) manejar(JSON.parse(l));
      }
      if (resto.trim()) manejar(JSON.parse(resto));
      if (!recibioFinal) throw new Error("La respuesta se cortó antes de terminar.");
    } catch (e) {
      pasos.remove();
      salida.append(el("div", { class: "respuesta es-error" },
        el("p", { class: "aviso-error" }, el("strong", { class: "tipo-estado" }, "No pude responder."),
          `${e.message} Revisá que el servidor siga abierto en la terminal.`)));
    } finally {
      ocupado = false;
      botonEnviar.disabled = false;
      cargarMemoria();
      campo.focus({ preventScroll: true });
    }
  }

  function dibujarRespuesta(salida, texto, consultas, otros) {
    const caja = el("div", { class: "respuesta" });
    caja.append(texto ? markdown(texto) : el("p", { class: "prosa" }, "El asistente no devolvió texto."));

    const buenas = consultas.filter((c) => c.estado === "ok" && c.filas.length > 0);
    const unaCelda = (c) => c.filas.length === 1 && c.columnas.length === 1;
    // Se muestra el último resultado graficable; si no hay, el más largo (menos una sola celda)
    const graficable = [...buenas].reverse().find((c) => planGrafico(c.columnas, c.filas));
    const principal = graficable ?? [...buenas].filter((c) => !unaCelda(c)).sort((a, b) => b.filas.length - a.filas.length)[0];
    if (principal) caja.append(bloqueDatos(principal));

    if (consultas.length || otros.size) {
      const hayProblema = consultas.some((c) => c.estado !== "ok" && c.estado !== "vacio");
      const resumen = consultas.length
        ? `${consultas.length} ${consultas.length === 1 ? "consulta ejecutada" : "consultas ejecutadas"}`
        : "pasos del asistente";
      const traza = el("details", { class: "traza", open: hayProblema },
        el("summary", {}, "Cómo lo calculé ", el("small", {}, resumen)));
      if (otros.size) traza.append(el("p", { class: "otros-pasos" }, [...otros].map((o) => TEXTO_OTROS[o]).filter(Boolean).join(" ")));
      consultas.forEach((c, i) => traza.append(bloqueConsulta(i + 1, c)));
      caja.append(traza);
    }
    salida.append(caja);
  }

  /* ---------- Memoria (historial) y datos del encabezado ---------- */
  const ETIQUETA_MEMORIA = { ok: "Respondida", vacio: "Sin datos", rechazada: "Bloqueada", error: "Con error", timeout: "Demoró de más" };

  async function cargarMemoria() {
    const lista = $("#lista-memoria");
    try {
      const r = await fetch("/api/historial");
      const d = await r.json();
      const consultas = d.consultas ?? [];
      $("#memoria-ayuda").hidden = consultas.length > 0;
      lista.replaceChildren(...consultas.map((c) => el("li", {},
        el("button", { class: "item-memoria", type: "button", dataset: { estado: c.estado }, onclick: () => {
          campo.value = c.pregunta; autoAjustar(); campo.focus(); cerrarRiel();
        } },
          el("span", { class: "item-texto" }, c.pregunta),
          el("span", { class: "item-meta" }, `${fmtHora(c.fecha_hora)}  ${ETIQUETA_MEMORIA[c.estado] ?? c.estado}`)))));
    } catch { /* la memoria es opcional: si falla, el chat sigue funcionando */ }
  }

  async function cargarFicha() {
    const ficha = $("#ficha");
    try {
      const d = await (await fetch("/api/estado")).json();
      if (d.estado !== "ok") throw new Error(d.mensaje);
      const t = d.tablas[0];
      const fecha = Object.values(d.rango_fechas)[0];
      const filas = [["Tabla", t.nombre], ["Filas", nf.format(t.filas)]];
      if (fecha) filas.push(["Desde", fmtFecha(fecha.desde)], ["Hasta", fmtFecha(fecha.hasta)]);
      if (d.modelo) filas.push(["Modelo", String(d.modelo).replace(/^ollama_chat\//, "")]);
      ficha.replaceChildren(...filas.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)]));
    } catch (e) {
      ficha.replaceChildren(el("dt", {}, "Estado"), el("dd", { class: "estado-mal" }, "No se pudieron cargar los datos"));
    }
  }

  /* ---------- Eventos ---------- */
  function cerrarRiel() {
    riel.classList.remove("abierto");
    $("#btn-riel").setAttribute("aria-expanded", "false");
  }
  $("#btn-riel").addEventListener("click", () => {
    const abierto = riel.classList.toggle("abierto");
    $("#btn-riel").setAttribute("aria-expanded", String(abierto));
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") cerrarRiel(); });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const texto = campo.value;
    if (!texto.trim() || ocupado) return;
    campo.value = "";
    autoAjustar();
    preguntar(texto);
  });
  campo.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
  });
  campo.addEventListener("input", autoAjustar);

  document.addEventListener("click", (e) => {
    const s = e.target.closest(".sugerencia");
    if (s) { campo.value = s.textContent; autoAjustar(); form.requestSubmit(); }
  });

  const bienvenidaOriginal = $("#bienvenida").cloneNode(true);
  $("#btn-nueva").addEventListener("click", () => {
    if (ocupado) return;
    sesion = nuevaSesion();
    hilo.replaceChildren(bienvenidaOriginal.cloneNode(true));
    campo.focus();
    cerrarRiel();
  });

  cargarFicha();
  cargarMemoria();
})();
