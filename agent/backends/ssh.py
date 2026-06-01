"""SSHBackend — exécution sur hôte distant via SSH avec ControlMaster."""
from __future__ import annotations

import asyncio
import hashlib
import shutil
import tempfile
from pathlib import Path

from loguru import logger

from agent.backends.base import BackendResult, ExecutionBackend


class SSHBackend(ExecutionBackend):
    """Spawn-per-call SSH avec réutilisation de connexion (ControlMaster, persist=60s).

    Le répertoire de travail distant est créé si absent.
    Hash court du user@host:port pour le socket ControlMaster (≤ 104 octets — macOS).

    Architecture inspirée de hermes-agent SSHEnvironment
    (MIT License, NousResearch — voir notices/exec-backends.md).
    """

    def __init__(
        self,
        host: str,
        user: str,
        port: int = 22,
        key_path: str = "",
        remote_workdir: str = "~/jarvis-workspace",
    ) -> None:
        self._host         = host
        self._user         = user
        self._port         = port
        self._key_path     = key_path
        self._remote_workdir = remote_workdir

        _tag = hashlib.sha1(f"{user}@{host}:{port}".encode()).hexdigest()[:12]
        _ctl_dir = Path(tempfile.gettempdir()) / "jarvis-ssh"
        _ctl_dir.mkdir(parents=True, exist_ok=True)
        self._control_path = str(_ctl_dir / f"cm-{_tag}")

    @property
    def name(self) -> str:
        return f"SSHBackend({self._user}@{self._host}:{self._port})"

    async def is_available(self) -> bool:
        return bool(shutil.which("ssh"))

    def _build_cmd(self, command: str) -> list[str]:
        """Construit la commande ssh avec ControlMaster et wrap workdir."""
        wrapped = (
            f"mkdir -p {self._remote_workdir} 2>/dev/null; "
            f"cd {self._remote_workdir} && {command}"
        )
        args: list[str] = [
            "ssh",
            "-o", f"ControlPath={self._control_path}",
            "-o", "ControlMaster=auto",
            "-o", "ControlPersist=60s",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "BatchMode=yes",
            "-p", str(self._port),
        ]
        if self._key_path:
            args += ["-i", self._key_path]
        args += [f"{self._user}@{self._host}", wrapped]
        return args

    async def execute(self, command: str, timeout: int = 60) -> BackendResult:  # noqa: ASYNC109
        cmd = self._build_cmd(command)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            logger.debug(
                "SSHBackend exec",
                host=self._host,
                cmd=command[:60],
                rc=proc.returncode,
            )
            return BackendResult(
                success=proc.returncode == 0,
                stdout=stdout.decode("utf-8", errors="replace")[:8000],
                stderr=stderr.decode("utf-8", errors="replace")[:2000],
                returncode=proc.returncode,
            )
        except TimeoutError:
            return BackendResult(
                success=False,
                stdout="",
                stderr=f"SSH timeout après {timeout}s ({self._host})",
                returncode=-1,
            )
        except Exception as exc:
            return BackendResult(
                success=False,
                stdout="",
                stderr=f"SSHBackend erreur : {exc}",
                returncode=-1,
            )
