"""Réflexion post-mission (CDC §5).

À la fin de chaque mission (DONE | FAILED | KILLED), produit une leçon
structurée via LLM, l'écrit comme `Event` `mission_lesson` ET la fait passer
par le pipeline d'ingestion `memory/ingest.py` — donc le matcher v2 PHASE 3
décide automatiquement si la leçon en confirme une précédente, en contredit
une, ou en crée une nouvelle.

Si la leçon flag `skill_candidate=true`, on émet un second `Event`
`skill_candidate_proposal` (signal vers le futur Skill Lab PHASE 4). On ne
crée JAMAIS la skill ici — c'est le rôle de PHASE 4.

Aucun stockage parallèle : la leçon EST de la mémoire, conformément au CDC.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from loguru import logger

from jarvis.engine.mission.schemas import Project, ProjectStatus, StepStatus
from jarvis.kernel.contracts import LLMProvider, MemoryIngest
from jarvis.kernel.contracts import MemoryStore as MemoryKernel

# Statuts considérés comme "fin de mission" (§5.1).
# PAUSED est exclu : la mission est reprenable, ce n'est pas une fin.
_TERMINAL_STATUSES: frozenset[ProjectStatus] = frozenset(
    {ProjectStatus.DONE, ProjectStatus.FAILED, ProjectStatus.KILLED}
)

_REFLEXION_SYSTEM = (
    "Tu es un analyste rétrospectif de mission d'agent. Tu produis des leçons "
    "d'exécution structurées, concises, factuelles. Tu réponds en JSON strict, "
    "sans markdown, sans préambule."
)


@dataclass
class MissionLesson:
    """Leçon d'exécution structurée (§5.1)."""

    project_id: str
    project_status: ProjectStatus
    what_worked: str
    what_failed: str
    root_cause: str
    corrective_action: str
    skill_candidate: bool
    skill_description: str
    lesson_event_id: str | None = None  # rempli après log_event/ingest


class Reflexion:
    """Pilote la réflexion post-mission.

    `kernel` et `memory_ingest` sont optionnels :
    - Avec ingest : la leçon devient un Event + passe par le matcher v2 → fact
      decision potentiel.
    - Avec kernel seul : la leçon est tracée comme Event (pas de fact).
    - Sans rien : la leçon est produite et retournée mais NON persistée
      (utilisé en tests et en cas de mémoire désactivée).
    """

    def __init__(
        self,
        llm: LLMProvider,
        kernel: MemoryKernel | None = None,
        memory_ingest: MemoryIngest | None = None,
    ) -> None:
        self._llm = llm
        self._kernel = kernel
        self._ingest = memory_ingest

    # ── API publique ──────────────────────────────────────────────────────────

    async def reflect(self, project: Project) -> MissionLesson | None:
        """Analyse la mission terminée, persiste la leçon, émet signal skill si besoin.

        Renvoie None si :
        - le projet n'est pas dans un état terminal (PAUSED, RUNNING, PLANNING),
        - l'appel LLM échoue ou retourne un JSON non parsable.
        """
        if project.status not in _TERMINAL_STATUSES:
            return None

        lesson = await self._analyse(project)
        if lesson is None:
            return None

        # Persistance (ingest > kernel > rien). On reste tolérant aux deux
        # premières absences pour permettre les tests et les modes dégradés.
        lesson_text = self._format_lesson_text(project, lesson)
        metadata = self._build_metadata(project, lesson)

        if self._ingest is not None:
            try:
                result = await self._ingest.ingest(
                    content=lesson_text,
                    source=f"reflexion:{project.id}",
                    event_type="mission_lesson",
                    metadata=metadata,
                )
                lesson.lesson_event_id = result.event.id
            except Exception as exc:  # noqa: BLE001 — la mission est close, on dégrade
                logger.warning("Reflexion: ingest échec", error=str(exc))
        elif self._kernel is not None:
            try:
                evt = self._kernel.log_event(
                    type="mission_lesson",
                    source=f"reflexion:{project.id}",
                    content=lesson_text,
                    metadata=metadata,
                )
                lesson.lesson_event_id = evt.id
            except Exception as exc:  # noqa: BLE001
                logger.warning("Reflexion: log_event échec", error=str(exc))

        # Signal Skill Lab (PHASE 4) — Event séparé sur le bus immuable.
        if lesson.skill_candidate and self._kernel is not None:
            try:
                self._kernel.log_event(
                    type="skill_candidate_proposal",
                    source=f"reflexion:{project.id}",
                    content=lesson.skill_description,
                    metadata={
                        "project_id": project.id,
                        "from_lesson_evt": lesson.lesson_event_id,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Reflexion: skill_candidate signal échec", error=str(exc))

        return lesson

    # ── Analyse LLM ───────────────────────────────────────────────────────────

    async def _analyse(self, project: Project) -> MissionLesson | None:
        prompt = self._build_prompt(project)
        try:
            raw = await self._llm.complete(
                messages=[{"role": "user", "content": prompt}],
                system=_REFLEXION_SYSTEM,
                stream=False,
                context="reflexion",
            )
        except Exception as exc:  # noqa: BLE001 — pas de leçon vaut mieux qu'un crash
            logger.warning("Reflexion: LLM échec", error=str(exc))
            return None

        if not isinstance(raw, str):
            return None
        data = _parse_lesson_json(raw)
        if data is None:
            logger.debug("Reflexion: JSON non parsable", preview=raw[:200] if raw else "")
            return None

        return MissionLesson(
            project_id=project.id,
            project_status=project.status,
            what_worked=str(data.get("what_worked", "")).strip()[:500],
            what_failed=str(data.get("what_failed", "")).strip()[:500],
            root_cause=str(data.get("root_cause", "")).strip()[:500],
            corrective_action=str(data.get("corrective_action", "")).strip()[:500],
            skill_candidate=bool(data.get("skill_candidate", False)) is True,
            skill_description=str(data.get("skill_description", "")).strip()[:500],
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _build_prompt(project: Project) -> str:
        steps_summary = []
        for s in project.steps:
            row = (
                f"  - [{s.status.value:<18}] {s.title}"
                f"\n      success_criterion: {s.success_criterion[:120]}"
            )
            if s.error:
                row += f"\n      ERROR: {s.error[:200]}"
            if s.verification_notes:
                row += f"\n      verif_notes: {s.verification_notes[:200]}"
            if s.output:
                row += f"\n      output: {s.output[:200]}"
            steps_summary.append(row)
        steps_text = "\n".join(steps_summary) or "  (aucune étape exécutée)"

        return (
            "## Mission terminée\n"
            f"Mission : {project.mission[:500]}\n"
            f"Titre : {project.title}\n"
            f"Statut final : {project.status.value}\n\n"
            "## Étapes\n"
            f"{steps_text}\n\n"
            "## Tâche\n"
            "Produis une leçon d'exécution sous forme de JSON strict, "
            "respectant ce schéma :\n"
            "{\n"
            '  "what_worked": "1-2 phrases sur ce qui a fonctionné (vide si tout a '
            'échoué)",\n'
            '  "what_failed": "1-2 phrases sur ce qui a échoué (vide si succès)",\n'
            '  "root_cause": "1 phrase sur la cause probable (vide si succès)",\n'
            '  "corrective_action": "1 phrase sur quoi faire différemment la '
            'prochaine fois (vide si aucune amélioration évidente)",\n'
            '  "skill_candidate": false,\n'
            '  "skill_description": ""\n'
            "}\n\n"
            "## Règles\n"
            "- skill_candidate=true UNIQUEMENT si la mission contient un PATTERN "
            "CLAIR ET RÉUTILISABLE qui apparaît plusieurs fois ou qui est "
            "manifestement générique (ex. 'créer N scripts similaires', "
            "'tester puis rapporter sur K artefacts'). Sois conservateur : "
            "par défaut false.\n"
            "- skill_description : si skill_candidate=true, décris l'outil "
            "proposé (nom technique + objectif en 1-2 phrases). Vide sinon.\n"
            "- Tous les champs string : 1-2 phrases maximum. Pas de verbosité.\n"
        )

    @staticmethod
    def _format_lesson_text(project: Project, lesson: MissionLesson) -> str:
        """Rend la leçon en texte lisible humain ET parseable par l'extracteur.

        Le mot-clé 'jarvis decided X' aide l'extracteur PHASE 3 (mapping prompt
        decision → decided) à produire un Fact category=decision.
        """
        lines = [
            f"Leçon de la mission '{project.title}' (statut: {project.status.value}).",
            "",
            f"Ce qui a marché : {lesson.what_worked or '(non rapporté)'}",
        ]
        if lesson.what_failed:
            lines.append(f"Ce qui a échoué : {lesson.what_failed}")
        if lesson.root_cause:
            lines.append(f"Cause probable : {lesson.root_cause}")
        if lesson.corrective_action:
            lines.append(f"Action corrective : jarvis decided {lesson.corrective_action}")
        else:
            lines.append(
                "Action corrective : jarvis decided continuer cette approche pour "
                "les missions similaires."
            )
        if lesson.skill_candidate and lesson.skill_description:
            lines.extend(
                [
                    "",
                    f"Pattern réutilisable détecté : {lesson.skill_description}",
                ]
            )
        return "\n".join(lines)

    @staticmethod
    def _build_metadata(project: Project, lesson: MissionLesson) -> dict:
        n_done = sum(1 for s in project.steps if s.status == StepStatus.DONE)
        n_failed = sum(1 for s in project.steps if s.status == StepStatus.FAILED)
        return {
            "project_id": project.id,
            "project_status": project.status.value,
            "n_steps_total": len(project.steps),
            "n_steps_done": n_done,
            "n_steps_failed": n_failed,
            "what_worked": lesson.what_worked,
            "what_failed": lesson.what_failed,
            "root_cause": lesson.root_cause,
            "corrective_action": lesson.corrective_action,
            "skill_candidate": lesson.skill_candidate,
            "skill_description": lesson.skill_description,
        }


# ── Parsing JSON (tolérant fences markdown) ──────────────────────────────────


_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_lesson_json(raw: str) -> dict | None:
    """Parse JSON tolérant aux ```json...``` autour. None si non parsable."""
    candidate = raw.strip()
    fence = _CODE_FENCE_RE.search(candidate)
    if fence:
        candidate = fence.group(1)
    match = _JSON_OBJ_RE.search(candidate)
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


__all__ = ["MissionLesson", "Reflexion", "_TERMINAL_STATUSES"]
