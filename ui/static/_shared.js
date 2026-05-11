/* ─────────────────────────────────────────────────────────────────────
   JARVIS V4 — Shared runtime (vanilla JS, ES2017+)
   Public API attached to window.Jarvis :

     Jarvis.mountAtmosphere()                   → injects vignette/grain/aurora
     Jarvis.mountSidebar({ sections, activeId, onNav, footer })
     Jarvis.mountTopbar({ pageTitle, crumb, onAsk, onCmdK })
     Jarvis.openCmdK()                          → show command palette
     Jarvis.closeCmdK()
     Jarvis.registerCommands(arr)               → add commands (slash + nav)
     Jarvis.mountBottomNav({ active })          → persistent 5-icon nav (active: "sphere"|"control"|"globe"|"intel"|"system")
     Jarvis.notify({ kind, text })              → kind: info|success|warn|error
     Jarvis.api.get(path) / .post(path, body)   → fetch wrappers w/ JSON
     Jarvis.fmt.num(v) / .pct(v) / .relTime(d)

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

  /* ───────── API wrapper (use existing FastAPI/Flask backend) ───────── */
  Jarvis.api = {
    base: window.JARVIS_API_BASE || "",
    async get(path) {
      const r = await fetch(this.base + path, { credentials: "same-origin" });
      if (!r.ok) throw new Error("GET " + path + " → " + r.status);
      return r.json();
    },
    async post(path, body) {
      const r = await fetch(this.base + path, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: body == null ? null : JSON.stringify(body),
      });
      if (!r.ok) throw new Error("POST " + path + " → " + r.status);
      return r.json();
    },
    async put(path, body) {
      const r = await fetch(this.base + path, {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: body == null ? null : JSON.stringify(body),
      });
      if (!r.ok) throw new Error("PUT " + path + " → " + r.status);
      return r.json();
    },
    async delete(path) {
      const r = await fetch(this.base + path, {
        method: "DELETE",
        credentials: "same-origin",
      });
      if (!r.ok) throw new Error("DELETE " + path + " → " + r.status);
      return r.json();
    },
  };

  /* ───────── Atmosphere (vignette + grain + aurora) ───────── */
  Jarvis.mountAtmosphere = function () {
    if (document.querySelector(".atmo--vignette")) return;
    document.body.appendChild(el("div", { class: "atmo atmo--aurora" }));
    document.body.appendChild(el("div", { class: "atmo atmo--vignette" }));
    document.body.appendChild(el("div", { class: "atmo atmo--grain" }));
  };

  /* ───────── Sidebar ─────────
     opts:
       sections: [{ label, items: [{ id, label, meta, dot? }] }]
       activeId, onNav(id)
       footer: { spend: "$X.YZ", cpu: "14%", ramPct: 0.42 }   (optional)
  */
  Jarvis.mountSidebar = function (opts) {
    const root = document.getElementById("sidebar") || el("aside", { id: "sidebar" });
    if (!root.parentNode) document.querySelector(".app").prepend(root);
    root.className = "sidebar";
    root.innerHTML = "";

    // Brand
    root.appendChild(el("div", { class: "sb-brand" }, [
      brandMark(),
      el("div", { class: "sb-brand-text" }, [
        el("span", { class: "sb-brand-name", text: "Jarvis" }),
        el("span", { class: "sb-brand-status", text: "Online · v4.2" }),
      ]),
    ]));

    // Sections
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

    // Footer (system pulse)
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
      const fill = el("div", { style: { width: ((opts.footer.ramPct || 0) * 100) + "%" } });
      bar.appendChild(fill); f.appendChild(bar);
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
    c.setAttribute("fill", "none"); c.setAttribute("stroke", "var(--accent)"); c.setAttribute("stroke-width", "1");
    c.setAttribute("opacity", "0.8");
    const c2 = document.createElementNS(ns, "circle");
    c2.setAttribute("cx", "13"); c2.setAttribute("cy", "13"); c2.setAttribute("r", "5");
    c2.setAttribute("fill", "var(--accent)"); c2.setAttribute("opacity", "0.18");
    const c3 = document.createElementNS(ns, "circle");
    c3.setAttribute("cx", "13"); c3.setAttribute("cy", "13"); c3.setAttribute("r", "1.6");
    c3.setAttribute("fill", "var(--accent)");
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
      el("span", { class: "topbar-crumb", text: opts.crumb || "/ control" }),
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
      el("button", {
        class: "tb-btn",
        onclick: () => Jarvis.openCmdK(),
      }, [
        el("span", { text: "Search" }),
        el("span", { class: "kbd", text: "⌘K" }),
      ]),
      el("button", {
        class: "tb-btn",
        onclick: () => opts.onAsk && opts.onAsk(),
      }, [
        el("span", { text: "Ask Jarvis" }),
      ]),
    ]));

    return root;
  };

  /* ───────── Command palette + slash commands ───────── */
  let cmdkRoot = null;
  let cmdkInput = null;
  let cmdkList = null;
  let cmdkPrefix = null;
  let cmdkCommands = [];
  let cmdkSelected = 0;
  let cmdkOpen = false;

  Jarvis.registerCommands = function (cmds) {
    cmdkCommands = cmdkCommands.concat(cmds);
  };

  function ensureCmdK() {
    if (cmdkRoot) return;
    cmdkRoot = el("div", { class: "cmdk-back is-hidden", onclick: (e) => { if (e.target === cmdkRoot) Jarvis.closeCmdK(); } });
    const box = el("div", { class: "cmdk" });
    const inputWrap = el("div", { class: "cmdk-input-wrap" });
    cmdkPrefix = el("span", { class: "cmdk-prefix", text: ">", style: { display: "none" } });
    cmdkInput = el("input", {
      class: "cmdk-input",
      placeholder: "Cherche · navigue · tape > pour les commandes",
      autocomplete: "off",
      oninput: handleCmdKInput,
      onkeydown: handleCmdKKey,
    });
    inputWrap.appendChild(cmdkPrefix); inputWrap.appendChild(cmdkInput);
    cmdkList = el("div", { class: "cmdk-list" });
    const foot = el("div", { class: "cmdk-foot" }, [
      el("span", { text: "↑↓ naviguer · ↵ exécuter · esc fermer" }),
      el("span", { text: "tape > pour slash commands" }),
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
    cmdkPrefix.style.display = "none";
    cmdkInput.classList.remove("has-prefix");
    renderCmdK("");
    setTimeout(() => cmdkInput.focus(), 30);
  };
  Jarvis.closeCmdK = function () {
    if (!cmdkRoot) return;
    cmdkOpen = false;
    cmdkRoot.classList.add("is-hidden");
  };

  function handleCmdKInput(e) {
    const v = e.target.value;
    const slash = v.startsWith(">");
    cmdkPrefix.style.display = slash ? "block" : "none";
    cmdkInput.classList.toggle("has-prefix", slash);
    cmdkSelected = 0;
    renderCmdK(v);
  }
  function handleCmdKKey(e) {
    if (e.key === "Escape")   { e.preventDefault(); Jarvis.closeCmdK(); return; }
    if (e.key === "ArrowDown"){ e.preventDefault(); cmdkSelected = Math.min(cmdkSelected + 1, currentResults().length - 1); renderCmdK(cmdkInput.value, true); return; }
    if (e.key === "ArrowUp")  { e.preventDefault(); cmdkSelected = Math.max(cmdkSelected - 1, 0); renderCmdK(cmdkInput.value, true); return; }
    if (e.key === "Enter")    { e.preventDefault(); execSelected(); return; }
  }

  function currentResults() {
    const v = cmdkInput.value.trim();
    if (v.startsWith(">")) {
      const q = v.slice(1).trim().toLowerCase();
      const slash = cmdkCommands.filter(c => c.kind === "slash");
      if (!q) return slash;
      // ">ask hello world" → expose Ask Jarvis pseudo-command
      if (q.startsWith("ask ")) {
        const prompt = q.slice(4);
        return [{ kind: "ask", id: "ask-jarvis", title: 'Demander à Jarvis : "' + prompt + '"', sub: "envoie au LLM", glyph: "›", run: () => askJarvis(prompt) }];
      }
      return slash.filter(c => c.title.toLowerCase().includes(q) || (c.id || "").includes(q));
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
    // Group by section
    const groups = {};
    items.forEach(it => {
      const g = it.group || (it.kind === "slash" ? "Commandes" : "Navigation");
      (groups[g] = groups[g] || []).push(it);
    });
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
          el("span", { class: "ck-glyph", text: it.glyph || (it.kind === "slash" ? ">" : "·") }),
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
    const items = currentResults();
    const it = items[cmdkSelected];
    if (!it) return;
    Jarvis.closeCmdK();
    if (typeof it.run === "function") it.run();
  }

  async function askJarvis(prompt) {
    Jarvis.notify({ kind: "info", text: "Jarvis · réflexion en cours…" });
    try {
      // Try the bundled claude.complete helper first (artifact mode)
      let answer;
      if (window.claude && window.claude.complete) {
        answer = await window.claude.complete(prompt);
      } else {
        // Otherwise post to backend agent endpoint (TODO: confirm path)
        const r = await Jarvis.api.post("/api/agent/ask", { prompt });
        answer = r.answer || r.text || JSON.stringify(r);
      }
      Jarvis.notify({ kind: "success", text: answer.slice(0, 240) });
    } catch (err) {
      Jarvis.notify({ kind: "error", text: "Échec : " + err.message });
    }
  }

  /* Global ⌘K + slash shortcut binding */
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      cmdkOpen ? Jarvis.closeCmdK() : Jarvis.openCmdK();
    }
  });

  /* ───────── Inspector mode (hold Alt) ───────── */
  let inspectHint = null;
  function setInspect(on) {
    document.documentElement.classList.toggle("inspect", on);
    if (on && !inspectHint) {
      inspectHint = el("div", { class: "inspect-hint" }, [
        el("span", { class: "dot" }),
        el("span", { text: "INSPECTOR · ⌥" }),
      ]);
      document.body.appendChild(inspectHint);
    } else if (!on && inspectHint) {
      inspectHint.remove(); inspectHint = null;
    }
  }
  document.addEventListener("keydown", (e) => { if (e.key === "Alt" || e.altKey) setInspect(true); });
  document.addEventListener("keyup",   (e) => { if (e.key === "Alt" || !e.altKey) setInspect(false); });
  window.addEventListener("blur", () => setInspect(false));

  /* ───────── Notification ribbon + sidebar breath ───────── */
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

    // Sidebar breath
    const sb = document.querySelector(".sidebar");
    if (sb) {
      const breath = el("div", { class: "sb-breath" });
      sb.appendChild(breath);
      setTimeout(() => breath.remove(), 1700);
    }
  };

  /* ───────── Sparkline (SVG, used by KPIs and sidebar) ───────── */
  Jarvis.sparkline = function (data, opts) {
    opts = opts || {};
    const w = opts.width || 180, h = opts.height || 28;
    const color = opts.color || "var(--accent)";
    if (!data || !data.length) return el("svg", { width: w, height: h });
    const min = Math.min.apply(null, data), max = Math.max.apply(null, data);
    const range = max - min || 1;
    const pts = data.map((v, i) => {
      const x = (i / (data.length - 1)) * w;
      const y = h - ((v - min) / range) * h * 0.85 - 2;
      return [x, y];
    });
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("width", w); svg.setAttribute("height", h); svg.setAttribute("viewBox", "0 0 " + w + " " + h);
    const path = document.createElementNS(ns, "path");
    path.setAttribute("d", pts.map((p, i) => (i ? "L" : "M") + p[0] + " " + p[1]).join(" "));
    path.setAttribute("fill", "none"); path.setAttribute("stroke", color);
    path.setAttribute("stroke-width", "1.4"); path.setAttribute("stroke-linecap", "round");
    svg.appendChild(path);
    const last = pts[pts.length - 1];
    const dot = document.createElementNS(ns, "circle");
    dot.setAttribute("cx", last[0]); dot.setAttribute("cy", last[1]); dot.setAttribute("r", "2");
    dot.setAttribute("fill", color);
    svg.appendChild(dot);
    return svg;
  };

  /* ───────── Bottom nav (persistent across pages) ───────── */
  Jarvis.mountBottomNav = function (opts) {
    opts = opts || {};
    const active = opts.active; // "sphere"|"control"|"globe"|"intel"|"system"

    const existing = document.getElementById("j-bottom-nav");
    if (existing) existing.remove();

    const nav = el("div", { id: "j-bottom-nav" });

    const BTNS = [
      { key: "sphere",  title: "Jarvis",        href: "/",          svg: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="1.8" fill="currentColor" stroke="none"/><circle cx="7.5" cy="9" r="1" fill="currentColor" stroke="none"/><circle cx="16.5" cy="9" r="1" fill="currentColor" stroke="none"/><circle cx="7.5" cy="15" r="1" fill="currentColor" stroke="none"/><circle cx="16.5" cy="15" r="1" fill="currentColor" stroke="none"/></svg>' },
      { key: "control", title: "Control",       href: "/dashboard", svg: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>' },
      { key: "globe",   title: "Globe mondial", href: "/",          svg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>' },
      { key: "intel",   title: "Intel Monde",   href: "/",          svg: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M13 2L4.09 13H11L10 22L19.91 11H13V2Z"/></svg>' },
      { key: "system",  title: "Système",       href: "/settings",  svg: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>' },
    ];

    BTNS.forEach(function (cfg) {
      const b = document.createElement("button");
      b.className = "jnav-btn" + (cfg.key === active ? " active" : "");
      b.title = cfg.title;
      b.innerHTML = cfg.svg;
      b.addEventListener("click", function () { window.location.href = cfg.href; });
      nav.appendChild(b);
    });

    document.body.appendChild(nav);
    return nav;
  };
})();
