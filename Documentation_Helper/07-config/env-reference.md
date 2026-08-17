# Environment Reference

Full `.env.example` grouped by section. Never commit real `.env`.

## Identité

- `USER_FIRSTNAME`
- `ASSISTANT_NAME`
- `USER_PROFILE`

## Serveur

- `PORT`
- `ENVIRONMENT`
- `LOG_LEVEL`

## Sécurité réseau

- `API_AUTH_ENABLED`
- `API_TOKEN`
- `CORS_ALLOW_ORIGINS`

## LLM

- `LLM_PROVIDER`
- `API_BACKEND`
- `ANTHROPIC_API_KEY`
- `ANTHROPIC_MODEL`
- `OPENAI_MODEL`
- `VOICE_ANTHROPIC_MODEL`

## OpenAI

- `OPENAI_API_KEY`

## Google / Gemini

- `GOOGLE_API_KEY`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`

## Ollama (LLM local)

- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`

## Mistral (optionnel)

- `MISTRAL_API_KEY`
- `MISTRAL_MODEL`

## TTS / Voix

- `TTS_PROVIDER`
- `ELEVENLABS_API_KEY`
- `ELEVENLABS_VOICE_ID`
- `ELEVENLABS_MODEL`
- `ELEVENLABS_SPEED`
- `GEMINI_TTS_MODEL`
- `GEMINI_TTS_VOICE`
- `QUEBEC_MODE`
- `QUEBEC_VOICE_ID`

## STT (pipeline vocal LiveKit)

- `STT_PROVIDER`
- `WHISPER_MODEL`
- `DEEPGRAM_API_KEY`

## LiveKit (pipeline vocal temps réel)

- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`

## Notion

- `NOTION_TOKEN`
- `NOTION_PAGE_ID`

## Spotify

- `SPOTIFY_CLIENT_ID`
- `SPOTIFY_CLIENT_SECRET`

## Deezer

- `DEEZER_APP_ID`
- `DEEZER_APP_SECRET`

## Cartographie

- `MAPBOX_TOKEN`
- `MAPTILER_KEY`

## Vision & Reconnaissance faciale

- `VISION_OBJECT_DETECTION`
- `VISION_WEBCAM_INDEX`
- `VISION_YOLO_CONFIDENCE`
- `FACE_RECOGNITION_ENABLED`
- `FACE_RECOGNITION_THRESHOLD`

## Wake Up (séquence démarrage)

- `WAKEUP_ENABLED`

## Clap Detection

- `CLAP_DETECTION_ENABLED`
- `CLAP_AMPLITUDE_THRESHOLD`

## Docker (sandbox agent)

- `DOCKER_ENABLED`
- `DOCKER_BASE_IMAGE`
- `DOCKER_MEMORY_LIMIT`
- `DOCKER_CPU_LIMIT`
- `DOCKER_TIMEOUT_SECONDS`

## Imprimante 3D (BambuLab)

- `PRINTER_IP`
- `PRINTER_SERIAL`
- `PRINTER_ACCESS_CODE`

## Fusion 360 MCP

- `FUSION_ENABLED`
- `FUSION_MCP_URL`

## Proactif (briefing / rappels)

- `BRIEFING_HOUR`
- `CALENDAR_REMINDER_MINUTES`
- `PROACTIVE_LAT`
- `PROACTIVE_LON`
- `PROACTIVE_CITY`

## Musique

- `MUSIC_PROVIDER`

## YouTube

- `YOUTUBE_API_KEY`
- `YOUTUBE_CHANNEL_ID`

## Briefing post-wakeup (macOS local : ouvre des fenêtres Safari)

- `BRIEFING_ENABLED`
- `BRIEFING_PRESET`
- `NOTION_TASKS_URL`

## GitHub

- `GITHUB_TOKEN`
- `GITHUB_REPO`

## AISstream (trafic maritime)

- `AISSTREAM_KEY`

## Telegram (accès mobile)

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_OWNER_ID`
- `TELEGRAM_ENABLED`

## Messaging Gateway (multi-plateforme)

- `MESSAGING_GATEWAY_ENABLED`

## Discord

- `DISCORD_BOT_TOKEN`
- `DISCORD_OWNER_ID`
- `DISCORD_ENABLED`

- **Source of truth:** [.env.example](../../.env.example)

## Related docs

- [INDEX](../INDEX.md)
- [AI_INSTRUCTIONS](../AI_INSTRUCTIONS.md)
- [settings-and-env](../02-kernel/settings-and-env.md)
- [setup-flow](../01-entry-points/setup-flow.md)
- [windows-launchers](../01-entry-points/windows-launchers.md)
- [bundle-offline](../02-kernel/bundle-offline.md)
- [process-map](../maps/process-map.md)
- [run-flow](../01-entry-points/run-flow.md)
- [logs-and-doctor](../09-operations/logs-and-doctor.md)
- [troubleshooting](../09-operations/troubleshooting.md)

- **Last reviewed:** 2026-08-13 (jarvis-os @ local)
