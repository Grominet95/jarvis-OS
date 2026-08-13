(function () {
  "use strict";

  const J = window.Jarvis;
  const el = J.el;
  const root = document.getElementById("setup-root");
  const btnBack = document.getElementById("btn-back");
  const btnNext = document.getElementById("btn-next");
  const stepIndicator = document.getElementById("step-indicator");

  const STEPS = [
    { id: "welcome", title: "Bienvenue" },
    { id: "identity", title: "Identité" },
    { id: "llm", title: "LLM" },
    { id: "modules", title: "Modules" },
    { id: "finish", title: "Terminer" },
  ];

  // Libellés des backends LLM proposés (tous supportés côté serveur).
  const LLM_BACKENDS = [
    { value: "anthropic", label: "Anthropic (Claude)" },
    { value: "openai", label: "OpenAI (GPT)" },
    { value: "mistral", label: "Mistral" },
    { value: "gemini", label: "Google Gemini" },
    { value: "local", label: "Local (Ollama)" },
  ];

  let step = 0;
  let doneUrl = "";
  let secretsSet = {};
  let bundlePollTimer = null;
  let bundleDownloading = false;

  const form = {
    user_firstname: "",
    api_backend: "anthropic",
    anthropic_api_key: "",
    openai_api_key: "",
    mistral_api_key: "",
    gemini_api_key: "",
    ollama_model: "mistral",
    ollama_base_url: "http://localhost:11434",
    proactive_city: "Paris",
    proactive_lat: "48.85",
    proactive_lon: "2.35",
    tts_provider: "piper",
    elevenlabs_api_key: "",
    elevenlabs_voice_id: "",
    voice_enabled: false,
    livekit_cloud: false,
    livekit_url: "",
    livekit_api_key: "",
    livekit_api_secret: "",
    deepgram_api_key: "",
    aisstream_key: "",
    face_recognition_enabled: false,
    elevenlabs_enabled: false,
    aisstream_enabled: false,
  };

  // ── Helpers ────────────────────────────────────────────────────────────

  function cardHeader(card, title, lead) {
    const hd = el("div", { class: "setup-hd" });
    hd.appendChild(el("div", {
      class: "setup-hd-eyebrow",
      text: "Étape " + (step + 1) + " / " + STEPS.length,
    }));
    hd.appendChild(el("h1", { class: "setup-hd-title", text: title }));
    if (lead) hd.appendChild(el("p", { class: "setup-lead", text: lead }));
    card.appendChild(hd);
  }

  function field(label, key, opts) {
    const options = opts || {};
    const wrap = el("div", { class: "setup-field" });
    wrap.appendChild(el("label", { text: label, for: key }));
    const input = el("input", {
      id: key,
      type: options.type || "text",
      value: form[key] || "",
      placeholder: options.placeholder || "",
    });
    input.addEventListener("input", () => {
      form[key] = input.value;
    });
    wrap.appendChild(input);
    return wrap;
  }

  // Champ secret : si la clé est déjà en place côté serveur et le champ est
  // vide, on l'indique et on laisse vide = « conserver l'existante ».
  function secretField(label, key) {
    const already = secretsSet[key] && !form[key];
    return field(label, key, {
      type: "password",
      placeholder: already ? "•••• déjà configurée (laisser vide pour conserver)" : "",
    });
  }

  // Dropdown custom (le <select> natif macOS est moche et non stylable).
  function selectField(label, key, options) {
    const wrap = el("div", { class: "setup-field" });
    if (label) wrap.appendChild(el("label", { text: label }));
    const sel = el("div", { class: "setup-select" });
    const current = options.find((o) => o.value === form[key]) || options[0];
    const btn = el("button", { class: "setup-select-btn", type: "button" });
    btn.appendChild(el("span", { text: current ? current.label : "" }));
    btn.appendChild(el("span", { class: "setup-select-chev", text: "▾" }));
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const wasOpen = sel.classList.contains("open");
      document.querySelectorAll(".setup-select.open").forEach((s) => s.classList.remove("open"));
      if (!wasOpen) sel.classList.add("open");
    });
    const menu = el("div", { class: "setup-select-menu" });
    options.forEach((o) => {
      const opt = el("div", {
        class: "setup-select-opt" + (o.value === form[key] ? " is-sel" : ""),
        text: o.label,
      });
      opt.addEventListener("click", () => {
        form[key] = o.value;
        render();
      });
      menu.appendChild(opt);
    });
    sel.appendChild(btn);
    sel.appendChild(menu);
    wrap.appendChild(sel);
    return wrap;
  }

  // Sélecteur de fichier custom (l'input file natif est moche).
  function fileField(label, accept, onFile) {
    const wrap = el("div", { class: "setup-field" });
    wrap.appendChild(el("label", { text: label }));
    const row = el("div", { class: "setup-file" });
    const btn = el("button", { class: "setup-file-btn", type: "button", text: "Parcourir…" });
    const name = el("span", { class: "setup-file-name", text: "Aucun fichier choisi" });
    const input = el("input", { type: "file", accept: accept });
    input.style.display = "none";
    btn.addEventListener("click", () => input.click());
    input.addEventListener("change", () => {
      if (input.files && input.files[0]) {
        name.textContent = input.files[0].name;
        onFile(input.files[0]);
      }
    });
    row.appendChild(btn);
    row.appendChild(name);
    row.appendChild(input);
    wrap.appendChild(row);
    return wrap;
  }

  function checkbox(label, key) {
    const wrap = el("label", { class: "setup-check" });
    const input = el("input", { type: "checkbox" });
    input.checked = !!form[key];
    input.addEventListener("change", () => {
      form[key] = input.checked;
      render();
    });
    wrap.appendChild(input);
    wrap.appendChild(el("span", { text: label }));
    return wrap;
  }

  function formatEta(seconds) {
    if (seconds == null || seconds < 0) return "";
    if (seconds < 60) return seconds + "s restantes";
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return m + "m " + s + "s restantes";
  }

  function formatSpeed(speedMbS) {
    if (!speedMbS || speedMbS <= 0) return "";
    return speedMbS.toFixed(1) + " Mo/s";
  }

  function formatBundleProgressLabel(st) {
    const phaseLabels = {
      download: "Téléchargement",
      extract: "Extraction",
      rehome: "Configuration",
      stage: "Modèles",
    };
    const parts = [];
    if (phaseLabels[st.phase]) parts.push(phaseLabels[st.phase]);
    if (st.speed_mb_s) parts.push(formatSpeed(st.speed_mb_s));
    if (st.eta_seconds != null && st.phase !== "done") parts.push(formatEta(st.eta_seconds));
    if (st.message) parts.push(st.message);
    return parts.join(" · ");
  }

  function updateBundleProgressUI(st) {
    const wrap = document.getElementById("bundle-progress");
    const bar = document.getElementById("bundle-progress-bar");
    const label = document.getElementById("bundle-progress-label");
    const badge = document.getElementById("bundle-status-badge");
    const finished = st.phase === "done" || !!(st.prerequisites && st.prerequisites.can_continue);
    if (wrap) wrap.hidden = finished || (!bundleDownloading && st.phase !== "done");
    if (bar) bar.style.width = (st.percent || 0) + "%";
    if (label) label.textContent = formatBundleProgressLabel(st);
    if (badge && bundleDownloading && !finished) {
      badge.className = "setup-status-warn";
      badge.textContent = "en cours";
    } else if (badge && finished) {
      badge.className = "setup-status-ok";
      badge.textContent = "prêt";
    }
  }

  async function finishBundleDownload(st, ok) {
    stopBundlePoll();
    bundleDownloading = false;
    try {
      cachedStatus = await J.api.get("/api/setup/status");
      if (st.prerequisites) {
        cachedStatus.prerequisites = st.prerequisites;
      }
    } catch (_) {}
    render();
    if (ok) {
      J.notify({ kind: "ok", text: "Bundle offline installé" });
    }
  }

  async function syncBundleDownloadState() {
    try {
      const st = await J.api.get("/api/setup/bundle/download/status");
      if (st.phase === "done" || (st.prerequisites && st.prerequisites.can_continue)) {
        bundleDownloading = false;
        if (cachedStatus && st.prerequisites) {
          cachedStatus.prerequisites = st.prerequisites;
        }
        if (st.phase === "done") {
          await finishBundleDownload(st, true);
        }
        return;
      }
      if (st.running || (st.phase && st.phase !== "idle" && st.phase !== "error")) {
        bundleDownloading = true;
        pollBundleDownload();
      }
    } catch (_) {}
  }

  function statusRow(label, ok, detail) {
    const cls = ok ? "setup-status-ok" : "setup-status-warn";
    const row = el("div", { class: "setup-status-row" });
    row.appendChild(el("span", { text: label }));
    row.appendChild(el("span", { class: cls, text: detail }));
    return row;
  }

  function statusRowDetailed(label, ok, badge, lines) {
    const cls = ok ? "setup-status-ok" : "setup-status-warn";
    const row = el("div", { class: "setup-status-row setup-status-row--detail" });
    const head = el("div", { class: "setup-status-head" });
    head.appendChild(el("span", { text: label }));
    head.appendChild(el("span", { class: cls, text: badge }));
    row.appendChild(head);
    (lines || []).filter(Boolean).forEach((line) => {
      row.appendChild(el("div", { class: "setup-status-sub", text: line }));
    });
    return row;
  }

  function canLeaveWelcome() {
    const prereq = (cachedStatus && cachedStatus.prerequisites) || {};
    return !!prereq.can_continue && !bundleDownloading;
  }

  function moduleHint(text) {
    return el("p", { class: "setup-hint", text: text });
  }

  function stopBundlePoll() {
    if (bundlePollTimer) {
      clearInterval(bundlePollTimer);
      bundlePollTimer = null;
    }
  }

  async function refreshPrerequisites() {
    if (bundleDownloading) return;
    try {
      const status = await J.api.get("/api/setup/status");
      const prev = cachedStatus && cachedStatus.prerequisites;
      cachedStatus = status;
      const next = status && status.prerequisites;
      if (step === 0 && next && (!prev || JSON.stringify(prev) !== JSON.stringify(next))) {
        render();
      }
    } catch (_) {}
  }

  function pollBundleDownload() {
    stopBundlePoll();
    bundlePollTimer = setInterval(async () => {
      try {
        const st = await J.api.get("/api/setup/bundle/download/status");
        updateBundleProgressUI(st);
        const btn = document.getElementById("bundle-download-btn");
        if (st.phase === "done") {
          await finishBundleDownload(st, true);
        } else if (st.phase === "error") {
          stopBundlePoll();
          bundleDownloading = false;
          render();
          if (btn) {
            btn.disabled = false;
            btn.textContent = "Télécharger";
          }
          J.notify({ kind: "err", text: st.error || "Échec du téléchargement" });
        }
      } catch (err) {
        stopBundlePoll();
        bundleDownloading = false;
        render();
        J.notify({ kind: "err", text: err.message || "Échec du suivi de téléchargement" });
      }
    }, 500);
  }

  async function startBundleDownload() {
    if (bundleDownloading) return;
    bundleDownloading = true;
    const btn = document.getElementById("bundle-download-btn");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Téléchargement…";
    }
    const progress = document.getElementById("bundle-progress");
    if (progress) progress.hidden = false;
    render();
    try {
      const resp = await J.api.post("/api/setup/bundle/download", {});
      if (!resp.started) {
        bundleDownloading = false;
        if (btn) {
          btn.disabled = false;
          btn.textContent = "Télécharger";
        }
        if (resp.reason === "already_present") {
          J.notify({ kind: "ok", text: "Bundle déjà présent" });
          await refreshPrerequisites();
        } else if (resp.reason === "windows_only") {
          J.notify({ kind: "err", text: "Téléchargement auto disponible uniquement sur Windows" });
        } else {
          J.notify({ kind: "err", text: "Téléchargement déjà en cours" });
        }
        return;
      }
      pollBundleDownload();
    } catch (err) {
      bundleDownloading = false;
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Télécharger";
      }
      J.notify({ kind: "err", text: err.message || "Impossible de démarrer le téléchargement" });
    }
  }

  function renderBundleStatusRow(prereq, bundleInfo) {
    const block = el("div", { class: "setup-status-row setup-status-row--bundle" });
    const inspection = prereq.bundle_inspection || {};
    const head = el("div", { class: "setup-bundle-head" });
    head.appendChild(el("span", { text: "Bundle offline" }));
    const right = el("div", { class: "setup-status-actions" });
    const ok = !!prereq.bundle;
    let badgeText = ok ? "prêt" : (bundleDownloading ? "en cours" : "absent");
    if (inspection.present && !ok && !bundleDownloading) badgeText = "incomplet";
    const badge = el("span", {
      id: "bundle-status-badge",
      class: ok ? "setup-status-ok" : "setup-status-warn",
      text: badgeText,
    });
    right.appendChild(badge);
    if (!ok && bundleInfo && bundleInfo.downloadable && !bundleDownloading) {
      const btn = el("button", {
        id: "bundle-download-btn",
        class: "setup-dl-btn",
        type: "button",
        text: "Télécharger",
      });
      btn.addEventListener("click", startBundleDownload);
      right.appendChild(btn);
    } else if (bundleDownloading) {
      const btn = el("button", {
        id: "bundle-download-btn",
        class: "setup-dl-btn",
        type: "button",
        text: "Téléchargement…",
      });
      btn.disabled = true;
      right.appendChild(btn);
    }
    head.appendChild(right);
    block.appendChild(head);

    const progress = el("div", {
      id: "bundle-progress",
      class: "setup-bundle-progress",
      hidden: !bundleDownloading,
    });
    const track = el("div", { class: "setup-progress-track" });
    track.appendChild(el("div", { id: "bundle-progress-bar", class: "setup-progress-bar" }));
    progress.appendChild(track);
    progress.appendChild(el("div", {
      id: "bundle-progress-label",
      class: "setup-progress-label",
      text: bundleDownloading ? "Téléchargement…" : "",
    }));
    block.appendChild(progress);
    if (inspection.present && !ok && inspection.missing && inspection.missing.length) {
      block.appendChild(el("div", {
        class: "setup-status-sub",
        text: "Manquant : " + inspection.missing.join(", "),
      }));
    }
    return block;
  }

  function renderIndicator() {
    stepIndicator.innerHTML = "";
    STEPS.forEach((s, i) => {
      const dot = el("div", {
        class: "setup-step-dot" + (i < step ? " done" : i === step ? " active" : ""),
        title: s.title,
      });
      stepIndicator.appendChild(dot);
    });
  }

  // ── Steps ──────────────────────────────────────────────────────────────

  function renderWelcome(status) {
    const card = el("div", { class: "setup-card" });
    cardHeader(
      card,
      "Configuration Jarvis",
      "Cet assistant configure ton instance locale. Sur Windows, tu peux télécharger le bundle offline (~700 Mo) directement ici.",
    );
    const list = el("div", { class: "setup-status-list" });
    const prereq = status.prerequisites || {};
    const bundleInfo = status.bundle_download || {};
    list.appendChild(renderBundleStatusRow(prereq, bundleInfo));

    const py = prereq.python_detail || {};
    const pyLines = [];
    if (py.system && py.system.installed) {
      pyLines.push("Machine · Python " + (py.system.version || "?"));
    } else {
      pyLines.push("Machine · Python non détecté");
    }
    if (py.monorepo && py.monorepo.present) {
      pyLines.push("Monorepo · Python " + (py.monorepo.version || "?"));
    } else {
      pyLines.push("Monorepo · .venv absent");
    }
    if (py.bundle && py.bundle.present) {
      pyLines.push("Bundle · Python " + (py.bundle.version || "?"));
    } else if (prereq.bundle_inspection && prereq.bundle_inspection.present) {
      pyLines.push("Bundle · venv absent");
    }
    if (py.runtime_source) {
      pyLines.push("Runtime Jarvis · " + py.runtime_source
        + (py.runtime_version ? " " + py.runtime_version : ""));
    }
    list.appendChild(statusRowDetailed(
      "Python",
      !!prereq.python,
      prereq.python ? "prêt" : "manquant",
      pyLines,
    ));

    const yolo = prereq.yolo_detail || {};
    list.appendChild(statusRowDetailed(
      "Modèle YOLO",
      !!prereq.yolo_model,
      prereq.yolo_model ? "prêt" : "manquant",
      [
        yolo.project_path ? "Projet · " + yolo.project_path.split("/").slice(-1)[0] : null,
        yolo.bundle_path ? "Bundle · " + yolo.bundle_path.split("/").slice(-2).join("/") : null,
        !prereq.yolo_model ? "Copié depuis le bundle à la fin de la config si absent" : null,
      ],
    ));

    const piper = prereq.piper_detail || {};
    list.appendChild(statusRowDetailed(
      "Modèle Piper",
      !!prereq.piper_model,
      prereq.piper_model ? "prêt" : "manquant",
      [
        piper.project_path ? "Projet · " + piper.project_path.split("/").slice(-2).join("/") : null,
        piper.bundle_path ? "Bundle · " + piper.bundle_path.split("/").slice(-2).join("/") : null,
        !prereq.piper_model ? "Copié depuis le bundle à la fin de la config si absent" : null,
      ],
    ));

    const lk = prereq.livekit_detail || {};
    list.appendChild(statusRowDetailed(
      "LiveKit local",
      !!prereq.livekit_binary,
      prereq.livekit_binary ? "prêt" : "optionnel",
      [
        lk.project_path ? "Projet · bin/" + lk.project_path.split("/").slice(-1)[0] : null,
        lk.bundle_path ? "Bundle · " + lk.bundle_path.split("/").slice(-2).join("/") : null,
        !prereq.livekit_binary ? "Requis uniquement pour le pipeline vocal local" : null,
      ],
    ));
    card.appendChild(list);
    if (!prereq.bundle && !bundleDownloading) {
      if (bundleInfo.downloadable) {
        card.appendChild(moduleHint(
          "Clique sur Télécharger, ou place manuellement un dossier bundle/ (manifest.json + .venv).",
        ));
      } else {
        card.appendChild(moduleHint(
          "Linux/macOS : lance scripts/release/build_bundle.sh, ou clone une release avec bundle/ inclus.",
        ));
      }
    } else if (prereq.bundle_inspection && prereq.bundle_inspection.present && !prereq.bundle) {
      card.appendChild(moduleHint(
        "Dossier bundle/ détecté mais incomplet — vérifie les fichiers manquants ci-dessus.",
      ));
    } else if (prereq.bundle && (!prereq.yolo_model || !prereq.piper_model)) {
      card.appendChild(moduleHint(
        "Les modèles YOLO et Piper seront copiés depuis le bundle à la fin de la configuration.",
      ));
    }
    return card;
  }

  function renderIdentity() {
    const card = el("div", { class: "setup-card" });
    cardHeader(card, "Identité", "Ton prénom est affiché lors du scan biométrique et dans l'interface.");
    card.appendChild(field("Prénom", "user_firstname", { placeholder: "Maxime" }));
    card.appendChild(field("Ville", "proactive_city", { placeholder: "Lyon" }));
    card.appendChild(
      fileField("Photo de référence (optionnel)", ".jpg,.jpeg", async (file) => {
        const body = new FormData();
        body.append("file", file);
        try {
          await fetch("/api/setup/upload-face", { method: "POST", body });
          J.notify({ kind: "ok", text: "Photo enregistrée dans vision_data/faces/" });
        } catch (_) {
          J.notify({ kind: "err", text: "Échec upload photo" });
        }
      }),
    );
    return card;
  }

  function renderLlm() {
    const card = el("div", { class: "setup-card" });
    cardHeader(card, "LLM principal", "Optionnel : tu peux laisser la clé vide et la configurer plus tard dans les réglages.");
    card.appendChild(selectField("Backend", "api_backend", LLM_BACKENDS));

    if (form.api_backend === "openai") {
      card.appendChild(secretField("Clé API OpenAI", "openai_api_key"));
    } else if (form.api_backend === "mistral") {
      card.appendChild(secretField("Clé API Mistral", "mistral_api_key"));
    } else if (form.api_backend === "gemini") {
      card.appendChild(secretField("Clé API Gemini", "gemini_api_key"));
    } else if (form.api_backend === "local") {
      card.appendChild(field("Modèle Ollama", "ollama_model", { placeholder: "mistral, llama3..." }));
      card.appendChild(field("URL Ollama", "ollama_base_url", { placeholder: "http://localhost:11434" }));
      card.appendChild(el("p", {
        class: "setup-lead",
        text: "Aucune clé API requise. Assure-toi qu'Ollama tourne et que le modèle est téléchargé (ollama pull).",
      }));
    } else {
      card.appendChild(secretField("Clé API Anthropic", "anthropic_api_key"));
    }
    return card;
  }

  function renderModules() {
    const card = el("div", { class: "setup-card" });
    cardHeader(card, "Modules optionnels", "Active uniquement ce dont tu as besoin. Tout reste modifiable plus tard dans les réglages ou .env.");
    card.appendChild(checkbox("Utiliser ElevenLabs (sinon Piper local)", "elevenlabs_enabled"));
    if (form.elevenlabs_enabled) {
      form.tts_provider = "elevenlabs";
      card.appendChild(secretField("Clé ElevenLabs", "elevenlabs_api_key"));
      card.appendChild(field("Voice ID ElevenLabs", "elevenlabs_voice_id", {
        placeholder: "ex. 21m00Tcm4TlvDq8ikWAM",
      }));
      card.appendChild(moduleHint(
        "elevenlabs.io → Profile → API Keys · Voices → copie l'ID de la voix choisie.",
      ));
    } else {
      form.tts_provider = "piper";
      card.appendChild(moduleHint(
        "Piper est inclus dans le bundle offline — aucune clé requise pour la synthèse vocale locale.",
      ));
    }
    card.appendChild(checkbox("Activer le pipeline vocal LiveKit", "voice_enabled"));
    if (form.voice_enabled) {
      card.appendChild(checkbox("Utiliser LiveKit Cloud (sinon serveur local)", "livekit_cloud"));
      card.appendChild(secretField("Clé Deepgram (STT)", "deepgram_api_key"));
      card.appendChild(moduleHint(
        "Deepgram : console.deepgram.com → API Keys → DEEPGRAM_API_KEY dans .env.",
      ));
      if (form.livekit_cloud) {
        card.appendChild(field("LiveKit URL", "livekit_url", { placeholder: "wss://…" }));
        card.appendChild(secretField("LiveKit API Key", "livekit_api_key"));
        card.appendChild(secretField("LiveKit API Secret", "livekit_api_secret"));
        card.appendChild(moduleHint(
          "LiveKit Cloud : livekit.io → ton projet → Settings → URL wss://, API Key et Secret dans .env.",
        ));
      } else {
        card.appendChild(moduleHint(
          "Serveur local : inclus dans le bundle Windows. Lance .\\jarvis.ps1 run — LiveKit démarre sur ws://localhost:7880.",
        ));
      }
    } else {
      card.appendChild(moduleHint(
        "Chat texte fonctionne sans voix. Pour activer plus tard : DEEPGRAM_API_KEY + .\\jarvis.ps1 run.",
      ));
    }
    card.appendChild(checkbox("Reconnaissance faciale (extra vision)", "face_recognition_enabled"));
    if (form.face_recognition_enabled) {
      card.appendChild(moduleHint(
        "Windows : uv sync --extra vision (Visual Studio Build Tools, workload C++). .env : FACE_RECOGNITION_ENABLED=true.",
      ));
    } else {
      card.appendChild(moduleHint(
        "Option avancée. Photo de référence dans vision_data/faces/reference.jpg (étape Identité).",
      ));
    }
    return card;
  }

  function renderFinish() {
    const card = el("div", { class: "setup-card setup-done" });
    card.appendChild(el("div", { class: "setup-done-badge", text: "✓" }));
    card.appendChild(el("h2", { text: "Configuration terminée" }));
    card.appendChild(el("p", {
      text: "Jarvis est prêt. Lance le serveur principal depuis le terminal, puis ouvre l'interface.",
    }));
    if (doneUrl) {
      const link = el("a", { class: "setup-done-url", href: doneUrl, text: doneUrl });
      link.target = "_blank";
      card.appendChild(link);
    }
    card.appendChild(el("p", {
      class: "setup-done-cmd",
      text: "Windows : .\\jarvis.ps1 run     ·     Linux/macOS : jarvis run",
    }));
    card.appendChild(el("p", {
      class: "setup-lead",
      text: "Utilise « Retour » pour revoir ou modifier une étape.",
    }));
    return card;
  }

  let cachedStatus = null;
  let prereqPollTimer = null;

  function stopPrereqPoll() {
    if (prereqPollTimer) {
      clearInterval(prereqPollTimer);
      prereqPollTimer = null;
    }
  }

  function startPrereqPoll() {
    if (prereqPollTimer) return;
    prereqPollTimer = setInterval(() => {
      if (step !== 0 || bundleDownloading) return;
      refreshPrerequisites();
    }, 3000);
  }

  async function loadStatus() {
    try {
      cachedStatus = await J.api.get("/api/setup/status");
      await J.api.post("/api/setup/bootstrap", {});
      cachedStatus = await J.api.get("/api/setup/status");
      await syncBundleDownloadState();
      secretsSet = cachedStatus.secrets_set || {};
      const cfg = cachedStatus.config || {};
      if (cachedStatus.user_firstname) form.user_firstname = cachedStatus.user_firstname;
      if (cachedStatus.api_backend) form.api_backend = cachedStatus.api_backend;
      if (cfg.proactive_city) form.proactive_city = cfg.proactive_city;
      if (cfg.proactive_lat) form.proactive_lat = cfg.proactive_lat;
      if (cfg.proactive_lon) form.proactive_lon = cfg.proactive_lon;
      if (cfg.ollama_model) form.ollama_model = cfg.ollama_model;
      if (cfg.ollama_base_url) form.ollama_base_url = cfg.ollama_base_url;
      if (cfg.elevenlabs_voice_id) form.elevenlabs_voice_id = cfg.elevenlabs_voice_id;
      if (cfg.livekit_url) form.livekit_url = cfg.livekit_url;
      form.elevenlabs_enabled = !!cfg.elevenlabs_enabled;
      form.tts_provider = cfg.elevenlabs_enabled ? "elevenlabs" : "piper";
      form.voice_enabled = !!cfg.voice_enabled;
      form.livekit_cloud = !!cfg.livekit_cloud;
      form.aisstream_enabled = !!cfg.aisstream_enabled;
      form.face_recognition_enabled = !!cfg.face_recognition_enabled;
      if (cachedStatus.complete && step < STEPS.length - 1) {
        doneUrl = "http://127.0.0.1:" + (cachedStatus.port || 8000) + "/";
        step = STEPS.length - 1;
      }
    } catch (_) {
      cachedStatus = { prerequisites: {} };
    }
  }

  function render() {
    renderIndicator();
    root.innerHTML = "";
    const current = STEPS[step];
    let body;
    if (current.id === "welcome") body = renderWelcome(cachedStatus || {});
    else if (current.id === "identity") body = renderIdentity();
    else if (current.id === "llm") body = renderLlm();
    else if (current.id === "modules") body = renderModules();
    else body = renderFinish();
    root.appendChild(body);

    // Retour disponible partout sauf à la première étape, y compris depuis
    // l'écran final, pour revoir/modifier la configuration.
    btnBack.hidden = step === 0;
    btnNext.textContent =
      step === STEPS.length - 2 ? "Terminer" : step === STEPS.length - 1 ? "Fermer" : "Continuer";
    if (step === 0) {
      btnNext.disabled = !canLeaveWelcome();
      btnNext.title = canLeaveWelcome()
        ? ""
        : "Installe ou place le bundle offline (bundle/manifest.json + .venv) avant de continuer.";
      startPrereqPoll();
    } else {
      stopPrereqPoll();
      btnNext.disabled = false;
      btnNext.title = "";
    }
  }

  function validateBeforeSubmit() {
    if (!form.user_firstname.trim()) {
      return "Prénom requis — retourne à l'étape Identité.";
    }
    if (form.elevenlabs_enabled) {
      const hasKey = form.elevenlabs_api_key.trim() || secretsSet.elevenlabs_api_key;
      if (!hasKey) return "Clé ElevenLabs requise.";
      const hasVoice = form.elevenlabs_voice_id.trim()
        || (cachedStatus && cachedStatus.config && cachedStatus.config.elevenlabs_voice_id);
      if (!hasVoice) return "Voice ID ElevenLabs requis (elevenlabs.io → Voices).";
    }
    if (form.voice_enabled) {
      const hasDeepgram = form.deepgram_api_key.trim() || secretsSet.deepgram_api_key;
      if (!hasDeepgram) return "Clé Deepgram requise pour le pipeline vocal.";
      if (form.livekit_cloud) {
        const hasLkUrl = form.livekit_url.trim();
        const hasLkKey = form.livekit_api_key.trim() || secretsSet.livekit_api_key;
        const hasLkSecret = form.livekit_api_secret.trim() || secretsSet.livekit_api_secret;
        if (!hasLkUrl || !hasLkKey || !hasLkSecret) {
          return "URL et clés LiveKit Cloud requises.";
        }
      }
    }
    return null;
  }

  async function postSetupComplete(payload) {
    const r = await fetch((J.api.base || "") + "/api/setup/complete", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      let msg = "Échec configuration";
      try {
        const data = await r.json();
        if (typeof data.detail === "string") msg = data.detail;
        else if (Array.isArray(data.detail) && data.detail[0] && data.detail[0].msg) {
          msg = data.detail[0].msg;
        }
      } catch (_) {}
      throw new Error(msg);
    }
    return r.json();
  }

  async function submit() {
    const validationError = validateBeforeSubmit();
    if (validationError) {
      J.notify({ kind: "err", text: validationError });
      return;
    }
    btnNext.disabled = true;
    btnNext.textContent = "Enregistrement...";
    try {
      const payload = {
        user_firstname: form.user_firstname,
        api_backend: form.api_backend,
        anthropic_api_key: form.anthropic_api_key,
        openai_api_key: form.openai_api_key,
        mistral_api_key: form.mistral_api_key,
        gemini_api_key: form.gemini_api_key,
        ollama_model: form.ollama_model,
        ollama_base_url: form.ollama_base_url,
        proactive_city: form.proactive_city,
        proactive_lat: form.proactive_lat,
        proactive_lon: form.proactive_lon,
        tts_provider: form.tts_provider,
        elevenlabs_api_key: form.elevenlabs_api_key,
        elevenlabs_voice_id: form.elevenlabs_voice_id,
        voice_enabled: form.voice_enabled,
        livekit_cloud: form.livekit_cloud,
        livekit_url: form.livekit_url,
        livekit_api_key: form.livekit_api_key,
        livekit_api_secret: form.livekit_api_secret,
        deepgram_api_key: form.deepgram_api_key,
        aisstream_key: form.aisstream_key,
        face_recognition_enabled: form.face_recognition_enabled,
      };
      const resp = await postSetupComplete(payload);
      doneUrl = resp.next;
      step = STEPS.length - 1;
      render();
    } catch (err) {
      J.notify({ kind: "err", text: err.message || "Échec configuration" });
      btnNext.textContent = "Terminer";
    } finally {
      btnNext.disabled = false;
    }
  }

  btnBack.addEventListener("click", () => {
    if (step > 0) {
      step -= 1;
      render();
    }
  });

  btnNext.addEventListener("click", async () => {
    if (step === STEPS.length - 1) {
      window.close();
      return;
    }
    if (step === 0 && !canLeaveWelcome()) {
      J.notify({ kind: "err", text: "Bundle offline requis avant de continuer." });
      return;
    }
    if (step === 1 && !form.user_firstname.trim()) {
      J.notify({ kind: "err", text: "Prénom requis." });
      return;
    }
    if (step === STEPS.length - 2) {
      await submit();
      return;
    }
    step += 1;
    render();
  });

  // Ferme tout dropdown custom ouvert quand on clique ailleurs.
  document.addEventListener("click", () => {
    document.querySelectorAll(".setup-select.open").forEach((s) => s.classList.remove("open"));
  });

  loadStatus().then(render);
})();
