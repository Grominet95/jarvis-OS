"""
DockerExecutor — exécution isolée dans un container Docker jetable.
Un container par projet : créé au démarrage, détruit à la fin.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from loguru import logger

from jarvis.kernel.settings import settings


class DockerExecutor:
    """Gère l'exécution de commandes dans un container Docker isolé par projet."""

    def __init__(self, workspace_path: str, project_id: str, network: str = "none") -> None:
        self._workspace = Path(workspace_path).resolve()
        self._project_id = project_id
        self._container_name = f"jarvis-worker-{project_id}"
        self._container_id: str | None = None
        self._network = network

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Crée et démarre le container. Le workspace est monté en volume rw."""
        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            self._container_name,
            "--rm",
            f"--memory={settings.docker_memory_limit}",
            f"--cpus={settings.docker_cpu_limit}",
            "--network",
            self._network,
            "--read-only",
            "--tmpfs",
            "/tmp:rw,size=100m",
            "--security-opt",
            "no-new-privileges",
            "--cap-drop",
            "ALL",
            "-v",
            f"{self._workspace}:/workspace:rw",
            "-w",
            "/workspace",
            settings.docker_base_image,
            "tail",
            "-f",
            "/dev/null",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(
                f"Docker start failed for {self._container_name}: {stderr.decode().strip()}"
            )

        self._container_id = stdout.decode().strip()
        logger.info(
            "Docker container started", name=self._container_name, id=self._container_id[:12]
        )

    async def stop(self) -> None:
        """Arrête le container (--rm le supprime automatiquement)."""
        if not self._container_id:
            return
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "stop",
            self._container_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
        logger.info("Docker container stopped", name=self._container_name)
        self._container_id = None

    # ── Execution ─────────────────────────────────────────────────────────────

    async def execute(self, command: str, timeout: int = 30) -> dict:  # noqa: ASYNC109
        """Exécute une commande dans le container avec workdir /workspace."""
        if not self._container_id:
            raise RuntimeError(f"Container {self._container_name} not started")

        cmd = [
            "docker",
            "exec",
            "-w",
            "/workspace",
            self._container_name,
            "sh",
            "-c",
            command,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
            return {
                "success": proc.returncode == 0,
                "stdout": stdout.decode("utf-8", errors="replace")[:8000],
                "stderr": stderr.decode("utf-8", errors="replace")[:2000],
                "returncode": proc.returncode,
            }

        except TimeoutError:
            # Tuer tous les process dans le container puis signaler proprement
            try:
                kill = await asyncio.create_subprocess_exec(
                    "docker",
                    "exec",
                    self._container_name,
                    "sh",
                    "-c",
                    "kill -9 -1",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await kill.communicate()
            except Exception:
                pass
            logger.warning("Docker exec timeout", command=command[:60], timeout=timeout)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Timeout : commande non terminée après {timeout}s — abandon.",
                "returncode": -1,
            }

    async def install_package(self, package: str) -> dict:
        """Installe un package Python dans le container."""
        return await self.execute(
            f"pip install {package} --quiet --no-cache-dir",
            timeout=120,
        )

    # ── Context manager ───────────────────────────────────────────────────────

    async def __aenter__(self) -> DockerExecutor:
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.stop()

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    async def is_available() -> bool:
        """Vérifie que Docker est installé et que le daemon tourne."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "ps",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
            return proc.returncode == 0
        except FileNotFoundError:
            return False
