#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { TOPIC_SYNONYMS } from "./keywords.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../..");
const DOC_ROOT = path.join(REPO_ROOT, "Documentation_Helper");

const TOPIC_DOC_LINKS = {
  setup: [
    "01-entry-points/setup-flow.md",
    "01-entry-points/windows-launchers.md",
    "02-kernel/bundle-offline.md",
    "maps/process-map.md",
    "07-config/env-reference.md",
  ],
  run: [
    "01-entry-points/run-flow.md",
    "01-entry-points/windows-launchers.md",
    "09-operations/logs-and-doctor.md",
    "maps/process-map.md",
  ],
  bundle: [
    "02-kernel/bundle-offline.md",
    "01-entry-points/setup-flow.md",
    "09-operations/troubleshooting.md",
    "09-operations/release-and-bundle.md",
  ],
  onedrive: [
    "09-operations/troubleshooting.md",
    "01-entry-points/windows-launchers.md",
    "01-entry-points/setup-flow.md",
  ],
  voice: [
    "06-interfaces/voice-livekit.md",
    "08-integrations/sheets/livekit.md",
    "08-integrations/sheets/deepgram.md",
    "08-integrations/sheets/elevenlabs.md",
    "07-config/env-reference.md",
  ],
  livekit: [
    "06-interfaces/voice-livekit.md",
    "08-integrations/sheets/livekit.md",
    "09-operations/troubleshooting.md",
  ],
  memory: [
    "03-providers/memory/memory-flow.md",
    "03-providers/overview.md",
    "04-capabilities/tools/memory.md",
    "07-config/env-reference.md",
  ],
  api: [
    "maps/route-map.md",
    "06-interfaces/api/overview.md",
    "06-interfaces/overview.md",
  ],
  env: [
    "07-config/env-reference.md",
    "07-config/runtime-config-files.md",
    "02-kernel/settings-and-env.md",
  ],
  tool: [
    "04-capabilities/tools-overview.md",
    "04-capabilities/tools-registry.md",
    "05-engine/mission/capability_engine.md",
  ],
  skill: [
    "04-capabilities/skills/abi.md",
    "docs/architecture/skills-abi.md",
    "04-capabilities/tools/skills.md",
  ],
  mission: [
    "05-engine/mission/overview.md",
    "05-engine/mission/backends.md",
    "05-engine/mission/orchestrator.md",
  ],
  proactive: [
    "05-engine/proactive/overview.md",
    "05-engine/proactive/engine.md",
    "08-integrations/index.md",
  ],
  gateway: [
    "05-engine/gateway-and-agent.md",
    "05-engine/overview.md",
    "06-interfaces/overview.md",
  ],
  error: [
    "09-operations/error-codes.md",
    "playbooks/error-catalog.md",
    "00-meta/error-collector-guide.md",
    "09-operations/troubleshooting.md",
    "09-operations/logs-and-doctor.md",
    "02-kernel/modules/preflight.md",
  ],
  kernel: [
    "02-kernel/overview.md",
    "02-kernel/settings-and-env.md",
    "02-kernel/events-bus.md",
    "00-meta/architecture-layers.md",
  ],
  llm: [
    "03-providers/llm/factory.md",
    "07-config/env-reference.md",
    "08-integrations/sheets/anthropic.md",
    "08-integrations/sheets/openai.md",
  ],
  telegram: ["06-interfaces/channels-messaging.md", "08-integrations/sheets/telegram.md"],
  discord: ["06-interfaces/channels-messaging.md", "08-integrations/sheets/discord.md"],
  spotify: ["08-integrations/sheets/spotify.md", "08-integrations/sheets/deezer.md", "maps/route-map.md"],
  google: ["08-integrations/sheets/google.md", "07-config/env-reference.md"],
  docker: ["01-entry-points/docker.md", "05-engine/mission/docker.md", "05-engine/mission/backends.md"],
  test: ["10-testing/pytest-and-ci.md", "10-testing/validation-scripts.md"],
  logs: ["09-operations/logs-and-doctor.md", "09-operations/troubleshooting.md"],
  ui: ["06-interfaces/ui/home.md", "06-interfaces/ui/settings.md", "06-interfaces/overview.md"],
};

const PREFIX_LINKS = {
  "00-meta/": ["INDEX.md", "00-meta/architecture-layers.md", "00-meta/bootstrap-wiring.md", "maps/process-map.md"],
  "01-entry-points/": ["maps/process-map.md", "09-operations/troubleshooting.md", "07-config/env-reference.md"],
  "02-kernel/": ["02-kernel/overview.md", "07-config/env-reference.md", "00-meta/architecture-layers.md"],
  "03-providers/": ["03-providers/overview.md", "00-meta/architecture-layers.md"],
  "03-providers/memory/": ["03-providers/memory/memory-flow.md", "04-capabilities/tools/memory.md"],
  "04-capabilities/": ["04-capabilities/tools-registry.md", "05-engine/gateway-and-agent.md"],
  "05-engine/": ["05-engine/overview.md", "05-engine/gateway-and-agent.md", "00-meta/bootstrap-wiring.md"],
  "05-engine/mission/": ["05-engine/mission/overview.md", "05-engine/mission/backends.md"],
  "05-engine/proactive/": ["05-engine/proactive/overview.md", "08-integrations/index.md"],
  "06-interfaces/": ["06-interfaces/overview.md", "maps/route-map.md"],
  "07-config/": ["07-config/env-reference.md", "02-kernel/settings-and-env.md"],
  "08-integrations/": ["08-integrations/index.md", "07-config/env-reference.md"],
  "09-operations/": ["09-operations/troubleshooting.md", "09-operations/logs-and-doctor.md", "INDEX.md"],
  "10-testing/": ["10-testing/pytest-and-ci.md", "10-testing/validation-scripts.md"],
};

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

function linkPath(fromRel, toRel) {
  const fromDir = path.dirname(fromRel);
  let href = path.relative(fromDir, toRel).replace(/\\/g, "/");
  if (!href.startsWith(".") && !href.startsWith("/")) href = `./${href}`;
  const label = toRel.replace(/\.md$/, "").split("/").pop();
  return `[${label}](${href})`;
}

function topicsForPath(rel) {
  const topics = new Set();
  for (const [topic, words] of Object.entries(TOPIC_SYNONYMS)) {
    const blob = `${rel} ${words.join(" ")}`.toLowerCase();
    if (blob.includes(topic)) topics.add(topic);
    for (const w of words) {
      if (rel.toLowerCase().includes(w.replace(/\s+/g, ""))) topics.add(topic);
    }
  }
  if (rel.includes("setup")) topics.add("setup");
  if (rel.includes("run-flow")) topics.add("run");
  if (rel.includes("voice")) topics.add("voice");
  if (rel.includes("memory")) topics.add("memory");
  if (rel.includes("troubleshoot")) topics.add("error");
  if (rel.includes("env-reference")) topics.add("env");
  if (rel.includes("mission")) topics.add("mission");
  if (rel.includes("proactive")) topics.add("proactive");
  if (rel.includes("tool")) topics.add("tool");
  if (rel.includes("skill")) topics.add("skill");
  return topics;
}

function suggestedLinks(rel) {
  const out = new Set(["INDEX.md", "AI_INSTRUCTIONS.md"]);
  for (const [prefix, links] of Object.entries(PREFIX_LINKS)) {
    if (rel.startsWith(prefix)) links.forEach((l) => out.add(l));
  }
  for (const topic of topicsForPath(rel)) {
    (TOPIC_DOC_LINKS[topic] || []).forEach((l) => out.add(l));
  }
  out.delete(rel);
  return [...out].filter((l) => fs.existsSync(path.join(DOC_ROOT, l))).slice(0, 10);
}

function upsertRelatedSection(content, rel, links) {
  if (!links.length) return content;
  const lines = links.map((l) => `- ${linkPath(rel, l)}`);
  const block = `## Related docs\n\n${lines.join("\n")}\n`;
  if (/^## Related docs\b/m.test(content)) {
    return content.replace(/^## Related docs\b[\s\S]*?(?=^## |\Z)/m, `${block}\n`);
  }
  const marker = /\n- \*\*Last reviewed:\*\*/;
  if (marker.test(content)) {
    return content.replace(marker, `\n\n${block}\n- **Last reviewed:**`);
  }
  return `${content.trim()}\n\n${block}`;
}

function enrichIndexKeywordTable() {
  const indexPath = path.join(DOC_ROOT, "INDEX.md");
  if (!fs.existsSync(indexPath)) return;
  let content = fs.readFileSync(indexPath, "utf8");
  const section = `## Keyword search (FR / EN, typos OK)

Use the FTS index: \`npm run query -- "ta question"\` from \`scripts/doc_helper/\`.

| Keywords (FR / EN) | Doc |
|--------------------|-----|
| install, setup, instaler, configuration | [01-entry-points/setup-flow.md](01-entry-points/setup-flow.md) |
| run, demarrer, lancer, start | [01-entry-points/run-flow.md](01-entry-points/run-flow.md) |
| voix, voice, micro, livekit, vocal | [06-interfaces/voice-livekit.md](06-interfaces/voice-livekit.md) |
| memoire, memory, rappel, recall | [03-providers/memory/memory-flow.md](03-providers/memory/memory-flow.md) |
| erreur, bug, probleme, fix | [09-operations/troubleshooting.md](09-operations/troubleshooting.md) |
| env, cle, token, .env, config | [07-config/env-reference.md](07-config/env-reference.md) |
| api, route, endpoint | [maps/route-map.md](maps/route-map.md) |
| outil, tool, skill, competence | [04-capabilities/tools-registry.md](04-capabilities/tools-registry.md) |
| mission, projet, project | [05-engine/mission/overview.md](05-engine/mission/overview.md) |
| telegram, discord, message | [06-interfaces/channels-messaging.md](06-interfaces/channels-messaging.md) |
| musique, spotify, deezer | [08-integrations/index.md](08-integrations/index.md) |
| docker, sandbox | [05-engine/mission/backends.md](05-engine/mission/backends.md) |
| log, doctor, preflight | [09-operations/logs-and-doctor.md](09-operations/logs-and-doctor.md) |

Rebuild index: \`npm run build-index\` · Query ~1k tokens: \`npm run query -- --max-tokens 1000 "question"\`
`;
  if (!content.includes("## Keyword search (FR / EN")) {
    content = content.replace(/\n## Maintenance\b/, `\n${section}\n## Maintenance`);
    fs.writeFileSync(indexPath, content, "utf8");
  }
}

function main() {
  const files = walkMarkdown(DOC_ROOT).filter((f) => !f.endsWith("doc_index.sqlite"));
  let updated = 0;
  for (const file of files) {
    const rel = relDoc(file);
    if (rel === "INDEX.md") continue;
    const links = suggestedLinks(rel);
    const raw = fs.readFileSync(file, "utf8");
    const next = upsertRelatedSection(raw, rel, links);
    if (next !== raw) {
      fs.writeFileSync(file, next, "utf8");
      updated++;
    }
  }
  enrichIndexKeywordTable();
  console.log(`Enriched ${updated} docs with Related sections`);
}

main();
