# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Synthétiseur de skills — génère et améliore des skills depuis des tâches accomplies."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

import yaml
from loguru import logger

from jarvis.kernel.contracts import LLMProvider
from jarvis.kernel.paths import SKILLS_CANDIDATES_DIR, SKILLS_INSTALLED_DIR  # noqa: F401, E402

# ── Prompts ───────────────────────────────────────────────────────────────────

_SYSTEM_SYNTHESIS = (
    "Tu es un expert en architecture de skills pour agents IA. "
    "Tu génères des skills réutilisables au format agentskills.io (SKILL.md). "
    "Réponds UNIQUEMENT avec le contenu du fichier SKILL.md. "
    "Commence impérativement par '---' (début du frontmatter YAML)."
)

_PROMPT_PROPOSE = """\
Analyse cette tâche Jarvis accomplie avec succès et génère un skill réutilisable.

## Tâche accomplie
{task}

## Extrait de conversation (derniers messages)
{messages}

## Outils utilisés
{tools}

## Résultat
{result}

---
Génère un SKILL.md complet au format agentskills.io capturant ce savoir-faire.

Frontmatter YAML obligatoire :
  name        : kebab-case, 2-64 chars (minuscules + chiffres + tirets, pas en début/fin)
  description : précise, max 200 chars — décrit QUAND utiliser ce skill
  license     : MIT
  metadata    :
    author  : jarvis-synthesizer
    version : "1.0"
    tags    : [tag1, tag2]   # 2-5 tags pertinents

Corps Markdown :
  Instructions concrètes en français, étapes numérotées, exemples, cas limites.
  Ce corps servira de prompt-système — rédige-le comme des instructions pour un LLM.

Commence par --- (frontmatter YAML).
"""

_PROMPT_IMPROVE = """\
Améliore ce skill Jarvis avec une nouvelle expérience.

## SKILL.md actuel
{existing}

## Nouvelle expérience à intégrer
{experience}

Consignes :
1. Intègre les leçons apprises dans les instructions
2. Améliore la description si pertinent
3. Incrémente la version (1.0 → 1.1, 1.9 → 2.0)
4. Conserve le même `name` (identifiant immuable)

Commence par --- (frontmatter YAML).
"""


# ── YAML Dumper avec block scalars pour les longues chaînes ──────────────────


class _BlockDumper(yaml.SafeDumper):
    pass


def _str_representer(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_BlockDumper.add_representer(str, _str_representer)


# ── Synthétiseur ──────────────────────────────────────────────────────────────


class SkillSynthesizer:
    """Génère et améliore des skills Jarvis depuis des tâches accomplies.

    Usage::

        synth = SkillSynthesizer(llm=llm)  # llm injecté par bootstrap.build()
        # PHASE 4 : on génère une candidate dans candidates_dir, JAMAIS
        # directement dans installed/. La promotion exige une validation
        # humaine via SkillLab.promote().
        skill_name = await synth.propose_skill_candidate(trajectory)
        await synth.improve_skill(skill_name, "Nouvelle leçon apprise.")
    """

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    # ── API publique ──────────────────────────────────────────────────────────

    async def propose_skill_candidate(
        self,
        trajectory: dict,
        target_dir: Path | None = None,
    ) -> str:
        """PHASE 4 : génère une skill et l'écrit dans `target_dir / {name}/`.

        Variante non-installante de `propose_skill` — la skill est en zone
        tampon et n'est PAS chargée par SkillRegistry tant que le Skill Lab
        ne l'a pas testée en sandbox et que l'humain ne l'a pas validée.

        Args:
            trajectory : dict identique à propose_skill.
            target_dir : dossier racine où écrire {name}/. Par défaut
              SKILLS_CANDIDATES_DIR (skills/candidates). Surchargeable par le
              SkillLab pour tester avec un dossier isolé.

        Returns:
            Nom du skill candidate (kebab-case, = nom du dossier candidate).
        """
        skill_md = await self._llm_propose(trajectory)
        name = self._extract_name(skill_md)
        if not name:
            raise ValueError(
                f"Le LLM n'a pas produit de 'name' kebab-case valide.\n"
                f"Début de la réponse :\n{skill_md[:400]}"
            )

        root = target_dir if target_dir is not None else SKILLS_CANDIDATES_DIR
        cand_dir = root / name
        cand_dir.mkdir(parents=True, exist_ok=True)

        fm = self._parse_frontmatter(skill_md)
        body = self._extract_body(skill_md)

        (cand_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
        (cand_dir / "skill.yaml").write_text(
            yaml.dump(
                self._to_jarvis_yaml(fm, body),
                Dumper=_BlockDumper,
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (cand_dir / "skill.py").write_text(
            self._generate_skill_py(name),
            encoding="utf-8",
        )

        logger.info("Skill candidate générée", name=name, path=str(cand_dir))
        return name

    async def improve_skill(self, skill_name: str, new_experience: str) -> None:
        """Affine un skill existant à partir d'une nouvelle expérience.

        Args:
            skill_name   : nom du skill dans skills/installed/
            new_experience : description textuelle de la nouvelle expérience
        """
        skill_dir = SKILLS_INSTALLED_DIR / skill_name
        skill_md_path = skill_dir / "SKILL.md"
        if not skill_md_path.exists():
            raise FileNotFoundError(f"Skill '{skill_name}' introuvable dans {SKILLS_INSTALLED_DIR}")

        existing = skill_md_path.read_text(encoding="utf-8")
        improved = await self._llm_improve(existing, new_experience)

        fm = self._parse_frontmatter(improved)
        body = self._extract_body(improved)

        skill_md_path.write_text(improved, encoding="utf-8")
        (skill_dir / "skill.yaml").write_text(
            yaml.dump(
                self._to_jarvis_yaml(fm, body),
                Dumper=_BlockDumper,
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (skill_dir / "skill.py").write_text(
            self._generate_skill_py(skill_name),
            encoding="utf-8",
        )

        logger.info("Skill amélioré", name=skill_name)

    # ── LLM ───────────────────────────────────────────────────────────────────

    async def _llm_propose(self, trajectory: dict) -> str:
        messages_txt = "\n".join(
            f"[{m['role']}] {str(m.get('content', ''))[:300]}"
            for m in trajectory.get("messages", [])[-8:]
        )
        tools_txt = "\n".join(
            f"- {tc.get('name', '?')}: {str(tc.get('result', ''))[:200]}"
            for tc in trajectory.get("tool_calls", [])
        )
        prompt = _PROMPT_PROPOSE.format(
            task=trajectory.get("task_description", "(non spécifié)"),
            messages=messages_txt or "(aucun)",
            tools=tools_txt or "(aucun)",
            result=str(trajectory.get("result", "(non spécifié)"))[:500],
        )
        response = await self._llm.complete(
            messages=[{"role": "user", "content": prompt}],
            system=_SYSTEM_SYNTHESIS,
            context="skill-synthesis",
        )
        return str(response).strip()

    async def _llm_improve(self, existing: str, experience: str) -> str:
        prompt = _PROMPT_IMPROVE.format(
            existing=existing,
            experience=experience[:1000],
        )
        response = await self._llm.complete(
            messages=[{"role": "user", "content": prompt}],
            system=_SYSTEM_SYNTHESIS,
            context="skill-improvement",
        )
        return str(response).strip()

    # ── Parsing ───────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_name(skill_md: str) -> str | None:
        """Extrait le champ `name` du frontmatter YAML."""
        m = re.search(
            r"^name:\s*([a-z0-9](?:[a-z0-9-]*[a-z0-9])?)\s*$",
            skill_md,
            re.MULTILINE,
        )
        return m.group(1) if m else None

    @staticmethod
    def _parse_frontmatter(skill_md: str) -> dict:
        """Extrait et parse le frontmatter YAML entre les délimiteurs ---."""
        m = re.match(r"^---\s*\n(.*?)\n---", skill_md, re.DOTALL)
        if not m:
            return {}
        try:
            return yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError as exc:
            logger.warning("Frontmatter YAML invalide", error=str(exc))
            return {}

    @staticmethod
    def _extract_body(skill_md: str) -> str:
        """Extrait le corps Markdown situé après le frontmatter."""
        m = re.match(r"^---\s*\n.*?\n---\s*\n(.*)", skill_md, re.DOTALL)
        return m.group(1).strip() if m else skill_md.strip()

    # ── Génération fichiers Jarvis ────────────────────────────────────────────

    @staticmethod
    def _to_jarvis_yaml(fm: dict, body: str) -> dict:
        """Convertit le frontmatter agentskills.io + corps en skill.yaml Jarvis."""
        metadata = fm.get("metadata") or {}
        tags = metadata.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        version = str(metadata.get("version", "1.0.0"))
        # Normalise la version au format semver
        if re.match(r"^\d+\.\d+$", version):
            version = version + ".0"
        return {
            "name": fm.get("name", "unknown-skill"),
            "version": version,
            "author": str(metadata.get("author", "jarvis-synthesizer")),
            "description": str(fm.get("description", "")),
            "tags": tags,
            "type": "conversational",
            "system_prompt": body,
            "capabilities": [],
            "requires_env": [],
            "requires_tools": [],
        }

    @staticmethod
    def _generate_skill_py(skill_name: str) -> str:
        """Génère le skill.py Jarvis minimaliste pour le skill synthétisé."""
        class_name = "".join(part.capitalize() for part in skill_name.split("-")) + "Skill"
        return textwrap.dedent(f'''\
            from __future__ import annotations
            from jarvis.capabilities.skills.base import SkillBase


            class {class_name}(SkillBase):
                """Skill synthétisé automatiquement par Jarvis."""

                @property  # type: ignore[override]
                def SYSTEM_PROMPT(self) -> str:
                    return self.metadata.get("system_prompt", "")

                def get_system_prompt(self) -> str:  # noqa: D102
                    return self.SYSTEM_PROMPT.strip()

                def is_active(self) -> bool:  # noqa: D102
                    return bool(self.SYSTEM_PROMPT)
        ''')
