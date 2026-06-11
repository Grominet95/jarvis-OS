from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from jarvis.capabilities.tools.memory import MemoryLoadTopicTool, MemorySearchTool
from jarvis.providers.memory.index import MemoryIndex
from jarvis.providers.memory.search import VectorIndex, _chunk_text
from jarvis.providers.memory.sessions import SessionStore
from jarvis.providers.memory.topics import TopicStore

# ── SessionStore ──────────────────────────────────────────────


def test_session_store_append_and_load(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    store.append("abc-123", "user", "Bonjour")
    store.append("abc-123", "assistant", "Salut chef.")

    messages = store.load("abc-123")
    assert len(messages) == 2
    assert messages[0] == {"role": "user", "content": "Bonjour"}
    assert messages[1] == {"role": "assistant", "content": "Salut chef."}


def test_session_store_load_unknown(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    assert store.load("does-not-exist") == []


def test_session_store_creates_dated_file(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    store = SessionStore(sessions_dir)
    store.append("uuid-xyz", "user", "Test")

    files = list(sessions_dir.glob("*_uuid-xyz.jsonl"))
    assert len(files) == 1
    # Fichier nommé YYYY-MM-DD_uuid-xyz.jsonl
    assert files[0].name.endswith("_uuid-xyz.jsonl")


def test_session_store_list_recent(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    store.append("s1", "user", "A")
    store.append("s2", "user", "B")
    recent = store.list_recent(n=5)
    assert len(recent) == 2


# ── MemoryIndex ───────────────────────────────────────────────


def test_memory_index_read(tmp_path: Path) -> None:
    md = tmp_path / "MEMORY.md"
    md.write_text("# Index\n\n## Utilisateur\n- profile: `topics/user.md` — Barth\n")
    idx = MemoryIndex(tmp_path)
    content = idx.read()
    assert "profile" in content


def test_memory_index_add_pointer_new_section(tmp_path: Path) -> None:
    md = tmp_path / "MEMORY.md"
    md.write_text("# Index\n")
    idx = MemoryIndex(tmp_path)
    idx.add_pointer("Projets actifs", "ipod", "topics/project_ipod.md", "DAP iPod PCM5102A")

    content = md.read_text()
    assert "ipod" in content
    assert "project_ipod.md" in content
    assert "DAP iPod PCM5102A" in content


def test_memory_index_update_existing_pointer(tmp_path: Path) -> None:
    md = tmp_path / "MEMORY.md"
    md.write_text("# Index\n\n## Projets actifs\n- ipod: `topics/old.md` — Ancienne description\n")
    idx = MemoryIndex(tmp_path)
    idx.add_pointer("Projets actifs", "ipod", "topics/project_ipod.md", "Nouvelle description")

    content = md.read_text()
    assert "Nouvelle description" in content
    assert "Ancienne description" not in content
    # Un seul pointeur ipod
    assert content.count("- ipod:") == 1


def test_memory_index_add_pointer_existing_section(tmp_path: Path) -> None:
    md = tmp_path / "MEMORY.md"
    initial = "# Index\n\n## Projets actifs\n- jarvis: `topics/jarvis.md` — Jarvis\n\n## Autre\n"
    md.write_text(initial)
    idx = MemoryIndex(tmp_path)
    idx.add_pointer("Projets actifs", "alfred", "topics/alfred.md", "Bras robotisé")

    content = md.read_text()
    assert "alfred" in content
    assert "Bras robotisé" in content


# ── TopicStore ────────────────────────────────────────────────


def test_topic_store_write_and_load(tmp_path: Path) -> None:
    store = TopicStore(tmp_path / "topics")
    store.write("project_ipod.md", "# iPod DAP\n\nPCM5102A, DAC haute qualité.")
    content = store.load("project_ipod.md")
    assert "PCM5102A" in content


def test_topic_store_load_all(tmp_path: Path) -> None:
    store = TopicStore(tmp_path / "topics")
    store.write("a.md", "# A")
    store.write("b.md", "# B")
    all_topics = store.load_all()
    assert set(all_topics.keys()) == {"a.md", "b.md"}


def test_topic_store_load_unknown(tmp_path: Path) -> None:
    store = TopicStore(tmp_path / "topics")
    assert store.load("inexistant.md") == ""


def test_topic_store_exists(tmp_path: Path) -> None:
    store = TopicStore(tmp_path / "topics")
    assert not store.exists("x.md")
    store.write("x.md", "# X")
    assert store.exists("x.md")


# ── Session persist callback ───────────────────────────────────


def test_session_persist_callback(tmp_path: Path) -> None:
    from jarvis.engine.session import Session

    written: list[tuple[str, str]] = []

    session = Session()
    session.set_persist(lambda role, content: written.append((role, content)))

    session.add_message("user", "Test persist")
    session.add_message("assistant", "Reçu.")

    assert written == [("user", "Test persist"), ("assistant", "Reçu.")]


def test_session_manager_restore_from_jsonl(tmp_path: Path) -> None:
    from jarvis.engine.session import SessionManager
    from jarvis.providers.memory.sessions import SessionStore

    # UUID valide requis — les sessions sont toujours identifiées par uuid4()
    session_id = "12345678-1234-5678-1234-567812345678"
    store = SessionStore(tmp_path / "sessions")
    store.append(session_id, "user", "Je travaille sur l'iPod DAP")
    store.append(session_id, "assistant", "Noté, iPod DAP avec PCM5102A.")

    mgr = SessionManager(store=store)
    session = mgr.get_or_create(session_id)

    assert len(session.messages) == 2
    assert session.messages[0]["content"] == "Je travaille sur l'iPod DAP"


# ── Couche 2 : injection de la liste seule + memory_load_topic ────────


def test_agent_build_system_lists_topics_only(tmp_path: Path) -> None:
    """_build_system() doit injecter la LISTE des topics, pas leur contenu."""
    from jarvis.engine.agent import Agent

    topics_dir = tmp_path / "topics"
    store = TopicStore(topics_dir)
    store.write("user_prefs.md", "# Préférences\nSecret: PCM5102A_iPod")
    store.write("spotify.md", "# Spotify\nID: SECRET_TOKEN_42")

    (tmp_path / "MEMORY.md").write_text("# Index\n")
    memory_index = MemoryIndex(tmp_path)

    class _DummyLLM:
        supports_tools = False

    from jarvis.kernel.settings import settings as _settings

    agent = Agent(settings=_settings, llm=_DummyLLM(), memory_index=memory_index, topic_store=store)
    system = agent._build_system()

    assert "user_prefs.md" in system
    assert "spotify.md" in system
    # Le contenu détaillé ne doit PAS être présent
    assert "PCM5102A_iPod" not in system
    assert "SECRET_TOKEN_42" not in system


async def test_memory_load_topic_reads_existing(tmp_path: Path) -> None:
    topics_dir = tmp_path / "topics"
    store = TopicStore(topics_dir)
    store.write("user_prefs.md", "# Préférences\nMode sombre activé.")

    tool = MemoryLoadTopicTool(topic_store=TopicStore(topics_dir))
    result = await tool.execute(filename="user_prefs.md")

    assert not result.is_error
    assert "Mode sombre activé." in result.content


async def test_memory_load_topic_rejects_invalid_name(tmp_path: Path) -> None:
    tool = MemoryLoadTopicTool(topic_store=TopicStore(tmp_path / "topics"))
    for bad in ["../secret.md", "etc/passwd", "no_extension", "evil\\path.md"]:
        result = await tool.execute(filename=bad)
        assert result.is_error, f"Nom invalide accepté : {bad}"


async def test_memory_load_topic_unknown_file(tmp_path: Path) -> None:
    topics_dir = tmp_path / "topics"
    TopicStore(topics_dir)  # crée le dossier
    tool = MemoryLoadTopicTool(topic_store=TopicStore(topics_dir))
    result = await tool.execute(filename="inexistant.md")
    assert result.is_error
    assert "introuvable" in result.content.lower()


# ── Couche 3 : VectorIndex avec embedding déterministe mocké ─────────


class _FakeEmbedder:
    """Embedder déterministe : projette des mots-clés sur des dimensions fixes.

    Évite le téléchargement du modèle fastembed en CI. La proximité cosinus
    reproduit le comportement attendu : un texte qui partage des mots-clés
    avec une requête obtient un meilleur score.
    """

    _VOCAB = {
        "ipod": 0,
        "dac": 1,
        "pcm5102a": 2,
        "spotify": 3,
        "musique": 4,
        "préférences": 5,
        "mode": 6,
        "sombre": 7,
        "calendrier": 8,
        "réunion": 9,
    }
    _DIM = 32

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        out: list[np.ndarray] = []
        for text in texts:
            vec = np.zeros(self._DIM, dtype=np.float32)
            lowered = text.lower()
            for word, idx in self._VOCAB.items():
                if word in lowered:
                    vec[idx] += 1.0
            # Composante secondaire stable pour différencier les textes proches
            h = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16)
            vec[10 + (h % (self._DIM - 10))] += 0.05
            out.append(vec)
        return out


@pytest.fixture
def fake_vector_index(tmp_path: Path) -> VectorIndex:
    index = VectorIndex(index_dir=tmp_path / "idx")
    index._model = _FakeEmbedder()
    return index


async def test_vector_index_add_and_search(fake_vector_index: VectorIndex) -> None:
    await fake_vector_index.add(
        doc_id="topic:user_prefs.md",
        text="Préférences mode sombre activé",
        metadata={"source": "topic", "filename": "user_prefs.md"},
    )
    await fake_vector_index.add(
        doc_id="topic:music.md",
        text="iPod DAC PCM5102A pour musique haute qualité",
        metadata={"source": "topic", "filename": "music.md"},
    )

    results = await fake_vector_index.search(query="DAC PCM5102A iPod", k=2)

    assert len(results) > 0
    assert results[0]["doc_id"] == "topic:music.md"
    assert results[0]["score"] > results[-1]["score"]


async def test_vector_index_persist_and_load_roundtrip(
    tmp_path: Path,
    fake_vector_index: VectorIndex,
) -> None:
    await fake_vector_index.add(
        doc_id="topic:a.md",
        text="iPod DAC PCM5102A musique",
        metadata={"filename": "a.md"},
    )
    await fake_vector_index.persist()

    # Nouvelle instance — doit recharger depuis disque
    reloaded = VectorIndex(index_dir=fake_vector_index._dir)
    reloaded._model = _FakeEmbedder()
    assert not reloaded.is_empty()

    results = await reloaded.search(query="iPod DAC", k=1)
    assert len(results) == 1
    assert results[0]["doc_id"] == "topic:a.md"
    assert results[0]["metadata"]["filename"] == "a.md"


async def test_vector_index_reindex_from_topics(
    tmp_path: Path,
    fake_vector_index: VectorIndex,
) -> None:
    topics_dir = tmp_path / "topics"
    store = TopicStore(topics_dir)
    store.write("music.md", "iPod DAC PCM5102A musique")
    store.write("ui.md", "Préférences mode sombre")

    count = await fake_vector_index.reindex(topic_store=store, transcripts_dir=None)
    assert count == 2

    results = await fake_vector_index.search(query="DAC PCM5102A", k=1)
    assert results[0]["metadata"]["filename"] == "music.md"


async def test_memory_search_tool_formats_results(
    fake_vector_index: VectorIndex,
) -> None:
    await fake_vector_index.add(
        doc_id="topic:music.md",
        text="iPod DAC PCM5102A musique",
        metadata={"filename": "music.md"},
    )
    tool = MemorySearchTool(vector_index=fake_vector_index)
    result = await tool.execute(query="iPod DAC", k=3)

    assert not result.is_error
    assert "music.md" in result.content
    assert "score=" in result.content


async def test_memory_search_tool_empty_query(
    fake_vector_index: VectorIndex,
) -> None:
    tool = MemorySearchTool(vector_index=fake_vector_index)
    result = await tool.execute(query="   ", k=3)
    assert result.is_error


def test_chunk_text_handles_short_and_long(tmp_path: Path) -> None:
    short = "Un texte court."
    assert _chunk_text(short) == [short]

    long_text = " ".join([f"mot{i}" for i in range(1200)])
    chunks = _chunk_text(long_text, chunk_size=500, overlap=50)
    assert len(chunks) >= 2
    # Premier chunk : 500 mots
    assert len(chunks[0].split()) == 500
