(function () {
  "use strict";
  const A = JSON.parse(document.getElementById("arranque").textContent);
  const id = (x) => document.getElementById(x), raiz = document.documentElement;
  const ESTADOS = { sin_analizar: "sin analizar", analizando: "analizando", listo: "listo", error: "con error", no_encontrado: "no se encuentra" };
  const ARCHIVOS = { comentarios: "Los comentarios", publicaciones: "Las publicaciones que se comentan",
    fuentes: "Las fuentes de esas publicaciones", cuentas: "Las cuentas que comentan" };
  const PESTANAS = [["resumen", "Resumen"], ["circula", "Qué circula"], ["cuando", "Desde cuándo"], ["empuja", "Quién lo empuja"],
    ["donde", "Dónde circula"], ["comentarios", "Comentarios"], ["corrida", "La corrida"]];
  let E = { proyectos: [], clave: {}, sugerencias: {} };
  let actual = null;
  try { actual = localStorage.getItem("delfos.proyecto"); } catch (e) { /* sin permiso para leer: se abre el último proyecto */ }
  let pintado = "";       // lo que quedó dibujado en el centro: evita redibujar el tablero en cada consulta
  let sondeo = null, giro = null;
  let delTablero = null;  // lo que el tablero abierto le cuenta a la aplicación: sus narrativas y operaciones
  let seleccion = null;   // la narrativa elegida en el tablero

  // --- Lo común ------------------------------------------------------------------------------------------
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
  const num = (n) => Number(n).toLocaleString("es-AR");
  const dec = (n, d) => Number(n).toLocaleString("es-AR", { minimumFractionDigits: d, maximumFractionDigits: d });
  const peso = (b) => b >= 1048576 ? dec(b / 1048576, 1) + " MB" : dec(Math.max(1, b / 1024), 0) + " KB";
  const plural = (n, uno, muchos) => num(n) + " " + (n === 1 ? uno : muchos);
  function fecha(iso) {
    const d = new Date(iso);
    return isNaN(d) ? "" : d.toLocaleString("es-AR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
  }
  function boton(texto, clase, alTocar) {
    const b = el("button", { type: "button", clase: clase == null ? "tt-boton" : clase, texto: texto });
    b.addEventListener("click", alTocar);
    return b;
  }
  const principal = (texto, alTocar) => boton(texto, "tt-boton tt-boton--tinta", alTocar);
  const enlace = (texto, alTocar) => boton(texto, "tt-enlace a-enlace", alTocar);
  // Una ventana del sistema: hoja con marco y el título montado sobre el marco. Los hijos van después de las opciones.
  function ventana(nombre, o) {
    o = o || {};
    const controles = el("span", { clase: "tt-ventana__controles" });
    if (o.alCerrar) {
      const x = boton("[×]", "", o.alCerrar);
      x.setAttribute("aria-label", "Cerrar");
      controles.append(x);
    }
    const cuerpo = el("div", { clase: "tt-ventana__cuerpo" });
    for (let i = 2; i < arguments.length; i++) if (arguments[i] != null) cuerpo.append(arguments[i]);
    return el("section", { clase: "tt-ventana" + (o.foco ? " is-foco" : "") + (o.clase ? " " + o.clase : ""), "aria-label": nombre },
      el("header", { clase: "tt-ventana__barra" }, el("h2", { clase: "tt-ventana__titulo", texto: nombre }), controles), cuerpo);
  }
  async function api(metodo, ruta, cuerpo) {
    let r;
    try {
      r = await fetch(ruta, { method: metodo, headers: { "X-Delfos-Token": A.token, "Content-Type": "application/json" },
        body: cuerpo ? JSON.stringify(cuerpo) : undefined });
    } catch (e) {
      throw new Error("No hay respuesta de " + A.nombre + ". Cerrá esta ventana y volvé a abrirlo.");
    }
    let datos = {};
    try { datos = await r.json(); } catch (e) { /* una respuesta sin contenido */ }
    if (!r.ok) throw new Error(datos.error || "No se pudo completar el pedido.");
    return datos;
  }

  // --- El tema: Papel u Oscuro ---------------------------------------------------------------------------
  const LLAVE = "delfos-tema";
  function ponerTema(t, guardar) {
    raiz.setAttribute("data-theme", t);
    id("tema").setAttribute("aria-checked", String(t === "oscuro"));
    id("tema").textContent = (t === "oscuro" ? "[x]" : "[ ]") + " Oscuro";
    if (!guardar) return;
    try { localStorage.setItem(LLAVE, t); } catch (e) { /* sin permiso para guardar: vale hasta cerrar */ }
    const marco = document.querySelector(".a-tablero");  // el tablero abierto se entera solo, por el almacenamiento; esto lo hace inmediato
    try { if (marco && marco.contentDocument) marco.contentDocument.documentElement.setAttribute("data-theme", t); } catch (e) { /* todavía cargando */ }
  }
  const cambiarTema = () => ponerTema(raiz.getAttribute("data-theme") === "oscuro" ? "papel" : "oscuro", true);

  // --- Ventanas de diálogo -------------------------------------------------------------------------------
  function modal(titulo, cuerpo, botones, ancho) {
    const capa = el("div", { clase: "a-capa" }), pie = el("div", { clase: "a-modal__pie" });
    const cerrar = () => { capa.remove(); document.removeEventListener("keydown", tecla); };
    function tecla(ev) {
      const capas = document.querySelectorAll(".a-capa");
      if (ev.key === "Escape" && capas[capas.length - 1] === capa) cerrar();
    }
    botones(cerrar).forEach((b) => pie.append(b));
    const v = ventana(titulo, { foco: true, clase: "is-flotante a-modal" + (ancho ? " is-ancho" : ""), alCerrar: cerrar }, cuerpo, pie);
    v.setAttribute("role", "dialog");
    v.setAttribute("aria-modal", "true");
    capa.append(v);
    document.body.append(capa);
    document.addEventListener("keydown", tecla);
    return cerrar;
  }
  function avisar(mensaje) {
    modal("No se pudo", el("p", { clase: "tt-lectura", texto: mensaje }), (cerrar) => [principal("Entendido", cerrar)]);
  }
  function confirmar(titulo, mensaje, accion, alAceptar) {
    modal(titulo, el("p", { clase: "tt-lectura", texto: mensaje }), (cerrar) => [boton("Cancelar", null, cerrar), principal(accion, () => { cerrar(); alAceptar(); })]);
  }

  // --- El estado, el árbol de proyectos y la barra de estado ---------------------------------------------
  const proyecto = () => E.proyectos.find((p) => p.id === actual) || null;
  function reemplazar(p) { E.proyectos = E.proyectos.map((x) => x.id === p.id ? p : x); }
  const marco = () => document.querySelector(".a-tablero");
  function alTablero(mensaje) {
    const m = marco();
    if (m && m.contentWindow) m.contentWindow.postMessage(mensaje, location.origin);
  }
  function elegir(pid) {
    if (pid !== actual) { delTablero = null; seleccion = null; }
    actual = pid;
    try {
      if (pid) localStorage.setItem("delfos.proyecto", pid);
      else localStorage.removeItem("delfos.proyecto");
    } catch (e) { /* sin permiso para guardar */ }
    pintar();
  }
  async function cargar() {
    E = await api("GET", "/api/estado");
    if (!proyecto()) actual = E.proyectos.length ? E.proyectos[E.proyectos.length - 1].id : null;
    pintar();
  }
  function pintar() {
    const p = proyecto();
    if (!p || p.estado !== "listo") { delTablero = null; seleccion = null; }
    pintarArbol();
    pintarCentro();
    pintarBarras();
    vigilar();
  }
  function rama(ultima, nombre, dato, o) {
    o = o || {};
    const b = el("button", { type: "button", clase: "tt-fila" + (o.abierta ? " is-abierta" : "") + (o.clase ? " " + o.clase : "") },
      el("span", { clase: "a-rama", texto: ultima ? "└─" : "├─" }), el("span", { clase: "a-nombre", texto: nombre }),
      dato ? el("span", { clase: "a-dato", texto: dato }) : null);
    if (o.titulo) b.title = o.titulo;
    b.addEventListener("click", o.alTocar);
    return el("li", o.sel ? { clase: "is-sel" } : null, b);
  }
  function pintarArbol() {
    const caja = id("lista"), p = proyecto();
    caja.replaceChildren();
    if (!E.proyectos.length) return caja.append(el("p", { clase: "a-suave", texto: "Todavía no hay proyectos." }));
    const proyectos = E.proyectos.slice().reverse(), arbol = el("ul", { clase: "tt-arbol" });
    proyectos.forEach((x, i) => arbol.append(rama(i === proyectos.length - 1, x.nombre, x.id === actual ? "abierto" : ESTADOS[x.estado],
      { abierta: x.id === actual, titulo: x.carpeta, alTocar: () => elegir(x.id) })));
    caja.append(arbol);
    if (!p || p.estado !== "listo" || !delTablero) return;
    const n = delTablero.narrativas, ops = delTablero.operaciones, narrativas = el("ul", { clase: "tt-arbol" });
    n.forEach((x, i) => narrativas.append(rama(i === n.length - 1, x.id, num(x.comentarios) + (x.tarde ? " nace " + x.tarde : ""),
      { sel: x.id === seleccion, titulo: x.titulo, alTocar: () => alTablero({ delfos: "elegir", id: x.id }) })));
    caja.append(el("p", { clase: "tt-arbol__grupo", texto: "Narrativas " + n.length }), narrativas);
    if (ops.length) {
      const operaciones = el("ul", { clase: "tt-arbol" });
      ops.forEach((x, i) => operaciones.append(rama(i === ops.length - 1, "◆ " + x.id, plural(x.cuentas, "cuenta", "cuentas"),
        { clase: "tt-coord", alTocar: () => alTablero({ delfos: "pestana", id: "empuja" }) })));
      caja.append(el("p", { clase: "tt-arbol__grupo", texto: "Operaciones " + ops.length }), operaciones);
    }
    const archivos = el("ul", { clase: "tt-arbol" }), nombres = ["comentarios.csv", "narrativas.csv", "cuentas.csv", "costo.json"];
    nombres.forEach((x, i) => archivos.append(rama(i === nombres.length - 1, x, "", { titulo: "Abrir la carpeta del proyecto", alTocar: () => abrirCarpeta(p) })));
    caja.append(el("p", { clase: "tt-arbol__grupo", texto: "Resultado" }), archivos);
  }
  function pintarBarras() {
    const p = proyecto(), u = (p && p.ultimo_analisis) || {}, c = u.conteos || {};
    id("cursor").hidden = !E.proyectos.some((x) => x.estado === "analizando");
    id("abierto").textContent = !p ? "" : p.estado === "listo" && u.fecha ? p.nombre + " · analizado el " + fecha(u.fecha) + (u.con_ia ? " · con IA" : " · sin IA") : p.nombre;
    const partes = [!p ? "sin proyectos" : ESTADOS[p.estado]];
    if (p && p.estado === "listo" && c.comentarios) {
      partes.push(plural(c.narrativas, "narrativa", "narrativas"), dec(100 * c.comentarios_con_narrativa / c.comentarios, 1) + " % con narrativa",
        "◆ " + plural(c.cuentas_marcadas, "cuenta", "cuentas"));
      partes.push(Number(u.usd_ia) ? "USD " + dec(u.usd_ia, 4) : "sin gasto de IA");
      if (u.segundos_del_motor != null) partes.push(dec(u.segundos_del_motor, 1) + " s");
      partes.push(seleccion ? "selección " + seleccion : "sin selección");
    }
    const clave = boton("Clave de IA: " + (E.clave.configurada ? "configurada" : "sin configurar"), "", claveIA);
    id("estado").replaceChildren(...partes.map((t) => el("span", { texto: t })), clave);
  }

  // --- Los menús de la barra de arriba -------------------------------------------------------------------
  let menuAbierto = null;
  function cerrarMenu() {
    if (!menuAbierto) return;
    menuAbierto.caja.remove();
    menuAbierto.boton.setAttribute("aria-expanded", "false");
    menuAbierto = null;
  }
  function opcionesDe(cual) {
    const p = proyecto(), estado = p ? p.estado : null, listo = estado === "listo";
    if (cual === "archivo") {
      return [["Proyecto nuevo…", nuevoProyecto, true], null,
        ["Abrir la carpeta del proyecto", () => abrirCarpeta(p), !!p && estado !== "no_encontrado"],
        ["Exportar el tablero", () => exportar(p), listo], null,
        ["Quitar el proyecto de la lista", () => quitar(p), !!p && estado !== "analizando"]];
    }
    if (cual === "analisis") {
      return [[listo ? "Volver a analizar" : "Analizar comentarios", () => (listo ? volverAAnalizar(p) : analizar(p.id)), !!p && estado !== "analizando" && estado !== "no_encontrado"],
        ["Cancelar el análisis", () => cancelar(p.id), estado === "analizando"]];
    }
    if (cual === "ver") {
      const oscuro = raiz.getAttribute("data-theme") === "oscuro";
      return [[(oscuro ? "[ ]" : "[x]") + " Tema Papel", () => ponerTema("papel", true), true], [(oscuro ? "[x]" : "[ ]") + " Tema Oscuro", () => ponerTema("oscuro", true), true], null]
        .concat(PESTANAS.map((x) => [x[1], () => alTablero({ delfos: "pestana", id: x[0] }), listo]));
    }
    return [["Cómo leer el tablero", ayuda, true], ["Clave de IA…", claveIA, true]];
  }
  function abrirMenu(b, cual) {
    const mismo = menuAbierto && menuAbierto.boton === b;
    cerrarMenu();
    if (mismo) return;
    const caja = el("div", { clase: "a-menu", role: "menu" }), r = b.getBoundingClientRect();
    opcionesDe(cual).forEach((o) => {
      if (!o) return caja.append(el("hr"));
      const x = el("button", { type: "button", role: "menuitem", texto: o[0] });
      x.disabled = !o[2];
      x.addEventListener("click", () => { cerrarMenu(); o[1](); });
      caja.append(x);
    });
    caja.style.left = r.left + "px";
    caja.style.top = r.bottom + 1 + "px";
    document.body.append(caja);
    b.setAttribute("aria-expanded", "true");
    menuAbierto = { caja: caja, boton: b };
  }
  // La letra subrayada es el atajo: Alt+A abre Archivo.
  const MENUS = [["archivo", "", "A", "rchivo"], ["analisis", "A", "n", "álisis"], ["ver", "", "V", "er"], ["ayuda", "A", "y", "uda"]];
  MENUS.forEach((m) => {
    const b = el("button", { type: "button", "aria-haspopup": "menu", "aria-expanded": "false", "data-menu": m[0] }, m[1], el("u", { texto: m[2] }), m[3]);
    b.addEventListener("click", (ev) => { ev.stopPropagation(); abrirMenu(b, m[0]); });
    id("menus").append(b);
  });
  document.addEventListener("click", (ev) => { if (menuAbierto && !menuAbierto.caja.contains(ev.target)) cerrarMenu(); });
  window.addEventListener("blur", cerrarMenu);  // un clic dentro del tablero no llega a esta página
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") return cerrarMenu();
    if (!ev.altKey || ev.ctrlKey || ev.metaKey) return;
    const m = MENUS.find((x) => x[2].toLowerCase() === ev.key.toLowerCase());
    if (!m || document.querySelector(".a-capa")) return;
    ev.preventDefault();
    abrirMenu(document.querySelector('[data-menu="' + m[0] + '"]'), m[0]);
  });

  // --- El centro -----------------------------------------------------------------------------------------
  function pintarCentro() {
    const p = proyecto();
    const marca = !p ? "vacio" : [p.id, p.estado, (p.ultimo_analisis || {}).fecha, (p.ultimo_intento || {}).fecha,
      p.estado === "listo" ? "" : E.clave.configurada].join("|");
    if (marca === pintado) return;
    pintado = marca;
    if (giro) { clearInterval(giro); giro = null; }
    const vistas = { analizando: vistaCarga, listo: vistaTablero, no_encontrado: vistaPerdido };
    id("centro").replaceChildren(...[].concat(!p ? vistaBienvenida() : (vistas[p.estado] || vistaFicha)(p)));
    if (p && p.estado === "analizando") actualizarCarga(p);
  }

  function delfin() {
    const pre = el("pre", { clase: "a-delfin tt-imprime", "aria-hidden": "true" });
    A.delfin.replace(/\n+$/, "").split("\n").forEach((linea, i) => pre.append(el("span", { style: "--i:" + i, texto: linea + "\n" })));
    return pre;
  }
  function lema() {
    const simbolo = el("span", { clase: "a-simbolo" }), marca = id("abierto").parentElement.querySelector(".marca").cloneNode(true);
    simbolo.innerHTML = A.simbolo;  // el símbolo de la marca: un SVG propio, que viene con la página
    return el("div", { clase: "a-lema" }, simbolo, marca);
  }
  function vistaBienvenida() {
    return el("div", { clase: "a-medio" }, ventana(A.nombre, { foco: true }, el("div", { clase: "a-bienvenida" }, delfin(), lema(),
      el("h1", { clase: "tt-pregunta", texto: "Todavía no hay proyectos" }),
      el("p", { clase: "tt-lectura", texto: "Un proyecto es un set de comentarios y su análisis. Para crear el primero, elegí la carpeta donde están los datos y dónde querés guardarlo." }),
      el("div", { clase: "a-acciones" }, principal("Agregar datos", nuevoProyecto)))));
  }

  function pie(p) {
    return el("div", { clase: "a-pie" }, el("span", { texto: "Carpeta del proyecto: " + p.carpeta }), enlace("Abrir carpeta", () => abrirCarpeta(p)),
      enlace("Quitar de la lista", () => quitar(p)));
  }
  function lineaClave() {
    if (E.clave.configurada) return el("p", { clase: "a-suave", texto: "Hay una clave de IA configurada: la IA redacta los títulos y revisa los casos dudosos." });
    return el("p", { clase: "a-suave" }, "No hay una clave de IA: el análisis corre igual, con títulos más simples. ", enlace("Configurar la clave", claveIA));
  }
  function vistaFicha(p) {
    const intento = p.ultimo_intento || {}, cabeza = ventana("Proyecto", { foco: true }, el("h1", { clase: "tt-titulo a-titulo", texto: p.nombre }),
      el("p", { clase: "a-suave", texto: "Creado el " + fecha(p.creado) + "." }));
    const cuerpo = cabeza.querySelector(".tt-ventana__cuerpo");
    if (p.estado === "error") {
      cuerpo.prepend(el("div", { clase: "a-error" }, el("b", { texto: "[!] El análisis no terminó. " }), intento.error || "",
        (intento.registro || []).length ? el("details", null, el("summary", { texto: "Ver el detalle técnico" }), el("pre", { clase: "tt-terminal", texto: intento.registro.join("\n") })) : null));
    }
    cuerpo.append(el("div", { clase: "a-acciones" }, principal(p.estado === "error" ? "Volver a intentar" : "Analizar comentarios", () => analizar(p.id)),
      el("span", { texto: "Detecta narrativas, posturas y cuentas con señales de coordinación." })), lineaClave(), pie(p));
    const filas = el("tbody");
    (p.ficha || []).forEach((f) => filas.append(el("tr", null, el("td", { texto: f.archivo }), el("td", { clase: "lectura", texto: ARCHIVOS[f.archivo.split(".")[0]] || "" }),
      el("td", { clase: "num", texto: f.filas == null ? "sin leer" : num(f.filas) }), el("td", { clase: "num", texto: peso(f.bytes) }))));
    const datos = ventana("Los datos", null, el("table", { clase: "tt-tabla" }, el("thead", null, el("tr", null, el("th", { texto: "Archivo" }),
      el("th", { texto: "Qué tiene" }), el("th", { clase: "num", texto: "Filas" }), el("th", { clase: "num", texto: "Tamaño" }))), filas));
    return el("div", { clase: "a-vista" }, cabeza, datos);
  }
  function vistaPerdido(p) {
    return el("div", { clase: "a-vista" }, ventana("Proyecto", { foco: true }, el("h1", { clase: "tt-titulo a-titulo", texto: p.nombre }),
      el("div", { clase: "a-error" }, el("b", { texto: "[!] " }), "No se encuentra la carpeta del proyecto: " + p.carpeta + ". Puede que se haya movido o borrado."),
      el("div", { clase: "a-acciones" }, boton("Quitar de la lista", null, () => quitar(p)))));
  }

  function vistaCarga(p) {
    const pasos = el("ol", { clase: "a-pasos", id: "pasos" });
    A.pasos.forEach((t) => pasos.append(el("li", null, el("span", { clase: "a-marca-paso", texto: "□" }), el("span", { texto: t }))));
    const sonar = el("div", { clase: "a-sonar", "aria-hidden": "true" });
    for (let i = 0; i < 48; i++) sonar.append(el("i", { style: "animation-delay:" + (-(i * 0.09) % 1.6).toFixed(2) + "s" }));
    let k = Math.floor(Math.random() * A.consejos.length);
    const texto = el("span", { texto: A.consejos[k] }), consejo = el("p", { clase: "tt-lectura a-consejo" }, el("small", { texto: "Mientras tanto" }), texto);
    giro = setInterval(() => {
      consejo.classList.add("cambia");
      setTimeout(() => {
        k = (k + 1) % A.consejos.length;
        texto.textContent = A.consejos[k];
        consejo.classList.remove("cambia");
      }, 380);
    }, 7000);
    return el("div", { clase: "a-medio" }, ventana("Analizando", { foco: true }, el("h1", { clase: "tt-titulo a-titulo", texto: p.nombre }),
      el("p", { clase: "a-suave", id: "transcurrido" }), sonar, pasos, el("pre", { clase: "tt-terminal", id: "registro" }), consejo,
      el("div", { clase: "a-acciones" }, boton("Cancelar", null, () => cancelar(p.id)))));
  }
  function actualizarCarga(p) {
    const pr = p.progreso || {}, lista = id("pasos");
    if (!lista) return;
    Array.from(lista.children).forEach((li, i) => {
      li.className = i < pr.paso ? "hecho" : i === pr.paso ? "en-curso" : "";
      li.firstChild.textContent = i < pr.paso ? "■" : i === pr.paso ? "›" : "□";
    });
    id("transcurrido").textContent = "Lleva " + dec(pr.segundos || 0, 0) + " segundos.";
    // El registro es lo que va anotando el motor, tal cual: es una cita, no una interfaz.
    id("registro").replaceChildren(el("span", { clase: "tt-terminal__prompt", texto: "δ $ " }), "analizar comentarios\n",
      ...(pr.registro || []).map((linea) => linea.indexOf("aviso:") === 0 ? el("span", { clase: "tt-terminal__aviso", texto: linea.slice(6).trim() + "\n" }) : linea + "\n"),
      el("span", { clase: "tt-terminal__cursor", texto: " " }));
  }

  function vistaTablero(p) {
    const u = p.ultimo_analisis || {}, intento = p.ultimo_intento || {}, partes = [];
    if (intento.error) {
      partes.push(el("div", { clase: "a-error a-franja" }, el("b", { texto: "[!] " }), "El último intento de análisis no terminó (" + intento.error + "). Se muestra el análisis anterior."));
    }
    const m = el("iframe", { clase: "a-tablero", title: "Tablero de " + p.nombre });
    m.src = "/proyectos/" + p.id + "/tablero.html?app=1&p=" + p.id + "&t=" + encodeURIComponent(A.token) + "&v=" + encodeURIComponent(u.fecha || "");
    partes.push(m);
    return partes;
  }

  // --- Las acciones --------------------------------------------------------------------------------------
  async function analizar(pid) {
    try {
      reemplazar(await api("POST", "/api/proyectos/" + pid + "/analizar"));
      pintar();
    } catch (e) { avisar(e.message); }
  }
  function volverAAnalizar(p) {
    confirmar("Volver a analizar", "El análisis nuevo reemplaza al actual. Si los datos no cambiaron, el resultado es el mismo y la IA no vuelve a gastar: " +
      "sus respuestas salen de la caché del proyecto.", "Analizar", () => analizar(p.id));
  }
  async function cancelar(pid) {
    try { await api("POST", "/api/proyectos/" + pid + "/cancelar"); } catch (e) { avisar(e.message); }
  }
  async function abrirCarpeta(p) {
    try { await api("POST", "/api/proyectos/" + p.id + "/abrir-carpeta"); } catch (e) { avisar(e.message); }
  }
  function exportar(p) {
    el("a", { href: "/proyectos/" + p.id + "/exportar?t=" + encodeURIComponent(A.token), download: "" }).click();
  }
  function quitar(p) {
    confirmar("Quitar de la lista", "«" + p.nombre + "» deja de aparecer en la lista. Sus archivos quedan donde están: " + p.carpeta, "Quitar", async () => {
      try {
        await api("DELETE", "/api/proyectos/" + p.id);
        actual = null;
        await cargar();
      } catch (e) { avisar(e.message); }
    });
  }
  function vigilar() {
    const enCurso = E.proyectos.some((p) => p.estado === "analizando");
    if (enCurso && !sondeo) sondeo = setInterval(consultar, 600);
    if (!enCurso && sondeo) { clearInterval(sondeo); sondeo = null; }
  }
  async function consultar() {
    const enCurso = E.proyectos.find((p) => p.estado === "analizando");
    if (!enCurso) return vigilar();
    let p;
    try { p = await api("GET", "/api/proyectos/" + enCurso.id); } catch (e) { return; }
    reemplazar(p);
    if (p.estado === "analizando") {
      if (p.id === actual) actualizarCarga(p);
    } else pintar();
  }

  // --- Proyecto nuevo ------------------------------------------------------------------------------------
  const nombreDeCarpeta = (t) => t.trim().replace(/[^\p{L}\p{N}_\- ]+/gu, "_").replace(/^[ ._]+|[ ._]+$/g, "");
  function nuevoProyecto() {
    const s = { datos: "", base: E.sugerencias.base };
    const nombre = el("input", { type: "text", id: "np-nombre", autocomplete: "off", placeholder: "Por ejemplo: Comentarios de octubre" });
    const datos = el("code"), destino = el("code"), error = el("p", { clase: "a-falla" });
    const separador = s.base.indexOf("\\") >= 0 ? "\\" : "/";
    function refrescar() {
      datos.textContent = s.datos || "Sin elegir";
      destino.textContent = s.base + separador + (nombreDeCarpeta(nombre.value) || "…");
    }
    nombre.addEventListener("input", refrescar);
    const cuerpo = el("div", null,
      el("div", { clase: "a-campo" }, el("span", { clase: "a-rotulo", texto: "Los datos" }),
        el("div", { clase: "a-ruta" }, datos, boton("Elegir carpeta", null, async () => {
          const r = await explorar({ titulo: "¿Dónde están los datos?", inicio: s.datos || E.sugerencias.datos, set: true });
          if (!r) return;
          s.datos = r;
          if (!nombre.value.trim()) nombre.value = r.split(/[\\/]/).filter(Boolean).pop() || "";
          refrescar();
        })),
        el("p", { clase: "a-ayuda", texto: "La carpeta con los 4 archivos del set: comentarios, publicaciones, fuentes y cuentas. Se copian al proyecto; los originales no se tocan." })),
      el("div", { clase: "a-campo" }, el("label", { for: "np-nombre", texto: "El nombre del proyecto" }), nombre),
      el("div", { clase: "a-campo" }, el("span", { clase: "a-rotulo", texto: "Dónde se guarda" }),
        el("div", { clase: "a-ruta" }, destino, boton("Cambiar", null, async () => {
          const r = await explorar({ titulo: "¿Dónde se guarda el proyecto?", inicio: s.base, set: false });
          if (!r) return;
          s.base = r;
          refrescar();
        })),
        el("p", { clase: "a-ayuda", texto: "Ahí quedan los datos, el resultado del análisis y el tablero." })),
      error);
    refrescar();
    modal("Proyecto nuevo", cuerpo, (cerrar) => {
      const crear = principal("Crear proyecto", async () => {
        crear.disabled = true;
        error.textContent = "";
        try {
          const p = await api("POST", "/api/proyectos", { nombre: nombre.value, datos: s.datos, base: s.base });
          cerrar();
          E.proyectos.push(p);
          elegir(p.id);
        } catch (e) {
          error.textContent = e.message;
          crear.disabled = false;
        }
      });
      return [boton("Cancelar", null, cerrar), crear];
    });
  }

  // El explorador de carpetas. Devuelve la carpeta elegida, o null si se cancela.
  function explorar(o) {
    return new Promise((resolver) => {
      const ruta = el("div", { clase: "a-donde" }), atajos = el("div", { clase: "a-atajos" });
      const carpetas = el("ul", { clase: "a-carpetas" }), estado = el("div", { clase: "a-set" });
      let aqui = null, cerrar = null;
      const elegirEsta = principal("Elegir esta carpeta", () => { cerrar(); resolver(aqui.ruta); });
      elegirEsta.disabled = true;
      function fila(texto, alTocar) {
        const b = el("button", { type: "button", clase: "tt-fila", texto: texto });
        b.addEventListener("click", alTocar);
        return el("li", null, b);
      }
      async function ir(destino) {
        try { aqui = await api("GET", "/api/carpetas?ruta=" + encodeURIComponent(destino || "")); } catch (e) {
          estado.className = "a-set";
          estado.textContent = e.message;
          return;
        }
        ruta.textContent = aqui.ruta;
        atajos.replaceChildren(...aqui.atajos.map((a) => boton(a.nombre, null, () => ir(a.ruta))));
        carpetas.replaceChildren();
        if (aqui.padre) carpetas.append(fila("↑ subir un nivel", () => ir(aqui.padre)));
        aqui.carpetas.forEach((c, i) => carpetas.append(fila((i === aqui.carpetas.length - 1 ? "└─ " : "├─ ") + c.nombre, () => ir(c.ruta))));
        if (!aqui.carpetas.length) carpetas.append(el("li", { clase: "a-suave", style: "padding:0 1ch", texto: aqui.sin_permiso ? "No se puede leer esta carpeta." : "Acá no hay más carpetas." }));
        carpetas.scrollTop = 0;
        estado.className = "a-set";
        if (!o.set) {
          estado.textContent = "El proyecto se guarda en una carpeta nueva, dentro de esta.";
          elegirEsta.disabled = false;
        } else if (aqui.set_completo) {
          estado.className = "a-set bien";
          estado.textContent = "Esta carpeta tiene los 4 archivos del set.";
          elegirEsta.disabled = false;
        } else {
          const chequeo = el("ul", { clase: "a-chequeo" });
          Object.keys(aqui.set).forEach((n) => chequeo.append(el("li", { clase: aqui.set[n] ? "" : "falta", texto: n })));
          estado.replaceChildren("Buscá la carpeta que tenga los 4 archivos del set. En esta:", chequeo);
          elegirEsta.disabled = true;
        }
      }
      cerrar = modal(o.titulo, el("div", null, atajos, ruta, carpetas, estado), (c) => [boton("Cancelar", null, () => { c(); resolver(null); }), elegirEsta], true);
      ir(o.inicio);
    });
  }

  // --- La clave de IA y la ayuda -------------------------------------------------------------------------
  function claveIA() {
    const c = E.clave, error = el("p", { clase: "a-falla" });
    const entrada = el("input", { type: "password", id: "clave-entrada", autocomplete: "off", placeholder: "sk-ant-..." });
    const situacion = !c.configurada ? "No hay ninguna clave configurada."
      : c.origen === "variable" ? "Hay una clave configurada: viene de la variable ANTHROPIC_API_KEY del sistema."
        : "Hay una clave configurada en esta computadora.";
    const cuerpo = el("div", null, el("p", null, el("b", { texto: situacion })),
      el("p", { clase: "tt-lectura", texto: "Con una clave de Anthropic, la IA redacta los títulos de las narrativas y revisa los casos dudosos. Sin clave, el análisis corre igual. " +
        "La clave se guarda en esta computadora, fuera de los proyectos, y no se vuelve a mostrar." }),
      el("div", { clase: "a-campo" }, el("label", { for: "clave-entrada", texto: c.configurada ? "Reemplazarla por otra" : "Pegá la clave" }), entrada),
      error);
    async function pedir(metodo, cuerpoDelPedido, cerrar) {
      error.textContent = "";
      try {
        E.clave = (await api(metodo, "/api/clave", cuerpoDelPedido)).clave;
        entrada.value = "";
        cerrar();
        pintar();
      } catch (e) { error.textContent = e.message; }
    }
    modal("Clave de IA", cuerpo, (cerrar) => {
      const botones = [boton("Cerrar", null, cerrar)];
      if (c.configurada && c.origen === "archivo") botones.push(boton("Borrar la clave", null, () => pedir("DELETE", null, cerrar)));
      botones.push(principal("Guardar", () => pedir("POST", { clave: entrada.value }, cerrar)));
      return botones;
    });
  }
  function ayuda() {
    const puntos = el("ul", { clase: "a-puntos" });
    ["El Resumen responde tres preguntas en una pantalla: qué circula, quién lo empuja y desde cuándo. Cada ventana empieza con la respuesta, en una oración.",
      "Tocá cualquier cifra, fila, gráfico o tabla: a la derecha aparece su nota, con qué muestra y cómo se obtiene.",
      "Al elegir una narrativa, se resalta en todas las ventanas a la vez y en la lista de la izquierda.",
      "En las barras, apoya va en tinta llena y rechaza en gris con borde.",
      "◆ marca las cuentas con señales de coordinación. Es conducta observada en el set: no identifica bots ni autoría y no prueba intención.",
      "[!] es un aviso del análisis: algo a tener en cuenta al leer el resultado.",
      "Cada ventana cierra con su fuente: de qué archivo sale lo que muestra."].forEach((t) => puntos.append(el("li", { texto: t })));
    modal("Cómo leer el tablero", puntos, (cerrar) => [principal("Entendido", cerrar)], true);
  }

  // --- Lo que cuenta el tablero abierto, y el arranque ---------------------------------------------------
  window.addEventListener("message", (ev) => {
    const m = marco();
    if (ev.origin !== location.origin || !m || ev.source !== m.contentWindow || !ev.data) return;
    if (ev.data.delfos === "tablero") { delTablero = { narrativas: ev.data.narrativas || [], operaciones: ev.data.operaciones || [] }; pintarArbol(); }
    if (ev.data.delfos === "seleccion") { seleccion = ev.data.id || null; pintarArbol(); pintarBarras(); }
  });
  id("boton-nuevo").addEventListener("click", nuevoProyecto);
  id("tema").addEventListener("click", cambiarTema);
  ponerTema(raiz.getAttribute("data-theme") === "oscuro" ? "oscuro" : "papel");
  setInterval(() => { fetch("/api/latido").catch(() => {}); }, 20000);
  cargar().catch((e) => {
    id("centro").replaceChildren(el("div", { clase: "a-medio" }, ventana("No se pudo abrir", { foco: true }, el("p", { clase: "tt-lectura", texto: e.message }))));
  });
})();
