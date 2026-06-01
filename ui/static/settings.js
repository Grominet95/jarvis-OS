/* settings.js — Configuration (Réglages) v2
 * 5 sous-pages : Profil · Modèles & API · Conso · Système · À propos
 */
(function () {
  "use strict";
  const J = window.Jarvis, el = J.el;

  const PAGES = [
    { id: "preferences", label: "Préférences" },
    { id: "modeles",     label: "Modèles" },
    { id: "conso",       label: "Conso" },
    { id: "systeme",     label: "Système" },
    { id: "apropos",     label: "À propos" },
  ];

  let _activePage = "preferences";
  const root = document.getElementById("page-root");
  let _settings = null;

  /* ───────── Helpers ───────── */
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

  function settingRow(label, sub, control) {
    const row = el("div", { class: "setting-row" });
    const txt = el("div");
    txt.appendChild(el("div", { class: "setting-label", text: label }));
    if (sub) txt.appendChild(el("div", { class: "setting-sub", text: sub }));
    row.appendChild(txt);
    row.appendChild(control);
    return row;
  }

  function makeSelect(options, current, key) {
    let selected = options.includes(current) ? current : (options[0] || "");

    const wrap = el("div", { class: "csel-wrap" });
    const btn  = el("button", { class: "csel-btn" });
    const lbl  = el("span", { class: "csel-label", text: selected });
    const chev = el("span", { class: "csel-chevron",
      html: '<svg width="10" height="6" viewBox="0 0 10 6" fill="none"><path d="M1 1L5 5L9 1" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>' });
    btn.appendChild(lbl); btn.appendChild(chev);
    wrap.appendChild(btn);

    const dropdown = el("div", { class: "csel-dropdown" });
    options.forEach(o => {
      const item = el("div", { class: "csel-item" + (o === selected ? " active" : ""), text: o });
      item.addEventListener("click", () => {
        selected = o;
        lbl.textContent = o;
        dropdown.querySelectorAll(".csel-item").forEach(it => it.classList.toggle("active", it.textContent === o));
        close();
      });
      dropdown.appendChild(item);
    });
    wrap.appendChild(dropdown);

    const handleOutside = e => { if (!wrap.contains(e.target)) close(); };
    const close = () => {
      wrap.classList.remove("open");
      document.removeEventListener("click", handleOutside);
    };

    btn.addEventListener("click", e => {
      e.stopPropagation();
      if (wrap.classList.contains("open")) { close(); return; }
      wrap.classList.add("open");
      setTimeout(() => document.addEventListener("click", handleOutside), 0);
    });

    const saveBtn = el("button", { class: "m-btn", text: "Sauv." });
    saveBtn.addEventListener("click", () => saveSetting(key, selected, saveBtn));
    const ctrl = el("div", { style: { display: "flex", gap: "8px", alignItems: "center" } });
    ctrl.appendChild(wrap); ctrl.appendChild(saveBtn);
    return ctrl;
  }

  async function getSettings() {
    if (_settings) return _settings;
    try { _settings = await J.api.get("/api/settings"); } catch (_) { _settings = {}; }
    return _settings;
  }

  async function saveSetting(key, value, btn) {
    if (btn) { btn.textContent = "…"; btn.disabled = true; }
    try {
      await J.api.post("/api/settings/update", { key, value });
      _settings = null; // invalidate cache
      J.notify({ kind: "success", text: key + " · mis à jour" });
    } catch (e) {
      J.notify({ kind: "error", text: e.message });
    }
    if (btn) { btn.textContent = "Sauv."; btn.disabled = false; }
  }

  /* ───────── 01 Préférences ───────── */
  async function renderPreferences() {
    const s   = await getSettings();
    const jarvis = s.jarvis    || {};
    const music  = s.music     || {};
    const pro    = s.proactive || {};

    const wrap = el("div", { style: { display:"flex", flexDirection:"column", gap:"40px" } });

    // ── Identité ──
    const identList = el("div");
    const fnInput = el("input", { class: "input-mono", style: { width:"220px" }, value: jarvis.user_firstname || "" });
    const fnSave  = el("button", { class: "m-btn", text: "Sauv." });
    fnSave.addEventListener("click", () => saveSetting("USER_FIRSTNAME", fnInput.value, fnSave));
    const fnCtrl  = el("div", { style: { display:"flex", gap:"8px" } });
    fnCtrl.appendChild(fnInput); fnCtrl.appendChild(fnSave);
    identList.appendChild(settingRow("Prénom", "USER_FIRSTNAME", fnCtrl));
    wrap.appendChild(ghostSec("Identité", "comment Jarvis s'adresse à toi", null, identList));

    // ── Langue & style ──
    const styleList = el("div");
    const qbTog = el("div", { class: "toggle" + (jarvis.quebec_mode ? " on" : "") });
    qbTog.addEventListener("click", () => {
      const next = !qbTog.classList.contains("on");
      qbTog.classList.toggle("on", next);
      saveSetting("QUEBEC_MODE", String(next), null);
    });
    styleList.appendChild(settingRow("Mode québécois", "Accent et expressions du Québec", qbTog));
    wrap.appendChild(ghostSec("Langue & style", "dialecte · voix", null, styleList));

    // ── Musique ──
    const musicList = el("div");
    musicList.appendChild(settingRow("Fournisseur", "MUSIC_PROVIDER",
      makeSelect(["—", "spotify", "deezer", "local"], music.music_provider || "—", "MUSIC_PROVIDER")));
    wrap.appendChild(ghostSec("Musique", "source de lecture active", null, musicList));

    // ── Proactivité ──
    const proList = el("div");

    const cityInput = el("input", { class: "input-mono", style: { width:"180px" }, value: pro.home_city || "" });
    const citySave  = el("button", { class: "m-btn", text: "Sauv." });
    citySave.addEventListener("click", () => saveSetting("HOME_CITY", cityInput.value, citySave));
    const cityCtrl  = el("div", { style: { display:"flex", gap:"8px" } });
    cityCtrl.appendChild(cityInput); cityCtrl.appendChild(citySave);
    proList.appendChild(settingRow("Ville météo", "HOME_CITY", cityCtrl));

    const hourInput = el("input", {
      type: "number", min: "0", max: "23",
      class: "input-mono", style: { width:"70px" },
      value: String(pro.briefing_hour ?? 9),
    });
    const hourSave = el("button", { class: "m-btn", text: "Sauv." });
    hourSave.addEventListener("click", () => saveSetting("BRIEFING_HOUR", hourInput.value, hourSave));
    const hourCtrl = el("div", { style: { display:"flex", gap:"8px", alignItems:"center" } });
    hourCtrl.appendChild(hourInput);
    hourCtrl.appendChild(el("span", { style: { color:"var(--fg-3)", fontFamily:"var(--mono)", fontSize:"11px" }, text:"h00" }));
    hourCtrl.appendChild(hourSave);
    proList.appendChild(settingRow("Heure du briefing", "BRIEFING_HOUR", hourCtrl));

    wrap.appendChild(ghostSec("Proactivité", "briefing · rappels · météo", null, proList));

    // ── Wake up ──
    const wakeList = el("div");

    const wupTog = el("div", { class: "toggle" + (jarvis.wakeup_enabled ? " on" : "") });
    wupTog.addEventListener("click", () => {
      const next = !wupTog.classList.contains("on");
      wupTog.classList.toggle("on", next);
      saveSetting("WAKEUP_ENABLED", String(next), null);
    });
    wakeList.appendChild(settingRow("Séquence wake up", "Veille + scan facial + clap", wupTog));

    const clapTog = el("div", { class: "toggle" + (jarvis.clap_detection_enabled ? " on" : "") });
    clapTog.addEventListener("click", () => {
      const next = !clapTog.classList.contains("on");
      clapTog.classList.toggle("on", next);
      saveSetting("CLAP_DETECTION_ENABLED", String(next), null);
    });
    wakeList.appendChild(settingRow("Détection de clap", "Double clap pour réveiller Jarvis", clapTog));

    wrap.appendChild(ghostSec("Wake up", "déclencheurs de réveil", null, wakeList));

    const page = pageWrapper("preferences", "Tes préférences", null, wrap);
    root.innerHTML = ""; root.appendChild(page);
  }

  /* ───────── Ollama helpers ───────── */

  const _OLLAMA_POPULAR = [
    { id: "qwen3:8b",     label: "Qwen 3 · 8B",    gb: "5.2", tag: "Recommandé" },
    { id: "qwen2.5:7b",   label: "Qwen 2.5 · 7B",  gb: "4.4", tag: "Tool use"   },
    { id: "qwen3:4b",     label: "Qwen 3 · 4B",     gb: "2.6", tag: "Léger"      },
    { id: "llama3.1:8b",  label: "Llama 3.1 · 8B",  gb: "4.7", tag: ""           },
    { id: "mistral:7b",   label: "Mistral · 7B",    gb: "4.1", tag: ""           },
  ];

  function showPullModal(modelId, onDone) {
    const overlay = el("div", { class: "ollama-pull-overlay" });

    const dialog = el("div", { class: "ollama-pull-dialog" });
    dialog.appendChild(el("div", { class: "ollama-pull-eyebrow", text: "Téléchargement" }));
    dialog.appendChild(el("div", { class: "ollama-pull-model-name", text: modelId }));

    const barWrap = el("div", { class: "ollama-pull-bar" });
    const barFill = el("div", { class: "ollama-pull-fill indeterminate" });
    barWrap.appendChild(barFill);
    dialog.appendChild(barWrap);

    const statusEl = el("div", { class: "ollama-pull-status", text: "Connexion à Ollama…" });
    dialog.appendChild(statusEl);

    const closeBtn = el("button", { class: "m-btn ghost", text: "✕ Fermer" });
    closeBtn.disabled = true;
    closeBtn.addEventListener("click", () => { overlay.remove(); if (onDone) onDone(); });
    dialog.appendChild(closeBtn);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    (async () => {
      try {
        const resp = await fetch("/api/ollama/pull", {
          method: "POST", credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model: modelId }),
        });
        if (!resp.ok || !resp.body) throw new Error("HTTP " + resp.status);

        const reader = resp.body.getReader();
        const dec = new TextDecoder();
        let buf = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          const lines = buf.split("\n");
          buf = lines.pop() || "";
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            let d;
            try { d = JSON.parse(line.slice(6)); } catch (_) { continue; }
            if (d.done) {
              barFill.classList.remove("indeterminate");
              barFill.style.width = "100%";
              statusEl.textContent = "Téléchargé ✓";
              closeBtn.disabled = false;
              return;
            }
            if (d.error) {
              statusEl.textContent = "Erreur : " + d.error;
              barFill.classList.remove("indeterminate");
              closeBtn.disabled = false;
              return;
            }
            if (d.total && d.completed) {
              const pct = Math.round((d.completed / d.total) * 100);
              barFill.classList.remove("indeterminate");
              barFill.style.width = pct + "%";
              statusEl.textContent = (d.status || "downloading") + " · " + pct + "%";
            } else if (d.status) {
              statusEl.textContent = d.status;
            }
          }
        }
        statusEl.textContent = "Terminé";
        barFill.classList.remove("indeterminate");
        barFill.style.width = "100%";
        closeBtn.disabled = false;
      } catch (err) {
        statusEl.textContent = "Erreur : " + err.message;
        barFill.classList.remove("indeterminate");
        closeBtn.disabled = false;
      }
    })();
  }

  async function makeOllamaSection(llm) {
    let data = { available: false, models: [] };
    try { data = await J.api.get("/api/ollama/models"); } catch (_) {}

    const content = el("div");

    if (!data.available) {
      const row = el("div", { class: "ollama-offline-row" });
      row.innerHTML =
        '<span class="ollama-dot"></span>Ollama non disponible · ' +
        (llm.ollama_base_url || "localhost:11434");
      content.appendChild(row);
      content.appendChild(el("div", {
        class: "ollama-hint",
        text: "Démarrez Ollama pour gérer vos modèles locaux.",
      }));
      return ghostSec("Modèles locaux", "Ollama · function calling hors-ligne", null, content);
    }

    const downloaded = new Set(data.models.map(m => m.name || m.model || ""));
    const currentModel = llm.ollama_model || "";

    // ── Modèle actif ──
    const names = data.models.map(m => m.name || m.model || "").filter(Boolean);
    if (names.length) {
      content.appendChild(settingRow("Modèle actif", "OLLAMA_MODEL",
        makeSelect(names, currentModel, "OLLAMA_MODEL")));
    } else {
      content.appendChild(el("div", { class: "ollama-hint", text: "Aucun modèle téléchargé." }));
    }

    // ── Bibliothèque de téléchargement ──
    const toDownload = _OLLAMA_POPULAR.filter(m => !downloaded.has(m.id));
    if (toDownload.length) {
      content.appendChild(el("div", { class: "ollama-lib-sep", text: "Télécharger un modèle" }));
      const grid = el("div", { class: "ollama-model-grid" });
      toDownload.forEach(m => {
        const card = el("div", { class: "ollama-model-card" });
        const info = el("div");
        const nameLine = el("div", { class: "ollama-model-name" });
        nameLine.textContent = m.label;
        if (m.tag) {
          const badge = el("span", { class: "ollama-tag", text: m.tag });
          nameLine.appendChild(badge);
        }
        info.appendChild(nameLine);
        info.appendChild(el("div", { class: "ollama-model-size", text: m.gb + " Go · " + m.id }));
        card.appendChild(info);

        const dlBtn = el("button", { class: "m-btn", text: "↓" });
        dlBtn.title = "Télécharger " + m.id;
        dlBtn.addEventListener("click", () => showPullModal(m.id, () => renderModeles()));
        card.appendChild(dlBtn);
        grid.appendChild(card);
      });
      content.appendChild(grid);
    } else if (data.models.length) {
      content.appendChild(el("div", { class: "ollama-hint",
        text: "Tous les modèles recommandés sont présents." }));
    }

    return ghostSec("Modèles locaux", "Ollama · function calling hors-ligne", null, content);
  }

  /* ───────── 02 Modèles & API ───────── */
  async function renderModeles() {
    const s = await getSettings();
    const llm   = s.llm   || {};
    const audio = s.audio || {};
    const keys  = s.api_keys || {};

    const wrap = el("div", { style: { display:"flex", flexDirection:"column", gap:"40px" } });

    const CLAUDE = ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"];
    const VISION = ["gpt-4o", "gpt-4o-mini", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"];

    const modelList = el("div");
    [
      { label: "LLM provider",     sub: "LLM_PROVIDER",          options: ["api", "local"],                   val: llm.llm_provider },
      { label: "Backend API",      sub: "API_BACKEND",            options: ["anthropic", "mistral", "openai"], val: llm.api_backend },
      { label: "Modèle principal", sub: "ANTHROPIC_MODEL",        options: CLAUDE,                             val: llm.anthropic_model },
      { label: "Modèle vocal",     sub: "VOICE_ANTHROPIC_MODEL",  options: CLAUDE,                             val: llm.voice_anthropic_model },
      { label: "Modèle vision",    sub: "VISION_MODEL",           options: VISION,                             val: llm.vision_model },
    ].forEach(m => modelList.appendChild(settingRow(m.label, m.sub, makeSelect(m.options, m.val, m.sub))));
    wrap.appendChild(ghostSec("Modèles LLM", "LLM · voix · vision", null, modelList));
    wrap.appendChild(await makeOllamaSection(llm));

    // ── Audio & voix ──
    const audioList = el("div");
    [
      { label: "TTS Provider",     sub: "TTS_PROVIDER",     options: ["piper", "elevenlabs"],                      val: audio.tts_provider },
      { label: "ElevenLabs model", sub: "ELEVENLABS_MODEL",  options: ["eleven_flash_v2_5", "eleven_turbo_v2_5"],   val: audio.elevenlabs_model },
      { label: "Whisper model",    sub: "WHISPER_MODEL",     options: ["tiny", "base", "small", "medium", "large"], val: audio.whisper_model },
    ].forEach(f => audioList.appendChild(settingRow(f.label, f.sub, makeSelect(f.options, f.val, f.sub))));

    let voices = [];
    try { voices = await J.api.get("/api/settings/voices"); } catch (_) {}
    if (voices.length) {
      const vSelect = el("select", { class: "select-mono", style: { minWidth: "200px" } });
      voices.forEach(v => {
        const opt = el("option", { value: v.id, text: v.name });
        if (v.id === audio.elevenlabs_voice_id) opt.selected = true;
        vSelect.appendChild(opt);
      });
      const saveBtn = el("button", { class: "m-btn", text: "Sauv." });
      saveBtn.addEventListener("click", () => saveSetting("ELEVENLABS_VOICE_ID", vSelect.value, saveBtn));
      const ctrl = el("div", { style: { display:"flex", gap:"8px", alignItems:"center" } });
      ctrl.appendChild(vSelect); ctrl.appendChild(saveBtn);
      audioList.appendChild(settingRow("Voix ElevenLabs", "ELEVENLABS_VOICE_ID", ctrl));
    }
    wrap.appendChild(ghostSec("Audio & voix", "TTS · STT · voix", null, audioList));

    // Clés API — édition inline, sans popup navigateur
    const keyList = el("div");
    Object.entries(keys).forEach(([k, masked]) => {
      const ctrl = el("div", { style: { display:"flex", gap:"8px", alignItems:"center" } });
      const valEl = el("div", { class: "key-val", text: masked || "— non configurée" });
      const editBtn = el("button", { class: "m-btn", text: "Éditer" });

      const showDisplay = () => {
        ctrl.innerHTML = "";
        ctrl.appendChild(valEl);
        ctrl.appendChild(editBtn);
      };

      editBtn.addEventListener("click", () => {
        ctrl.innerHTML = "";
        const inp = el("input", {
          type: "password",
          class: "input-mono",
          style: { width: "220px" },
          placeholder: "Nouvelle valeur…",
        });
        const saveBtn  = el("button", { class: "m-btn",        text: "Sauvegarder" });
        const cancelBtn = el("button", { class: "m-btn ghost",  text: "✕" });

        saveBtn.addEventListener("click", async () => {
          if (!inp.value.trim()) return;
          await saveSetting(k, inp.value.trim(), saveBtn);
          valEl.textContent = "••••••••";
          showDisplay();
        });
        cancelBtn.addEventListener("click", showDisplay);

        inp.addEventListener("keydown", e => {
          if (e.key === "Enter") saveBtn.click();
          if (e.key === "Escape") cancelBtn.click();
        });

        ctrl.appendChild(inp);
        ctrl.appendChild(saveBtn);
        ctrl.appendChild(cancelBtn);
        inp.focus();
      });

      showDisplay();
      keyList.appendChild(settingRow(k, "clé secrète", ctrl));
    });
    wrap.appendChild(ghostSec("Clés API", "champs masqués", null, keyList));

    const page = pageWrapper("modeles", "Modèles & clés API", null, wrap);
    root.innerHTML = ""; root.appendChild(page);
  }

  /* ───────── 03 Conso ───────── */
  async function renderConso() {
    const C = window.JarvisCharts;

    let session = {}, daily = [], monthly = {}, byModel = [], hourly = Array(24).fill(0);
    try {
      [session, daily, monthly, byModel, hourly] = await Promise.all([
        J.api.get("/api/conso/session"),
        J.api.get("/api/conso/daily?days=30"),
        J.api.get("/api/conso/monthly"),
        J.api.get("/api/conso/by_model"),
        J.api.get("/api/conso/hourly"),
      ]);
    } catch (_) {}

    const BUDGET = 500;
    const monthlyCost = monthly.cost_usd || 0;
    const monthlyTokens = monthly.tokens || 0;
    const todayCost = session.total_cost_usd || 0;
    const budgetPct = Math.min(100, (monthlyCost / BUDGET) * 100);
    // Forecast: linear extrapolation from elapsed days
    const now = new Date();
    const dayOfMonth = now.getDate();
    const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
    const forecast = dayOfMonth > 0 ? monthlyCost / dayOfMonth * daysInMonth : monthlyCost;

    // Helper: format tokens
    function fmtTokens(n) {
      if (n >= 1e9) return (n / 1e9).toFixed(1) + "B";
      if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
      if (n >= 1e3) return (n / 1e3).toFixed(0) + "K";
      return String(n);
    }

    const wrap = el("div", { style: { display:"flex", flexDirection:"column" } });

    /* ── Hero 4 tiles ── */
    const hero = el("div", { class: "conso-hero" });

    // Tile 1: Total mois
    const t1 = el("div", { class: "conso-tile primary" });
    t1.appendChild(el("div", { class: "l", text: "Total · ce mois" }));
    const v1 = el("div", { class: "v" });
    const whole1 = Math.floor(monthlyCost);
    const dec1 = (monthlyCost % 1).toFixed(2).slice(1);
    v1.innerHTML = `$${whole1}<span class="dec">${dec1}</span> <span class="rel">ce mois</span>`;
    t1.appendChild(v1);
    t1.appendChild(el("div", { class: "d", text: `budget mensuel · $${BUDGET} · ${budgetPct.toFixed(0)}% consommé` }));
    const budgetBar = el("div", { class: "conso-budget-bar" });
    const budgetFill = el("i"); budgetFill.style.width = budgetPct.toFixed(1) + "%";
    budgetBar.appendChild(budgetFill); t1.appendChild(budgetBar);
    hero.appendChild(t1);

    // Tile 2: Aujourd'hui
    const t2 = el("div", { class: "conso-tile" });
    t2.appendChild(el("div", { class: "l", text: "Aujourd'hui" }));
    const v2 = el("div", { class: "v" });
    v2.innerHTML = `$${Math.floor(todayCost)}<span class="dec">${(todayCost % 1).toFixed(2).slice(1)}</span>`;
    t2.appendChild(v2);
    t2.appendChild(el("div", { class: "d sub", text: "session courante" }));
    const spark2 = C.sparkline(daily.slice(-7).map(d => d.cost_usd || 0), { color: "#4A9EFF" });
    spark2.setAttribute("class", "conso-spark");
    t2.appendChild(spark2);
    hero.appendChild(t2);

    // Tile 3: Tokens
    const t3 = el("div", { class: "conso-tile" });
    t3.appendChild(el("div", { class: "l", text: "Tokens · mois" }));
    const v3 = el("div", { class: "v" });
    const fmtTok = fmtTokens(monthlyTokens);
    const tokNum = fmtTok.slice(0, -1), tokUnit = fmtTok.slice(-1);
    v3.innerHTML = `${tokNum}<span class="unit">${tokUnit}</span>`;
    t3.appendChild(v3);
    t3.appendChild(el("div", { class: "d sub", text: "input + output · tous providers" }));
    const spark3 = C.sparkline(daily.slice(-7).map(d => d.cost_usd || 0), { color: "#36D399" });
    spark3.setAttribute("class", "conso-spark");
    t3.appendChild(spark3);
    hero.appendChild(t3);

    // Tile 4: Forecast
    const t4 = el("div", { class: "conso-tile" });
    t4.appendChild(el("div", { class: "l", text: "Forecast fin de mois" }));
    const v4 = el("div", { class: "v gold", text: "$" + Math.round(forecast) });
    t4.appendChild(v4);
    t4.appendChild(el("div", { class: "d sub", text: "extrapolation linéaire" }));
    const flag = el("div", { class: "conso-tile-flag" });
    flag.innerHTML = `<span class="dot"></span> extrapolé`;
    t4.appendChild(flag);
    hero.appendChild(t4);
    wrap.appendChild(hero);

    /* ── Evolution area chart ── */
    const evol = el("div", { class: "card conso-evolution" });
    const evolHd = el("div", { class: "card-hd" });
    const evolTtl = el("div");
    evolTtl.appendChild(el("h2", { text: "Évolution · 30 derniers jours" }));
    evolTtl.appendChild(el("span", { class: "sub", text: "coût USD / jour" }));
    evolHd.appendChild(evolTtl);

    // Range toggles
    const rangeWrap = el("div", { class: "conso-range" });
    const rg1 = el("div", { class: "conso-range-group" });
    const btnUSD = el("button", { text: "USD", class: "on" });
    rg1.appendChild(btnUSD);
    const rg2 = el("div", { class: "conso-range-group" });
    let activeRange = "30j";
    ["7j", "30j", "90j"].forEach(r => {
      const btn = el("button", { text: r });
      if (r === activeRange) btn.classList.add("on");
      btn.addEventListener("click", () => {
        rg2.querySelectorAll("button").forEach(b => b.classList.remove("on"));
        btn.classList.add("on");
        activeRange = r;
        const days = parseInt(r);
        const sliced = daily.slice(-days);
        areaWrap.innerHTML = "";
        areaWrap.appendChild(C.areaChart(sliced.map(d => d.cost_usd || 0), { color: "#4A9EFF" }));
      });
      rg2.appendChild(btn);
    });
    rangeWrap.appendChild(rg1); rangeWrap.appendChild(rg2);
    evolHd.appendChild(rangeWrap);
    evol.appendChild(evolHd);

    const areaWrap = el("div", { class: "conso-area-wrap" });
    areaWrap.appendChild(C.areaChart(daily.map(d => d.cost_usd || 0), { color: "#4A9EFF" }));
    evol.appendChild(areaWrap);

    const axis = el("div", { class: "conso-axis" });
    axis.appendChild(el("span", { text: "J-29" }));
    axis.appendChild(el("span", { text: "J-15" }));
    axis.appendChild(el("span", { text: "J-1" }));
    evol.appendChild(axis);

    const legend = el("div", { class: "conso-legend" });
    const li = el("span", { class: "conso-legend-item" });
    const sw = el("span", { class: "sw" }); sw.style.background = "#4A9EFF";
    li.appendChild(sw);
    li.appendChild(document.createTextNode(" Jarvis "));
    li.appendChild(el("span", { class: "val", text: "$" + monthlyCost.toFixed(2) }));
    legend.appendChild(li);
    evol.appendChild(legend);
    wrap.appendChild(evol);

    /* ── Row 2: Usage + Providers ── */
    const row2 = el("div", { class: "conso-row-2" });

    // Usage by type card
    const usageCard = el("div", { class: "card conso-usage" });
    const usageHd = el("div", { class: "card-hd" });
    const usageTtl = el("div");
    usageTtl.appendChild(el("h2", { text: "Répartition par type d'usage" }));
    usageTtl.appendChild(el("span", { class: "sub", text: "où part vraiment l'argent" }));
    usageHd.appendChild(usageTtl); usageCard.appendChild(usageHd);

    const byType = (monthly.by_type || []).slice(0, 6);
    if (byType.length) {
      byType.forEach(u => {
        const row = el("div", { class: "conso-usage-row" });
        const sw = el("span", { class: "conso-usage-sw" }); sw.style.background = u.color || "var(--accent)";
        row.appendChild(sw);
        const body = el("div", { class: "conso-usage-body" });
        body.appendChild(el("div", { class: "nm", text: u.label }));
        body.appendChild(el("div", { class: "ctx", text: u.sub }));
        const bar = el("div", { class: "conso-usage-bar" });
        const fill = el("i"); fill.style.width = Math.round((u.pct || 0) * 100) + "%";
        fill.style.background = u.color || "var(--accent)";
        bar.appendChild(fill); body.appendChild(bar);
        row.appendChild(body);
        const vals = el("div", { class: "conso-usage-vals" });
        vals.appendChild(el("div", { class: "val", text: "$" + (u.cost_usd || 0).toFixed(2) }));
        vals.appendChild(el("div", { class: "pct", text: Math.round((u.pct || 0) * 100) + "%" }));
        row.appendChild(vals);
        usageCard.appendChild(row);
      });
    } else {
      usageCard.appendChild(el("div", { class: "conso-empty", text: "— données insuffisantes" }));
    }
    row2.appendChild(usageCard);

    // Providers card (donut + heatmap)
    const provCard = el("div", { class: "card conso-providers" });
    const provHd = el("div", { class: "card-hd" });
    const provTtl = el("div");
    provTtl.appendChild(el("h2", { text: "Par provider" }));
    provTtl.appendChild(el("span", { class: "sub", text: "part du total" }));
    provHd.appendChild(provTtl); provCard.appendChild(provHd);

    const provList = monthly.providers || [];
    const PROV_COLORS = { anthropic: "#E5A23E", elevenlabs: "#A78BFA", openai: "#36D399", deepgram: "#4A9EFF" };
    const donutSlices = provList.map(p => ({
      value: p.cost_usd || 0,
      color: PROV_COLORS[p.name] || "var(--fg-3)",
    }));
    const donutTotal = "$" + Math.round(monthlyCost);

    const provGrid = el("div", { class: "conso-providers-grid" });
    const donutEl = C.donut(donutSlices, donutTotal);
    donutEl.setAttribute("class", "conso-donut");
    provGrid.appendChild(donutEl);
    const provLeg = el("div", { class: "conso-providers-legend" });
    provList.forEach(p => {
      const row = el("div", { class: "conso-providers-row" });
      const sw = el("span", { class: "sw" }); sw.style.background = PROV_COLORS[p.name] || "var(--fg-3)";
      row.appendChild(sw);
      row.appendChild(el("span", { class: "nm", text: p.name }));
      row.appendChild(el("span", { class: "val", text: "$" + (p.cost_usd || 0).toFixed(2) }));
      provLeg.appendChild(row);
    });
    provGrid.appendChild(provLeg);
    provCard.appendChild(provGrid);

    // Heatmap
    const peakHour = hourly.indexOf(Math.max(...hourly));
    const peakVal = Math.max(...hourly);
    const heat = el("div", { class: "conso-heat" });
    const heatHd = el("div", { class: "conso-heat-head" });
    heatHd.appendChild(el("span", { text: "Usage · 24h · $/heure" }));
    heatHd.appendChild(el("span", { text: `peak ${String(peakHour).padStart(2,"0")}:00 · $${peakVal.toFixed(3)}` }));
    heat.appendChild(heatHd);
    heat.appendChild(C.heatRow(hourly));
    const heatFt = el("div", { class: "conso-heat-foot" });
    ["00:00", "06:00", "12:00", "18:00", "23:59"].forEach(t => heatFt.appendChild(el("span", { text: t })));
    heat.appendChild(heatFt);
    provCard.appendChild(heat);
    row2.appendChild(provCard);
    wrap.appendChild(row2);

    /* ── Row 3: Par modèle + Par skill ── */
    const row3 = el("div", { class: "conso-row-2" });

    // Par modèle
    const modCard = el("div", { class: "card" });
    const modHd = el("div", { class: "card-hd" });
    const modTtl = el("div");
    modTtl.appendChild(el("h2", { text: "Par modèle" }));
    modTtl.appendChild(el("span", { class: "sub", text: "tokens consommés · part" }));
    modHd.appendChild(modTtl); modCard.appendChild(modHd);
    if (byModel.length) {
      byModel.slice(0, 5).forEach(m => {
        const row = el("div", { class: "conso-mod-row" });
        row.appendChild(el("div", { class: "nm", text: m.model }));
        const bar = el("div", { class: "conso-mod-bar" });
        const fill = el("i"); fill.style.width = (m.pct || 0) + "%";
        bar.appendChild(fill); row.appendChild(bar);
        const vals = el("div", { class: "conso-mod-vals" });
        vals.appendChild(el("span", { class: "meta", text: fmtTokens(m.tokens || 0) }));
        vals.appendChild(el("span", { class: "meta accent", text: "$" + (m.cost_usd || 0).toFixed(2) }));
        row.appendChild(vals);
        modCard.appendChild(row);
      });
    } else {
      modCard.appendChild(el("div", { class: "conso-empty", text: "— aucune donnée ce mois" }));
    }
    row3.appendChild(modCard);

    // Par skill (placeholder — pas de données backend pour l'instant)
    const skillCard = el("div", { class: "card" });
    const skillHd = el("div", { class: "card-hd" });
    const skillTtl = el("div");
    skillTtl.appendChild(el("h2", { text: "Par skill" }));
    skillTtl.appendChild(el("span", { class: "sub", text: "skills qui consomment le plus" }));
    skillHd.appendChild(skillTtl); skillCard.appendChild(skillHd);
    skillCard.appendChild(el("div", { class: "conso-empty", text: "— bientôt disponible" }));
    row3.appendChild(skillCard);
    wrap.appendChild(row3);

    const page = pageWrapper("conso", "Ce que Jarvis consomme pour fonctionner", null, wrap);
    root.innerHTML = ""; root.appendChild(page);
  }

  /* ───────── 04 Système ───────── */
  async function renderSysteme() {
    let perf = {};
    try { perf = await J.api.get("/api/system/perf"); } catch (_) {}

    const wrap = el("div", { style: { display:"flex", flexDirection:"column", gap:"40px" } });

    // Perf tiles
    const perfGrid = el("div", { class: "perf-grid" });
    const tiles = [
      { label: "CPU",     val: (perf.cpu_pct||0).toFixed(0), unit: "%", bar: perf.cpu_pct },
      { label: "RAM",     val: (perf.ram_used_gb||0).toFixed(1), unit: " GB", bar: perf.ram_pct },
      { label: "Disque",  val: (perf.disk_used_gb||0).toFixed(0), unit: " GB", bar: perf.disk_pct },
      perf.battery_pct != null
        ? { label: "Batterie", val: perf.battery_pct, unit: "%", bar: perf.battery_pct }
        : { label: "Uptime", val: perf.uptime_s ? Math.floor(perf.uptime_s/3600)+"h" : "—", unit: "", bar: null },
    ];
    tiles.forEach(t => {
      const tile = el("div", { class: "perf-tile" });
      tile.appendChild(el("div", { class: "perf-label", text: t.label }));
      const valEl = el("div", { class: "perf-val" });
      valEl.textContent = t.val;
      valEl.appendChild(el("span", { class: "perf-unit", text: t.unit }));
      tile.appendChild(valEl);
      if (t.bar != null) {
        const bw = el("div", { class: "perf-bar-wrap" });
        bw.appendChild(el("div", { class: "perf-bar-fill", style: { width: Math.min(100, t.bar||0)+"%", background: t.bar > 80 ? "var(--red)" : "var(--accent)" } }));
        tile.appendChild(bw);
      }
      perfGrid.appendChild(tile);
    });
    wrap.appendChild(ghostSec("Performances", perf.platform || "système", null, perfGrid));

    // Stats Jarvis
    let stats = {};
    try { stats = await J.api.get("/api/system/stats"); } catch (_) {}
    if (Object.keys(stats).length) {
      const statGrid = el("div", { class: "perf-grid" });
      const stiles = [
        { label: "Projets",  val: (stats.projects||{}).total||0, unit: "" },
        { label: "En cours", val: (stats.projects||{}).running||0, unit: "" },
        { label: "Topics",   val: (stats.memory||{}).topics||0, unit: "" },
        { label: "Sessions", val: (stats.sessions||{}).total||0, unit: "" },
      ];
      stiles.forEach(t => {
        const tile = el("div", { class: "perf-tile" });
        tile.appendChild(el("div", { class: "perf-label", text: t.label }));
        tile.appendChild(el("div", { class: "perf-val", text: String(t.val) }));
        statGrid.appendChild(tile);
      });
      wrap.appendChild(ghostSec("Statistiques Jarvis", "projets · mémoire · sessions", null, statGrid));
    }

    // Logs
    let logs = [];
    try { logs = await J.api.get("/api/system/logs"); } catch (_) {}
    const logView = el("div", { class: "log-viewer" });
    (logs.length ? logs : ["Aucun log récent"]).forEach(line => {
      const entry = el("span", { class: "log-entry" + (line.includes("ERROR")?" error":line.includes("WARN")?" warn":""), text: line });
      logView.appendChild(entry);
      logView.appendChild(document.createTextNode("\n"));
    });
    logView.scrollTop = logView.scrollHeight;
    wrap.appendChild(ghostSec("Logs récents", logs.length + " lignes", null, logView));

    // Danger zone
    const danger = el("div", { class: "danger-zone" });
    danger.appendChild(el("div", { class: "danger-title", text: "ZONE DANGER" }));

    const cleanRow = el("div", { class: "danger-row" });
    const cleanTxt = el("div");
    cleanTxt.appendChild(el("div", { class: "danger-label", text: "Nettoyer les projets terminés" }));
    cleanTxt.appendChild(el("div", { class: "danger-sub", text: "Supprime les workspaces done/failed/killed" }));
    cleanRow.appendChild(cleanTxt);
    const cleanBtn = el("button", { class: "btn-danger", text: "Nettoyer" });
    cleanBtn.addEventListener("click", async () => {
      if (!confirm("Nettoyer tous les projets terminés ?")) return;
      cleanBtn.textContent = "…"; cleanBtn.disabled = true;
      try {
        const r = await J.api.delete("/api/system/projects/done");
        J.notify({ kind: "success", text: r.removed + " projets supprimés" });
      } catch (e) { J.notify({ kind: "error", text: e.message }); }
      cleanBtn.textContent = "Nettoyer"; cleanBtn.disabled = false;
    });
    cleanRow.appendChild(cleanBtn);
    danger.appendChild(cleanRow);

    const restartRow = el("div", { class: "danger-row" });
    const restartTxt = el("div");
    restartTxt.appendChild(el("div", { class: "danger-label", text: "Redémarrer Jarvis" }));
    restartTxt.appendChild(el("div", { class: "danger-sub", text: "Relance le processus FastAPI" }));
    restartRow.appendChild(restartTxt);
    const restartBtn = el("button", { class: "btn-danger", text: "Redémarrer" });
    restartBtn.addEventListener("click", async () => {
      if (!confirm("Redémarrer Jarvis ?")) return;
      restartBtn.textContent = "…"; restartBtn.disabled = true;
      try { await J.api.post("/api/system/restart"); }
      catch (_) { setTimeout(() => window.location.reload(), 3000); }
    });
    restartRow.appendChild(restartBtn);
    danger.appendChild(restartRow);

    wrap.appendChild(danger);

    const page = pageWrapper("systeme", "Système & processus", null, wrap);
    root.innerHTML = ""; root.appendChild(page);
  }

  /* ───────── 05 À propos ───────── */
  async function renderApropos() {
    const year = new Date().getFullYear();

    const wrap = el("div", { class: "about2" });

    // ── Header : nom + badge ──────────────────────────────────
    const hdr = el("div", { class: "about2-hdr" });
    const nameWrap = el("div", { class: "about2-name-wrap" });
    nameWrap.appendChild(el("div", { class: "about2-name", text: "Jarvis" }));
    const sub = el("div", { class: "about2-sub-row" });
    sub.appendChild(el("span", { class: "about2-badge", text: "v4.0" }));
    sub.appendChild(el("span", { class: "about2-tagline", text: "Assistant personnel intelligent · vocal · proactif" }));
    nameWrap.appendChild(sub);
    hdr.appendChild(nameWrap);
    wrap.appendChild(hdr);

    wrap.appendChild(el("div", { class: "about2-sep" }));

    // ── Métadonnées ───────────────────────────────────────────
    const meta = el("dl", { class: "about2-meta" });
    [
      ["Auteur",  "Barth Houot"],
      ["Licence", "Propriétaire · Tous droits réservés"],
      ["Année",   String(year)],
    ].forEach(([k, v]) => {
      meta.appendChild(el("dt", { class: "about2-dt", text: k }));
      meta.appendChild(el("dd", { class: "about2-dd", text: v }));
    });
    wrap.appendChild(meta);

    wrap.appendChild(el("div", { class: "about2-sep" }));

    // ── Copyright ─────────────────────────────────────────────
    wrap.appendChild(el("p", { class: "about2-copy",
      text: `© ${year} Barth Houot — Tous droits réservés.` }));

    // ── Bouton mise à jour ────────────────────────────────────
    const updateBtn = el("button", { class: "about2-update-btn", text: "Vérifier les mises à jour" });
    const updateStatus = el("div", { class: "about2-update-status" });

    updateBtn.addEventListener("click", async () => {
      updateBtn.disabled = true;
      updateBtn.textContent = "Mise à jour en cours…";
      updateStatus.textContent = "";
      updateStatus.className = "about2-update-status";
      try {
        const res = await J.api.post("/admin/api/system/update", {});
        if (res.already_up_to_date) {
          updateStatus.textContent = "Jarvis est déjà à jour.";
          updateStatus.className = "about2-update-status ok";
          updateBtn.textContent = "À jour";
        } else if (res.ok) {
          updateStatus.textContent = "Mise à jour réussie. Redémarre Jarvis pour appliquer les changements.";
          updateStatus.className = "about2-update-status ok";
          updateBtn.textContent = "Redémarrer";
          updateBtn.disabled = false;
          updateBtn.addEventListener("click", () => {
            J.api.post("/admin/api/system/restart", {}).catch(() => {});
          }, { once: true });
        } else {
          updateStatus.textContent = "Erreur : " + (res.error || "Échec de la mise à jour.");
          updateStatus.className = "about2-update-status err";
          updateBtn.textContent = "Réessayer";
          updateBtn.disabled = false;
        }
      } catch (_) {
        updateStatus.textContent = "Impossible de contacter le serveur.";
        updateStatus.className = "about2-update-status err";
        updateBtn.textContent = "Réessayer";
        updateBtn.disabled = false;
      }
    });

    const updateWrap = el("div", { class: "about2-update-wrap" });
    updateWrap.appendChild(updateBtn);
    updateWrap.appendChild(updateStatus);
    wrap.appendChild(updateWrap);

    const page = pageWrapper("apropos", "À propos de Jarvis", null, wrap);
    root.innerHTML = ""; root.appendChild(page);
  }

  /* ───────── Router ───────── */
  const RENDERERS = {
    preferences: renderPreferences,
    modeles:     renderModeles,
    conso:       renderConso,
    systeme:     renderSysteme,
    apropos:     renderApropos,
  };

  function navigate(pageId) {
    _activePage = pageId;
    const nav = document.getElementById("j-rooms-pages");
    if (nav) {
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
    mode: "config",
    pages: PAGES,
    activePage: _activePage,
    onNav: (id) => navigate(id),
  });

  J.registerCommands(PAGES.map(p => ({
    kind: "nav", id: "cfg-" + p.id, group: "Réglages",
    title: p.label, glyph: "→",
    run: () => navigate(p.id),
  })));

  renderPreferences();
})();
