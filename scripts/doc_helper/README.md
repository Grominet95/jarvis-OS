# Documentation Helper — FTS5 index

Build and query the `Documentation_Helper/` corpus for AI context (~1k tokens).

## Setup

```powershell
cd scripts/doc_helper
npm install
npm run enrich-links    # inject ## Related docs cross-links
npm run build-index       # build Documentation_Helper/doc_index.sqlite
```

## Query

```powershell
npm run query -- --max-tokens 1000 "livekit voix marche pas"
npm run query -- --max-tokens 1000 "instaler jarvis onedrive"
npm run query -- --json "memoire rappel session"
```

## Files

| File | Role |
|------|------|
| `keywords.js` | FR/EN synonyms + typo variants |
| `build_fts_index.js` | Chunk markdown → SQLite FTS5 |
| `query_context.js` | BM25 search + related links, token cap |
| `enrich_crosslinks.js` | Add `## Related docs` to all markdown |

Output database: `Documentation_Helper/doc_index.sqlite` (gitignored). Corpus markdown under `Documentation_Helper/` is tracked; `AI_INSTRUCTIONS.md` stays local only.
