# Integrations Index

| Service | Env keys | Module |
|---------|----------|--------|
| Livekit | LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET | voice/agent.py |
| Deepgram | DEEPGRAM_API_KEY | STT LiveKit plugin |
| Elevenlabs | ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID | TTS + LiveKit plugin |
| Anthropic | ANTHROPIC_API_KEY, ANTHROPIC_MODEL | LLM api backend |
| Openai | OPENAI_API_KEY | LLM / STT / Whisper |
| Google | GOOGLE_API_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET | Gemini, Calendar, Gmail |
| Spotify | SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET | Music provider |
| Deezer | DEEZER_APP_ID, DEEZER_APP_SECRET | Music provider |
| Notion | NOTION_TOKEN, NOTION_PAGE_ID | Notion tasks tool |
| Telegram | TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_ID | Mobile channel |
| Discord | DISCORD_BOT_TOKEN, DISCORD_OWNER_ID | Discord channel |
| Mapbox | MAPBOX_TOKEN, MAPTILER_KEY | Globe / maps |

Sheets in [sheets/](sheets/).


## Related docs

- [INDEX](../INDEX.md)
- [AI_INSTRUCTIONS](../AI_INSTRUCTIONS.md)
- [env-reference](../07-config/env-reference.md)
- [setup-flow](../01-entry-points/setup-flow.md)
- [windows-launchers](../01-entry-points/windows-launchers.md)
- [bundle-offline](../02-kernel/bundle-offline.md)
- [process-map](../maps/process-map.md)
- [run-flow](../01-entry-points/run-flow.md)
- [logs-and-doctor](../09-operations/logs-and-doctor.md)
- [troubleshooting](../09-operations/troubleshooting.md)

- **Last reviewed:** 2026-08-13 (jarvis-os @ local)
