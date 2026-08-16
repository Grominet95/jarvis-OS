import { expandQuery, ftsMatchTerms, normalizeToken, TOPIC_SYNONYMS } from "./keywords.js";
import { errorCodesToContextRows, extractJrvCodes, lookupErrorCodes } from "./errorLookup.js";

const CHARS_PER_TOKEN = 3.5;

export function estimateDocTokens(text) {
  return Math.ceil(text.length / CHARS_PER_TOKEN);
}

export function detectKeywordTopics(query) {
  const norm = normalizeToken(query);
  const topics = new Set();
  for (const [topic, words] of Object.entries(TOPIC_SYNONYMS)) {
    for (const w of words) {
      if (norm.includes(normalizeToken(w))) topics.add(topic);
    }
  }
  return topics;
}

export function routerTopicsToKeywordSet(topics = []) {
  const s = new Set();
  for (const t of topics) {
    if (t === "install") s.add("setup");
    if (t === "api_keys") {
      s.add("env");
      s.add("llm");
    }
    if (t === "error") s.add("error");
    if (t === "voice") s.add("voice");
    if (t === "run") s.add("run");
    if (t === "feature_request") s.add("feature");
  }
  return s;
}

function rerankScore(row, topics) {
  let score = row.rank;
  const p = row.doc_path;
  if (p.startsWith("playbooks/")) score -= 5;
  if (p.startsWith("playbooks/error-catalog")) score -= 8;
  if (p.startsWith("09-operations/error-codes") && topics.has("error")) score -= 10;
  if (p.startsWith("09-operations/troubleshooting") && topics.has("error")) score -= 4;
  if (p.startsWith("01-entry-points/") && (topics.has("setup") || topics.has("run"))) score -= 3;
  if (p.startsWith("maps/process-map") && topics.has("setup")) score -= 2;
  if (p.startsWith("06-interfaces/voice") && topics.has("voice")) score -= 4;
  if (p.startsWith("07-config/env-reference") && topics.has("env")) score -= 3;
  if (p.startsWith("05-engine/budget") && (topics.has("error") || topics.has("llm"))) score -= 3;
  if (p.startsWith("05-engine/gateway") && topics.has("gateway")) score -= 3;
  if (p.includes("/modules/") || /\/(0[3-6]-[^/]+\/[^/]+\/[^/]+\.md)$/.test(p)) score += 2;
  if (p === "MAINTENANCE.md" || p === "AI_INSTRUCTIONS.md") score += 3;
  return score;
}

function chunkMatchesQuery(body, terms) {
  const norm = body.toLowerCase();
  let hits = 0;
  for (const t of terms) {
    if (t.length >= 4 && norm.includes(t)) hits++;
  }
  return hits;
}

function isModuleCard(body) {
  return body.includes("**Layer:**") && body.includes("**Source of truth:**");
}

function isUserFacing(topics) {
  return (
    topics.has("setup") ||
    topics.has("run") ||
    topics.has("error") ||
    topics.has("voice") ||
    topics.has("env") ||
    topics.has("llm")
  );
}

export function searchDocs(db, query, options = {}) {
  const limit = options.limit ?? 24;
  const terms = expandQuery(query);
  const match = ftsMatchTerms(terms);
  if (!match) return [];

  const sql = `
    SELECT
      c.id,
      d.path AS doc_path,
      d.title AS doc_title,
      d.priority,
      c.section_title,
      c.body,
      bm25(chunks_fts) AS rank
    FROM chunks_fts
    JOIN chunks c ON c.id = chunks_fts.rowid
    JOIN docs d ON d.id = c.doc_id
    WHERE chunks_fts MATCH ?
    ORDER BY rank ASC, d.priority DESC
    LIMIT ?
  `;

  let rows;
  try {
    rows = db.prepare(sql).all(match, limit * 2);
  } catch {
    const fallback = terms.slice(0, 8).map((t) => `"${t}"`).join(" OR ");
    rows = db.prepare(sql).all(fallback, limit * 2);
  }

  const keywordTopics =
    options.topics instanceof Set
      ? options.topics
      : routerTopicsToKeywordSet(options.topics || []);
  for (const t of detectKeywordTopics(query)) keywordTopics.add(t);

  const strong = terms.filter((t) => t.length >= 5);
  const userFacing = isUserFacing(keywordTopics);
  const allowModuleCards = options.allowModuleCards ?? !userFacing;

  return rows
    .filter((row) => {
      if (row.rank > 5) return false;
      if (userFacing && !allowModuleCards && isModuleCard(row.body)) return false;
      if (userFacing && (row.doc_path === "MAINTENANCE.md" || row.doc_path === "AI_INSTRUCTIONS.md")) {
        return false;
      }
      if (!strong.length) return chunkMatchesQuery(row.body, terms) > 0;
      return chunkMatchesQuery(row.body, strong) > 0 || chunkMatchesQuery(row.body, terms) >= 2;
    })
    .map((row) => ({ ...row, rerank: rerankScore(row, keywordTopics) }))
    .sort((a, b) => a.rerank - b.rerank || b.priority - a.priority)
    .slice(0, limit);
}

export function relatedFromLinks(db, docPaths, limit = 8) {
  if (!docPaths.length) return [];
  const placeholders = docPaths.map(() => "?").join(",");
  const sql = `
    SELECT DISTINCT dl.to_path AS doc_path, d.title AS doc_title, c.section_title, c.body, d.priority
    FROM doc_links dl
    JOIN docs d ON d.path = dl.to_path
    JOIN chunks c ON c.doc_id = d.id
    WHERE dl.from_path IN (${placeholders})
    ORDER BY d.priority DESC, c.id ASC
    LIMIT ?
  `;
  return db.prepare(sql).all(...docPaths, limit);
}

export function fetchDocChunks(db, docPaths, limit = 6) {
  if (!docPaths.length) return [];
  const placeholders = docPaths.map(() => "?").join(",");
  const sql = `
    SELECT d.path AS doc_path, d.title AS doc_title, c.section_title, c.body, d.priority
    FROM docs d
    JOIN chunks c ON c.doc_id = d.id
    WHERE d.path IN (${placeholders})
    ORDER BY d.priority DESC, c.id ASC
    LIMIT ?
  `;
  return db.prepare(sql).all(...docPaths, limit);
}

export function buildDocContext(rows, related, symbolRows, maxChars, tagPrefix = "") {
  const usedDocs = new Map();
  const blocks = [];
  let used = 0;

  const pushBlock = (row, tag) => {
    const header = `### [${tag}] ${row.doc_path} — ${row.section_title}\n`;
    const snippet = row.body.trim().slice(0, 900);
    const block = `${header}${snippet}\n`;
    const perDoc = usedDocs.get(row.doc_path) || 0;
    if (perDoc >= 2) return false;
    if (used + block.length > maxChars) return false;
    blocks.push({ tag, block, path: row.doc_path, section: row.section_title });
    usedDocs.set(row.doc_path, perDoc + 1);
    used += block.length;
    return true;
  };

  for (const row of symbolRows || []) {
    if (!pushBlock(row, `${tagPrefix}symbol`.trim() || "symbol")) break;
  }

  for (const row of rows) {
    if (!pushBlock(row, `${tagPrefix}doc`.trim() || "doc")) break;
  }

  for (const row of related || []) {
    if (used >= maxChars) break;
    pushBlock(row, `${tagPrefix}related`.trim() || "related");
  }

  const text = blocks.map((b) => b.block).join("\n");
  return {
    text,
    charCount: used,
    tokenEstimate: estimateDocTokens(text),
    sources: blocks.map((b) => b.path),
  };
}

export function queryDocContext(db, query, options = {}) {
  const maxChars =
    options.maxChars ?? Math.floor((options.maxTokens ?? 1000) * CHARS_PER_TOKEN);
  const jrvCodes = extractJrvCodes(query);
  const errorRows = errorCodesToContextRows(lookupErrorCodes(db, jrvCodes));
  const hits = searchDocs(db, query, options);
  const mergedHits = [...errorRows, ...hits.filter((h) => !jrvCodes.includes(h.section_title?.toUpperCase?.()))];
  const topPaths = [...new Set(mergedHits.slice(0, 5).map((h) => h.doc_path))];
  const symbolPaths = options.symbolPaths || [];
  const related = relatedFromLinks(db, [...topPaths, ...symbolPaths], options.relatedLimit ?? 8);
  const symbolRows = symbolPaths.length ? fetchDocChunks(db, symbolPaths, 6) : [];
  return buildDocContext(mergedHits, related, symbolRows, maxChars);
}
