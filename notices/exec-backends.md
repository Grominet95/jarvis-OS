# Attribution — Execution Backends

Les fichiers `agent/backends/` (LocalBackend, DockerBackend, SSHBackend,
RemoteBackend, ScriptRPCRunner) s'inspirent de l'architecture du projet
**hermes-agent** (https://github.com/NousResearch/hermes-agent).

## Éléments repris

| Fichier Jarvis                     | Référence hermes-agent                                   |
|------------------------------------|----------------------------------------------------------|
| `agent/backends/base.py`           | `tools/environments/base.py` — ABC + contrat execute()  |
| `agent/backends/ssh.py`            | `tools/environments/ssh.py` — ControlMaster, hash court |
| `agent/backends/remote.py`         | `providers/managed_modal.py`, `providers/daytona.py`    |
| `agent/backends/rpc.py`            | `tools/code_execution_tool.py` — transport fichiers RPC |
| `tools/subagent.py` (SpawnSubagent)| `tools/delegate_tool.py` — contexte isolé, résumé       |
| `tools/subagent.py` (ScriptRPC)    | `tools/code_execution_tool.py` — script-via-RPC         |

## Différences architecturales

- Transport RPC : fichiers JSON dans le workspace partagé au lieu d'Unix Domain Sockets,
  ce qui fonctionne uniformément en local ET en Docker (volume monté).
- Backends simplifiés : le modèle spawn-per-call de hermes est conservé mais les
  snapshots de session shell ne sont pas repris (Jarvis passe par WorkerCLITool).
- Pas de ControlPersist multi-hôte ni de gestion de clés SSH temporaires.
- La sous-classe RemoteBackend remplace les providers Modal/Daytona complets.

## Licence source

```
MIT License

Copyright (c) 2025 Nous Research

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
