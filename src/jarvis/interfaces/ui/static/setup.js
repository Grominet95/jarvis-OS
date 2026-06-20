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

  function statusRow(label, ok, detail) {
    const cls = ok ? "setup-status-ok" : "setup-status-warn";
    const row = el("div", { class: "setup-status-row" });
    row.appendChild(el("span", { text: label }));
    row.appendChild(el("span", { class: cls, text: detail }));
    return row;
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
      "Cet assistant configure ton instance locale. Avec un bundle offline, aucun téléchargement supplémentaire n'est nécessaire.",
    );
    const list = el("div", { class: "setup-status-list" });
    const prereq = status.prerequisites || {};
    list.appendChild(statusRow("Bundle offline", prereq.bundle, prereq.bundle ? "prêt" : "absent"));
    list.appendChild(statusRow("Python", prereq.python, prereq.python ? "prêt" : "manquant"));
    list.appendChild(statusRow("Modèle YOLO", prereq.yolo_model, prereq.yolo_model ? "prêt" : "à copier"));
    list.appendChild(statusRow("Modèle Piper", prereq.piper_model, prereq.piper_model ? "prêt" : "à copier"));
    list.appendChild(statusRow("LiveKit local", prereq.livekit_binary, prereq.livekit_binary ? "prêt" : "optionnel"));
    card.appendChild(list);
    if (!prereq.offline_ready) {
      card.appendChild(el("p", {
        class: "setup-lead",
        text: "Sans bundle, lance scripts/release/build_bundle une fois avec réseau, ou télécharge une release pré-packagée.",
      }));
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
    cardHeader(card, "Modules optionnels", "Active uniquement ce dont tu as besoin. Tout reste modifiable plus tard dans les réglages.");
    card.appendChild(checkbox("Utiliser ElevenLabs (sinon Piper local)", "elevenlabs_enabled"));
    if (form.elevenlabs_enabled) {
      form.tts_provider = "elevenlabs";
      card.appendChild(secretField("Clé ElevenLabs", "elevenlabs_api_key"));
    } else {
      form.tts_provider = "piper";
    }
    card.appendChild(checkbox("Activer le pipeline vocal LiveKit", "voice_enabled"));
    if (form.voice_enabled) {
      card.appendChild(checkbox("Utiliser LiveKit Cloud (sinon serveur local)", "livekit_cloud"));
      card.appendChild(secretField("Clé Deepgram (STT)", "deepgram_api_key"));
      if (form.livekit_cloud) {
        card.appendChild(field("LiveKit URL", "livekit_url", { placeholder: "wss://..." }));
        card.appendChild(secretField("LiveKit API Key", "livekit_api_key"));
        card.appendChild(secretField("LiveKit API Secret", "livekit_api_secret"));
      }
    }
    card.appendChild(checkbox("Reconnaissance faciale (extra vision installé)", "face_recognition_enabled"));
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

  async function loadStatus() {
    try {
      cachedStatus = await J.api.get("/api/setup/status");
      await J.api.post("/api/setup/bootstrap", {});
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
  }

  async function submit() {
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
      const resp = await J.api.post("/api/setup/complete", payload);
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
