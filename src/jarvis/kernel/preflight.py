# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""preflight.py — Diagnostic de démarrage."""

from __future__ import annotations

import importlib
import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

_USE_COLOR = sys.stderr.isatty() and os.name != "nt"
_LEVEL_PREFIX = {"error": "ERROR", "warning": "WARN", "impossible": "IMPOSSIBLE"}


def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _USE_COLOR else s


def _emit_stderr(code: str, message: str, *, level: str = "error") -> None:
    prefix = _LEVEL_PREFIX.get(level, level.upper())
    print(f"[{code}] {prefix}: {message}", file=sys.stderr, flush=True)


def _block(jrv_code: str, level: str, marker: str, color: str, title: str, body: str) -> None:
    text = f"{title}\n{body.strip()}"
    _emit_stderr(jrv_code, text, level=level)
    print("\n" + _c(color, f"{marker} {title}"), file=sys.stderr)
    for line in body.strip("\n").splitlines():
        print("  " + line, file=sys.stderr)


def _err(jrv_code: str, title: str, body: str) -> None:
    _block(jrv_code, "error", "[ERREUR]", "91", title, body)


def _warn(jrv_code: str, title: str, body: str) -> None:
    _block(jrv_code, "warning", "[ATTENTION]", "93", title, body)


_CRITICAL_DEPS: dict[str, str] = {
    "fastapi": "le serveur web de l'API",
    "uvicorn": "le moteur qui fait tourner l'API",
    "pydantic": "la validation de la configuration",
    "pydantic_core": "le cœur compilé de pydantic (binaire natif)",
    "httpx": "les appels réseau (LLM, Notion, YouTube…)",
    "numpy": "le calcul (mémoire vectorielle)",
    "loguru": "les logs",
}

_SHELL_TOKENS = ("$env:", "Set-", "setx ", "export ", "&&", "|", "<", ">")


def check_python() -> bool:
    if sys.version_info < (3, 11):  # noqa: UP036
        _err(
            "JRV-KRN-003",
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


def check_deps() -> bool:
    missing: list[tuple[str, str, str]] = []
    for mod, role in _CRITICAL_DEPS.items():
        try:
            importlib.import_module(mod)
        except Exception as e:  # jrv: probe missing dep import
            missing.append((mod, role, type(e).__name__))

    if not missing:
        return True

    lines = ["Des paquets nécessaires au démarrage de l'API sont absents ou cassés :", ""]
    for mod, role, err in missing:
        lines.append(f"  - {mod}  ({role})  [{err}]")
    lines += [
        "",
        "POURQUOI : c'est presque toujours l'environnement Python (.venv), PAS l'API LLM.",
        "FIX, dans le dossier du projet :",
        "    uv sync --extra vision",
    ]
    _err("JRV-KRN-004", "Dépendances manquantes ou cassées", "\n".join(lines))
    return False


def check_env() -> bool:
    env_path = Path(".env")
    if not env_path.exists():
        _warn(
            "JRV-KRN-005",
            "Fichier .env absent",
            """
Jarvis lit ses clés API et sa config dans un fichier .env, introuvable ici.
FIX : copie « .env.example » en « .env » et remplis au minimum la clé de ton LLM.
""",
        )
        return True

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
        lines = ["Des lignes de .env semblent cassées :", ""]
        for ln, key, why in suspicious:
            lines.append(f"  - ligne {ln}  ({key})  : {why}")
        _warn("JRV-KRN-006", "Configuration .env suspecte", "\n".join(lines))

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
                "JRV-KRN-007",
                "Clé LLM manquante ou non remplie",
                f"""
API_BACKEND={backend} mais {key_name} est vide ou encore à sa valeur d'exemple.
FIX : mets ta vraie clé {key_name} dans .env (la clé brute, sans guillemets).
""",
            )
        else:
            _check_llm_key_live(backend, key_name, val)
    return True


_LLM_MODELS = {
    "anthropic": (
        "https://api.anthropic.com/v1/models",
        {"x-api-key": "{key}", "anthropic-version": "2023-06-01"},
    ),
    "openai": ("https://api.openai.com/v1/models", {"Authorization": "Bearer {key}"}),
    "mistral": ("https://api.mistral.ai/v1/models", {"Authorization": "Bearer {key}"}),
}


def _check_llm_key_live(backend: str, key_name: str, key: str) -> None:
    entry = _LLM_MODELS.get(backend)
    if entry is None:
        return
    url, headers_tmpl = entry
    headers = {k: v.replace("{key}", key) for k, v in headers_tmpl.items()}
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=6)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            _warn(
                "JRV-KRN-008",
                "Clé LLM refusée par le fournisseur",
                f"{key_name} est remplie mais {backend} la REFUSE (HTTP {e.code}).",
            )
        elif e.code == 429:
            _warn(
                "JRV-KRN-009",
                "Quota / crédits LLM atteints",
                f"{backend} répond 429 sur {key_name}.",
            )
    except Exception:  # jrv: offline network — non-blocking
        pass


def check_port() -> bool:
    port = int(os.getenv("PORT", "8000"))
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        _err(
            "JRV-KRN-010",
            f"Port {port} déjà utilisé",
            f"Le port {port} est occupé. Ferme l'instance précédente ou change PORT dans .env.",
        )
        return False
    finally:
        try:
            s.close()
        except Exception:  # jrv: socket close best-effort
            pass


def main() -> int:
    load_dotenv()
    print(_c("2", "Vérification de l'environnement Jarvis…"), file=sys.stderr)

    fatal = False
    for chk in (check_python, check_deps, check_env, check_port):
        try:
            if not chk():
                fatal = True
        except Exception as e:
            _err("JRV-KRN-011", f"Échec de la vérification « {chk.__name__} »", str(e))
            fatal = True

    if fatal:
        msg = "Démarrage annulé : corrige le(s) problème(s) ci-dessus, puis relance."
        print("\n" + _c("91", msg), file=sys.stderr)
        return 1

    print(_c("92", "[OK] Environnement vérifié — démarrage de l'API."), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
