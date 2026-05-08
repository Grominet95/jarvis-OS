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
    const [activeRes, dataRes] = await Promise.all([
      J.api.get("/api/analytics/active"),
      J.api.get("/api/analytics/data"),
    ]);
    return { active: activeRes.widgets || [], data: dataRes.widgets || {} };
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
    if (data.length === 0) {
      root.appendChild(el("div", { class: "j-empty", text: "Aucun appareil détecté" }));
      root.appendChild(el("div", { style: { marginTop: "14px" } }, [
        el("button", { class: "btn-ghost", onclick: () => window.openKeypadDrawer?.(), text: "Ajouter un appareil Jarvis (Keypad Studio)" }),
      ]));
      return;
    }
    const grid = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "12px" } });
    data.forEach(d => {
      const col = COL[d.col] || d.col;
      const aRaw = d.a && d.a.length > 1 ? String(d.a[1]) : "—";
      const bRaw = d.b && d.b.length > 1 ? String(d.b[1]) : "—";
      const parts = [
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
      ];
      if (d.type === "macropad") {
        parts.push(el("div", { style: { marginTop: "10px" } }, [
          el("button", { class: "btn-ghost", onclick: () => window.openKeypadDrawer?.(), text: "Configurer dans Keypad Studio" }),
        ]));
      }
      const isNearby = d.status === "Nearby";
      grid.appendChild(el("div", { class: "dev-card" + (isNearby ? " dev-card--nearby" : "") }, parts));
    });
    root.appendChild(grid);
  }

  /* ───────── Analytics widget system ───────── */

  function renderAnalytics(root, { active, data }) {
    root.innerHTML = "";

    const hd = el("div", { class: "sec-hd" }, [
      el("div", { class: "sec-hd-l" }, [
        el("div", { class: "sec-hd-row" }, [
          el("span", { class: "sec-hd-num",   text: "05" }),
          el("span", { class: "sec-hd-title", text: "Analytics" }),
        ]),
        el("span", { class: "sec-hd-disp", text: "Ce qui se passe en ce moment" }),
      ]),
      el("div", { class: "sec-hd-r", style: { display: "flex", gap: "8px", alignItems: "center" } }, [
        el("span", { class: "t-mono", style: { fontSize: "10px", color: "var(--fg-3)" }, text: "multi-source · 7j" }),
        el("button", { class: "btn-ghost", onclick: openAddWidgetModal, text: "+ Ajouter" }),
        el("button", { class: "btn-ghost", onclick: refreshAnalyticsView, text: "↻" }),
      ]),
    ]);
    root.appendChild(hd);

    const grid = el("div", { class: "analytics-grid" });
    if (!active.length) {
      grid.appendChild(el("div", { class: "j-empty", style: { gridColumn: "span 4" }, text: "Aucun widget actif — cliquer + Ajouter pour commencer." }));
    } else {
      active.forEach(manifest => grid.appendChild(renderWidget(manifest, data[manifest.id])));
    }
    root.appendChild(grid);

    clearTimeout(window._analyticsTimer);
    window._analyticsTimer = setTimeout(refreshAnalyticsView, 5 * 60 * 1000);
  }

  async function refreshAnalyticsView() {
    if (state.active === "analytics") renderActive();
  }

  function renderWidget(manifest, wd) {
    const isNative = manifest.requires_env.length === 0;
    const div = el("div", { class: "widget widget-" + manifest.size });
    div.appendChild(el("div", { class: "widget-header" }, [
      el("div",  { class: "widget-icon",  text: manifest.icon }),
      el("span", { class: "widget-label", text: manifest.label }),
      isNative ? null : el("button", { class: "widget-remove", onclick: () => removeWidget(manifest.id), text: "×" }),
    ]));
    if (!wd || !wd.success) {
      div.appendChild(renderWidgetError(manifest, wd && wd.error));
      return div;
    }
    const body = el("div", { class: "widget-body" });
    const renderers = { jarvis_stats: renderJarvisStats, conso: renderConso, youtube: renderYouTube, github: renderGitHub, discord: renderDiscord };
    if (renderers[manifest.id]) renderers[manifest.id](body, wd.data);
    div.appendChild(body);
    return div;
  }

  function renderWidgetError(manifest, error) {
    const div = el("div", { class: "widget-error" });
    div.appendChild(el("span", { text: "⚠ " + (error || "Erreur de chargement") }));
    if (manifest.requires_env.length) {
      div.appendChild(el("span", { class: "widget-config-hint", text: "Configurer dans Système → Outils → " + manifest.label }));
    }
    return div;
  }

  function renderJarvisStats(body, d) {
    const row = el("div", { class: "widget-metrics" });
    [
      { lbl: "Sessions (7j)",    val: d.sessions_7d },
      { lbl: "Missions",         val: d.missions_total },
      { lbl: "Coût aujourd'hui", val: "$" + d.cost_today },
      { lbl: "Tokens",           val: J.fmt.num(d.tokens_today) },
    ].forEach(m => row.appendChild(el("div", { class: "widget-metric" }, [
      el("div", { class: "widget-metric-lbl", text: m.lbl }),
      el("div", { class: "widget-metric-val", text: String(m.val) }),
    ])));
    body.appendChild(row);
  }

  function renderConso(body, d) {
    body.appendChild(el("div", { class: "widget-conso-totals" }, [
      el("span", { text: "Coût 7j : $" + d.total_7d }),
      el("span", { text: "Total 30j : $" + d.total_30d }),
    ]));
    const days7 = Object.entries(d.daily || {}).slice(0, 7).reverse();
    const maxCost = Math.max(...days7.map(([, v]) => v.cost), 0.0001);
    const MAX_PX = 48;
    const bars = el("div", { class: "widget-bars" });
    days7.forEach(([date, v]) => {
      const px = Math.max(2, Math.round((v.cost / maxCost) * MAX_PX));
      bars.appendChild(el("div", { class: "widget-bar-col" }, [
        el("div", { class: "widget-bar", style: { height: px + "px" } }),
        el("div", { class: "widget-bar-lbl", text: date.slice(5) }),
      ]));
    });
    body.appendChild(bars);
  }

  function renderYouTube(body, d) {
    const row = el("div", { class: "widget-metrics" });
    [
      { lbl: "Abonnés",     val: J.fmt.num(d.subscribers) },
      { lbl: "Vues totales",val: J.fmt.num(d.total_views) },
      { lbl: "Vidéos",      val: d.video_count },
    ].forEach(m => row.appendChild(el("div", { class: "widget-metric" }, [
      el("div", { class: "widget-metric-lbl", text: m.lbl }),
      el("div", { class: "widget-metric-val", text: String(m.val) }),
    ])));
    body.appendChild(row);
    if (d.recent_videos && d.recent_videos.length) {
      const list = el("div", { class: "widget-video-list" });
      d.recent_videos.slice(0, 4).forEach((v, i) => list.appendChild(el("div", { class: "widget-video-row" }, [
        el("span", { class: "widget-video-rank", text: String(i + 1).padStart(2, "0") }),
        el("span", { class: "widget-video-title", text: v.title }),
        el("span", { class: "widget-video-date",  text: v.published }),
      ])));
      body.appendChild(list);
    }
  }

  function renderGitHub(body, d) {
    const row = el("div", { class: "widget-metrics" });
    [
      { lbl: "Stars",   val: J.fmt.num(d.stars) },
      { lbl: "Forks",   val: d.forks },
      { lbl: "Watchers",val: d.watchers },
      { lbl: "Issues",  val: d.open_issues },
    ].forEach(m => row.appendChild(el("div", { class: "widget-metric" }, [
      el("div", { class: "widget-metric-lbl", text: m.lbl }),
      el("div", { class: "widget-metric-val", text: String(m.val) }),
    ])));
    body.appendChild(row);
  }

  function renderDiscord(body, d) {
    body.appendChild(el("div", { class: "widget-discord" }, [
      el("div", { class: "widget-discord-name", text: d.name }),
      el("div", { class: "widget-discord-stats" }, [
        el("span", { text: "● " + J.fmt.num(d.members_total) + " membres" }),
        el("span", { text: "● " + d.members_online + " en ligne" }),
      ]),
    ]));
  }

  async function removeWidget(widgetId) {
    const res = await fetch("/api/analytics/remove/" + widgetId, { method: "DELETE" });
    if ((await res.json()).success) renderActive();
  }

  async function openAddWidgetModal() {
    const res = await J.api.get("/api/analytics/catalog");
    const catalog = (res.widgets || []).filter(w => !w.active && w.requires_env.length > 0);

    let selected = null;
    const overlay = el("div", { class: "modal-overlay" });
    overlay.addEventListener("click", e => { if (e.target === overlay) overlay.remove(); });
    const modal = el("div", { class: "add-widget-modal" });
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    function step1() {
      modal.innerHTML = "";
      modal.appendChild(el("div", { class: "modal-header" }, [
        el("span", { class: "modal-title", text: "AJOUTER UN WIDGET" }),
        el("button", { class: "widget-remove", onclick: () => overlay.remove(), text: "×" }),
      ]));
      modal.appendChild(el("p", { class: "modal-sub", text: "Choisissez une source de données" }));

      const list = el("div", { class: "catalog-list" });
      if (!catalog.length) {
        list.appendChild(el("div", { class: "j-empty", text: "Tous les widgets sont déjà actifs." }));
      }
      catalog.forEach(w => {
        const item = el("div", { class: "catalog-item", onclick: () => {
          selected = w;
          modal.querySelectorAll(".catalog-item").forEach(i => i.classList.remove("selected"));
          item.classList.add("selected");
        }});
        item.appendChild(el("div", { class: "catalog-item-main" }, [
          el("div", { class: "src-glyph", text: w.icon }),
          el("div", {}, [
            el("div", { class: "catalog-item-label", text: w.label }),
            el("div", { class: "catalog-item-desc",  text: w.description }),
          ]),
          el("span", { class: w.configured ? "badge badge--solid" : "badge", text: w.configured ? "✓ Configuré" : "Requiert config" }),
        ]));
        if (w.requires_env.length) {
          item.appendChild(el("div", { class: "catalog-item-env", text: "⚠ Requiert : " + w.requires_env.join(" · ") }));
        }
        list.appendChild(item);
      });
      modal.appendChild(list);
      modal.appendChild(el("div", { class: "modal-footer" }, [
        el("button", { class: "btn-accent", onclick: () => {
          if (!selected) return;
          selected.configured ? step3(false) : step2();
        }, text: "Suivant →" }),
      ]));
    }

    function step2() {
      modal.innerHTML = "";
      modal.appendChild(el("div", { class: "modal-header" }, [
        el("span", { class: "modal-title", text: "AJOUTER UN WIDGET — " + selected.label }),
        el("button", { class: "widget-remove", onclick: () => overlay.remove(), text: "×" }),
      ]));
      modal.appendChild(el("p", { class: "modal-sub", text: "Configuration requise" }));

      const form = el("div", { class: "modal-form" });
      selected.requires_env.forEach(key => {
        form.appendChild(el("div", { class: "modal-field" }, [
          el("label", { class: "modal-field-lbl", text: key }),
          el("input", { class: "j-input", type: "text", placeholder: key }),
        ]));
      });
      modal.appendChild(form);

      const status = el("div", { class: "modal-status" });
      modal.appendChild(status);
      modal.appendChild(el("div", { class: "modal-footer" }, [
        el("button", { class: "btn-ghost", onclick: step1, text: "← Retour" }),
        el("button", { class: "btn-accent", onclick: async () => {
          status.textContent = "Test en cours…";
          const r = await fetch("/api/analytics/add/" + selected.id, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
          const d = await r.json();
          if (d.success) step3(true);
          else status.textContent = "✗ " + d.message;
        }, text: "Tester la connexion →" }),
      ]));
    }

    async function step3(alreadyAdded) {
      if (!alreadyAdded) {
        await fetch("/api/analytics/add/" + selected.id, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      }
      modal.innerHTML = "";
      modal.appendChild(el("div", { class: "modal-header" }, [
        el("span", { class: "modal-title", text: "AJOUTER UN WIDGET" }),
        el("button", { class: "widget-remove", onclick: () => overlay.remove(), text: "×" }),
      ]));
      modal.appendChild(el("div", { class: "modal-confirm" }, [
        el("div", { class: "modal-confirm-icon", text: "✓" }),
        el("div", { class: "modal-confirm-msg",  text: selected.label + " ajouté" }),
        el("div", { class: "modal-confirm-sub",  text: "Le widget apparaît maintenant dans votre Analytics." }),
      ]));
      modal.appendChild(el("div", { class: "modal-footer" }, [
        el("button", { class: "btn-accent", onclick: () => { overlay.remove(); renderActive(); }, text: "Fermer" }),
      ]));
    }

    step1();
  }

  /* ───────── Routines ───────── */
  async function loadRoutines() {
    try {
      const res = await J.api.get("/api/routines");
      return (res && res.routines) ? res.routines : [];
    } catch (_) { return []; }
  }

  const _routineProgress = {};

  function renderRoutines(root, routines) {
    root.appendChild(secHd("05", "Routines", "Séquences automatisées", routines.length + " installée(s)"));

    if (!routines.length) {
      const empty = el("div", { class: "j-empty" });
      empty.appendChild(document.createTextNode("Aucune routine installée. "));
      const link = el("a", { href: "/settings", style: { color: "var(--accent)" }, text: "Aller au Marketplace →" });
      empty.appendChild(link);
      root.appendChild(card({ title: "Routines installées", sub: "0 routine" }, empty));
      return;
    }

    const list = el("div");
    routines.forEach((r, i) => {
      const triggersText = (r.triggers || []).slice(0, 2).map(t => `"${t}"`).join(", ");
      const platformsText = (r.platforms || []).join(", ") || "—";
      const stepsText = (r.steps_count || 0) + " step" + (r.steps_count !== 1 ? "s" : "");

      const progressEl = el("div", {
        style: { fontSize: "11px", color: "var(--fg-3)", marginTop: "4px", display: "none" },
      });

      const launchBtn = el("button", { class: "btn-ghost", text: "▶ Lancer" });
      launchBtn.onclick = async () => {
        launchBtn.disabled = true;
        launchBtn.textContent = "▶ En cours…";
        progressEl.style.display = "block";
        progressEl.textContent = "Démarrage…";
        _routineProgress[r.name] = { btn: launchBtn, progress: progressEl };
        try {
          const res = await fetch("/api/routines/" + encodeURIComponent(r.name) + "/execute", { method: "POST" });
          const data = await res.json();
          const done = data.steps_done || 0;
          const fail = data.steps_failed || 0;
          J.notify({ kind: "success", text: `Routine "${r.label || r.name}" terminée — ${done} étapes réalisées` + (fail ? `, ${fail} en erreur` : "") });
        } catch (e) {
          J.notify({ kind: "error", text: "Erreur routine : " + e.message });
        }
        launchBtn.disabled = false;
        launchBtn.textContent = "▶ Lancer";
        progressEl.style.display = "none";
        delete _routineProgress[r.name];
      };

      const infoCol = el("div", { style: { flex: 1 } });
      infoCol.appendChild(el("span", { style: { color: "var(--fg-0)" }, text: r.label || r.name }));
      infoCol.appendChild(el("span", { class: "tn-sub", text: ` ${stepsText} · ${platformsText}` }));
      if (triggersText) infoCol.appendChild(el("span", { class: "tn-sub", text: triggersText }));
      infoCol.appendChild(progressEl);

      list.appendChild(el("div", {
        class: "tool-row",
        style: { borderTop: i ? "1px solid var(--line-1)" : "0", alignItems: "start" },
      }, [
        el("div", { class: "tg", text: "▶" }),
        infoCol,
        launchBtn,
      ]));
    });

    const mktLink = el("a", { href: "/settings", class: "btn-ghost", style: { fontSize: "12px" }, text: "Marketplace →" });
    root.appendChild(card({ title: "Routines installées", sub: routines.length + " routine(s)", right: mktLink }, list));
  }

  // WebSocket handler temps réel (appelé depuis _shared.js si exposé)
  window._handleRoutineEvent = function(msg) {
    const entry = _routineProgress[msg.routine];
    if (!entry) return;
    if (msg.type === "routine_step") {
      entry.progress.textContent = `Étape ${msg.step_index}/${msg.total_steps || "?"} : ${msg.step_name}`;
    } else if (msg.type === "routine_finished") {
      entry.progress.textContent = "Terminé ✓";
    }
  };

  /* ───────── App state + routing ───────── */
  const state = {
    active: "initiatives",
    sections: [
      { id: "initiatives", label: "Initiatives", meta: "6" },
      { id: "missions",    label: "Missions",    meta: "5" },
      { id: "domotique",   label: "Écosystème",  meta: "—" },
      { id: "devices",     label: "Devices",     meta: "4" },
      { id: "routines",    label: "Routines",    meta: "" },
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
        case "routines":    renderRoutines(surface, await loadRoutines()); break;
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
      { kind: "nav",   group: "Aller à", title: "Routines",     glyph: "05", run: () => { state.active = "routines";    renderActive(); refreshSidebar(); } },
      { kind: "nav",   group: "Aller à", title: "Analytics",    glyph: "06", run: () => { state.active = "analytics";   renderActive(); refreshSidebar(); } },
      { kind: "nav",   group: "Pages",   title: "Keypad Studio", glyph: "⌨", sub: "firmware macropad CH552", run: () => { window.openKeypadDrawer?.(); } },
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
