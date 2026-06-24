/* ─────────────────────────────────────────────────────────────────────
   JARVIS — Shared runtime v2 (vanilla JS, ES2017+)
   Public API attached to window.Jarvis :

     Jarvis.mountAtmosphere()
     Jarvis.setMode(mode)                        → "home"|"workspace"|"capacites"|"config"
     Jarvis.mountRooms({ mode, pages, activePage, onNav, onMissionControl })
     Jarvis.mountTopbar({ pageTitle, crumb, onAsk, onCmdK })
     Jarvis.openCmdK() / .closeCmdK()
     Jarvis.openMissionControl() / .closeMissionControl()
     Jarvis.registerCommands(arr)
     Jarvis.notify({ kind, text })
     Jarvis.api.get(path) / .post(path, body)
     Jarvis.fmt.num(v) / .pct(v) / .relTime(d)
     Jarvis.sparkline(data, opts)

   Depends on _shared.css being loaded first.
   ───────────────────────────────────────────────────────────────────── */

(function () {
  "use strict";

  const Jarvis = (window.Jarvis = window.Jarvis || {});

  /* ───────── Tiny DOM helpers ───────── */
  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const k in attrs) {
        const v = attrs[k];
        if (v == null || v === false) continue;
        if (k === "class")        node.className = v;
        else if (k === "html")    node.innerHTML = v;
        else if (k === "text")    node.textContent = v;
        else if (k === "style" && typeof v === "object") Object.assign(node.style, v);
        else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2).toLowerCase(), v);
        else if (k === "dataset" && typeof v === "object") for (const dk in v) node.dataset[dk] = v[dk];
        else node.setAttribute(k, v === true ? "" : v);
      }
    }
    if (children != null) {
      const arr = Array.isArray(children) ? children : [children];
      for (const c of arr) {
        if (c == null || c === false) continue;
        node.appendChild(c.nodeType ? c : document.createTextNode(String(c)));
      }
    }
    return node;
  }
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }
  Jarvis.el = el; Jarvis.$ = $; Jarvis.$$ = $$;

  /* ───────── Formatting ───────── */
  Jarvis.fmt = {
    num(v) {
      if (v == null) return "—";
      const n = Number(v);
      if (!isFinite(n)) return String(v);
      if (Math.abs(n) >= 1000) return n.toLocaleString("en-US", { maximumFractionDigits: 1 });
      return n.toString();
    },
    pct(v, digits = 1) {
      if (v == null) return "—";
      return Number(v).toFixed(digits) + "%";
    },
    relTime(date) {
      const d = date instanceof Date ? date : new Date(date);
      const s = Math.round((Date.now() - d.getTime()) / 1000);
      if (s < 60)   return "à l'instant";
      if (s < 3600) return Math.floor(s / 60) + " min";
      if (s < 86400) return Math.floor(s / 3600) + " h";
      return Math.floor(s / 86400) + " j";
    },
  };

  /* ───────── View registry ───────── */
  Jarvis.views = {
    _registry: {},
    _active: null,

    register(id, { meta, show, hide, command, gestures }) {
      this._registry[id] = { meta: meta || {}, show, hide, command, gestures: gestures || null };
    },

    list() {
      return Object.entries(this._registry).map(([id, v]) => ({ id, ...v.meta }));
    },

    activate(id, params) {
      const view = this._registry[id];
      if (!view) return;
      if (this._active && this._active !== id) this.deactivate(this._active);
      this._active = id;
      view.show(params || {});
    },

    deactivate(id) {
      const target = id || this._active;
      if (!target) return;
      const view = this._registry[target];
      if (view) view.hide();
      if (this._active === target) this._active = null;
    },

    dispatch(id, cmd, params) {
      const view = this._registry[id];
      if (view?.command) view.command(cmd, params || {});
    },
  };

  /* ───────── API wrapper ───────── */
  function authHeaders(extra) {
    const headers = Object.assign({}, extra || {});
    const token = window.JARVIS_API_TOKEN;
    if (token) headers.Authorization = "Bearer " + token;
    return headers;
  }

  Jarvis.api = {
    base: window.JARVIS_API_BASE || "",
    async get(path) {
      const r = await fetch(this.base + path, {
        credentials: "same-origin",
        headers: authHeaders(),
      });
      if (!r.ok) throw new Error("GET " + path + " → " + r.status);
      return r.json();
    },
    async post(path, body) {
      const r = await fetch(this.base + path, {
        method: "POST", credentials: "same-origin",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: body == null ? null : JSON.stringify(body),
      });
      if (!r.ok) throw new Error("POST " + path + " → " + r.status);
      return r.json();
    },
    async put(path, body) {
      const r = await fetch(this.base + path, {
        method: "PUT", credentials: "same-origin",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: body == null ? null : JSON.stringify(body),
      });
      if (!r.ok) throw new Error("PUT " + path + " → " + r.status);
      return r.json();
    },
    async patch(path, body) {
      const r = await fetch(this.base + path, {
        method: "PATCH", credentials: "same-origin",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: body == null ? null : JSON.stringify(body),
      });
      if (!r.ok) throw new Error("PATCH " + path + " → " + r.status);
      return r.json();
    },
    async delete(path) {
      const r = await fetch(this.base + path, {
        method: "DELETE",
        credentials: "same-origin",
        headers: authHeaders(),
      });
      if (!r.ok) throw new Error("DELETE " + path + " → " + r.status);
      return r.json();
    },
  };
  Jarvis.authHeaders = authHeaders;

  /* ───────── Navigation (iframe-aware) ───────── */
  Jarvis.navigate = function (url) {
    // Si on tourne dans l'iframe, déléguer au shell parent
    if (window !== window.top && window.top.Jarvis?.navigateFrame) {
      window.top.Jarvis.navigateFrame(url);
      return;
    }
    // Si le shell home a enregistré un handler iframe
    if (typeof Jarvis.navigateFrame === "function") {
      Jarvis.navigateFrame(url);
      return;
    }
    window.location.href = url;
  };

  /* ───────── Atmosphere ───────── */
  Jarvis.mountAtmosphere = function () {
    if (document.querySelector(".atmo--vignette")) return;
    document.body.appendChild(el("div", { class: "spotlight", id: "j-spotlight" }));
    document.body.appendChild(el("div", { class: "atmo atmo--aurora" }));
    document.body.appendChild(el("div", { class: "atmo atmo--vignette" }));
    document.body.appendChild(el("div", { class: "atmo atmo--grain" }));
    document.body.appendChild(el("div", { class: "mode-glow" }));

    // Spotlight mouse tracking
    document.addEventListener("mousemove", (e) => {
      const sp = document.getElementById("j-spotlight");
      if (sp) {
        sp.style.setProperty("--mx", e.clientX + "px");
        sp.style.setProperty("--my", e.clientY + "px");
      }
    }, { passive: true });
  };

  /* ───────── Mode system ───────── */
  const MODE_META = {
    home:       { chapter: "—",  num: "00", label: "JARVIS",        watermark: "" },
    workspace:  { chapter: "I",  num: "01", label: "PILOTAGE",      watermark: "Pilotage" },
    capacites:  { chapter: "II", num: "02", label: "ATELIER",       watermark: "Atelier" },
    config:     { chapter: "III",num: "03", label: "RÉGLAGES",      watermark: "Réglages" },
  };

  Jarvis.setMode = function (mode) {
    document.body.dataset.mode = mode;
    // Watermark
    let wm = document.getElementById("j-watermark");
    const meta = MODE_META[mode] || MODE_META.home;
    if (meta.watermark) {
      if (!wm) {
        wm = el("div", { id: "j-watermark", class: "mode-watermark" });
        document.body.appendChild(wm);
      }
      wm.textContent = meta.watermark;
    } else if (wm) {
      wm.textContent = "";
    }
    // Chapter indicator
    const ch = document.getElementById("j-rooms-chapter");
    if (ch && meta.chapter !== "—") {
      ch.querySelector(".rooms-num").textContent = meta.chapter;
      ch.querySelector(".rooms-lbl").textContent = meta.label;
    }
  };

  /* ───────── Scene card ───────── */
  Jarvis.showSceneCard = function (chapter, title, duration) {
    duration = duration || 900;
    let sc = document.getElementById("j-scene-card");
    if (!sc) {
      sc = el("div", { id: "j-scene-card", class: "scene-card" });
      const inner = el("div", { class: "scene-card-inner" }, [
        el("div", { class: "scene-card-chapter", id: "j-sc-chapter" }),
        el("div", { class: "scene-card-title",   id: "j-sc-title" }),
      ]);
      sc.appendChild(inner);
      document.body.appendChild(sc);
    }
    sc.querySelector("#j-sc-chapter").textContent = chapter || "";
    sc.querySelector("#j-sc-title").textContent   = title   || "";
    sc.classList.add("is-visible");
    setTimeout(() => {
      sc.style.transition = "opacity .5s ease";
      sc.style.opacity = "0";
      setTimeout(() => { sc.classList.remove("is-visible"); sc.style.opacity = ""; sc.style.transition = ""; }, 520);
    }, duration);
  };

  /* ─────────────────────────────────────────────────────────────────
     Rooms navigation (chapter indicator + subpages editorial sidebar)
  ───────────────────────────────────────────────────────────────────── */
  let _roomsOpts = null;

  Jarvis.mountRooms = function (opts) {
    _roomsOpts = opts;
    const { mode, pages, activePage, onNav } = opts;
    document.body.dataset.mode = mode;

    // ── Chapter indicator top-left ──
    let ch = document.getElementById("j-rooms-chapter");
    if (!ch) {
      ch = el("div", { id: "j-rooms-chapter", class: "rooms-chapter" });
      document.body.appendChild(ch);
    }
    const meta = MODE_META[mode] || MODE_META.home;
    ch.innerHTML = "";
    ch.appendChild(el("span", { class: "rooms-num", text: meta.chapter }));
    ch.appendChild(el("span", { class: "rooms-bar" }));
    ch.appendChild(el("span", { class: "rooms-lbl", text: meta.label }));

    // ── Watermark ──
    Jarvis.setMode(mode);

    // ── Mission Control trigger bottom-left ──
    let mc = document.getElementById("j-rooms-mc");
    if (!mc) {
      mc = el("button", { id: "j-rooms-mc", class: "rooms-mc", onclick: () => Jarvis.openMissionControl() });
      mc.appendChild(el("span", { class: "mc-dot" }));
      mc.appendChild(el("span", { text: "Mission Control" }));
      const kbd = el("span", { class: "mc-kbd" });
      kbd.appendChild(el("span", { text: "⌘" }));
      kbd.appendChild(el("span", { text: "T" }));
      mc.appendChild(kbd);
      document.body.appendChild(mc);
    }

    // ── Subpages nav (editorial sidebar or bottom pill) ──
    const isEditorial = mode !== "home";
    if (isEditorial) {
      document.body.dataset.subpages = "cocoon-wide-display";
    } else {
      delete document.body.dataset.subpages;
    }

    let nav = document.getElementById("j-rooms-pages");
    if (!nav) {
      nav = el("div", { id: "j-rooms-pages", class: "rooms-pages" });
      document.body.appendChild(nav);
    }
    nav.dataset.modeLabel = meta.label;
    nav.innerHTML = "";

    (pages || []).forEach((p, idx) => {
      const btn = el("button", {
        dataset: { active: p.id === activePage ? "true" : "false" },
        onclick: () => {
          $$(".rooms-pages button", nav).forEach(b => b.dataset.active = "false");
          btn.dataset.active = "true";
          onNav && onNav(p.id);
        },
      });
      btn.appendChild(el("span", { class: "num", text: String(idx + 1).padStart(2, "0") }));
      btn.appendChild(el("span", { class: "lbl", text: p.label }));
      nav.appendChild(btn);
    });

    // Keyboard ←/→ for subpage cycling
    document.addEventListener("keydown", _handleRoomsKey, { once: false });
  };

  function _handleRoomsKey(e) {
    if (cmdkOpen || mcOpen) return;
    if (!_roomsOpts || !_roomsOpts.pages) return;
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    if (document.activeElement && ["INPUT","TEXTAREA"].includes(document.activeElement.tagName)) return;

    const pages = _roomsOpts.pages;
    const nav = document.getElementById("j-rooms-pages");
    if (!nav) return;
    const btns = $$("button", nav);
    const curIdx = btns.findIndex(b => b.dataset.active === "true");
    let next = e.key === "ArrowRight" ? curIdx + 1 : curIdx - 1;
    next = Math.max(0, Math.min(next, pages.length - 1));
    if (next === curIdx) return;
    e.preventDefault();
    btns.forEach(b => b.dataset.active = "false");
    btns[next].dataset.active = "true";
    _roomsOpts.onNav && _roomsOpts.onNav(pages[next].id);
  }

  /* ─────────────────────────────────────────────────────────────────
     Mission Control overlay (⌘T)
  ───────────────────────────────────────────────────────────────────── */
  let mcRoot = null;
  let mcOpen = false;

  const ROOMS = [
    { mode: "home",      label: "Home",          sub: "Ambient · À l'écoute",                  href: "/",             chapter: "—",   pages: [] },
    { mode: "workspace", label: "Workspace",      sub: "Ce que tu pilotes en ce moment",         href: "/dashboard",    chapter: "I",   pages: ["Aperçu","Initiatives","Missions","Tâches","Analytics"] },
    { mode: "capacites", label: "Capacités",      sub: "Ce que Jarvis sait faire pour toi",      href: "/capabilities", chapter: "II",  pages: ["Intégrations","Skills","Routines","Ambiances","Store","Écosystème"] },
    { mode: "config",    label: "Configuration",  sub: "Tes préférences et ton coffre",           href: "/settings",     chapter: "III", pages: ["Préférences","Modèles & API","Audio & voix","Conso","Système","À propos"] },
  ];

  function ensureMissionControl() {
    if (mcRoot) return;
    mcRoot = el("div", { class: "mission-overlay is-hidden", onclick: (e) => { if (e.target === mcRoot) Jarvis.closeMissionControl(); } });

    // Header bar
    const header = el("div", { class: "mc-header" });
    header.appendChild(el("span", { class: "mc-header-title", text: "Mission Control" }));
    const hint = el("span", { class: "mc-header-hint" });
    const kbd1 = el("span", { class: "mc-hkbd" });
    kbd1.appendChild(el("span", { text: "⌘" }));
    kbd1.appendChild(el("span", { text: "T" }));
    hint.appendChild(kbd1);
    hint.appendChild(document.createTextNode(" pour fermer"));
    hint.appendChild(el("span", { class: "mc-hdot", text: " · " }));
    hint.appendChild(el("span", { class: "mc-hkbd", text: "ESC" }));
    header.appendChild(hint);
    header.appendChild(el("button", { class: "mc-close", onclick: () => Jarvis.closeMissionControl(), text: "×" }));
    mcRoot.appendChild(header);

    const grid = el("div", { class: "mission-grid" });
    ROOMS.forEach(r => {
      const card = el("button", {
        class: "mission-card",
        dataset: { mode: r.mode },
        onclick: () => { Jarvis.closeMissionControl(); Jarvis.navigate(r.href); },
      });
      const eyebrow = el("div", { class: "mc-card-eyebrow" });
      eyebrow.appendChild(el("span", { class: "mc-card-num", text: r.chapter }));
      if (r.pages.length) eyebrow.appendChild(el("span", { text: r.pages.length + " SECTIONS" }));
      card.appendChild(eyebrow);
      card.appendChild(el("div", { class: "mc-card-title", text: r.label }));
      card.appendChild(el("div", { class: "mc-card-sub",   text: r.sub }));
      if (r.pages.length) {
        const pagesEl = el("div", { class: "mc-card-pages" });
        r.pages.forEach((p, i) => {
          pagesEl.appendChild(el("span", { class: "mc-card-page" }, [
            el("span", { class: "mc-pg-num", text: String(i + 1).padStart(2, "0") }),
            el("span", { class: "mc-pg-lbl", text: p }),
          ]));
        });
        card.appendChild(pagesEl);
      }
      grid.appendChild(card);
    });
    mcRoot.appendChild(grid);
    document.body.appendChild(mcRoot);
  }

  Jarvis.openMissionControl = function () {
    ensureMissionControl();
    mcOpen = true;
    mcRoot.classList.remove("is-hidden");
  };
  Jarvis.closeMissionControl = function () {
    if (!mcRoot) return;
    mcOpen = false;
    mcRoot.classList.add("is-hidden");
  };

  /* ───────── Legacy sidebar (still used on pages without rooms nav) ─────────
     opts: sections, activeId, onNav, footer
  */
  Jarvis.mountSidebar = function (opts) {
    const root = document.getElementById("sidebar") || el("aside", { id: "sidebar" });
    if (!root.parentNode) document.querySelector(".app").prepend(root);
    root.className = "sidebar";
    root.innerHTML = "";

    root.appendChild(el("div", { class: "sb-brand" }, [
      brandMark(),
      el("div", { class: "sb-brand-text" }, [
        el("span", { class: "sb-brand-name", text: "Jarvis" }),
        el("span", { class: "sb-brand-status", text: "Online · v4.2" }),
      ]),
    ]));

    (opts.sections || []).forEach(sec => {
      root.appendChild(el("div", { class: "sb-section-eyebrow" }, [
        el("span", { text: sec.label }),
        sec.right ? el("span", { text: sec.right, style: { color: "var(--fg-2)" } }) : null,
      ]));
      const nav = el("div", { class: "sb-nav" });
      sec.items.forEach(it => {
        const b = el("button", {
          class: "sb-item" + (it.id === opts.activeId ? " is-on" : ""),
          dataset: { id: it.id },
          onclick: () => opts.onNav && opts.onNav(it.id),
        }, [
          el("span", { class: "sb-dot" }),
          el("span", { text: it.label }),
          it.meta ? el("span", { class: "sb-meta", text: it.meta }) : el("span"),
        ]);
        nav.appendChild(b);
      });
      root.appendChild(nav);
    });

    if (opts.footer) {
      const f = el("div", { class: "sb-foot" });
      f.appendChild(el("div", { class: "sb-foot-row" }, [
        el("span", { text: "Spend · 24h" }),
        el("span", { text: opts.footer.spend || "—" }),
      ]));
      f.appendChild(el("div", { class: "sb-foot-row" }, [
        el("span", { text: "CPU" }),
        el("span", { text: opts.footer.cpu || "—" }),
      ]));
      const bar = el("div", { class: "sb-foot-bar" });
      bar.appendChild(el("div", { style: { width: ((opts.footer.ramPct || 0) * 100) + "%" } }));
      f.appendChild(bar);
      root.appendChild(f);
    }
    return root;
  };

  function brandMark() {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("width", "26"); svg.setAttribute("height", "26"); svg.setAttribute("viewBox", "0 0 26 26");
    const c = document.createElementNS(ns, "circle");
    c.setAttribute("cx", "13"); c.setAttribute("cy", "13"); c.setAttribute("r", "11");
    c.setAttribute("fill", "none"); c.setAttribute("stroke", "var(--accent)"); c.setAttribute("stroke-width", "1"); c.setAttribute("opacity", "0.8");
    const c2 = document.createElementNS(ns, "circle");
    c2.setAttribute("cx", "13"); c2.setAttribute("cy", "13"); c2.setAttribute("r", "5");
    c2.setAttribute("fill", "var(--accent)"); c2.setAttribute("opacity", "0.18");
    const c3 = document.createElementNS(ns, "circle");
    c3.setAttribute("cx", "13"); c3.setAttribute("cy", "13"); c3.setAttribute("r", "1.6"); c3.setAttribute("fill", "var(--accent)");
    svg.appendChild(c); svg.appendChild(c2); svg.appendChild(c3);
    return svg;
  }

  /* ───────── Topbar ───────── */
  Jarvis.mountTopbar = function (opts) {
    const root = document.getElementById("topbar") || el("header", { id: "topbar", class: "topbar" });
    root.className = "topbar";
    root.innerHTML = "";

    const t = new Date();
    const tStr = String(t.getHours()).padStart(2, "0") + ":" + String(t.getMinutes()).padStart(2, "0");

    root.appendChild(el("div", { class: "topbar-l" }, [
      el("span", { class: "topbar-page-title", text: opts.pageTitle || "Dashboard" }),
      el("span", { class: "topbar-crumb",      text: opts.crumb || "/ control" }),
    ]));

    root.appendChild(el("div", { class: "topbar-c" }, [
      el("span", { class: "dot" }),
      el("span", { text: "Online" }),
      el("span", { class: "sep" }),
      el("span", { text: tStr }),
      el("span", { class: "sep" }),
      el("span", { text: "Paris" }),
    ]));

    root.appendChild(el("div", { class: "topbar-r" }, [
      el("button", { class: "tb-btn", onclick: () => Jarvis.openCmdK() }, [
        el("span", { text: "Recherche" }),
        el("span", { class: "kbd", text: "⌘K" }),
      ]),
      el("button", { class: "tb-btn", onclick: () => opts.onAsk && opts.onAsk() }, [
        el("span", { text: "Ask Jarvis" }),
      ]),
    ]));

    return root;
  };

  /* ─────────────────────────────────────────────────────────────────
     Command palette (⌘K)
  ───────────────────────────────────────────────────────────────────── */
  let cmdkRoot = null, cmdkInput = null, cmdkList = null;
  let cmdkCommands = [], cmdkSelected = 0, cmdkOpen = false;

  // Seed with room navigation commands
  const _navCmds = ROOMS.map(r => ({
    kind: "nav", id: "goto-" + r.mode, group: "Aller à",
    title: r.label, sub: r.href, glyph: "→",
    run: () => { Jarvis.navigate(r.href); },
  }));
  cmdkCommands = _navCmds;

  Jarvis.registerCommands = function (cmds) {
    const ids = new Set(cmdkCommands.map(c => c.id));
    cmds.forEach(c => { if (!ids.has(c.id)) cmdkCommands.push(c); });
  };

  function ensureCmdK() {
    if (cmdkRoot) return;
    cmdkRoot = el("div", { class: "cmdk-back is-hidden", onclick: (e) => { if (e.target === cmdkRoot) Jarvis.closeCmdK(); } });
    const box = el("div", { class: "cmdk" });
    const inputWrap = el("div", { class: "cmdk-input-wrap" });
    const prefix = el("span", { class: "cmdk-prefix", text: ">", style: { display: "none" } });
    cmdkInput = el("input", {
      class: "cmdk-input",
      placeholder: "Cherche · navigue · > commandes",
      autocomplete: "off",
      oninput: (e) => {
        const v = e.target.value;
        const slash = v.startsWith(">");
        prefix.style.display = slash ? "block" : "none";
        cmdkInput.classList.toggle("has-prefix", slash);
        cmdkSelected = 0; renderCmdK(v);
      },
      onkeydown: (e) => {
        if (e.key === "Escape")    { e.preventDefault(); Jarvis.closeCmdK(); }
        if (e.key === "ArrowDown") { e.preventDefault(); cmdkSelected = Math.min(cmdkSelected + 1, currentResults().length - 1); renderCmdK(cmdkInput.value, true); }
        if (e.key === "ArrowUp")   { e.preventDefault(); cmdkSelected = Math.max(cmdkSelected - 1, 0); renderCmdK(cmdkInput.value, true); }
        if (e.key === "Enter")     { e.preventDefault(); execSelected(); }
      },
    });
    inputWrap.appendChild(prefix); inputWrap.appendChild(cmdkInput);
    cmdkList = el("div", { class: "cmdk-list" });
    const foot = el("div", { class: "cmdk-foot" }, [
      el("span", { text: "↑↓ naviguer · ↵ exécuter · esc fermer" }),
      el("span", { text: "> pour commandes" }),
    ]);
    box.appendChild(inputWrap); box.appendChild(cmdkList); box.appendChild(foot);
    cmdkRoot.appendChild(box);
    document.body.appendChild(cmdkRoot);
  }

  Jarvis.openCmdK = function () {
    ensureCmdK();
    cmdkOpen = true;
    cmdkRoot.classList.remove("is-hidden");
    cmdkInput.value = ""; cmdkSelected = 0;
    renderCmdK("");
    setTimeout(() => cmdkInput.focus(), 30);
  };
  Jarvis.closeCmdK = function () {
    if (!cmdkRoot) return;
    cmdkOpen = false;
    cmdkRoot.classList.add("is-hidden");
  };

  function currentResults() {
    const v = cmdkInput.value.trim();
    if (v.startsWith(">")) {
      const q = v.slice(1).trim().toLowerCase();
      if (q.startsWith("ask ")) {
        const p = q.slice(4);
        return [{ kind: "ask", id: "ask", title: 'Demander : "' + p + '"', glyph: "›", group: "Faire", run: () => _askJarvis(p) }];
      }
      const slash = cmdkCommands.filter(c => c.kind === "slash");
      if (!q) return slash;
      return slash.filter(c => c.title.toLowerCase().includes(q));
    }
    const q = v.toLowerCase();
    const all = cmdkCommands.filter(c => c.kind !== "slash");
    if (!q) return all;
    return all.filter(c => (c.title + " " + (c.sub || "")).toLowerCase().includes(q));
  }

  function renderCmdK(_v, keepFocus) {
    cmdkList.innerHTML = "";
    const items = currentResults();
    if (!items.length) {
      cmdkList.appendChild(el("div", { class: "cmdk-empty", text: "Aucune commande" }));
      return;
    }
    const groups = {};
    items.forEach(it => { const g = it.group || "Navigation"; (groups[g] = groups[g] || []).push(it); });
    let idx = 0;
    Object.keys(groups).forEach(g => {
      cmdkList.appendChild(el("div", { class: "cmdk-group-lbl", text: g }));
      groups[g].forEach(it => {
        const i = idx++;
        const row = el("div", {
          class: "cmdk-item" + (i === cmdkSelected ? " is-on" : ""),
          onclick: () => { cmdkSelected = i; execSelected(); },
          onmousemove: () => { if (cmdkSelected !== i) { cmdkSelected = i; renderCmdK(cmdkInput.value, true); } },
        }, [
          el("span", { class: "ck-glyph", text: it.glyph || "·" }),
          el("div", {}, [
            el("span", { text: it.title }),
            it.sub ? el("span", { class: "ck-sub", text: it.sub }) : null,
          ]),
          it.kbd ? el("span", { class: "ck-kbd" }, it.kbd.split("+").map(k => el("span", { text: k }))) : el("span"),
        ]);
        cmdkList.appendChild(row);
      });
    });
    if (keepFocus) cmdkInput.focus();
  }

  function execSelected() {
    const it = currentResults()[cmdkSelected];
    if (!it) return;
    Jarvis.closeCmdK();
    if (typeof it.run === "function") it.run();
  }

  async function _askJarvis(prompt) {
    Jarvis.notify({ kind: "info", text: "Jarvis · réflexion…" });
    try {
      const r = await Jarvis.api.post("/api/agent/ask", { prompt });
      Jarvis.notify({ kind: "success", text: (r.answer || r.text || "").slice(0, 240) });
    } catch (err) {
      Jarvis.notify({ kind: "error", text: "Échec : " + err.message });
    }
  }

  /* ───────── Global keyboard shortcuts ───────── */
  document.addEventListener("keydown", (e) => {
    // ⌘K — palette
    if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      cmdkOpen ? Jarvis.closeCmdK() : Jarvis.openCmdK();
    }
    // ⌘T — Mission Control
    if ((e.metaKey || e.ctrlKey) && (e.key === "t" || e.key === "T")) {
      e.preventDefault();
      mcOpen ? Jarvis.closeMissionControl() : Jarvis.openMissionControl();
    }
    // Escape
    if (e.key === "Escape") {
      if (cmdkOpen) Jarvis.closeCmdK();
      if (mcOpen)   Jarvis.closeMissionControl();
    }
  });

  /* ───────── Inspector mode (Alt) ───────── */
  let inspectHint = null;
  function setInspect(on) {
    document.documentElement.classList.toggle("inspect", on);
    if (on && !inspectHint) {
      inspectHint = el("div", { class: "inspect-hint" }, [
        el("span", { class: "dot" }), el("span", { text: "INSPECTOR · ⌥" }),
      ]);
      document.body.appendChild(inspectHint);
    } else if (!on && inspectHint) {
      inspectHint.remove(); inspectHint = null;
    }
  }
  document.addEventListener("keydown", (e) => { if (e.key === "Alt") setInspect(true); });
  document.addEventListener("keyup",   (e) => { if (e.key === "Alt") setInspect(false); });
  window.addEventListener("blur", () => setInspect(false));

  /* ───────── Notification ribbon ───────── */
  let notifStack = null;
  Jarvis.notify = function ({ kind = "info", text = "" }) {
    if (!notifStack) {
      notifStack = el("div", { class: "notif-stack" });
      document.body.appendChild(notifStack);
    }
    const cls = "notif" + (kind && kind !== "info" ? " notif--" + kind : "");
    const node = el("div", { class: cls }, [
      el("span", { class: "notif-mark" }),
      el("div", { class: "notif-text", text }),
      el("span", { class: "notif-time", text: "MAINT." }),
    ]);
    notifStack.appendChild(node);
    setTimeout(() => node.remove(), 4400);
    const sb = document.querySelector(".sidebar");
    if (sb) {
      const breath = el("div", { class: "sb-breath" });
      sb.appendChild(breath);
      setTimeout(() => breath.remove(), 1700);
    }
  };

  /* ───────── Sparkline ───────── */
  Jarvis.sparkline = function (data, opts) {
    opts = opts || {};
    const w = opts.width || 180, h = opts.height || 28;
    const color = opts.color || "var(--accent)";
    if (!data || !data.length) return el("svg", { width: w, height: h });
    const min = Math.min(...data), max = Math.max(...data), range = max - min || 1;
    const pts = data.map((v, i) => [
      (i / (data.length - 1)) * w,
      h - ((v - min) / range) * h * 0.85 - 2,
    ]);
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("width", w); svg.setAttribute("height", h);
    svg.setAttribute("viewBox", "0 0 " + w + " " + h);
    const path = document.createElementNS(ns, "path");
    path.setAttribute("d", pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" "));
    path.setAttribute("fill", "none"); path.setAttribute("stroke", color);
    path.setAttribute("stroke-width", "1.4"); path.setAttribute("stroke-linecap", "round");
    svg.appendChild(path);
    const last = pts[pts.length - 1];
    const dot = document.createElementNS(ns, "circle");
    dot.setAttribute("cx", last[0]); dot.setAttribute("cy", last[1]);
    dot.setAttribute("r", "2"); dot.setAttribute("fill", color);
    svg.appendChild(dot);
    return svg;
  };

  /* ───────── Bottom nav (legacy, conservé pour compat) ───────── */
  Jarvis.mountBottomNav = function (opts) {
    const existing = document.getElementById("j-bottom-nav");
    if (existing) existing.remove();
    // No-op in v2 — navigation handled by rooms system
  };
})();
