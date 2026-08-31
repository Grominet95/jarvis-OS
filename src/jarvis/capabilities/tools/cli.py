# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import asyncio
import re
import shlex
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml
from loguru import logger

from jarvis.capabilities.tools.base import Tool, ToolResult
from jarvis.kernel.error_collector import collector  # jrv: autofix
from jarvis.kernel.settings import settings

# ── Whitelist binaires autorisés pour execute_cli ────────────────────────────
CLI_WHITELIST: frozenset[str] = frozenset(
    {
        # Dev
        "git",
        "python",
        "python3",
        "pip",
        "uv",
        # Exploration fichiers
        "ls",
        "cat",
        "head",
        "tail",
        "grep",
        "find",
        "mv",
        "cp",
        "rm",
        "mkdir",
        "touch",
        "zip",
        "unzip",
        "rename",
        # Médias
        "yt-dlp",
        "ffmpeg",
        # Images
        "rembg",
        "convert",
        "magick",
        "sips",
        # PDF
        "pdftk",
        "pdftoppm",
        # Métadonnées
        "exiftool",
        # macOS
        "open",
        "osascript",
        "say",
        "screencapture",
        "afinfo",
        # Énergie / système (approbation requise)
        "pmset",
        "shutdown",
    }
)

# ── Interpréteurs : binaires qui exécutent du code passé en argument ─────────
# Ces binaires déclenchent TOUJOURS _requires_approval, même whitelistés.
# Le LLM — ou une injection de prompt — ne peut pas les utiliser sans confirmation.
_INTERPRETERS_REQUIRE_APPROVAL: frozenset[str] = frozenset(
    {
        "osascript",  # AppleScript arbitraire = exécution de code
    }
)

# ── Binaires système à effets de bord irréversibles ───────────────────────────
_SYSTEM_REQUIRE_APPROVAL: frozenset[str] = frozenset(
    {
        "shutdown",
        "pmset",
        "sudo",
        "rm",
    }
)

# Patterns vraiment irréversibles — refusés même avec confirmation
_EXEC_BLOCKED_RE = re.compile(
    r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/?(\.\./)*/?$"
    r"|rm\s+--no-preserve-root"
    r"|:\(\)\s*\{.*\}"  # fork bomb
    r"|\bmkfs\b|\bfdisk\b|\bparted\b"
    r"|dd\s+if=.*\bof=/dev/"
    r"|>\s*/dev/(sda|hda|nvme|loop|disk)\d*"
    r"|\|\s*(bash|sh|zsh|fish|dash)\b"
    r"|curl\b[^|]*\|\s*sudo"
    r"|wget\b[^|]*-O\s*-[^|]*\|\s*(bash|sh)",
    re.IGNORECASE | re.DOTALL,
)

_TIMEOUT = 30.0
_APPROVAL_TTL = timedelta(minutes=5)

# ── Blocklist inconditionnelle ────────────────────────────────────────────────
# Ces patterns sont refusés MÊME si le script est whitelisté et marqué "safe".
# Contrôle de sécurité de dernier recours.
_BLOCKED_PATTERNS: list[str] = [
    r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/?(\.\./)*/?$",  # rm -rf / ou rm /
    r"rm\s+--no-preserve-root",
    r":\(\)\s*\{.*\}",  # fork bomb
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bhalt\b",
    r"\bmkfs\b",
    r"\bfdisk\b",
    r"\bparted\b",
    r"dd\s+if=.*\bof=/dev/",
    r">\s*/dev/(sda|hda|nvme|loop|disk)\d*",
    r"\|\s*(bash|sh|zsh|fish|dash)\b",  # piping to shell
    r"curl\b[^|]*\|\s*sudo",
    r"wget\b[^|]*-O\s*-[^|]*\|\s*(bash|sh)",
    r"\bsudo\b",  # sudo bloqué par défaut
]
_BLOCKED_RE = re.compile("|".join(_BLOCKED_PATTERNS), re.IGNORECASE | re.DOTALL)


class _PendingApproval:
    """Script en attente de confirmation utilisateur."""

    __slots__ = ("cmd", "alias", "description", "expires_at")

    def __init__(self, alias: str, cmd: list[str], description: str) -> None:
        self.alias = alias
        self.cmd = cmd
        self.description = description
        self.expires_at = datetime.now(UTC) + _APPROVAL_TTL


class CLIRunnerTool(Tool):
    """Lance des scripts shell whitelistés avec 3 niveaux de sécurité.

    Tiers :
      safe    — exécuté immédiatement (whitelist suffit comme garantie)
      confirm — mis en attente, nécessite que l'utilisateur dise 'confirme <alias>'
      reject  — toujours refusé

    Sécurité supplémentaire :
      • Blocklist de patterns dangereux (appliquée avant le tier)
      • Option sandboxed=true : exécution dans un répertoire temporaire isolé
      • Timeout strict (30s par défaut)
      • TTL de 5 min sur les approbations en attente
    """

    name = "run_script"

    def __init__(self, whitelist_path: Path, games_path: Path | None = None) -> None:
        self._whitelist_path = whitelist_path
        self._games_path = games_path
        self._pending: dict[str, _PendingApproval] = {}

    def _load_scripts(self) -> dict[str, dict]:
        """Relit tools.yaml + games.yaml à chaque appel : un jeu ajouté depuis
        Réglages → Jeux est utilisable immédiatement, sans redémarrer Jarvis."""
        scripts: dict[str, dict] = {}
        if self._whitelist_path.exists():
            data = yaml.safe_load(self._whitelist_path.read_text(encoding="utf-8"))
            scripts.update(data or {})

        if self._games_path and self._games_path.exists():
            games = yaml.safe_load(self._games_path.read_text(encoding="utf-8")) or {}
            for alias, g in games.items():
                path = g.get("path", "")
                scripts[alias] = {
                    "command": [path],
                    "cwd": str(Path(path).parent) if path else None,
                    "description": f"Lance {g.get('name', alias)}",
                    "name": g.get("name", alias),
                    "tier": "safe",
                    "detached": True,
                }
        return scripts

    def match_alias(self, text: str) -> str | None:
        """Trouve l'alias correspondant à un texte libre (nom du jeu/script
        demandé par l'utilisateur) — pour le filet de rattrapage du Gateway
        quand le modèle décrit un lancement sans appeler l'outil.

        Tolère un mot manquant ou tronqué (ex: "fnaf" pour "fnaf9", "assassin's
        creed" pour "assassin's creed shadows"), mais ne matche jamais plus
        d'un candidat à la fois — en cas d'ambiguïté, on préfère ne rien deviner.
        """
        scripts = self._load_scripts()
        text_low = text.lower()
        text_tokens = [t for t in re.findall(r"[\w']+", text_low) if len(t) >= 3]

        def word_hit(word: str) -> bool:
            if word in text_low:
                return True
            return any(word.startswith(tok) or tok.startswith(word) for tok in text_tokens)

        matches = []
        for alias, script in scripts.items():
            name = script.get("name") or alias.replace("_", " ")
            cand_words = [w for w in re.findall(r"[\w']+", name.lower()) if len(w) >= 3]
            if not cand_words:
                continue
            hits = sum(1 for w in cand_words if word_hit(w))
            if hits >= max(1, len(cand_words) - 1):
                matches.append(alias)

        return matches[0] if len(matches) == 1 else None

    @property
    def description(self) -> str:  # type: ignore[override]
        scripts = self._load_scripts()
        safe_names = [k for k, v in scripts.items() if v.get("tier", "safe") == "safe"]
        confirm_names = [k for k, v in scripts.items() if v.get("tier") == "confirm"]
        aliases = ", ".join(scripts) if scripts else "aucun — édite config/tools.yaml"
        return (
            f"Lance un script whitelisté ou un jeu/app ajouté depuis Réglages → Jeux. "
            f"Alias disponibles : {aliases}. "
            f"Niveaux : safe (auto)={safe_names or 'aucun'}, "
            f"confirm (approbation requise)={confirm_names or 'aucun'}. "
            "Pour confirmer un script en attente, passe action='confirm'."
        )

    @property
    def input_schema(self) -> dict:  # type: ignore[override]
        scripts = self._load_scripts()
        return {
            "type": "object",
            "properties": {
                "alias": {
                    "type": "string",
                    "description": (
                        f"Alias du script/jeu. Disponibles : {', '.join(scripts) or 'aucun'}"
                    ),
                },
                "action": {
                    "type": "string",
                    "enum": ["run", "confirm"],
                    "description": (
                        "'run' : lance le script (ou met en attente si tier=confirm). "
                        "'confirm' : exécute un script précédemment mis en attente."
                    ),
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Arguments supplémentaires passés au script (optionnel).",
                },
            },
            "required": ["alias"],
        }

    async def execute(
        self,
        alias: str,
        action: str = "run",
        args: list[str] | None = None,
        **_: object,
    ) -> ToolResult:
        scripts = self._load_scripts()

        # ── Confirmation d'un script en attente ──────────────────────────────
        if action == "confirm":
            return await self._confirm_pending(alias)

        # ── Lookup whitelist ──────────────────────────────────────────────────
        script = scripts.get(alias)
        if script is None:
            available = ", ".join(scripts) or "aucun"
            return ToolResult(
                content=f"Script inconnu : '{alias}'. Disponibles : {available}",
                is_error=True,
            )

        cmd = list(script["command"]) + (args or [])
        cmd_str = " ".join(cmd)
        tier = str(script.get("tier", "safe")).lower()

        # ── Blocklist inconditionnelle ─────────────────────────────────────────
        if _BLOCKED_RE.search(cmd_str):
            logger.warning("CLIRunner BLOCKED by pattern", alias=alias, cmd=cmd_str)
            return ToolResult(
                content=(
                    f"Commande '{alias}' refusée — pattern dangereux détecté dans : `{cmd_str}`. "
                    "Cette vérification est inconditionnelle."
                ),
                is_error=True,
            )

        # ── Tier reject ───────────────────────────────────────────────────────
        if tier == "reject":
            logger.info("CLIRunner rejected by tier", alias=alias)
            return ToolResult(
                content=(
                    f"Script '{alias}' désactivé (tier: reject)."
                    " Modifie config/tools.yaml pour l'activer."
                ),
                is_error=True,
            )

        # ── Tier confirm : mise en attente d'approbation ──────────────────────
        if tier == "confirm":
            desc = script.get("description", cmd_str)
            self._pending[alias] = _PendingApproval(alias=alias, cmd=cmd, description=cmd_str)
            logger.info("CLIRunner awaiting approval", alias=alias)
            return ToolResult(
                content=(
                    f"⚠️ Ce script nécessite ton approbation avant exécution.\n"
                    f"Script : {desc}\n"
                    f"Commande : `{cmd_str}`\n\n"
                    f"Pour exécuter : réponds 'confirme {alias}' "
                    f"(approbation valide 5 minutes)."
                )
            )

        # ── Tier safe : exécution (avec sandbox optionnelle) ──────────────────
        sandboxed = bool(script.get("sandboxed", False))
        detached = bool(script.get("detached", False))
        cwd = script.get("cwd")
        return await self._run(cmd, alias, sandboxed=sandboxed, detached=detached, cwd=cwd)

    async def _confirm_pending(self, alias: str) -> ToolResult:
        """Exécute un script préalablement mis en attente de confirmation."""
        # Nettoyage des entrées expirées
        now = datetime.now(UTC)
        expired = [k for k, p in self._pending.items() if p.expires_at <= now]
        for k in expired:
            logger.debug("CLIRunner approval expired", alias=k)
            del self._pending[k]

        pending = self._pending.pop(alias, None)
        if pending is None:
            return ToolResult(
                content=(
                    f"Aucun script '{alias}' en attente d'approbation "
                    "(ou délai de 5 minutes expiré). "
                    "Relance la commande pour un nouveau cycle d'approbation."
                ),
                is_error=True,
            )

        logger.info("CLIRunner confirmed and executing", alias=alias)
        return await self._run(pending.cmd, alias, sandboxed=False)

    async def _run(
        self,
        cmd: list[str],
        alias: str,
        *,
        sandboxed: bool,
        detached: bool = False,
        cwd: str | None = None,
    ) -> ToolResult:
        """Exécute le subprocess, en sandbox si demandé, ou détaché pour les apps
        longue durée (jeux, GUI) qu'on ne veut pas attendre ni tuer après le timeout."""
        if detached:
            # Sur Windows, les apps GUI (jeux, launchers) doivent être ouvertes via
            # ShellExecute (comme un double-clic) plutôt que CreateProcess
            # (asyncio.create_subprocess_exec) : certains exécutables — notamment les
            # jeux avec protection anti-tampering — se lancent puis se ferment
            # silencieusement en quelques secondes quand ils détectent un lancement
            # "brut" via CreateProcess, mais tournent normalement via ShellExecute.
            #
            # On passe par `cmd /c start` plutôt qu'un os.startfile() direct : `start`
            # utilise aussi ShellExecute (même bénéfice anti-tampering), MAIS cmd.exe
            # se termine aussitôt après avoir lancé le jeu, qui devient orphelin en
            # <1s — au lieu d'avoir pour parent le process Jarvis appelant, dont la
            # durée de vie peut être limitée (ex: le pipeline vocal LiveKit tourne
            # dans un sous-process de job qui se termine après la session). Certains
            # jeux protégés surveillent leur parent et s'auto-ferment quand il meurt ;
            # sans cet intermédiaire, un jeu lancé par la voix se fermait 3-5 min
            # après la fin du job vocal, alors qu'il tournait sans souci lancé par le
            # texte (process serveur long-vivant qui ne meurt jamais).
            if sys.platform == "win32":
                # noqa justifiés : ASYNC220 (subprocess.Popen dans une fonction async) est
                # volontaire — Popen est fire-and-forget ici (pas d'attente du résultat), et
                # S602/S603/S607 car le chemin vient de tools.yaml/games.yaml, pas d'entrée
                # utilisateur libre.
                flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                try:
                    subprocess.Popen(  # noqa: ASYNC220,S602,S603,S607
                        ["cmd", "/c", "start", "", cmd[0], *cmd[1:]],
                        cwd=cwd or None,
                        creationflags=flags,
                        close_fds=True,
                    )
                except OSError as e:
                    collector.error("JRV-TOL-001", "JRV-TOL-001", cause=e)
                    return ToolResult(content=f"Erreur de lancement : {e}", is_error=True)
                logger.info("CLIRunner launched detached (cmd start)", alias=alias, cmd=cmd)
                return ToolResult(content=f"'{alias}' lancé.")

            extra_kwargs: dict = {
                "stdout": asyncio.subprocess.DEVNULL,
                "stderr": asyncio.subprocess.DEVNULL,
                "stdin": asyncio.subprocess.DEVNULL,
            }
            if cwd:
                extra_kwargs["cwd"] = cwd
            try:
                await asyncio.create_subprocess_exec(*cmd, **extra_kwargs)
            except OSError as e:
                collector.error("JRV-TOL-001", "JRV-TOL-001", cause=e)
                return ToolResult(content=f"Erreur de lancement : {e}", is_error=True)
            logger.info("CLIRunner launched detached", alias=alias, cmd=cmd)
            return ToolResult(content=f"'{alias}' lancé.")

        extra_kwargs: dict = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.STDOUT,
        }

        tmp_dir: str | None = None
        if sandboxed:
            tmp_dir = tempfile.mkdtemp(prefix="jarvis_sandbox_")
            extra_kwargs["cwd"] = tmp_dir
            extra_kwargs["env"] = {
                "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
                "HOME": tmp_dir,
                "TMPDIR": tmp_dir,
                "LANG": "fr_FR.UTF-8",
                "LC_ALL": "fr_FR.UTF-8",
            }
            logger.info("CLIRunner sandboxed", alias=alias, cwd=tmp_dir)
        else:
            logger.info("CLIRunner executing", alias=alias, cmd=cmd)

        try:
            proc = await asyncio.create_subprocess_exec(*cmd, **extra_kwargs)
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)
            output = stdout.decode(errors="replace").strip() or "Terminé (pas de sortie)."
            success = proc.returncode == 0
            logger.info("CLIRunner done", alias=alias, returncode=proc.returncode)
            return ToolResult(content=output, is_error=not success)
        except TimeoutError:
            collector.error("JRV-TOL-001", "JRV-TOL-001")
            try:
                proc.kill()
            except ProcessLookupError:
                collector.error("JRV-TOL-001", "JRV-TOL-001")
                pass
            return ToolResult(content=f"Timeout après {_TIMEOUT}s.", is_error=True)
        except OSError as e:
            collector.error("JRV-TOL-001", "JRV-TOL-001", cause=e)
            return ToolResult(content=f"Erreur d'exécution : {e}", is_error=True)


class ExecuteCLITool(Tool):
    """Exécute une commande shell libre depuis la whitelist de binaires autorisés.

    Modèle de menace :
      Ce tool est déclenché par le LLM, lequel peut avoir lu du contenu externe
      non fiable (Gmail, navigateur, Notion). Une injection de prompt dans ce
      contenu peut pousser le LLM à émettre une commande malveillante.
      La confirmation humaine des commandes sensibles est la DERNIÈRE ligne de
      défense non contournable.

    Couches de sécurité (dans l'ordre d'application) :
      1. Blocklist irréversible — fork bomb, rm -rf /, pipe→shell :
         refus même avec confirmed=True
      2. Parsing strict         — shlex.split requis ; guillemets non fermés = refus
         (jamais de split naïf)
      3. Allowlist binaire      — seuls les binaires de CLI_WHITELIST sont admis,
         résolu via Path(parts[0]).name (robuste aux chemins absolus)
      4. Approbation robuste    — basée sur le binaire résolu + args :
         interpréteurs (_INTERPRETERS_REQUIRE_APPROVAL), open -a/URL,
         rm, pmset, shutdown, sudo
      5. Sandbox par défaut     — tmpdir isolé + env restreint
         (ALLOW_UNSANDBOXED_EXEC=true pour opt-out explicite)

    Les interpréteurs (_INTERPRETERS_REQUIRE_APPROVAL : osascript…) exigent
    confirmed=True systématiquement ; confirmed=True ne contourne JAMAIS la
    couche 1 (blocklist irréversible).
    """

    name = "execute_cli"
    description = (
        "Exécute une commande shell complète. Le premier binaire doit être dans la whitelist. "
        "Pour les commandes sensibles (shutdown, rm, pmset, sudo) ou les interpréteurs "
        "(osascript) : appelle d'abord sans confirmed, présente la commande à l'utilisateur, "
        "puis rappelle avec confirmed=true après son accord explicite. "
        "Exemples sans approbation : yt-dlp, ffmpeg, rembg, pdftk, sips, screencapture."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": (
                    "Commande shell complète. "
                    "Ex: 'yt-dlp -o ~/Downloads/%(title)s.%(ext)s -f mp4 https://...' "
                    "ou 'sips -z 800 600 input.jpg --out output.jpg'"
                ),
            },
            "confirmed": {
                "type": "boolean",
                "description": (
                    "true après confirmation explicite de l'utilisateur (commandes sensibles)."
                ),
            },
        },
        "required": ["command"],
    }

    @staticmethod
    def _requires_approval(parts: list[str]) -> bool:
        """Détermine si la commande nécessite une confirmation humaine.

        Basé sur le BINAIRE RÉSOLU (Path(parts[0]).name) et les arguments parsés.
        Robuste aux chemins absolus (/usr/bin/osascript) et à la casse.
        """
        if not parts:
            return False
        binary = Path(parts[0]).name.lower()

        # Interpréteurs : exécutent du code passé en argument → approbation systématique
        if binary in _INTERPRETERS_REQUIRE_APPROVAL:
            return True

        # open : approbation si lancement d'app (-a) ou URL externe
        if binary == "open":
            rest = parts[1:]
            if "-a" in rest or any(a.startswith(("http://", "https://")) for a in rest):
                return True

        # Binaires système à effets de bord irréversibles
        if binary in _SYSTEM_REQUIRE_APPROVAL:
            return True

        return False

    async def _run(self, parts: list[str], cmd_str: str) -> ToolResult:
        """Exécute le subprocess, sandboxé par défaut."""

        sandboxed = not getattr(settings, "allow_unsandboxed_exec", False)
        extra_kwargs: dict = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.STDOUT,
        }

        if sandboxed:
            tmp_dir = tempfile.mkdtemp(prefix="jarvis_exec_")
            extra_kwargs["cwd"] = tmp_dir
            extra_kwargs["env"] = {
                "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
                "HOME": tmp_dir,
                "TMPDIR": tmp_dir,
                "LANG": "fr_FR.UTF-8",
                "LC_ALL": "fr_FR.UTF-8",
            }
            logger.info(f"ExecuteCLI sandboxed cwd={tmp_dir}: {cmd_str[:60]}")
        else:
            logger.info(f"ExecuteCLI unsandboxed (allow_unsandboxed_exec=true): {cmd_str[:60]}")

        try:
            proc = await asyncio.create_subprocess_exec(*parts, **extra_kwargs)
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300.0)
            output = stdout.decode(errors="replace").strip() or "Terminé (pas de sortie)."
            success = proc.returncode == 0
            logger.info(f"ExecuteCLI done: rc={proc.returncode}")
            return ToolResult(content=output, is_error=not success)
        except TimeoutError:
            collector.error("JRV-TOL-001", "JRV-TOL-001")
            try:
                proc.kill()
            except ProcessLookupError:
                collector.error("JRV-TOL-001", "JRV-TOL-001")
                pass
            return ToolResult(content="Timeout après 300s.", is_error=True)
        except OSError as e:
            collector.error("JRV-TOL-001", "JRV-TOL-001", cause=e)
            return ToolResult(content=f"Erreur d'exécution : {e}", is_error=True)

    async def execute(
        self,
        command: str,
        confirmed: bool = False,
        **_: object,
    ) -> ToolResult:
        # Couche 1 : blocklist irréversible — refus inconditionnel, avant tout parsing
        if _EXEC_BLOCKED_RE.search(command):
            logger.warning(f"ExecuteCLI BLOCKED: {command[:80]}")
            return ToolResult(content="Refusé — pattern dangereux détecté.", is_error=True)

        # Couche 2 : parsing strict — refus si syntaxe invalide (guillemets non fermés…)
        try:
            parts = shlex.split(command)
        except ValueError as e:
            collector.error("JRV-TOL-001", "JRV-TOL-001", cause=e)
            logger.warning(f"ExecuteCLI parse error ({e}): {command[:60]}")
            return ToolResult(
                content=f"Commande non parsable ({e}). Vérifiez les guillemets.",
                is_error=True,
            )

        if not parts:
            return ToolResult(content="Commande vide.", is_error=True)

        # Couche 3 : allowlist — binaire résolu (robuste aux chemins absolus)
        binary = Path(parts[0]).name
        if binary not in CLI_WHITELIST:
            return ToolResult(
                content=(
                    f"Binaire '{binary}' non autorisé."
                    f" Whitelist : {', '.join(sorted(CLI_WHITELIST))}"
                ),
                is_error=True,
            )

        # Couche 4 : approbation robuste — basée sur le binaire résolu + args
        if self._requires_approval(parts) and not confirmed:
            logger.info(f"ExecuteCLI awaiting approval: {command[:60]}")
            return ToolResult(
                content=(
                    f"⚠️ Commande sensible — confirmation requise avant exécution.\n"
                    f"Commande : `{command}`\n\n"
                    "Présente cette commande à l'utilisateur et demande sa confirmation. "
                    "Si l'utilisateur dit oui, rappelle execute_cli avec confirmed=true."
                )
            )

        # Couche 5 : exécution sandboxée par défaut
        logger.info(f"ExecuteCLI running: {command[:80]}")
        return await self._run(parts, command)
