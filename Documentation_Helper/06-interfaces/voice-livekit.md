# Voice LiveKit Pipeline

Process: `python -m jarvis.interfaces.voice.agent dev`

## Stack

- LiveKit room + browser client (`voice_livekit.js`)
- STT: Deepgram / OpenAI / Google (`STT_PROVIDER`)
- LLM: follows `API_BACKEND` / `VOICE_LLM_MODEL`
- TTS: ElevenLabs plugin or fallbacks

## Env keys

`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `DEEPGRAM_API_KEY`, `ELEVENLABS_*`

## Source of truth

[src/jarvis/interfaces/voice/agent.py](../../src/jarvis/interfaces/voice/agent.py)


## Related docs

- [INDEX](../INDEX.md)
- [AI_INSTRUCTIONS](../AI_INSTRUCTIONS.md)
- [overview](./overview.md)
- [route-map](../maps/route-map.md)
- [setup-flow](../01-entry-points/setup-flow.md)
- [windows-launchers](../01-entry-points/windows-launchers.md)
- [bundle-offline](../02-kernel/bundle-offline.md)
- [process-map](../maps/process-map.md)
- [env-reference](../07-config/env-reference.md)
- [run-flow](../01-entry-points/run-flow.md)

- **Last reviewed:** 2026-08-13 (jarvis-os @ local)
