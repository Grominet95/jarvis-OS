"""Miroir Markdown UNIDIRECTIONNEL — SQLite → MD lecture seule (CDC §6.7).

Génère des vues Markdown lisibles (`user/preferences.md`, `user/projects.md`, etc.)
depuis les facts actifs du Kernel. **Le sens d'écriture est strictement SQLite → MD.**
Aucune édition manuelle d'un .md ne modifie la mémoire ; la régénération écrase
toute édition humaine.

Pour corriger un souvenir, l'utilisateur passe par `kernel.apply_correction()`
qui crée un Event `human_correction` (cf. §6.7).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from loguru import logger

from jarvis.providers.memory.kernel import MemoryKernel
from jarvis.providers.memory.schemas import Fact, FactStatus

# ── Mapping catégorie → fichier MD (§6.7) ─────────────────────────────────────

# Les facts par catégorie sont groupés dans le fichier MD correspondant.
# uncertain-beliefs.md = facts à faible confidence (< 0.5) sur belief/persona.
_CATEGORY_TO_FILE: dict[str, str] = {
    "preference": "user/preferences.md",
    "project": "user/projects.md",
    "goal": "user/goals.md",
    "habit": "user/habits.md",
    "constraint": "user/constraints.md",
    "decision": "user/decisions.md",
    "identity": "user/identity.md",
    "values": "user/values.md",
    "relationship": "user/relationships.md",
    "tool": "user/tools.md",
    "health_fitness": "user/health.md",
    "work_style": "user/work_style.md",
    "persona": "jarvis/persona.md",
    "memory_correction": "jarvis/corrections.md",
}

_UNCERTAIN_FILE = "jarvis/uncertain-beliefs.md"
_NEEDS_REVIEW_FILE = "jarvis/needs-review.md"
_UNCERTAIN_THRESHOLD = 0.5

# Bandeau d'avertissement en tête de chaque fichier (lecture seule)
_HEADER_WARNING = (
    "<!-- AUTO-GÉNÉRÉ par memory/mirror.py — NE PAS ÉDITER À LA MAIN. -->\n"
    "<!-- Toute modification sera écrasée à la prochaine régénération. -->\n"
    "<!-- Pour corriger : utiliser la commande Jarvis (crée un human_correction). -->\n"
)


@dataclass
class MirrorReport:
    files_written: list[str]
    facts_exported: int


class MemoryMirror:
    """Exporte le contenu du Kernel vers une arborescence Markdown lisible."""

    def __init__(self, kernel: MemoryKernel, mirror_dir: Path) -> None:
        self._kernel = kernel
        self._dir = Path(mirror_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._dir

    def export(self) -> MirrorReport:
        """Régénère TOUS les fichiers du miroir depuis l'état SQLite actuel."""
        # Récupère tous les facts actifs + ceux à revoir (séparés)
        active = self._kernel.list_facts_by_status(FactStatus.ACTIVE)
        needs_review = self._kernel.list_facts_by_status(FactStatus.NEEDS_REVIEW)

        # Bucket par fichier cible
        by_file: dict[str, list[Fact]] = {}
        uncertain: list[Fact] = []
        for f in active:
            target = _CATEGORY_TO_FILE.get(f.category)
            if target is None:
                # Catégorie connue mais sans fichier dédié → uncertain
                uncertain.append(f)
                continue
            if f.category in ("belief", "persona") and f.confidence < _UNCERTAIN_THRESHOLD:
                uncertain.append(f)
                continue
            by_file.setdefault(target, []).append(f)

        written: list[str] = []
        total = 0
        for filename, facts in by_file.items():
            self._write_file(filename, facts)
            written.append(filename)
            total += len(facts)

        if uncertain:
            self._write_file(_UNCERTAIN_FILE, uncertain, title_override="Croyances incertaines")
            written.append(_UNCERTAIN_FILE)
            total += len(uncertain)

        if needs_review:
            self._write_file(
                _NEEDS_REVIEW_FILE,
                needs_review,
                title_override="Facts à revoir (vocabulaire hors liste)",
            )
            written.append(_NEEDS_REVIEW_FILE)
            total += len(needs_review)

        logger.info("Memory mirror exported", files=len(written), facts=total)
        return MirrorReport(files_written=written, facts_exported=total)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _write_file(
        self,
        filename: str,
        facts: Iterable[Fact],
        title_override: str | None = None,
    ) -> None:
        path = self._dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        facts_list = list(facts)
        title = title_override or _file_to_title(filename)
        body = _render(facts_list, title)
        path.write_text(_HEADER_WARNING + body, encoding="utf-8")


def _file_to_title(filename: str) -> str:
    stem = Path(filename).stem
    return stem.replace("_", " ").replace("-", " ").title()


def _render(facts: list[Fact], title: str) -> str:
    if not facts:
        return f"# {title}\n\n_Aucun fait enregistré._\n"
    # Tri par importance × confidence décroissant
    facts.sort(key=lambda f: (-(f.importance * f.confidence), -f.support_count))
    lines = [f"# {title}", ""]
    lines.append(f"_Mis à jour : {datetime.now().isoformat(timespec='seconds')}_")
    lines.append(f"_{len(facts)} fait(s)._\n")
    for f in facts:
        meta = (
            f"conf {f.confidence:.2f} · imp {f.importance:.2f} · "
            f"vu {f.support_count}× · {f.decay_policy.value}"
        )
        lines.append(f"- **{f.subject} {f.predicate} {f.object}** ({meta})")
        if f.valid_to:
            lines.append(f"  - échéance : {f.valid_to.date().isoformat()}")
    return "\n".join(lines) + "\n"
