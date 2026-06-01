/* dashboard.js — Workspace (Pilotage) v2
 * 5 sous-pages : Aperçu · Initiatives · Missions · Tâches · Analytics
 */
(function () {
  "use strict";
  const J = window.Jarvis, el = J.el;

  const PAGES = [
    { id: "apercu",      label: "Aperçu" },
    { id: "initiatives", label: "Initiatives" },
    { id: "missions",    label: "Missions" },
    { id: "taches",      label: "Tâches" },
    { id: "analytics",   label: "Analytics" },
  ];

  let _activePage = "apercu";
  const root = document.getElementById("page-root");


  /* ───────── Loaders ───────── */
  async function loadInitiatives() {
    try {
      const raw = await J.api.get("/api/initiatives");
      const pMap = { haute:"high", moyen:"med", basse:"low", high:"high", med:"med", low:"low" };
      return raw.map(i => ({
        id:       i.id,
        title:    i.title,
        type:     i.type || "Action",
        priority: pMap[String(i.priority||"").toLowerCase()] || "low",
        source:   i.context ? i.context.slice(0,40) : "Jarvis",
        due:      i.created_at ? J.fmt.relTime(i.created_at) : "—",
        raw:      i,
      }));
    } catch (_) { return []; }
  }

  async function loadMissions() {
    try {
      const raw = await J.api.get("/api/projects");
      const sMap = { running:"run", planning:"run", waiting:"wait", queued:"queue", queue:"queue", done:"done", failed:"failed", killed:"killed" };
      const toRow = p => ({
        id:     p.id ? p.id.slice(0,6).toUpperCase() : "?",
        status: sMap[p.status] || "run",
        title:  p.title || p.instruction || "Mission sans titre",
        sub:    "agent · " + (p.status||"running"),
        prog:   p.steps_total > 0 ? p.steps_done/p.steps_total : (p.status === "done" ? 1 : 0),
        cur:    p.steps_done||null,
        tot:    p.steps_total||null,
        rawId:  p.id,
      });
      const active = raw.filter(p => p.status !== "done" && p.status !== "failed" && p.status !== "killed").map(toRow);
      const ended  = raw.filter(p => p.status === "done" || p.status === "failed" || p.status === "killed").map(toRow);
      return { active, ended };
    } catch (_) { return { active: [], ended: [] }; }
  }

  /* ───────── Page builder ───────── */
  function pageWrapper(pageId, title, meta, body) {
    const idx = PAGES.findIndex(p => p.id === pageId);
    const num = String(idx + 1).padStart(2, "0");
    const wrap = el("div", { class: "page room-in" });

    const head = el("div", { class: "page-head" });
    const left = el("div");
    const eyebrow = el("div", { class: "page-eyebrow" });
    eyebrow.appendChild(el("span", { class: "num", text: num }));
    eyebrow.appendChild(el("span", { text: " · " + PAGES[idx].label.toUpperCase() }));
    left.appendChild(eyebrow);
    left.appendChild(el("h1", { text: title }));
    head.appendChild(left);
    if (meta) {
      const m = el("div", { class: "page-head-meta" });
      m.innerHTML = meta;
      head.appendChild(m);
    }
    wrap.appendChild(head);

    const pb = el("div", { class: "page-body" });
    pb.appendChild(body);
    wrap.appendChild(pb);
    return wrap;
  }

  function ghostSec(title, sub, right, content) {
    const sec = el("div", { class: "ghost-sec" });
    const hd = el("div", { class: "ghost-sec-hd" });
    const l = el("div");
    l.appendChild(el("div", { class: "ghost-sec-title", text: title }));
    if (sub) l.appendChild(el("div", { class: "ghost-sec-sub", text: sub }));
    hd.appendChild(l);
    if (right) hd.appendChild(el("div", { class: "ghost-sec-r", text: right }));
    sec.appendChild(hd);
    sec.appendChild(content);
    return sec;
  }

  /* ───────── Aperçu ───────── */
  async function renderApercu() {
    const [inits, { active }, tasksRaw] = await Promise.all([
      loadInitiatives(),
      loadMissions(),
      J.api.get("/api/tasks").catch(() => []),
    ]);
    const shown = inits.slice(0, 5);
    const highCount = inits.filter(i => i.priority === "high").length;
    const tasks = (tasksRaw.tasks || tasksRaw || [])
      .map(t => ({ id: t.id, label: t.title || t.label || t.text || "", done: !!(t.done || t.checked), src: t.source || "NOTION" }))
      .filter(t => t.label);

    const wrap = el("div", { style: { display: "flex", flexDirection: "column", gap: "44px" } });

    // À traiter — toujours affiché
    {
      const list = el("div");
      if (shown.length) {
        shown.forEach(i => list.appendChild(renderInitRow(i)));
      } else {
        list.appendChild(el("div", { class: "j-empty", text: "Aucune initiative en attente" }));
      }
      const sub = shown.length
        ? shown.length + " en attente" + (highCount ? " · " + highCount + " urgente" + (highCount > 1 ? "s" : "") : "")
        : "—";
      wrap.appendChild(ghostSec("À traiter", sub, shown.length ? "voir tout →" : null, list));
    }

    // Missions — toujours affiché
    const missionList = el("div");
    if (active.length) {
      active.slice(0, 3).forEach(m => missionList.appendChild(renderMissionRow(m)));
    } else {
      missionList.appendChild(el("div", { class: "j-empty", text: "Aucune mission en cours" }));
    }
    wrap.appendChild(ghostSec(
      "Missions",
      active.length ? active.length + " en cours" : "—",
      null,
      missionList
    ));

    // Tâches
    const taskList = el("div");
    if (tasks.length) {
      tasks.forEach(t => taskList.appendChild(buildTaskRow(t, taskList)));
    } else {
      taskList.appendChild(el("div", { class: "j-empty", text: "Aucune tâche" }));
    }
    wrap.appendChild(ghostSec(
      "Tâches",
      tasks.length ? tasks.filter(t => t.done).length + " / " + tasks.length + " terminées" : "—",
      null,
      taskList
    ));

    const page = pageWrapper(
      "apercu",
      "Ce qui mérite ton attention",
      null,
      wrap
    );
    root.innerHTML = "";
    root.appendChild(page);
  }

  /* ───────── Initiatives ───────── */
  async function renderInitiatives() {
    const inits = await loadInitiatives();
    const list = el("div");
    if (!inits.length) {
      list.appendChild(el("div", { class: "j-empty", text: "Aucune initiative en attente" }));
    } else {
      inits.forEach(i => list.appendChild(renderInitRow(i, true)));
    }

    const wrap = el("div");
    wrap.appendChild(ghostSec(
      "En attente",
      inits.length + " initiatives · proactif Jarvis",
      null,
      list
    ));

    const page = pageWrapper(
      "initiatives",
      "Ce qui mérite ton arbitrage",
      '<span class="v">' + inits.length + '</span> à traiter',
      wrap
    );
    root.innerHTML = "";
    root.appendChild(page);
  }

  function buildInitPanel(panel, i) {
    const raw = i.raw || {};
    const closeBtn = el("button", { class: "panel-close", text: "✕" });
    closeBtn.addEventListener("click", closePanel);

    const hdr = el("div", { class: "mp-header" });
    const left = el("div", { class: "mp-header-left" });
    const badge = el("div", { class: "mp-status-badge run", text: (raw.type || i.type || "").toUpperCase().replace("_", " ") });
    const info = el("div");
    info.appendChild(el("div", { class: "mp-title", text: i.title }));
    info.appendChild(el("div", { class: "mp-sub", text: i.source || "Jarvis proactif · " + (i.due || "") }));
    left.appendChild(badge); left.appendChild(info);
    hdr.appendChild(left); hdr.appendChild(closeBtn);
    panel.appendChild(hdr);

    const body = el("div", { class: "panel-body" });

    const addSec = (title, text) => {
      if (!text) return;
      const s = el("div", { class: "panel-section" });
      s.appendChild(el("div", { class: "panel-section-title", text: title }));
      s.appendChild(el("div", { style: { fontSize: "12px", lineHeight: "1.6", color: "var(--fg-2)" }, text: text }));
      body.appendChild(s);
    };

    addSec("Action proposée", raw.action || i.title);
    addSec("Contexte", raw.context);
    addSec("Raisonnement", raw.reasoning);

    if (raw.draft_content) {
      const s = el("div", { class: "panel-section" });
      s.appendChild(el("div", { class: "panel-section-title", text: "Brouillon" }));
      const pre = el("div", {
        style: { fontFamily: "var(--mono)", fontSize: "11px", lineHeight: "1.6",
                 whiteSpace: "pre-wrap", wordBreak: "break-word",
                 background: "rgba(74,158,255,0.04)", border: "1px solid rgba(74,158,255,0.10)",
                 borderRadius: "6px", padding: "10px 12px", color: "var(--fg-2)" },
        text: raw.draft_content,
      });
      s.appendChild(pre);
      body.appendChild(s);
    }

    // Actions
    const actSec = el("div", { class: "panel-section", style: { display: "flex", gap: "8px", marginTop: "8px" } });
    const approveBtn = el("button", { class: "m-btn", text: raw.type === "draft_response" ? "📤 Préparer & envoyer" : "✓ Approuver" });
    approveBtn.addEventListener("click", async () => {
      approveBtn.textContent = "…"; approveBtn.disabled = true;
      try {
        await J.api.post("/api/initiatives/" + raw.id + "/approve");
        J.notify({ kind: "success", text: "Initiative approuvée" });
        closePanel();
        if (_activePage === "apercu") renderApercu(); else renderInitiatives();
      } catch (e) { J.notify({ kind: "error", text: "Erreur : " + e.message }); approveBtn.disabled = false; approveBtn.textContent = "Approuver"; }
    });
    const rejectBtn = el("button", { class: "m-btn danger", text: "✗ Rejeter" });
    rejectBtn.addEventListener("click", async () => {
      rejectBtn.textContent = "…"; rejectBtn.disabled = true;
      try {
        await J.api.post("/api/initiatives/" + raw.id + "/reject");
        J.notify({ kind: "success", text: "Initiative rejetée" });
        closePanel();
        if (_activePage === "apercu") renderApercu(); else renderInitiatives();
      } catch (e) { J.notify({ kind: "error", text: "Erreur : " + e.message }); rejectBtn.disabled = false; rejectBtn.textContent = "Rejeter"; }
    });
    actSec.appendChild(approveBtn);
    actSec.appendChild(rejectBtn);
    body.appendChild(actSec);

    panel.appendChild(body);
  }

  function renderInitRow(i, showActions) {
    const row = el("div", { class: "row-stripe", style: { cursor: "pointer" } });
    row.addEventListener("click", (e) => {
      if (e.target.closest("button")) return;
      openPanel(buildInitPanel, i);
    });

    // Priority bar
    const bar = el("div", { class: "row-stripe-bar " + (i.priority || "low") });
    row.appendChild(bar);

    // Content
    const inner = el("div", { class: "row-stripe-inner" });
    inner.appendChild(el("div", { class: "row-stripe-title", text: i.title }));
    const meta = el("div", { class: "row-stripe-meta" });
    meta.appendChild(el("span", { class: "badge badge--solid", text: i.type || "Action" }));
    meta.appendChild(el("span", { text: i.source || "Jarvis" }));
    meta.appendChild(el("span", { style: { opacity: ".4" }, text: "·" }));
    meta.appendChild(el("span", { text: i.due || "—" }));
    inner.appendChild(meta);
    row.appendChild(inner);

    // Right — actions or ID
    const right = el("div", { class: "row-stripe-right" });
    if (showActions && i.raw) {
      const approve = el("button", { class: "m-btn", text: "Approuver" });
      approve.addEventListener("click", (e) => { e.stopPropagation(); approveInit(i.raw.id, approve); });
      const reject = el("button", { class: "m-btn danger", text: "Rejeter" });
      reject.addEventListener("click", (e) => { e.stopPropagation(); rejectInit(i.raw.id, reject); });
      right.appendChild(approve); right.appendChild(reject);
    } else {
      right.appendChild(el("span", { style: { fontFamily: "var(--mono)", fontSize: "10px", color: "var(--fg-3)" }, text: i.id || "" }));
    }
    row.appendChild(right);
    return row;
  }

  async function approveInit(id, btn) {
    btn.textContent = "…"; btn.disabled = true;
    try {
      await J.api.post("/api/initiatives/" + id + "/approve");
      J.notify({ kind: "success", text: "Initiative approuvée" });
      renderInitiatives();
    } catch (e) { J.notify({ kind: "error", text: "Erreur : " + e.message }); btn.textContent = "Approuver"; btn.disabled = false; }
  }
  async function rejectInit(id, btn) {
    btn.textContent = "…"; btn.disabled = true;
    try {
      await J.api.post("/api/initiatives/" + id + "/reject");
      J.notify({ kind: "success", text: "Initiative rejetée" });
      renderInitiatives();
    } catch (e) { J.notify({ kind: "error", text: "Erreur : " + e.message }); btn.textContent = "Rejeter"; btn.disabled = false; }
  }

  /* ───────── Panel (mission detail) ───────── */
  let _panelKeyListener = null;

  function initPanel() {
    if (document.getElementById("dash-detail-panel")) return;
    const overlay = el("div", { id: "dash-detail-overlay" });
    overlay.addEventListener("click", closePanel);
    document.body.appendChild(overlay);
    document.body.appendChild(el("div", { id: "dash-detail-panel" }));
    _panelKeyListener = e => { if (e.key === "Escape") closePanel(); };
    document.addEventListener("keydown", _panelKeyListener);
  }

  function closePanel() {
    const p = document.getElementById("dash-detail-panel");
    const o = document.getElementById("dash-detail-overlay");
    if (p) p.classList.remove("open");
    if (o) o.classList.remove("open");
  }

  function openPanel(buildFn, data) {
    initPanel();
    const panel = document.getElementById("dash-detail-panel");
    panel.innerHTML = "";
    buildFn(panel, data);
    requestAnimationFrame(() => {
      document.getElementById("dash-detail-overlay").classList.add("open");
      panel.classList.add("open");
    });
  }

  /* ───────── Simple markdown renderer ───────── */
  function renderMd(md) {
    if (!md) return "";
    let html = md
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      // fenced code blocks
      .replace(/```[\w]*\n?([\s\S]*?)```/g, (_, c) => "<pre><code>" + c.trim() + "</code></pre>")
      // headings
      .replace(/^### (.+)$/gm, "<h3>$1</h3>")
      .replace(/^## (.+)$/gm, "<h2>$1</h2>")
      .replace(/^# (.+)$/gm, "<h1>$1</h1>")
      // bold / italic
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      // inline code
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      // links
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
      // bullet lists (simple)
      .replace(/^[-*] (.+)$/gm, "<li>$1</li>")
      // paragraphs: double newlines
      .split(/\n{2,}/).map(block => {
        if (/^<(h[1-3]|pre|li|ul|ol)/.test(block.trim())) return block;
        if (block.includes("<li>")) return "<ul>" + block + "</ul>";
        return "<p>" + block.replace(/\n/g, "<br>") + "</p>";
      }).join("\n");
    return html;
  }

  /* ───────── File viewer popup ───────── */
  function openFileViewer(projectId, filePath) {
    let popup = document.getElementById("dash-file-popup");
    if (!popup) {
      const ov = el("div", { id: "dash-file-popup-overlay" });
      ov.addEventListener("click", () => closeFileViewer());
      document.body.appendChild(ov);
      popup = el("div", { id: "dash-file-popup" });
      document.body.appendChild(popup);
    }
    popup.innerHTML = '<div class="fp-loading">Chargement…</div>';
    document.getElementById("dash-file-popup-overlay").classList.add("open");
    popup.classList.add("open");

    J.api.get("/api/projects/" + projectId + "/files/" + filePath)
      .then(res => {
        const content = res.content || "";
        const isMd = filePath.endsWith(".md") || filePath.endsWith(".markdown");
        const isTxt = /\.(txt|json|yaml|yml|toml|ini|csv|py|js|ts|sh|env)$/.test(filePath);

        popup.innerHTML = "";
        const hdr = el("div", { class: "fp-header" });
        hdr.appendChild(el("span", { class: "fp-path", text: filePath }));
        const closeBtn = el("button", { class: "fp-close", text: "✕" });
        closeBtn.addEventListener("click", closeFileViewer);
        hdr.appendChild(closeBtn);
        popup.appendChild(hdr);

        const body = el("div", { class: "fp-body" });
        if (isMd) {
          const rendered = el("div", { class: "fp-markdown" });
          rendered.innerHTML = renderMd(content);
          body.appendChild(rendered);
        } else {
          const pre = el("pre", { class: "fp-code" });
          pre.textContent = content;
          body.appendChild(pre);
        }
        popup.appendChild(body);
      })
      .catch(e => {
        popup.innerHTML = '<div class="fp-loading" style="color:var(--red)">Erreur : ' + e.message + '</div>';
      });
  }

  function closeFileViewer() {
    const ov = document.getElementById("dash-file-popup-overlay");
    const popup = document.getElementById("dash-file-popup");
    if (ov) ov.classList.remove("open");
    if (popup) popup.classList.remove("open");
  }

  /* ───────── Mission detail panel ───────── */
  async function buildMissionPanel(panel, m) {
    // Header
    const hdr = el("div", { class: "mp-header" });
    const left = el("div", { class: "mp-header-left" });
    const badge = el("div", { class: "mp-status-badge " + m.status, text: m.status.toUpperCase() });
    const info = el("div");
    info.appendChild(el("div", { class: "mp-title", text: m.title }));
    info.appendChild(el("div", { class: "mp-sub", text: m.id + " · " + m.sub }));
    left.appendChild(badge); left.appendChild(info);
    const closeBtn = el("button", { class: "panel-close", text: "✕" });
    closeBtn.addEventListener("click", closePanel);
    hdr.appendChild(left); hdr.appendChild(closeBtn);
    panel.appendChild(hdr);

    const body = el("div", { class: "panel-body" });

    // Progress bar
    const progSec = el("div", { class: "panel-section" });
    const progBar = el("div", { class: "mp-prog-bar" });
    progBar.appendChild(el("div", { style: { width: Math.round((m.prog||0)*100) + "%" } }));
    progSec.appendChild(progBar);
    progSec.appendChild(el("div", { class: "mp-prog-label", text: m.cur != null ? m.cur + " / " + (m.tot||"?") + " étapes" : "En cours…" }));
    body.appendChild(progSec);

    body.appendChild(el("div", { class: "mp-loading", text: "Chargement des détails…" }));
    panel.appendChild(body);

    // Fetch detailed data
    let detail = null, files = [];
    try { [detail, files] = await Promise.all([
      J.api.get("/api/projects/" + m.rawId),
      J.api.get("/api/projects/" + m.rawId + "/files"),
    ]); } catch (_) {}

    // Remove loading indicator
    const loadEl = body.querySelector(".mp-loading");
    if (loadEl) loadEl.remove();

    // Steps
    if (detail && detail.steps && detail.steps.length) {
      const stepSec = el("div", { class: "panel-section" });
      stepSec.appendChild(el("div", { class: "panel-section-title", text: "Étapes" }));
      detail.steps.forEach((s, i) => {
        const row = el("div", { class: "mp-step mp-step--" + (s.status || "pending") });
        const num = el("div", { class: "mp-step-num", text: String(i + 1).padStart(2, "0") });
        const content = el("div", { class: "mp-step-content" });
        content.appendChild(el("div", { class: "mp-step-title", text: s.title || s.id }));
        const statusBadge = el("span", { class: "mp-step-status mp-step-status--" + (s.status || "pending"), text: s.status || "pending" });
        content.appendChild(statusBadge);
        if (s.output) {
          const out = el("div", { class: "mp-step-output", text: s.output.slice(0, 300) + (s.output.length > 300 ? "…" : "") });
          content.appendChild(out);
        }
        if (s.error) {
          const err = el("div", { class: "mp-step-error", text: s.error.slice(0, 200) });
          content.appendChild(err);
        }
        row.appendChild(num); row.appendChild(content);
        stepSec.appendChild(row);
      });
      body.appendChild(stepSec);
    }

    // Files
    if (files && files.length) {
      const fileSec = el("div", { class: "panel-section" });
      fileSec.appendChild(el("div", { class: "panel-section-title", text: "Fichiers produits" }));
      files.forEach(f => {
        const row = el("div", { class: "mp-file-row" });
        const icon = el("span", { class: "mp-file-icon", text: f.endsWith(".md") ? "📄" : f.endsWith(".json") ? "📋" : f.endsWith(".py") || f.endsWith(".js") ? "📝" : "📁" });
        const name = el("button", { class: "mp-file-name", text: f });
        name.addEventListener("click", () => openFileViewer(m.rawId, f));
        row.appendChild(icon); row.appendChild(name);
        fileSec.appendChild(row);
      });
      body.appendChild(fileSec);
    } else if (detail) {
      const fileSec = el("div", { class: "panel-section" });
      fileSec.appendChild(el("div", { class: "panel-section-title", text: "Fichiers produits" }));
      fileSec.appendChild(el("div", { class: "j-empty", text: "Aucun fichier produit" }));
      body.appendChild(fileSec);
    }

    // Actions
    if (m.rawId) {
      const actSec = el("div", { class: "panel-section" });
      actSec.appendChild(el("div", { class: "panel-section-title", text: "Actions" }));
      const actRow = el("div", { class: "mp-act-row" });
      const retryBtn = el("button", { class: "m-btn", text: "Retry" });
      retryBtn.addEventListener("click", async () => {
        retryBtn.textContent = "…"; retryBtn.disabled = true;
        try {
          await J.api.post("/api/projects/" + m.rawId + "/retry");
          J.notify({ kind: "success", text: "Relancée" });
          closePanel();
          renderMissions();
        } catch (e) { J.notify({ kind: "error", text: e.message }); retryBtn.textContent = "Retry"; retryBtn.disabled = false; }
      });
      actRow.appendChild(retryBtn);
      actSec.appendChild(actRow);
      body.appendChild(actSec);
    }
  }

  /* ───────── Missions ───────── */
  async function renderMissions() {
    const { active, ended } = await loadMissions();
    const wrap = el("div", { style: { display: "flex", flexDirection: "column", gap: "44px" } });

    const activeList = el("div");
    if (!active.length) {
      activeList.appendChild(el("div", { class: "j-empty", text: "Aucune mission active" }));
    } else {
      active.forEach(m => activeList.appendChild(renderMissionRow(m)));
    }
    wrap.appendChild(ghostSec("En cours", active.length + " active" + (active.length > 1 ? "s" : ""), null, activeList));

    if (ended.length) {
      const endedList = el("div");
      ended.forEach(m => endedList.appendChild(renderMissionRow(m)));
      wrap.appendChild(ghostSec("Terminées", ended.length + " mission" + (ended.length > 1 ? "s" : ""), null, endedList));
    }

    const page = pageWrapper(
      "missions",
      "Les missions en vol",
      '<span class="v">' + active.length + '</span> actives · <span class="v">' + ended.length + '</span> terminées',
      wrap
    );
    root.innerHTML = "";
    root.appendChild(page);
  }

  function renderMissionRow(m) {
    const isEnded = m.status === "done" || m.status === "failed" || m.status === "killed";
    let cls = "mission-row mission-row--clickable";
    if (isEnded) cls += " mission-row--ended";
    if (m.status === "failed") cls += " mission-row--failed";
    const row = el("div", { class: cls });
    row.addEventListener("click", () => openPanel(buildMissionPanel, m));

    const idCol = el("div");
    idCol.appendChild(el("div", { class: "m-id t-mono", text: m.id }));
    idCol.appendChild(el("div", { class: "m-status " + m.status, text: m.status.toUpperCase() }));
    row.appendChild(idCol);

    const titleCol = el("div");
    titleCol.appendChild(el("div", { class: "m-title", text: m.title }));
    titleCol.appendChild(el("div", { class: "m-sub",   text: m.sub }));
    row.appendChild(titleCol);

    const progCol = el("div");
    const bar = el("div", { class: "m-prog-bar" });
    bar.appendChild(el("div", { style: { width: Math.round((m.prog||0)*100)+"%" } }));
    progCol.appendChild(bar);
    const meta = el("div", { class: "m-prog-meta" });
    meta.appendChild(el("span", { text: m.cur != null ? m.cur + " / " + (m.tot||"?") + " étapes" : "En cours" }));
    progCol.appendChild(meta);
    row.appendChild(progCol);

    const actCol = el("div", { class: "m-actions" });
    actCol.appendChild(el("span", { class: "m-detail-hint", text: "Détails →" }));
    row.appendChild(actCol);
    return row;
  }

  /* ───────── Tâches — helper partagé ───────── */
  function buildTaskRow(t, list) {
    const row = el("div", { class: "task-row " + (t.done ? "done" : "") });
    const chk = el("div", { class: "task-check" });
    const txt = el("div", { style: { flex: "1", minWidth: "0" } });
    txt.appendChild(el("div", { class: "task-label", text: t.label }));
    txt.appendChild(el("div", { class: "task-src",   text: t.src }));

    const del = el("div", { class: "task-del", text: "×" });
    del.title = "Supprimer";
    del.addEventListener("click", async (e) => {
      e.stopPropagation();
      row.style.opacity = "0.4";
      try {
        await J.api.delete("/api/tasks/" + t.id);
        row.remove();
        if (list && !list.querySelectorAll(".task-row").length) {
          const empty = el("div", { class: "j-empty", text: "Aucune tâche" });
          const addBar = list.querySelector(".add-bar");
          if (addBar) list.insertBefore(empty, addBar);
          else list.appendChild(empty);
        }
      } catch (_) { row.style.opacity = ""; }
    });

    chk.addEventListener("click", async (e) => {
      e.stopPropagation();
      const newDone = !t.done;
      t.done = newDone;
      row.classList.toggle("done", newDone);
      J.api.patch("/api/tasks/" + t.id, { done: newDone }).catch(() => {
        t.done = !newDone;
        row.classList.toggle("done", !newDone);
      });
    });

    row.appendChild(chk); row.appendChild(txt); row.appendChild(del);
    return row;
  }

  /* ───────── Tâches ───────── */
  async function renderTaches() {
    let tasks = [];
    try {
      const raw = await J.api.get("/api/tasks");
      tasks = (raw.tasks || raw || []).map(t => ({
        id: t.id,
        label: t.title || t.label || t.text || "",
        done: !!(t.done || t.checked),
        src: t.source || "NOTION",
      })).filter(t => t.label);
    } catch (_) {}

    const list = el("div");

    if (!tasks.length) {
      list.appendChild(el("div", { class: "j-empty", text: "Aucune tâche" }));
    } else {
      tasks.forEach(t => list.appendChild(buildTaskRow(t, list)));
    }

    const addBar = el("div", { class: "add-bar" });
    addBar.appendChild(el("span", { text: "+" }));
    addBar.appendChild(el("span", { text: "Nouvelle tâche" }));
    addBar.addEventListener("click", () => {
      const input = document.createElement("input");
      input.type = "text";
      input.placeholder = "Titre de la tâche…";
      input.className = "task-new-input";
      addBar.style.display = "none";
      list.insertBefore(input, addBar);
      input.focus();

      let submitted = false;
      async function submit() {
        if (submitted) return;
        submitted = true;
        const text = input.value.trim();
        input.remove();
        addBar.style.display = "";
        if (!text) return;
        try {
          const created = await J.api.post("/api/tasks", { text });
          const t = { id: created.id, label: created.text, done: false, src: "NOTION" };
          const empty = list.querySelector(".j-empty");
          if (empty) empty.remove();
          list.insertBefore(buildTaskRow(t, list), addBar);
        } catch (_) {}
      }

      input.addEventListener("keydown", e => {
        if (e.key === "Enter") { e.preventDefault(); submit(); }
        if (e.key === "Escape") { submitted = true; input.remove(); addBar.style.display = ""; }
      });
      input.addEventListener("blur", submit);
    });
    list.appendChild(addBar);

    const done = tasks.filter(t => t.done).length;
    const wrap = el("div");
    wrap.appendChild(ghostSec("Tâches du jour", "Notion", null, list));

    const page = pageWrapper(
      "taches",
      "Les choses à faire",
      tasks.length ? done + " / " + tasks.length + " terminées" : null,
      wrap
    );
    root.innerHTML = "";
    root.appendChild(page);
  }

  /* ───────── Analytics ───────── */
  async function renderAnalytics() {
    let analytics = null;
    try {
      const [activeRes, dataRes] = await Promise.all([
        J.api.get("/api/analytics/active"),
        J.api.get("/api/analytics/data"),
      ]);
      analytics = { active: activeRes.widgets||[], data: dataRes.widgets||{} };
    } catch (_) {}

    const wrap = el("div", { style: { display: "flex", flexDirection: "column", gap: "44px" } });

    // Jarvis KPIs from /api/analytics/jarvis
    let jarvisData = null;
    try { jarvisData = await J.api.get("/api/analytics/jarvis?days=30"); } catch (_) {}

    if (jarvisData) {
      const kpiGrid = el("div", { class: "kpi-strip" });
      const kpis = [
        { lbl: "Requêtes 30j", val: jarvisData.total_calls||0, unit: "" },
        { lbl: "Coût 30j",     val: jarvisData.total_cost ? "$"+jarvisData.total_cost.toFixed(2) : "—", unit: "" },
        { lbl: "Tokens",       val: jarvisData.total_tokens||0, unit: "" },
      ];
      kpis.forEach(k => {
        const card = el("div", { class: "kpi-card" });
        card.appendChild(el("div", { class: "kpi-lbl", text: k.lbl }));
        card.appendChild(el("div", { class: "kpi-val", text: typeof k.val === "number" ? J.fmt.num(k.val) : k.val }));
        kpiGrid.appendChild(card);
      });
      wrap.appendChild(kpiGrid);
    } else {
      wrap.appendChild(el("div", { class: "j-empty", text: "Aucune donnée analytics disponible" }));
    }


    const page = pageWrapper("analytics", "Métriques & signaux", null, wrap);
    root.innerHTML = "";
    root.appendChild(page);
  }

  /* ───────── Router ───────── */
  const RENDERERS = {
    apercu:      renderApercu,
    initiatives: renderInitiatives,
    missions:    renderMissions,
    taches:      renderTaches,
    analytics:   renderAnalytics,
  };

  function navigate(pageId) {
    _activePage = pageId;
    // Update rooms nav
    const nav = document.getElementById("j-rooms-pages");
    if (nav) {
      Array.from(nav.querySelectorAll("button")).forEach(b => {
        b.dataset.active = b.querySelector(".lbl") && b.querySelector(".lbl").textContent === PAGES.find(p=>p.id===pageId)?.label ? "true" : "false";
      });
      // More reliable: check by index
      const btns = Array.from(nav.querySelectorAll("button"));
      const idx = PAGES.findIndex(p => p.id === pageId);
      btns.forEach((b, i) => b.dataset.active = i === idx ? "true" : "false");
    }
    const fn = RENDERERS[pageId];
    if (fn) { root.innerHTML = ""; fn(); }
  }

  /* ───────── Init ───────── */
  J.mountAtmosphere();

  J.mountRooms({
    mode: "workspace",
    pages: PAGES,
    activePage: _activePage,
    onNav: (id) => navigate(id),
  });

  J.registerCommands(PAGES.map(p => ({
    kind: "nav", id: "ws-" + p.id, group: "Pilotage",
    title: p.label, glyph: "→",
    run: () => navigate(p.id),
  })));

  // Kick off
  renderApercu();
})();
