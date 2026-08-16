#!/usr/bin/env node
import path from "node:path";
import { fileURLToPath } from "node:url";
import Database from "better-sqlite3";
import { queryDocContext } from "./docSearch.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../..");
const DB_PATH = path.join(REPO_ROOT, "Documentation_Helper", "doc_index.sqlite");

const DEFAULT_MAX_CHARS = 3500;
const CHARS_PER_TOKEN = 3.5;

function parseArgs(argv) {
  const args = { query: "", maxChars: DEFAULT_MAX_CHARS, json: false };
  const rest = [];
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--json") args.json = true;
    else if (a === "--max-chars") args.maxChars = Number(argv[++i]) || DEFAULT_MAX_CHARS;
    else if (a === "--max-tokens") {
      const tokens = Number(argv[++i]) || 1000;
      args.maxChars = Math.floor(tokens * CHARS_PER_TOKEN);
    } else rest.push(a);
  }
  args.query = rest.join(" ").trim();
  return args;
}

function main() {
  const args = parseArgs(process.argv);
  if (!args.query) {
    console.error("Usage: node query_context.js [--max-tokens 1000] [--json] <question>");
    process.exit(1);
  }

  const db = new Database(DB_PATH, { readonly: true });
  const ctx = queryDocContext(db, args.query, { maxChars: args.maxChars });
  db.close();

  if (args.json) {
    console.log(JSON.stringify({ query: args.query, ...ctx }, null, 2));
    return;
  }

  console.log(`# Doc context (~${ctx.tokenEstimate} tokens, ${ctx.charCount} chars)\n`);
  console.log(ctx.text || "(no matches — try broader terms)");
  if (ctx.sources.length) {
    console.log("\n---\nSources:");
    for (const s of [...new Set(ctx.sources)]) {
      console.log(`- ${s}`);
    }
  }
}

main();
