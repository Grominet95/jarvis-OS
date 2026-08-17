#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import Database from "better-sqlite3";
import { expandTextKeywords } from "./keywords.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../..");
const DOC_ROOT = path.join(REPO_ROOT, "Documentation_Helper");
const DB_PATH = path.join(DOC_ROOT, "doc_index.sqlite");
const ERROR_CODES_JSON = path.join(REPO_ROOT, "scripts", "doc_helper", "error_codes.json");

function walkMarkdown(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walkMarkdown(full));
    else if (entry.name.endsWith(".md")) out.push(full);
  }
  return out;
}

function relDoc(fullPath) {
  return path.relative(DOC_ROOT, fullPath).replace(/\\/g, "/");
}

function splitSections(content) {
  const lines = content.split(/\r?\n/);
  const sections = [];
  let currentTitle = "(intro)";
  let buf = [];

  const flush = () => {
    const body = buf.join("\n").trim();
    if (body) sections.push({ title: currentTitle, body });
    buf = [];
  };

  for (const line of lines) {
    const h2 = line.match(/^##\s+(.+)/);
    const h1 = line.match(/^#\s+(.+)/);
    if (h2 || (h1 && currentTitle !== "(intro)")) {
      flush();
      currentTitle = (h2 || h1)[1].trim();
      continue;
    }
    if (h1 && currentTitle === "(intro)") {
      currentTitle = h1[1].trim();
      continue;
    }
    buf.push(line);
  }
  flush();
  return sections.length ? sections : [{ title: "(document)", body: content.trim() }];
}

function extractLinks(content, fromPath) {
  const links = [];
  const re = /\[([^\]]*)\]\(([^)]+)\)/g;
  let m;
  while ((m = re.exec(content))) {
    const target = m[2].split("#")[0].trim();
    if (!target || target.startsWith("http")) continue;
    const resolved = path.normalize(path.join(path.dirname(fromPath), target)).replace(/\\/g, "/");
    const rel = path.relative(DOC_ROOT, resolved).replace(/\\/g, "/");
    if (!rel.startsWith("..")) links.push(rel);
  }
  return [...new Set(links)];
}

function priorityScore(relPath) {
  if (relPath === "INDEX.md") return 100;
  if (relPath.startsWith("playbooks/error-catalog")) return 98;
  if (relPath.startsWith("09-operations/error-codes")) return 97;
  if (relPath.startsWith("playbooks/")) return 96;
  if (relPath.startsWith("09-operations/troubleshooting")) return 95;
  if (relPath.startsWith("01-entry-points/")) return 90;
  if (relPath.startsWith("07-config/env-reference")) return 88;
  if (relPath.startsWith("maps/process-map")) return 85;
  if (relPath.includes("overview.md") || relPath.includes("-flow.md")) return 80;
  if (relPath.startsWith("08-integrations/")) return 75;
  if (relPath.startsWith("02-kernel/modules/")) return 40;
  if (relPath.startsWith("06-interfaces/api/")) return 45;
  return 55;
}

function loadErrorCodesJson() {
  if (!fs.existsSync(ERROR_CODES_JSON)) return {};
  try {
    return JSON.parse(fs.readFileSync(ERROR_CODES_JSON, "utf8"));
  } catch {
    console.warn(`Warning: could not parse ${ERROR_CODES_JSON}`);
    return {};
  }
}

function indexErrorCodes(db) {
  const raw = loadErrorCodesJson();
  const codes = Object.keys(raw).sort();
  if (!codes.length) {
    console.warn("No error_codes.json entries — run generate_docs.py first");
    return 0;
  }

  const insert = db.prepare(`
    INSERT INTO error_codes (
      code, domain, severity, title_fr, message_fr, resolution_fr, docs, since, modules
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);

  let count = 0;
  for (const code of codes) {
    const spec = raw[code] || {};
    const docs = (spec.docs || []).join("|");
    const modules = (spec.modules || []).join("|");
    insert.run(
      code,
      spec.domain || "",
      spec.severity || "error",
      spec.title_fr || "",
      spec.message_fr || "",
      spec.resolution_fr || "",
      docs,
      spec.since || "",
      modules
    );
    count++;
  }
  return count;
}

function build() {
  if (!fs.existsSync(DOC_ROOT)) {
    console.error("Documentation_Helper/ not found. Run doc generation first.");
    process.exit(1);
  }

  if (fs.existsSync(DB_PATH)) fs.unlinkSync(DB_PATH);

  const db = new Database(DB_PATH);
  db.pragma("journal_mode = WAL");

  db.exec(`
    CREATE TABLE docs (
      id INTEGER PRIMARY KEY,
      path TEXT UNIQUE NOT NULL,
      title TEXT,
      priority INTEGER NOT NULL DEFAULT 50
    );

    CREATE TABLE chunks (
      id INTEGER PRIMARY KEY,
      doc_id INTEGER NOT NULL REFERENCES docs(id),
      section_title TEXT NOT NULL,
      body TEXT NOT NULL,
      keywords TEXT NOT NULL,
      char_count INTEGER NOT NULL
    );

    CREATE VIRTUAL TABLE chunks_fts USING fts5(
      section_title,
      body,
      keywords,
      content='chunks',
      content_rowid='id',
      tokenize='unicode61 remove_diacritics 2'
    );

    CREATE TABLE doc_links (
      from_path TEXT NOT NULL,
      to_path TEXT NOT NULL,
      UNIQUE(from_path, to_path)
    );

    CREATE TABLE error_codes (
      code TEXT PRIMARY KEY,
      domain TEXT NOT NULL,
      severity TEXT NOT NULL,
      title_fr TEXT NOT NULL,
      message_fr TEXT NOT NULL,
      resolution_fr TEXT NOT NULL,
      docs TEXT NOT NULL DEFAULT '',
      since TEXT NOT NULL DEFAULT '',
      modules TEXT NOT NULL DEFAULT ''
    );

    CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
      INSERT INTO chunks_fts(rowid, section_title, body, keywords)
      VALUES (new.id, new.section_title, new.body, new.keywords);
    END;

    CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
      INSERT INTO chunks_fts(chunks_fts, rowid, section_title, body, keywords)
      VALUES ('delete', old.id, old.section_title, old.body, old.keywords);
    END;

    CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
      INSERT INTO chunks_fts(chunks_fts, rowid, section_title, body, keywords)
      VALUES ('delete', old.id, old.section_title, old.body, old.keywords);
      INSERT INTO chunks_fts(rowid, section_title, body, keywords)
      VALUES (new.id, new.section_title, new.body, new.keywords);
    END;
  `);

  const insertDoc = db.prepare("INSERT INTO docs (path, title, priority) VALUES (?, ?, ?)");
  const insertChunk = db.prepare(
    "INSERT INTO chunks (doc_id, section_title, body, keywords, char_count) VALUES (?, ?, ?, ?, ?)"
  );
  const insertLink = db.prepare(
    "INSERT OR IGNORE INTO doc_links (from_path, to_path) VALUES (?, ?)"
  );

  const files = walkMarkdown(DOC_ROOT).filter((f) => !f.endsWith("doc_index.sqlite"));
  let chunkCount = 0;
  let linkCount = 0;

  const tx = db.transaction(() => {
    for (const file of files) {
      const rel = relDoc(file);
      const raw = fs.readFileSync(file, "utf8");
      const titleMatch = raw.match(/^#\s+(.+)/m);
      const title = titleMatch ? titleMatch[1].trim() : rel;
      const priority = priorityScore(rel);
      const docResult = insertDoc.run(rel, title, priority);
      const docId = docResult.lastInsertRowid;

      for (const link of extractLinks(raw, file)) {
        insertLink.run(rel, link);
        linkCount++;
      }

      for (const section of splitSections(raw)) {
        const searchable = `${title}\n${section.title}\n${section.body}`;
        const keywords = expandTextKeywords(searchable).join(" ");
        insertChunk.run(
          docId,
          section.title,
          section.body,
          keywords,
          section.body.length
        );
        chunkCount++;
      }
    }
  });

  tx();
  const errorCount = indexErrorCodes(db);
  db.close();

  console.log(`Indexed ${files.length} docs, ${chunkCount} chunks, ${linkCount} links`);
  console.log(`Indexed ${errorCount} JRV error codes`);
  console.log(`SQLite FTS5: ${DB_PATH}`);
}

build();
