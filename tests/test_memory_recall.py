"""Tests du rappel cross-session et du modèle utilisateur."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from jarvis.providers.memory.search import FTSIndex, VectorIndex

# ── 1. FTSIndex ───────────────────────────────────────────────────────────────


class TestFTSIndex:
    """FTSIndex : CRUD + recherche plein texte."""

    @pytest.fixture
    def fts(self, tmp_path: Path) -> FTSIndex:
        return FTSIndex(db_path=tmp_path / "fts.db")

    @pytest.mark.asyncio
    async def test_add_and_search(self, fts: FTSIndex) -> None:
        await fts.add("session1.jsonl", "Barth veut un café le matin")
        results = await fts.search("café")
        assert len(results) == 1
        assert results[0]["doc_id"] == "session1.jsonl"
        assert "café" in results[0]["text"]

    @pytest.mark.asyncio
    async def test_add_remplace_existant(self, fts: FTSIndex) -> None:
        await fts.add("session1.jsonl", "Contenu original")
        await fts.add("session1.jsonl", "Contenu mis à jour")
        results = await fts.search("mis à jour")
        assert len(results) == 1
        assert "mis à jour" in results[0]["text"]

    @pytest.mark.asyncio
    async def test_remove(self, fts: FTSIndex) -> None:
        await fts.add("session1.jsonl", "Texte à supprimer")
        await fts.remove("session1.jsonl")
        assert await fts.count() == 0

    @pytest.mark.asyncio
    async def test_search_requete_malformee_retourne_vide(self, fts: FTSIndex) -> None:
        await fts.add("session1.jsonl", "Texte normal")
        # Guillemets non fermés → requête FTS5 invalide
        results = await fts.search('"requête non fermée')
        assert results == []

    @pytest.mark.asyncio
    async def test_is_empty_et_count(self, fts: FTSIndex) -> None:
        assert await fts.is_empty() is True
        await fts.add("s1.jsonl", "Texte quelconque")
        assert await fts.is_empty() is False
        assert await fts.count() == 1

    @pytest.mark.asyncio
    async def test_rebuild_depuis_jsonl(self, fts: FTSIndex, tmp_path: Path) -> None:
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        (sessions_dir / "2024-01-01_abc.jsonl").write_text(
            json.dumps({"role": "user", "content": "Texte de session rebuild"}) + "\n",
            encoding="utf-8",
        )
        count = await fts.rebuild(sessions_dir)
        assert count == 1
        results = await fts.search("session rebuild")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_vide_retourne_vide(self, fts: FTSIndex) -> None:
        results = await fts.search("")
        assert results == []

    @pytest.mark.asyncio
    async def test_rebuild_ignore_jsonl_vides(self, fts: FTSIndex, tmp_path: Path) -> None:
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        (sessions_dir / "empty.jsonl").write_text("", encoding="utf-8")
        count = await fts.rebuild(sessions_dir)
        assert count == 0


# ── 2. VectorIndex.transcript_to_text ────────────────────────────────────────


class TestTranscriptToText:
    """transcript_to_text est désormais public — vérifie la méthode."""

    def test_extrait_messages(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            json.dumps({"role": "user", "content": "Bonjour"})
            + "\n"
            + json.dumps({"role": "assistant", "content": "Salut chef"})
            + "\n",
            encoding="utf-8",
        )
        text = VectorIndex.transcript_to_text(jsonl)
        assert "user: Bonjour" in text
        assert "assistant: Salut chef" in text

    def test_fichier_absent_retourne_vide(self, tmp_path: Path) -> None:
        text = VectorIndex.transcript_to_text(tmp_path / "absent.jsonl")
        assert text == ""

    def test_ignore_lignes_invalides(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            "pas du json\n" + json.dumps({"role": "user", "content": "Message valide"}) + "\n",
            encoding="utf-8",
        )
        text = VectorIndex.transcript_to_text(jsonl)
        assert "Message valide" in text


# ── 3. CrossSessionRecall ────────────────────────────────────────────────────


@pytest.fixture(autouse=False)
def _force_api_mode() -> Iterator[None]:
    """Force le mode 'api' pour les tests CrossSessionRecall qui vérifient l'appel LLM."""
    from jarvis.kernel.settings import settings

    old = settings.llm_provider
    object.__setattr__(settings, "llm_provider", "api")
    yield
    object.__setattr__(settings, "llm_provider", old)


class TestCrossSessionRecall:
    """CrossSessionRecall combine FTS + vecteur et résume via LLM."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_force_api_mode")
    async def test_recall_retourne_resume(self, tmp_path: Path) -> None:
        from jarvis.providers.memory.consolidation import CrossSessionRecall

        fts = FTSIndex(db_path=tmp_path / "fts.db")
        await fts.add("s1.jsonl", "user: Je veux du café\nassistant: Bien sûr chef")

        mock_vector = MagicMock()
        mock_vector.search = AsyncMock(return_value=[])

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value="Barth veut du café le matin.")

        recall = CrossSessionRecall(llm=mock_llm, fts_index=fts, vector_index=mock_vector)
        result = await recall.recall("café")

        assert result == "Barth veut du café le matin."
        mock_llm.complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_recall_retourne_none_si_index_vide(self, tmp_path: Path) -> None:
        from jarvis.providers.memory.consolidation import CrossSessionRecall

        fts = FTSIndex(db_path=tmp_path / "fts.db")
        mock_vector = MagicMock()
        mock_vector.search = AsyncMock(return_value=[])
        mock_llm = MagicMock()

        recall = CrossSessionRecall(llm=mock_llm, fts_index=fts, vector_index=mock_vector)
        result = await recall.recall("quelque chose")

        assert result is None
        mock_llm.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_recall_retourne_none_si_query_vide(self, tmp_path: Path) -> None:
        from jarvis.providers.memory.consolidation import CrossSessionRecall

        fts = FTSIndex(db_path=tmp_path / "fts.db")
        mock_vector = MagicMock()
        mock_vector.search = AsyncMock(return_value=[])
        mock_llm = MagicMock()

        recall = CrossSessionRecall(llm=mock_llm, fts_index=fts, vector_index=mock_vector)
        result = await recall.recall("   ")

        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_force_api_mode")
    async def test_recall_resilient_si_llm_plante(self, tmp_path: Path) -> None:
        from jarvis.providers.memory.consolidation import CrossSessionRecall

        fts = FTSIndex(db_path=tmp_path / "fts.db")
        await fts.add("s1.jsonl", "Contenu de session")

        mock_vector = MagicMock()
        mock_vector.search = AsyncMock(return_value=[])
        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(side_effect=RuntimeError("LLM down"))

        recall = CrossSessionRecall(llm=mock_llm, fts_index=fts, vector_index=mock_vector)
        result = await recall.recall("session")

        assert result is None  # Pas de propagation d'exception

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_force_api_mode")
    async def test_recall_deduplique_par_doc_id(self, tmp_path: Path) -> None:
        from jarvis.providers.memory.consolidation import CrossSessionRecall

        fts = FTSIndex(db_path=tmp_path / "fts.db")
        await fts.add("s1.jsonl", "Texte FTS")

        # VectorIndex retourne le même doc_id
        mock_vector = MagicMock()
        mock_vector.search = AsyncMock(
            return_value=[
                {"doc_id": "s1.jsonl", "text": "Texte vecteur", "score": 0.9},
            ]
        )

        captured_prompts: list[str] = []

        async def _capture_complete(**kwargs: object) -> str:
            captured_prompts.append(kwargs.get("messages", [{}])[0].get("content", ""))
            return "Résumé."

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(side_effect=_capture_complete)

        recall = CrossSessionRecall(llm=mock_llm, fts_index=fts, vector_index=mock_vector)
        await recall.recall("texte")

        # Le prompt ne doit contenir qu'une seule occurrence de s1.jsonl
        assert captured_prompts[0].count("s1.jsonl") == 1


# ── 4. UserModel ─────────────────────────────────────────────────────────────


class TestUserModel:
    """UserModel : lecture, mise à jour fire-and-forget."""

    @pytest.mark.asyncio
    async def test_load_vide_si_fichier_absent(self, tmp_path: Path) -> None:
        from jarvis.providers.memory.user_model import UserModel

        model = UserModel(llm=MagicMock(), model_path=tmp_path / "user_model.md")
        assert model.load() == ""

    @pytest.mark.asyncio
    async def test_load_lit_fichier(self, tmp_path: Path) -> None:
        from jarvis.providers.memory.user_model import UserModel

        path = tmp_path / "user_model.md"
        path.write_text("- Préfère le café\n", encoding="utf-8")
        model = UserModel(llm=MagicMock(), model_path=path)
        assert "café" in model.load()

    @pytest.mark.asyncio
    async def test_update_ecrit_le_fichier(self, tmp_path: Path) -> None:
        from jarvis.providers.memory.user_model import UserModel

        path = tmp_path / "user_model.md"
        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value="- Aime le café\n- Travaille tôt")

        model = UserModel(llm=mock_llm, model_path=path)
        await model._update("Je veux du café", "Bien sûr chef")

        assert path.exists()
        assert "café" in path.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_fire_cree_une_task(self, tmp_path: Path) -> None:
        from jarvis.providers.memory.user_model import UserModel

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value="- Modèle mis à jour")

        model = UserModel(llm=mock_llm, model_path=tmp_path / "user_model.md")
        model.fire(user_message="msg", assistant_message="rep")
        await asyncio.sleep(0.05)  # laisse la task se terminer

        mock_llm.complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_safe_silencieux_si_llm_plante(self, tmp_path: Path) -> None:
        from jarvis.providers.memory.user_model import UserModel

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(side_effect=RuntimeError("LLM down"))

        model = UserModel(llm=mock_llm, model_path=tmp_path / "user_model.md")
        # Ne doit pas propager l'exception
        await model._update_safe("msg", "rep")


# ── 5. CrossSessionRecallTool ─────────────────────────────────────────────────


class TestCrossSessionRecallTool:
    """CrossSessionRecallTool : délègue à FTS + VectorIndex, formate le résultat."""

    @pytest.mark.asyncio
    async def test_retourne_resultats_fusionnes(self, tmp_path: Path) -> None:
        from jarvis.capabilities.tools.memory import CrossSessionRecallTool

        fts = FTSIndex(db_path=tmp_path / "fts.db")
        await fts.add("s1.jsonl", "user: Je veux du café")

        mock_vector = MagicMock()
        mock_vector.search = AsyncMock(
            return_value=[
                {"doc_id": "s2.jsonl", "text": "assistant: Bon café", "score": 0.8},
            ]
        )

        tool = CrossSessionRecallTool(fts_index=fts, vector_index=mock_vector)
        result = await tool.execute(query="café")

        assert result.is_error is False
        assert "s1.jsonl" in result.content
        assert "s2.jsonl" in result.content

    @pytest.mark.asyncio
    async def test_retourne_aucun_resultat(self, tmp_path: Path) -> None:
        from jarvis.capabilities.tools.memory import CrossSessionRecallTool

        fts = FTSIndex(db_path=tmp_path / "fts.db")
        mock_vector = MagicMock()
        mock_vector.search = AsyncMock(return_value=[])

        tool = CrossSessionRecallTool(fts_index=fts, vector_index=mock_vector)
        result = await tool.execute(query="introuvable xyz")

        assert result.is_error is False
        assert "Aucun résultat" in result.content

    @pytest.mark.asyncio
    async def test_requete_vide_retourne_erreur(self, tmp_path: Path) -> None:
        from jarvis.capabilities.tools.memory import CrossSessionRecallTool

        fts = FTSIndex(db_path=tmp_path / "fts.db")
        mock_vector = MagicMock()
        mock_vector.search = AsyncMock(return_value=[])

        tool = CrossSessionRecallTool(fts_index=fts, vector_index=mock_vector)
        result = await tool.execute(query="")

        assert result.is_error is True


# ── 6. SessionStore.list_all ─────────────────────────────────────────────────


class TestSessionStoreListAll:
    """SessionStore.list_all() retourne tous les fichiers JSONL."""

    def test_list_all_vide(self, tmp_path: Path) -> None:
        from jarvis.providers.memory.sessions import SessionStore

        store = SessionStore(tmp_path / "sessions")
        assert store.list_all() == []

    def test_list_all_retourne_tous(self, tmp_path: Path) -> None:
        from jarvis.providers.memory.sessions import SessionStore

        sessions_dir = tmp_path / "sessions"
        store = SessionStore(sessions_dir)
        for name in ["2024-01-01_a.jsonl", "2024-01-02_b.jsonl", "2024-01-03_c.jsonl"]:
            (sessions_dir / name).write_text("{}", encoding="utf-8")

        all_files = store.list_all()
        assert len(all_files) == 3
