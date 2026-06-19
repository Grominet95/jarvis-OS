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
    { id: "identity", title: "Identite" },
    { id: "llm", title: "LLM" },
    { id: "location", title: "Localisation" },
    { id: "modules", title: "Modules" },
    { id: "finish", title: "Terminer" },
  ];

  let step = 0;
  let doneUrl = "";

  const form = {
    user_firstname: "",
    api_backend: "anthropic",
    anthropic_api_key: "",
    openai_api_key: "",
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

  function renderWelcome(status) {
    const card = el("div", { class: "setup-card" });
    card.appendChild(el("h1", { class: "setup-title", text: "Configuration Jarvis" }));
    card.appendChild(el("p", {
      class: "setup-lead",
      text: "Cet assistant configure ton instance locale. Avec un bundle offline, aucun telechargement supplementaire n'est necessaire.",
    }));
    const list = el("div", { class: "setup-status-list" });
    const prereq = status.prerequisites || {};
    list.appendChild(statusRow("Bundle offline", prereq.bundle, prereq.bundle ? "pret" : "absent"));
    list.appendChild(statusRow("Python", prereq.python, prereq.python ? "pret" : "manquant"));
    list.appendChild(statusRow("Modele YOLO", prereq.yolo_model, prereq.yolo_model ? "pret" : "a copier"));
    list.appendChild(statusRow("Modele Piper", prereq.piper_model, prereq.piper_model ? "pret" : "a copier"));
    list.appendChild(statusRow("LiveKit local", prereq.livekit_binary, prereq.livekit_binary ? "pret" : "optionnel"));
    card.appendChild(list);
    if (!prereq.offline_ready) {
      card.appendChild(el("p", {
        class: "setup-lead",
        text: "Sans bundle, lance scripts/release/build_bundle une fois avec reseau, ou telecharge une release pre-packaged.",
      }));
    }
    return card;
  }

  function renderIdentity() {
    const card = el("div", { class: "setup-card" });
    card.appendChild(el("h1", { class: "setup-title", text: "Identite" }));
    card.appendChild(el("p", { class: "setup-lead", text: "Ton prenom est affiche lors du scan biométrique et dans l'interface." }));
    card.appendChild(field("Prenom", "user_firstname", { placeholder: "Maxime" }));
    const face = el("div", { class: "setup-field" });
    face.appendChild(el("label", { text: "Photo de reference (optionnel)" }));
    const file = el("input", { type: "file", accept: ".jpg,.jpeg" });
    file.addEventListener("change", async () => {
      if (!file.files || !file.files[0]) return;
      const body = new FormData();
      body.append("file", file.files[0]);
      try {
        await fetch("/api/setup/upload-face", { method: "POST", body });
        J.notify({ kind: "ok", text: "Photo enregistree dans vision_data/faces/" });
      } catch (_) {
        J.notify({ kind: "err", text: "Echec upload photo" });
      }
    });
    face.appendChild(file);
    card.appendChild(face);
    return card;
  }

  function renderLlm() {
    const card = el("div", { class: "setup-card" });
    card.appendChild(el("h1", { class: "setup-title", text: "LLM principal" }));
    card.appendChild(el("p", { class: "setup-lead", text: "Choisis le fournisseur utilise pour le chat et les missions." }));
    const backend = el("div", { class: "setup-field" });
    backend.appendChild(el("label", { text: "Backend" }));
    const select = el("select");
    ["anthropic", "openai"].forEach((v) => {
      const opt = el("option", { value: v, text: v });
      if (form.api_backend === v) opt.selected = true;
      select.appendChild(opt);
    });
    select.addEventListener("change", () => {
      form.api_backend = select.value;
      render();
    });
    backend.appendChild(select);
    card.appendChild(backend);
    if (form.api_backend === "openai") {
      card.appendChild(field("Cle API OpenAI", "openai_api_key", { type: "password" }));
    } else {
      card.appendChild(field("Cle API Anthropic", "anthropic_api_key", { type: "password" }));
    }
    return card;
  }

  function renderLocation() {
    const card = el("div", { class: "setup-card" });
    card.appendChild(el("h1", { class: "setup-title", text: "Localisation" }));
    card.appendChild(el("p", { class: "setup-lead", text: "Utilisee par le moteur proactif (meteo, briefing)." }));
    card.appendChild(field("Ville", "proactive_city"));
    const grid = el("div", { class: "setup-grid-2" });
    grid.appendChild(field("Latitude", "proactive_lat"));
    grid.appendChild(field("Longitude", "proactive_lon"));
    card.appendChild(grid);
    return card;
  }

  function renderModules() {
    const card = el("div", { class: "setup-card" });
    card.appendChild(el("h1", { class: "setup-title", text: "Modules optionnels" }));
    card.appendChild(checkbox("Utiliser ElevenLabs (sinon Piper local)", "elevenlabs_enabled"));
    if (form.elevenlabs_enabled) {
      form.tts_provider = "elevenlabs";
      card.appendChild(field("Cle ElevenLabs", "elevenlabs_api_key", { type: "password" }));
      card.appendChild(field("Voice ID", "elevenlabs_voice_id"));
    } else {
      form.tts_provider = "piper";
    }
    card.appendChild(checkbox("Activer le pipeline vocal LiveKit", "voice_enabled"));
    if (form.voice_enabled) {
      card.appendChild(checkbox("Utiliser LiveKit Cloud (sinon serveur local)", "livekit_cloud"));
      card.appendChild(field("Cle Deepgram (STT)", "deepgram_api_key", { type: "password" }));
      if (form.livekit_cloud) {
        card.appendChild(field("LiveKit URL", "livekit_url", { placeholder: "wss://..." }));
        card.appendChild(field("LiveKit API Key", "livekit_api_key", { type: "password" }));
        card.appendChild(field("LiveKit API Secret", "livekit_api_secret", { type: "password" }));
      }
    }
    card.appendChild(checkbox("Configurer AISstream (globe maritime)", "aisstream_enabled"));
    if (form.aisstream_enabled) {
      card.appendChild(field("Cle AISstream", "aisstream_key", { type: "password" }));
    }
    card.appendChild(checkbox("Reconnaissance faciale (extra vision installe)", "face_recognition_enabled"));
    return card;
  }

  function renderFinish() {
    const card = el("div", { class: "setup-card setup-done" });
    card.appendChild(el("h2", { text: "Configuration terminee" }));
    card.appendChild(el("p", { text: "Jarvis est pret. Lance le serveur principal depuis le terminal." }));
    if (doneUrl) {
      const link = el("a", { href: doneUrl, text: doneUrl });
      link.target = "_blank";
      card.appendChild(link);
    }
    card.appendChild(el("p", {
      text: "Commande Windows : .\\jarvis.ps1 run — Linux/macOS : jarvis run",
    }));
    return card;
  }

  let cachedStatus = null;

  async function loadStatus() {
    try {
      cachedStatus = await J.api.get("/api/setup/status");
      await J.api.post("/api/setup/bootstrap", {});
      if (cachedStatus.user_firstname) form.user_firstname = cachedStatus.user_firstname;
      if (cachedStatus.api_backend) form.api_backend = cachedStatus.api_backend;
      if (cachedStatus.complete && step < STEPS.length - 1) {
        doneUrl = "http://127.0.0.1:" + (cachedStatus.port || 8000) + "/admin";
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
    else if (current.id === "location") body = renderLocation();
    else if (current.id === "modules") body = renderModules();
    else body = renderFinish();
    root.appendChild(body);

    btnBack.hidden = step === 0 || step === STEPS.length - 1;
    btnNext.textContent = step === STEPS.length - 2 ? "Terminer" : step === STEPS.length - 1 ? "Fermer" : "Continuer";
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
      J.notify({ kind: "err", text: err.message || "Echec configuration" });
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

  loadStatus().then(render);
})();
