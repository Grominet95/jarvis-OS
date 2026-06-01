# Attributions — Memory Recall & User Modeling

## Hermes-Agent (NousResearch)

Portions of the cross-session recall architecture (FTS5 search, LLM-powered session
summarization, recall injection into the system prompt) are inspired by the
`session_search` and `recall` patterns from the Hermes-Agent project.

- **Project**: hermes-agent
- **Author**: NousResearch
- **License**: MIT License, 2025
- **Source**: https://github.com/NousResearch/hermes-agent
- **Files inspired**: `memory/search.py` (FTSIndex), `memory/consolidation.py`
  (CrossSessionRecall)

## Honcho (Plastic Labs)

The dialectical user modeling layer (`memory/user_model.py`) is inspired by the
Honcho framework's approach to evolving user representations: tracking preferences,
behavioral patterns, and contradictions over time through structured LLM updates.

- **Project**: Honcho
- **Author**: Plastic Labs
- **License**: MIT License, 2024
- **Source**: https://github.com/plastic-labs/honcho
- **Files inspired**: `memory/user_model.py`

Both components adapt the above patterns to Jarvis V3's layered memory architecture
(3-layer: MEMORY.md index → topic files → semantic/FTS search).
