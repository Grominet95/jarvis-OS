# Feature requests and improvements — evaluation guide

Source: jarvis-OS architecture docs + README. Last reviewed: 2026-08-15.

Use this playbook when users ask to add, improve, integrate, or extend Jarvis OS.

## Response format (mandatory)

1. **Rephrase** the request in one sentence.
2. **Status today** — already exists / partial / missing / workaround exists.
3. **Feasibility** — one of: `Facile` | `Moyen` | `Difficile` | `Hors scope`.
4. **Why** — 2–4 bullets (architecture layer, deps, governance, self-hosted constraint).
5. **Best path** — config only | skill | new tool | integration | GitHub issue | mission/skill lab.
6. **What to send** — screenshot, use case, API docs link (no random internet search).

Never promise dates or "coming soon". Never invent features not listed below.

## What Jarvis OS already supports

### Core (built-in)

| Area | Capability |
|------|------------|
| Voice | LiveKit local, STT (Deepgram/Whisper), TTS (ElevenLabs/Piper) |
| Chat | FastAPI gateway, sessions, multi-LLM (Anthropic, Mistral, OpenAI, Ollama, Gemini) |
| Memory | SQLite kernel, topics, facts, cross-session recall, mirror markdown |
| Proactive | Briefings, initiatives (autonomy 0–5), Command Center, curator |
| Mission | Orchestrator, worker agents, verifier, Docker executor (optional) |
| Governance | Approvals, permissions whitelist, budget guard, audit |

### Tools (agent-callable, L1 capabilities)

weather, browser, vision (YOLO + visual memory), filesystem (read/find in allowed roots), CLI runner, Gmail list, Google Calendar list/create, Notion tasks, Spotify, memory read/write/search, cross-session recall, show_view (UI), presets, subagent spawn, script RPC, skill create/improve/list, report missing capability.

Skills from [jarvis-skills](https://github.com/Grominet95/jarvis-skills) extend tools at runtime (ABI, lifecycle, Skill Lab sandbox).

### Integrations (env keys required)

LiveKit, Deepgram, ElevenLabs, Anthropic, OpenAI, Google (Gemini/Calendar/Gmail), Spotify, Deezer, Notion, Telegram, Discord, Mapbox/MapTiler.

See `08-integrations/index.md` and `07-config/env-reference.md`.

## Feasibility rubric

| Label | Meaning | Typical effort |
|-------|---------|----------------|
| **Facile** | Config / `.env` / wizard / enable existing integration / install published skill | Minutes to hours (user) |
| **Moyen** | New skill (jarvis-skills), prompt/routine tweak, permissions entry, small L1 tool following patterns | Hours to days (dev) |
| **Difficile** | New L1 tool + bootstrap wiring + tests + import-linter; new external API with OAuth; voice pipeline change; mission backend | Days to weeks |
| **Hors scope** | Breaks self-hosted/local-first; needs cloud-only SaaS with no API; violates layer rules (L0→L3); replaces core kernel; unsupported OS without bundle work; legal/ToS grey area |

## Decision tree

```
User request
├─ Already a tool/integration? → point to env + doc, mark Facile
├─ Similar skill exists on jarvis-skills? → install skill, Facile–Moyen
├─ "Automate X on my PC" with CLI/API? → skill or CLI tool, Moyen
├─ New web service with public API? → new tool + integration sheet, Difficile
├─ UI/dashboard change? → show_view / Command Center / issue, Moyen–Difficile
├─ Voice/mic/LiveKit? → voice playbook, usually config not new feature
├─ "Jarvis should do everything like Alexa/Google Home" → partial; explain local + tools limit, Moyen–Hors scope
└─ Unclear → ask use case + frequency + data/API available; suggest GitHub issue
```

## Common request patterns

| Request type | Verdict guidance |
|--------------|------------------|
| New music service | Deezer/Spotify exist; other APIs = Difficile new provider |
| Home Assistant / domotique | Proactive collector exists (`home_assistant`); extend collector = Moyen |
| WhatsApp / SMS | No native module; third-party API + governance = Difficile, ToS risk |
| Windows app control | CLI tool or skill if app has CLI; UI automation = Moyen–Difficile |
| Mobile app | Telegram channel exists; native mobile app = Hors scope (use web UI) |
| Better memory / remember X | Memory kernel exists; tuning ingest/topics = Facile–Moyen |
| Auto-install packages | Capability engine + Skill Lab; user approval required |
| Plugin store | jarvis-skills + ClawHub mapping; not arbitrary binary plugins |
| Multi-user / SaaS hosting | Personal assistant design; multi-tenant = Hors scope |
| Offline LLM | Ollama backend supported = Facile (config) |
| Custom voice | ElevenLabs voice ID / Piper = Facile |
| Browser automation for site X | Browser tool exists; fragile selectors = Moyen |
| Print / filesystem / Notion | Tools exist = Facile if keys configured |

## Extension paths (official)

1. **Config only** — `.env`, `config/tools.yaml`, `config/permissions.yaml`, setup wizard.
2. **Skill** — [jarvis-skills](https://github.com/Grominet95/jarvis-skills) repo; ABI in `docs/architecture/skills-abi.md`.
3. **Skill Lab** — generate/test in sandbox (Docker optional); human validates before install.
4. **New tool** — `capabilities/tools/*.py`, register in `bootstrap.py`, tests, import-linter L1 rules.
5. **GitHub issue** — https://github.com/Grominet95/jarvis-OS/issues for core features.

## What NOT to suggest

- Downloading from Discord or unofficial zips for core OS changes.
- Forking without understanding layer architecture (L0 kernel ← L1 providers/capabilities ← L2 engine ← L3 interfaces).
- Disabling governance/approvals for convenience.
- pip install random packages into user bundle without skill/tool path.

## Community context

Discord threads may mention desired features. Use them as **signal of demand**, not as spec. Cross-check with this playbook and official docs before stating something is planned.
