const STOP = new Set([
  "a", "an", "the", "and", "or", "to", "of", "in", "on", "for", "is", "it", "be", "as", "at",
  "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "en", "au", "aux", "est", "ce",
  "que", "qui", "par", "pour", "sur", "avec", "pas", "ne", "se", "sa", "son", "ses", "mon", "mes",
]);

const TOPIC_SYNONYMS = {
  setup: ["setup", "install", "installation", "instalation", "instaler", "installer", "configurer", "configuration", "wizard", "first-run", "premier", "demarrage", "bootstrap"],
  run: ["run", "start", "demarrer", "demarrage", "lancer", "launch", "activer", "activation", "jarvis.ps1"],
  bundle: ["bundle", "offline", "cdn", "download", "telecharger", "pyvenv", "venv", "rehome"],
  onedrive: ["onedrive", "one drive", "cloud", "sync", "guard"],
  voice: ["voice", "voix", "vocal", "livekit", "micro", "mic", "microphone", "parler", "speech", "webrtc"],
  livekit: ["livekit", "live kit", "livekitt", "lk", "7880", "wss"],
  stt: ["stt", "speech", "deepgram", "whisper", "transcription", "reconnaissance", "ecoute"],
  tts: ["tts", "elevenlabs", "piper", "gemini", "synthese", "parole", "voix"],
  api: ["api", "endpoint", "route", "rest", "fastapi", "http", "port", "8000"],
  env: ["env", "dotenv", ".env", "variable", "cle", "key", "token", "secret"],
  memory: ["memory", "memoire", "memoir", "souvenir", "recall", "rappel", "ingest", "topic", "facts"],
  tool: ["tool", "outil", "tools", "execute", "registry"],
  skill: ["skill", "competence", "skills", "abi", "lab", "install skill"],
  mission: ["mission", "project", "projet", "orchestrator", "worker", "docker executor"],
  proactive: ["proactive", "proactif", "briefing", "initiative", "curator", "rappel"],
  gateway: ["gateway", "agent", "chat", "conversation", "session"],
  error: ["error", "erreur", "bug", "fail", "echec", "probleme", "problem", "fix", "corriger", "troubleshoot", "jrv", "code erreur", "error code"],
  docker: ["docker", "container", "compose", "sandbox"],
  telegram: ["telegram", "bot", "telegrame", "tg"],
  discord: ["discord", "discorde"],
  spotify: ["spotify", "spotify", "music", "musique", "deezer", "player"],
  google: ["google", "gmail", "calendar", "oauth", "gemini"],
  notion: ["notion", "tasks", "taches"],
  vision: ["vision", "webcam", "face", "visage", "yolo", "detection"],
  kernel: ["kernel", "settings", "paths", "events", "bus", "permissions", "approval"],
  llm: ["llm", "claude", "anthropic", "openai", "gpt", "mistral", "ollama", "model", "modele"],
  test: ["test", "pytest", "ci", "validation"],
  logs: ["log", "logs", "doctor", "preflight", "diagnostic"],
  ui: ["ui", "html", "interface", "dashboard", "settings page", "mission control"],
  feature: ["feature", "ajout", "ajouter", "amelioration", "amélioration", "suggestion", "idee", "idée", "wish", "roadmap", "fonctionnalite", "fonctionnalité", "integration", "intégration", "plugin", "extension", "faisable", "possible", "supporte", "compatibilite", "compatibilité", "demande", "implementer", "implémenter", "nouveau", "manque", "besoin"],
};

const TYPO_REPLACEMENTS = [
  [/ph/g, "f"],
  [/qu/g, "k"],
  [/ck/g, "k"],
  [/tion/g, "sion"],
  [/eau/g, "o"],
  [/ai/g, "e"],
  [/oi/g, "wa"],
];

const KEYBOARD_NEIGHBORS = {
  a: ["s", "q", "z"],
  e: ["r", "w", "d"],
  i: ["o", "u", "k"],
  o: ["i", "p", "l"],
  u: ["y", "i", "j"],
  s: ["a", "d", "w"],
  r: ["e", "t", "f"],
  n: ["b", "m", "h"],
  m: ["n", "j", "k"],
};

export function stripDiacritics(text) {
  return text.normalize("NFD").replace(/\p{M}/gu, "");
}

export function normalizeToken(raw) {
  return stripDiacritics(String(raw).toLowerCase())
    .replace(/[''`]/g, "")
    .replace(/[^a-z0-9._-]+/g, " ")
    .trim();
}

function dropVowel(token) {
  if (token.length < 5) return token;
  return token.replace(/[aeiouy]/g, "");
}

function keyboardTypos(token) {
  const out = new Set();
  if (token.length < 4) return out;
  for (let i = 0; i < token.length; i++) {
    const c = token[i];
    const neighbors = KEYBOARD_NEIGHBORS[c];
    if (!neighbors) continue;
    for (const n of neighbors) {
      out.add(token.slice(0, i) + n + token.slice(i + 1));
    }
  }
  return out;
}

function typoVariants(token) {
  const variants = new Set([token]);
  if (token.length >= 4) {
    variants.add(token.slice(0, -1));
    variants.add(token + token.at(-1));
    variants.add(dropVowel(token));
  }
  let base = token;
  for (const [re, rep] of TYPO_REPLACEMENTS) {
    if (re.test(base)) variants.add(base.replace(re, rep));
  }
  for (const kt of keyboardTypos(token)) variants.add(kt);
  return [...variants].filter((v) => v.length >= 3);
}

function topicHits(text) {
  const norm = normalizeToken(text);
  const hits = new Set();
  for (const [topic, words] of Object.entries(TOPIC_SYNONYMS)) {
    for (const w of words) {
      const nw = normalizeToken(w);
      if (norm.includes(nw)) hits.add(topic);
    }
  }
  return hits;
}

export function expandTextKeywords(text) {
  const tokens = normalizeToken(text).split(/\s+/).filter(Boolean);
  const expanded = new Set();
  for (const t of tokens) {
    if (t.length < 2 || STOP.has(t)) continue;
    expanded.add(t);
    for (const v of typoVariants(t)) expanded.add(v);
  }
  for (const topic of topicHits(text)) {
    for (const w of TOPIC_SYNONYMS[topic]) {
      expanded.add(normalizeToken(w));
      for (const v of typoVariants(normalizeToken(w))) expanded.add(v);
    }
  }
  return [...expanded];
}

export function expandQuery(query) {
  const base = expandTextKeywords(query);
  const topics = topicHits(query);
  for (const topic of topics) {
    for (const w of TOPIC_SYNONYMS[topic]) {
      base.push(normalizeToken(w));
      base.push(...typoVariants(normalizeToken(w)));
    }
  }
  return [...new Set(base)].filter((t) => t.length >= 2 && !STOP.has(t));
}

export function ftsMatchTerms(terms) {
  const safe = terms
    .map((t) => t.replace(/["'*]/g, ""))
    .filter((t) => t.length >= 2)
    .slice(0, 40);
  if (!safe.length) return "";
  return safe.map((t) => `"${t}"`).join(" OR ");
}

export { TOPIC_SYNONYMS };
