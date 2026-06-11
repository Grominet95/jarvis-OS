"""ProjectManager — analyse une mission et la décompose en étapes exécutables."""

from __future__ import annotations

import json
import re

from loguru import logger

from jarvis.engine.mission.project_store import ProjectStore
from jarvis.engine.mission.schemas import Project, Step, StepStatus
from jarvis.engine.vocab import AccessLevel
from jarvis.kernel.contracts import LLMProvider

_PLANNING_SYSTEM = """\
Tu es un chef de projet expert. Analyse la demande utilisateur et décompose-la en étapes
précises et exécutables par un agent autonome travaillant dans un workspace isolé.

Règles générales :
- Chaque étape est atomique (une seule action claire)
- Marque requires_approval=true pour : push git, envoi email/message, appel API avec side effects,
  suppression de fichiers, déploiement en production
- Maximum 12 étapes (RAPPORT.md inclus)
- Sois réaliste sur ce qui est faisable dans un répertoire isolé

Règles qualité obligatoires :
- Insère une étape de vérification/test toutes les 3-4 étapes de production (exécuter le code,
  vérifier les liens HTML, tester une fonctionnalité clé)
- Ajoute une étape de test final avant la livraison

Types de projet :
- "website"       : site HTML/CSS/JS, landing page, portfolio
- "python_script" : script Python, automatisation, traitement de données
- "content"       : document, rapport, contenu textuel
- "fusion_360"    : modélisation 3D dans Autodesk Fusion 360
- "generic"       : tout autre type

Règles spéciales pour fusion_360 :
- Détecte fusion_360 si la demande mentionne Fusion 360, CAO, modélisation 3D,
  impression 3D, STL, coque, boîtier, pièce 3D, etc.
- Chaque étape doit décrire EXACTEMENT l'opération Fusion 360 à faire avec l'outil fusion_360.
- NE PAS utiliser execute_cli ou write_file pour des tâches Fusion 360.
- L'agent dispose de l'outil fusion_360(action="execute_script", script="...")
  pour exécuter des scripts Python Fusion API.
- Les scripts Fusion utilisent adsk.core, adsk.fusion, et les CENTIMÈTRES (10mm → createByReal(1)).
- Chaque étape = une opération (sketch, extrusion, fillet, shell, export STL, etc.)
- Toujours prendre un screenshot après les opérations importantes.
- requires_network=false (Fusion est local)
- Exemple d'étape Fusion : "Créer le sketch de base 14.3x7.1 cm sur le plan XY,
  puis l'extruder de 1.5 cm vers le haut avec l'outil fusion_360."

Réseau :
- requires_network=true si le projet nécessite internet (npm install, pip install, API externe,
  téléchargement de ressources)
- requires_network=false pour tout ce qui est faisable offline (dont Fusion 360)

Pour CHAQUE étape, tu DOIS fournir un critère de succès vérifiable.

Règles success_criterion (obligatoire, non vide) :
- Décrit ce que signifie "étape terminée" en termes OBJECTIFS et VÉRIFIABLES
- Préfère des conditions mesurables : "le fichier X existe et fait > N lignes",
  "la commande Y exit 0", "le HTML contient un <h1> avec le texte Z"
- Ne dis JAMAIS "le code marche bien" ou "tout est ok" — ce n'est pas vérifiable

Règles verification_command (facultatif, exit 0 = succès) :
- Si l'étape produit du code/fichiers testables, fournis une commande shell qui
  exit 0 ssi le critère est atteint. Ex : "test -s index.html", "python3 -c 'import script'"
- Vide ou null si pas de commande déterministe

Règles access_level (entier 0-5, par défaut 1) :
- 0 = READ_ONLY (lecture seule)
- 1 = WRITE_LOCAL (créer/modifier dans le workspace) — défaut
- 2 = EXECUTE_CODE (exécuter du code sandboxé)
- 3 = NETWORK (appel réseau)
- 4 = INSTALL_PACKAGE (pip/npm install — DEMANDE TOUJOURS approbation humaine)
- 5 = MODIFY_CORE (jamais demandé en mission)

Réponds UNIQUEMENT avec du JSON valide (sans markdown, sans commentaires) :
{
  "title": "Titre court du projet (< 40 chars)",
  "project_type": "website|python_script|content|fusion_360|generic",
  "requires_network": false,
  "steps": [
    {
      "id": "step_001",
      "title": "Titre de l'étape (< 50 chars)",
      "description": "Description précise de ce que l'agent doit faire (1-3 phrases)",
      "success_criterion": "Condition objective et vérifiable d'achèvement",
      "verification_command": null,
      "access_level": 1,
      "requires_approval": false
    }
  ]
}
"""


class ProjectManager:
    def __init__(self, llm: LLMProvider) -> None:
        self._store = ProjectStore()
        self._llm = llm

    async def create_project(self, mission: str, timeout_minutes: int = 30) -> Project:
        logger.info("ProjectManager planning", mission=mission[:80])

        raw = await self._llm.complete(
            messages=[{"role": "user", "content": f"Mission : {mission}"}],
            system=_PLANNING_SYSTEM,
            stream=False,
        )
        assert isinstance(raw, str)

        plan = self._parse_plan(raw)
        plan = self._add_quality_steps(plan)
        project = self._store.create_project(
            mission=mission,
            title=plan["title"],
            timeout_minutes=timeout_minutes,
        )
        project.requires_network = bool(plan.get("requires_network", False))

        for step_data in plan["steps"]:
            project.steps.append(
                Step(
                    id=step_data["id"],
                    title=step_data["title"],
                    description=step_data["description"],
                    requires_approval=step_data.get("requires_approval", False),
                    status=StepStatus.PENDING,
                    # PHASE 1 — champs vérification & gouvernance (§3.4)
                    success_criterion=step_data.get("success_criterion", "").strip(),
                    verification_command=step_data.get("verification_command") or None,
                    access_level=AccessLevel(
                        int(step_data.get("access_level", int(AccessLevel.WRITE_LOCAL)))
                    ),
                )
            )

        project.llm_calls += 1
        self._store.save_project(project)
        logger.info(
            "Project created",
            id=project.id,
            steps=len(project.steps),
            project_type=plan.get("project_type", "generic"),
            requires_network=project.requires_network,
        )
        return project

    def _add_quality_steps(self, plan: dict) -> dict:
        """Injecte une étape de test typée + RAPPORT.md en fin de plan."""
        project_type = plan.get("project_type", "generic")
        steps = plan["steps"]

        # Retire les doublons que le LLM aurait pu générer
        steps = [
            s
            for s in steps
            if "rapport" not in s.get("title", "").lower() and "test" not in s.get("id", "").lower()
        ]

        n = len(steps)
        test_step = self._add_test_step(project_type, step_num=n + 1)
        rapport_step = {
            "id": f"step_{n + 2:03d}",
            "title": "Générer RAPPORT.md",
            "description": (
                "Crée un fichier RAPPORT.md à la racine du workspace résumant : "
                "la liste des fichiers créés avec leurs tailles, les fonctionnalités "
                "implémentées, les tests effectués et leurs résultats, et les points "
                "d'amélioration éventuels. Format Markdown avec sections ## claires."
            ),
            "requires_approval": False,
            "success_criterion": (
                "Le fichier RAPPORT.md existe à la racine, fait > 200 caractères, "
                "et contient au moins 3 sections '##'."
            ),
            "verification_command": (
                "test -s RAPPORT.md && grep -c '^## ' RAPPORT.md | awk '{exit ($1 >= 3) ? 0 : 1}'"
            ),
            "access_level": int(AccessLevel.WRITE_LOCAL),
        }

        steps.append(test_step)
        if project_type != "fusion_360":
            steps.append(rapport_step)
        plan["steps"] = steps
        return plan

    def _add_test_step(self, project_type: str, step_num: int) -> dict:
        """Retourne une étape de test adaptée au type de projet."""
        step_id = f"step_{step_num:03d}"

        # Critères et access_level partagés par les variantes (vérification = pas de risque accru)
        base = {
            "requires_approval": False,
            "access_level": int(AccessLevel.EXECUTE_CODE),
        }

        if project_type == "website":
            return {
                "id": step_id,
                "title": "Vérification finale du site",
                "description": (
                    "1. Lister tous les fichiers HTML créés avec list_files. "
                    "2. Pour chaque HTML : vérifier que les CSS et JS référencés existent. "
                    "3. Si des fichiers manquent : les créer maintenant. "
                    "4. Vérifier que index.html existe à la racine. "
                    "5. Exécuter une validation syntaxique si possible."
                ),
                "success_criterion": (
                    "index.html existe à la racine et toutes ses dépendances "
                    "CSS/JS/images référencées sont présentes dans le workspace."
                ),
                "verification_command": "test -s index.html",
                **base,
            }

        if project_type == "python_script":
            return {
                "id": step_id,
                "title": "Test du script Python",
                "description": (
                    "1. Exécuter le script principal avec python3 et des données de test. "
                    "2. Vérifier que le code de retour est 0. "
                    "3. Analyser stdout : la sortie est-elle cohérente avec l'objectif ? "
                    "4. Si erreur (returncode != 0) : lire stderr, corriger, relancer. "
                    "5. Ne pas continuer tant que le script ne tourne pas sans erreur."
                ),
                "success_criterion": (
                    "Le script principal s'exécute avec returncode=0 et sa sortie "
                    "stdout correspond à l'objectif initial de la mission."
                ),
                "verification_command": None,
                **base,
            }

        if project_type == "content":
            return {
                "id": step_id,
                "title": "Relecture et cohérence",
                "description": (
                    "1. Lire chaque fichier créé avec read_file et vérifier qu'il n'est pas vide. "
                    "2. Vérifier la cohérence entre les fichiers (références croisées, etc.). "
                    "3. Vérifier que l'objectif initial de la mission est atteint. "
                    "4. Corriger toute incohérence détectée."
                ),
                "success_criterion": (
                    "Tous les livrables texte produits sont non vides, cohérents entre eux, "
                    "et couvrent l'objectif initial de la mission."
                ),
                "verification_command": None,
                **base,
            }

        if project_type == "fusion_360":
            return {
                "id": step_id,
                "title": "Vérification finale Fusion 360",
                "description": (
                    "1. Prendre un screenshot isométrique avec "
                    "fusion_360(action='read', query_type='screenshot',"
                    " direction='iso-top-right'). "
                    "2. Vérifier que la géométrie est visible et conforme à l'objectif. "
                    "3. Si problème détecté, utiliser fusion_360(action='undo') et corriger. "
                    "4. Prendre un screenshot final (direction='top') pour confirmer."
                ),
                "success_criterion": (
                    "Un screenshot final confirme que la géométrie 3D correspond "
                    "à l'objectif décrit dans la mission."
                ),
                "verification_command": None,
                **base,
            }

        # generic (défaut)
        return {
            "id": step_id,
            "title": "Vérification et validation",
            "description": (
                "1. Lister tous les fichiers créés avec list_files, vérifier qu'aucun n'est vide. "
                "2. Vérifier que l'objectif initial de la mission est atteint. "
                "3. Tester / exécuter les livrables principaux si applicable. "
                "4. Corriger tout problème détecté avant de passer à l'étape suivante."
            ),
            "success_criterion": (
                "Tous les livrables principaux existent, sont non vides, et l'objectif "
                "initial de la mission est démontrablement atteint."
            ),
            "verification_command": None,
            **base,
        }

    def _parse_plan(self, raw: str) -> dict:
        clean = re.sub(r"```json|```", "", raw).strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError as e:
            logger.error("Plan parse failed", error=str(e), raw=raw[:300])
            raise ValueError(f"Impossible de parser le plan LLM : {e}") from e
