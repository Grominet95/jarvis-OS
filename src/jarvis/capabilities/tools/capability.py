"""Tool LLM pour signaler un manque de capacité (PHASE 5 §8).

Le voice/text agent appelle ce tool quand il identifie qu'il ne sait pas
traiter une demande. Le CapabilityEngine cherche d'abord une skill/tool
existant ; sinon, délègue au Skill Lab (PHASE 4) qui génère une candidate
testée en sandbox. EN AUCUN CAS le tool n'installe quoi que ce soit.

Promotion vers installed/ : EXIGE un humain (POST /api/skills/lab/{name}/promote).
"""

from __future__ import annotations

from jarvis.capabilities.tools.base import Tool, ToolResult
from jarvis.kernel.contracts import CapabilityEngine


class ReportMissingCapabilityTool(Tool):
    """Signale un type de tâche que Jarvis ne sait pas faire.

    Le tool NE CRÉE RIEN par lui-même. Il signale un manque, le système :
    1. Cherche si une skill installée ou un tool natif couvre déjà ce besoin
       (heuristique textuelle) — si oui, retourne le pointer.
    2. Sinon, demande au Skill Lab de générer une candidate qui sera
       AUTOMATIQUEMENT testée en sandbox.
    3. Si le sandbox passe vert : la candidate ATTEND une validation humaine
       explicite via POST /api/skills/lab/{name}/promote. Aucune installation
       automatique en MVP, même quand le sandbox réussit.
    4. Le tool retourne un statut clair indiquant ce qui s'est passé.

    Ce tool est l'unique point d'entrée du Capability Engine. Le voice agent
    DOIT l'utiliser quand il identifie un gap, plutôt que d'inventer une
    solution maison.
    """

    name = "report_missing_capability"
    description = (
        "Signaler à Jarvis un type de tâche qu'il ne sait pas faire (ex. "
        "transcrire un fichier audio .ogg, parser un format de données custom, "
        "convertir un format de fichier inconnu). Le système enregistre le "
        "besoin, cherche d'abord si une capacité existe déjà, sinon propose "
        "la création d'une skill candidate qui devra être validée MANUELLEMENT "
        "avant installation. Ce tool NE crée RIEN par lui-même et n'installe "
        "JAMAIS de skill automatiquement — toute capacité doit passer par une "
        "validation humaine."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": (
                    "Verbalisation claire du besoin manquant en 1-3 phrases. "
                    "Ex. : 'transcrire un fichier audio .ogg en texte', "
                    "'extraire les tableaux d'un PDF complexe', "
                    "'envoyer une notification iOS push'. "
                    "Évite de demander : install/installer un paquet/library, "
                    "modifier le core/runtime, sudo, system level — ces "
                    "demandes seront refusées avant même d'être traitées."
                ),
            },
            "example_input": {
                "type": "string",
                "description": (
                    "Optionnel : un échantillon de l'input qui a échoué "
                    "(extrait de texte, chemin de fichier, exemple de format)."
                ),
            },
        },
        "required": ["description"],
    }

    def __init__(self, engine: CapabilityEngine) -> None:
        # Engine requis : aucun fallback silencieux. Si le tool est instancié
        # sans engine, l'erreur est immédiate (pas de chemin install caché).
        self._engine = engine

    async def execute(  # type: ignore[override]
        self,
        description: str,
        example_input: str = "",
    ) -> ToolResult:
        try:
            resolution = await self._engine.detect_and_propose(
                description=description,
                example_input=example_input or None,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(content=f"Erreur CapabilityEngine : {exc}", is_error=True)

        kind = resolution.kind.value
        if kind == "existing_skill":
            return ToolResult(
                content=(
                    f"Une skill installée couvre déjà ce besoin : "
                    f"'{resolution.target_name}'. Utilise-la directement."
                )
            )
        if kind == "existing_tool":
            return ToolResult(
                content=(
                    f"Un tool natif couvre déjà ce besoin : "
                    f"'{resolution.target_name}'. Utilise-le directement."
                )
            )
        if kind == "new_candidate":
            return ToolResult(
                content=(
                    f"Skill candidate '{resolution.target_name}' générée et "
                    f"sandbox vert. EN ATTENTE de validation humaine via "
                    f"POST /api/skills/lab/{resolution.target_name}/promote. "
                    f"Aucune installation automatique en PHASE 5 MVP — "
                    f"signale à l'utilisateur qu'une nouvelle capacité a été "
                    f"proposée et attend son approbation."
                )
            )
        if kind == "sandbox_rejected":
            return ToolResult(
                content=(
                    f"Candidate '{resolution.target_name}' rejetée par le "
                    f"sandbox : {resolution.notes}. Aucune installation. "
                    f"Reformule le besoin ou indique à l'utilisateur que "
                    f"cette capacité n'est pas réalisable automatiquement."
                ),
                is_error=True,
            )
        if kind == "lab_failed":
            return ToolResult(
                content=(
                    "Le Skill Lab n'a pas pu générer de candidate "
                    "(LLM indisponible ou JSON non parsable). Aucune action."
                ),
                is_error=True,
            )
        if kind == "blocked_dangerous":
            return ToolResult(
                content=(
                    f"Demande REFUSÉE — la description évoque INSTALL_PACKAGE "
                    f"ou MODIFY_CORE. Ces opérations exigent l'intervention "
                    f"directe de l'utilisateur et ne peuvent JAMAIS être "
                    f"déléguées à un agent. {resolution.notes}"
                ),
                is_error=True,
            )
        return ToolResult(content=f"Résolution inattendue : {kind}", is_error=True)
