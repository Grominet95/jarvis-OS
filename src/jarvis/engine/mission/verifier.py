"""Self-verification en 3 couches (CDC §4.3).

Couche 1 — structurelle : QualityChecker existant (artefact bien formé).
Couche 2 — déterministe : step.verification_command via cli sandboxé (exit 0).
Couche 3 — sémantique : LLM grader STRICT qui compare au success_criterion.

Règle absolue : en cas de doute (parse impossible, erreur LLM), verified=false.
Un échec de parse n'est jamais un succès. La vérification structurelle ne doit pas
appeler le LLM ; la sémantique ne re-vérifie pas la syntaxe.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from jarvis.engine.mission.quality_checker import QualityChecker
from jarvis.engine.mission.schemas import Project, Step
from jarvis.kernel.contracts import LLMProvider

# Plafond de contenu inclus dans le prompt sémantique (caractères).
# Au-dessus, on tronque pour ne pas exploser les tokens.
_MAX_CONTENT_CHARS = 6000
_MAX_FILES_INCLUDED = 10


@dataclass
class VerificationResult:
    """Verdict d'une vérification."""

    verified: bool
    layer: str  # "structural" | "deterministic" | "semantic"
    issues: list[str] = field(default_factory=list)
    notes: str = ""


_SEMANTIC_SYSTEM = (
    "Tu es un évaluateur STRICT et SCEPTIQUE d'une étape de mission d'agent. "
    "Ton seul travail est de juger si l'artefact produit RÉPOND VRAIMENT au critère "
    "de succès, pas seulement s'il existe ou compile. Tu réponds UNIQUEMENT en JSON, "
    "sans markdown, sans commentaire, sans préambule."
)


class Verifier:
    """Pipeline 3-couches de vérification d'un step.

    `cli_executor` est une coroutine `(command, timeout) -> {success, stdout, stderr, returncode}`
    typiquement `WorkerCLITool.execute`. None → couche 2 désactivée (mais traçable).
    """

    def __init__(
        self,
        quality_checker: QualityChecker,
        llm: LLMProvider,
        cli_executor: Callable[[str, int], Awaitable[dict]] | None = None,
    ) -> None:
        self._quality = quality_checker
        self._llm = llm
        self._cli = cli_executor

    # ── Point d'entrée principal ──────────────────────────────────────────────

    async def verify(
        self,
        project: Project,
        step: Step,
        files_before: list[str],
    ) -> VerificationResult:
        """Lance les trois couches en cascade. Stop à la première qui échoue."""
        # Couche 1
        structural = self._layer_structural(files_before)
        if not structural.verified:
            return structural

        # Couche 2
        if step.verification_command and self._cli is not None:
            deterministic = await self._layer_deterministic(step)
            if not deterministic.verified:
                return deterministic

        # Couche 3
        return await self._layer_semantic(project, step, files_before)

    # ── Couche 1 — structurelle ───────────────────────────────────────────────

    def _layer_structural(self, files_before: list[str]) -> VerificationResult:
        """Réutilise QualityChecker.check_step_output() tel quel (CDC §4.3)."""
        issues = self._quality.check_step_output(files_before)
        if issues:
            return VerificationResult(
                verified=False,
                layer="structural",
                issues=issues,
                notes=(
                    "Artefact mal formé (fichier vide, syntaxe invalide, refs HTML manquantes...)"
                ),
            )
        return VerificationResult(verified=True, layer="structural")

    # ── Couche 2 — déterministe ───────────────────────────────────────────────

    async def _layer_deterministic(self, step: Step) -> VerificationResult:
        """Exécute step.verification_command. Exit 0 = succès. Cette couche fait foi."""
        assert step.verification_command is not None
        assert self._cli is not None
        try:
            res = await self._cli(step.verification_command, 60)
        except Exception as exc:  # noqa: BLE001 — on capture tout exec error
            logger.warning("Verifier couche 2 — erreur d'exécution", error=str(exc))
            return VerificationResult(
                verified=False,
                layer="deterministic",
                issues=[f"erreur d'exécution: {exc}"],
                notes="Échec d'exécution de verification_command",
            )

        if not res.get("success", False):
            return VerificationResult(
                verified=False,
                layer="deterministic",
                issues=[
                    f"verification_command rc={res.get('returncode')}: "
                    f"{(res.get('stderr') or '')[:300]}"
                ],
                notes="Commande de vérification déterministe a échoué",
            )
        return VerificationResult(verified=True, layer="deterministic")

    # ── Couche 3 — sémantique LLM ─────────────────────────────────────────────

    async def _layer_semantic(
        self,
        project: Project,
        step: Step,
        files_before: list[str] | None = None,
    ) -> VerificationResult:
        """Appel LLM strict-sceptique. En cas de doute → verified=false.

        Le prompt inclut le CONTENU des fichiers nouveaux/modifiés depuis files_before
        (tronqué) pour permettre une vraie évaluation, pas un jugement sur la simple
        liste de fichiers.
        """
        new_files_block = self._new_files_with_content(
            project.workspace_path,
            files_before or [],
        )
        prompt = (
            f"## Mission globale\n{project.mission}\n\n"
            f"## Étape à évaluer\n"
            f"Titre : {step.title}\n"
            f"Description : {step.description}\n"
            f"Critère de succès : {step.success_criterion}\n\n"
            f"## Résultat rapporté par l'agent (auto-rapport, à ne pas faire confiance seul)\n"
            f"{step.output or '(aucun output)'}\n\n"
            f"## Liste des fichiers du workspace\n"
            f"{self._workspace_summary()}\n\n"
            f"## CONTENU des fichiers nouveaux/modifiés (vérité de terrain)\n"
            f"{new_files_block}\n\n"
            f"## Tâche\n"
            f"Réponds UNIQUEMENT avec ce JSON :\n"
            f'{{"verified": true|false, "issues": ["..."], "notes": "..."}}\n\n'
            f"Évalue le CONTENU réel ci-dessus contre le critère. Ignore l'auto-rapport "
            f"de l'agent : seul le contenu fait foi. "
            f"verified=true SEULEMENT si le critère est RÉELLEMENT atteint d'après le "
            f"contenu. En cas de doute, verified=false. Le fait que le fichier existe "
            f"ou compile ne suffit JAMAIS.\n"
        )
        try:
            raw = await self._llm.complete(
                messages=[{"role": "user", "content": prompt}],
                system=_SEMANTIC_SYSTEM,
                stream=False,
                context="verifier",
            )
        except Exception as exc:  # noqa: BLE001 — erreur LLM = doute = verified=false
            logger.warning("Verifier couche 3 — erreur LLM", error=str(exc))
            return VerificationResult(
                verified=False,
                layer="semantic",
                issues=[f"erreur LLM: {exc}"],
                notes="Appel LLM grader a échoué — verdict prudent",
            )

        if not isinstance(raw, str):
            return VerificationResult(
                verified=False,
                layer="semantic",
                issues=["réponse LLM non textuelle"],
                notes="Type de réponse inattendu — doute",
            )

        verdict = self._parse_verdict(raw)
        if verdict is None:
            return VerificationResult(
                verified=False,
                layer="semantic",
                issues=["verdict LLM non parsable"],
                notes=f"JSON illisible — verdict prudent (raw[:200]: {raw[:200]!r})",
            )

        # Strictement : verified=true SEULEMENT si la clé est explicitement True (bool).
        # Un "True", "yes", 1, ou clé absente → false par défaut.
        verified_raw = verdict.get("verified")
        verified = verified_raw is True
        return VerificationResult(
            verified=verified,
            layer="semantic",
            issues=[str(i) for i in (verdict.get("issues") or [])][:10],
            notes=str(verdict.get("notes") or "")[:500],
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_verdict(raw: str) -> dict | None:
        """Parse JSON strict. Retourne None si non parsable ou format inattendu."""
        clean = raw.strip()
        # Retire les fences markdown ```json ... ```
        if clean.startswith("```"):
            first_newline = clean.find("\n")
            if first_newline != -1:
                clean = clean[first_newline + 1 :]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()
        try:
            parsed = json.loads(clean)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        return parsed

    def _workspace_summary(self) -> str:
        """Liste compacte des fichiers du workspace (top 20)."""
        files = self._quality.list_all_files()
        if not files:
            return "(workspace vide)"
        lines = [f"- {f['path']} ({f['size']}B)" for f in files[:20]]
        if len(files) > 20:
            lines.append(f"... +{len(files) - 20} autres fichiers")
        return "\n".join(lines)

    def _new_files_with_content(
        self,
        workspace_path: str,
        files_before: list[str],
    ) -> str:
        """Renvoie le contenu (tronqué) des fichiers créés/modifiés depuis files_before.

        Le grader sémantique a besoin du contenu réel — pas seulement de la liste — pour
        juger si le critère est atteint. Sans ça, il ne peut pas distinguer un artefact
        plausible d'un artefact réel.
        """
        files_now = self._quality.list_all_files()
        before_set = set(files_before)
        new_or_modified = [f for f in files_now if f["path"] not in before_set]
        if not new_or_modified:
            return "(aucun fichier nouveau ou modifié)"

        # Limite raisonnable : fichiers de texte uniquement (skip binaires lourds).
        ws = Path(workspace_path).resolve()
        text_exts = {
            ".html",
            ".css",
            ".js",
            ".ts",
            ".py",
            ".json",
            ".md",
            ".txt",
            ".yaml",
            ".yml",
            ".toml",
            ".xml",
            ".sh",
            ".csv",
        }

        parts: list[str] = []
        used = 0
        included = 0
        for f in new_or_modified:
            if included >= _MAX_FILES_INCLUDED:
                parts.append(
                    f"\n[... +{len(new_or_modified) - included} fichiers tronqués "
                    "pour limite tokens]"
                )
                break
            path = f["path"]
            if Path(path).suffix.lower() not in text_exts:
                parts.append(f"\n=== {path} ({f['size']}B, binaire — skipé) ===")
                included += 1
                continue
            try:
                content = (ws / path).read_text(encoding="utf-8", errors="replace")
            except Exception as exc:  # noqa: BLE001
                parts.append(f"\n=== {path} (illisible: {exc}) ===")
                included += 1
                continue
            remaining = _MAX_CONTENT_CHARS - used
            if remaining < 300:
                parts.append(
                    f"\n[... +{len(new_or_modified) - included} fichiers tronqués "
                    "pour limite tokens]"
                )
                break
            truncated = content[:remaining]
            parts.append(f"\n=== {path} ({f['size']}B) ===\n{truncated}")
            if len(content) > remaining:
                parts.append(f"\n[... fichier tronqué à {remaining} chars / {len(content)}]")
            used += len(truncated)
            included += 1

        return "\n".join(parts) if parts else "(aucun fichier texte à examiner)"
