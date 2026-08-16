# Channels and Messaging

Telegram, Discord, WhatsApp, Signal via `interfaces/channels/`. Unified gateway when `MESSAGING_GATEWAY_ENABLED=true`.

Cross-link: [notices/messaging-gateway.md](../../notices/messaging-gateway.md)

## JRV error lookup

| Canal | Bot | Lookup JRV |
|-------|-----|------------|
| **Telegram** (gateway Jarvis) | `interfaces/channels/telegram_bot.py` | `/error`, `/jrv`, message `JRV-XXX-NNN` via `jarvis.kernel.error_doc_lookup` |
| **Discord** (gateway Jarvis, owner DM) | `interfaces/channels/discord_bot.py` | Pas de lookup JRV — messagerie LLM uniquement |
| **Discord communauté (Le Labo)** | [Jarvis-Helper](https://github.com/Grominet95/Jarvis-Helper) | `/error`, message `JRV-XXX-NNN`, `/faq` avec code |

Rebuild SQLite côté Helper : `node scripts/sync-jrv-from-os.js <jarvis-OS>` puis `npm run build-doc-index`.

Voir [09-operations/error-codes-sqlite.md](../09-operations/error-codes-sqlite.md).


## Related docs

- [INDEX](../INDEX.md)
- [AI_INSTRUCTIONS](../AI_INSTRUCTIONS.md)
- [error-codes](../09-operations/error-codes.md)
- [error-codes-sqlite](../09-operations/error-codes-sqlite.md)
- [overview](./overview.md)
- [route-map](../maps/route-map.md)
- [setup-flow](../01-entry-points/setup-flow.md)
- [windows-launchers](../01-entry-points/windows-launchers.md)
- [bundle-offline](../02-kernel/bundle-offline.md)
- [process-map](../maps/process-map.md)
- [env-reference](../07-config/env-reference.md)
- [run-flow](../01-entry-points/run-flow.md)

- **Last reviewed:** 2026-08-16 (jarvis-os @ local)
