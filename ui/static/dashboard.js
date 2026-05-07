/* dashboard.js — Control page (vanilla, branche sur backend Jarvis)
 *
 * Données mockées pour le port initial. Les TODOs marquent où brancher
 * les vrais endpoints (api/analytics.py, api/admin.py, agent runtime).
 */
(function () {
  "use strict";
  const J = window.Jarvis, el = J.el;

  /* ───────── Mocks (replace with API calls) ───────── */
  const MOCK_INITIATIVES = [
    { id: "INI·041", title: "Renouveler abonnement Cloudflare avant expiration", type: "Action",    priority: "high", source: "Email · billing@cf",     due: "2j" },
    { id: "INI·040", title: "Répondre à 3 emails marqués important",             type: "Triage",    priority: "med",  source: "Inbox · prioritaire",    due: "Auj." },
    { id: "INI·039", title: "Optimiser la pipeline YouTube (−14% sur 7 shorts)", type: "Stratégie", priority: "med",  source: "Analytics drift",        due: "Cette sem." },
    { id: "INI·038", title: "Bloquer 90 min pour la review trimestrielle Q2",    type: "Calendrier",priority: "low",  source: "Pattern hebdo",          due: "Demain" },
    { id: "INI·037", title: "Tester Sonnet 4.5 sur la pipeline transcription",   type: "R&D",       priority: "low",  source: "Anthropic update",       due: "—" },
    { id: "INI·036", title: "Fermer 7 onglets idle Chrome",                       type: "Hygiène",   priority: "low",  source: "Detection auto",         due: "—" },
  ];
  const MOCK_KPIS = [
    { lbl: "Vues 30j",        val: 248.3, unit: "K",    delta: "+12.4%", dir: "up", spark: [180,195,188,210,215,230,248] },
    { lbl: "Subs YouTube",    val: 41.2,  unit: "K",    delta: "+1.8%",  dir: "up", spark: [39.8,40.1,40.4,40.6,40.9,41.0,41.2] },
    { lbl: "Requêtes Jarvis", val: 18742, unit: "/sem", delta: "+24%",   dir: "up", spark: [12000,13500,14800,15600,16800,17400,18742] },
    { lbl: "Latence p95",     val: 312,   unit: "ms",   delta: "−8%",    dir: "up", spark: [380,360,350,340,330,320,312] },
  ];
  const MOCK_SOURCES = [
    { name: "YouTube",     glyph: "Y", w: 0.82, num: "248.3K", delta: "+12.4%", dir: "up",   color: "rgba(220,232,255,.85)" },
    { name: "Twitter / X", glyph: "𝕏", w: 0.61, num: "184.0K", delta: "+6.1%",  dir: "up",   color: "rgba(74,158,255,.78)" },
    { name: "Email",       glyph: "@", w: 0.42, num: "1,284",  delta: "+3.0%",  dir: "up",   color: "rgba(184,150,62,.78)" },
    { name: "Substack",    glyph: "S", w: 0.28, num: "12.8K",  delta: "−1.4%",  dir: "down", color: "rgba(220,232,255,.55)" },
    { name: "Jarvis",      glyph: "J", w: 0.94, num: "18,742", delta: "+24%",   dir: "up",   color: "rgba(54,211,153,.78)" },
  ];
  const MOCK_TOP = [
    { rank: "01", title: "L'IA personnelle ne ressemble pas à ChatGPT", views: "184K", chg: "+8.2%" },
    { rank: "02", title: "J'ai construit mon propre Jarvis (12 mois)",  views: "142K", chg: "+4.1%" },
    { rank: "03", title: "Pourquoi vos prompts sont nuls",              views: "96.4K", chg: "+12%" },
    { rank: "04", title: "Stack 2026 : ce que j'utilise vraiment",      views: "78.1K", chg: "−2.3%" },
  ];

  /* ───────── Data loaders ───────── */
  async function loadInitiatives() {
    // SHAPE EXPECTED: [{ id, title, type, priority: "high"|"med"|"low", source, due }]
    // Backend GET /api/initiatives → [{ id, type, title, context, priority, created_at, … }]
    // priority: "haute"→"high", "moyen"→"med", "basse"→"low" (also accepts English forms)
    try {
      const raw = await J.api.get("/api/initiatives");
      const pMap = { haute: "high", moyen: "med", basse: "low", high: "high", med: "med", low: "low" };
      return raw.map(i => ({
        id:       i.id,
        title:    i.title,
        type:     i.type || "Action",
        priority: pMap[String(i.priority || "").toLowerCase()] || "low",
        source:   i.context ? i.context.slice(0, 40) : "Jarvis",
        due:      i.created_at ? J.fmt.relTime(i.created_at) : "—",
      }));
    } catch (_) { return MOCK_INITIATIVES; }
  }

  async function loadMissions() {
    try {
      const raw = await J.api.get("/api/projects");
      const sMap = { running: "run", planning: "run", waiting: "wait", queued: "queue", queue: "queue" };
      const missions = raw
        .filter(p => p.status !== "done" && p.status !== "failed" && p.status !== "killed")
        .map(p => ({
          id:     p.id ? p.id.slice(0, 6).toUpperCase() : "?",
          status: sMap[p.status] || "run",
          title:  p.title || p.instruction || "Mission sans titre",
          sub:    "agent · " + (p.status || "running"),
          prog:   p.steps_total > 0 ? p.steps_done / p.steps_total : 0,
          cur:    p.steps_done || null,
          tot:    p.steps_total || null,
          eta:    "—",
        }));
      const doneCount = raw.filter(p => p.status === "done").length;
      return { missions, doneCount };
    } catch (_) { return { missions: [], doneCount: 0 }; }
  }

  async function loadAnalytics() {
    // SHAPE EXPECTED: { kpis: [{lbl,val,unit,delta,dir,spark}], sources: [...], topVideos: [...] }
    // Backend GET /api/analytics/jarvis → { sessions, missions, total_tokens, total_cost_usd, top_model }
    //         GET /api/analytics/youtube → { configured, subscribers, total_views, recent_videos, top_video }
    // sources array: TODO - no multi-source endpoint yet, keeps mock
    try {
      const [jarvis, yt] = await Promise.allSettled([
        J.api.get("/api/analytics/jarvis?days=30"),
        J.api.get("/api/analytics/youtube?days=7"),
      ]);
      const j = jarvis.status === "fulfilled" ? jarvis.value : null;
      const y = yt.status === "fulfilled" ? yt.value : null;

      const kpis = [];
      if (j) {
        kpis.push({ lbl: "Sessions 30j",  val: j.sessions || 0,    unit: "",  delta: "—", dir: "up", spark: [0, j.sessions || 0] });
        kpis.push({ lbl: "Tokens 30j",    val: Math.round((j.total_tokens || 0) / 1000), unit: "K", delta: "—", dir: "up", spark: [0, Math.round((j.total_tokens || 0) / 1000)] });
        kpis.push({ lbl: "Coût 30j",      val: (j.total_cost_usd || 0).toFixed(2), unit: "$", delta: "—", dir: "up", spark: [0, j.total_cost_usd || 0] });
      }
      if (y && y.configured) {
        kpis.push({ lbl: "Subs YouTube",  val: Math.round((y.subscribers || 0) / 1000 * 10) / 10, unit: "K", delta: "—", dir: "up", spark: [0, y.subscribers || 0] });
      }

      const topVideos = (y && y.configured && y.recent_videos && y.recent_videos.length)
        ? y.recent_videos.slice(0, 4).map((v, i) => ({
            rank:  String(i + 1).padStart(2, "0"),
            title: v.title || "—",
            views: J.fmt.num(v.views || 0),
            chg:   "—",
          }))
        : MOCK_TOP;

      return { kpis: kpis.length > 0 ? kpis : MOCK_KPIS, sources: MOCK_SOURCES, topVideos };
    } catch (_) { return { kpis: MOCK_KPIS, sources: MOCK_SOURCES, topVideos: MOCK_TOP }; }
  }

  async function loadDevices() {
    try { return await J.api.get("/api/settings/devices"); }
    catch (_) { return []; }
  }

  /* ───────── Render helpers ───────── */
  function card(opts, children) {
    const c = el("div", { class: "card" });
    if (opts.title || opts.right) {
      c.appendChild(el("div", { class: "card-hd" }, [
        el("div", {}, [
          el("div", { class: "card-title", text: opts.title }),
          opts.sub ? el("div", { class: "card-sub", text: opts.sub }) : null,
        ]),
        opts.right || null,
      ]));
    }
    (Array.isArray(children) ? children : [children]).forEach(ch => ch && c.appendChild(ch));
    return c;
  }
  function secHd(num, title, display, right) {
    return el("div", { class: "sec-hd" }, [
      el("div", { class: "sec-hd-l" }, [
        el("div", { class: "sec-hd-row" }, [
          el("span", { class: "sec-hd-num", text: num }),
          el("span", { class: "sec-hd-title", text: title }),
        ]),
        el("span", { class: "sec-hd-disp", text: display }),
      ]),
      right ? el("div", { class: "sec-hd-r", text: right }) : null,
    ]);
  }

  const PRI_BADGE = {
    high: { cls: "badge--gold",   label: "P1" },
    med:  { cls: "badge--accent", label: "P2" },
    low:  { cls: "badge--solid",  label: "P3" },
  };
  const STATUS_LBL = { run: "Running", wait: "Waiting", queue: "Queued" };

  /* ───────── Section renderers ───────── */
  function renderInitiatives(root, data) {
    root.innerHTML = "";
    root.appendChild(secHd("01", "Initiatives", "Ce qui mérite ton attention", "Mis à jour il y a 4 min"));
    const filters = el("div", { style: { display: "flex", gap: "8px", alignItems: "center" } }, [
      el("span", { class: "badge badge--solid", text: "All" }),
      el("span", { class: "badge", text: "Action" }),
      el("span", { class: "badge", text: "Stratégie" }),
      el("button", { class: "btn-ghost", text: "+ New ⌘N" }),
    ]);
    const list = el("div");
    data.forEach((it, i) => {
      const pri = PRI_BADGE[it.priority] || PRI_BADGE.low;
      list.appendChild(el("div", { class: "init-row fx-focus" }, [
        el("div", { class: "init-num", text: String(i + 1).padStart(2, "0") }),
        el("div", {}, [
          el("div", { class: "init-title", text: it.title }),
          el("div", { class: "init-meta" }, [
            el("span", { text: it.id }),
            el("span", { style: { color: "var(--fg-4)" }, text: "·" }),
            el("span", { text: it.source }),
            el("span", { style: { color: "var(--fg-4)" }, text: "·" }),
            el("span", { text: "Échéance · " + it.due }),
          ]),
        ]),
        el("div", { class: "init-badges" }, [
          el("span", { class: "badge " + pri.cls }, [
            el("span", { class: "pri-dot" }),
            document.createTextNode(pri.label),
          ]),
          el("span", { class: "badge badge--solid", text: it.type }),
        ]),
        el("div", { class: "init-arrow", text: "→" }),
      ]));
    });
    root.appendChild(card({ title: "Initiatives", sub: data.length + " active · proposées par l'agent · triées par priorité", right: filters }, list));
  }

  function renderMissions(root, data) {
    const { missions, doneCount } = data;
    root.innerHTML = "";
    const statParts = [];
    if (missions.length > 0) statParts.push(missions.length + " en cours");
    if (doneCount > 0) statParts.push(doneCount + " terminées");
    root.appendChild(secHd("02", "Missions", "Ce que l'agent fait pour toi", statParts.join(" · ") || "Aucune mission"));
    const list = el("div");
    if (missions.length === 0) {
      list.appendChild(el("div", { class: "j-empty", text: "Aucune mission en cours" }));
    } else {
      missions.forEach(m => {
        list.appendChild(el("div", { class: "mission" }, [
          el("div", { class: "m-id" }, [
            document.createTextNode(m.id),
            el("div", { class: "m-id-status " + m.status, text: STATUS_LBL[m.status] }),
          ]),
          el("div", {}, [
            el("div", { class: "m-title", text: m.title }),
            el("div", { class: "m-sub", text: m.sub }),
          ]),
          el("div", { class: "m-prog" }, [
            el("div", { class: "m-prog-bar" }, [el("div", { style: { width: (m.prog * 100) + "%" } })]),
            el("div", { class: "m-prog-meta" }, [
              el("span", { text: Math.round(m.prog * 100) + "%" }),
              el("span", { text: m.cur != null ? (m.cur + " / " + m.tot) : "—" }),
            ]),
          ]),
          el("div", { class: "m-eta" }, [
            el("div", { class: "m-eta-lbl", text: "ETA" }),
            document.createTextNode(m.eta),
          ]),
        ]));
      });
    }
    const cardOpts = { title: "Missions", sub: missions.length + " en cours · agent autonomous" };
    if (doneCount > 0) cardOpts.right = el("button", { class: "btn-ghost", text: "Voir tout · " + (missions.length + doneCount) });
    root.appendChild(card(cardOpts, list));
  }

  function renderDomotique(root) {
    root.innerHTML = "";
    root.appendChild(secHd("03", "Écosystème", "Modules & intégrations", "0 device"));
    root.appendChild(el("div", { class: "placeholder" }, [
      el("div", {}, [
        el("div", { class: "ph-eyebrow", text: "Écosystème · aucun module connecté" }),
        el("div", { class: "ph-title",   text: "Aucun device" }),
        el("div", { class: "ph-body",    text: "Connecte un module de l'écosystème Jarvis, HomeKit, Matter ou Home Assistant pour piloter lumières, capteurs et thermostats depuis Jarvis." }),
        el("div", { style: { marginTop: "18px", display: "flex", gap: "8px", justifyContent: "center" } }, [
          el("button", { class: "btn-accent", text: "Connecter un hub" }),
          el("button", { class: "tb-btn",     text: "Documentation" }),
        ]),
      ]),
    ]));
  }

  function renderDevices(root, data) {
    const COL = { green: "var(--green)", accent: "var(--accent)", muted: "var(--fg-3)" };
    const activeCount = data.filter(d => d.status === "Active" || d.status === "Connected").length;
    const nearbyCount = data.filter(d => d.status === "Nearby").length;
    const statParts = [];
    if (activeCount) statParts.push(activeCount + " actifs");
    if (nearbyCount) statParts.push(nearbyCount + " à proximité");
    root.innerHTML = "";
    root.appendChild(secHd("04", "Devices", "Tes appareils", statParts.join(" · ") || "—"));
    root.appendChild(el("div", {
      style: { display: "flex", justifyContent: "flex-end", marginBottom: "14px" },
    }, [
      el("button", {
        class: "btn-accent",
        text: "Ajouter un appareil",
        onclick: () => { window.location.href = "/keypad"; },
      }),
    ]));
    if (data.length === 0) {
      root.appendChild(el("div", { class: "j-empty", text: "Aucun appareil détecté" }));
      return;
    }
    const grid = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "12px" } });
    data.forEach(d => {
      const col = COL[d.col] || d.col;
      const aRaw = d.a && d.a.length > 1 ? String(d.a[1]) : "—";
      const bRaw = d.b && d.b.length > 1 ? String(d.b[1]) : "—";
      grid.appendChild(el("div", { class: "dev-card" }, [
        el("div", { class: "dev-head" }, [
          el("div", {}, [
            el("div", { class: "dev-name", text: d.name }),
            el("div", { class: "dev-id",   text: d.id }),
          ]),
          el("div", {}, [
            el("span", {
              class: "t-mono",
              style: { fontSize: "10px", color: col, letterSpacing: ".12em", textTransform: "uppercase" },
              text: "● " + d.status,
            }),
          ]),
        ]),
        el("div", { class: "dev-meters" }, [
          el("div", { class: "dev-meter" }, [
            el("div", { class: "lbl", text: d.a[0] }),
            el("div", { class: "val" }, [document.createTextNode(aRaw)]),
          ]),
          el("div", { class: "dev-meter" }, [
            el("div", { class: "lbl", text: d.b[0] }),
            el("div", { class: "val" }, [document.createTextNode(bRaw)]),
          ]),
        ]),
      ]));
    });
    root.appendChild(grid);
  }

  function renderAnalytics(root, data) {
    root.innerHTML = "";
    root.appendChild(secHd("05", "Analytics", "Ce qui se passe en ce moment", "multi-source · 7j"));

    // KPIs
    const kpiGrid = el("div", { class: "kpi-grid" });
    data.kpis.forEach(k => {
      const sparkSlot = el("div");
      sparkSlot.appendChild(J.sparkline(k.spark, { width: 180, height: 28, color: k.dir === "up" ? "var(--green)" : "var(--accent)" }));
      kpiGrid.appendChild(el("div", {
        class: "kpi",
        dataset: { inspect: k.lbl + " · " + k.delta + " vs 7j · src: " + (k.lbl.indexOf("Latence") >= 0 ? "edge ping" : "agg. multi-source") },
      }, [
        el("div", { class: "kpi-lbl" }, [
          el("span", { text: k.lbl }),
          el("span", { class: "kpi-delta " + k.dir, text: k.delta }),
        ]),
        el("div", { class: "kpi-val" }, [
          el("span", { class: "v", text: J.fmt.num(k.val) }),
          el("span", { class: "u", text: k.unit }),
        ]),
        sparkSlot,
      ]));
    });
    root.appendChild(kpiGrid);

    // Multi-source + Top videos
    const twoCol = el("div", { style: { display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: "18px", marginTop: "18px" } });

    const srcList = el("div");
    data.sources.forEach(s => {
      srcList.appendChild(el("div", { class: "src-row" }, [
        el("div", { class: "src-name" }, [
          el("div", { class: "src-glyph", text: s.glyph }),
          el("span", { text: s.name }),
        ]),
        el("div", { class: "src-bar" }, [el("div", { style: { width: (s.w * 100) + "%", background: s.color } })]),
        el("div", { class: "src-num", text: s.num }),
        el("div", { class: "src-delta", style: { color: s.dir === "up" ? "var(--green)" : "var(--red)" }, text: s.delta }),
      ]));
    });
    twoCol.appendChild(card({ title: "Multi-source", sub: "reach · 7 derniers jours", right: el("button", { class: "btn-ghost", text: "Période · 7j ▾" }) }, srcList));

    const topList = el("div");
    data.topVideos.forEach((v, i) => {
      topList.appendChild(el("div", {
        style: {
          display: "grid",
          gridTemplateColumns: "32px 1fr 80px 60px",
          padding: "13px 0",
          borderTop: i ? "1px solid var(--line-1)" : "0",
          alignItems: "center", gap: "14px", fontSize: "12.5px",
        },
      }, [
        el("span", { class: "t-mono", style: { color: "var(--fg-3)" }, text: v.rank }),
        el("span", { style: { color: "var(--fg-0)" }, text: v.title }),
        el("span", { class: "t-mono", style: { textAlign: "right", color: "var(--fg-1)" }, text: v.views }),
        el("span", { class: "t-mono", style: { textAlign: "right", color: v.chg.indexOf("−") === 0 ? "var(--red)" : "var(--green)", fontSize: "10.5px" }, text: v.chg }),
      ]));
    });
    twoCol.appendChild(card({ title: "Top contenus", sub: "YouTube · 30j" }, topList));

    root.appendChild(twoCol);
  }

  /* ───────── App state + routing ───────── */
  const state = {
    active: "initiatives",
    sections: [
      { id: "initiatives", label: "Initiatives", meta: "6" },
      { id: "missions",    label: "Missions",    meta: "5" },
      { id: "domotique",   label: "Écosystème",  meta: "—" },
      { id: "devices",     label: "Devices",     meta: "4" },
      { id: "analytics",   label: "Analytics",   meta: "7j" },
    ],
  };

  function mountSidebar() {
    J.mountSidebar({
      activeId: state.active,
      onNav: (id) => { state.active = id; renderActive(); refreshSidebar(); },
      sections: [
        { label: "Control", items: state.sections },
      ],
      footer: { spend: "$3.42", cpu: "14%", ramPct: 0.65 },
    });
  }
  function refreshSidebar() {
    document.querySelectorAll(".sb-item").forEach(b => {
      b.classList.toggle("is-on", b.dataset.id === state.active);
    });
  }

  async function renderActive() {
    const root = document.getElementById("page-root");
    root.innerHTML = '<div class="surface"><div class="j-loading">Chargement…</div></div>';
    const surface = el("section", { class: "surface page-in", dataset: { screenLabel: "dashboard-" + state.active } });

    try {
      switch (state.active) {
        case "initiatives": renderInitiatives(surface, await loadInitiatives()); break;
        case "missions":    renderMissions(surface, await loadMissions()); break;
        case "domotique":   renderDomotique(surface); break;
        case "devices":     renderDevices(surface, await loadDevices()); break;
        case "analytics":   renderAnalytics(surface, await loadAnalytics()); break;
      }
    } catch (err) {
      surface.appendChild(el("div", { class: "j-empty", text: "Erreur de chargement : " + err.message }));
    }
    root.innerHTML = "";
    root.appendChild(surface);
  }

  /* ───────── Boot ───────── */
  function registerCommands() {
    J.registerCommands([
      // Navigation (no slash)
      { kind: "nav",   group: "Aller à", title: "Initiatives",  glyph: "01", run: () => { state.active = "initiatives"; renderActive(); refreshSidebar(); } },
      { kind: "nav",   group: "Aller à", title: "Missions",     glyph: "02", run: () => { state.active = "missions";    renderActive(); refreshSidebar(); } },
      { kind: "nav",   group: "Aller à", title: "Écosystème",   glyph: "03", run: () => { state.active = "domotique";   renderActive(); refreshSidebar(); } },
      { kind: "nav",   group: "Aller à", title: "Devices",      glyph: "04", run: () => { state.active = "devices";     renderActive(); refreshSidebar(); } },
      { kind: "nav",   group: "Aller à", title: "Analytics",    glyph: "05", run: () => { state.active = "analytics";   renderActive(); refreshSidebar(); } },
      { kind: "nav",   group: "Pages",   title: "Keypad Studio", glyph: "⌨", sub: "firmware macropad CH552", run: () => { window.location.href = "/keypad"; } },
      { kind: "nav",   group: "Pages",   title: "Système",      glyph: "→",  sub: "tools, mémoire, conso, params", run: () => { window.handleSettingsClick && window.handleSettingsClick(); } },
      // Slash commands (>)
      { kind: "slash", group: "Commandes", title: "restart",  glyph: ">", sub: "redémarre le runtime agent",  run: () => J.notify({ kind: "warn",   text: "Runtime · restart envoyé" }) },
      { kind: "slash", group: "Commandes", title: "logs",     glyph: ">", sub: "ouvre les logs récents",       run: () => J.notify({ kind: "info",   text: "Logs · ouverture…" }) },
      { kind: "slash", group: "Commandes", title: "spend",    glyph: ">", sub: "dépense aujourd'hui",          run: () => J.notify({ kind: "info",   text: "Spend · $3.42 aujourd'hui" }) },
      { kind: "slash", group: "Commandes", title: "memo",     glyph: ">", sub: "ajoute un mémo rapide",        run: () => J.notify({ kind: "success",text: "Memo · enregistré" }) },
      { kind: "slash", group: "Commandes", title: "calm",     glyph: ">", sub: "mode calme (focus)",           run: () => document.body.dataset.mode = "calm" },
      { kind: "slash", group: "Commandes", title: "control",  glyph: ">", sub: "mode control (default)",       run: () => document.body.dataset.mode = "control" },
    ]);
  }

  function boot() {
    J.mountAtmosphere();
    mountSidebar();
    J.mountTopbar({
      pageTitle: "Dashboard",
      crumb: "/ control",
      onAsk: () => { J.openCmdK(); setTimeout(() => { document.querySelector(".cmdk-input").value = "> ask "; document.querySelector(".cmdk-input").dispatchEvent(new Event("input")); }, 50); },
    });
    J.mountBottomNav({ active: "control" });
    registerCommands();
    renderActive();
  }
  window.Dashboard = { boot };
})();
