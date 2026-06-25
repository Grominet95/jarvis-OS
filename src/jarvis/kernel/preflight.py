# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""preflight.py — Diagnostic de démarrage.

Détecte les problèmes les plus courants AVANT de lancer l'API et les explique
clairement (cause + fix), pour ne pas laisser l'utilisateur face à un traceback
Python illisible ou à un « API timeout » opaque.

Lancé par le launcher (`jarvis` / `jarvis.ps1`) juste avant `python -m jarvis.app`.
N'IMPORTE QUE LA STDLIB au niveau module : il doit pouvoir tourner même si les
dépendances du projet sont cassées — c'est précisément ce qu'il vérifie.

Sortie : 0 si tout est OK (démarrage autorisé), 1 si un problème bloquant est
détecté (le message d'explication est déjà affiché).
"""

from __future__ import annotations

import importlib
import os
import socket
import sys
from pathlib import Path

_USE_COLOR = sys.stderr.isatty() and os.name != "nt"


def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _USE_COLOR else s


def _block(marker: str, color: str, title: str, body: str) -> None:
    print("\n" + _c(color, f"{marker} {title}"), file=sys.stderr)
    for line in body.strip("\n").splitlines():
        print("  " + line, file=sys.stderr)


def _err(title: str, body: str) -> None:
    _block("[ERREUR]", "91", title, body)


def _warn(title: str, body: str) -> None:
    _block("[ATTENTION]", "93", title, body)


# ── 1. Version de Python ──────────────────────────────────────────────────────


def check_python() -> bool:
    if sys.version_info < (3, 11):  # noqa: UP036 — détection runtime volontaire
        _err(
            "Version de Python trop ancienne",
            f"""
Jarvis a besoin de Python 3.11 ou plus récent.
Version détectée : {sys.version.split()[0]}

POURQUOI : le code utilise des fonctionnalités de Python 3.11 (typing, etc.).
FIX : installe Python 3.11+ puis recrée l'environnement avec « uv sync ».
""",
        )
        return False
    return True


# ── 2. Dépendances nécessaires au démarrage ───────────────────────────────────

# module importable -> rôle (pour un message compréhensible). Ce sont les paquets
# requis pour que l'API démarre ; les binaires natifs (pydantic_core) sont les
# premiers suspects quand « uv sync » a échoué ou que le venv a été déplacé/copié.
_CRITICAL_DEPS: dict[str, str] = {
    "fastapi": "le serveur web de l'API",
    "uvicorn": "le moteur qui fait tourner l'API",
    "pydantic": "la validation de la configuration",
    "pydantic_core": "le cœur compilé de pydantic (binaire natif)",
    "httpx": "les appels réseau (LLM, Notion, YouTube…)",
    "numpy": "le calcul (mémoire vectorielle)",
    "loguru": "les logs",
}


def check_deps() -> bool:
    missing: list[tuple[str, str, str]] = []
    for mod, role in _CRITICAL_DEPS.items():
        try:
            importlib.import_module(mod)
        except Exception as e:  # ImportError, mais aussi erreurs de binaire natif
            missing.append((mod, role, type(e).__name__))

    if not missing:
        return True

    lines = ["Des paquets nécessaires au démarrage de l'API sont absents ou cassés :", ""]
    for mod, role, err in missing:
        lines.append(f"  - {mod}  ({role})  [{err}]")
    lines += [
        "",
        "POURQUOI : c'est presque toujours l'environnement Python (.venv), PAS l'API LLM.",
        "Causes typiques : « uv sync » a échoué, le .venv a été copié/déplacé d'une",
        "autre machine, ou un binaire natif (pydantic_core, onnxruntime) ne correspond",
        "pas à ton OS/CPU.",
        "",
        "FIX, dans le dossier du projet :",
        "    uv sync --extra vision",
        "Si l'erreur persiste (typiquement sur pydantic_core / onnxruntime / dlib) :",
        "    supprime le dossier .venv, puis relance « uv sync --extra vision ».",
    ]
    _err("Dépendances manquantes ou cassées", "\n".join(lines))
    return False


# ── 3. Fichier .env ───────────────────────────────────────────────────────────

# Marqueurs qui trahissent une COMMANDE shell collée dans une valeur (erreur très
# fréquente : on copie un « setx KEY=... » ou un « $env:KEY=... » au lieu de la valeur).
_SHELL_TOKENS = ("$env:", "Set-", "setx ", "export ", "&&", "|", "<", ">")


def check_env() -> bool:
    """Vérifie .env. Non bloquant (avertit) : un .env douteux n'empêche pas
    forcément de démarrer, mais c'est la 2e cause de « ça capte mais rien ne marche »."""
    env_path = Path(".env")
    if not env_path.exists():
        _warn(
            "Fichier .env absent",
            """
Jarvis lit ses clés API et sa config dans un fichier .env, introuvable ici.
FIX : copie « .env.example » en « .env » et remplis au minimum la clé de ton LLM
      (ANTHROPIC_API_KEY, ou OPENAI_API_KEY si API_BACKEND=openai).
""",
        )
        return True  # non bloquant : l'app peut démarrer et le dira aussi

    suspicious: list[tuple[int, str, str]] = []
    text = env_path.read_text(encoding="utf-8", errors="replace")
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if any(tok in val for tok in _SHELL_TOKENS):
            suspicious.append((i, key, "ressemble à une commande shell, pas à une valeur"))
        elif (val.count('"') % 2) or (val.count("'") % 2):
            suspicious.append((i, key, "guillemets non équilibrés"))

    if suspicious:
        lines = ["Des lignes de .env semblent cassées (cause fréquente de crash) :", ""]
        for ln, key, why in suspicious:
            lines.append(f"  - ligne {ln}  ({key})  : {why}")
        lines += [
            "",
            "POURQUOI : une valeur de .env doit être la clé BRUTE, sur une seule ligne,",
            "sans guillemets ni commande. Exemple correct :",
            "    DEEPGRAM_API_KEY=ab12cd34ef...",
            "Exemple CASSÉ (commande PowerShell collée) :",
            '    DEEPGRAM_API_KEY=$env:DEEPGRAM_API_KEY = "ab12..."',
        ]
        _warn("Configuration .env suspecte", "\n".join(lines))

    # Clé LLM du backend choisi : présente et pas un placeholder ? Sinon Jarvis
    # démarre mais ne peut PAS répondre — le cas « ça marche pas » le plus déroutant.
    env: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    backend = (env.get("API_BACKEND") or "anthropic").lower()
    key_name = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "mistral": "MISTRAL_API_KEY",
    }.get(backend)
    if key_name:
        val = env.get(key_name, "")
        if not val or "..." in val or len(val) < 20:
            _warn(
                "Clé LLM manquante ou non remplie",
                f"""
API_BACKEND={backend} mais {key_name} est vide ou encore à sa valeur d'exemple.
CONSÉQUENCE : Jarvis va démarrer, mais ne pourra PAS répondre (ni chat, ni voix).
FIX : mets ta vraie clé {key_name} dans .env (la clé brute, sans guillemets).
""",
            )
    return True


# ── 4. Port de l'API ──────────────────────────────────────────────────────────


def check_port() -> bool:
    port = int(os.getenv("PORT", "8000"))
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        _err(
            f"Port {port} déjà utilisé",
            f"""
Le port {port} est occupé : soit une instance de Jarvis tourne déjà, soit un
autre programme l'utilise. L'API ne pourra pas démarrer dessus.

FIX :
  - ferme l'instance précédente (Ctrl-C dans son terminal), ou
  - tue le processus qui écoute sur {port}, ou
  - change PORT=… dans .env pour un autre port libre.
""",
        )
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


# ── Orchestration ─────────────────────────────────────────────────────────────


def main() -> int:
    print(_c("2", "Vérification de l'environnement Jarvis…"), file=sys.stderr)

    fatal = False
    for chk in (check_python, check_deps, check_env, check_port):
        try:
            if not chk():
                fatal = True
        except Exception as e:  # un check ne doit JAMAIS faire planter le préflight
            _err(f"Échec de la vérification « {chk.__name__} »", str(e))
            fatal = True

    if fatal:
        msg = "Démarrage annulé : corrige le(s) problème(s) ci-dessus, puis relance."
        print("\n" + _c("91", msg), file=sys.stderr)
        return 1

    print(_c("92", "[OK] Environnement vérifié — démarrage de l'API."), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
