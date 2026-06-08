/* capabilities.js — Atelier (Capacités) v2
 * 9 sous-pages : Intégrations · Skills · Routines · Vues · Store · Écosystème · Appareils · Fils · Mémoire
 */
(function () {
  "use strict";
  const J = window.Jarvis, el = J.el;

  const PAGES = [
    { id: "integrations", label: "Intégrations" },
    { id: "skills",       label: "Skills" },
    { id: "routines",     label: "Routines" },
    { id: "vues",         label: "Vues" },
    { id: "store",        label: "Store" },
    { id: "ecosysteme",   label: "Écosystème" },
    { id: "appareils",    label: "Appareils" },
    { id: "fils",         label: "Fils" },
    { id: "memoire",      label: "Mémoire" },
  ];

  let _activePage = "integrations";
  const root = document.getElementById("page-root");

  /* ─── Config des connecteurs ─── */
  const CONNECTOR_CONFIG = {
    "Gmail":              { kind: "oauth", url: "/api/google/auth/gmail" },
    "Google Calendar":    { kind: "oauth", url: "/api/google/auth/calendar" },
    "Spotify":            { kind: "oauth", url: "/api/spotify/auth" },
    "Deezer":             { kind: "oauth", url: "/api/deezer/auth" },
    "Notion":             { kind: "key",   keys: [{ key: "NOTION_TOKEN",         label: "Token d'intégration", secret: true }] },
    "Anthropic (Claude)": { kind: "key",   keys: [{ key: "ANTHROPIC_API_KEY",    label: "Clé API Anthropic",   secret: true }] },
    "ElevenLabs":         { kind: "key",   keys: [{ key: "ELEVENLABS_API_KEY",   label: "Clé API ElevenLabs",  secret: true }] },
    "OpenAI":             { kind: "key",   keys: [{ key: "OPENAI_API_KEY",       label: "Clé API OpenAI",      secret: true }] },
    "Google (API Key)":   { kind: "key",   keys: [{ key: "GOOGLE_API_KEY",       label: "Clé API Google",      secret: true }] },
    "LiveKit":            { kind: "key",   keys: [
      { key: "LIVEKIT_URL",        label: "URL",        secret: false },
      { key: "LIVEKIT_API_KEY",    label: "API Key",    secret: true },
      { key: "LIVEKIT_API_SECRET", label: "API Secret", secret: true },
    ]},
    "Deepgram":           { kind: "key",   keys: [{ key: "DEEPGRAM_API_KEY",     label: "Clé API Deepgram",    secret: true }] },
    "Mistral":            { kind: "key",   keys: [{ key: "MISTRAL_API_KEY",      label: "Clé API Mistral",     secret: true }] },
    // ── Messagerie ───────────────────────────────────────────────────────────
    "Telegram":           { kind: "messaging", keys: [
      { key: "TELEGRAM_BOT_TOKEN", label: "Bot Token",              secret: true,  hint: "@BotFather → /newbot" },
      { key: "TELEGRAM_OWNER_ID",  label: "Ton User ID",            secret: false, hint: "@userinfobot → envoie un message" },
      { key: "TELEGRAM_ENABLED",   label: "Activer le bot",         secret: false, type: "toggle" },
    ]},
    "Discord":            { kind: "messaging", keys: [
      { key: "DISCORD_BOT_TOKEN",  label: "Bot Token",              secret: true,  hint: "discord.com/developers → Bot" },
      { key: "DISCORD_OWNER_ID",   label: "Ton User ID",            secret: false, hint: "Profil → Copier l'identifiant" },
      { key: "DISCORD_ENABLED",    label: "Activer le bot",         secret: false, type: "toggle" },
    ]},
    "WhatsApp":           { kind: "stub", note: "Bientôt disponible via Twilio ou WhatsApp Business API (WABA)." },
  };

  /* ─── Skills reclassifiés en routines ─── */
  const SKILL_AS_ROUTINE = new Set(["mode-streameur"]);

  /* ─── Registre de config statique ─── */
  const CONFIGS = {
    "fusion360": {
      fullDesc: "Contrôle Autodesk Fusion 360 via MCP HTTP — scripts Python API, lecture et modification de designs 3D, undo/redo, export et lancement d'actions Fusion directement depuis Jarvis.",
      fields: [
        { key: "FUSION360_CLIENT_ID",     label: "Client ID",      hint: "Depuis app.autodesk.com", secret: false },
        { key: "FUSION360_CLIENT_SECRET", label: "Client Secret",  hint: "", secret: true },
        { key: "FUSION360_MCP_URL",       label: "MCP Server URL", hint: "http://localhost:8765", secret: false },
      ],
    },
    "bambulab-printer": {
      fullDesc: "Contrôle l'imprimante 3D BambuLab — slice STL, lancement et suivi d'impression via MQTT et API Cloud BambuLab. Compatible X1C, P1S, A1.",
      fields: [
        { key: "BAMBULAB_API_KEY", label: "Clé API Bambulab",     hint: "makerworld.bambulab.com", secret: true },
        { key: "BAMBULAB_SERIAL",  label: "Numéro de série",      hint: "XXXXXXXXXX", secret: false },
        { key: "BAMBULAB_IP",      label: "IP locale imprimante", hint: "192.168.1.x", secret: false },
      ],
    },
    "mode-streameur": {
      isRoutine: true,
      fullDesc: "Lance l'environnement stream complet — OBS Studio, scènes préconfigurées, overlay Twitch. Jarvis orchestre le démarrage, gère les transitions et t'alerte si une app ne répond pas.",
      appChecks: ["OBS Studio", "Twitch"],
      fields: [
        { key: "TWITCH_CLIENT_ID",     label: "Twitch Client ID",       hint: "dev.twitch.tv", secret: false },
        { key: "TWITCH_CLIENT_SECRET", label: "Twitch Client Secret",   hint: "", secret: true },
        { key: "OBS_WS_HOST",          label: "OBS WebSocket host",     hint: "localhost:4455", secret: false },
        { key: "OBS_WS_PASSWORD",      label: "OBS WebSocket password", hint: "", secret: true },
      ],
    },
  };

  /* ─────────────────────────────────────────
     DETAIL PANEL
  ───────────────────────────────────────── */
  let _panelKeyListener = null;

  function initPanel() {
    if (document.getElementById("detail-panel")) return;
    const overlay = el("div", { id: "detail-overlay" });
    overlay.addEventListener("click", closePanel);
    document.body.appendChild(overlay);
    document.body.appendChild(el("div", { id: "detail-panel" }));
    _panelKeyListener = e => { if (e.key === "Escape") closePanel(); };
    document.addEventListener("keydown", _panelKeyListener);
  }

  function closePanel() {
    const panel = document.getElementById("detail-panel");
    const overlay = document.getElementById("detail-overlay");
    if (panel) panel.classList.remove("open");
    if (overlay) overlay.classList.remove("open");
  }

  function openPanel(buildFn, data) {
    initPanel();
    const panel = document.getElementById("detail-panel");
    panel.innerHTML = "";
    buildFn(panel, data);
    const overlay = document.getElementById("detail-overlay");
    requestAnimationFrame(() => {
      overlay.classList.add("open");
      panel.classList.add("open");
    });
  }

  function makeCloseBtn() {
    const btn = el("button", { class: "panel-close", text: "✕" });
    btn.addEventListener("click", closePanel);
    return btn;
  }

  function appendConfigSection(panel, displayName, cfg) {
    if (!cfg.fields || !cfg.fields.length) return;
    const sec = el("div", { class: "panel-section" });
    sec.appendChild(el("div", { class: "panel-section-title", text: "Configuration" }));
    const inputs = [];
    cfg.fields.forEach(f => {
      const fw = el("div", { class: "panel-field" });
      fw.appendChild(el("div", { class: "panel-field-label", text: f.label }));
      const inp = el("input", { class: "panel-field-input", type: f.secret ? "password" : "text", placeholder: f.hint || "" });
      J.api.get("/api/settings").then(ss => {
        const v = (ss.api_keys || {})[f.key] || "";
        if (v) inp.value = v;
      }).catch(() => {});
      fw.appendChild(inp);
      inputs.push({ key: f.key, inp });
      sec.appendChild(fw);
    });
    const saveBtn = el("button", { class: "panel-save-btn", text: "Sauvegarder" });
    saveBtn.addEventListener("click", async () => {
      saveBtn.textContent = "…"; saveBtn.disabled = true;
      try {
        for (const { key, inp } of inputs) {
          if (inp.value) await J.api.post("/api/settings/update", { key, value: inp.value });
        }
        J.notify({ kind: "success", text: displayName + " · config sauvegardée" });
      } catch (e) {
        J.notify({ kind: "error", text: e.message });
      }
      saveBtn.textContent = "Sauvegarder"; saveBtn.disabled = false;
    });
    sec.appendChild(saveBtn);
    panel.appendChild(sec);
  }

  /* ─── Skill panel ─── */
  function buildSkillPanel(panel, s) {
    const cfg = CONFIGS[s.name] || {};
    const glyph3 = (s.name || "?").slice(0, 3).toUpperCase();

    const hdr = el("div", { class: "panel-header" });
    const left = el("div", { class: "panel-header-left" });
    const glyph = el("div", { class: "panel-glyph skill", text: glyph3 });
    const info = el("div");
    info.appendChild(el("div", { class: "panel-name", text: s.name }));
    info.appendChild(el("div", { class: "panel-type-badge", text: "SKILL" }));
    left.appendChild(glyph); left.appendChild(info);
    hdr.appendChild(left); hdr.appendChild(makeCloseBtn());
    panel.appendChild(hdr);

    const body = el("div", { class: "panel-body" });
    body.appendChild(el("div", { class: "panel-desc", text: cfg.fullDesc || s.description || "—" }));

    const stSec = el("div", { class: "panel-section" });
    stSec.appendChild(el("div", { class: "panel-section-title", text: "Statut" }));
    const stRow = el("div", { class: "panel-check-row" });
    stRow.appendChild(el("span", { class: "panel-check-label", text: "Configuré" }));
    stRow.appendChild(el("span", {
      class: "panel-check-status " + (s.configured !== false ? "ok" : "ko"),
      text: s.configured !== false ? "Actif" : "Non configuré",
    }));
    stSec.appendChild(stRow);
    body.appendChild(stSec);

    appendConfigSection(body, s.name, cfg);
    panel.appendChild(body);
  }

  /* ─── Vue panel ─── */
  function buildViewPanel(panel, v) {
    const glyphText = (v.label || v.name || "?").slice(0, 3).toUpperCase();

    const hdr = el("div", { class: "panel-header" });
    const left = el("div", { class: "panel-header-left" });
    const glyph = el("div", { class: "panel-glyph skill", text: glyphText });
    const info = el("div");
    info.appendChild(el("div", { class: "panel-name", text: v.label || v.name }));
    info.appendChild(el("div", { class: "panel-type-badge", text: "VUE" }));
    left.appendChild(glyph); left.appendChild(info);
    hdr.appendChild(left); hdr.appendChild(makeCloseBtn());
    panel.appendChild(hdr);

    const body = el("div", { class: "panel-body" });
    if (v.description) body.appendChild(el("div", { class: "panel-desc", text: v.description }));

    // Statut actif
    const registered = window.top?.Jarvis?.views?.list() || [];
    const isActive = registered.some(rv => v.name.includes(rv.id));
    const stSec = el("div", { class: "panel-section" });
    stSec.appendChild(el("div", { class: "panel-section-title", text: "Statut" }));
    const stRow = el("div", { class: "panel-check-row" });
    stRow.appendChild(el("span", { class: "panel-check-label", text: "État" }));
    stRow.appendChild(el("span", {
      class: "panel-check-status " + (isActive ? "ok" : "ko"),
      text: isActive ? "Active" : "Installée (rechargement requis)",
    }));
    stSec.appendChild(stRow);
    if (v.version) {
      const vRow = el("div", { class: "panel-check-row" });
      vRow.appendChild(el("span", { class: "panel-check-label", text: "Version" }));
      vRow.appendChild(el("span", { class: "panel-check-status ok", text: v.version }));
      stSec.appendChild(vRow);
    }
    body.appendChild(stSec);

    // Capacités
    if (v.capabilities?.length) {
      const capSec = el("div", { class: "panel-section" });
      capSec.appendChild(el("div", { class: "panel-section-title", text: "Capacités" }));
      v.capabilities.forEach(c => {
        const row = el("div", { class: "panel-check-row" });
        row.appendChild(el("span", { class: "panel-check-label", text: c }));
        capSec.appendChild(row);
      });
      body.appendChild(capSec);
    }

    // Désinstaller
    const actSec = el("div", { class: "panel-section" });
    const uninstBtn = el("button", {
      class: "panel-save-btn",
      text: "Désinstaller",
      style: { background: "rgba(255,80,80,0.08)", borderColor: "rgba(255,80,80,0.25)", color: "rgba(255,120,120,0.85)" },
    });
    uninstBtn.addEventListener("click", async () => {
      uninstBtn.textContent = "…"; uninstBtn.disabled = true;
      try {
        await J.api.delete("/api/skills/uninstall/" + v.name);
        J.notify({ kind: "success", text: (v.label || v.name) + " désinstallé" });
        closePanel();
        renderVues();
      } catch (err) {
        J.notify({ kind: "error", text: err.message });
        uninstBtn.textContent = "Désinstaller"; uninstBtn.disabled = false;
      }
    });
    actSec.appendChild(uninstBtn);
    body.appendChild(actSec);
    panel.appendChild(body);
  }

  /* ─── Routine panel ─── */
  function buildRoutinePanel(panel, p) {
    const cfg = CONFIGS[p.name] || {};
    const glyph3 = (p.name || "?").slice(0, 3).toUpperCase();

    const hdr = el("div", { class: "panel-header" });
    const left = el("div", { class: "panel-header-left" });
    const glyph = el("div", { class: "panel-glyph routine", text: glyph3 });
    const info = el("div");
    info.appendChild(el("div", { class: "panel-name", text: p.label || p.name }));
    info.appendChild(el("div", { class: "panel-type-badge routine", text: "ROUTINE" }));
    left.appendChild(glyph); left.appendChild(info);
    hdr.appendChild(left); hdr.appendChild(makeCloseBtn());
    panel.appendChild(hdr);

    const body = el("div", { class: "panel-body" });
    body.appendChild(el("div", { class: "panel-desc", text: cfg.fullDesc || p.description || "—" }));

    if (cfg.appChecks && cfg.appChecks.length) {
      const chkSec = el("div", { class: "panel-section" });
      chkSec.appendChild(el("div", { class: "panel-section-title", text: "Applications requises" }));
      cfg.appChecks.forEach(appName => {
        const row = el("div", { class: "panel-check-row" });
        row.appendChild(el("span", { class: "panel-check-label", text: appName }));
        row.appendChild(el("span", { class: "panel-check-status ko", text: "Non vérifié" }));
        chkSec.appendChild(row);
      });
      body.appendChild(chkSec);
    }

    if (p.platforms && p.platforms.length) {
      const platSec = el("div", { class: "panel-section" });
      platSec.appendChild(el("div", { class: "panel-section-title", text: "Plateformes" }));
      const platRow = el("div", { style: { display: "flex", gap: "6px", flexWrap: "wrap" } });
      p.platforms.forEach(pl => platRow.appendChild(el("span", { class: "preset-platform", text: pl })));
      platSec.appendChild(platRow);
      body.appendChild(platSec);
    }

    const runSec = el("div", { class: "panel-section" });
    runSec.appendChild(el("div", { class: "panel-section-title", text: "Lancer" }));
    const runBtn = el("button", { class: "panel-run-btn", text: "▶ Lancer la routine" });
    runBtn.addEventListener("click", async () => {
      runBtn.textContent = "…"; runBtn.disabled = true;
      try {
        await J.api.post("/api/presets/" + p.name + "/execute");
        J.notify({ kind: "success", text: (p.label || p.name) + " lancée" });
      } catch (e) {
        J.notify({ kind: "error", text: e.message });
      }
      runBtn.textContent = "▶ Lancer la routine"; runBtn.disabled = false;
    });
    runSec.appendChild(runBtn);
    body.appendChild(runSec);

    appendConfigSection(body, p.label || p.name, cfg);
    panel.appendChild(body);
  }

  /* ─── Ambiance panel ─── */
  function buildAmbiancePanel(panel, a) {
    const hdr = el("div", { class: "panel-header" });
    const left = el("div", { class: "panel-header-left" });
    const glyph = el("div", { class: "panel-glyph ambiance", text: (a.name || "").slice(0, 3).toUpperCase() });
    const info = el("div");
    info.appendChild(el("div", { class: "panel-name", text: a.name }));
    info.appendChild(el("div", { class: "panel-type-badge ambiance", text: "AMBIANCE" }));
    left.appendChild(glyph); left.appendChild(info);
    hdr.appendChild(left); hdr.appendChild(makeCloseBtn());
    panel.appendChild(hdr);

    const body = el("div", { class: "panel-body" });
    body.appendChild(el("div", { class: "panel-desc", text: a.desc || "—" }));

    const actSec = el("div", { class: "panel-section" });
    actSec.appendChild(el("div", { class: "panel-section-title", text: "Activer" }));
    const actBtn = el("button", { class: "panel-run-btn", text: "Activer cette ambiance" });
    actBtn.addEventListener("click", async () => {
      actBtn.textContent = "…"; actBtn.disabled = true;
      try {
        await J.api.post("/api/ambiances/" + a.id, {});
        J.notify({ kind: "success", text: a.name + " · activée" });
      } catch (_) {}
      actBtn.textContent = "Activer cette ambiance"; actBtn.disabled = false;
    });
    actSec.appendChild(actBtn);
    body.appendChild(actSec);
    panel.appendChild(body);
  }

  /* ─────────────────────────────────────────
     PAGE HELPERS
  ───────────────────────────────────────── */
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
    if (meta) { const m = el("div", { class: "page-head-meta" }); m.innerHTML = meta; head.appendChild(m); }
    wrap.appendChild(head);

    const pb = el("div", { class: "page-body" });
    pb.appendChild(body);
    wrap.appendChild(pb);
    return wrap;
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function openCorrectionModal(fact, onDone) {
    /* Modal minimal — overlay + carte. Pas de dépendance externe. */
    const ov = el("div");
    ov.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.7);display:flex;align-items:center;justify-content:center;z-index:9999;";
    const card = el("div");
    card.style.cssText = "background:#0a0a0a;border:1px solid #2a2a2a;border-radius:10px;padding:24px;max-width:540px;width:92%;box-shadow:0 20px 60px rgba(0,0,0,.6);";
    card.innerHTML = '<div style="font-family:Space Grotesk,Geist,sans-serif;font-size:18px;margin-bottom:6px;color:#d4af6a;">Corriger un fact</div>'
      + '<div style="font-size:12px;color:#888;margin-bottom:18px;">Trace un event <code>human_correction</code> en audit immuable (§6.7).</div>'
      + '<div style="font-size:13px;margin-bottom:14px;padding:10px;background:rgba(255,255,255,.04);border-radius:6px;">'
      + '<span style="color:#aaa">' + escapeHtml(fact.subject) + ' · </span>'
      + '<span style="color:#d4af6a">' + escapeHtml(fact.predicate) + '</span> · '
      + '<span>' + escapeHtml(fact.object) + '</span></div>';

    const labelObj = el("label", { text: "Nouvel objet (vide = inchangé)" });
    labelObj.style.cssText = "display:block;font-size:11px;color:#888;margin-bottom:4px;text-transform:uppercase;letter-spacing:.08em;";
    card.appendChild(labelObj);
    const inObj = el("input"); inObj.type = "text"; inObj.placeholder = fact.object;
    inObj.style.cssText = "width:100%;padding:8px 10px;background:#1a1a1a;border:1px solid #333;border-radius:5px;color:#eee;margin-bottom:14px;font-size:13px;font-family:Geist,sans-serif;";
    card.appendChild(inObj);

    const labelSt = el("label", { text: "Nouveau statut" });
    labelSt.style.cssText = "display:block;font-size:11px;color:#888;margin-bottom:4px;text-transform:uppercase;letter-spacing:.08em;";
    card.appendChild(labelSt);
    const inSt = el("select");
    ["", "active", "superseded", "archived", "needs_review"].forEach(v => {
      const o = el("option"); o.value = v; o.textContent = v || "(inchangé)"; inSt.appendChild(o);
    });
    inSt.style.cssText = "width:100%;padding:8px 10px;background:#1a1a1a;border:1px solid #333;border-radius:5px;color:#eee;margin-bottom:14px;font-size:13px;";
    card.appendChild(inSt);

    const labelTxt = el("label", { text: "Motif" });
    labelTxt.style.cssText = "display:block;font-size:11px;color:#888;margin-bottom:4px;text-transform:uppercase;letter-spacing:.08em;";
    card.appendChild(labelTxt);
    const inTxt = el("textarea"); inTxt.rows = 2; inTxt.placeholder = "Pourquoi cette correction…";
    inTxt.style.cssText = "width:100%;padding:8px 10px;background:#1a1a1a;border:1px solid #333;border-radius:5px;color:#eee;margin-bottom:18px;font-size:13px;font-family:Geist,sans-serif;resize:vertical;";
    card.appendChild(inTxt);

    const row = el("div"); row.style.cssText = "display:flex;justify-content:flex-end;gap:8px;";
    const cancel = el("button", { class: "m-btn", text: "Annuler" });
    cancel.addEventListener("click", () => ov.remove());
    const save = el("button", { class: "m-btn m-btn--save", text: "Appliquer" });
    save.addEventListener("click", async () => {
      save.disabled = true; save.textContent = "…";
      try {
        const body = { target_fact_id: fact.id, correction_text: inTxt.value || "" };
        if (inObj.value.trim()) body.new_object = inObj.value.trim();
        if (inSt.value) body.new_status = inSt.value;
        await J.api.post("/api/memory/correct", body);
        J.notify({ kind: "success", text: "Correction appliquée — event tracé en audit" });
        ov.remove();
        if (onDone) onDone();
      } catch (e) {
        J.notify({ kind: "error", text: e.message });
        save.disabled = false; save.textContent = "Appliquer";
      }
    });
    row.appendChild(cancel); row.appendChild(save);
    card.appendChild(row);

    ov.appendChild(card);
    ov.addEventListener("click", (ev) => { if (ev.target === ov) ov.remove(); });
    document.body.appendChild(ov);
    inObj.focus();
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

  /* ─────────────────────────────────────────
     01 Intégrations
  ───────────────────────────────────────── */
  async function renderIntegrations() {
    let connectors = [];
    try { connectors = await J.api.get("/api/settings/connectors"); } catch (_) {}

    const list = el("div", { class: "cn-list" });

    // Sépare les connecteurs "services" des connecteurs "messagerie"
    const services  = connectors.filter(c => c.group !== "messaging");
    const messaging = connectors.filter(c => c.group === "messaging");

    function renderConnectorRow(c) {
      const cfg = CONNECTOR_CONFIG[c.name] || { kind: "key", keys: [] };
      const status = c.status || "off";

      const row = el("div", { class: "cn-row" });
      row.appendChild(el("div", { class: "cn-dot " + (status === "soon" ? "off" : status) }));

      const info = el("div", { class: "cn-info" });
      info.appendChild(el("div", { class: "cn-name", text: c.name }));
      info.appendChild(el("div", { class: "cn-sub", text: c.sub || "" }));
      row.appendChild(info);

      const right = el("div", { class: "cn-right" });
      if (status === "on") {
        right.appendChild(el("span", { class: "cn-badge on", text: "Connecté" }));
      } else if (status === "expired") {
        right.appendChild(el("span", { class: "cn-badge expired", text: "Expiré" }));
        const btn = el("button", { class: "cn-btn", text: "Reconnecter" });
        btn.addEventListener("click", () => triggerConnect(c, cfg, expand));
        right.appendChild(btn);
      } else if (status === "soon") {
        right.appendChild(el("span", { class: "cn-badge", text: "Bientôt" }));
      } else {
        const btn = el("button", { class: "cn-btn", text: "Configurer →" });
        btn.addEventListener("click", () => triggerConnect(c, cfg, expand));
        right.appendChild(btn);
      }
      row.appendChild(right);
      list.appendChild(row);

      const expand = el("div", { class: "cn-expand" });
      list.appendChild(expand);
    }

    services.forEach(renderConnectorRow);

    if (messaging.length) {
      const sep = el("div", { class: "cn-section-sep", text: "Messagerie" });
      list.appendChild(sep);
      messaging.forEach(renderConnectorRow);
    }

    const activeCount = connectors.filter(c => c.status === "on").length;
    const wrap = el("div");
    wrap.appendChild(ghostSec(
      "Intégrations",
      activeCount + " actives · " + connectors.length + " total",
      null, list
    ));

    const page = pageWrapper("integrations", "Tes connecteurs", null, wrap);
    root.innerHTML = ""; root.appendChild(page);
  }

  function triggerConnect(c, cfg, expandEl) {
    if (cfg.kind === "oauth") {
      window.location.href = cfg.url;
      return;
    }
    if (cfg.kind === "stub") {
      if (expandEl.classList.contains("open")) {
        expandEl.classList.remove("open");
        expandEl.innerHTML = "";
        return;
      }
      expandEl.innerHTML = "";
      expandEl.appendChild(el("div", { class: "cn-stub-note", text: cfg.note || "Bientôt disponible." }));
      expandEl.classList.add("open");
      return;
    }
    if (cfg.kind === "key" || cfg.kind === "messaging") {
      // Toggle expand with input fields
      if (expandEl.classList.contains("open")) {
        expandEl.classList.remove("open");
        expandEl.innerHTML = "";
        return;
      }
      expandEl.innerHTML = "";
      const inputs = [];
      J.api.get("/api/settings").then(ss => {
        (cfg.keys || []).forEach(f => {
          const fw = el("div", { class: "cn-field" });
          const labelEl = el("label", { class: "cn-field-label", text: f.label });
          fw.appendChild(labelEl);
          if (f.hint) {
            fw.appendChild(el("div", { class: "cn-field-hint", text: f.hint }));
          }

          if (f.type === "toggle") {
            // Valeur courante depuis .env via env-status
            const tog = el("div", { class: "cn-toggle" });
            J.api.get("/api/settings/env-status?keys=" + f.key).then(st => {
              if (st[f.key]) tog.classList.add("on");
            }).catch(() => {});
            tog.addEventListener("click", () => tog.classList.toggle("on"));
            fw.appendChild(tog);
            inputs.push({ key: f.key, tog, isToggle: true });
          } else {
            const inp = el("input", {
              class: "cn-field-input",
              type: f.secret ? "password" : "text",
              placeholder: f.secret ? "••••••••••" : "",
            });
            const v = (ss.api_keys || {})[f.key] || "";
            if (v) inp.value = v;
            fw.appendChild(inp);
            inputs.push({ key: f.key, inp });
          }
          expandEl.appendChild(fw);
        });
      }).catch(() => {});

      const saveBtn = el("button", { class: "cn-save-btn", text: "Sauvegarder" });
      saveBtn.addEventListener("click", async () => {
        saveBtn.textContent = "…"; saveBtn.disabled = true;
        try {
          for (const item of inputs) {
            if (item.isToggle) {
              await J.api.post("/api/settings/update", { key: item.key, value: item.tog.classList.contains("on") ? "true" : "false" });
            } else if (item.inp.value) {
              await J.api.post("/api/settings/update", { key: item.key, value: item.inp.value });
            }
          }
          J.notify({ kind: "success", text: c.name + " · configuré" });
          expandEl.classList.remove("open");
          expandEl.innerHTML = "";
          renderIntegrations();
        } catch (e) {
          J.notify({ kind: "error", text: e.message });
          saveBtn.textContent = "Sauvegarder"; saveBtn.disabled = false;
        }
      });
      expandEl.appendChild(saveBtn);
      expandEl.classList.add("open");
    }
  }

  /* ─────────────────────────────────────────
     02 Skills
  ───────────────────────────────────────── */
  async function renderSkills() {
    let skills = [];
    try {
      const r = await J.api.get("/api/skills/installed");
      skills = r.skills || [];
    } catch (_) {
      try {
        const tools = await J.api.get("/api/tools");
        skills = tools.map(t => ({ name: t.name, description: t.description, configured: true }));
      } catch (_) {}
    }

    skills = skills.filter(s => !SKILL_AS_ROUTINE.has(s.name));

    const grid = el("div", { class: "skills-grid" });
    skills.forEach(s => {
      const card = el("div", { class: "skill-card" });
      card.appendChild(el("div", { class: "skill-glyph", text: (s.name || "?").slice(0, 3).toUpperCase() }));
      card.appendChild(el("div", { class: "skill-name", text: s.name || s.label || "—" }));
      const desc = (s.description || "").slice(0, 100);
      if (desc) card.appendChild(el("div", { class: "skill-desc", text: desc }));
      card.addEventListener("click", () => openPanel(buildSkillPanel, s));
      grid.appendChild(card);
    });

    const wrap = el("div");
    wrap.appendChild(ghostSec("Skills installés", skills.length + " outils actifs", null, grid));
    const page = pageWrapper("skills", "Tes outils & skills", null, wrap);
    root.innerHTML = ""; root.appendChild(page);
  }

  /* ─────────────────────────────────────────
     03 Routines
  ───────────────────────────────────────── */
  async function renderRoutines() {
    let presets = [];
    let extraRoutines = [];
    try {
      const r = await J.api.get("/api/presets");
      presets = r.presets || [];
    } catch (_) {}

    try {
      const r = await J.api.get("/api/skills/installed");
      (r.skills || [])
        .filter(s => SKILL_AS_ROUTINE.has(s.name) && !presets.some(p => p.name === s.name))
        .forEach(s => extraRoutines.push({
          name: s.name,
          label: s.label || s.name,
          description: s.description,
          platforms: [],
        }));
    } catch (_) {}

    const allRoutines = [...presets, ...extraRoutines];

    const grid = el("div", { class: "routine-grid" });
    if (!allRoutines.length) {
      grid.appendChild(el("div", { class: "j-empty", text: "Aucune routine installée" }));
    } else {
      allRoutines.forEach(p => {
        const card = el("div", { class: "routine-card" });
        card.appendChild(el("div", { class: "routine-glyph", text: (p.name || "?").slice(0, 3).toUpperCase() }));
        card.appendChild(el("div", { class: "routine-name", text: p.label || p.name }));
        const desc = (p.description || "").slice(0, 100);
        if (desc) card.appendChild(el("div", { class: "routine-desc", text: desc }));
        if (p.platforms && p.platforms.length) {
          const platRow = el("div", { class: "routine-platforms" });
          p.platforms.forEach(pl => platRow.appendChild(el("span", { class: "preset-platform", text: pl })));
          card.appendChild(platRow);
        }
        card.addEventListener("click", () => openPanel(buildRoutinePanel, p));
        grid.appendChild(card);
      });
    }

    const wrap = el("div");
    wrap.appendChild(ghostSec("Routines", allRoutines.length + " automatisations", null, grid));
    const page = pageWrapper("routines", "Tes automatisations", null, wrap);
    root.innerHTML = ""; root.appendChild(page);
  }

  /* ─────────────────────────────────────────
     04 Ambiances
  ───────────────────────────────────────── */
  async function renderVues() {
    let installedViews = [];
    try {
      const r = await J.api.get("/api/skills/installed");
      installedViews = (r.skills || []).filter(s =>
        (s.tags || []).includes("view") || s.type === "view"
      );
    } catch (_) {}

    const registered = window.top?.Jarvis?.views?.list() || [];

    const grid = el("div", { class: "skills-grid" });
    installedViews.forEach(v => {
      const card = el("div", { class: "skill-card" });
      const glyphText = (v.label || v.name || "?").slice(0, 3).toUpperCase();
      card.appendChild(el("div", { class: "skill-glyph", text: glyphText }));
      card.appendChild(el("div", { class: "skill-name", text: v.label || v.name }));
      if (v.description) card.appendChild(el("div", { class: "skill-desc", text: v.description }));
      const isActive = registered.some(rv => v.name.includes(rv.id));
      card.appendChild(el("div", {
        class: "skill-installed-badge",
        text: isActive ? "● Active" : "Installée",
      }));
      card.addEventListener("click", () => openPanel(buildViewPanel, v));
      grid.appendChild(card);
    });

    if (!installedViews.length) {
      const empty = el("div", { class: "empty-hint", text: "Aucune vue installée — rendez-vous dans le Store." });
      grid.appendChild(empty);
    }

    const wrap = el("div");
    wrap.appendChild(ghostSec("Vues installées", installedViews.length + " vue" + (installedViews.length !== 1 ? "s" : ""), null, grid));
    const page = pageWrapper("vues", "Vues & affichages", null, wrap);
    root.innerHTML = ""; root.appendChild(page);
  }

  /* ─────────────────────────────────────────
     05 Store
  ───────────────────────────────────────── */
  async function renderStore() {
    let catalog = [];
    try {
      const r = await J.api.get("/api/skills/catalog");
      catalog = r.skills || [];
    } catch (_) {}

    const isView    = s => s.type === "view"   || (s.tags || []).includes("view");
    const isRoutine = s => s.type === "preset" || (s.tags || []).includes("preset");

    const views    = catalog.filter(s => isView(s));
    const routines = catalog.filter(s => !isView(s) && isRoutine(s));
    const skills   = catalog.filter(s => !isView(s) && !isRoutine(s));

    function makeStoreCard(s, kind) {
      const glyphCls = kind === "routine" ? "skill-glyph routine-glyph"
                     : kind === "view"    ? "skill-glyph view-glyph"
                     : "skill-glyph";
      const card = el("div", { class: "skill-card" });
      card.appendChild(el("div", { class: glyphCls, text: (s.name || "?").slice(0, 3).toUpperCase() }));
      card.appendChild(el("div", { class: "skill-name", text: s.name }));
      if (s.description) card.appendChild(el("div", { class: "skill-desc", text: s.description.slice(0, 100) }));

      const footer = el("div", { style: { marginTop: "auto", paddingTop: "4px" } });
      if (s.installed) {
        footer.appendChild(el("div", { class: "skill-installed-badge", text: "✓ Installé" }));
      } else {
        const installBtn = el("button", { class: "skill-install-btn", text: "Installer" });
        installBtn.addEventListener("click", async e => {
          e.stopPropagation();
          installBtn.textContent = "…"; installBtn.disabled = true;
          try {
            await J.api.post("/api/skills/install/" + s.name);
            J.notify({ kind: "success", text: s.name + " installé" });
            renderStore();
          } catch (err) {
            J.notify({ kind: "error", text: err.message });
            installBtn.textContent = "Installer"; installBtn.disabled = false;
          }
        });
        footer.appendChild(installBtn);
      }
      card.appendChild(footer);
      return card;
    }

    const wrap = el("div", { style: { display: "flex", flexDirection: "column", gap: "32px" } });

    if (!catalog.length) {
      wrap.appendChild(el("div", { class: "j-empty", text: "Catalogue indisponible" }));
    }

    if (skills.length) {
      const grid = el("div", { class: "skills-grid" });
      skills.forEach(s => grid.appendChild(makeStoreCard(s, "skill")));
      wrap.appendChild(ghostSec("Skills", skills.length + " disponible" + (skills.length !== 1 ? "s" : ""), null, grid));
    }

    if (routines.length) {
      const grid = el("div", { class: "skills-grid" });
      routines.forEach(s => grid.appendChild(makeStoreCard(s, "routine")));
      wrap.appendChild(ghostSec("Routines", routines.length + " disponible" + (routines.length !== 1 ? "s" : ""), null, grid));
    }

    if (views.length) {
      const grid = el("div", { class: "skills-grid" });
      views.forEach(s => grid.appendChild(makeStoreCard(s, "view")));
      wrap.appendChild(ghostSec("Vues", views.length + " disponible" + (views.length !== 1 ? "s" : ""), null, grid));
    }

    const page = pageWrapper("store", "Le store de skills", '<span class="v">' + catalog.length + '</span> disponibles', wrap);
    root.innerHTML = ""; root.appendChild(page);
  }

  /* ─────────────────────────────────────────
     06 Écosystème
  ───────────────────────────────────────── */
  function renderEcosysteme() {
    const wrap = el("div", { class: "coming-soon-wrap" });
    wrap.appendChild(el("div", { class: "coming-soon-msg", text: "À venir…" }));
    const page = pageWrapper("ecosysteme", "L'écosystème Jarvis", null, wrap);
    root.innerHTML = ""; root.appendChild(page);
  }

  /* ─────────────────────────────────────────
     07 Appareils
  ───────────────────────────────────────── */

  /* ── Three.js device scenes ──────────────────────────────────────── */
  /* ─── Macropad 2 touches Le Labo panel ─── */
  async function buildMacropadPanel(panel) {
    const hdr  = el("div", { class: "panel-header" });
    const left = el("div", { class: "panel-header-left" });
    const glyph = el("div", { class: "panel-glyph skill", text: "MAC" });
    const info  = el("div");
    info.appendChild(el("div", { class: "panel-name",       text: "Macropad 2 touches Le Labo" }));
    info.appendChild(el("div", { class: "panel-type-badge", text: "MACROPAD" }));
    left.appendChild(glyph); left.appendChild(info);
    hdr.appendChild(left); hdr.appendChild(makeCloseBtn());
    panel.appendChild(hdr);

    const body = el("div", { class: "panel-body" });
    body.appendChild(el("div", { class: "panel-desc",
      text: "Macropad 2 touches sur puce CH552. Configure les raccourcis, l'éclairage et flash le firmware directement depuis Jarvis." }));

    /* ── Statut USB ── */
    const stSec = el("div", { class: "panel-section" });
    stSec.appendChild(el("div", { class: "panel-section-title", text: "Connexion" }));
    const hidRow  = el("div", { class: "panel-check-row" });
    const bootRow = el("div", { class: "panel-check-row" });
    hidRow.appendChild(el("span",  { class: "panel-check-label", text: "Mode HID" }));
    bootRow.appendChild(el("span", { class: "panel-check-label", text: "Bootloader" }));
    const hidSt  = el("span", { class: "panel-check-status ko", text: "—" });
    const bootSt = el("span", { class: "panel-check-status ko", text: "—" });
    hidRow.appendChild(hidSt); bootRow.appendChild(bootSt);
    stSec.appendChild(hidRow); stSec.appendChild(bootRow);
    body.appendChild(stSec);

    J.api.get("/api/macropad/status").then(st => {
      if (st.hidPresent)         { hidSt.textContent  = "Connecté";  hidSt.className  = "panel-check-status ok"; }
      else                       { hidSt.textContent  = "Absent";    hidSt.className  = "panel-check-status ko"; }
      if (st.bootloaderPresent)  { bootSt.textContent = "Prêt";      bootSt.className = "panel-check-status ok"; }
      else                       { bootSt.textContent = "Absent";    bootSt.className = "panel-check-status ko"; }
    }).catch(() => { hidSt.textContent = "Erreur"; bootSt.textContent = "Erreur"; });

    /* ── Profil actif + touches ── */
    const profSec = el("div", { class: "panel-section" });
    profSec.appendChild(el("div", { class: "panel-section-title", text: "Profil actif" }));
    const k1Row = el("div", { class: "panel-check-row" });
    const k2Row = el("div", { class: "panel-check-row" });
    k1Row.appendChild(el("span", { class: "panel-check-label", text: "Touche K1 (droite)" }));
    k2Row.appendChild(el("span", { class: "panel-check-label", text: "Touche K2 (gauche)" }));
    const k1Val = el("span", { class: "panel-check-status", style: "color:var(--fg-2)", text: "—" });
    const k2Val = el("span", { class: "panel-check-status", style: "color:var(--fg-2)", text: "—" });
    k1Row.appendChild(k1Val); k2Row.appendChild(k2Val);
    const profName = el("div", { style: "font-family:var(--mono);font-size:10px;color:var(--fg-3);margin-bottom:10px", text: "Chargement…" });
    profSec.appendChild(profName);
    profSec.appendChild(k1Row); profSec.appendChild(k2Row);
    body.appendChild(profSec);

    J.api.get("/api/macropad/profile").then(({ bundle }) => {
      if (!bundle) return;
      const active = (bundle.profiles || []).find(p => p.id === bundle.activeProfileId) || bundle.profiles[0];
      if (!active) return;
      profName.textContent = "Profil : " + (active.name || active.id);
      const keys = active.data && active.data.keys;
      if (keys) {
        k1Val.textContent = keys.k1RightP1 ? (keys.k1RightP1.label || keys.k1RightP1.hidCode || "—") : "—";
        k2Val.textContent = keys.k2LeftP2  ? (keys.k2LeftP2.label  || keys.k2LeftP2.hidCode  || "—") : "—";
      }
    }).catch(() => { profName.textContent = "Profil non disponible"; });

    /* ── Actions ── */
    const actSec = el("div", { class: "panel-section" });
    actSec.appendChild(el("div", { class: "panel-section-title", text: "Actions" }));

    const compileBtn = el("button", { class: "panel-run-btn", text: "⚙ Compiler le firmware" });
    compileBtn.style.marginBottom = "8px";
    compileBtn.addEventListener("click", async () => {
      compileBtn.textContent = "…"; compileBtn.disabled = true;
      try {
        const r = await J.api.post("/api/macropad/compile", { workspace: null });
        J.notify({ kind: r.ok ? "success" : "error", text: r.ok ? "Compilation réussie" : r.output });
      } catch (e) { J.notify({ kind: "error", text: e.message }); }
      compileBtn.textContent = "⚙ Compiler le firmware"; compileBtn.disabled = false;
    });

    const flashBtn = el("button", { class: "panel-run-btn", text: "⚡ Flasher le firmware" });
    flashBtn.addEventListener("click", async () => {
      flashBtn.textContent = "…"; flashBtn.disabled = true;
      try {
        const r = await J.api.post("/api/macropad/upload", { workspace: null });
        J.notify({ kind: r.ok ? "success" : "error", text: r.ok ? "Flash réussi" : r.output });
      } catch (e) { J.notify({ kind: "error", text: e.message }); }
      flashBtn.textContent = "⚡ Flasher le firmware"; flashBtn.disabled = false;
    });

    actSec.appendChild(compileBtn);
    actSec.appendChild(flashBtn);

    const editorBtn = el("a", { class: "panel-run-btn",
      text: "✎ Ouvrir l'éditeur complet",
      href: "/macropad", target: "_blank",
      style: "display:block;text-align:center;text-decoration:none;margin-top:8px" });
    actSec.appendChild(editorBtn);

    body.appendChild(actSec);
    panel.appendChild(body);
  }

  const _scenes = [];

  function _killScenes() {
    _scenes.forEach(s => s.dispose());
    _scenes.length = 0;
  }

  function buildDevice3D(d) {
    const type   = d.type || "unknown";
    const btType = (d.a && d.a[0] === "Type") ? (d.a[1] || "").toLowerCase() : "";
    const wrap   = el("div", { class: "dv-scene-wrap" });
    const canvas = document.createElement("canvas");
    canvas.className = "dv-scene-canvas";
    wrap.appendChild(canvas);
    requestAnimationFrame(() => {
      if (!canvas.isConnected) return;
      const ctrl = _makeDeviceScene(canvas, type, btType);
      if (ctrl) _scenes.push(ctrl);
    });
    return wrap;
  }

  function _makeDeviceScene(canvas, type, btType) {
    const T = window.THREE;
    if (!T) return null;
    const W = canvas.offsetWidth  || 280;
    const H = canvas.offsetHeight || 200;

    const renderer = new T.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setSize(W, H, false);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);

    const scene  = new T.Scene();
    const camera = new T.PerspectiveCamera(32, W / H, 0.1, 100);

    // Lights
    scene.add(new T.AmbientLight(0xd0dcff, 0.55));
    const key = new T.DirectionalLight(0xffffff, 1.1);
    key.position.set(3, 5, 4);
    scene.add(key);
    const fill = new T.DirectionalLight(0x4a9eff, 0.38);
    fill.position.set(-4, 1, -2);
    scene.add(fill);
    const rim = new T.DirectionalLight(0xaaaaff, 0.18);
    rim.position.set(0, -2, -4);
    scene.add(rim);

    const group = new T.Group();
    scene.add(group);

    if (type === "host") {
      _meshMac(T, group);
      camera.position.set(0, 1.6, 5.5);
      camera.lookAt(0, 0.25, 0);
    } else if (type === "macropad") {
      _meshMacropad(T, group);
      camera.position.set(0, 2.8, 3.2);
      camera.lookAt(0, 0, 0);
    } else if (btType.includes("headphone") || btType.includes("headset")) {
      _meshHeadphones(T, group);
      camera.position.set(0, 0.8, 4.2);
      camera.lookAt(0, 0.2, 0);
    } else if (btType.includes("mouse")) {
      _meshMouse(T, group);
      camera.position.set(0, 1.8, 4.0);
      camera.lookAt(0, 0, 0);
    } else {
      _meshGeneric(T, group);
      camera.position.set(0, 1.5, 4.5);
      camera.lookAt(0, 0.1, 0);
    }

    let raf, speed = 0.007;
    canvas.addEventListener("mouseenter", () => { speed = 0; });
    canvas.addEventListener("mouseleave", () => { speed = 0.007; });

    const tick = () => {
      raf = requestAnimationFrame(tick);
      group.rotation.y += speed;
      renderer.render(scene, camera);
    };
    tick();

    return {
      dispose() {
        cancelAnimationFrame(raf);
        group.traverse(o => {
          if (o.geometry) o.geometry.dispose();
          if (o.material) {
            (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => m.dispose());
          }
        });
        renderer.dispose();
      }
    };
  }

  /* ── MacBook Pro ─────────────────────────────── */
  function _meshMac(T, group) {
    const alum  = new T.MeshStandardMaterial({ color: 0xb4b4c2, metalness: 0.85, roughness: 0.20 });
    const dark  = new T.MeshStandardMaterial({ color: 0x060a14,
      emissive: new T.Color(0x1a3a8a), emissiveIntensity: 0.55, roughness: 0.9 });
    const bezel = new T.MeshStandardMaterial({ color: 0x080c1a, roughness: 0.8 });
    const tpad  = new T.MeshStandardMaterial({ color: 0xa8a8b4, metalness: 0.72, roughness: 0.30 });

    // Base (keyboard deck)
    group.add(new T.Mesh(new T.BoxGeometry(2.2, 0.08, 1.52), alum));

    // Trackpad
    const tp = new T.Mesh(new T.BoxGeometry(0.58, 0.005, 0.40), tpad);
    tp.position.set(0, 0.043, 0.34);
    group.add(tp);

    // Hinge pivot at top-back of base
    const hinge = new T.Group();
    hinge.position.set(0, 0.04, -0.76);
    group.add(hinge);

    const lidH = 1.38;

    // Lid outer frame
    const lid = new T.Mesh(new T.BoxGeometry(2.2, lidH, 0.06), alum);
    lid.position.set(0, lidH / 2, 0);
    hinge.add(lid);

    // Display
    const disp = new T.Mesh(new T.BoxGeometry(2.04, 1.24, 0.01), dark);
    disp.position.set(0, lidH / 2 + 0.01, 0.035);
    hinge.add(disp);

    // Notch
    const notch = new T.Mesh(new T.BoxGeometry(0.24, 0.05, 0.015), bezel);
    notch.position.set(0, lidH - 0.04, 0.036);
    hinge.add(notch);

    // Open ~115° (25° past vertical → rotate hinge backward)
    hinge.rotation.x = -(25 * Math.PI / 180);

    group.position.y = -0.44;
  }

  /* ── Macropad ────────────────────────────────── */
  function _meshMacropad(T, group) {
    const bodyMat = new T.MeshStandardMaterial({ color: 0x141420, metalness: 0.3, roughness: 0.6 });
    const frameMat= new T.MeshStandardMaterial({ color: 0x1e1e2e, metalness: 0.2, roughness: 0.5 });
    const keyMat  = new T.MeshStandardMaterial({ color: 0x22223a, roughness: 0.7 });
    const litMat  = new T.MeshStandardMaterial({ color: 0x0d2242,
      emissive: new T.Color(0x4a9eff), emissiveIntensity: 0.85, roughness: 0.6 });
    const encMat  = new T.MeshStandardMaterial({ color: 0x4a9eff, metalness: 0.4,
      emissive: new T.Color(0x4a9eff), emissiveIntensity: 0.35 });

    const frame = new T.Mesh(new T.BoxGeometry(1.88, 0.22, 1.38), frameMat);
    frame.position.y = -0.01;
    group.add(frame);
    group.add(new T.Mesh(new T.BoxGeometry(1.82, 0.20, 1.32), bodyMat));

    // 3×4 key grid
    const cols = 4, rows = 3;
    const kW = 0.30, kD = 0.25, kH = 0.07;
    const gapX = 0.08, gapZ = 0.07;
    const totalW = cols * kW + (cols - 1) * gapX;
    const totalD = rows * kD + (rows - 1) * gapZ;
    let idx = 0;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const key = new T.Mesh(new T.BoxGeometry(kW, kH, kD), idx % 3 === 0 ? litMat : keyMat);
        key.position.set(
          -totalW / 2 + c * (kW + gapX) + kW / 2,
          0.135,
          -totalD / 2 + r * (kD + gapZ) + kD / 2
        );
        group.add(key);
        idx++;
      }
    }

    // Encoder knob
    const enc = new T.Mesh(new T.CylinderGeometry(0.12, 0.12, 0.1, 20), encMat);
    enc.position.set(0.68, 0.20, -0.48);
    group.add(enc);

    group.position.y = -0.12;
    group.rotation.x = -0.15;
  }

  /* ── Headphones ──────────────────────────────── */
  function _meshHeadphones(T, group) {
    const bandMat = new T.MeshStandardMaterial({ color: 0x282830, metalness: 0.6, roughness: 0.35 });
    const cupMat  = new T.MeshStandardMaterial({ color: 0x1e1e28, metalness: 0.4, roughness: 0.45 });
    const padMat  = new T.MeshStandardMaterial({ color: 0x2a2a2a, roughness: 0.85 });

    // Headband (half-torus arc — arche vers le haut)
    const band = new T.Mesh(new T.TorusGeometry(0.72, 0.062, 10, 40, Math.PI), bandMat);
    band.position.y = 0;
    group.add(band);

    [-0.72, 0.72].forEach(x => {
      // Stem
      const stem = new T.Mesh(new T.CylinderGeometry(0.038, 0.038, 0.32, 10), bandMat);
      stem.rotation.z = Math.PI / 2;
      stem.position.set(x, 0, 0);
      group.add(stem);

      // Cup shell
      const cup = new T.Mesh(new T.CylinderGeometry(0.27, 0.24, 0.20, 26), cupMat);
      cup.rotation.z = Math.PI / 2;
      cup.position.set(x, 0, 0);
      group.add(cup);

      // Ear pad
      const pad = new T.Mesh(new T.CylinderGeometry(0.21, 0.21, 0.04, 26), padMat);
      pad.rotation.z = Math.PI / 2;
      pad.position.set(x < 0 ? x - 0.12 : x + 0.12, 0, 0);
      group.add(pad);
    });

    group.position.y = -0.38;
  }

  /* ── Mouse ───────────────────────────────────── */
  function _meshMouse(T, group) {
    const bodyMat   = new T.MeshStandardMaterial({ color: 0xbcbcca, metalness: 0.68, roughness: 0.28 });
    const btnLMat   = new T.MeshStandardMaterial({ color: 0xccccda, metalness: 0.62, roughness: 0.32 });
    const btnRMat   = new T.MeshStandardMaterial({ color: 0xb8b8c8, metalness: 0.60, roughness: 0.35 });
    const scrollMat = new T.MeshStandardMaterial({ color: 0x808090, metalness: 0.5, roughness: 0.5 });

    // Body (scaled sphere)
    const body = new T.Mesh(new T.SphereGeometry(0.52, 28, 18), bodyMat);
    body.scale.set(0.88, 0.43, 1.18);
    group.add(body);

    // Left button
    const lBtn = new T.Mesh(new T.BoxGeometry(0.40, 0.032, 0.52), btnLMat);
    lBtn.position.set(-0.22, 0.21, -0.18);
    group.add(lBtn);

    // Right button
    const rBtn = new T.Mesh(new T.BoxGeometry(0.40, 0.032, 0.52), btnRMat);
    rBtn.position.set(0.22, 0.21, -0.18);
    group.add(rBtn);

    // Scroll wheel
    const scroll = new T.Mesh(new T.CylinderGeometry(0.06, 0.06, 0.24, 14), scrollMat);
    scroll.rotation.z = Math.PI / 2;
    scroll.position.set(0, 0.248, -0.15);
    group.add(scroll);

    group.position.y = -0.08;
  }

  /* ── Generic BT ──────────────────────────────── */
  function _meshGeneric(T, group) {
    const frameMat  = new T.MeshStandardMaterial({ color: 0x1e1e34, metalness: 0.25, roughness: 0.55 });
    const bodyMat   = new T.MeshStandardMaterial({ color: 0x16162a, metalness: 0.30, roughness: 0.60 });
    const screenMat = new T.MeshStandardMaterial({ color: 0x060a14,
      emissive: new T.Color(0x1a3a8a), emissiveIntensity: 0.48, roughness: 0.9 });
    const dotMat    = new T.MeshStandardMaterial({ color: 0x4a9eff,
      emissive: new T.Color(0x4a9eff), emissiveIntensity: 1.0 });

    group.add(new T.Mesh(new T.BoxGeometry(1.05, 0.10, 1.60), frameMat));
    const body = new T.Mesh(new T.BoxGeometry(0.98, 0.09, 1.52), bodyMat);
    body.position.y = 0.005;
    group.add(body);

    const screen = new T.Mesh(new T.BoxGeometry(0.82, 0.01, 1.12), screenMat);
    screen.position.set(0, 0.055, -0.08);
    group.add(screen);

    const dot = new T.Mesh(new T.CylinderGeometry(0.07, 0.07, 0.012, 16), dotMat);
    dot.position.set(0, 0.056, 0.58);
    group.add(dot);

    group.position.y = -0.18;
    group.rotation.x = -0.14;
  }

  async function renderAppareils() {
    let devices = [];
    try { devices = await J.api.get("/api/settings/devices"); } catch (_) {}

    const grid = el("div", { class: "device-grid-v2" });
    devices.forEach(d => {
      const col  = d.col || "muted";
      const card = el("div", { class: "dv-card-v2" + (col === "muted" ? " dv-card--dim" : " dv-card--glow-" + col) });

      card.appendChild(buildDevice3D(d));
      if (d.type === "macropad") {
        card.style.cursor = "pointer";
        card.addEventListener("click", () => openPanel(buildMacropadPanel));
      }

      const body = el("div", { class: "dv-body-v2" });

      const nameRow = el("div", { class: "dv-name-row" });
      nameRow.appendChild(el("div", { class: "dv-name-v2", text: d.name }));
      nameRow.appendChild(el("div", { class: "dv-badge " + col, text: d.status || "Unknown" }));
      body.appendChild(nameRow);

      if (d.id) body.appendChild(el("div", { class: "dv-sub-v2", text: d.id }));

      if (d.a || d.b) {
        const meta = el("div", { class: "dv-meta-v2" });
        [d.a, d.b].forEach(pair => {
          if (!pair) return;
          const item = el("div", { class: "dv-meta-item-v2" });
          item.appendChild(el("div", { class: "dv-meta-k-v2", text: pair[0] || "" }));
          item.appendChild(el("div", { class: "dv-meta-v-v2", text: pair[1] || "" }));
          meta.appendChild(item);
        });
        body.appendChild(meta);
      }

      card.appendChild(body);
      grid.appendChild(card);
    });

    const wrap = el("div");
    wrap.appendChild(ghostSec("Appareils", devices.length + " détectés", null, grid));
    const page = pageWrapper("appareils", "Tes appareils", null, wrap);
    root.innerHTML = ""; root.appendChild(page);
  }

  /* ─────────────────────────────────────────
     08 Fils (Sessions)
  ───────────────────────────────────────── */
  async function renderFils() {
    let sessions = [];
    try { sessions = await J.api.get("/api/sessions"); } catch (_) {}

    const list = el("div");
    if (!sessions.length) {
      list.appendChild(el("div", { class: "j-empty", text: "Aucune session récente" }));
    } else {
      sessions.slice(0, 20).forEach(s => {
        const row = el("div", { class: "session-row" });
        row.appendChild(el("div", { class: "sess-id t-mono", text: (s.id || "").slice(0, 6).toUpperCase() }));

        const preview = el("div");
        const titleEl = el("div", { class: "sess-preview", text: s.title || s.preview || "—" });
        preview.appendChild(titleEl);
        preview.appendChild(el("div", { style: { fontFamily: "var(--mono)", fontSize: "9.5px", color: "var(--fg-3)", marginTop: "3px" },
          text: (s.message_count || 0) + " messages" }));
        row.appendChild(preview);
        row.appendChild(el("div", { class: "sess-date", text: s.date || "" }));

        const viewBtn   = el("button", { class: "m-btn", text: "Voir" });
        const renameBtn = el("button", { class: "m-btn", text: "Renommer" });
        const delBtn    = el("button", { class: "m-btn m-btn--danger", text: "✕" });
        delBtn.title = "Supprimer ce fil";
        const acts = el("div", { class: "mem-btn-row" });
        acts.appendChild(viewBtn);
        acts.appendChild(renameBtn);
        acts.appendChild(delBtn);
        row.appendChild(acts);
        list.appendChild(row);

        /* inline conversation viewer */
        const viewer   = el("div", { class: "sess-viewer" });
        const msgList  = el("div", { class: "sess-msg-list" });
        const closeViewBtn = el("button", { class: "m-btn", text: "Fermer" });
        viewer.appendChild(msgList);
        viewer.appendChild(closeViewBtn);
        list.appendChild(viewer);

        viewBtn.addEventListener("click", async () => {
          if (viewer.classList.contains("open")) {
            viewer.classList.remove("open");
            viewBtn.textContent = "Voir";
            return;
          }
          editor.classList.remove("open");
          renameBtn.textContent = "Renommer";
          viewBtn.textContent = "…"; viewBtn.disabled = true;
          try {
            const msgs = await J.api.get("/api/sessions/" + encodeURIComponent(s.id) + "/messages?limit=100");
            msgList.innerHTML = "";
            if (!msgs.length) {
              msgList.appendChild(el("div", { class: "sess-msg-empty", text: "Aucun message." }));
            } else {
              msgs.forEach(m => {
                const bubble = el("div", { class: "sess-bubble sess-bubble--" + (m.role === "user" ? "user" : "assistant") });
                const label  = el("div", { class: "sess-bubble-role", text: m.role === "user" ? "Toi" : "Jarvis" });
                const body   = el("div", { class: "sess-bubble-body", text: m.content || "" });
                bubble.appendChild(label);
                bubble.appendChild(body);
                msgList.appendChild(bubble);
              });
            }
            viewer.classList.add("open");
            setTimeout(() => viewer.scrollIntoView({ behavior: "smooth", block: "nearest" }), 50);
          } catch (e) {
            J.notify({ kind: "error", text: e.message });
          }
          viewBtn.textContent = "Voir"; viewBtn.disabled = false;
        });

        closeViewBtn.addEventListener("click", () => {
          viewer.classList.remove("open");
          viewBtn.textContent = "Voir";
        });

        /* inline rename editor */
        const editor  = el("div", { class: "sess-rename-editor" });
        const inp     = el("input", { class: "sess-rename-input", type: "text" });
        inp.value       = s.title || s.preview || "";
        inp.placeholder = "Nouveau titre…";
        editor.appendChild(inp);
        const saveBtn  = el("button", { class: "m-btn m-btn--save", text: "Sauvegarder" });
        const closeBtn = el("button", { class: "m-btn",              text: "Annuler" });
        const btnRow   = el("div",    { class: "mem-btn-row" });
        btnRow.appendChild(saveBtn);
        btnRow.appendChild(closeBtn);
        editor.appendChild(btnRow);
        list.appendChild(editor);

        renameBtn.addEventListener("click", () => {
          const open = editor.classList.contains("open");
          if (!open) { viewer.classList.remove("open"); viewBtn.textContent = "Voir"; }
          editor.classList.toggle("open", !open);
          renameBtn.textContent = open ? "Renommer" : "Annuler";
          if (!open) { inp.focus(); inp.select(); }
        });

        closeBtn.addEventListener("click", () => {
          editor.classList.remove("open");
          renameBtn.textContent = "Renommer";
        });

        inp.addEventListener("keydown", e => {
          if (e.key === "Enter")  saveBtn.click();
          if (e.key === "Escape") closeBtn.click();
        });

        saveBtn.addEventListener("click", async () => {
          const newTitle = inp.value.trim();
          if (!newTitle) return;
          const orig = saveBtn.textContent;
          saveBtn.textContent = "…"; saveBtn.disabled = true;
          try {
            await J.api.put("/api/sessions/" + encodeURIComponent(s.id) + "/title", { title: newTitle });
            titleEl.textContent = newTitle;
            editor.classList.remove("open");
            renameBtn.textContent = "Renommer";
            J.notify({ kind: "success", text: "Fil renommé" });
          } catch (e) {
            J.notify({ kind: "error", text: e.message });
            saveBtn.textContent = "✗ Erreur";
          }
          setTimeout(() => { saveBtn.textContent = orig; saveBtn.disabled = false; }, 1800);
        });

        delBtn.addEventListener("click", async () => {
          if (!confirm("Supprimer ce fil définitivement ?")) return;
          delBtn.disabled = true;
          try {
            await J.api.delete("/api/sessions/" + encodeURIComponent(s.id));
            row.remove();
            editor.remove();
            J.notify({ kind: "success", text: "Fil supprimé" });
          } catch (e) {
            J.notify({ kind: "error", text: e.message });
            delBtn.disabled = false;
          }
        });
      });
    }

    const wrap = el("div");
    wrap.appendChild(ghostSec("Sessions récentes", sessions.length + " fils", null, list));
    const page = pageWrapper("fils", "Tes conversations", '<span class="v">' + sessions.length + '</span> fils', wrap);
    root.innerHTML = ""; root.appendChild(page);
  }

  /* ─────────────────────────────────────────
     09 Mémoire
  ───────────────────────────────────────── */
  function relTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso); const now = new Date();
    const sec = Math.round((now - d) / 1000);
    if (sec < 60) return "à l'instant";
    if (sec < 3600) return Math.round(sec / 60) + " min";
    if (sec < 86400) return Math.round(sec / 3600) + " h";
    if (sec < 86400 * 30) return Math.round(sec / 86400) + " j";
    return d.toLocaleDateString("fr");
  }

  async function renderMemoire() {
    let topics = [], index = "", facts = [];
    try {
      topics = await J.api.get("/api/memory/topics");
      const idx = await J.api.get("/api/memory/index");
      index = idx.content || "";
    } catch (_) {}
    try {
      facts = await J.api.get("/api/memory/facts?status=active&limit=200");
    } catch (_) {}

    const wrap = el("div", { style: { display: "flex", flexDirection: "column", gap: "40px" } });

    /* ── Facts (Kernel SQL — construit ici, appendé en bas de la page) ── */
    const factsList = el("div", { style: { display: "flex", flexDirection: "column", gap: "8px" } });
    if (!facts.length) {
      factsList.appendChild(el("div", { class: "j-empty", text: "Aucun fact actif dans le Kernel" }));
    } else {
      /* Group by category for legibility */
      const byCat = {};
      facts.forEach(f => { (byCat[f.category] = byCat[f.category] || []).push(f); });
      const cats = Object.keys(byCat).sort();
      cats.forEach(cat => {
        const catHead = el("div", { class: "mem-cat-head", text: cat + " · " + byCat[cat].length });
        catHead.style.cssText = "font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#888;margin-top:14px;margin-bottom:4px;";
        factsList.appendChild(catHead);
        byCat[cat].forEach(f => {
          const row = el("div", { class: "fact-row" });
          row.style.cssText = "display:grid;grid-template-columns:1fr 90px 80px 80px auto;gap:10px;padding:8px 10px;border:1px solid rgba(255,255,255,.06);border-radius:6px;align-items:center;background:rgba(255,255,255,.02);";

          const txt = el("div");
          txt.innerHTML = '<span style="color:#aaa">' + escapeHtml(f.subject) + ' · </span>'
            + '<span style="color:#d4af6a">' + escapeHtml(f.predicate) + '</span> · '
            + '<span>' + escapeHtml(f.object) + '</span>';
          row.appendChild(txt);

          row.appendChild(el("div", { text: "conf " + (f.confidence * 100).toFixed(0) + "%", style: { fontSize: "11px", color: "#888", textAlign: "right", fontFamily: "Geist Mono, monospace" } }));
          row.appendChild(el("div", { text: f.decay_policy, style: { fontSize: "11px", color: "#888", textAlign: "center" } }));
          row.appendChild(el("div", { text: relTime(f.last_seen_at), style: { fontSize: "11px", color: "#888", textAlign: "right" } }));

          const corrBtn = el("button", { class: "m-btn", text: "Corriger" });
          corrBtn.style.cssText = "padding:4px 10px;font-size:11px;";
          corrBtn.addEventListener("click", () => openCorrectionModal(f, () => renderMemoire()));
          row.appendChild(corrBtn);

          factsList.appendChild(row);
        });
      });
    }
    const factsSection = ghostSec(
      "Facts (Kernel)",
      facts.length + " actifs · régénéré à chaque passe deep",
      null,
      factsList
    );

    /* ── Index MEMORY.md (éditable) ── */
    const indexWrap = el("div", { style: { display: "flex", flexDirection: "column", gap: "10px" } });
    const indexTa = el("textarea", { class: "mem-textarea" });
    indexTa.rows = 10;
    indexTa.value = index;
    indexWrap.appendChild(indexTa);
    const indexSave = el("button", { class: "m-btn m-btn--save", text: "Sauvegarder" });
    indexSave.addEventListener("click", async () => {
      const orig = indexSave.textContent;
      indexSave.textContent = "…"; indexSave.disabled = true;
      try {
        await J.api.put("/api/memory/index", { content: indexTa.value });
        J.notify({ kind: "success", text: "MEMORY.md sauvegardé" });
        indexSave.textContent = "✓ Sauvegardé";
      } catch (e) {
        J.notify({ kind: "error", text: e.message });
        indexSave.textContent = "✗ Erreur";
      }
      setTimeout(() => { indexSave.textContent = orig; indexSave.disabled = false; }, 2000);
    });
    const idxRow = el("div", { class: "mem-btn-row" });
    idxRow.appendChild(indexSave);
    indexWrap.appendChild(idxRow);
    wrap.appendChild(ghostSec("Index mémoire", "MEMORY.md", null, indexWrap));

    /* ── Topics ── */
    const list = el("div");
    if (!topics.length) {
      list.appendChild(el("div", { class: "j-empty", text: "Aucun topic en mémoire" }));
    } else {
      topics.forEach(t => {
        const row = el("div", { class: "memory-row" });
        row.appendChild(el("div", { class: "mem-name", text: t.name }));
        row.appendChild(el("div", { class: "mem-meta", text: Math.round((t.size || 0) / 1024 * 10) / 10 + " ko" }));
        row.appendChild(el("div", { class: "mem-meta", text: t.mtime ? new Date(t.mtime).toLocaleDateString("fr") : "—" }));

        const editBtn = el("button", { class: "m-btn", text: "Éditer" });
        const delBtn  = el("button", { class: "m-btn m-btn--danger", text: "✕" });
        delBtn.title = "Supprimer " + t.name;
        const acts = el("div", { class: "mem-btn-row" });
        acts.appendChild(editBtn);
        acts.appendChild(delBtn);
        row.appendChild(acts);
        list.appendChild(row);

        /* inline editor (hidden by default) */
        const editor = el("div", { class: "mem-topic-editor" });
        const ta = el("textarea", { class: "mem-textarea" });
        ta.rows = 14;
        editor.appendChild(ta);
        const saveBtn  = el("button", { class: "m-btn m-btn--save",  text: "Sauvegarder" });
        const closeBtn = el("button", { class: "m-btn",               text: "Fermer" });
        const btnRow   = el("div",    { class: "mem-btn-row" });
        btnRow.appendChild(saveBtn);
        btnRow.appendChild(closeBtn);
        editor.appendChild(btnRow);
        list.appendChild(editor);

        editBtn.addEventListener("click", async () => {
          if (editor.classList.contains("open")) {
            editor.classList.remove("open");
            editBtn.textContent = "Éditer";
            return;
          }
          editBtn.textContent = "…"; editBtn.disabled = true;
          try {
            const { content } = await J.api.get("/api/memory/topics/" + encodeURIComponent(t.name));
            ta.value = content;
            editor.classList.add("open");
            editBtn.textContent = "Éditer";
            setTimeout(() => editor.scrollIntoView({ behavior: "smooth", block: "nearest" }), 50);
          } catch (e) {
            J.notify({ kind: "error", text: e.message });
            editBtn.textContent = "Éditer";
          }
          editBtn.disabled = false;
        });

        closeBtn.addEventListener("click", () => {
          editor.classList.remove("open");
          editBtn.textContent = "Éditer";
        });

        saveBtn.addEventListener("click", async () => {
          const orig = saveBtn.textContent;
          saveBtn.textContent = "…"; saveBtn.disabled = true;
          try {
            await J.api.put("/api/memory/topics/" + encodeURIComponent(t.name), { content: ta.value });
            J.notify({ kind: "success", text: t.name + " sauvegardé" });
            saveBtn.textContent = "✓ Sauvegardé";
          } catch (e) {
            J.notify({ kind: "error", text: e.message });
            saveBtn.textContent = "✗ Erreur";
          }
          setTimeout(() => { saveBtn.textContent = orig; saveBtn.disabled = false; }, 2000);
        });

        delBtn.addEventListener("click", async () => {
          if (!confirm("Supprimer « " + t.name + " » définitivement ?")) return;
          delBtn.disabled = true;
          try {
            await J.api.delete("/api/memory/topics/" + encodeURIComponent(t.name));
            row.remove();
            editor.remove();
            J.notify({ kind: "success", text: t.name + " supprimé" });
          } catch (e) {
            J.notify({ kind: "error", text: e.message });
            delBtn.disabled = false;
          }
        });
      });
    }
    wrap.appendChild(ghostSec("Topics", topics.length + " fichiers", null, list));

    /* Facts en bas — la vraie fenêtre Kernel SQL, sous l'Index et les Topics. */
    wrap.appendChild(factsSection);

    const page = pageWrapper(
      "memoire",
      "La mémoire de Jarvis",
      '<span class="v">' + facts.length + '</span> facts · <span class="v">' + topics.length + '</span> topics',
      wrap
    );
    root.innerHTML = ""; root.appendChild(page);
  }

  /* ─────────────────────────────────────────
     ROUTER
  ───────────────────────────────────────── */
  const RENDERERS = {
    integrations: renderIntegrations,
    skills:       renderSkills,
    routines:     renderRoutines,
    vues:         renderVues,
    store:        renderStore,
    ecosysteme:   renderEcosysteme,
    appareils:    renderAppareils,
    fils:         renderFils,
    memoire:      renderMemoire,
  };

  function navigate(pageId) {
    _activePage = pageId;
    closePanel();
    _killScenes();
    const nav = document.getElementById("j-rooms-pages");
    if (nav) {
      const btns = Array.from(nav.querySelectorAll("button"));
      const idx = PAGES.findIndex(p => p.id === pageId);
      btns.forEach((b, i) => b.dataset.active = i === idx ? "true" : "false");
    }
    const fn = RENDERERS[pageId];
    if (fn) { root.innerHTML = ""; fn(); }
  }

  /* ─────────────────────────────────────────
     INIT
  ───────────────────────────────────────── */
  J.mountAtmosphere();

  J.mountRooms({
    mode: "capacites",
    pages: PAGES,
    activePage: _activePage,
    onNav: (id) => navigate(id),
  });

  J.registerCommands(PAGES.map(p => ({
    kind: "nav", id: "cap-" + p.id, group: "Atelier",
    title: p.label, glyph: "→",
    run: () => navigate(p.id),
  })));

  renderIntegrations();
})();
