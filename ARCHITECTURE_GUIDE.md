# 🤖 JARVIS-OS — Guide Complet de l'Architecture

## 📊 Vue d'ensemble

**Jarvis OS** est un assistant personnel IA qui tourne en local. Il expose un serveur FastAPI qui gère à la fois une interface de chat texte et un pipeline vocal temps réel (via LiveKit). Il se connecte au LLM de ton choix, mémorise les conversations, utilise des outils (recherche web, Gmail, Google Calendar, Spotify, vision, exécution de code…) et fait tourner des tâches proactives en arrière-plan (alertes météo, digests d'actualités, etc.).

C'est une **architecture en 4 couches strictes** validées par `import-linter` en CI.

```
┌─────────────────────────────────────────────────────┐
│ L3: INTERFACES & BOOTSTRAP                           │
│   FastAPI app.py, WebUI, Voice (LiveKit), Channels  │
└─────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────┐
│ L2: ENGINE                                           │
│   Agent, Gateway, Mission Engine, Proactive Engine  │
│   Background Worker, Scheduler, Governance          │
└─────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────┐
│ L1: PROVIDERS & CAPABILITIES                        │
│   LLM (Claude/Mistral/Gemini), Memory Kernel,      │
│   Tools (Gmail, Spotify, Vision), Skills Registry   │
└─────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────┐
│ L0: KERNEL (Contracts, Schemas, Events, Settings)   │
└─────────────────────────────────────────────────────┘
```

## 🎯 Architecture en Couches

### **L0: KERNEL** (Foundation)
- **`kernel/contracts.py`** → Protocols (LLMProvider, MemoryKernel, etc.)
- **`kernel/schemas.py`** → Dataclasses partagées (Fact, Tool, Skill, etc.)
- **`kernel/events.py`** → Event bus pub/sub (async)
- **`kernel/settings.py`** → Configuration (Pydantic Settings)
- **`kernel/errors.py`** → Error codes + exceptions
- **`kernel/vocab.py`** → Enums (TaskStatus, SkillPhase, etc.)
- **`kernel/permissions.py`** → Permission model (read, write, execute)
- **`kernel/approval.py`** → Approval workflow (humain dans la boucle)
- **`kernel/paths.py`** → Resolved paths (~/.jarvis/, config/, workspace/)
- **`kernel/notifications.py`** → Notification events

### **L1: PROVIDERS** (Data & LLM)

#### Memory Kernel (SQLite)
```
providers/memory/
  ├── kernel.py          → Ingestion + Search + Consolidation
  ├── ingest.py          → Parse facts, sourcings, decay policies
  ├── search.py          → BM25 + semantic search (FastEmbed)
  ├── retrieval.py       → In-context facts for LLM
  ├── consolidation.py   → Midnight cleanup (decay, archive)
  ├── auto_dream.py      → Narrative summaries
  └── mirror.py          → Markdown export (lisible, portable)
```
- **Source vérité** : SQLite (`~/.jarvis/memory.db`)
- **Faits atomiques** : `{content, dates, sources, decay_policy, mutable}`
- **Miroir Markdown** : Export lisible dans `~/.jarvis/memory_mirror/`

#### LLM Factory
```
providers/llm/
  ├── api.py      → Anthropic Claude (main)
  ├── local.py    → Ollama wrapper
  ├── factory.py  → LLMProvider builder (from settings)
```

#### Audio (STT + TTS)
```
providers/audio/
  ├── stt.py                → Whisper | Deepgram | Silero
  ├── tts.py                → Piper | ElevenLabs | Google
  ├── elevenlabs_voices.py  → ElevenLabs voice sync
  ├── clap_detector.py      → Wake-word (clap detection)
```

#### Vision
```
providers/vision/
  ├── vision/__init__.py     → Controller
  ├── daemon.py              → Polling loop (~1fps)
  ├── face_recognizer.py     → Face encoding + matching
  ├── object_detector.py     → YOLOv8 real-time
  ├── objects_queue.py       → Frame queue + cache
```

### **L1: CAPABILITIES** (Tools & Skills)

#### Tools Registry
```
capabilities/tools/
  ├── base.py       → Tool base class
  ├── registry.py   → ToolRegistry (singleton)
  ├── browser.py    → Selenium-based web browser
  ├── gmail.py      → Google API wrapper
  ├── calendar.py   → Google Calendar
  ├── spotify.py    → Spotify API
  ├── notion.py     → Notion integration
  ├── cli.py        → Shell command executor
  ├── filesystem.py → Safe file R/W
  ├── vision.py     → Real-time camera
  ├── memory.py     → Fact retrieval interface
  └── ...
```

#### Skills System
```
capabilities/skills/
  ├── base.py         → SkillBase (abstract)
  ├── registry.py     → SkillRegistry (dynamic loading)
  ├── lifecycle.py    → Phases (DEV, SANDBOXED, ACTIVE, ARCHIVED)
  ├── lab.py          → SkillLab (propose → test → promote)
  ├── synthesizer.py  → LLM-powered skill generation
  ├── executor.py     → Execute skill.execute() + error handling
  └── installer.py    → Install/uninstall workflow
```

**Skill Lifecycle:**
```
Event detected (user action)
    ↓
SkillLab.scan() polls for candidates
    ↓
SkillSynthesizer.propose_skill(trajectory)
    ↓ (LLM generates skill.py + skill.yaml)
    ↓
Docker sandbox test (30s timeout)
    ↓
If PASS → await human approval
    ↓
Promote to ~/.jarvis/skills/installed/{name}/
    ↓
SkillRegistry.reload()
```

### **L2: ENGINE** (Orchestration)

#### Agent & Gateway
```
engine/
  ├── gateway.py      → HTTP request → Agent.chat()
  ├── agent.py        → Main inference loop
  │   ├── context building
  │   ├── LLM.complete(tools=available_tools)
  │   ├── tool execution + retry logic
  │   └── response streaming
```

#### Mission Engine
```
engine/mission/
  ├── orchestrator.py    → Mission lifecycle (PLAN → EXECUTE → VERIFY)
  ├── worker_agent.py    → AI worker (LLM + tools in loop)
  ├── verifier.py        → Quality gates (syntax, semantic, functional)
  ├── governance.py      → Permissions + Budget checks
  ├── capability_engine.py → Fill capability gaps
  └── reflexion.py       → Learn from failures
```

**Mission Phases:**
```
1. PLAN      → LLM generates structured plan (tools needed?)
2. VERIFY    → Check syntax + permissions + budget
3. EXECUTE   → Worker agent runs tools iteratively
4. VERIFY    → Check results vs goal
5. REFLECT   → Post-mortem (success factors, failure analysis)
```

#### Proactive Engine
```
engine/proactive/
  ├── engine.py              → Main loop
  ├── initiative_generator.py → LLM proposes proactive actions
  ├── command_center.py       → UI for user to accept/reject/snooze
  ├── curator.py              → Nightly cleanup (facts, skills, costs)
  ├── scheduler.py            → Periodic jobs (cron-like)
  ├── collectors/
  │   ├── email.py            → Recent emails context
  │   ├── calendar.py         → Upcoming events
  │   ├── weather.py          → Weather forecast
  │   ├── news.py             → RSS feeds
  │   └── tasks.py            → Pending tasks
```

**Initiative Model:**
```json
{
  "id": "init_xxx",
  "title": "Rappel réunion avec Alice",
  "reasoning": "Email urgent hier, RDV aujourd'hui 15h",
  "desired_outcome": "User notifié",
  "priority": "HIGH",
  "execution_mode": "NOTIFY",  // NOTIFY | VALIDATE | AUTO
  "autonomy_level": 1          // 0=ask, 1=notify, 2=confirm, 3=auto_if_free, 4=auto, 5=autonomous
}
```

#### Background Worker
```
engine/background/
  ├── worker.py     → Task queue processor (asyncio)
  ├── scheduler.py  → Cron-like scheduler
  ├── notifications.py → Delivery pipeline
  └── routines.py   → Routine tasks
```

### **L3: INTERFACES** (I/O)

#### FastAPI App
```
app.py:
  @asynccontextmanager
  async def lifespan(app):
      # SETUP
      container = build(settings)
      app.state.container = container
      
      # Launch background tasks
      asyncio.create_task(container.vector_index.reindex())
      asyncio.create_task(container.worker.run_loop())
      asyncio.create_task(run_vision_daemon())
      container.scheduler.start()
      
      yield  # ← app runs here
      
      # TEARDOWN
      container.worker.stop()
      container.scheduler.stop()
```

#### API Routes
```
interfaces/api/
  ├── chat.py         → POST /api/chat, WS /ws/chat
  ├── memory.py       → GET /api/memory, POST /api/memory/facts
  ├── skills.py       → GET /api/skills, POST /api/skills/{id}/execute
  ├── proactive.py    → GET /api/proactive/initiatives, POST /api/proactive/initiatives/{id}/accept
  ├── budget.py       → GET /api/budget, token tracking
  ├── sessions.py     → Session management
  ├── config/
  │   ├── llm.py      → LLM settings (rotate backends)
  │   ├── devices.py  → Audio/camera config
  │   ├── permissions.py → Role-based permissions
  │   └── settings.py → General settings
  └── admin.py        → Admin functions
```

#### Voice Agent (LiveKit)
```
interfaces/voice/agent.py:
  class JarvisVoiceAgent:
      async def on_message(user_message):
          # STT (Deepgram | Whisper | Silero)
          text = await stt_provider.transcribe(audio_frame)
          
          # Context (time, profile, memory)
          context = build_voice_context()
          
          # LLM (Claude + tools)
          response = await llm.complete(
              messages=[{"role": "user", "content": text}],
              system=system_prompt,
              tools=available_tools
          )
          
          # TTS (Piper | ElevenLabs | Google)
          audio_chunks = await tts_provider.synthesize(response)
          
          # Stream back to LiveKit
          await room.send_audio(audio_chunks)
```

## 🔄 Flux d'une Requête (Text → Chat)

```
User message (HTTP POST /api/chat)
    ↓
Gateway.route_chat_message(msg)
    ↓
Agent.chat(messages, tools)
    ├─ Load context (recent facts, tool descriptions)
    ├─ LLM.complete(
    │    messages=[system, history, user_msg],
    │    tools=available_tools
    │  )
    │    ↓ (if tool_use)
    │  Tool execution (with governance checks)
    │    ├─ Check permissions (filesystem, network)
    │    ├─ Check budget (tokens left)
    │    ├─ Execute tool (browser, Gmail, CLI, etc.)
    │    └─ Capture output (audit log)
    │    ↓
    │  LLM.complete(
    │    messages=[...previous..., tool_result],
    │    tools=[]  # LLM may call more tools or finalize
    │  )
    │
    └─ Stream response to client
       (HTTP streaming or WebSocket chunks)
```

## 📁 Arborescence Clé

```
jarvis-OS/
├── src/jarvis/
│   ├── kernel/                 ← L0: Contracts + Schemas + Events
│   ├── providers/
│   │   ├── llm/               ← LLM factory (Claude, Mistral, etc.)
│   │   ├── memory/            ← Memory Kernel (SQLite)
│   │   ├── audio/             ← STT/TTS
│   │   └── vision/            ← YOLOv8, face recognition
│   ├── capabilities/
│   │   ├── tools/             ← Tool registry + implementations
│   │   └── skills/            ← Skill lifecycle + Lab
│   ├── engine/
│   │   ├── mission/           ← Mission Engine (PLAN → EXECUTE → VERIFY)
│   │   ├── proactive/         ← Proactive initiatives + Curator
│   │   ├── background/        ← Worker + Scheduler
│   │   ├── gateway.py         ← HTTP entry point
│   │   └── agent.py           ← Main LLM loop
│   ├── interfaces/
│   │   ├── api/               ← FastAPI routers
│   │   ├── ui/                ← WebUI (React/Svelte)
│   │   ├── voice/             ← LiveKit agent
│   │   └── channels/          ← Discord, Telegram, Slack
│   ├── app.py                 ← FastAPI instance + lifespan
│   └── bootstrap.py           ← Composition root (DI container)
├── tests/                      ← Unit tests (587 tests, <30s)
├── Documentation_Helper/       ← 300+ .md files (architecture docs)
├── config/                     ← backends.json, approvals.json
├── voice_agent.py            ← Entry point vocal (LiveKit)
├── main.py                    ← Entry point text (FastAPI)
└── Dockerfile, docker-compose.yml
```

## 🔐 Gouvernance & Audit

### Permissions Model
```python
class Permission(Protocol):
    scope: str         # "filesystem", "network", "llm", "memory"
    action: str        # "read", "write", "execute"
    resource: str      # path, domain, model
    user_role: str     # "admin", "user", "guest"
    
    def allows(target: str) -> bool:
        """Check if action is allowed."""
```

### Governance Gates
```
1. STRUCTURAL GATE
   ├─ Tool input valid? (schema check)
   └─ Budget available? (token quota)

2. SEMANTIC GATE
   ├─ Does LLM request make sense?
   └─ Is result coherent?

3. FUNCTIONAL GATE
   ├─ Did tool execute without error?
   └─ Is output parseable?

4. AUDIT GATE
   ├─ Log every action (immutable)
   └─ Track costs (tokens, API calls)
```

**Audit Immuable:**
```sqlite
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME,
    event_type TEXT,  -- tool_execute, skill_create, memory_write
    actor TEXT,       -- user | system | agent_name
    resource TEXT,    -- filename | fact_id | skill_name
    action TEXT,      -- read | write | execute
    result TEXT,      -- success | failure
    details JSONL     -- error_code, output, permissions_used
);
```

## ⚙️ Stack Technique

| Composant | Tech | Rôle |
|-----------|------|------|
| **Framework Web** | FastAPI 0.115+ | HTTP async + WebSocket |
| **Server ASGI** | Uvicorn 0.32+ | Production-ready ASGI |
| **Validation** | Pydantic 2.9+ | Data validation + Config |
| **LLM Principal** | Anthropic Claude | Main inference (API) |
| **LLM Alternatif** | Mistral, Gemini, Ollama | Fallback providers |
| **Voice Temps Réel** | LiveKit 1.5+ | Real-time communication |
| **STT** | Deepgram, Whisper, Silero | Speech-to-text |
| **TTS** | Piper, ElevenLabs, Google | Text-to-speech |
| **Memory** | SQLite + FastEmbed | Persistent + semantic search |
| **Vision** | YOLOv8, face-recognition | Object/face detection |
| **Async Runtime** | asyncio | All I/O non-blocking |
| **CLI Tools** | subprocess + shell exec | Safe command execution |
| **Web Scraping** | Selenium + BeautifulSoup | Browser automation |
| **OAuth** | google-auth-oauthlib | Google integration |
| **Logging** | Loguru | Structured logs |
| **Testing** | pytest | Unit + integration tests |
| **Linting** | ruff, mypy, import-linter | Code quality gates |

## 🚀 Points d'Entrée

| Point | Fichier | Commande |
|-------|---------|----------|
| **FastAPI (Texte + UI)** | `app.py` | `python -m jarvis` ou `uvicorn jarvis.app:app` |
| **Voice Agent (LiveKit)** | `voice_agent.py` | `python voice_agent.py` |
| **Bootstrap (DI)** | `bootstrap.py:build()` | Appelé auto par `app.py` lifespan |
| **Setup Wizard** | `interfaces/api/setup_wizard.py` | POST `/api/setup` |
| **Docker** | `Dockerfile` + `docker-compose.yml` | `docker-compose up` |

## 🎓 Patterns Clés

### 1. Injection de Dépendances (Protocols)
```python
# L0: kernel/contracts.py
class LLMProvider(Protocol):
    async def complete(self, messages, system, tools=None, stream=False) -> str | AsyncIterator[str]:
        ...

# L1: providers/llm/api.py
class AnthropicLLM(LLMProvider):
    async def complete(self, ...):
        return await client.messages.create(...)

# L2: engine/agent.py
class Agent:
    def __init__(self, llm_provider: LLMProvider):
        self.llm = llm_provider  # Type-safe, testable
```

### 2. Event Bus (Pub/Sub)
```python
# kernel/events.py
class EventBus:
    async def emit(event_type: str, data: dict):
        # Notify all subscribers
        for handler in self._handlers[event_type]:
            await handler(data)
    
    def on(event_type: str, handler: Callable):
        self._handlers[event_type].append(handler)

# Usage:
bus.on("skill_candidate_proposal", skill_lab.scan)
bus.emit("skill_candidate_proposal", {"event_id": "..."})
```

### 3. Async Composition (Lifespan)
```python
@asynccontextmanager
async def lifespan(app):
    # Startup
    container = build()
    tasks = [
        asyncio.create_task(worker.run_loop()),
        asyncio.create_task(scheduler.start()),
        asyncio.create_task(vision_daemon()),
    ]
    yield
    # Shutdown
    for task in tasks:
        task.cancel()
```

### 4. Tool Registry Pattern
```python
class ToolRegistry:
    _tools: dict[str, Tool] = {}
    
    def register(name: str, tool: Tool):
        self._tools[name] = tool
    
    def available_for(user_role: str, budget: TokenBudget) -> list[Tool]:
        return [t for t in self._tools.values()
                if t.requires_permission.is_allowed(user_role)
                and budget.can_afford(t.estimated_tokens)]
```

### 5. Skill Lifecycle (State Machine)
```
DEV → SANDBOXED_PASS → ACTIVE → ARCHIVED
           ↓
      SANDBOXED_FAIL → (auto-reject)

Each phase triggers events and notifications.
```

## 📈 CI/CD Gates

| Gate | Vérifie | Vitesse |
|------|---------|---------|
| `ruff check` | Style + erreurs Python | ~2s |
| `lint-imports` | 3 contrats (import layer enforcement) | ~5s |
| `mypy` | Types contre Protocols | ~10s |
| `pytest -m "not integration"` | 587 tests unitaires | ~30s |
| `check_pr.py` | Error codes sync + sites mappés | ~5s |
| `snapshot_routes.py` | URLs HTTP invariantes | ~3s |
| **Heavy (scheduled)** | Full test suite + integration | ~5 min |

## 💡 Takeaways

1. **Architecture en couches stricte** → Chaque couche a une responsabilité claire
2. **Injection de dépendances typées** → Testable, mockable, refactorisable
3. **Event-driven** → Scalable (ex: skill proposals auto-trigger Lab)
4. **Gouvernance omniprésente** → Permissions, budget, audit intégrés partout
5. **Async-first** → Pas de blocs, scalable à des centaines d'utilisateurs
6. **Multi-LLM + fallbacks** → Robuste, pas de vendor lock-in
7. **Mémoire vivante** → Pas juste un chat ephémère, persistence + recall
8. **Proactive autonome** → Pas juste réactif, peut agir de lui-même (avec gating)
9. **Skill Lab** → Auto-learns from use, no manual skill addition needed
10. **Voice first-class** → LiveKit pipeline temps-réel, pas juste TTS+STT

## 🔗 Ressources

- **README.md** → Overview français
- **Documentation_Helper/INDEX.md** → Map complète des docs
- **Documentation_Helper/00-meta/architecture-layers.md** → Détails des couches
- **Documentation_Helper/05-engine/mission/overview.md** → Mission Engine deep dive
- **Documentation_Helper/05-engine/proactive/overview.md** → Proactive engine
- **Documentation_Helper/04-capabilities/skills/ → Skills system docs

---

*Architecture guide pour jarvis-OS v0.3.2 - Pour contribuer au projet ou comprendre l'implémentation complète*
