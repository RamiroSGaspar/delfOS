(function () {
  "use strict";
  const D = JSON.parse(document.getElementById("datos").textContent);
  const NOTAS = JSON.parse(document.getElementById("textos").textContent);
  const T = D.totales, TR = D.tramos, INF = D.informe, G = D.genuinas, SVG = "http://www.w3.org/2000/svg";
  // Abierto desde la aplicación, el tablero suma el explorador de comentarios, que necesita al servidor.
  const Q = new URLSearchParams(location.search), APP = Q.get("app") === "1", raiz = document.documentElement;
  const UMBRAL = 1.5, MINIMO = 30;  // una narrativa «se concentra» en una fuente si pesa ahí 1,5 veces lo que la fuente pesa en el total
  const porEtiqueta = {};
  D.narrativas.forEach((n) => { porEtiqueta[n.etiqueta] = n; });
  const porVolumen = D.narrativas.slice().sort((a, b) => b.comentarios - a.comentarios || a.etiqueta.localeCompare(b.etiqueta));
  const porOrigen = D.narrativas.filter((n) => n.comentarios).sort((a, b) =>
    (a.origen_s == null ? Infinity : a.origen_s) - (b.origen_s == null ? Infinity : b.origen_s) || (a.primero_s || 0) - (b.primero_s || 0));
  const diaInicial = D.periodo.desde_s == null ? null : Math.floor(D.periodo.desde_s / 86400);
  const fuentesConDatos = D.fuentes.filter((f) => f.comentarios);

  // --- Elementos, números y fechas -----------------------------------------------------------------------
  function el(tag, attrs) {
    const e = document.createElement(tag);
    Object.keys(attrs || {}).forEach((k) => {
      if (k === "texto") e.textContent = attrs[k];
      else if (k === "clase") e.className = attrs[k];
      else e.setAttribute(k, attrs[k]);
    });
    for (let i = 2; i < arguments.length; i++) if (arguments[i] != null) e.append(arguments[i]);
    return e;
  }
  function svg(tag, attrs) {
    const e = document.createElementNS(SVG, tag);
    Object.keys(attrs || {}).forEach((k) => e.setAttribute(k, attrs[k]));
    return e;
  }
  const id = (x) => document.getElementById(x);
  const num = (n) => Number(n).toLocaleString("es-AR");
  const dec = (n, d) => Number(n).toLocaleString("es-AR", { minimumFractionDigits: d, maximumFractionDigits: d });
  function pct(parte, total) {
    if (!total) return "sin datos";
    const v = 100 * parte / total;
    return dec(v, v > 0 && v < 1 ? 2 : 1) + " %";
  }
  // Un porcentaje chico se entiende mejor como «1 de cada N».
  const unoDeCada = (parte, total) => parte > 0 && parte / total < 0.01 ? "1 de cada " + num(Math.round(total / parte)) : "";
  function pctFino(parte, total) {
    const u = unoDeCada(parte, total);
    return pct(parte, total) + (u ? ", " + u : "");
  }
  const dos = (n) => String(n).padStart(2, "0");
  // Las fechas llegan como segundos en la hora local del set: se leen con los métodos UTC para no moverlas.
  function fecha(s, conHora) {
    const d = new Date(s * 1000), f = dos(d.getUTCDate()) + "/" + dos(d.getUTCMonth() + 1);
    return conHora === false ? f : f + " " + dos(d.getUTCHours()) + ":" + dos(d.getUTCMinutes());
  }
  const hora = (s) => fecha(s).slice(6);
  const fechaLarga = (s) => fecha(s, false) + "/" + new Date(s * 1000).getUTCFullYear();
  const plural = (n, uno, muchos) => num(n) + " " + (n === 1 ? uno : muchos);
  function tramoTexto() {
    const s = TR.segundos;
    if (!s) return "tiempo";
    if (s % 86400 === 0) return s === 86400 ? "1 día" : s / 86400 + " días";
    return s === 3600 ? "1 hora" : s / 3600 + " horas";
  }
  const dias = (n) => n == null ? "sin datos" : plural(Math.round(n), "día", "días");
  function boton(texto, clase, alTocar, etiqueta) {
    const b = el("button", { type: "button", clase: clase || "", texto: texto });
    if (etiqueta) { b.setAttribute("aria-label", etiqueta); b.title = etiqueta; }
    b.addEventListener("click", alTocar);
    return b;
  }
  const enlace = (texto, alTocar) => boton(texto, "tt-enlace d-enlace", alTocar);
  const lista = (cosas) => cosas.length < 2 ? cosas.join("") : cosas.slice(0, -1).join(", ") + " y " + cosas[cosas.length - 1];
  // Un título que no redactó la IA es la frase más repetida, tal como la deja la limpieza del texto: va entre comillas.
  const titulo = (n) => n.titulo_de_ia === false ? "«" + n.titulo + "»" : n.titulo;
  const etiquetaTitulo = (n) => n.titulo_de_ia === false ? el("span", { clase: "d-etiqueta", texto: "frase más repetida" }) : null;

  // --- El tema: Papel u Oscuro ---------------------------------------------------------------------------
  const LLAVE = "delfos-tema";
  function temaGuardado() {
    try { return localStorage.getItem(LLAVE) === "oscuro" ? "oscuro" : "papel"; } catch (e) { return "papel"; }
  }
  function ponerTema(t) {
    raiz.setAttribute("data-theme", t);
    id("tema").setAttribute("aria-checked", String(t === "oscuro"));
    id("tema").textContent = (t === "oscuro" ? "[x]" : "[ ]") + " Oscuro";
  }
  id("tema").addEventListener("click", () => {
    const t = raiz.getAttribute("data-theme") === "oscuro" ? "papel" : "oscuro";
    ponerTema(t);
    try { localStorage.setItem(LLAVE, t); } catch (e) { /* sin permiso para guardar: vale hasta cerrar */ }
  });
  window.addEventListener("storage", (ev) => { if (ev.key === LLAVE) ponerTema(temaGuardado()); });  // la aplicación cambió el tema

  // --- Las notas: qué muestra cada elemento y cómo se obtiene -------------------------------------------
  const GLOBALES = {
    comentarios: num(T.comentarios), narrativas: num(T.narrativas), con_narrativa: num(T.con_narrativa),
    pct_con_narrativa: pct(T.con_narrativa, T.comentarios), ruido: num(T.ruido), pct_ruido: pct(T.ruido, T.comentarios),
    cuentas: num(T.cuentas), cuentas_coordinadas: num(T.cuentas_coordinadas),
    pct_coordinadas: pctFino(T.cuentas_coordinadas, T.cuentas), operaciones: plural(T.operaciones, "operación", "operaciones"),
    publicaciones: plural(T.publicaciones, "publicación", "publicaciones"), fuentes: plural(T.fuentes, "fuente", "fuentes"),
    tramo: tramoTexto(), zona: D.periodo.zona, por_celda: num(D.pajar.por_celda), umbral: dec(UMBRAL, 1), minimo: num(MINIMO),
    desde: D.periodo.desde_s == null ? "una fecha que no se pudo leer" : fechaLarga(D.periodo.desde_s),
    hasta: D.periodo.hasta_s == null ? "una fecha que no se pudo leer" : fechaLarga(D.periodo.hasta_s)
  };
  const valoresDe = new WeakMap();
  // Deja un elemento listo para explicarse: al tocarlo, su nota aparece en la ventana de notas.
  function nota(e, clave, valores) {
    e.dataset.nota = clave;
    if (!e.matches("button, summary")) e.tabIndex = 0;
    valoresDe.set(e, valores || {});
    return e;
  }
  const ex = (texto, clave, valores) => nota(el("span", { texto: texto }), clave, valores);
  const llenar = (texto, valores) =>
    texto.replace(/\{(\w+)\}/g, (m, k) => valores[k] != null ? valores[k] : GLOBALES[k] != null ? GLOBALES[k] : "").replace(/\s+/g, " ").trim();
  const angosto = () => window.matchMedia("(max-width: 1000px)").matches;
  function verNotas(si) {
    document.body.classList.toggle("sin-nota", !si);
    id("ver-notas").setAttribute("aria-checked", String(si));
    id("ver-notas").textContent = (si ? "[x]" : "[ ]") + " Notas";
  }
  function mostrarNota(e) {
    document.querySelectorAll("[data-nota].elegido").forEach((x) => x.classList.remove("elegido"));
    const n = (e && NOTAS[e.dataset.nota]) || NOTAS.inicio, v = (e && valoresDe.get(e)) || {};
    if (e) e.classList.add("elegido");
    if (e && angosto()) verNotas(true);
    id("nota").replaceChildren(
      el("header", { clase: "tt-ventana__barra" }, el("h2", { clase: "tt-ventana__titulo", texto: "Notas" }),
        el("span", { clase: "tt-ventana__controles" }, boton("[×]", "", () => verNotas(false), "Cerrar las notas"))),
      el("div", { clase: "tt-ventana__cuerpo" }, el("h3", { clase: "tt-titulo", texto: n.titulo }),
        el("section", { clase: "d-nota__bloque" }, el("h4", { texto: "Qué muestra" }), el("p", { texto: llenar(n.que, v) })),
        el("section", { clase: "d-nota__bloque d-nota__como" }, el("h4", { texto: "Cómo se obtiene" }), el("p", { texto: llenar(n.como, v) }))));
  }
  id("ver-notas").addEventListener("click", () => verNotas(document.body.classList.contains("sin-nota")));

  function valoresNarrativa(n) {
    return {
      titulo: n.titulo, etiqueta: n.etiqueta, comentarios: num(n.comentarios), pct: pct(n.comentarios, T.con_narrativa),
      apoya: num(n.apoya), pct_apoya: pct(n.apoya, n.comentarios), rechaza: num(n.rechaza),
      pct_rechaza: pct(n.rechaza, n.comentarios), cuentas: num(n.cuentas), coordinados: num(n.coordinados),
      origen: n.origen_s == null ? "sin una fecha que se pueda leer" : "el " + fechaLarga(n.origen_s) + " a las " + hora(n.origen_s),
      decide: n.lado_lo_decide === "tope" ? "En esta narrativa, el lado que apoya lo decidió la cantidad de comentarios que no responden a nadie."
        : n.lado_lo_decide === "modelo" ? "En esta narrativa, el lado que apoya lo decidió la IA." : "",
      de_ia: n.titulo_de_ia === true ? "En esta narrativa, el título lo redactó la IA."
        : n.titulo_de_ia === false ? "En esta narrativa, el título es la frase más repetida: por eso va entre comillas, en minúsculas y sin tildes." : ""
    };
  }

  // --- La selección: la narrativa elegida se resalta en todas las ventanas a la vez ----------------------
  let elegida = null;
  function marcarSeleccion() {
    document.querySelectorAll("[data-id]").forEach((e) => e.classList.toggle("is-sel", e.dataset.id === elegida));
  }
  function elegir(etiqueta, fija) {
    elegida = elegida === etiqueta && !fija ? null : (porEtiqueta[etiqueta] ? etiqueta : null);
    marcarSeleccion();
    pintarSeleccion();
    pintarFicha();
    pintarEstado();
    if (APP && window.parent !== window) window.parent.postMessage({ delfos: "seleccion", id: elegida }, location.origin);
  }
  function pintarSeleccion() {
    const n = porEtiqueta[elegida];
    document.querySelectorAll(".d-seleccion").forEach((caja) => {
      if (!n) return caja.replaceChildren(el("p", { clase: "d-vacio", texto: "Elegí una narrativa: se resalta en las tres ventanas." }));
      caja.replaceChildren(
        el("p", null, el("span", { clase: "tt-resaltado", texto: n.etiqueta }),
          (n.origen_s == null ? "  sin fecha de origen" : "  nace " + fecha(n.origen_s)) + "   apoya " + num(n.apoya) + " (" + pct(n.apoya, n.comentarios) +
          ")   rechaza " + num(n.rechaza) + " (" + pct(n.rechaza, n.comentarios) + ")"),
        el("p", { clase: "tt-titulo", texto: titulo(n) }),
        enlace("Ver su ficha completa", () => { abrir("circula"); id("ficha").scrollIntoView({ block: "start" }); }));
    });
  }

  // --- Piezas: ventanas, preguntas y respuestas -----------------------------------------------------------
  // Una ventana del sistema: hoja con marco y el título montado sobre el marco. Los hijos van después de las opciones.
  function ventana(nombre, o) {
    o = o || {};
    const controles = el("span", { clase: "tt-ventana__controles" });
    if (o.num != null) controles.append(el("span", { clase: "tt-ventana__num", texto: String(o.num) }));
    if (o.ver) controles.append(boton("[□]", "", () => abrir(o.ver), "Ver completo"));
    const cuerpo = el("div", { clase: "tt-ventana__cuerpo" });
    for (let i = 2; i < arguments.length; i++) if (arguments[i] != null) cuerpo.append(arguments[i]);
    const v = el("section", { clase: "tt-ventana" + (o.foco ? " is-foco" : "") + (o.continuo ? " is-continuo" : "") + (o.clase ? " " + o.clase : ""),
      "aria-label": nombre, "data-ventana": "" },
      el("header", { clase: "tt-ventana__barra" }, el("h2", { clase: "tt-ventana__titulo", texto: nombre }), controles), cuerpo);
    if (o.id) v.id = o.id;
    if (o.fuente) v.append(el("p", { clase: "tt-ventana__fuente", texto: "Fuente: " + o.fuente }));
    return v;
  }
  function enfocar(v) {
    const s = v.closest("#vista > section");
    if (s) s.querySelectorAll("[data-ventana]").forEach((w) => w.classList.toggle("is-foco", w === v));
  }
  const pregunta = (texto) => el("h3", { clase: "tt-pregunta", texto: texto });
  function respuesta() {
    const p = el("p", { clase: "tt-lectura d-respuesta" });
    for (let i = 0; i < arguments.length; i++) if (arguments[i] != null) p.append(arguments[i]);
    return p;
  }
  const mono = (texto) => el("span", { clase: "d-mono", texto: texto });  // un id dentro de una oración va en la voz de la máquina
  const rotulo = (texto) => el("h4", { clase: "d-rotulo", texto: texto });
  const ayuda = (texto) => el("p", { clase: "d-ayuda", texto: texto });
  // El set se nombra con su nombre (si lo tiene) y su huella: la misma en cualquier computadora, para saber de qué datos sale cada cifra.
  const huella = D.set.indexOf(" ") >= 0 ? D.set.slice(D.set.lastIndexOf(" ") + 1) : D.set;
  const delSet = D.nombre ? "set «" + D.nombre + "» (" + huella + ")" : "set " + D.set;

  // --- Las oraciones que responden: calculadas, nunca escritas a mano ------------------------------------
  function respuestaCircula() {
    if (!porVolumen.length) return respuesta("El análisis no detectó narrativas: los " + num(T.comentarios) + " comentarios quedaron sin narrativa.");
    const m = porVolumen[0];
    return respuesta(ex(plural(T.narrativas, "narrativa", "narrativas"), "cifra_narrativas"), T.narrativas === 1 ? " reúne " : " reúnen ",
      ex(num(T.con_narrativa) + " de los " + num(T.comentarios) + " comentarios", "cifra_comentarios"), " (" + pct(T.con_narrativa, T.comentarios) + "). ",
      T.narrativas > 1 ? "La más comentada es «" + m.titulo + "» (" : "Es «" + m.titulo + "» (", mono(m.etiqueta), "), con " + num(m.comentarios) + ". ",
      ex("El ruido suma " + num(T.ruido), "cifra_ruido"), " (" + pct(T.ruido, T.comentarios) + ").");
  }
  function respuestaCuando() {
    const con = porOrigen.filter((n) => n.origen_s != null);
    if (!TR.cantidad || !con.length) return respuesta("El set no tiene fechas que se puedan leer: no se puede decir desde cuándo circula cada narrativa.");
    const primeras = con.filter((n) => Math.floor(n.origen_s / 86400) === diaInicial), tarde = con.filter((n) => Math.floor(n.origen_s / 86400) !== diaInicial);
    const p = respuesta(), dia = fecha(D.periodo.desde_s, false);
    if (primeras.length === 1) p.append("Una narrativa nace el primer día del set (" + dia + "), a las " + hora(primeras[0].origen_s) + ". ");
    else if (primeras.length) {
      p.append((tarde.length ? num(primeras.length) + " narrativas nacen" : "Las " + num(primeras.length) + " narrativas nacen") + " el primer día del set (" + dia +
        "), entre las " + hora(primeras[0].origen_s) + " y las " + hora(primeras[primeras.length - 1].origen_s) + ". ");
    } else p.append("Ninguna narrativa nace el primer día del set (" + dia + "). ");
    if (tarde.length) {
      const muestra = tarde.slice(0, tarde.length > 4 ? 3 : 4);
      p.append(primeras.length ? (tarde.length === 1 ? "Una nace después: " : num(tarde.length) + " nacen después: ") : (tarde.length === 1 ? "Nace " : "Nacen "));
      muestra.forEach((n, i) => {
        p.append(i === 0 ? "" : i === muestra.length - 1 && muestra.length === tarde.length ? " y " : ", ", mono(n.etiqueta), " el " + fecha(n.origen_s, false) + " a las " + hora(n.origen_s));
      });
      p.append(muestra.length < tarde.length ? " y " + num(tarde.length - muestra.length) + " más." : ".");
    }
    return nota(p, "origen_todas");
  }
  function respuestaEmpuja() {
    if (!D.operaciones.length) return respuesta("Ninguna de las " + num(T.cuentas) + " cuentas del set muestra señales de coordinación.");
    const op = D.operaciones.slice().sort((a, b) => b.comentarios - a.comentarios)[0], principal = op.narrativas[0], p = respuesta();
    p.append(ex(num(T.cuentas_coordinadas) + " de las " + num(T.cuentas) + " cuentas", "cifra_coordinadas"), " (" + pctFino(T.cuentas_coordinadas, T.cuentas) + ") " +
      (T.cuentas_coordinadas === 1 ? "muestra" : "muestran") + " señales de coordinación, " +
      (T.operaciones === 1 ? "todas en una misma operación. " : "en " + num(T.operaciones) + " operaciones. "),
      "Escribieron " + num(T.comentarios_coordinados) + " de los " + num(T.comentarios) + " comentarios (" + pctFino(T.comentarios_coordinados, T.comentarios) + ").");
    if (principal) {
      const n = porEtiqueta[principal.etiqueta] || { titulo: principal.etiqueta };
      p.append(" " + (T.operaciones === 1 ? "" : "En la operación más activa, ") + num(principal.comentarios) + " de " + (T.operaciones === 1 ? "ellos" : "sus comentarios") +
        " van a «" + n.titulo + "» (", mono(principal.etiqueta), "), y " + num(principal.apoya) + " la apoyan.");
    }
    return p;
  }

  // --- Narrativas: una fila por narrativa, con su barra partida por postura ------------------------------
  function barraPostura(n, max) {
    const b = el("span", { clase: "d-barra2", "aria-hidden": "true" });
    [["d-apoya", n.apoya], ["d-rechaza", n.rechaza], ["d-sinpostura", n.sin_postura || 0]].forEach((x) => {
      if (x[1]) b.append(el("i", { clase: x[0], style: "width:" + (max ? 100 * x[1] / max : 0) + "%" }));
    });
    return b;
  }
  const reparto = (n) => "apoya " + pct(n.apoya, n.comentarios) + " · rechaza " + pct(n.rechaza, n.comentarios);
  // filas: narrativas, o las cuentas de una operación en una narrativa ({etiqueta, comentarios, apoya, rechaza}).
  function listaPostura(filas, o) {
    o = o || {};
    const max = filas.reduce((m, x) => Math.max(m, x.comentarios), 0), ul = el("ul", { clase: "d-postura" + (o.completa ? " is-completa" : "") });
    if (o.ancho) ul.style.setProperty("--reparto", o.ancho);
    filas.forEach((x) => {
      const n = porEtiqueta[x.etiqueta] || x;
      const fila = el("button", { type: "button", clase: "tt-fila d-postura__fila", "data-elige": x.etiqueta,
        "aria-label": x.etiqueta + ": " + num(x.comentarios) + " comentarios, apoya " + num(x.apoya) + ", rechaza " + num(x.rechaza) },
        el("span", { clase: "d-id", texto: x.etiqueta }), el("span", { clase: "tt-postura__titulo", title: n.titulo, texto: titulo(n) }),
        barraPostura(x, max), el("span", { clase: "tt-postura__cifra", texto: num(x.comentarios) }),
        o.completa ? el("span", { clase: "d-reparto", texto: o.reparto ? o.reparto(x, n) : reparto(x) }) : null);
      ul.append(el("li", { "data-id": x.etiqueta }, nota(fila, o.nota || "narrativa", valoresNarrativa(n))));
    });
    return ul;
  }
  function leyendaPostura(max, queEs) {
    return el("p", { clase: "d-leyenda" }, el("span", null, el("i", { clase: "d-muestra d-apoya" }), "apoya"),
      el("span", null, el("i", { clase: "d-muestra d-rechaza" }), "rechaza"),
      el("span", { texto: "escala común desde cero: la barra más larga son " + num(max) + " " + (queEs || "comentarios") }));
  }

  // --- El tiempo ------------------------------------------------------------------------------------------
  let diasDelEje = null;
  function diasEje() {
    if (diasDelEje) return diasDelEje;
    diasDelEje = [];
    if (!TR.cantidad) return diasDelEje;
    const fin = TR.inicio_s + TR.cantidad * TR.segundos;
    for (let e = Math.ceil(TR.inicio_s / 86400) * 86400; e < fin; e += 86400) diasDelEje.push({ x: (e - TR.inicio_s) / TR.segundos, s: e });
    return diasDelEje;
  }
  function eje() {
    const d = diasEje(), cada = Math.max(1, Math.ceil(d.length / 12)), e = el("span", { clase: "d-eje", "aria-hidden": "true" });
    d.forEach((x, i) => {
      if (i % cada === 0) e.append(el("span", { style: "left:" + (100 * x.x / TR.cantidad) + "%", texto: fecha(x.s, false) }));
    });
    return e;
  }
  // capas: [{valores, clase, nombre}], apiladas de abajo hacia arriba. Cada barra es un tramo; la altura, sus comentarios.
  function grafico(capas, o) {
    o = o || {};
    const n = TR.cantidad, alto = 40;
    const total = Array.from({ length: n }, (_, i) => capas.reduce((s, c) => s + (c.valores[i] || 0), 0));
    const pico = total.reduce((a, b) => Math.max(a, b), 0), max = Math.max(1, pico), s = svg("svg", { viewBox: "0 0 " + Math.max(1, n) + " " + alto,
      preserveAspectRatio: "none", class: "d-graf" + (o.alto ? " is-alto" : ""), role: "img", "aria-label": o.descripcion || "Comentarios por tramo de " + tramoTexto() });
    diasEje().forEach((d) => s.append(svg("line", { x1: d.x, x2: d.x, y1: 0, y2: alto, class: "dia" })));
    for (let i = 0; i < n; i++) {
      if (!total[i]) continue;
      let y = alto;
      capas.forEach((c) => {
        const v = c.valores[i] || 0;
        if (!v) return;
        const h = v / max * (alto - 7);
        y -= h;
        s.append(svg("rect", { x: i + 0.1, y: y, width: 0.8, height: h, class: c.clase }));
      });
      const zona = svg("rect", { x: i, y: 0, width: 1, height: alto, class: "zona" }), t = svg("title"), desde = TR.inicio_s + i * TR.segundos;
      t.textContent = fecha(desde) + " a " + fecha(desde + TR.segundos) + " · " + capas.filter((c) => c.valores[i]).map((c) => c.nombre + ": " + num(c.valores[i])).join(" · ");
      zona.append(t);
      s.append(zona);
    }
    if (o.origen != null) {
      const x = (o.origen - TR.inicio_s) / TR.segundos;
      if (x >= 0 && x <= n) {
        s.append(svg("line", { x1: x, x2: x, y1: 5, y2: alto, class: "origen" }),
          svg("polygon", { points: (x - 0.55) + ",0 " + (x + 0.55) + ",0 " + x + ",6", class: "origen-marca" }));
      }
    }
    return { svg: s, pico: pico, cuando: pico ? TR.inicio_s + total.indexOf(pico) * TR.segundos : null };
  }
  const totalPorTramo = (n) => n.serie.apoya.map((v, i) => v + n.serie.rechaza[i] + n.serie.sin_postura[i]);
  const capasPostura = (n) => [{ valores: n.serie.apoya, clase: "b", nombre: "apoya" }, { valores: n.serie.rechaza, clase: "b2", nombre: "rechaza" },
    { valores: n.serie.sin_postura, clase: "b3", nombre: "sin postura" }];
  const cuantoPico = (g) => plural(g.pico, "comentario", "comentarios");
  const tarde = (n) => n.origen_s != null && Math.floor(n.origen_s / 86400) !== diaInicial;
  function figuraTiempo(alta) {
    const ul = el("ul", { clase: "d-tiempo" + (alta ? " is-alta" : "") });
    ul.append(el("li", { clase: "d-tiempo__eje" }, el("div", { clase: "d-tiempo__fila" }, el("span"), el("span", { clase: "tt-postura__titulo" }), eje(),
      el("span"), el("span", { clase: "d-nace" }))));
    porOrigen.forEach((n) => {
      const g = grafico([{ valores: totalPorTramo(n), clase: "b", nombre: "comentarios" }], { origen: n.origen_s });
      const fila = el("button", { type: "button", clase: "tt-fila d-tiempo__fila", "data-elige": n.etiqueta },
        el("span", { clase: "d-id", texto: n.etiqueta }), el("span", { clase: "tt-postura__titulo", title: n.titulo, texto: titulo(n) }), g.svg,
        el("span", { clase: "tt-postura__cifra", texto: num(n.comentarios) }),
        el("span", { clase: "d-nace" + (tarde(n) ? " is-tarde" : ""), texto: n.origen_s == null ? "sin fecha" : "nace " + fecha(n.origen_s) }));
      ul.append(el("li", { "data-id": n.etiqueta }, nota(fila, "crecimiento", Object.assign(valoresNarrativa(n), { pico: cuantoPico(g) }))));
    });
    const todos = grafico([{ valores: D.serie_total.con_narrativa, clase: "b", nombre: "con narrativa" }, { valores: D.serie_total.ruido, clase: "b2", nombre: "ruido" }]);
    ul.append(el("li", { clase: "d-todos" }, nota(el("div", { clase: "d-tiempo__fila d-fija" }, el("span", { texto: "todo" }),
      el("span", { clase: "tt-postura__titulo", texto: "Todos los comentarios: con narrativa y ruido" }), todos.svg,
      el("span", { clase: "tt-postura__cifra", texto: num(T.comentarios) }), el("span", { clase: "d-nace" })), "tiempo_total", { pico: cuantoPico(todos) })));
    return ul;
  }
  const leyendaTiempo = () => el("p", { clase: "d-leyenda" }, el("span", { texto: "Cada barra son " + tramoTexto() + "; su altura, los comentarios de ese tramo." }),
    el("span", { texto: "▼ origen estimado de la narrativa." }),
    el("span", { texto: "Escala propia por fila: muestra la forma, no el tamaño. El total va a la derecha." }));

  // --- Coordinación: la operación contra las demás cuentas, y el pajar -----------------------------------
  const SENALES = { T: "Texto propio", S: "Sincronía por narrativa", R: "Respuestas en grupo", P: "Sincronía por publicación" };
  const sello = (op) => el("span", { clase: "tt-sello", texto: "◆ " + op.etiqueta + " · " + plural(op.cuentas, "cuenta", "cuentas") });
  function valoresOperacion(op) {
    return { etiqueta: op.etiqueta, cuentas: plural(op.cuentas, "cuenta", "cuentas"), comentarios: plural(op.comentarios, "comentario", "comentarios"),
      por_cuenta: dec(op.por_cuenta, 1), por_cuenta_demas: G.por_cuenta == null ? "sin datos" : dec(G.por_cuenta, 1),
      dias: dias(op.antiguedad_mediana_dias), dias_demas: dias(G.antiguedad_mediana_dias) };
  }
  function pares(op, enLaMesa) {
    const caja = el("div", { clase: "d-pares" }), v = valoresOperacion(op), parte = (x) => dec(100 * x, 1) + " %";
    function par(clave, que, deLaOp, deLasDemas, formato, valores) {
      if (deLaOp == null || deLasDemas == null) return;
      const max = Math.max(deLaOp, deLasDemas) || 1;
      const fila = (clase, quien, valor) => el("div", { clase: "d-par__fila " + clase }, el("span", { texto: quien }),
        el("span", { clase: "d-par__barra", "aria-hidden": "true" }, el("i", { style: "width:" + 100 * valor / max + "%" })),
        el("span", { clase: "d-par__valor", texto: formato(valor) }));
      caja.append(nota(el("div", { clase: "d-par" }, el("div", { clase: "d-par__que", texto: que }),
        fila("tt-coord", "◆ operación", deLaOp), fila("", "· las demás", deLasDemas)), clave, Object.assign({}, v, valores)));
    }
    par("par_antiguedad", "Antigüedad de las cuentas al empezar el set (mediana)", op.antiguedad_mediana_dias, G.antiguedad_mediana_dias, dias);
    if (!enLaMesa) par("par_por_cuenta", "Comentarios por cuenta", op.por_cuenta, G.por_cuenta, (x) => dec(x, 1));
    const principal = op.narrativas[0], n = principal && porEtiqueta[principal.etiqueta];
    if (n && op.comentarios && G.comentarios) {
      const apoyoCoordinado = D.operaciones.reduce((s, o) => s + ((o.narrativas.find((x) => x.etiqueta === n.etiqueta) || {}).apoya || 0), 0);
      const resto = n.comentarios - n.coordinados, valores = { narrativa: n.etiqueta, titulo: n.titulo };
      par("par_concentracion", "Parte de sus comentarios que va a " + n.etiqueta + ", su narrativa principal", principal.comentarios / op.comentarios, resto / G.comentarios, parte,
        Object.assign({ de_la_op: parte(principal.comentarios / op.comentarios), de_las_demas: parte(resto / G.comentarios) }, valores));
      if (principal.comentarios && resto) {
        par("par_apoyo", "De esos comentarios, cuántos apoyan a " + n.etiqueta, principal.apoya / principal.comentarios, (n.apoya - apoyoCoordinado) / resto, parte,
          Object.assign({ de_la_op: parte(principal.apoya / principal.comentarios), de_las_demas: parte((n.apoya - apoyoCoordinado) / resto) }, valores));
      }
    }
    return caja.children.length ? caja : null;
  }
  function pajar() {
    const P = D.pajar, celdas = new Array(P.celdas).fill(false);
    Object.keys(P.marcadas).forEach((g) => P.marcadas[g].forEach((i) => { celdas[i] = true; }));
    const conMarca = celdas.filter(Boolean).length, p = el("p", { clase: "tt-pajar d-pajar", role: "img",
      "aria-label": num(T.cuentas) + " cuentas en " + num(P.celdas) + " celdas de " + num(P.por_celda) + "; " + num(conMarca) + " celdas con cuentas con señales de coordinación" });
    let tramo = "";  // los puntos seguidos van en un solo texto: la página no arma mil elementos
    celdas.forEach((si) => {
      if (!si) { tramo += "·"; return; }
      p.append(tramo, el("b", { texto: "◆" }));
      tramo = "";
    });
    p.append(tramo);
    return nota(el("div", null, p, el("p", { clase: "d-leyenda" }, el("span", { texto: "· " + num(P.por_celda) + " cuentas" }),
      el("span", { clase: "tt-coord", texto: "◆ al menos una con señales de coordinación" }),
      el("span", { texto: "En orden de id: la posición no significa nada; muestra cuántas son." }))), "pajar", { celdas: num(P.celdas), con_marca: num(conMarca) });
  }
  const descargo = () => el("p", { clase: "tt-aviso", texto: "Señal de coordinación es conducta observada en este set: textos repetidos y comentarios " +
    "sincronizados. No identifica bots ni autoría y no prueba intención." });

  // --- Tablas, fichas y avisos ---------------------------------------------------------------------------
  // Una tabla que se ordena tocando el nombre de la columna. columnas: [{titulo, valor(fila), texto(fila), num, largo, lectura}].
  function tabla(columnas, filas, claseDeFila) {
    const t = el("table", { clase: "tt-tabla" }), cabeza = el("tr"), cuerpo = el("tbody");
    let por = -1, baja = true;
    function pintar() {
      const orden = filas.slice();
      if (por >= 0) {
        const c = columnas[por];
        orden.sort((a, b) => {
          const x = c.valor(a), y = c.valor(b);
          const r = typeof x === "string" || typeof y === "string" ? String(x == null ? "" : x).localeCompare(String(y == null ? "" : y), "es")
            : (x == null ? -Infinity : x) - (y == null ? -Infinity : y);
          return baja ? -r : r;
        });
      }
      cuerpo.replaceChildren(...orden.map((f) => {
        const tr = el("tr", claseDeFila && claseDeFila(f) ? { clase: claseDeFila(f) } : null);
        columnas.forEach((c) => {
          const v = c.texto ? c.texto(f) : c.valor(f);
          tr.append(el("td", { clase: (c.num ? "num " : "") + (c.largo ? "largo " : "") + (c.lectura ? "lectura" : "") }, v == null ? "" : v instanceof Node ? v : String(v)));
        });
        return tr;
      }));
      Array.from(cabeza.children).forEach((th, i) => th.setAttribute("aria-sort", i === por ? (baja ? "descending" : "ascending") : "none"));
    }
    columnas.forEach((c, i) => {
      cabeza.append(el("th", { scope: "col", clase: c.num ? "num" : "" }, boton(c.titulo, "", () => {
        baja = por === i ? !baja : !!c.num;
        por = i;
        pintar();
      })));
    });
    t.append(el("thead", null, cabeza), cuerpo);
    pintar();
    return el("div", { clase: "tt-desborde" }, t);
  }
  function ficha(pares) {
    const dl = el("dl", { clase: "d-ficha" });
    pares.forEach((p) => { if (p[1] != null && p[1] !== "") dl.append(el("dt", { texto: p[0] }), el("dd", { texto: String(p[1]) })); });
    return dl;
  }
  // Los avisos del motor, dichos en llano. El de una señal de coordinación apagada se arma con sus cifras; el texto original queda plegado.
  function avisos() {
    if (!INF) return [];
    const c = INF.coordinacion || {}, alarma = c.alarma || {};
    return INF.avisos.map((a) => {
      const m = /^coordinación, capa (\w+):/.exec(a), x = m && alarma[m[1]];
      if (!x || x.real == null || x.barajado == null) return { llano: a.charAt(0).toUpperCase() + a.slice(1) + ".", original: null };
      const apagada = (c.capas_apagadas || []).indexOf(m[1]) >= 0;
      return { original: a, llano: "La señal de coordinación «" + (SENALES[m[1]] || m[1]) + "» no distingue nada en este set: con las cuentas mezcladas al azar marca " +
        num(x.barajado) + " cuentas, y con las reales, " + num(x.real) + "." + (apagada ? " El análisis la apagó y no la usó para marcar cuentas." : "") };
    });
  }
  function ventanaAvisos(o) {
    const todos = avisos();
    if (!INF) return null;
    const v = ventana(todos.length === 1 ? "1 aviso del análisis" : todos.length + " avisos del análisis", o);
    const cuerpo = v.querySelector(".tt-ventana__cuerpo");
    if (!todos.length) cuerpo.append(el("p", { clase: "d-vacio", texto: "El motor no dejó avisos sobre este set." }));
    todos.forEach((a) => cuerpo.append(el("div", { clase: "d-aviso" }, el("b", { texto: "[!]" }), el("div", null, el("p", { texto: a.llano }),
      a.original ? el("details", null, el("summary", { texto: "Texto del motor" }), el("p", { texto: a.original })) : null))));
    return nota(v, "avisos");
  }
  const pie = () => el("p", { clase: "d-pie d-ancho", texto: "Tablero generado el " + D.generado.slice(0, 16).replace("T", " a las ") +
    " a partir del resultado del análisis y del " + delSet + "." });

  // --- Las pestañas ---------------------------------------------------------------------------------------
  const PESTANAS = [
    { id: "resumen", nombre: "Resumen", pinta: pintarResumen },
    { id: "circula", nombre: "Qué circula", pinta: pintarCircula },
    { id: "cuando", nombre: "Desde cuándo", pinta: pintarCuando },
    { id: "empuja", nombre: "Quién lo empuja", pinta: pintarEmpuja },
    { id: "donde", nombre: "Dónde circula", pinta: pintarDonde },
    APP ? { id: "comentarios", nombre: "Comentarios", pinta: pintarComentarios } : null,
    { id: "corrida", nombre: "La corrida", pinta: pintarCorrida }].filter(Boolean);
  const pintadas = {};
  function pintarPestana(p) {
    if (pintadas[p.id]) return;
    pintadas[p.id] = true;
    p.pinta(id("p-" + p.id));
    marcarSeleccion();
    pintarSeleccion();
    pintarFicha();
  }
  function abrir(pid) {
    const p = PESTANAS.find((x) => x.id === pid) || PESTANAS[0];
    PESTANAS.forEach((x) => {
      id("p-" + x.id).hidden = x !== p;
      id("b-" + x.id).setAttribute("aria-selected", x === p ? "true" : "false");
    });
    pintarPestana(p);
    try { history.replaceState(null, "", "#" + p.id); } catch (e) { /* algunos navegadores no lo permiten en archivos sueltos */ }
    window.scrollTo(0, 0);
    mostrarNota(null);
  }

  // --- Resumen: la mesa con las tres preguntas ------------------------------------------------------------
  function pintarResumen(s) {
    s.classList.add("d-mesa");
    const visibles = porVolumen.slice(0, 12), max = porVolumen.length ? porVolumen[0].comentarios : 0;
    s.append(ventana("Qué circula", { num: 1, foco: true, ver: "circula", fuente: "comentarios.csv y narrativas.csv del resultado; " + delSet + "; n = " + num(T.comentarios) + " comentarios." },
      pregunta("¿Qué circula?"), respuestaCircula(), porVolumen.length ? listaPostura(visibles) : null,
      porVolumen.length > visibles.length ? enlace("Ver las " + num(porVolumen.length) + " narrativas", () => abrir("circula")) : null,
      porVolumen.length ? leyendaPostura(max) : null, porVolumen.length ? el("div", { clase: "d-seleccion" }) : null));

    const empuja = ventana("Quién lo empuja", { num: 2, ver: "empuja", fuente: "cuentas.csv del resultado y las cuentas del " + delSet + "; n = " + num(T.cuentas) + " cuentas." },
      pregunta("¿Quién lo empuja?"), respuestaEmpuja());
    const cuerpo = empuja.querySelector(".tt-ventana__cuerpo");
    if (D.operaciones.length) {
      const ops = D.operaciones.slice().sort((a, b) => b.comentarios - a.comentarios);
      ops.slice(0, 4).forEach((op) => cuerpo.append(nota(sello(op), "operacion", valoresOperacion(op)), " "));
      if (ops.length > 4) cuerpo.append(el("span", { clase: "d-vacio", texto: "y " + num(ops.length - 4) + " más" }));
      cuerpo.append(rotulo("La operación " + (ops.length > 1 ? ops[0].etiqueta + " " : "") + "contra las demás cuentas"), pares(ops[0], true) || "", pajar(), descargo());
    }
    s.append(empuja);

    s.append(ventana("Desde cuándo", { num: 3, ver: "cuando", continuo: true, clase: "d-ancho",
      fuente: "narrativas.csv y comentarios.csv del resultado, con la fecha de cada comentario en el " + delSet + ". Horas del set (" + D.periodo.zona + ")." },
      pregunta("¿Desde cuándo?"), respuestaCuando(), TR.cantidad && porOrigen.length ? figuraTiempo(false) : null, TR.cantidad && porOrigen.length ? leyendaTiempo() : null));
    s.append(ventanaAvisos({ clase: "d-ancho", ver: "corrida" }) || "", pie());
  }

  // --- Qué circula ----------------------------------------------------------------------------------------
  function pintarCircula(s) {
    if (!porVolumen.length) return s.append(ventana("Qué circula", { foco: true }, pregunta("¿Qué circula?"), respuestaCircula()));
    s.append(ventana("Qué circula", { num: 1, foco: true, fuente: "comentarios.csv y narrativas.csv del resultado; " + delSet + "; n = " + num(T.comentarios) + " comentarios." },
      pregunta("¿Qué circula?"), respuestaCircula(),
      ayuda("Las " + num(T.narrativas) + " narrativas, de la que más comentarios tiene a la que menos. Al elegir una, abajo se abre su ficha completa."),
      listaPostura(porVolumen, { completa: true }), leyendaPostura(porVolumen[0].comentarios)));
    s.append(ventana("Ficha de la narrativa", { num: 2, id: "ficha" }));
    s.append(nota(ventana("Todas las narrativas, en tabla", { num: 3 }, tabla([
      { titulo: "ID", valor: (n) => n.etiqueta },
      { titulo: "Título", valor: (n) => n.titulo, texto: (n) => titulo(n), lectura: true, largo: true },
      { titulo: "Comentarios", valor: (n) => n.comentarios, texto: (n) => num(n.comentarios), num: true },
      { titulo: "Del total con narrativa", valor: (n) => n.comentarios, texto: (n) => pct(n.comentarios, T.con_narrativa), num: true },
      { titulo: "Apoyan", valor: (n) => n.apoya, texto: (n) => num(n.apoya) + " (" + pct(n.apoya, n.comentarios) + ")", num: true },
      { titulo: "Rechazan", valor: (n) => n.rechaza, texto: (n) => num(n.rechaza) + " (" + pct(n.rechaza, n.comentarios) + ")", num: true },
      { titulo: "Cuentas", valor: (n) => n.cuentas, texto: (n) => num(n.cuentas), num: true },
      { titulo: "Nace", valor: (n) => n.origen_s, texto: (n) => n.origen_s == null ? "sin fecha" : fecha(n.origen_s), num: true },
      { titulo: "De cuentas con señales", valor: (n) => n.coordinados, texto: (n) => num(n.coordinados) + " (" + pct(n.coordinados, n.comentarios) + ")", num: true }
    ], porVolumen, (n) => n.etiqueta === elegida ? "is-elegida" : "")), "tabla_narrativas"), pie());
  }
  function concentraciones(n) {
    return fuentesConDatos.map((f) => {
      const c = n.fuentes[f.id] || 0;
      return { f: f, c: c, veces: n.comentarios && T.comentarios ? (c / n.comentarios) / (f.comentarios / T.comentarios) : 0 };
    }).filter((x) => x.veces >= UMBRAL && x.c >= MINIMO).sort((a, b) => b.veces - a.veces);
  }
  function lado(n, postura, nombre) {
    const caja = el("div", { clase: "d-lado" }, el("h4", null, el("i", { clase: "d-muestra d-" + postura }), nombre + " (" + num(n[postura]) + ")"));
    const ej = n.ejemplos[postura] || [];
    if (!ej.length) caja.append(el("p", { clase: "d-vacio", texto: "Sin comentarios de este lado." }));
    ej.forEach((e) => caja.append(el("div", { clase: "d-cita" }, el("p", { clase: "tt-cita", texto: e.texto }), el("small", { texto: plural(e.me_gusta, "me gusta", "me gusta") }))));
    return caja;
  }
  function campo(nombre, valor, detalle, clave, valores) {
    return nota(el("div", null, el("dt", { texto: nombre }), el("dd", null, valor, detalle ? el("small", { texto: detalle }) : null)), clave, valores);
  }
  function pintarFicha() {
    const caja = id("ficha");
    if (!caja) return;
    const cuerpo = caja.querySelector(".tt-ventana__cuerpo"), n = porEtiqueta[elegida];
    if (!n) return cuerpo.replaceChildren(el("p", { clase: "d-vacio", texto: "Elegí una narrativa de la lista de arriba para ver su ficha completa." }));
    const v = valoresNarrativa(n);
    cuerpo.replaceChildren(nota(el("div", null, el("p", null, el("span", { clase: "tt-resaltado", texto: n.etiqueta }), etiquetaTitulo(n)),
      el("h3", { clase: "tt-titulo", texto: titulo(n) })), "titulo", v));
    cuerpo.append(el("dl", { clase: "tt-campos" },
      campo("Comentarios", num(n.comentarios), pct(n.comentarios, T.con_narrativa) + " de los que tienen narrativa", "narrativa", v),
      campo("La apoyan", pct(n.apoya, n.comentarios), plural(n.apoya, "comentario", "comentarios"), "postura", v),
      campo("La rechazan", pct(n.rechaza, n.comentarios), plural(n.rechaza, "comentario", "comentarios"), "postura", v),
      campo("Cuentas distintas", num(n.cuentas), "escribieron sobre ella", "cuentas_narrativa", v),
      campo("Nace", n.origen_s == null ? "sin fecha" : fecha(n.origen_s), n.origen_s == null ? "" : "hora del set (" + D.periodo.zona + ")", "origen", v),
      campo("De cuentas con señales", pct(n.coordinados, n.comentarios), plural(n.coordinados, "comentario", "comentarios"), "coordinados_narrativa",
        Object.assign({}, v, { pct: pctFino(n.coordinados, n.comentarios) }))));
    if (n.frases.length) {
      const f = el("div", { clase: "d-frases" });
      n.frases.forEach((x) => f.append(el("span", { texto: x })));
      cuerpo.append(rotulo("Frases clave"), nota(f, "titulo", v));
    }
    if (TR.cantidad && n.comentarios) {
      const g = grafico(capasPostura(n), { origen: n.origen_s, alto: true });
      cuerpo.append(rotulo("Cómo creció"), nota(el("div", null, g.svg, eje()), "crecimiento", Object.assign({}, v, { pico: cuantoPico(g) })),
        el("p", { clase: "d-leyenda" }, el("span", null, el("i", { clase: "d-muestra d-apoya" }), "apoya"), el("span", null, el("i", { clase: "d-muestra d-rechaza" }), "rechaza"),
          el("span", { texto: "Cada barra son " + tramoTexto() + ". ▼ origen. Pico: " + cuantoPico(g) + (g.cuando == null ? "" : ", el " + fecha(g.cuando)) + "." })));
    }
    cuerpo.append(rotulo("Qué dice cada lado"), ayuda("Los comentarios con más me gusta de cada lado, sin repetir textos."),
      nota(el("div", { clase: "d-dos" }, lado(n, "apoya", "La apoyan"), lado(n, "rechaza", "La rechazan")), "ejemplos"));
    const fuentes = fuentesConDatos.map((f) => ({ f: f, c: n.fuentes[f.id] || 0 })).filter((x) => x.c).sort((a, b) => b.c - a.c);
    if (fuentes.length) {
      const b = el("div", { clase: "d-barras" }), fuertes = concentraciones(n);
      fuentes.forEach((x) => b.append(el("span", { texto: x.f.nombre + (x.f.tipo ? " (" + x.f.tipo + ")" : "") }),
        el("span", { clase: "barra", "aria-hidden": "true" }, el("i", { style: "width:" + 100 * x.c / fuentes[0].c + "%" })),
        el("span", { clase: "cuanto", texto: num(x.c) + " · " + pct(x.c, n.comentarios) })));
      cuerpo.append(rotulo("En qué fuentes circula"), el("p", { clase: "tt-lectura d-respuesta", texto: fuertes.length
        ? "Se concentra en " + fuertes[0].f.nombre + ": " + pct(fuertes[0].c, n.comentarios) + " de sus comentarios, contra " + pct(fuertes[0].f.comentarios, T.comentarios) + " del total."
        : "No se concentra en ninguna fuente: su reparto se parece al de todos los comentarios." }), nota(b, "fuentes_narrativa"));
    }
    if (APP) cuerpo.append(enlace("Ver sus " + num(n.comentarios) + " comentarios, uno por uno", () => verComentarios({ narrativa: n.etiqueta })));
  }

  // --- Desde cuándo ---------------------------------------------------------------------------------------
  function porDia(valores) {
    const dias = {};
    valores.forEach((v, i) => { const d = Math.floor((TR.inicio_s + i * TR.segundos) / 86400); dias[d] = (dias[d] || 0) + v; });
    return dias;
  }
  function pintarCuando(s) {
    if (!TR.cantidad || !porOrigen.length) return s.append(ventana("Desde cuándo", { foco: true }, pregunta("¿Desde cuándo?"), respuestaCuando()));
    s.append(ventana("Desde cuándo", { num: 1, foco: true, continuo: true,
      fuente: "narrativas.csv y comentarios.csv del resultado, con la fecha de cada comentario en el " + delSet + ". Horas del set (" + D.periodo.zona + ")." },
      pregunta("¿Desde cuándo?"), respuestaCuando(),
      ayuda("Una fila por narrativa, de la que nace primero a la que nace última. Al elegir una, se resalta también en las demás ventanas."),
      figuraTiempo(true), leyendaTiempo()));
    const picos = porOrigen.map((n) => ({ n: n, g: grafico([{ valores: totalPorTramo(n), clase: "b", nombre: "comentarios" }]) }));
    s.append(nota(ventana("Nacimiento y pico de cada narrativa", { num: 2 }, tabla([
      { titulo: "ID", valor: (x) => x.n.etiqueta },
      { titulo: "Título", valor: (x) => x.n.titulo, texto: (x) => titulo(x.n), lectura: true, largo: true },
      { titulo: "Nace", valor: (x) => x.n.origen_s, texto: (x) => x.n.origen_s == null ? "sin fecha" : fecha(x.n.origen_s), num: true },
      { titulo: "Primer comentario", valor: (x) => x.n.primero_s, texto: (x) => x.n.primero_s == null ? "sin fecha" : fecha(x.n.primero_s), num: true },
      { titulo: "Pico (tramo de " + tramoTexto() + ")", valor: (x) => x.g.cuando, texto: (x) => x.g.cuando == null ? "" : fecha(x.g.cuando), num: true },
      { titulo: "Comentarios en el pico", valor: (x) => x.g.pico, texto: (x) => num(x.g.pico), num: true },
      { titulo: "Comentarios", valor: (x) => x.n.comentarios, texto: (x) => num(x.n.comentarios), num: true }
    ], picos)), "tabla_origen"));
    const dias = Object.keys(porDia(D.serie_total.con_narrativa)).map(Number).sort((a, b) => a - b);
    const columnas = [{ titulo: "ID", valor: (f) => f.nombre }].concat(dias.map((d) => ({ titulo: fecha(d * 86400, false), valor: (f) => f.dias[d] || 0,
      texto: (f) => f.dias[d] ? num(f.dias[d]) : "", num: true })), [{ titulo: "Total", valor: (f) => f.total, texto: (f) => num(f.total), num: true }]);
    const filas = porOrigen.map((n) => ({ nombre: n.etiqueta, dias: porDia(totalPorTramo(n)), total: n.comentarios }));
    filas.push({ nombre: "ruido", dias: porDia(D.serie_total.ruido), total: T.ruido });
    s.append(nota(ventana("Comentarios por día", { num: 3 }, ayuda("Los números de la figura de arriba, día por día. No incluye los comentarios sin una fecha legible."),
      tabla(columnas, filas)), "tabla_dias"), pie());
  }

  // --- Quién lo empuja ------------------------------------------------------------------------------------
  function ventanaOperacion(op, k, foco) {
    const v = valoresOperacion(op), caja = ventana("Operación " + op.etiqueta, { num: k, foco: foco,
      fuente: "cuentas.csv y comentarios.csv del resultado, con las cuentas y los textos del " + delSet + "." });
    const cuerpo = caja.querySelector(".tt-ventana__cuerpo");
    cuerpo.append(nota(sello(op), "operacion", v),
      el("p", { clase: "tt-lectura d-respuesta", texto: plural(op.cuentas, "cuenta", "cuentas") + " (" + pctFino(op.cuentas, T.cuentas) + " de las del set) escribieron " +
        plural(op.comentarios, "comentario", "comentarios") + " (" + pctFino(op.comentarios, T.comentarios) + " del total)." }),
      rotulo("La operación contra las demás cuentas"), pares(op) || el("p", { clase: "d-vacio", texto: "No hay datos para comparar." }));
    cuerpo.append(rotulo("Qué empuja"));
    if (op.narrativas.length) {
      cuerpo.append(listaPostura(op.narrativas, { completa: true, ancho: "41ch", nota: "empuja", reparto: (x, n) => pct(x.comentarios, n.comentarios) + " de esa narrativa · apoya " + pct(x.apoya, x.comentarios) }),
        leyendaPostura(op.narrativas[0].comentarios, "comentarios de la operación"));
      if (op.ruido) cuerpo.append(el("p", { clase: "d-ayuda", texto: "Además, " + plural(op.ruido, "comentario suyo quedó", "comentarios suyos quedaron") + " sin narrativa." }));
    } else cuerpo.append(el("p", { clase: "d-vacio", texto: "Ninguno de sus comentarios tiene narrativa." }));
    if (op.textos.length) {
      const ul = el("ul", { clase: "d-repite" });
      op.textos.forEach((t) => ul.append(el("li", null, el("span", { texto: plural(t.veces, "vez", "veces") + " · " + plural(t.cuentas, "cuenta", "cuentas") }),
        el("span", { clase: "tt-cita", texto: t.texto }))));
      cuerpo.append(rotulo("Lo que más repite"), nota(ul, "repite"));
    }
    if (TR.cantidad && op.comentarios) {
      const g = grafico([{ valores: op.serie, clase: "coord", nombre: "comentarios de la operación" }], { alto: true });
      cuerpo.append(rotulo("Cuándo actúa"), nota(el("div", null, g.svg, eje()), "cuando_actua", { pico: cuantoPico(g) }),
        el("p", { clase: "d-leyenda" }, el("span", { texto: "Cada barra son " + tramoTexto() + ". Pico: " + cuantoPico(g) + (g.cuando == null ? "" : ", el " + fecha(g.cuando)) + "." })));
    }
    if ((op.cuentas_una_por_una || []).length) {
      cuerpo.append(rotulo("Las cuentas, una por una"), nota(tabla([
        { titulo: "Cuenta", valor: (c) => c.cuenta },
        { titulo: "Usuario", valor: (c) => c.usuario },
        { titulo: "Creada", valor: (c) => c.creada },
        { titulo: "Seguidores", valor: (c) => c.seguidores, texto: (c) => c.seguidores == null ? "" : num(c.seguidores), num: true },
        { titulo: "Siguiendo", valor: (c) => c.siguiendo, texto: (c) => c.siguiendo == null ? "" : num(c.siguiendo), num: true },
        { titulo: "Comentarios", valor: (c) => c.comentarios, texto: (c) => num(c.comentarios), num: true },
        { titulo: "Con narrativa", valor: (c) => c.con_narrativa, texto: (c) => num(c.con_narrativa), num: true }
      ], op.cuentas_una_por_una), "cuentas_operacion"));
      if (APP) cuerpo.append(enlace("Ver los comentarios de las cuentas con señales de coordinación", () => verComentarios({ coordinadas: true })));
    }
    return caja;
  }
  function ventanaSenales(k) {
    const c = INF && INF.coordinacion;
    if (!c || !c.marcadas_por_capa) return null;
    const apagadas = c.capas_apagadas || [], alarma = c.alarma || {};
    const filas = Object.keys(c.marcadas_por_capa).map((x) => ({ k: x, a: alarma[x] || {}, apagada: apagadas.indexOf(x) >= 0, n: c.marcadas_por_capa[x] }));
    return nota(ventana("Las cuatro señales de coordinación", { num: k }, tabla([
      { titulo: "Señal", valor: (f) => SENALES[f.k] || f.k },
      { titulo: "Cuentas que marca", valor: (f) => f.a.real, texto: (f) => f.a.real == null ? "" : num(f.a.real), num: true },
      { titulo: "Con las cuentas mezcladas al azar", valor: (f) => f.a.barajado, texto: (f) => f.a.barajado == null ? "" : num(f.a.barajado), num: true },
      { titulo: "En el resultado", valor: (f) => f.apagada ? -1 : f.n, texto: (f) => f.apagada ? "se apagó: no distingue" : "◆ " + plural(f.n, "cuenta", "cuentas"), num: true }
    ], filas)), "senales");
  }
  function pintarEmpuja(s) {
    s.append(ventana("Quién lo empuja", { num: 1, foco: true, fuente: "cuentas.csv del resultado y las cuentas del " + delSet + "; n = " + num(T.cuentas) + " cuentas." },
      pregunta("¿Quién lo empuja?"), respuestaEmpuja(), pajar(), descargo()));
    let k = 2;
    D.operaciones.forEach((op) => s.append(ventanaOperacion(op, k++, false)));
    const con = D.narrativas.filter((n) => n.coordinados).sort((a, b) => b.coordinados / b.comentarios - a.coordinados / a.comentarios);
    if (con.length) {
      const max = con[0].coordinados / con[0].comentarios, b = el("div", { clase: "d-barras tt-coord" });
      con.forEach((n) => b.append(el("span", { clase: "tt-postura__titulo", style: "color:var(--tinta)", texto: titulo(n) }),
        el("span", { clase: "barra", "aria-hidden": "true" }, el("i", { style: "width:" + 100 * (n.coordinados / n.comentarios) / max + "%" })),
        el("span", { clase: "cuanto", texto: pct(n.coordinados, n.comentarios) + " · " + num(n.coordinados) + " de " + num(n.comentarios) })));
      s.append(nota(ventana("Qué parte de cada narrativa viene de cuentas con señales", { num: k++ },
        ayuda("La barra más larga equivale a " + pct(con[0].coordinados, con[0].comentarios) + " de los comentarios de su narrativa: la escala está ampliada para que se vea. " +
          "Las narrativas que no figuran no tienen comentarios de esas cuentas."), b), "parte_coordinada", { max: pct(con[0].coordinados, con[0].comentarios) }));
    }
    s.append(ventanaSenales(k++) || "", pie());
  }

  // --- Dónde circula --------------------------------------------------------------------------------------
  function pintarDonde(s) {
    const narrativas = porVolumen.filter((n) => n.comentarios);
    if (!fuentesConDatos.length || !narrativas.length) return s.append(ventana("Dónde circula", { foco: true }, pregunta("¿Dónde circula?"), respuesta("El set no trae fuentes para mostrar.")));
    let marcadas = 0, mayor = null;
    narrativas.forEach((n) => concentraciones(n).forEach((x) => { marcadas++; if (!mayor || x.veces > mayor.x.veces) mayor = { n: n, x: x }; }));
    const p = respuesta(marcadas ? num(marcadas) + " de las " + num(narrativas.length * fuentesConDatos.length) + " combinaciones de narrativa y fuente llevan ▲: ahí la narrativa pesa al menos " +
      dec(UMBRAL, 1) + " veces lo que la fuente pesa en el total." : "Ninguna narrativa se concentra en una fuente: todas se reparten parecido al total de los comentarios.");
    if (mayor) p.append(" La más marcada es «" + mayor.n.titulo + "» (", mono(mayor.n.etiqueta), ") en " + mayor.x.f.nombre + ": " + pct(mayor.x.c, mayor.n.comentarios) +
      " de sus comentarios, contra " + pct(mayor.x.f.comentarios, T.comentarios) + " del total.");
    const t = el("table", { clase: "tt-tabla d-fuentes" }), cabeza = el("tr", null, el("th", { scope: "col", texto: "ID" }), el("th", { scope: "col", texto: "Narrativa" }));
    fuentesConDatos.forEach((f) => cabeza.append(el("th", { scope: "col", clase: "num" }, f.nombre, el("small", { texto: f.tipo || " " }))));
    const cuerpo = el("tbody"), base = el("tr", { clase: "is-base" }, el("td"), el("td", { texto: "Todos los comentarios del set" }));
    fuentesConDatos.forEach((f) => base.append(el("td", { clase: "num", title: num(f.comentarios) + " comentarios", texto: pct(f.comentarios, T.comentarios) })));
    cuerpo.append(base);
    narrativas.forEach((n) => {
      const fuertes = concentraciones(n).map((x) => x.f.id), fila = el("tr", { "data-id": n.etiqueta }, el("td", { texto: n.etiqueta }), el("td", { clase: "lectura largo", texto: titulo(n) }));
      fuentesConDatos.forEach((f) => {
        const c = n.fuentes[f.id] || 0, si = fuertes.indexOf(f.id) >= 0;
        fila.append(el("td", { clase: "num" + (si ? " is-marca" : ""), title: num(c) + " de " + num(n.comentarios) + " comentarios", texto: c ? (si ? "▲ " : "") + pct(c, n.comentarios) : "" }));
      });
      cuerpo.append(fila);
    });
    t.append(el("thead", null, cabeza), cuerpo);
    s.append(ventana("Dónde circula", { num: 1, foco: true, fuente: "comentarios.csv del resultado, con la publicación y la fuente de cada comentario en el " + delSet + "." },
      pregunta("¿Dónde circula?"), p,
      ayuda("Qué parte de los comentarios de cada narrativa está en las publicaciones de cada fuente. Cada fila suma 100 %. La primera fila es la referencia: cómo se reparten todos los comentarios del set."),
      nota(el("div", { clase: "tt-desborde" }, t), "fuentes"),
      el("p", { clase: "d-leyenda" }, el("span", { texto: "▲ la narrativa pesa en esa fuente al menos " + dec(UMBRAL, 1) + " veces lo que la fuente pesa en el total, con " + num(MINIMO) + " comentarios o más." }))), pie());
  }

  // --- Comentarios, uno por uno (solo desde la aplicación) -----------------------------------------------
  const filtro = { narrativa: "", postura: "", coordinadas: false, texto: "", orden: "fecha", pagina: 0 };
  let cargarComentarios = null;
  function verComentarios(cambios) {
    Object.assign(filtro, { narrativa: "", postura: "", coordinadas: false, texto: "", pagina: 0 }, cambios);
    abrir("comentarios");
    cargarComentarios(true);
  }
  function pintarComentarios(s) {
    const opcion = (valor, texto) => el("option", { value: valor, texto: texto });
    const narrativa = el("select", { "aria-label": "Narrativa" }, opcion("", "Todas las narrativas y el ruido"), opcion("ruido", "Sin narrativa (ruido)"));
    porVolumen.forEach((n) => narrativa.append(opcion(n.etiqueta, n.etiqueta + " · " + n.titulo.slice(0, 56))));
    const postura = el("select", { "aria-label": "Postura" }, opcion("", "Las dos posturas"), opcion("apoya", "Apoya"), opcion("rechaza", "Rechaza"));
    const orden = el("select", { "aria-label": "Orden" }, opcion("fecha", "Por fecha"), opcion("me_gusta", "Por me gusta"));
    const coordinadas = el("input", { type: "checkbox" }), texto = el("input", { type: "search", placeholder: "Buscar en el texto" });
    const cuerpo = el("tbody"), cuenta = el("span", { clase: "d-id" }), antes = boton("Anterior", "tt-boton", () => { filtro.pagina--; cargar(); });
    const despues = boton("Siguiente", "tt-boton", () => { filtro.pagina++; cargar(); });
    async function cargar() {
      const consulta = new URLSearchParams({ narrativa: filtro.narrativa, postura: filtro.postura, coordinadas: filtro.coordinadas ? "1" : "",
        texto: filtro.texto, orden: filtro.orden, pagina: filtro.pagina, t: Q.get("t") || "" });
      let r;
      try {
        const pedido = await fetch("/api/proyectos/" + encodeURIComponent(Q.get("p") || "") + "/comentarios?" + consulta);
        r = await pedido.json();
        if (!pedido.ok) throw new Error(r.error);
      } catch (e) {
        cuerpo.replaceChildren(el("tr", null, el("td", { colspan: "7", clase: "d-vacio", texto: (e && e.message) || "No se pudieron leer los comentarios." })));
        cuenta.textContent = "";
        return;
      }
      cuerpo.replaceChildren(...r.filas.map((f) => el("tr", f.operacion ? { clase: "is-marcada" } : null,
        el("td", { texto: f.fecha || "sin fecha" }),
        el("td", null, f.usuario || f.cuenta, f.operacion ? el("div", { clase: "tt-coord", texto: "◆ " + f.operacion }) : null),
        el("td", { clase: "lectura largo", texto: f.texto }),
        el("td", { title: f.narrativa ? f.titulo : "", texto: f.narrativa || "ruido" }),
        el("td", { texto: f.postura || "" }), el("td", { clase: "num", texto: num(f.me_gusta) }), el("td", { texto: f.fuente || "" }))));
      if (!r.filas.length) cuerpo.append(el("tr", null, el("td", { colspan: "7", clase: "d-vacio", texto: "Ningún comentario cumple esos filtros." })));
      const desde = r.pagina * r.por_pagina;
      cuenta.textContent = r.total ? "Del " + num(desde + 1) + " al " + num(desde + r.filas.length) + ", de " + plural(r.total, "comentario", "comentarios") : "";
      antes.disabled = r.pagina === 0;
      despues.disabled = desde + r.filas.length >= r.total;
    }
    cargarComentarios = (desdeAfuera) => {
      if (desdeAfuera) {
        narrativa.value = filtro.narrativa;
        postura.value = filtro.postura;
        coordinadas.checked = filtro.coordinadas;
        texto.value = filtro.texto;
      }
      cargar();
    };
    function cambio() {
      Object.assign(filtro, { narrativa: narrativa.value, postura: postura.value, coordinadas: coordinadas.checked, texto: texto.value.trim(), orden: orden.value, pagina: 0 });
      cargar();
    }
    [narrativa, postura, orden, coordinadas].forEach((x) => x.addEventListener("change", cambio));
    texto.addEventListener("keydown", (ev) => { if (ev.key === "Enter") cambio(); });
    texto.addEventListener("search", cambio);
    s.append(nota(ventana("Comentarios", { num: 1, foco: true, fuente: "comentarios.csv del resultado, con el texto, la cuenta y la fuente de cada comentario en el " + delSet + "." },
      ayuda("Los " + num(T.comentarios) + " comentarios del set, uno por uno, con la narrativa y la postura que les asignó el análisis. La marca ◆ señala las cuentas con señales de coordinación."),
      el("div", { clase: "d-filtros" }, narrativa, postura, el("label", null, coordinadas, "Solo cuentas con señales de coordinación"), texto, orden),
      el("div", { clase: "tt-desborde" }, el("table", { clase: "tt-tabla" }, el("thead", null, el("tr", null,
        el("th", { texto: "Fecha" }), el("th", { texto: "Cuenta" }), el("th", { texto: "Comentario" }), el("th", { texto: "Narrativa" }),
        el("th", { texto: "Postura" }), el("th", { clase: "num", texto: "Me gusta" }), el("th", { texto: "Fuente" }))), cuerpo)),
      el("div", { clase: "d-paginas" }, antes, despues, cuenta)), "comentarios"));
    cargar();
  }

  // --- La corrida -----------------------------------------------------------------------------------------
  const ETAPAS = { lectura: "lectura", preparacion: "preparación del texto", acompanamientos: "respuestas cortas",
    familias: "textos casi iguales", puente: "narrativas", coordinacion: "coordinación", lado_que_apoya: "lado que apoya",
    espera_del_modelo: "espera de la IA", plan_b: "revisión del ruido", titulos: "títulos", lados: "posturas", origen: "origen",
    idioma: "idioma", perfil: "medidas del set", escritura: "escritura" };
  const INTEGRIDAD = { ids_repetidos: "identificadores repetidos", sin_id: "comentarios sin identificador", sin_texto: "comentarios sin texto",
    fechas_sin_leer: "fechas que no se pudieron leer", fechas_sin_zona: "fechas sin zona horaria", fechas_en_otro_formato: "fechas en otro formato",
    fechas_numericas: "fechas escritas como número", respuestas_a_inexistente: "respuestas a un comentario que no existe",
    respuestas_a_si_mismo: "respuestas a sí mismas", sin_publicacion_conocida: "comentarios de una publicación desconocida",
    sin_cuenta_conocida: "comentarios de una cuenta desconocida" };
  function recibo() {
    const c = D.costo || {}, u = (INF && INF.uso_modelo) || {}, r = el("article", { clase: "tt-recibo", "aria-label": "Recibo de la corrida" });
    const fila = (que, valor) => valor == null || valor === "" ? null : el("div", { clase: "tt-recibo__fila" }, el("span", { texto: que }), el("span", { texto: String(valor) }));
    const corte = () => el("div", { clase: "tt-recibo__corte" });
    r.append(el("div", { clase: "tt-recibo__centro" }, el("b", { texto: "δ delfOS" }), el("br"), "Recibo de la corrida", el("br"),
      D.generado.slice(8, 10) + "/" + D.generado.slice(5, 7) + "/" + D.generado.slice(0, 4) + (INF && INF.version ? ", motor " + INF.version : "")), corte());
    [fila("comentarios procesados", c.comentarios_procesados == null ? num(T.comentarios) : num(c.comentarios_procesados)), fila("cuentas", num(T.cuentas)),
      fila("tiempo de proceso", c.segundos == null ? null : dec(c.segundos, 1) + " s"),
      fila("memoria pico", INF && INF.memoria_pico_mib ? dec(INF.memoria_pico_mib, 0) + " MiB" : null)].forEach((x) => { if (x) r.append(x); });
    const etapas = Object.keys((INF && INF.tiempos) || {}).map((k) => ({ k: k, s: Number(INF.tiempos[k]) || 0 }));
    if (etapas.length) {
      const max = etapas.reduce((m, e) => Math.max(m, e.s), 0) || 1;
      r.append(corte(), el("div", { texto: "Etapas, en segundos" }));
      etapas.forEach((e) => r.append(el("div", { clase: "d-recibo__etapa" }, el("span", { texto: ETAPAS[e.k] || e.k }),
        el("span", { clase: "barra", "aria-hidden": "true" }, el("i", { style: "width:" + 100 * e.s / max + "%" })), el("span", { texto: dec(e.s, 2) }))));
    }
    r.append(corte());
    if (INF && INF.sin_modelo) r.append(el("div", { texto: "corrida sin IA, a propósito" }));
    [fila("pedidos a la IA", u.pedidos), fila("llamadas a la API", u.llamadas_api), fila("respuestas de la caché", u.respuestas_de_cache),
      fila("tokens de IA", c.tokens_ia == null ? null : num(c.tokens_ia)), fila("costo de IA", c.usd_ia == null ? null : "USD " + dec(c.usd_ia, 4))].forEach((x) => { if (x) r.append(x); });
    if (c.usd_por_mil_comentarios != null) r.append(corte(), el("div", { texto: "Por cada mil comentarios" }), el("div", { clase: "tt-recibo__total", texto: "USD " + dec(c.usd_por_mil_comentarios, 6) }));
    if (c.hardware || c.almacenamiento) r.append(corte(), el("div", { clase: "d-recibo__chico", texto: [c.hardware, c.almacenamiento].filter(Boolean).join(". ") }));
    return nota(r, "costo");
  }
  function ventanaSetDeEntrada(k) {
    const m = INF && INF.medidas;
    if (!m || !Object.keys(m).length) return null;
    const filas = [], parte = (x) => x == null ? "" : dec(100 * x, 1) + " %";
    const medida = (clave, nombre, formato) => { if (m[clave]) filas.push({ nombre: nombre, este: formato(m[clave].valor), referencia: formato(m[clave].practica) }); };
    medida("respuestas", "Respuestas sobre comentarios", parte);
    medida("textos_distintos", "Textos distintos sobre comentarios", parte);
    medida("nucleos_sobre_textos", "Frases base sobre textos distintos", parte);
    medida("max_comentarios_publicacion", "Comentarios en la publicación más grande", (x) => x == null ? "" : num(x));
    medida("max_comentarios_cuenta", "Comentarios de la cuenta más activa", (x) => x == null ? "" : num(x));
    if (m.volumen) filas.push({ nombre: "Comentarios, cuentas y días", este: [m.volumen.comentarios, m.volumen.cuentas, m.volumen.dias].map((x) => x == null ? "?" : num(x)).join(" · "), referencia: "" });
    if (m.idioma && m.idioma.idioma_del_set) {
      const p = m.idioma.proporcion_detectada || {};
      filas.push({ nombre: "Idioma del set", este: m.idioma.idioma_del_set + (Object.keys(p).length ? " (" + Object.keys(p).map((x) => x + " " + parte(p[x])).join(", ") + ")" : ""), referencia: "" });
    }
    const sucios = Object.keys(m.integridad || {}).filter((x) => INTEGRIDAD[x] && m.integridad[x]);
    filas.push({ nombre: "Datos sucios", este: sucios.length ? sucios.map((x) => num(m.integridad[x]) + " " + INTEGRIDAD[x]).join("; ") : "ninguno", referencia: "" });
    return nota(ventana("El set de entrada", { num: k }, tabla([{ titulo: "Medida", valor: (f) => f.nombre }, { titulo: "Este set", valor: (f) => f.este, largo: true },
      { titulo: "Set de referencia", valor: (f) => f.referencia }], filas)), "set_entrada");
  }
  function pintarCorrida(s) {
    s.classList.add("d-corrida");
    const c = D.costo, derecha = el("div", { clase: "d-columna" });
    s.append(el("div", { clase: "d-columna" }, c ? recibo() : el("p", { clase: "d-vacio", texto: "El resultado no trae costo.json." })), derecha);
    if (c && c.segundos != null) {
      derecha.append(ventana("La corrida", { num: 1, foco: true, fuente: "costo.json del resultado" + (INF ? " y el informe de la corrida." : ".") }, pregunta("¿Cuánto costó?"),
        respuesta("El análisis procesó " + num(c.comentarios_procesados == null ? T.comentarios : c.comentarios_procesados) + " comentarios en " + dec(c.segundos, 1) + " segundos" +
          (Number(c.usd_ia) ? " y gastó USD " + dec(c.usd_ia, 4) + " en IA: USD " + dec(c.usd_por_mil_comentarios || 0, 6) + " por cada mil comentarios." : ", sin gasto de IA."))));
    }
    derecha.append(ventanaAvisos({ num: 2 }) || "");
    const limites = el("ul", { clase: "d-lista" }), punto = (t) => limites.append(el("li", { texto: t }));
    punto("Estas cifras son lo que detectó el análisis. El tablero no las contrasta con una respuesta correcta: muestra el resultado, no mide cuánto acertó.");
    punto(num(T.ruido) + " comentarios (" + pct(T.ruido, T.comentarios) + ") quedaron sin narrativa. Son reacciones, temas sueltos o comentarios que no se pudieron ubicar en ninguna.");
    punto("Una cuenta figura con señales de coordinación cuando el análisis la agrupó en una operación. Que una cuenta no figure no prueba que sea genuina.");
    punto("El origen de cada narrativa es una estimación del análisis, no un dato del set.");
    if (c && Number(c.tokens_ia) === 0) punto("Esta corrida no usó IA: los títulos son la frase más repetida de cada narrativa, en minúsculas y sin tildes.");
    const sinTitulo = D.narrativas.filter((n) => n.sin_titulo).length;
    if (sinTitulo) punto(plural(sinTitulo, "narrativa no tiene", "narrativas no tienen") + " título en el resultado: se muestra su etiqueta.");
    if (T.sin_hora) punto(plural(T.sin_hora, "comentario no tiene", "comentarios no tienen") + " una fecha legible y no aparecen en los gráficos de tiempo.");
    if (T.sin_entrega) punto(plural(T.sin_entrega, "comentario del set no está", "comentarios del set no están") + " en el resultado: se cuentan como ruido.");
    D.problemas.forEach((p) => punto("Datos sucios del set: " + p.problema + " (" + num(p.cantidad) + ")."));
    if (!INF) punto("Este tablero se armó sin el informe de la corrida: no muestra los avisos del motor, las señales de coordinación ni los tiempos por etapa.");
    derecha.append(nota(ventana("Cómo leer las cifras", { num: 3 }, limites), "limites"));
    let k = 4;
    if (INF) {
      const u = INF.uso_modelo || {};
      derecha.append(nota(ventana("Uso de la IA", { num: k++ }, INF.sin_modelo ? el("p", { clase: "d-vacio", texto: "Esta corrida se hizo sin IA, a propósito." })
        : ficha([["Pedidos distintos", u.pedidos], ["Llamadas a la API en esta corrida", u.llamadas_api], ["Respuestas que salieron de la caché", u.respuestas_de_cache],
          ["Pedidos que fallaron", u.errores], ["Tokens", u.tokens == null ? null : num(u.tokens)], ["Costo de todos los pedidos", u.usd == null ? null : "USD " + dec(u.usd, 4)],
          ["Gastado en esta corrida", u.usd_gastado == null ? null : "USD " + dec(u.usd_gastado, 4)],
          ["Títulos redactados por la IA", D.narrativas.filter((n) => n.titulo_de_ia === true).length + " de " + D.narrativas.length]])), "uso_ia"));
      derecha.append(ventanaSetDeEntrada(k++) || "");
      const parametros = Object.keys(INF.configuracion || {});
      if (parametros.length) {
        derecha.append(nota(ventana("Parámetros del motor", { num: k++ }, el("details", null, el("summary", { texto: "Ver los " + parametros.length + " parámetros" }),
          ficha(parametros.map((x) => [x, typeof INF.configuracion[x] === "object" ? JSON.stringify(INF.configuracion[x]) : String(INF.configuracion[x])])))), "parametros"));
      }
    }
    if (c) derecha.append(nota(ventana("Notas de la corrida", { num: k++ }, ficha([["Equipo", c.hardware], ["Almacenamiento", c.almacenamiento], ["Notas del motor", c.notas]])), "costo"));
    derecha.append(nota(ventana("Los archivos del resultado", { num: k++ }, ficha([
      ["comentarios.csv", "Una fila por comentario: su narrativa y su postura. El ruido va con las dos vacías."],
      ["narrativas.csv", "Una fila por narrativa: el título, las frases clave y la fecha de origen."],
      ["cuentas.csv", "Una fila por cuenta: la operación a la que pertenece, o vacío si no está en ninguna."],
      ["costo.json", "Cuánto se procesó, cuánto tardó, cuánto costó la IA y en qué equipo corrió."]])), "archivos"));
    s.append(pie());
  }

  // --- La barra de estado y el arranque -------------------------------------------------------------------
  function pintarEstado() {
    const c = D.costo || {}, partes = ["listo", plural(T.narrativas, "narrativa", "narrativas"), pct(T.con_narrativa, T.comentarios) + " con narrativa",
      "◆ " + plural(T.cuentas_coordinadas, "cuenta", "cuentas"), c.usd_ia == null ? null : "USD " + dec(c.usd_ia, 4), c.segundos == null ? null : dec(c.segundos, 1) + " s",
      elegida ? "selección " + elegida : "sin selección", "Tocá una cifra o una figura para ver su nota"];
    id("estado").replaceChildren(...partes.filter(Boolean).map((t) => el("span", { texto: t })));
  }
  document.addEventListener("click", (ev) => {
    const fila = ev.target.closest("[data-elige]"), explicable = ev.target.closest("[data-nota]"), v = ev.target.closest("[data-ventana]");
    if (fila) elegir(fila.dataset.elige);
    if (explicable) mostrarNota(explicable);
    if (v) enfocar(v);
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && ev.target.matches && ev.target.matches("[data-nota]:not(button)")) mostrarNota(ev.target);
  });
  // La aplicación puede pedir una pestaña o una narrativa desde su árbol.
  window.addEventListener("message", (ev) => {
    if (ev.origin !== location.origin || !ev.data) return;
    if (ev.data.delfos === "elegir") elegir(ev.data.id, true);
    if (ev.data.delfos === "pestana") abrir(ev.data.id);
  });
  let temaAntes = null;
  window.addEventListener("beforeprint", () => {
    PESTANAS.forEach(pintarPestana);
    temaAntes = raiz.getAttribute("data-theme");
    ponerTema("papel");
  });
  window.addEventListener("afterprint", () => { if (temaAntes) ponerTema(temaAntes); });

  if (APP) document.body.classList.add("en-app");
  ponerTema(temaGuardado());
  verNotas(!angosto());
  id("set").textContent = D.nombre ? D.nombre + " · " + huella : D.set;
  PESTANAS.forEach((p) => {
    const b = boton(p.nombre, "tt-pestana", () => abrir(p.id));
    b.id = "b-" + p.id;
    b.setAttribute("role", "tab");
    id("pestanas").append(b);
    id("vista").append(el("section", { id: "p-" + p.id, hidden: "" }));
  });
  pintarEstado();
  abrir(location.hash.slice(1));
  if (APP && window.parent !== window) {
    window.parent.postMessage({ delfos: "tablero", narrativas: porVolumen.map((n) => ({ id: n.etiqueta, titulo: n.titulo, comentarios: n.comentarios, tarde: tarde(n) ? fecha(n.origen_s, false) : "" })),
      operaciones: D.operaciones.map((o) => ({ id: o.etiqueta, cuentas: o.cuentas })) }, location.origin);
  }
})();
