# Error catalog — diagnostic routing

Source: community threads + ops docs. Last reviewed: 2026-08-16.

Terminal format: `[JRV-XXX-NNN] ERROR|WARN: message` — full reference in `09-operations/error-codes.md`.

| Code | Symptom / log line | Likely area | First docs |
|------|--------------------|-------------|------------|
| JRV-LLM-001 | `429 Too Many Requests` | LLM API rate limit | `07-config/env-reference.md`, `05-engine/budget.md`, `playbooks/api-keys.md` |
| JRV-BGT-001 | `BudgetGuard exceeded` | Usage budget | `05-engine/budget.md`, `07-config/env-reference.md` |
| JRV-GWY-001 / JRV-LLM-002 | `API timeout` / chat silent | Gateway / LLM backend | `05-engine/gateway.md`, `playbooks/api-keys.md` |
| JRV-VOI-001 | `Connection refused localhost:7880` | LiveKit local | `06-interfaces/voice-livekit.md`, `01-entry-points/run-flow.md` |
| JRV-VOI-002 | `track publish timeout` | Voice pipeline / LiveKit | `06-interfaces/voice-livekit.md`, `09-operations/logs-and-doctor.md` |
| JRV-TOL-002 | Spotify tool / auth fail | Spotify tool | `04-capabilities/tools/spotify.md` |
| JRV-TOL-003 | Gmail read/send fail | Gmail tool | `04-capabilities/tools/gmail.md` |
| JRV-TOL-004 | Browser page load fail | Browser tool | `04-capabilities/tools/browser.md` |
| JRV-TOL-005 | Notion API fail | Notion tool | `04-capabilities/tools/notion.md` |
| JRV-TOL-007 | CLI whitelist fail | CLI tool | `04-capabilities/tools/cli.md` |
| JRV-API-002 | HTTP 401 Bearer | API auth | `05-engine/auth.md` |
| JRV-API-003 | HTTP 404 resource | API routes | `06-interfaces/api/` |
| JRV-API-005 | HTTP 503 service down | Bootstrap / subsystem | `09-operations/troubleshooting.md` |
| JRV-SET-001 | Wizard `:8765` unreachable | Setup / bundle | `playbooks/install-windows.md`, `01-entry-points/setup-flow.md` |
| JRV-LLM-004 | Ollama / tool loop local | LLM local provider | `03-providers/llm/local.md`, `05-engine/gateway.md` |
| JRV-KRN-001 / JRV-KRN-012 | OneDrive / sync path errors | Paths guard | `playbooks/install-windows.md`, `02-kernel/paths-and-layout.md` |
| JRV-KRN-010 | Port already in use | Preflight | `01-entry-points/run-flow.md` |
| JRV-MSG-002 | Telegram bot offline | Channels | `06-interfaces/channels/telegram.md` |
| JRV-MSG-003 | Discord bot offline | Channels | `06-interfaces/channels/discord.md` |
| JRV-PRO-001 / JRV-PRO-003 | Proactive collector offline | Proactive | `05-engine/proactive/overview.md` |
| JRV-UNK-001 | Uncaught Python exception | Unknown | `09-operations/logs-and-doctor.md` |

## Diagnostic order (official)

1. Confirm **official** clone `https://github.com/Grominet95/jarvis-OS` — not fork/beta.
2. Note the `[JRV-...]` code from terminal or `%TEMP%\jarvis\api.log`.
3. Look up the code in `09-operations/error-codes.md`.
4. Cross-check `.env` keys for the failing layer (`07-config/env-reference.md`).

## Related docs

- [error-codes.md](../09-operations/error-codes.md)
- [error-codes-contributor-guide.md](../09-operations/error-codes-contributor-guide.md)
- [error-collector-guide.md](../00-meta/error-collector-guide.md)
- [error-codes-ai-instructions.md](../00-meta/error-codes-ai-instructions.md)
- [troubleshooting.md](../09-operations/troubleshooting.md)
- [logs-and-doctor.md](../09-operations/logs-and-doctor.md)
