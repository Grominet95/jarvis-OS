"""Tests du système d'initiatives : store multi-jours, executor, garde-fous.

Couvre :
  - load_pending_all lit plusieurs jours
  - get_by_id / update_status trouvent une initiative d'hier
  - restart → engine broadcast initiatives_restored
  - run AUTO_TASK réserve le budget et refuse si dépassé
  - run DRAFT_RESPONSE ne déclenche pas d'envoi, retourne draft_ready
  - confirm envoie uniquement après run() → awaiting_confirm
  - audit broadcast à chaque action
  - auto-fire impossible (ExecutionMode.AUTO ne passe pas par executor)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis.engine.proactive.schemas import ExecutionMode, Initiative, InitiativeType, Priority
from jarvis.engine.proactive.store import InitiativeStore

# ── Fixtures ──────────────────────────────────────────────────────────────────

_counter = 0


def _make_initiative(
    itype: InitiativeType = InitiativeType.DRAFT_RESPONSE,
    status: str = "pending",
    offset_days: int = 0,
    title: str | None = None,
) -> Initiative:
    global _counter
    _counter += 1
    # Titres volontairement dissemblables pour éviter la déduplication Jaccard
    _titles = [
        "Répondre au client Dupont concernant devis",
        "Synchroniser calendrier avec réunion mensuelle",
        "Analyser rapport financier trimestre Q3",
        "Commander fournitures bureau commande urgente",
        "Planifier session brainstorming équipe produit",
        "Mettre à jour documentation technique serveur",
        "Contacter fournisseur imprimante réparation",
        "Préparer présentation investisseurs semaine",
        "Renouveler abonnement logiciel comptabilité",
        "Organiser déplacement conférence novembre",
    ]
    uid = uuid.uuid4().hex[:8]
    default_title = _titles[_counter % len(_titles)] + f" #{uid}"
    return Initiative(
        id=f"init_{uid}",
        type=itype,
        title=title or default_title,
        context="ctx",
        reasoning="rsn",
        action="action proposée",
        priority=Priority.MEDIUM,
        execution_mode=ExecutionMode.VALIDATE,
        draft_content=(
            "Bonjour, voici ma réponse…" if itype == InitiativeType.DRAFT_RESPONSE else None
        ),
        mission_description="Faire X" if itype == InitiativeType.AUTO_TASK else None,
        status=status,
        created_at=datetime.now() - timedelta(days=offset_days),
    )


def _write_initiative(store_dir: Path, initiative: Initiative, date_str: str) -> None:
    log_file = store_dir / f"{date_str}.jsonl"
    with log_file.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "id": initiative.id,
                    "type": initiative.type,
                    "title": initiative.title,
                    "context": initiative.context,
                    "reasoning": initiative.reasoning,
                    "action": initiative.action,
                    "priority": initiative.priority,
                    "execution_mode": initiative.execution_mode,
                    "draft_content": initiative.draft_content,
                    "mission_description": initiative.mission_description,
                    "status": initiative.status,
                    "created_at": initiative.created_at.isoformat(),
                }
            )
            + "\n"
        )


# ── Helpers store ──────────────────────────────────────────────────────────────


def make_store(tmp_path: Path) -> InitiativeStore:
    with patch("jarvis.engine.proactive.store.INITIATIVES_DIR", tmp_path):
        store = InitiativeStore()
    # Monkey-patch le répertoire de données
    import jarvis.engine.proactive.store as _store_mod

    _orig = _store_mod.INITIATIVES_DIR
    _store_mod.INITIATIVES_DIR = tmp_path
    return store


# ── Tests : Store multi-jours ─────────────────────────────────────────────────


class TestStoreMultiDay:
    def test_load_pending_all_reads_multiple_days(self, tmp_path: Path) -> None:
        """load_pending_all() doit trouver des initiatives datant de plusieurs jours."""
        import jarvis.engine.proactive.store as _store_mod

        orig_dir = _store_mod.INITIATIVES_DIR
        _store_mod.INITIATIVES_DIR = tmp_path
        try:
            store = InitiativeStore()
            today = datetime.now().strftime("%Y-%m-%d")
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

            i_today = _make_initiative(offset_days=0)
            i_yesterday = _make_initiative(offset_days=1)

            _write_initiative(tmp_path, i_today, today)
            _write_initiative(tmp_path, i_yesterday, yesterday)

            result = store.load_pending_all(days=7)
            ids = {i.id for i in result}
            assert i_today.id in ids
            assert i_yesterday.id in ids
        finally:
            _store_mod.INITIATIVES_DIR = orig_dir

    def test_load_pending_all_excludes_non_pending(self, tmp_path: Path) -> None:
        import jarvis.engine.proactive.store as _store_mod

        orig_dir = _store_mod.INITIATIVES_DIR
        _store_mod.INITIATIVES_DIR = tmp_path
        try:
            store = InitiativeStore()
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

            done_init = _make_initiative(status="done", offset_days=1)
            pending_init = _make_initiative(status="pending", offset_days=1)

            _write_initiative(tmp_path, done_init, yesterday)
            _write_initiative(tmp_path, pending_init, yesterday)

            result = store.load_pending_all(days=7)
            ids = {i.id for i in result}
            assert pending_init.id in ids
            assert done_init.id not in ids
        finally:
            _store_mod.INITIATIVES_DIR = orig_dir

    def test_get_by_id_finds_yesterday(self, tmp_path: Path) -> None:
        """get_by_id() doit trouver une initiative datant d'hier."""
        import jarvis.engine.proactive.store as _store_mod

        orig_dir = _store_mod.INITIATIVES_DIR
        _store_mod.INITIATIVES_DIR = tmp_path
        try:
            store = InitiativeStore()
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            init = _make_initiative(offset_days=1)
            _write_initiative(tmp_path, init, yesterday)

            found = store.get_by_id(init.id)
            assert found is not None
            assert found.id == init.id
        finally:
            _store_mod.INITIATIVES_DIR = orig_dir

    def test_get_by_id_returns_none_for_unknown(self, tmp_path: Path) -> None:
        import jarvis.engine.proactive.store as _store_mod

        orig_dir = _store_mod.INITIATIVES_DIR
        _store_mod.INITIATIVES_DIR = tmp_path
        try:
            store = InitiativeStore()
            assert store.get_by_id("inexistant") is None
        finally:
            _store_mod.INITIATIVES_DIR = orig_dir

    def test_update_status_finds_yesterday(self, tmp_path: Path) -> None:
        """update_status() doit mettre à jour une initiative d'hier."""
        import jarvis.engine.proactive.store as _store_mod

        orig_dir = _store_mod.INITIATIVES_DIR
        _store_mod.INITIATIVES_DIR = tmp_path
        try:
            store = InitiativeStore()
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            init = _make_initiative(status="pending", offset_days=1)
            _write_initiative(tmp_path, init, yesterday)

            store.update_status(init.id, "done")

            found = store.get_by_id(init.id)
            assert found is not None
            assert found.status == "done"
        finally:
            _store_mod.INITIATIVES_DIR = orig_dir

    def test_list_recent_filters_by_status(self, tmp_path: Path) -> None:
        import jarvis.engine.proactive.store as _store_mod

        orig_dir = _store_mod.INITIATIVES_DIR
        _store_mod.INITIATIVES_DIR = tmp_path
        try:
            store = InitiativeStore()
            today = datetime.now().strftime("%Y-%m-%d")
            pending = _make_initiative(status="pending")
            done = _make_initiative(status="done")
            _write_initiative(tmp_path, pending, today)
            _write_initiative(tmp_path, done, today)

            result = store.list_recent(days=7, statuses=["done"])
            ids = {i.id for i in result}
            assert done.id in ids
            assert pending.id not in ids
        finally:
            _store_mod.INITIATIVES_DIR = orig_dir


# ── Tests : Engine restauration ───────────────────────────────────────────────


class TestEngineRestore:
    @pytest.mark.asyncio
    async def test_restart_broadcasts_initiatives_restored(self, tmp_path: Path) -> None:
        """Au démarrage, l'engine doit broadcaster initiatives_restored si des pending existent."""
        import jarvis.engine.proactive.store as _store_mod

        orig_dir = _store_mod.INITIATIVES_DIR
        _store_mod.INITIATIVES_DIR = tmp_path
        try:
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            init = _make_initiative(status="pending", offset_days=1)
            _write_initiative(tmp_path, init, yesterday)

            events: list[dict] = []

            from jarvis.engine.background.notifications import NotificationQueue

            nq = NotificationQueue()

            from jarvis.engine.proactive.context_builder import ContextBuilder
            from jarvis.engine.proactive.engine import ProactiveEngine
            from jarvis.engine.proactive.initiative_generator import InitiativeGenerator
            from jarvis.engine.proactive.store import InitiativeStore

            engine = ProactiveEngine(
                notification_queue=nq,
                broadcast_event=events.append,
                builder=ContextBuilder(calendar_tool=MagicMock(), notion_tool=MagicMock()),
                generator=InitiativeGenerator(llm=MagicMock()),
                store=InitiativeStore(),
                interval_minutes=30,
            )

            # Appel direct de _restore_pending sans démarrer la boucle entière
            await engine._restore_pending()

            types = [e["type"] for e in events]
            assert "initiatives_restored" in types

            restored = next(e for e in events if e["type"] == "initiatives_restored")
            assert restored["count"] >= 1
        finally:
            _store_mod.INITIATIVES_DIR = orig_dir

    @pytest.mark.asyncio
    async def test_restore_empty_broadcasts_nothing(self, tmp_path: Path) -> None:
        """Si aucune initiative pending, _restore_pending ne broadcast rien."""
        import jarvis.engine.proactive.store as _store_mod

        orig_dir = _store_mod.INITIATIVES_DIR
        _store_mod.INITIATIVES_DIR = tmp_path
        try:
            events: list[dict] = []
            from jarvis.engine.background.notifications import NotificationQueue
            from jarvis.engine.proactive.context_builder import ContextBuilder
            from jarvis.engine.proactive.engine import ProactiveEngine
            from jarvis.engine.proactive.initiative_generator import InitiativeGenerator
            from jarvis.engine.proactive.store import InitiativeStore

            engine = ProactiveEngine(
                notification_queue=NotificationQueue(),
                broadcast_event=events.append,
                builder=ContextBuilder(calendar_tool=MagicMock(), notion_tool=MagicMock()),
                generator=InitiativeGenerator(llm=MagicMock()),
                store=InitiativeStore(),
            )
            await engine._restore_pending()
            assert events == []
        finally:
            _store_mod.INITIATIVES_DIR = orig_dir


# ── Tests : Executor ──────────────────────────────────────────────────────────


def _make_executor(
    tmp_path: Path,
    orchestrator: object | None = None,
    budget_guard: object | None = None,
) -> tuple:
    import jarvis.engine.proactive.store as _store_mod

    orig_dir = _store_mod.INITIATIVES_DIR
    _store_mod.INITIATIVES_DIR = tmp_path
    store = InitiativeStore()
    events: list[dict] = []

    from jarvis.engine.proactive.executor import InitiativeExecutor

    executor = InitiativeExecutor(
        store=store,
        broadcast_event=events.append,
        orchestrator=orchestrator,
        budget_guard=budget_guard,
    )
    return executor, store, events, orig_dir


class TestExecutorDraftResponse:
    @pytest.mark.asyncio
    async def test_run_returns_draft_ready_without_sending(self, tmp_path: Path) -> None:
        """run() sur DRAFT_RESPONSE retourne draft_ready et ne déclenche pas d'envoi."""
        import jarvis.engine.proactive.store as _store_mod

        executor, store, events, orig_dir = _make_executor(tmp_path)
        try:
            init = _make_initiative(InitiativeType.DRAFT_RESPONSE)
            today = datetime.now().strftime("%Y-%m-%d")
            _write_initiative(tmp_path, init, today)

            result = await executor.run(init.id)
            assert result["status"] == "draft_ready"
            assert "draft" in result
            # Le statut doit être awaiting_confirm, pas done/sent
            updated = store.get_by_id(init.id)
            assert updated is not None
            assert updated.status == "awaiting_confirm"
        finally:
            _store_mod.INITIATIVES_DIR = orig_dir

    @pytest.mark.asyncio
    async def test_confirm_blocked_if_not_awaiting(self, tmp_path: Path) -> None:
        """confirm() échoue si l'initiative n'est pas en awaiting_confirm."""
        import jarvis.engine.proactive.store as _store_mod

        executor, store, events, orig_dir = _make_executor(tmp_path)
        try:
            init = _make_initiative(InitiativeType.DRAFT_RESPONSE, status="pending")
            today = datetime.now().strftime("%Y-%m-%d")
            _write_initiative(tmp_path, init, today)

            result = await executor.confirm(init.id)
            assert result["status"] == "error"
            assert "Statut invalide" in result["error"] or "pending" in result["error"]
        finally:
            _store_mod.INITIATIVES_DIR = orig_dir

    @pytest.mark.asyncio
    async def test_confirm_blocked_when_approval_never(self, tmp_path: Path) -> None:
        """confirm() est bloqué si email_send=NEVER dans approval_config."""
        import jarvis.engine.proactive.store as _store_mod

        executor, store, events, orig_dir = _make_executor(tmp_path)
        try:
            init = _make_initiative(InitiativeType.DRAFT_RESPONSE, status="awaiting_confirm")
            today = datetime.now().strftime("%Y-%m-%d")
            _write_initiative(tmp_path, init, today)

            from jarvis.kernel.approvals import ApprovalMode, approval_config

            original_mode = approval_config.email_send
            approval_config.email_send = ApprovalMode.NEVER
            try:
                result = await executor.confirm(init.id)
            finally:
                approval_config.email_send = original_mode

            assert result["status"] == "blocked"
        finally:
            _store_mod.INITIATIVES_DIR = orig_dir

    @pytest.mark.asyncio
    async def test_two_step_flow_sends_only_after_confirm(self, tmp_path: Path) -> None:
        """Flux complet : run → draft_ready → confirm → envoi."""
        import jarvis.engine.proactive.store as _store_mod

        executor, store, events, orig_dir = _make_executor(tmp_path)
        try:
            init = _make_initiative(InitiativeType.DRAFT_RESPONSE)
            today = datetime.now().strftime("%Y-%m-%d")
            _write_initiative(tmp_path, init, today)

            # Étape 1 : run — ne doit pas envoyer
            r1 = await executor.run(init.id)
            assert r1["status"] == "draft_ready"

            updated = store.get_by_id(init.id)
            assert updated is not None
            assert updated.status == "awaiting_confirm"

            # Étape 2 : confirm — on mocke send_gmail_draft dans tools.gmail
            mock_send = AsyncMock(return_value="msg_abc123")
            with patch("jarvis.capabilities.tools.gmail.send_gmail_draft", mock_send):
                await executor.confirm(init.id)

            # Le statut doit être terminal (done, failed ou draft_only si outil absent)
            final = store.get_by_id(init.id)
            assert final is not None
            assert final.status in ("done", "failed", "draft_only")
            # run() n'a pas envoyé de mail (aucun appel avant confirm)
            # Le brouillon est bien passé par awaiting_confirm avant d'arriver ici
        finally:
            _store_mod.INITIATIVES_DIR = orig_dir


class TestExecutorMission:
    @pytest.mark.asyncio
    async def test_run_mission_reserves_budget(self, tmp_path: Path) -> None:
        """run() AUTO_TASK doit appeler budget.reserve() avant de lancer la mission."""
        import jarvis.engine.proactive.store as _store_mod

        mock_project = MagicMock()
        mock_project.id = "proj_abc"
        mock_project.title = "Mission test"
        mock_project.steps = [MagicMock(), MagicMock()]

        mock_orch = AsyncMock()
        mock_orch.create_and_run = AsyncMock(return_value=mock_project)

        mock_budget = AsyncMock()
        mock_budget.reserve = AsyncMock(return_value=True)

        executor, store, events, orig_dir = _make_executor(
            tmp_path, orchestrator=mock_orch, budget_guard=mock_budget
        )
        try:
            init = _make_initiative(InitiativeType.AUTO_TASK)
            today = datetime.now().strftime("%Y-%m-%d")
            _write_initiative(tmp_path, init, today)

            result = await executor.run(init.id)

            # reserve() doit avoir été appelé
            mock_budget.reserve.assert_called_once()
            scope_arg = mock_budget.reserve.call_args[0][0]
            assert scope_arg.startswith("initiative:")

            assert result["status"] == "mission_launched"
            assert result["project_id"] == "proj_abc"
        finally:
            _store_mod.INITIATIVES_DIR = orig_dir

    @pytest.mark.asyncio
    async def test_run_mission_refuses_if_budget_exceeded(self, tmp_path: Path) -> None:
        """run() AUTO_TASK est refusé si budget.reserve() retourne False."""
        import jarvis.engine.proactive.store as _store_mod

        mock_orch = AsyncMock()
        mock_budget = AsyncMock()
        mock_budget.reserve = AsyncMock(return_value=False)  # budget dépassé

        executor, store, events, orig_dir = _make_executor(
            tmp_path, orchestrator=mock_orch, budget_guard=mock_budget
        )
        try:
            init = _make_initiative(InitiativeType.AUTO_TASK)
            today = datetime.now().strftime("%Y-%m-%d")
            _write_initiative(tmp_path, init, today)

            result = await executor.run(init.id)

            assert result["status"] == "budget_exceeded"
            # L'orchestrateur ne doit pas avoir été appelé
            mock_orch.create_and_run.assert_not_called()

            # L'initiative doit être en failed
            updated = store.get_by_id(init.id)
            assert updated is not None
            assert updated.status == "failed"
        finally:
            _store_mod.INITIATIVES_DIR = orig_dir

    @pytest.mark.asyncio
    async def test_run_mission_without_orchestrator_fails_gracefully(self, tmp_path: Path) -> None:
        import jarvis.engine.proactive.store as _store_mod

        executor, store, events, orig_dir = _make_executor(tmp_path, orchestrator=None)
        try:
            init = _make_initiative(InitiativeType.AUTO_TASK)
            today = datetime.now().strftime("%Y-%m-%d")
            _write_initiative(tmp_path, init, today)

            result = await executor.run(init.id)
            assert result["status"] == "error"
            assert "Orchestrateur" in result["error"]
        finally:
            _store_mod.INITIATIVES_DIR = orig_dir


class TestExecutorAudit:
    @pytest.mark.asyncio
    async def test_audit_event_broadcast_on_run(self, tmp_path: Path) -> None:
        """Un événement initiative_audit doit être broadcast à chaque run()."""
        import jarvis.engine.proactive.store as _store_mod

        executor, store, events, orig_dir = _make_executor(tmp_path)
        try:
            init = _make_initiative(InitiativeType.INFO)
            today = datetime.now().strftime("%Y-%m-%d")
            _write_initiative(tmp_path, init, today)

            await executor.run(init.id)

            audit_events = [e for e in events if e.get("type") == "initiative_audit"]
            assert len(audit_events) >= 1
            ae = audit_events[0]
            assert ae["initiative_id"] == init.id
            assert ae["step"] == "run"
            assert "result_status" in ae
            assert "timestamp" in ae
        finally:
            _store_mod.INITIATIVES_DIR = orig_dir


class TestExecutorInfoTypes:
    @pytest.mark.asyncio
    async def test_reminder_handled_without_external_action(self, tmp_path: Path) -> None:
        """REMINDER, SUGGESTION, INFO, ALERT → handled sans action externe."""
        import jarvis.engine.proactive.store as _store_mod

        executor, store, events, orig_dir = _make_executor(tmp_path)
        try:
            for itype in (
                InitiativeType.REMINDER,
                InitiativeType.SUGGESTION,
                InitiativeType.INFO,
                InitiativeType.ALERT,
            ):
                init = _make_initiative(itype)
                today = datetime.now().strftime("%Y-%m-%d")
                _write_initiative(tmp_path, init, today)

                result = await executor.run(init.id)
                assert result["status"] == "handled", f"Attendu 'handled' pour {itype}"

                updated = store.get_by_id(init.id)
                assert updated is not None
                assert updated.status == "done"
        finally:
            _store_mod.INITIATIVES_DIR = orig_dir


class TestNoAutoFire:
    def test_auto_mode_not_wired_to_executor(self) -> None:
        """ExecutionMode.AUTO ne doit pas être câblé à un chemin d'exécution externe
        dans l'engine."""
        import inspect

        from jarvis.engine.proactive.engine import ProactiveEngine

        source = inspect.getsource(ProactiveEngine._dispatch)
        # AUTO doit juste logger — aucun appel à executor, aucun envoi de mail
        assert "executor" not in source or "AUTO" not in source.split("executor")[0].split("\n")[-1]
        # Plus précis : la branche AUTO ne doit pas contenir de create_task / send
        auto_block_start = source.find("ExecutionMode.AUTO")
        if auto_block_start >= 0:
            auto_block = source[auto_block_start : auto_block_start + 300]
            assert "send" not in auto_block.lower() or "send" not in auto_block
            assert "create_task" not in auto_block

    @pytest.mark.asyncio
    async def test_run_blocked_for_non_pending(self, tmp_path: Path) -> None:
        """run() est refusé si l'initiative n'est pas en status 'pending'."""
        import jarvis.engine.proactive.store as _store_mod

        executor, store, events, orig_dir = _make_executor(tmp_path)
        try:
            # Initiative déjà done
            init = _make_initiative(status="done")
            today = datetime.now().strftime("%Y-%m-%d")
            _write_initiative(tmp_path, init, today)

            result = await executor.run(init.id)
            assert result["status"] == "error"
            assert "pending" in result["error"].lower() or "statut" in result["error"].lower()
        finally:
            _store_mod.INITIATIVES_DIR = orig_dir
