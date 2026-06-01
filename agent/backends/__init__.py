"""Package backends — abstraction d'exécution multi-environnement pour Jarvis."""
from __future__ import annotations

from agent.backends.base import BackendResult, ExecutionBackend
from agent.backends.docker import DockerBackend
from agent.backends.local import LocalBackend
from agent.backends.remote import RemoteBackend
from agent.backends.rpc import RPC_ALLOWED_TOOLS, ScriptRPCRunner
from agent.backends.ssh import SSHBackend

__all__ = [
    "BackendResult",
    "DockerBackend",
    "ExecutionBackend",
    "LocalBackend",
    "RemoteBackend",
    "RPC_ALLOWED_TOOLS",
    "ScriptRPCRunner",
    "SSHBackend",
]
