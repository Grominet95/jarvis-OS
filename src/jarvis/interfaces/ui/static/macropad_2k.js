/* macropad_2k.js — Macropad 2 touches Le Labo, integrated inside Jarvis V4.
 * Vanilla JS port of the original React/Tauri studio.
 * Uses Jarvis design system (mountSidebar, mountTopbar) + macropad_2k.css.
 */
(function () {
  "use strict";
  const J = window.Jarvis;
  const el = J.el;
  const isEmbedded = new URLSearchParams(window.location.search).get("embedded") === "1";

  /* ─────────────── Constants ─────────────── */
  const KP2K_MM = {
    plateW: 64.408,
    plateH: 56.886,
    cornerR: 6,
    keyW: 15.625,
    keyH: 14.716,
    k2: { l: 12.571, t: 27.18 },
    k1: { l: 36.051, t: 27.081 },
  };
  const EDGE_LED_COUNT = 25;

  const EFFECT_LABELS = {
    static: "Statique",
    breath: "Respiration",
    rainbow: "Arc-en-ciel",
    reactive: "Réactif",
    wave: "Vague",
    theater: "Chenillard",
    sparkle: "Scintillement",
  };
  const TRIGGER_LABELS = {
    press: "Appui",
    release: "Relâchement",
    both: "Appui + relâchement",
    hold: "Maintien",
  };
  const EFFECTS = ["static", "breath", "rainbow", "reactive", "wave", "theater", "sparkle"];
  const TRIGGERS = ["press", "release", "both", "hold"];
  const MODIFIER_BUTTONS = [
    { id: "ctrl", label: "Ctrl" },
    { id: "shift", label: "Maj" },
    { id: "alt", label: "Alt" },
    { id: "gui", label: "Win" },
  ];
  const KEYPAD_PRODUCT_OPTIONS = [
    {
      id: "keypad_2k_v1",
      label: "Keypad 2 touches",
      hint: "Profil matériel actuel (firmware CH552). D'autres références viendront s'ajouter.",
    },
  ];
  const HID_KEY_OPTIONS = (function () {
    const arr = [];
    for (const c of "ABCDEFGHIJKLMNOPQRSTUVWXYZ") arr.push({ code: "Key" + c, label: c });
    for (const d of "1234567890") arr.push({ code: "Digit" + d, label: d });
    [
      ["Enter", "Enter"],
      ["Escape", "Escape"],
      ["Backspace", "Backspace"],
      ["Tab", "Tab"],
      ["Space", "Space"],
      ["Minus", "-"],
      ["Equal", "="],
      ["BracketLeft", "["],
      ["BracketRight", "]"],
      ["Backslash", "\\"],
      ["Semicolon", ";"],
      ["Quote", "'"],
      ["Backquote", "`"],
      ["Comma", ","],
      ["Period", "."],
      ["Slash", "/"],
    ].forEach(([code, label]) => arr.push({ code, label }));
    for (let i = 1; i <= 24; i++) arr.push({ code: "F" + i, label: "F" + i });
    return arr;
  })();
  const MACRO_PRESETS = [
    { id: "win-notepad",       label: "Windows — Ouvrir Notepad",    modifiers: ["gui"], hidCode: "KeyR",  macroText: "notepad",    macroDelayMs: 220, macroTapEnter: true },
    { id: "win-cmd",           label: "Windows — Ouvrir CMD",        modifiers: ["gui"], hidCode: "KeyR",  macroText: "cmd",        macroDelayMs: 220, macroTapEnter: true },
    { id: "win-powershell",    label: "Windows — Ouvrir PowerShell", modifiers: ["gui"], hidCode: "KeyR",  macroText: "powershell", macroDelayMs: 220, macroTapEnter: true },
    { id: "win-explorer",      label: "Windows — Ouvrir Explorateur",modifiers: ["gui"], hidCode: "KeyE",  macroText: "",           macroDelayMs: 120, macroTapEnter: false },
    { id: "mac-spotlight-ter", label: "macOS — Spotlight Terminal",  modifiers: ["gui"], hidCode: "Space", macroText: "Terminal",   macroDelayMs: 260, macroTapEnter: true },
    { id: "mac-spotlight-saf", label: "macOS — Spotlight Safari",    modifiers: ["gui"], hidCode: "Space", macroText: "Safari",     macroDelayMs: 260, macroTapEnter: true },
    { id: "linux-terminal",    label: "Linux — Terminal Ctrl+Alt+T", modifiers: ["ctrl", "alt"], hidCode: "KeyT", macroText: "",      macroDelayMs: 100, macroTapEnter: false },
  ];

  const APP_VERSION = "0.1.0";

  /* ─────────────── Color helpers ─────────────── */
  function clamp01(v) { return Math.max(0, Math.min(1, v)); }
  function smoothstep01(t) { const x = clamp01(t); return x * x * (3 - 2 * x); }
  function triangle01(p) { const x = ((p % 1) + 1) % 1; return x < 0.5 ? x * 2 : 2 - x * 2; }
  function hexToRgb(hex) {
    const m = String(hex || "").trim().replace("#", "");
    const full = m.length === 3 ? m.split("").map((c) => c + c).join("") : m;
    const n = Number.parseInt(full, 16);
    if (!Number.isFinite(n)) return { r: 128, g: 128, b: 128 };
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
  }
  function rgbToHex(c) {
    const toHex = (v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0");
    return `#${toHex(c.r)}${toHex(c.g)}${toHex(c.b)}`;
  }
  function mixHex(a, b, t) {
    const x = hexToRgb(a), y = hexToRgb(b), k = clamp01(t);
    return rgbToHex({ r: x.r + (y.r - x.r) * k, g: x.g + (y.g - x.g) * k, b: x.b + (y.b - x.b) * k });
  }
  function scaleHex(hex, factor) {
    const c = hexToRgb(hex);
    return rgbToHex({ r: c.r * factor, g: c.g * factor, b: c.b * factor });
  }
  function hueToRgb(p, q, t) {
    let v = t;
    if (v < 0) v += 1;
    if (v > 1) v -= 1;
    if (v < 1 / 6) return p + (q - p) * 6 * v;
    if (v < 1 / 2) return q;
    if (v < 2 / 3) return p + (q - p) * (2 / 3 - v) * 6;
    return p;
  }
  function hslToHex(h, s, l) {
    const hue = (((h % 360) + 360) % 360) / 360;
    const sat = clamp01(s), lig = clamp01(l);
    if (sat === 0) { const v = lig * 255; return rgbToHex({ r: v, g: v, b: v }); }
    const q = lig < 0.5 ? lig * (1 + sat) : lig + sat - lig * sat;
    const p = 2 * lig - q;
    return rgbToHex({
      r: hueToRgb(p, q, hue + 1 / 3) * 255,
      g: hueToRgb(p, q, hue) * 255,
      b: hueToRgb(p, q, hue - 1 / 3) * 255,
    });
  }
  function phaseNoise(seed) { const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); }

  /* ─────────────── Geometry helpers (rounded rect perimeter) ─────────────── */
  function roundedRectPerimeterLength(w, h, r) {
    return 2 * (w - 2 * r) + 2 * (h - 2 * r) + 2 * Math.PI * r;
  }

  /* ─────────────── Profile defaults / merge ─────────────── */
  function defaultProfile(workspace) {
    return {
      version: 1,
      workspaceRoot: workspace || "",
      device: { keypadProductId: "macropad_2k_le_labo", productName: "Macropad 2 touches Le Labo" },
      keysOptions: { debounceMs: 5, layoutFrAzerty: true, softwareRapidTrigger: false, rapidTriggerResetMs: 2 },
      keys: {
        k1RightP1: { modifiers: [], hidCode: "KeyA", label: "A", mode: "hold", macroText: "", macroDelayMs: 180, macroTapEnter: true },
        k2LeftP2: { modifiers: [], hidCode: "KeyB", label: "B", mode: "hold", macroText: "", macroDelayMs: 180, macroTapEnter: true },
      },
      hardware: { keyLedsGpio: "P3.4", keyLedOrder: [1, 2], edgeLedsGpio: "P3.0", edgeLedCount: EDGE_LED_COUNT, pcbNote: "Visual left is P2 (K2), visual right is P1 (K1)" },
      lighting: {
        effect: "static",
        keyBrightness: 0.75,
        edgeBrightness: 0.75,
        keySpeed: 0.6,
        edgeSpeed: 0.6,
        trigger: "press",
        staticKeyColor: "#30ad6c",
        staticEdgeColor: "#30ad6c",
        keyPixels: ["#00f0ff", "#ff2d95"],
        edgePixels: Array.from({ length: EDGE_LED_COUNT }, () => "#8b5cf6"),
      },
    };
  }
  function defaultBundle(workspace) {
    return {
      bundleVersion: 2,
      activeProfileId: "default",
      profiles: [{ id: "default", name: "Principal", data: defaultProfile(workspace) }],
    };
  }
  function newSlotId() { return "p_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8); }

  /* ─────────────── State ─────────────── */
  const state = {
    workspace: "",
    workspaceValid: false,
    vendoredWorkspace: "",
    bundle: defaultBundle(""),
    status: null,
    tab: "keys",
    selectedKey: null,
    lightingSubtab: "effect",
    fwLog: "",
    fwBusy: null,
    saveError: null,
    saving: false,
    profileMenuOpen: false,
    installedApps: [],
    appsLoading: false,
    arduinoCli: { installed: false, path: null, vendored: "" },
    arduinoBusy: false,
  };

  function activeProfile() {
    const b = state.bundle;
    const slot = b.profiles.find((p) => p.id === b.activeProfileId);
    return (slot && slot.data) || (b.profiles[0] && b.profiles[0].data) || defaultProfile(state.workspace);
  }
  function setProfile(next) {
    const id = state.bundle.activeProfileId;
    const idx = state.bundle.profiles.findIndex((p) => p.id === id);
    if (idx < 0) return;
    const prev = state.bundle.profiles[idx].data;
    const data = typeof next === "function" ? next(prev) : next;
    state.bundle.profiles[idx] = Object.assign({}, state.bundle.profiles[idx], { data: Object.assign({}, data, { workspaceRoot: state.workspace }) });
    render();
  }
  function setLighting(patch) {
    setProfile((p) => Object.assign({}, p, { lighting: Object.assign({}, p.lighting, patch) }));
  }
  function setKeysOptions(patch) {
    setProfile((p) => Object.assign({}, p, { keysOptions: Object.assign({}, p.keysOptions, patch) }));
  }

  /* ─────────────── API ─────────────── */
  const api = {
    async status() { return await J.api.get("/api/macropad/status"); },
    async getWorkspace() { return await J.api.get("/api/macropad/workspace"); },
    async setWorkspace(path) { return await J.api.post("/api/macropad/workspace", { path }); },
    async validateWorkspace(path) {
      const u = "/api/macropad/workspace/validate?path=" + encodeURIComponent(path);
      return await J.api.get(u);
    },
    async getProfile(workspace) {
      const u = "/api/macropad/profile" + (workspace ? "?workspace=" + encodeURIComponent(workspace) : "");
      return await J.api.get(u);
    },
    async putProfile(bundle, workspace) {
      const r = await fetch("/api/macropad/profile", {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bundle, workspace }),
      });
      if (!r.ok) throw new Error("PUT /api/macropad/profile " + r.status);
      return r.json();
    },
    async compile(workspace, blinkHz) {
      return await J.api.post("/api/macropad/compile", { workspace, blinkHz: blinkHz == null ? null : blinkHz });
    },
    async upload(workspace, opts) {
      return await J.api.post("/api/macropad/upload", Object.assign({ workspace, preferPython: false, attempts: 1 }, opts || {}));
    },
    async installedApps() { return await J.api.get("/api/macropad/installed-apps"); },
    async createLauncher(appId, appName, slot) {
      return await J.api.post("/api/macropad/launcher", { appId, appName, slot });
    },
    async openDeviceManager() { return await J.api.post("/api/macropad/open-device-manager", {}); },
    async arduinoCliStatus() { return await J.api.get("/api/macropad/arduino-cli"); },
    async arduinoCliInstall() { return await J.api.post("/api/macropad/arduino-cli/install", {}); },
  };

  /* ─────────────── SVG icons (lucide-equivalents, inlined) ─────────────── */
  function svgIcon(d, size) {
    const s = size || 14;
    const w = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    w.setAttribute("width", s);
    w.setAttribute("height", s);
    w.setAttribute("viewBox", "0 0 24 24");
    w.setAttribute("fill", "none");
    w.setAttribute("stroke", "currentColor");
    w.setAttribute("stroke-width", "1.5");
    w.setAttribute("stroke-linecap", "round");
    w.setAttribute("stroke-linejoin", "round");
    const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
    p.setAttribute("d", d);
    w.appendChild(p);
    return w;
  }
  const ICONS = {
    keyboard: "M2 6h20v12H2zM6 10h0M10 10h0M14 10h0M18 10h0M6 14h0M10 14h0M14 14h0M18 14h0M8 18h8",
    lightbulb: "M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7c1 1 1 1.5 1 3.3h6c0-1.8 0-2.3 1-3.3A7 7 0 0 0 12 2z",
    layers: "M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5",
    usb: "M12 17V7M9 7h6l-3-5-3 5zM18 11l3 3-3 3M6 11l-3 3 3 3M6 14h12",
    cpu: "M9 3v2M15 3v2M9 19v2M15 19v2M3 9h2M3 15h2M19 9h2M19 15h2M5 5h14v14H5z",
    wrench: "M14.7 6.3a4 4 0 1 0-5.4 5.4L4 17v3h3l5.3-5.3a4 4 0 1 0 2.4-8.4z",
    info: "M12 8v4M12 16h0M12 22a10 10 0 1 1 0-20 10 10 0 0 1 0 20z",
    save: "M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2zM17 21v-8H7v8M7 3v5h8",
    folder: "M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z",
    plus: "M12 5v14M5 12h14",
    trash: "M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6",
    upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
    close: "M18 6L6 18M6 6l12 12",
    chevron: "M6 9l6 6 6-6",
  };

  /* ─────────────── KeypadPlate SVG component (vanilla port) ─────────────── */
  function buildKeypadPlateSvg(opts) {
    const u = KP2K_MM;
    const svgNS = "http://www.w3.org/2000/svg";
    const rid = "kp" + Math.random().toString(36).slice(2, 8);
    const s = (n) => Number(n).toFixed(3);

    const editingKey = opts.editingKey || null;
    const onKeyClick = opts.onKeyClick || null;
    const keyLedK1 = opts.keyLedK1 || "#222";
    const keyLedK2 = opts.keyLedK2 || "#222";
    const keyCapStyle = opts.keyCapStyle || "neutral";
    const edgePixels = (opts.edgePixels && opts.edgePixels.length === EDGE_LED_COUNT) ? opts.edgePixels : null;

    const k1Fill = keyCapStyle === "ledPreview" ? keyLedK1 : (editingKey === "k1" ? `url(#${rid}-k1-hi)` : `url(#${rid}-k1)`);
    const k2Fill = keyCapStyle === "ledPreview" ? keyLedK2 : (editingKey === "k2" ? `url(#${rid}-k2-hi)` : `url(#${rid}-k2)`);
    const k1Stroke = editingKey === "k1" ? "#78716c" : "#3f3f46";
    const k2Stroke = editingKey === "k2" ? "#64748b" : "#3f3f46";
    const k1Sw = editingKey === "k1" ? 0.24 : 0.17;
    const k2Sw = editingKey === "k2" ? 0.24 : 0.17;
    const k1Op = editingKey === "k1" ? 0.72 : 0.5;
    const k2Op = editingKey === "k2" ? 0.72 : 0.5;

    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", `0 0 ${s(u.plateW)} ${s(u.plateH)}`);
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");

    const defs = document.createElementNS(svgNS, "defs");
    const gradients = [
      ["plate", "#18181b", "#0f0f11"],
      ["k2", "#252a30", "#121418"],
      ["k2-hi", "#2c333c", "#161a1f"],
      ["k1", "#2a262c", "#121114"],
      ["k1-hi", "#322c34", "#18161a"],
    ];
    gradients.forEach(([n, a, b]) => {
      const g = document.createElementNS(svgNS, "linearGradient");
      g.setAttribute("id", `${rid}-${n}`);
      g.setAttribute("x1", "0"); g.setAttribute("y1", "0");
      g.setAttribute("x2", "0"); g.setAttribute("y2", "1");
      const s1 = document.createElementNS(svgNS, "stop");
      s1.setAttribute("offset", "0%"); s1.setAttribute("stop-color", a);
      const s2 = document.createElementNS(svgNS, "stop");
      s2.setAttribute("offset", "100%"); s2.setAttribute("stop-color", b);
      g.appendChild(s1); g.appendChild(s2);
      defs.appendChild(g);
    });
    const drop = document.createElementNS(svgNS, "filter");
    drop.setAttribute("id", `${rid}-drop`);
    drop.setAttribute("x", "-40%"); drop.setAttribute("y", "-40%");
    drop.setAttribute("width", "180%"); drop.setAttribute("height", "180%");
    const ds = document.createElementNS(svgNS, "feDropShadow");
    ds.setAttribute("dx", "0"); ds.setAttribute("dy", "0.45");
    ds.setAttribute("stdDeviation", "0.7");
    ds.setAttribute("flood-color", "#000000");
    ds.setAttribute("flood-opacity", "0.42");
    drop.appendChild(ds);
    defs.appendChild(drop);
    const blur = document.createElementNS(svgNS, "filter");
    blur.setAttribute("id", `${rid}-edge`);
    blur.setAttribute("x", "-20%"); blur.setAttribute("y", "-20%");
    blur.setAttribute("width", "140%"); blur.setAttribute("height", "140%");
    const fb = document.createElementNS(svgNS, "feGaussianBlur");
    fb.setAttribute("stdDeviation", "0.14");
    blur.appendChild(fb);
    defs.appendChild(blur);
    svg.appendChild(defs);

    const plate = document.createElementNS(svgNS, "rect");
    plate.setAttribute("x", "0"); plate.setAttribute("y", "0");
    plate.setAttribute("width", s(u.plateW)); plate.setAttribute("height", s(u.plateH));
    plate.setAttribute("rx", s(u.cornerR)); plate.setAttribute("ry", s(u.cornerR));
    plate.setAttribute("fill", `url(#${rid}-plate)`);
    plate.setAttribute("stroke", "#3f3f46");
    plate.setAttribute("stroke-opacity", "0.38");
    plate.setAttribute("stroke-width", "0.32");
    plate.setAttribute("stroke-linejoin", "round");
    svg.appendChild(plate);

    if (edgePixels) {
      const EDGE_SAMPLES = 220;
      const perimeter = roundedRectPerimeterLength(u.plateW, u.plateH, u.cornerR);
      const step = perimeter / EDGE_SAMPLES;
      const dash = step + 0.5;
      const topLeftOffset =
        (u.plateW - 2 * u.cornerR) +
        (Math.PI / 2) * u.cornerR +
        (u.plateH - 2 * u.cornerR) +
        (Math.PI / 2) * u.cornerR +
        (u.plateW - 2 * u.cornerR);
      const samples = [];
      for (let i = 0; i < EDGE_SAMPLES; i++) {
        const p = (i / EDGE_SAMPLES) * EDGE_LED_COUNT;
        const i0 = Math.floor(p) % EDGE_LED_COUNT;
        const i1 = (i0 + 1) % EDGE_LED_COUNT;
        samples.push(mixHex(edgePixels[i0], edgePixels[i1], p - Math.floor(p)));
      }
      const g = document.createElementNS(svgNS, "g");
      g.setAttribute("pointer-events", "none");
      g.setAttribute("filter", `url(#${rid}-edge)`);
      const guide = document.createElementNS(svgNS, "rect");
      guide.setAttribute("x", "0.22"); guide.setAttribute("y", "0.22");
      guide.setAttribute("width", s(u.plateW - 0.44)); guide.setAttribute("height", s(u.plateH - 0.44));
      guide.setAttribute("rx", s(u.cornerR - 0.22)); guide.setAttribute("ry", s(u.cornerR - 0.22));
      guide.setAttribute("fill", "none");
      guide.setAttribute("stroke", "rgba(255,255,255,0.06)");
      guide.setAttribute("stroke-width", "0.2");
      g.appendChild(guide);
      for (let i = 0; i < samples.length; i++) {
        const r = document.createElementNS(svgNS, "rect");
        r.setAttribute("x", "0.22"); r.setAttribute("y", "0.22");
        r.setAttribute("width", s(u.plateW - 0.44)); r.setAttribute("height", s(u.plateH - 0.44));
        r.setAttribute("rx", s(u.cornerR - 0.22)); r.setAttribute("ry", s(u.cornerR - 0.22));
        r.setAttribute("fill", "none");
        r.setAttribute("stroke", samples[i]);
        r.setAttribute("stroke-opacity", "0.95");
        r.setAttribute("stroke-width", "0.62");
        r.setAttribute("stroke-linecap", "round");
        r.setAttribute("stroke-linejoin", "round");
        r.setAttribute("stroke-dasharray", `${dash} ${perimeter - dash}`);
        r.setAttribute("stroke-dashoffset", String(-(topLeftOffset + i * step)));
        g.appendChild(r);
      }
      svg.appendChild(g);
    }

    function makeKey(slot, ledFill, stroke, sw, op, color) {
      const k = u[slot];
      const g = document.createElementNS(svgNS, "g");
      if (onKeyClick) g.style.cursor = "pointer";
      if (onKeyClick) g.addEventListener("click", (e) => { e.stopPropagation(); onKeyClick(slot); });
      const inner = document.createElementNS(svgNS, "g");
      if (keyCapStyle === "neutral") inner.setAttribute("filter", `url(#${rid}-drop)`);
      const rect = document.createElementNS(svgNS, "rect");
      rect.setAttribute("x", s(k.l)); rect.setAttribute("y", s(k.t));
      rect.setAttribute("width", s(u.keyW)); rect.setAttribute("height", s(u.keyH));
      rect.setAttribute("rx", "1.05"); rect.setAttribute("ry", "1.05");
      rect.setAttribute("fill", ledFill);
      rect.setAttribute("stroke", stroke);
      rect.setAttribute("stroke-opacity", String(op));
      rect.setAttribute("stroke-width", String(sw));
      rect.setAttribute("stroke-linejoin", "round");
      inner.appendChild(rect);
      g.appendChild(inner);
      const txt = document.createElementNS(svgNS, "text");
      txt.setAttribute("x", s(k.l + u.keyW / 2));
      txt.setAttribute("y", s(k.t + u.keyH / 2 + 1.6));
      txt.setAttribute("text-anchor", "middle");
      txt.setAttribute("font-size", "4.6");
      txt.setAttribute("font-weight", "550");
      txt.setAttribute("fill", color);
      txt.setAttribute("pointer-events", "none");
      txt.textContent = slot.toUpperCase();
      g.appendChild(txt);
      return g;
    }

    svg.appendChild(makeKey("k2", k2Fill, k2Stroke, k2Sw, k2Op, "#c4c9cf"));
    svg.appendChild(makeKey("k1", k1Fill, k1Stroke, k1Sw, k1Op, "#cbc4c8"));
    return svg;
  }

  /* ─────────────── Light preview computation ─────────────── */
  function computePreview(profile, timeSec) {
    const baseEdge = profile.lighting.edgePixels;
    const baseK1 = profile.lighting.keyPixels[0];
    const baseK2 = profile.lighting.keyPixels[1];
    const fx = profile.lighting.effect;
    const keyB = clamp01(profile.lighting.keyBrightness);
    const edgeB = clamp01(profile.lighting.edgeBrightness);
    const keyS = clamp01(profile.lighting.keySpeed);
    const edgeS = clamp01(profile.lighting.edgeSpeed);
    const keySpeedF = 0.55 + keyS * 3.9;
    const edgeSpeedF = 0.55 + edgeS * 3.9;
    const trigger = profile.lighting.trigger;
    const sKey = profile.lighting.staticKeyColor;
    const sEdge = profile.lighting.staticEdgeColor;

    if (fx === "static") {
      return {
        k1: scaleHex(sKey, keyB),
        k2: scaleHex(sKey, keyB),
        edge: Array.from({ length: baseEdge.length || EDGE_LED_COUNT }, () => scaleHex(sEdge, edgeB)),
      };
    }
    if (fx === "breath") {
      const keyAmp = 0.16 + 0.84 * smoothstep01(triangle01(timeSec * (0.52 + keyS * 1.75)));
      const edgeAmp = 0.16 + 0.84 * smoothstep01(triangle01(timeSec * (0.52 + edgeS * 1.75)));
      return {
        k1: scaleHex(baseK1, keyAmp * keyB),
        k2: scaleHex(baseK2, keyAmp * keyB),
        edge: baseEdge.map((c) => scaleHex(c, edgeAmp * edgeB)),
      };
    }
    if (fx === "rainbow") {
      const sk = (timeSec * (24 + keyS * 120)) % 360;
      const se = (timeSec * (24 + edgeS * 120)) % 360;
      return {
        k1: scaleHex(hslToHex((sk + 335) % 360, 0.82, 0.58), keyB),
        k2: scaleHex(hslToHex((sk + 205) % 360, 0.82, 0.58), keyB),
        edge: Array.from({ length: EDGE_LED_COUNT }, (_, i) => scaleHex(hslToHex((se + (i / EDGE_LED_COUNT) * 360) % 360, 0.88, 0.58), edgeB)),
      };
    }
    if (fx === "wave") {
      const edge = baseEdge.map((c, i) => scaleHex(c, (0.2 + 0.8 * (0.5 + 0.5 * Math.sin(timeSec * edgeSpeedF * 2.2 - i * 0.5))) * edgeB));
      const k1w = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(timeSec * keySpeedF * 2.8));
      const k2w = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(timeSec * keySpeedF * 2.8 + 1.3));
      return { k1: scaleHex(baseK1, k1w * keyB), k2: scaleHex(baseK2, k2w * keyB), edge };
    }
    if (fx === "theater") {
      const n = baseEdge.length || EDGE_LED_COUNT;
      const ph = timeSec * edgeSpeedF * Math.PI * 0.62;
      const edge = baseEdge.map((c, i) => scaleHex(c, (0.1 + 0.9 * (0.5 + 0.5 * Math.sin((i / n) * Math.PI * 2 + ph))) * edgeB));
      const kb = 0.24 + 0.76 * (0.5 + 0.5 * Math.sin(timeSec * keySpeedF * Math.PI * 1.35));
      return { k1: scaleHex(baseK1, kb * keyB), k2: scaleHex(baseK2, (1.05 - 0.55 * kb) * keyB), edge };
    }
    if (fx === "sparkle") {
      const edge = baseEdge.map((c, i) => {
        const n = phaseNoise((i + 1) * 19.37 + timeSec * edgeSpeedF * 2.35);
        const a = smoothstep01(n);
        return scaleHex(c, (0.12 + 0.88 * (a * a)) * edgeB);
      });
      const k1s = 0.25 + 0.75 * (0.5 + 0.5 * Math.sin(timeSec * keySpeedF * 5.6));
      const k2s = 0.25 + 0.75 * (0.5 + 0.5 * Math.sin(timeSec * keySpeedF * 6.2 + 1.4));
      return { k1: scaleHex(baseK1, k1s * keyB), k2: scaleHex(baseK2, k2s * keyB), edge };
    }
    const count = EDGE_LED_COUNT;
    const t = timeSec * edgeSpeedF * (trigger === "hold" ? 1.6 : 5.4);
    const pA = trigger === "release" ? (count - (t % count)) % count : t % count;
    const pB =
      trigger === "both" ? (pA + count / 2) % count :
      trigger === "hold" ? (pA + count / 3) % count :
      pA;
    const width = trigger === "hold" ? 16.5 : 10.2;
    const edge = baseEdge.map((c, i) => {
      const dA = Math.min(Math.abs(i - pA), count - Math.abs(i - pA));
      const dB = Math.min(Math.abs(i - pB), count - Math.abs(i - pB));
      const gA = Math.exp(-(dA * dA) / width);
      const gB = Math.exp(-(dB * dB) / width);
      const glow = (trigger === "press" || trigger === "release") ? gA : Math.max(gA, gB);
      return scaleHex(c, (0.12 + 0.9 * glow) * edgeB);
    });
    const kp = 0.3 + 0.7 * (0.5 + 0.5 * Math.sin(timeSec * keySpeedF * 6.8));
    return { k1: scaleHex(baseK1, kp * keyB), k2: scaleHex(baseK2, (1 - 0.45 * kp) * keyB), edge };
  }

  /* ─────────────── Render bricks ─────────────── */
  function btn(opts, children) {
    const cls = "kp-btn" + (opts.variant ? " kp-btn--" + opts.variant : "") + (opts.size ? " kp-btn--" + opts.size : "");
    const node = el("button", {
      type: "button",
      class: cls,
      onclick: opts.onClick,
      disabled: opts.disabled,
      title: opts.title,
    });
    if (opts.icon) node.appendChild(svgIcon(ICONS[opts.icon] || opts.icon, 13));
    if (typeof children === "string") node.appendChild(document.createTextNode(children));
    else if (Array.isArray(children)) children.forEach((c) => node.appendChild(c));
    else if (children) node.appendChild(children);
    return node;
  }
  function chip(label, on, onClick, disabled) {
    return el("button", {
      type: "button",
      class: "kp-chip" + (on ? " is-on" : ""),
      onclick: onClick,
      disabled: disabled,
    }, label);
  }
  function slider(label, value, onChange) {
    const num = el("span", { class: "num", text: Math.round(value * 100) + "%" });
    const input = el("input", {
      type: "range", min: 0, max: 1, step: 0.05, value: String(value), class: "kp-slider",
      oninput: (e) => onChange(parseFloat(e.target.value)),
    });
    return el("div", { class: "kp-slider-row" }, [
      el("div", { class: "kp-slider-hd" }, [el("span", { text: label }), num]),
      input,
    ]);
  }
  function pageHead(title, subtitle, actions) {
    const head = el("div", { class: "kp-page-head" });
    const left = el("div");
    left.appendChild(el("h1", { class: "kp-page-title", text: title }));
    if (subtitle) left.appendChild(el("p", { class: "kp-page-subtitle", text: subtitle }));
    head.appendChild(left);
    if (actions && actions.length) head.appendChild(el("div", { class: "kp-page-actions" }, actions));
    return head;
  }
  function card(opts, children) {
    const c = el("section", { class: "kp-card" });
    if (opts.title || opts.right) {
      const hd = el("div", { class: "kp-card-hd" });
      const left = el("div");
      if (opts.title) left.appendChild(el("h2", { class: "kp-card-title", text: opts.title }));
      if (opts.description) left.appendChild(el("p", { class: "kp-card-sub", text: opts.description }));
      hd.appendChild(left);
      if (opts.right) hd.appendChild(opts.right);
      c.appendChild(hd);
    }
    if (Array.isArray(children)) children.forEach((x) => c.appendChild(x));
    else if (children) c.appendChild(children);
    return c;
  }

  /* ─────────────── Pages ─────────────── */
  function renderKeysPage() {
    const profile = activeProfile();
    const ko = profile.keysOptions;
    const root = el("div");
    root.appendChild(pageHead("Touches", "Mappage des deux touches et comportement de saisie."));

    const grid = el("div", { class: "kp-grid" });

    const previewRight = el("span", { class: "kp-status-pill", text: "Cliquez pour modifier" });
    const canvas = el("div", { class: "kp-canvas" });
    canvas.appendChild(buildKeypadPlateSvg({
      editingKey: state.selectedKey,
      onKeyClick: (k) => { state.selectedKey = state.selectedKey === k ? null : k; render(); },
      keyLedK1: profile.lighting.keyPixels[0],
      keyLedK2: profile.lighting.keyPixels[1],
      keyCapStyle: "neutral",
    }));
    const previewCard = card({ title: "Aperçu", description: "Cliquez sur une touche pour la modifier.", right: previewRight }, [
      el("div", { class: "kp-canvas-wrap" }, canvas),
      el("div", { class: "kp-key-cards" }, [
        keyCard("k2", profile.keys.k2LeftP2),
        keyCard("k1", profile.keys.k1RightP1),
      ]),
    ]);

    const right = el("div", { class: "kp-stack" });
    right.appendChild(state.selectedKey ? renderChordEditor(state.selectedKey) : emptySelectionCard());
    right.appendChild(card({ title: "Comportement", description: "Réglages compilés dans le firmware CH552." }, behaviorBlock(ko)));

    grid.appendChild(previewCard);
    grid.appendChild(right);
    root.appendChild(grid);
    return root;
  }

  function keyCard(slot, chord) {
    const on = state.selectedKey === slot;
    const labelMap = { k1: "K1 — droite", k2: "K2 — gauche" };
    const c = el("button", {
      type: "button",
      class: "kp-key-card" + (on ? " is-on" : ""),
      onclick: () => { state.selectedKey = on ? null : slot; render(); },
    });
    c.appendChild(el("span", { class: "lbl", text: labelMap[slot] }));
    const txt = (chord.mode === "macro" ? "Macro · " : "")
      + (chord.modifiers.length ? chord.modifiers.join("+") + "+" : "")
      + chord.label;
    c.appendChild(el("span", { class: "val", text: txt }));
    return c;
  }

  function emptySelectionCard() {
    return card({ title: "Sélectionner une touche", description: "Cliquez K1 ou K2 sur le schéma pour configurer son code HID, ses modificateurs et les macros." },
      el("div", { class: "kp-empty-pane", text: "Aucune touche sélectionnée" }));
  }

  function behaviorBlock(ko) {
    const stack = el("div", { class: "kp-stack" });

    const swToggle = el("label", { class: "kp-toggle-row" }, [
      el("input", {
        type: "checkbox", checked: ko.softwareRapidTrigger,
        onchange: (e) => setKeysOptions({ softwareRapidTrigger: e.target.checked }),
      }),
      el("span", { class: "kp-toggle-text" }, [
        el("strong", { text: "Rapid trigger logiciel" }),
        el("span", { class: "help", text: "Lecture plus fréquente des contacts pour des réappuis plus rapides. Approximation logicielle, sans capteur Hall." }),
      ]),
    ]);
    stack.appendChild(swToggle);

    if (ko.softwareRapidTrigger) {
      const window = el("div", { class: "kp-stack--tight kp-stack" });
      const num = el("span", { class: "num", text: ko.rapidTriggerResetMs + " ms" });
      const input = el("input", {
        type: "range", min: 1, max: 8, step: 1, value: String(ko.rapidTriggerResetMs), class: "kp-slider",
        oninput: (e) => setKeysOptions({ rapidTriggerResetMs: parseInt(e.target.value, 10) }),
      });
      window.appendChild(el("div", { class: "kp-slider-hd" }, [el("span", { text: "Fenêtre après relâchement" }), num]));
      window.appendChild(input);
      stack.appendChild(window);
    }

    const debounceWrap = el("div");
    const debounceRow = el("div", { class: "kp-row kp-row--justify" }, [
      el("span", { text: "Anti-rebond", style: { fontSize: "12.5px" } }),
      el("input", {
        type: "number", min: 2, max: 50, value: String(ko.debounceMs), class: "kp-field kp-field--mono",
        style: { maxWidth: "92px", textAlign: "right" },
        disabled: ko.softwareRapidTrigger,
        onchange: (e) => {
          const v = parseInt(e.target.value, 10);
          const n = Number.isNaN(v) ? ko.debounceMs : Math.max(2, Math.min(50, v));
          setKeysOptions({ debounceMs: n });
        },
      }),
    ]);
    debounceWrap.appendChild(debounceRow);
    debounceWrap.appendChild(el("p", { text: "Ignoré quand le rapid trigger logiciel est actif.",
      style: { color: "var(--fg-3)", fontSize: "11px", marginTop: "6px" } }));
    stack.appendChild(debounceWrap);

    stack.appendChild(el("label", { class: "kp-toggle-row" }, [
      el("input", {
        type: "checkbox", checked: ko.layoutFrAzerty,
        onchange: (e) => setKeysOptions({ layoutFrAzerty: e.target.checked }),
      }),
      el("span", { class: "kp-toggle-text" }, [
        el("strong", { text: "Disposition AZERTY" }),
        el("span", { class: "help", text: "Échange A/Q et W/Z dans les codes envoyés." }),
      ]),
    ]));
    return stack;
  }

  function renderChordEditor(slot) {
    const profile = activeProfile();
    const chord = slot === "k1" ? profile.keys.k1RightP1 : profile.keys.k2LeftP2;
    const updateChord = (next) => {
      setProfile((p) => {
        const newKeys = Object.assign({}, p.keys);
        if (slot === "k1") newKeys.k1RightP1 = next;
        else newKeys.k2LeftP2 = next;
        return Object.assign({}, p, { keys: newKeys });
      });
    };

    const closeBtn = el("button", { type: "button", class: "kp-btn kp-btn--ghost kp-btn--sm",
      onclick: () => { state.selectedKey = null; render(); }, title: "Fermer" }, svgIcon(ICONS.close, 12));

    const stack = el("div", { class: "kp-stack" });

    stack.appendChild(el("div", { class: "kp-row kp-row--justify" }, [
      el("h3", { class: "kp-card-title", text: slot === "k1" ? "K1 — droite" : "K2 — gauche" }),
      closeBtn,
    ]));

    const modeRow = el("div");
    modeRow.appendChild(el("span", { class: "kp-label", text: "Mode" }));
    modeRow.appendChild(el("div", { class: "kp-btn-row" }, [
      btn({ variant: chord.mode !== "macro" ? "primary" : "", size: "sm",
        onClick: () => updateChord(Object.assign({}, chord, { mode: "hold" })) }, "Maintenir"),
      btn({ variant: chord.mode === "macro" ? "primary" : "", size: "sm",
        onClick: () => updateChord(Object.assign({}, chord, { mode: "macro" })) }, "Macro"),
    ]));
    stack.appendChild(modeRow);

    const modsRow = el("div");
    modsRow.appendChild(el("span", { class: "kp-label", text: "Modificateurs" }));
    const modGrid = el("div", { class: "kp-btn-row" });
    MODIFIER_BUTTONS.forEach((m) => {
      const on = chord.modifiers.includes(m.id);
      modGrid.appendChild(btn({ variant: on ? "primary" : "", size: "sm", onClick: () => {
        const mods = on ? chord.modifiers.filter((x) => x !== m.id) : chord.modifiers.concat(m.id);
        updateChord(Object.assign({}, chord, { modifiers: mods }));
      } }, m.label));
    });
    modsRow.appendChild(modGrid);
    stack.appendChild(modsRow);

    const keyDisp = el("div");
    keyDisp.appendChild(el("span", { class: "kp-label", text: "Touche" }));
    keyDisp.appendChild(el("div", { class: "kp-key-pill", text: chord.label }));
    stack.appendChild(keyDisp);

    const hidRow = el("div");
    hidRow.appendChild(el("span", { class: "kp-label", text: "Code HID" }));
    const sel = el("select", { class: "kp-field", onchange: (e) => {
      const opt = HID_KEY_OPTIONS.find((o) => o.code === e.target.value);
      updateChord(Object.assign({}, chord, { hidCode: e.target.value, label: opt ? opt.label : e.target.value }));
    } });
    HID_KEY_OPTIONS.forEach((o) => sel.appendChild(el("option", { value: o.code, selected: o.code === chord.hidCode, text: `${o.label} — ${o.code}` })));
    hidRow.appendChild(sel);
    stack.appendChild(hidRow);

    const kbdLine = el("div", { class: "kp-kbd-line" });
    kbdLine.appendChild(el("span", { text: chord.mode === "macro" ? "Déclenche" : "Envoie" }));
    chord.modifiers.forEach((m) => kbdLine.appendChild(el("span", { class: "kp-kbd", text: m })));
    if (chord.modifiers.length) kbdLine.appendChild(el("span", { text: "+" }));
    kbdLine.appendChild(el("span", { class: "kp-kbd", text: chord.label }));
    stack.appendChild(kbdLine);

    if (chord.mode === "macro") {
      stack.appendChild(macroBlock(chord, updateChord));
    }

    return card({}, stack);
  }

  function macroBlock(chord, updateChord) {
    const wrap = el("div", { class: "kp-stack--tight kp-stack",
      style: { background: "var(--bg-2)", border: "1px solid var(--line-2)", borderRadius: "10px", padding: "12px" } });

    if (state.installedApps && state.installedApps.length) {
      const lab = el("label", {});
      lab.appendChild(el("span", { class: "kp-label", text: "Application installée" }));
      const sel = el("select", { class: "kp-field", onchange: (e) => {
        const app = state.installedApps.find((a) => a.appId === e.target.value);
        if (!app) return;
        bindInstalledApp(app, chord, updateChord);
        e.target.value = "";
      } });
      sel.appendChild(el("option", { value: "", text: "Choisir une app Windows..." }));
      state.installedApps.forEach((a) => sel.appendChild(el("option", { value: a.appId, text: a.name })));
      lab.appendChild(sel);
      wrap.appendChild(lab);
    } else if (state.appsLoading) {
      wrap.appendChild(el("p", { class: "kp-card-sub", text: "Recherche des apps installées..." }));
    }

    const lab2 = el("label", {});
    lab2.appendChild(el("span", { class: "kp-label", text: "Preset rapide" }));
    const sel2 = el("select", { class: "kp-field", onchange: (e) => {
      const p = MACRO_PRESETS.find((x) => x.id === e.target.value);
      if (!p) return;
      const opt = HID_KEY_OPTIONS.find((o) => o.code === p.hidCode);
      updateChord(Object.assign({}, chord, {
        modifiers: p.modifiers.slice(),
        hidCode: p.hidCode,
        label: opt ? opt.label : p.hidCode,
        macroText: p.macroText,
        macroDelayMs: p.macroDelayMs,
        macroTapEnter: p.macroTapEnter,
      }));
      e.target.value = "";
    } });
    sel2.appendChild(el("option", { value: "", text: "Choisir une action..." }));
    MACRO_PRESETS.forEach((p) => sel2.appendChild(el("option", { value: p.id, text: p.label })));
    lab2.appendChild(sel2);
    wrap.appendChild(lab2);

    const lab3 = el("label", {});
    lab3.appendChild(el("span", { class: "kp-label", text: "Délai après combo (ms)" }));
    lab3.appendChild(el("input", {
      type: "number", min: 0, max: 1200, value: String(chord.macroDelayMs == null ? 180 : chord.macroDelayMs),
      class: "kp-field", style: { maxWidth: "120px" },
      onchange: (e) => updateChord(Object.assign({}, chord, {
        macroDelayMs: Math.max(0, Math.min(1200, parseInt(e.target.value, 10) || 0)),
      })),
    }));
    wrap.appendChild(lab3);

    const lab4 = el("label", {});
    lab4.appendChild(el("span", { class: "kp-label", text: "Texte à saisir" }));
    lab4.appendChild(el("input", {
      type: "text", maxlength: 96, value: chord.macroText || "",
      class: "kp-field", placeholder: "notepad",
      oninput: (e) => updateChord(Object.assign({}, chord, { macroText: e.target.value })),
    }));
    wrap.appendChild(lab4);

    const tgl = el("label", { class: "kp-toggle-row" });
    tgl.appendChild(el("input", {
      type: "checkbox", checked: chord.macroTapEnter !== false,
      onchange: (e) => updateChord(Object.assign({}, chord, { macroTapEnter: e.target.checked })),
    }));
    tgl.appendChild(el("span", { class: "kp-toggle-text" }, [
      el("strong", { text: "Entrée automatique après la saisie" }),
    ]));
    wrap.appendChild(tgl);

    return wrap;
  }

  async function bindInstalledApp(app, chord, updateChord) {
    try {
      const r = await api.createLauncher(app.appId, app.name, state.selectedKey || "k1");
      const opt = HID_KEY_OPTIONS.find((o) => o.code === "KeyR");
      updateChord(Object.assign({}, chord, {
        mode: "macro",
        modifiers: ["gui"],
        hidCode: "KeyR",
        label: opt ? opt.label : "R",
        macroText: r.alias,
        macroDelayMs: 85,
        macroTapEnter: true,
      }));
      J.notify && J.notify({ kind: "success", text: "Launcher Windows prêt: " + r.alias });
    } catch (e) {
      J.notify && J.notify({ kind: "error", text: "Échec création launcher: " + e.message });
    }
  }

  /* ── Lighting page ── */
  let lightFrameTime = 0;
  let lightStart = 0;
  let lightRaf = 0;

  function startLightLoop() {
    cancelAnimationFrame(lightRaf);
    lightStart = performance.now();
    const tick = (now) => {
      lightFrameTime = (now - lightStart) / 1000;
      const canvas = document.getElementById("kp-light-canvas");
      if (canvas) {
        const profile = activeProfile();
        const preview = computePreview(profile, lightFrameTime);
        canvas.innerHTML = "";
        canvas.appendChild(buildKeypadPlateSvg({
          keyCapStyle: "ledPreview",
          keyLedK1: preview.k1,
          keyLedK2: preview.k2,
          edgePixels: preview.edge,
        }));
      }
      lightRaf = requestAnimationFrame(tick);
    };
    lightRaf = requestAnimationFrame(tick);
  }
  function stopLightLoop() { cancelAnimationFrame(lightRaf); lightRaf = 0; }

  function renderLightingPage() {
    const profile = activeProfile();
    const root = el("div");
    root.appendChild(pageHead("Éclairage", "Effets, couleurs et intensité — séparés pour les touches et le contour."));

    const grid = el("div", { class: "kp-grid" });

    const canvasWrap = el("div", { id: "kp-light-canvas", class: "kp-canvas" });
    const previewCard = card({ title: "Aperçu en direct" }, [
      el("div", { class: "kp-canvas-wrap" }, canvasWrap),
      el("div", { class: "kp-row kp-row--justify",
        style: { marginTop: "16px", color: "var(--fg-3)", fontSize: "11.5px" } }, [
        el("span", {}, [
          el("span", { text: "Effet : " }),
          el("span", { text: EFFECT_LABELS[profile.lighting.effect] || profile.lighting.effect, style: { color: "var(--fg-1)" } }),
        ]),
        el("span", { text: profile.hardware.edgeLedCount + " LED contour · 2 LED touches" }),
      ]),
    ]);

    const subTabs = el("div", { class: "kp-sub-tabs" }, [
      subTab("effect", "Effet"),
      subTab("keys", "Touches"),
      subTab("edge", "Contour"),
    ]);
    let body;
    if (state.lightingSubtab === "effect") body = lightingEffectBlock(profile);
    else if (state.lightingSubtab === "keys") body = lightingKeysBlock(profile);
    else body = lightingEdgeBlock(profile);
    body.classList.add("kp-fade-in");
    const cfgCard = card({ title: "Configuration", right: subTabs }, body);

    grid.appendChild(previewCard);
    grid.appendChild(cfgCard);
    root.appendChild(grid);
    return root;
  }
  function subTab(key, label) {
    return el("button", {
      type: "button", class: "kp-sub-tab" + (state.lightingSubtab === key ? " is-on" : ""),
      onclick: () => { state.lightingSubtab = key; render(); },
    }, label);
  }

  function lightingEffectBlock(profile) {
    const wrap = el("div", { class: "kp-stack" });

    const fxWrap = el("div");
    fxWrap.appendChild(el("span", { class: "kp-label", text: "Type d'effet" }));
    const fxGrid = el("div", { class: "kp-chip-grid" });
    EFFECTS.forEach((fx) => {
      fxGrid.appendChild(chip(EFFECT_LABELS[fx], profile.lighting.effect === fx, () => setLighting({ effect: fx }), false));
    });
    fxWrap.appendChild(fxGrid);
    wrap.appendChild(fxWrap);

    const trigWrap = el("div");
    trigWrap.appendChild(el("span", { class: "kp-label", text: "Déclencheur (effet réactif)" }));
    const trigGrid = el("div", { class: "kp-chip-grid" });
    TRIGGERS.forEach((m) => {
      trigGrid.appendChild(chip(TRIGGER_LABELS[m], profile.lighting.trigger === m, () => setLighting({ trigger: m }), profile.lighting.effect !== "reactive"));
    });
    trigWrap.appendChild(trigGrid);
    if (profile.lighting.effect !== "reactive") {
      trigWrap.appendChild(el("p", { text: "Activez l'effet « Réactif » pour utiliser ces options.",
        style: { color: "var(--fg-3)", fontSize: "11.5px", marginTop: "10px" } }));
    }
    wrap.appendChild(trigWrap);
    return wrap;
  }

  function lightingKeysBlock(profile) {
    const wrap = el("div", { class: "kp-stack" });

    const staticBlock = el("div");
    staticBlock.appendChild(el("span", { class: "kp-label", text: "Couleur statique" }));
    staticBlock.appendChild(el("div", {
      class: "kp-row kp-row--justify",
      style: { background: "var(--bg-2)", border: "1px solid var(--line-2)", borderRadius: "10px", padding: "10px 14px" },
    }, [
      el("span", { text: "Sous K1 et K2", style: { color: "var(--fg-2)", fontSize: "12px" } }),
      el("input", {
        type: "color", class: "kp-color", value: profile.lighting.staticKeyColor,
        oninput: (e) => setLighting({ staticKeyColor: e.target.value }),
      }),
    ]));
    staticBlock.appendChild(btn({ size: "sm", onClick: () => setLighting({
      keyPixels: [profile.lighting.staticKeyColor, profile.lighting.staticKeyColor],
    }) }, "Appliquer aussi aux effets animés"));
    wrap.appendChild(staticBlock);

    const animBlock = el("div");
    animBlock.appendChild(el("span", { class: "kp-label", text: "Teintes pour effets animés" }));
    const grid = el("div", {
      style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" },
    });
    [["K1 — droite", 0], ["K2 — gauche", 1]].forEach(([label, idx]) => {
      const cell = el("label", {
        style: { background: "var(--bg-2)", border: "1px solid var(--line-2)", borderRadius: "10px", padding: "10px 12px", display: "flex", flexDirection: "column", gap: "8px" },
      }, [
        el("span", { class: "kp-label", text: label }),
        el("input", {
          type: "color", class: "kp-color", value: profile.lighting.keyPixels[idx],
          oninput: (e) => {
            const k = profile.lighting.keyPixels.slice();
            k[idx] = e.target.value;
            setLighting({ keyPixels: k });
          },
        }),
      ]);
      grid.appendChild(cell);
    });
    animBlock.appendChild(grid);
    wrap.appendChild(animBlock);

    wrap.appendChild(slider("Luminosité", profile.lighting.keyBrightness, (v) => setLighting({ keyBrightness: v })));
    wrap.appendChild(slider("Vitesse", profile.lighting.keySpeed, (v) => setLighting({ keySpeed: v })));
    return wrap;
  }

  function lightingEdgeBlock(profile) {
    const wrap = el("div", { class: "kp-stack" });

    const block = el("div");
    block.appendChild(el("span", { class: "kp-label", text: "Couleur statique" }));
    block.appendChild(el("div", {
      class: "kp-row kp-row--justify",
      style: { background: "var(--bg-2)", border: "1px solid var(--line-2)", borderRadius: "10px", padding: "10px 14px" },
    }, [
      el("span", { text: profile.hardware.edgeLedCount + " segments", style: { color: "var(--fg-2)", fontSize: "12px" } }),
      el("input", {
        type: "color", class: "kp-color", value: profile.lighting.staticEdgeColor,
        oninput: (e) => setLighting({ staticEdgeColor: e.target.value }),
      }),
    ]));
    block.appendChild(btn({ size: "sm", onClick: () => setLighting({
      edgePixels: Array.from({ length: profile.hardware.edgeLedCount }, () => profile.lighting.staticEdgeColor),
    }) }, "Appliquer aussi aux effets animés"));
    wrap.appendChild(block);

    wrap.appendChild(slider("Luminosité", profile.lighting.edgeBrightness, (v) => setLighting({ edgeBrightness: v })));
    wrap.appendChild(slider("Vitesse", profile.lighting.edgeSpeed, (v) => setLighting({ edgeSpeed: v })));
    return wrap;
  }

  /* ── Profiles page ── */
  function renderProfilesPage() {
    const root = el("div");
    const actions = [
      btn({ icon: "layers", onClick: duplicateProfile }, "Dupliquer l'actif"),
      btn({ variant: "primary", icon: "plus", onClick: addProfile }, "Nouveau profil"),
    ];
    root.appendChild(pageHead("Profils", "Plusieurs configurations enregistrées dans le même projet firmware.", actions));
    const list = el("ul", { class: "kp-list-divided" });
    state.bundle.profiles.forEach((slot) => {
      const active = slot.id === state.bundle.activeProfileId;
      const li = el("li");
      li.appendChild(btn({ variant: active ? "primary" : "", size: "sm",
        onClick: () => { state.bundle.activeProfileId = slot.id; render(); } }, active ? "Actif" : "Activer"));
      const input = el("input", {
        type: "text", value: slot.name, class: "kp-field",
        style: { flex: "1 1 0", minWidth: "10rem" },
        onchange: (e) => renameProfile(slot.id, e.target.value),
      });
      li.appendChild(input);
      const del = btn({ variant: "ghost", size: "sm", icon: "trash",
        onClick: () => deleteProfile(slot.id),
        disabled: state.bundle.profiles.length <= 1, title: "Supprimer" });
      li.appendChild(del);
      list.appendChild(li);
    });
    root.appendChild(card({}, list));
    return root;
  }
  function duplicateProfile() {
    const cur = activeProfile();
    const id = newSlotId();
    const curSlot = state.bundle.profiles.find((p) => p.id === state.bundle.activeProfileId);
    const name = "Copie — " + ((curSlot && curSlot.name) || "Profil");
    const copy = JSON.parse(JSON.stringify(cur));
    copy.workspaceRoot = state.workspace;
    state.bundle.profiles.push({ id, name, data: copy });
    state.bundle.activeProfileId = id;
    render();
  }
  function addProfile() {
    const id = newSlotId();
    state.bundle.profiles.push({ id, name: "Nouveau profil", data: defaultProfile(state.workspace) });
    state.bundle.activeProfileId = id;
    render();
  }
  function deleteProfile(id) {
    if (state.bundle.profiles.length <= 1) return;
    state.bundle.profiles = state.bundle.profiles.filter((p) => p.id !== id);
    if (state.bundle.activeProfileId === id) state.bundle.activeProfileId = state.bundle.profiles[0].id;
    render();
  }
  function renameProfile(id, name) {
    const t = (name || "").trim() || "Profil";
    state.bundle.profiles = state.bundle.profiles.map((p) => p.id === id ? Object.assign({}, p, { name: t }) : p);
    render();
  }

  /* ── Device page ── */
  function renderDevicePage() {
    const profile = activeProfile();
    const root = el("div");
    root.appendChild(pageHead("Appareil", "Identité USB et référence matérielle."));
    const grid = el("div", { class: "kp-grid--equal kp-grid" });

    const sel = el("select", { class: "kp-field", onchange: (e) => setProfile((p) => Object.assign({}, p, {
      device: Object.assign({}, p.device, { keypadProductId: e.target.value }),
    })) });
    KEYPAD_PRODUCT_OPTIONS.forEach((o) => sel.appendChild(el("option", { value: o.id, selected: o.id === profile.device.keypadProductId, text: o.label })));
    const hint = (KEYPAD_PRODUCT_OPTIONS.find((o) => o.id === profile.device.keypadProductId) || {}).hint || "";
    grid.appendChild(card({ title: "Modèle du macropad" }, [
      sel,
      el("p", { class: "kp-card-sub", text: hint }),
    ]));

    const usbStack = el("div", { class: "kp-stack--tight kp-stack" });
    usbStack.appendChild(infoField("Fabricant", "Techalchemy SI", true));
    usbStack.appendChild(infoField("Numéro de série", "TCY-CH552-KB", true));
    const nameRow = el("div");
    nameRow.appendChild(el("span", { class: "kp-label", text: "Nom du produit" }));
    nameRow.appendChild(el("input", {
      type: "text", maxlength: 31, value: profile.device.productName, class: "kp-field",
      onchange: (e) => setProfile((p) => Object.assign({}, p, {
        device: Object.assign({}, p.device, { productName: e.target.value }),
      })),
    }));
    usbStack.appendChild(nameRow);
    grid.appendChild(card({ title: "Identité USB" }, usbStack));

    root.appendChild(grid);
    return root;
  }
  function infoField(label, value, ro) {
    const w = el("div");
    w.appendChild(el("span", { class: "kp-label", text: label }));
    w.appendChild(el("div", {
      class: "kp-field",
      style: ro ? { background: "var(--bg-3)", cursor: "default" } : null,
      text: value,
    }));
    return w;
  }

  /* ── Firmware page ── */
  function renderFirmwarePage() {
    const root = el("div");
    const compileBtn = btn({
      icon: "cpu", onClick: () => runFirmware("compile"),
      disabled: !state.workspaceValid || state.fwBusy != null,
    }, state.fwBusy === "compile" ? "Compilation…" : "Compiler");
    const uploadBtn = btn({
      variant: "primary", icon: "upload", onClick: () => runFirmware("upload"),
      disabled: !state.workspaceValid || state.fwBusy != null,
    }, state.fwBusy === "upload" ? "Envoi…" : "Envoyer");
    root.appendChild(pageHead("Mise à jour", "Compilez le firmware puis envoyez-le sur le macropad.", [compileBtn, uploadBtn]));

    if (!state.arduinoCli.installed) {
      const banner = el("div", { class: "kp-banner" }, [
        el("strong", { text: "arduino-cli non installé." }),
        el("span", { text: " Cliquez sur ", style: { marginLeft: "4px" } }),
        btn({ size: "sm", onClick: installArduinoCli, disabled: state.arduinoBusy },
          state.arduinoBusy ? "Téléchargement…" : "Télécharger maintenant"),
        el("span", { text: " — sera téléchargé automatiquement à la première compilation.",
          style: { marginLeft: "4px" } }),
      ]);
      root.appendChild(banner);
    }

    const grid = el("div", { class: "kp-grid--wide kp-grid" });
    const steps = [
      { n: "1", title: "Compiler", detail: "Génère le micrologiciel à partir du dossier projet sélectionné." },
      { n: "2", title: "Mode téléchargement", detail: "Maintenez le bouton sous le clavier enfoncé, branchez le câble USB, puis relâchez le bouton juste après la connexion." },
      { n: "3", title: "Envoyer", detail: "Cliquez sur Envoyer pendant que l'appareil reste en mode téléchargement." },
    ];
    const list = el("ol", { class: "kp-step-list" });
    steps.forEach((s) => list.appendChild(el("li", {}, [
      el("span", { class: "kp-step-num", text: s.n }),
      el("div", {}, [
        el("p", { text: s.title }),
        el("p", { text: s.detail }),
      ]),
    ])));
    grid.appendChild(card({ title: "Étapes" }, list));

    const logEl = el("pre", { class: "kp-log", "data-empty": "Aucune sortie pour le moment.", id: "kp-fwlog", text: state.fwLog || "" });
    grid.appendChild(card({ title: "Sortie outil" }, logEl));

    root.appendChild(grid);
    return root;
  }
  async function runFirmware(kind) {
    state.fwBusy = kind;
    state.fwLog = "Exécution…\n";
    render();
    try {
      const r = kind === "compile"
        ? await api.compile(state.workspace, null)
        : await api.upload(state.workspace, { preferPython: false, attempts: 1 });
      state.fwLog = (r.output || "").trim() || "Terminé.";
      J.notify && J.notify({ kind: "success", text: kind === "compile" ? "Compilation OK" : "Envoi OK" });
    } catch (e) {
      state.fwLog = String(e && e.message ? e.message : e);
      J.notify && J.notify({ kind: "error", text: (kind === "compile" ? "Compilation: " : "Envoi: ") + state.fwLog });
    } finally {
      state.fwBusy = null;
      render();
      const log = document.getElementById("kp-fwlog");
      if (log) log.scrollTop = log.scrollHeight;
    }
  }

  async function installArduinoCli() {
    state.arduinoBusy = true;
    render();
    try {
      const r = await api.arduinoCliInstall();
      state.arduinoCli = { installed: true, path: r.path, vendored: state.arduinoCli.vendored };
      J.notify && J.notify({ kind: "success", text: "arduino-cli installé." });
    } catch (e) {
      J.notify && J.notify({ kind: "error", text: "Échec téléchargement arduino-cli: " + e.message });
    } finally {
      state.arduinoBusy = false;
      render();
    }
  }

  /* ── Drivers page ── */
  function renderDriversPage() {
    const root = el("div");
    root.appendChild(pageHead("Pilotes", "Si Windows ne reconnaît pas l'appareil, installez un pilote."));
    const grid = el("div", { class: "kp-grid--equal kp-grid" });
    const links = [
      ["Pilote USB CH372 / CH375 (Windows)", "https://www.wch-ic.com/downloads/CH372DRV_ZIP.html"],
      ["Pilote CH341 (série, souvent fourni avec les outils)", "https://www.wch-ic.com/downloads/CH341SER_ZIP.html"],
      ["Centre de téléchargement WCH", "https://www.wch-ic.com/downloads.html"],
    ];
    const list = el("div", { class: "kp-stack--tight kp-stack" });
    links.forEach(([lab, url]) => {
      const b = el("button", { type: "button", class: "kp-link-row",
        onclick: () => window.open(url, "_blank") }, lab);
      list.appendChild(b);
    });
    grid.appendChild(card({ title: "Téléchargements" }, list));
    grid.appendChild(card({ title: "Gestionnaire de périphériques" }, [
      el("p", { class: "kp-card-sub", text: "Repérez un périphérique inconnu ou « WCH », puis mettez à jour le pilote." }),
      btn({ icon: "wrench", onClick: () => api.openDeviceManager().catch(() => null) }, "Ouvrir le gestionnaire"),
    ]));
    root.appendChild(grid);
    return root;
  }

  /* ── About page ── */
  function renderAboutPage() {
    const root = el("div");
    root.appendChild(pageHead("À propos", "Macropad 2 touches Le Labo — outil communautaire de personnalisation."));
    const grid = el("div", { class: "kp-grid--wide kp-grid" });

    const info = el("div", { class: "kp-stack" });
    info.appendChild(el("p", { class: "kp-card-sub",
      text: "Application de personnalisation pour les keypads et macropads de la communauté Le Labo. Pensée pour rester claire, sans surcharge visuelle, et exploiter le matériel cible sans promettre ce qu'il ne peut pas faire." }));
    info.appendChild(el("p", { class: "kp-card-sub", text: "Conçue par Puparia. Projet Open Source." }));
    info.appendChild(el("div", { class: "kp-info-grid" }, [
      el("div", { class: "kp-info-cell" }, [el("span", { class: "kp-label", text: "Version" }), el("p", { class: "val", text: APP_VERSION })]),
      el("div", { class: "kp-info-cell" }, [el("span", { class: "kp-label", text: "Auteur" }), el("p", { class: "val", text: "Puparia" })]),
    ]));
    info.appendChild(btn({ onClick: () => window.open("https://github.com/Pupariaa", "_blank") }, "Ouvrir GitHub"));
    grid.appendChild(card({ title: "Le projet" }, info));

    const features = [
      ["Profils multiples", "Plusieurs configurations dans un même fichier projet, profil actif compilé dans le firmware."],
      ["Éclairage par zone", "Couleurs et effets séparés pour les touches et le contour, avec aperçu en temps réel."],
      ["Mappage HID", "Affectation libre des deux touches via codes HID standards et modificateurs."],
      ["Rapid trigger logiciel", "Détection rapide du relâchement / re-pression, paramétrable par profil."],
      ["Anti-rebond ajustable", "Debounce configurable et mise en page AZERTY native côté firmware."],
      ["Compilation & flash intégrés", "Génération du header, build et upload vers le CH552 sans quitter l'application."],
    ];
    const limits = [
      ["Entrée numérique uniquement", "Le CH552 lit les touches en tout-ou-rien. Pas de course analogique ni de capteur Hall."],
      ["Pas de SOCD ni DKS avancé", "Les comportements dépendants d'une course continue ne sont pas reproductibles."],
      ["Deux touches", "Le matériel cible expose deux entrées. Pas de calques étendus comme sur un clavier complet."],
      ["Stockage limité", "Un seul profil actif réside à bord. Les autres restent dans le fichier projet et sont flashés à la demande."],
    ];
    const right = el("div", { class: "kp-stack" });
    right.appendChild(card({ title: "Ce que fait l'application", description: "Fonctions prises en charge nativement par cette interface et le firmware associé." },
      el("ul", { class: "kp-feature-grid" }, features.map(([t, d]) => featureLi(t, d, "ok")))
    ));
    right.appendChild(card({ title: "Limites matérielles", description: "Le CH552 reste un microcontrôleur d'entrée de gamme. Certaines fonctions populaires sur d'autres claviers ne sont pas réalisables, et l'application l'assume." },
      el("ul", { class: "kp-feature-grid" }, limits.map(([t, d]) => featureLi(t, d, "limit")))
    ));
    grid.appendChild(right);
    root.appendChild(grid);
    return root;
  }
  function featureLi(title, desc, kind) {
    return el("li", { class: "kp-feature" }, [
      el("span", { class: "dot " + (kind === "ok" ? "dot--ok" : "dot--limit") }),
      el("div", {}, [
        el("p", { text: title }),
        el("span", { text: desc }),
      ]),
    ]);
  }

  /* ─────────────── Top toolbar (workspace + status + save) ─────────────── */
  function renderToolbar() {
    const tb = el("div", { class: "kp-toolbar" });
    const wsLabel = state.workspace
      ? state.workspace.split(/[\\/]/).filter(Boolean).slice(-2).join(" / ")
      : "Aucun dossier";
    const pickBtn = el("button", {
      type: "button", class: "kp-ws-pill", title: state.workspace || "Cliquer pour définir le workspace",
      onclick: chooseWorkspaceDialog,
    }, [
      svgIcon(ICONS.folder, 13),
      el("span", { class: "label", text: wsLabel }),
    ]);
    tb.appendChild(pickBtn);

    if (state.workspaceValid && state.bundle.profiles.length > 0) {
      const slot = state.bundle.profiles.find((p) => p.id === state.bundle.activeProfileId) || state.bundle.profiles[0];
      const sel = el("select", {
        class: "kp-field kp-field--mono", style: { maxWidth: "220px" },
        onchange: (e) => { state.bundle.activeProfileId = e.target.value; render(); },
      });
      state.bundle.profiles.forEach((p) => sel.appendChild(el("option", { value: p.id, selected: p.id === slot.id, text: p.name })));
      tb.appendChild(sel);
    }

    tb.appendChild(el("div", { class: "kp-toolbar-spacer" }));
    const pill = statusPill(state.status);
    pill.id = "kp-status-pill";
    tb.appendChild(pill);
    tb.appendChild(btn({
      variant: "primary", icon: "save", onClick: saveBundle,
      disabled: !state.workspaceValid || state.saving,
    }, state.saving ? "Sauvegarde…" : "Enregistrer"));

    return tb;
  }

  function statusPill(status) {
    if (status == null) return el("span", { class: "kp-status-pill" }, [el("span", { class: "dot" }), el("span", { text: "Recherche" })]);
    if (status.bootloaderPresent) return el("span", { class: "kp-status-pill is-bootloader" }, [el("span", { class: "dot" }), el("span", { text: "Mode téléchargement" })]);
    if (status.hidPresent) return el("span", { class: "kp-status-pill is-connected" }, [el("span", { class: "dot" }), el("span", { text: "Connecté" })]);
    return el("span", { class: "kp-status-pill" }, [el("span", { class: "dot" }), el("span", { text: "Aucun appareil" })]);
  }

  async function chooseWorkspaceDialog() {
    const cur = state.workspace || state.vendoredWorkspace || "";
    const v = window.prompt(
      "Chemin absolu du dossier workspace (qui contient CH552_HID_Keyboard).\n\nLaisser vide pour utiliser le firmware vendoré dans Jarvis.",
      cur,
    );
    if (v == null) return;
    const path = v.trim() || state.vendoredWorkspace;
    if (!path) return;
    try {
      const r = await api.setWorkspace(path);
      state.workspace = r.workspace;
      state.workspaceValid = !!r.valid;
      await reloadBundle();
      render();
    } catch (e) {
      J.notify && J.notify({ kind: "error", text: "Workspace invalide: " + e.message });
    }
  }

  async function reloadBundle() {
    try {
      const r = await api.getProfile(state.workspace);
      state.bundle = r.bundle || defaultBundle(state.workspace);
    } catch (e) {
      state.bundle = defaultBundle(state.workspace);
    }
  }

  async function saveBundle() {
    if (!state.workspaceValid) return;
    state.saving = true; state.saveError = null;
    render();
    try {
      await api.putProfile(state.bundle, state.workspace);
      J.notify && J.notify({ kind: "success", text: "Profil enregistré et firmware régénéré." });
    } catch (e) {
      state.saveError = e.message || String(e);
      J.notify && J.notify({ kind: "error", text: state.saveError });
    } finally {
      state.saving = false;
      render();
    }
  }

  /* ─────────────── Main render ─────────────── */
  function render() {
    const root = document.getElementById("page-root");
    if (!root) return;
    root.innerHTML = "";

    if (!state.workspaceValid && state.workspace) {
      root.appendChild(el("div", { class: "kp-banner kp-banner--err",
        text: "Ce dossier ne contient pas le projet CH552_HID_Keyboard — sélectionnez la racine du firmware (le firmware vendoré est dans " + state.vendoredWorkspace + ")." }));
    }
    if (state.saveError) {
      root.appendChild(el("div", { class: "kp-banner kp-banner--err", text: state.saveError }));
    }

    root.appendChild(renderToolbar());
    if (isEmbedded) root.appendChild(renderEmbeddedTabs());

    const pageWrap = el("div", { class: "kp-page-wrap" });
    let page;
    switch (state.tab) {
      case "keys":     page = renderKeysPage(); break;
      case "light":    page = renderLightingPage(); break;
      case "profiles": page = renderProfilesPage(); break;
      case "device":   page = renderDevicePage(); break;
      case "firmware": page = renderFirmwarePage(); break;
      case "drivers":  page = renderDriversPage(); break;
      case "about":    page = renderAboutPage(); break;
      default:         page = renderKeysPage();
    }
    page.classList.add("kp-fade-in");
    pageWrap.appendChild(page);
    root.appendChild(pageWrap);

    if (state.tab === "light") startLightLoop();
    else stopLightLoop();
  }

  function renderEmbeddedTabs() {
    const TABS = [
      { id: "keys",     label: "Touches" },
      { id: "light",    label: "Éclairage" },
      { id: "profiles", label: "Profils" },
      { id: "device",   label: "Appareil" },
      { id: "firmware", label: "Mise à jour" },
      { id: "drivers",  label: "Pilotes" },
      { id: "about",    label: "À propos" },
    ];
    const bar = el("div", { class: "kp-emb-tabs" });
    TABS.forEach(t => {
      bar.appendChild(el("button", {
        type: "button",
        class: "kp-emb-tab" + (state.tab === t.id ? " is-on" : ""),
        onclick: () => {
          state.tab = t.id;
          if (t.id !== "light") stopLightLoop();
          render();
        },
      }, [document.createTextNode(t.label)]));
    });
    return bar;
  }

  /* ─────────────── Boot ─────────────── */
  async function boot() {
    if (isEmbedded) {
      document.body.classList.add("is-embedded");
    } else {
      J.mountAtmosphere();

      J.mountSidebar({
        sections: [
          {
            label: "Macropad 2 touches Le Labo",
            items: [
              { id: "keys",     label: "Touches" },
              { id: "light",    label: "Éclairage" },
              { id: "profiles", label: "Profils" },
              { id: "device",   label: "Appareil" },
              { id: "firmware", label: "Mise à jour" },
              { id: "drivers",  label: "Pilotes" },
              { id: "about",    label: "À propos" },
            ],
          },
          {
            label: window.JARVIS_ASSISTANT_NAME || "Jarvis",
            items: [
              { id: "_dashboard", label: "Dashboard" },
              { id: "_settings",  label: "Système" },
              { id: "_home",      label: "Accueil" },
            ],
          },
        ],
        activeId: state.tab,
        onNav: (id) => {
          if (id === "_dashboard") { window.location.href = "/dashboard"; return; }
          if (id === "_settings")  { window.location.href = "/settings"; return; }
          if (id === "_home")      { window.location.href = "/"; return; }
          state.tab = id;
          try { history.replaceState(null, "", "#" + id); } catch (_) {}
          render();
        },
      });

      J.mountTopbar({ pageTitle: "Macropad 2 touches Le Labo", crumb: "/ macropad" });
      J.mountBottomNav && J.mountBottomNav({ active: "system" });
    }

    try {
      const ws = await api.getWorkspace();
      state.vendoredWorkspace = ws.vendored;
      state.workspace = ws.workspace || ws.vendored || "";
      state.workspaceValid = !!ws.valid;
    } catch (e) { console.warn("getWorkspace failed", e); }

    try { await reloadBundle(); } catch (e) { console.warn("reloadBundle failed", e); }

    try {
      const ac = await api.arduinoCliStatus();
      state.arduinoCli = ac;
    } catch (e) { console.warn("arduino-cli status failed", e); }

    try {
      state.appsLoading = true;
      const apps = await api.installedApps();
      state.installedApps = apps.apps || [];
    } catch (e) { /* ignore */ }
    finally { state.appsLoading = false; }

    const hash = (window.location.hash || "").replace(/^#/, "");
    const VALID_TABS = ["keys", "light", "profiles", "device", "firmware", "drivers", "about"];
    if (VALID_TABS.includes(hash)) state.tab = hash;
    window.addEventListener("hashchange", () => {
      const h = (window.location.hash || "").replace(/^#/, "");
      if (VALID_TABS.includes(h) && h !== state.tab) { state.tab = h; render(); }
    });

    pollStatus();
    render();
  }

  function _statusKey(s) {
    if (!s) return "none";
    return (s.bootloaderPresent ? "1" : "0") + (s.hidPresent ? "1" : "0");
  }

  async function pollStatus() {
    try {
      const next = await api.status();
      const prevKey = _statusKey(state.status);
      const nextKey = _statusKey(next);
      state.status = next;
      if (prevKey !== nextKey) {
        const oldPill = document.getElementById("kp-status-pill");
        if (oldPill && oldPill.parentNode) {
          const newPill = statusPill(next);
          newPill.id = "kp-status-pill";
          oldPill.replaceWith(newPill);
        }
      }
    } catch (e) { /* ignore */ }
    setTimeout(pollStatus, 2500);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
