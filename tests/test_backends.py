"""Tests des backends d'exécution et des outils de délégation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis.engine.mission.backend_factory import get_backend
from jarvis.engine.mission.backends.base import ExecutionBackend
from jarvis.engine.mission.backends.docker import DockerBackend
from jarvis.engine.mission.backends.local import LocalBackend
from jarvis.engine.mission.backends.remote import RemoteBackend
from jarvis.engine.mission.backends.rpc import ScriptRPCRunner, _build_stub
from jarvis.engine.mission.backends.ssh import SSHBackend
from jarvis.kernel.backends import BackendsConfig, BackendType, SSHConfig

pytestmark = pytest.mark.integration  # CDC §A.1.5 — exercice Docker backend

# ── Helpers ───────────────────────────────────────────────────────────────────


def _ok(stdout: str = "ok") -> dict:
    return {"success": True, "stdout": stdout, "stderr": "", "returncode": 0}


def _fail(stderr: str = "erreur") -> dict:
    return {"success": False, "stdout": "", "stderr": stderr, "returncode": -1}


# ── 1. Sélection de backend ───────────────────────────────────────────────────


class TestGetBackend:
    """get_backend() retourne le bon backend selon la config et les paramètres."""

    def test_auto_avec_docker_executor_retourne_docker(self, tmp_path: Path) -> None:
        executor = MagicMock()
        with patch(
            "jarvis.engine.mission.backend_factory.load_backends_config",
            return_value=BackendsConfig(),
        ):
            with patch("jarvis.engine.mission.backend_factory.settings") as mock_settings:
                mock_settings.docker_enabled = True
                backend = get_backend(str(tmp_path), docker_executor=executor)
        assert isinstance(backend, DockerBackend)

    def test_auto_sans_docker_retourne_local(self, tmp_path: Path) -> None:
        with patch(
            "jarvis.engine.mission.backend_factory.load_backends_config",
            return_value=BackendsConfig(),
        ):
            with patch("jarvis.engine.mission.backend_factory.settings") as mock_settings:
                mock_settings.docker_enabled = False
                backend = get_backend(str(tmp_path), docker_executor=None)
        assert isinstance(backend, LocalBackend)

    def test_docker_explicite_sans_executor_retourne_none(self, tmp_path: Path) -> None:
        with patch(
            "jarvis.engine.mission.backend_factory.load_backends_config",
            return_value=BackendsConfig(default_backend=BackendType.DOCKER),
        ):
            with patch("jarvis.engine.mission.backend_factory.settings") as mock_settings:
                mock_settings.docker_enabled = True
                backend = get_backend(str(tmp_path), docker_executor=None)
        assert backend is None

    def test_ssh_sans_host_retourne_none(self, tmp_path: Path) -> None:
        cfg = BackendsConfig(default_backend=BackendType.SSH, ssh=SSHConfig(host="", user=""))
        with patch("jarvis.engine.mission.backend_factory.load_backends_config", return_value=cfg):
            backend = get_backend(str(tmp_path))
        assert backend is None

    def test_ssh_avec_config_retourne_ssh_backend(self, tmp_path: Path) -> None:
        cfg = BackendsConfig(
            default_backend=BackendType.SSH,
            ssh=SSHConfig(host="host.example.com", user="jarvis"),
        )
        with patch("jarvis.engine.mission.backend_factory.load_backends_config", return_value=cfg):
            backend = get_backend(str(tmp_path))
        assert isinstance(backend, SSHBackend)

    def test_remote_retourne_remote_backend(self, tmp_path: Path) -> None:
        cfg = BackendsConfig(default_backend=BackendType.REMOTE, remote_provider="modal")
        with patch("jarvis.engine.mission.backend_factory.load_backends_config", return_value=cfg):
            backend = get_backend(str(tmp_path))
        assert isinstance(backend, RemoteBackend)


# ── 2. DockerBackend délègue à docker_executor ───────────────────────────────


class TestDockerBackend:
    """DockerBackend.execute() délègue bien à DockerExecutor."""

    @pytest.mark.asyncio
    async def test_execute_delegue_au_executor(self) -> None:
        executor = MagicMock()
        executor.execute = AsyncMock(return_value=_ok("hello docker"))

        backend = DockerBackend(executor)
        result = await backend.execute("echo hello", timeout=10)

        executor.execute.assert_awaited_once_with("echo hello", 10)
        assert result["success"] is True
        assert result["stdout"] == "hello docker"

    @pytest.mark.asyncio
    async def test_execute_sans_executor_retourne_erreur(self) -> None:
        backend = DockerBackend(None)
        result = await backend.execute("echo hello")
        assert result["success"] is False
        assert "non démarré" in result["stderr"]

    @pytest.mark.asyncio
    async def test_is_available_respecte_docker_enabled(self) -> None:
        executor = MagicMock()
        backend = DockerBackend(executor)
        with patch("jarvis.engine.mission.backends.docker.settings") as mock_settings:
            mock_settings.docker_enabled = False
            with patch(
                "jarvis.engine.mission.docker_executor.DockerExecutor.is_available",
                new_callable=AsyncMock,
                return_value=True,
            ):
                assert await backend.is_available() is False


# ── 3. Refus si aucun backend sûr ────────────────────────────────────────────


class TestRefusSansBackendSur:
    """LocalBackend refuse si allow_unsandboxed_exec est False/absent."""

    @pytest.mark.asyncio
    async def test_local_refuse_sans_optin(self, tmp_path: Path) -> None:
        backend = LocalBackend(str(tmp_path))
        with patch("jarvis.engine.mission.backends.local.settings") as mock_settings:
            mock_settings.allow_unsandboxed_exec = False
            result = await backend.execute("echo test")
        assert result["success"] is False
        assert "ALLOW_UNSANDBOXED_EXEC" in result["stderr"]

    @pytest.mark.asyncio
    async def test_local_is_available_false_sans_optin(self, tmp_path: Path) -> None:
        backend = LocalBackend(str(tmp_path))
        with patch("jarvis.engine.mission.backends.local.settings") as mock_settings:
            mock_settings.allow_unsandboxed_exec = False
            assert await backend.is_available() is False

    @pytest.mark.asyncio
    async def test_remote_toujours_indisponible(self) -> None:
        backend = RemoteBackend("modal")
        assert await backend.is_available() is False
        result = await backend.execute("echo test")
        assert result["success"] is False
        assert "non implémenté" in result["stderr"]


# ── 4. spawn_subagent renvoie un résumé ──────────────────────────────────────


class TestSpawnSubagent:
    """SpawnSubagentTool lance un sous-agent isolé et retourne un résumé."""

    @pytest.mark.asyncio
    async def test_spawn_retourne_resume(self) -> None:
        from jarvis.capabilities.tools.subagent import SpawnSubagentTool

        mock_agent = MagicMock()
        mock_agent.respond_tools = AsyncMock(return_value="Résultat de la tâche déléguée.")

        tool = SpawnSubagentTool(agent=mock_agent)
        result = await tool.execute(task="Analyse le fichier data.csv")

        assert result.is_error is False
        assert "Sous-agent terminé" in result.content
        assert "Résultat de la tâche" in result.content

    @pytest.mark.asyncio
    async def test_spawn_session_fraiche_sans_historique(self) -> None:
        from jarvis.capabilities.tools.subagent import SpawnSubagentTool
        from jarvis.engine.session import Session

        captured_sessions: list[Session] = []

        async def _capture_session(session: Session) -> str:
            captured_sessions.append(session)
            return "ok"

        mock_agent = MagicMock()
        mock_agent.respond_tools = AsyncMock(side_effect=_capture_session)

        tool = SpawnSubagentTool(agent=mock_agent)
        await tool.execute(task="tâche test")

        assert len(captured_sessions) == 1
        # La session reçue ne doit contenir que le message utilisateur
        assert len(captured_sessions[0].messages) == 1
        assert captured_sessions[0].messages[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_spawn_erreur_retourne_is_error(self) -> None:
        from jarvis.capabilities.tools.subagent import SpawnSubagentTool

        mock_agent = MagicMock()
        mock_agent.respond_tools = AsyncMock(side_effect=RuntimeError("LLM down"))

        tool = SpawnSubagentTool(agent=mock_agent)
        result = await tool.execute(task="tâche impossible")

        assert result.is_error is True
        assert "LLM down" in result.content


# ── 5. Script-RPC exécute une séquence d'outils ──────────────────────────────


class TestScriptRPC:
    """ScriptRPCRunner exécute un script et dispatch les appels RPC."""

    @pytest.mark.asyncio
    async def test_script_simple_stdout(self, tmp_path: Path) -> None:
        mock_registry = MagicMock()
        mock_registry.schemas = MagicMock(return_value=[])

        mock_backend = MagicMock(spec=ExecutionBackend)
        mock_backend.execute = AsyncMock(return_value=_ok("Bonjour depuis le script"))

        runner = ScriptRPCRunner(mock_backend, mock_registry, tmp_path)
        result = await runner.run("print('Bonjour depuis le script')", timeout=10)

        assert result["success"] is True
        assert "Bonjour depuis le script" in result["stdout"]
        assert result["tool_calls"] == 0

    @pytest.mark.asyncio
    async def test_script_appelle_outil_rpc(self, tmp_path: Path) -> None:
        from jarvis.capabilities.tools.base import ToolResult

        mock_registry = MagicMock()
        mock_registry.schemas = MagicMock(return_value=[{"name": "weather"}])
        mock_registry.call = AsyncMock(return_value=ToolResult(content="Soleil 22°C"))

        call_received: list[dict] = []

        async def fake_execute(command: str, timeout: int = 60) -> dict:  # noqa: ASYNC109
            rpc_dir_path = tmp_path / ".jarvis_rpc"
            # Simuler le script : écrire un fichier request
            for rpc_run in sorted(rpc_dir_path.iterdir()):
                req = rpc_run / "req_test001.json"
                req.write_text(json.dumps({"tool": "weather", "inputs": {"city": "Lyon"}}))
                call_received.append({"run": rpc_run.name})
                break
            # Attendre que le dispatcher traite la requête
            await asyncio.sleep(0.3)
            return _ok("météo ok")

        mock_backend = MagicMock(spec=ExecutionBackend)
        mock_backend.execute = AsyncMock(side_effect=fake_execute)

        runner = ScriptRPCRunner(mock_backend, mock_registry, tmp_path)
        result = await runner.run("import jarvis_tools; print(jarvis_tools.weather(city='Lyon'))")

        # Le dispatcher a vu et traité l'appel
        mock_registry.call.assert_awaited()
        assert result["success"] is True

    def test_build_stub_genere_fonctions(self) -> None:
        stub = _build_stub("/rpc/dir", ["weather", "browser"])
        assert "def weather(**kwargs):" in stub
        assert "def browser(**kwargs):" in stub
        assert "_call('weather'" in stub
        assert "_RPC_DIR = '/rpc/dir'" in stub

    @pytest.mark.asyncio
    async def test_outil_non_autorise_retourne_erreur_rpc(self, tmp_path: Path) -> None:
        mock_registry = MagicMock()
        mock_registry.schemas = MagicMock(return_value=[])
        mock_registry.call = AsyncMock()

        async def fake_execute(command: str, timeout: int = 60) -> dict:  # noqa: ASYNC109
            rpc_dir_path = tmp_path / ".jarvis_rpc"
            for rpc_run in sorted(rpc_dir_path.iterdir()):
                req = rpc_run / "req_badtool.json"
                req.write_text(json.dumps({"tool": "rm_rf", "inputs": {}}))
                break
            await asyncio.sleep(0.3)
            return _ok("")

        mock_backend = MagicMock(spec=ExecutionBackend)
        mock_backend.execute = AsyncMock(side_effect=fake_execute)

        runner = ScriptRPCRunner(mock_backend, mock_registry, tmp_path)
        await runner.run("import jarvis_tools")

        # L'outil interdit ne doit PAS avoir été appelé
        mock_registry.call.assert_not_awaited()


# ── 6. worker_cli route via le backend ───────────────────────────────────────


class TestWorkerCLIRouting:
    """WorkerCLITool.execute() route via get_backend()."""

    @pytest.mark.asyncio
    async def test_route_vers_docker_si_dispo(self, tmp_path: Path) -> None:
        from jarvis.engine.mission.worker_cli import WorkerCLITool

        mock_docker = MagicMock()
        mock_docker.execute = AsyncMock(return_value=_ok("via docker"))

        cli = WorkerCLITool(str(tmp_path), docker_executor=mock_docker)

        with patch(
            "jarvis.engine.mission.backend_factory.load_backends_config",
            return_value=BackendsConfig(),
        ):
            with patch("jarvis.engine.mission.backend_factory.settings") as s:
                s.docker_enabled = True
                result = await cli.execute("ls")

        assert result["success"] is True
        assert result["stdout"] == "via docker"

    @pytest.mark.asyncio
    async def test_refuse_si_aucun_backend(self, tmp_path: Path) -> None:
        from jarvis.engine.mission.worker_cli import WorkerCLITool

        cli = WorkerCLITool(str(tmp_path))

        with patch(
            "jarvis.engine.mission.backend_factory.load_backends_config",
            return_value=BackendsConfig(default_backend=BackendType.DOCKER),
        ):
            with patch("jarvis.engine.mission.backend_factory.settings") as s:
                s.docker_enabled = True
                # docker_executor=None + DOCKER explicite → get_backend retourne None
                result = await cli.execute("ls")

        assert result["success"] is False
        assert "backend" in result["stderr"].lower()
