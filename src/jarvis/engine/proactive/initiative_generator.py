"""
InitiativeGenerator — analyse l'état du monde et génère des initiatives.
"""

from __future__ import annotations

import json
import re
import uuid

from loguru import logger

from jarvis.engine.proactive.context_builder import WorldState
from jarvis.engine.proactive.schemas import ExecutionMode, Initiative, InitiativeType, Priority
from jarvis.kernel.contracts import LLMProvider

MAX_INITIATIVES = 5
MAX_HIGH = 3
_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _title_key(title: str) -> str:
    return re.sub(r"\W+", "", title.lower())


def _word_overlap(a: str, b: str) -> float:
    wa = set(re.findall(r"\w+", a.lower()))
    wb = set(re.findall(r"\w+", b.lower()))
    if not wa and not wb:
        return 1.0
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _dedup_similar(items: list, threshold: float = 0.70) -> list:
    result: list = []
    for candidate in items:
        merged = False
        for idx, existing in enumerate(result):
            if _word_overlap(candidate.title, existing.title) >= threshold:
                # Keep the richer one
                score_c = len(candidate.context or "") + len(candidate.reasoning or "")
                score_e = len(existing.context or "") + len(existing.reasoning or "")
                if score_c > score_e:
                    result[idx] = candidate
                merged = True
                break
        if not merged:
            result.append(candidate)
    return result


def _is_valid_json(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except Exception:
        return False


def _salvage_json(s: str) -> str | None:
    """Extrait les objets d'initiative complets d'un JSON tronqué."""
    # Trouver tous les objets complets dans le tableau "initiatives"
    start = s.find('"initiatives"')
    if start == -1:
        return None

    items = []
    depth = 0
    in_str = False
    escape = False
    obj_start = None

    for i, ch in enumerate(s[start:], start):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"' and not escape:
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and obj_start is not None:
                items.append(s[obj_start : i + 1])
                obj_start = None

    if not items:
        return None

    return '{"initiatives": [' + ",".join(items) + "]}"


def _apply_caps(items: list) -> list:
    sorted_items = sorted(items, key=lambda x: _PRIORITY_ORDER.get(str(x.priority), 9))
    result: list = []
    high_count = 0
    for i in sorted_items:
        if str(i.priority) == "high":
            if high_count >= MAX_HIGH:
                continue
            high_count += 1
        result.append(i)
        if len(result) >= MAX_INITIATIVES:
            break
    return result


# Corps statique du prompt d'initiatives (indépendant de l'utilisateur). Le token
# __NAME__ est substitué par le prénom configuré. Les accolades JSON sont littérales
# (pas de .format) — on utilise .replace pour éviter tout conflit.
_INITIATIVE_BODY = """
Génère 5 initiatives MAX (2 HIGH max).
Chaque champ est limité en longueur — RESPECTE ces limites absolues.

TYPES : draft_response | reminder | suggestion | alert | auto_task | info
MODES : auto | notify | validate

## EXEMPLES DE CROISEMENTS INTELLIGENTS

Ces exemples illustrent le TYPE de raisonnement attendu.
Ne les copie pas — utilise-les comme modèle de logique.

### Météo × Agenda
Si un événement extérieur est dans les 2h ET qu'il va pleuvoir :
→ "Il va pleuvoir à [heure] — ton RDV [événement] est à [heure], pense au parapluie."
→ type: reminder, priority: high

### Email en attente × Deadline
Si un email requiert une action ET qu'une deadline liée approche dans 24h :
→ "La commande [X] attend ta validation — délai fabrication = semaines, chaque jour compte."
→ type: alert, priority: high

### Agenda libre × Projet bloqué
Si l'agenda est libre pendant 3h+ ET qu'un projet important est en attente :
→ "Fenêtre libre de [durée] — [projet] attend depuis [durée], c'est le bon moment."
→ type: suggestion, priority: medium

### Tâche longtemps en attente × Pattern
Si une tâche est dans Notion depuis plus de 7 jours non cochée :
→ "Post Impulsion en attente depuis 9 jours — bloquer 30min maintenant ?"
→ type: reminder, priority: medium

### Série d'emails sans réponse
Si 3+ emails du même expéditeur sans réponse :
→ "NextPCB t'a contacté 3 fois sans réponse — risque de frein sur la production."
→ type: alert, priority: high

## RÈGLE 0 — RAPPELS TEMPORELS IMMINENTS (priorité absolue)

Si la section AGENDA du contexte contient un événement qui commence dans moins
de 30 minutes, génère IMPÉRATIVEMENT une initiative pour ce rappel — c'est
exactement ce que l'utilisateur attend d'un assistant proactif.

Format obligatoire pour ce type de rappel :
  type           : "reminder"
  priority       : "high"
  execution_mode : "notify"   (PAS "validate" — l'utilisateur doit recevoir
                                le rappel intégré dans sa prochaine réponse,
                                pas dans un panneau de décision séparé)
  title          : "Rappel : <nom événement> dans <X> min"
  action         : "Préparer / rejoindre <nom événement> à <heure>"

Cette règle prime sur la règle 3 ci-dessous ("doit déclencher une action concrète") :
un rappel temporel imminent EST une action concrète (préparer / rejoindre).

## RÈGLES DE QUALITÉ

1. Maximum 5 initiatives par cycle, maximum 2 HIGH
2. Zéro doublon — si un sujet a été traité dans la journée, ne pas régénérer
3. Une initiative doit déclencher une ACTION concrète de __NAME__ dans les 48h
   Si ce n'est pas le cas → c'est une observation, pas une initiative. Ne pas inclure.
4. Chaque initiative doit se résumer en 10 mots max
5. Priorité HIGH seulement si l'inaction a des conséquences réelles sous 24h

Réponds UNIQUEMENT en JSON valide, sans markdown, sans explication :
{
  "initiatives": [
    {
      "type": "...",
      "title": "60 chars max",
      "context": "80 chars max",
      "action": "80 chars max",
      "priority": "high|medium|low",
      "execution_mode": "auto|notify|validate",
      "to_email": "email@dest.com ou null",
      "email_subject": "Sujet court ou null",
      "thread_id": "thread_id ou null",
      "mission_description": "60 chars max ou null"
    }
  ]
}
"""

def _initiative_system(name: str, profile: str = "") -> str:
    """Prompt système du moteur d'initiatives, personnalisé au prénom + bio."""
    header = f"\nTu es le moteur d'analyse proactif de Jarvis, assistant personnel de {name}."
    if profile.strip():
        header += f"\n{name} : {profile.strip()}"
    return header + "\n" + _INITIATIVE_BODY.replace("__NAME__", name)


def _draft_system(name: str) -> str:
    return (
        f"\nTu es Jarvis, assistant de {name}. Rédige un brouillon d'email professionnel,\n"
        "direct, 3 phrases max (50 mots max).\n"
        "Réponds UNIQUEMENT avec le corps du message, sans salutation formelle inutile, en français.\n"
    )


def _rectify_system(name: str) -> str:
    return (
        f"\nTu es Jarvis, assistant proactif de {name}. Tu dois régénérer une initiative\n"
        "en intégrant la correction de l'utilisateur.\n"
        "Réponds UNIQUEMENT en JSON valide (un seul objet, pas un tableau) avec\n"
        "les mêmes champs que l'initiative originale.\n"
        "Si le type est draft_response, respecte impérativement le format :\n"
        "À: email@destinataire.com\n"
        "Sujet: RE: Sujet\n"
        "[THREAD_ID: id]\n"
        "---\n"
        "Corps\n"
    )


class InitiativeGenerator:
    def __init__(
        self, llm: LLMProvider, user_firstname: str = "Barth", user_profile: str = ""
    ) -> None:
        self._llm = llm
        self._name = user_firstname
        self._initiative_system = _initiative_system(user_firstname, user_profile)
        self._draft_system = _draft_system(user_firstname)
        self._rectify_system = _rectify_system(user_firstname)

    async def generate(self, state: WorldState) -> list[Initiative]:
        """Génère des initiatives à partir de l'état du monde."""
        logger.info("InitiativeGenerator: analyzing world state")

        world_context = state.to_prompt_context()
        if not world_context.strip():
            logger.info("InitiativeGenerator: no context available")
            return []

        prompt = (
            f"État du monde de {self._name} :\n\n"
            f"{world_context}\n\n"
            "Génère les 5 initiatives les plus pertinentes et urgentes (3 HIGH max)."
        )

        response = await self._llm.complete(
            messages=[{"role": "user", "content": prompt}],
            system=self._initiative_system,
            stream=False,
            context="proactive",
        )
        if not isinstance(response, str):
            chunks: list[str] = []
            async for chunk in response:
                chunks.append(chunk)
            response = "".join(chunks)

        initiatives = self._parse_initiatives(response)

        # Générer les brouillons séparément pour ne pas saturer le JSON principal
        for init in initiatives:
            if init.type == InitiativeType.DRAFT_RESPONSE:
                init.draft_content = await self._generate_draft(init)

        return initiatives

    async def _generate_draft(self, init: Initiative) -> str | None:
        """Génère le brouillon email pour une initiative draft_response."""
        to_email = getattr(init, "_to_email", None) or ""
        subject = getattr(init, "_email_subject", None) or ""
        thread_id = getattr(init, "_thread_id", None) or ""

        prompt = (
            f"Initiative : {init.title}\n"
            f"Contexte : {init.context}\n"
            f"Action : {init.action}\n"
            f"Destinataire : {to_email}\n"
            f"Sujet de l'email original : {subject}\n\n"
            "Rédige le corps du brouillon de réponse (50 mots max, 3 phrases)."
        )
        try:
            body = await self._llm.complete(
                messages=[{"role": "user", "content": prompt}],
                system=self._draft_system,
                stream=False,
                context="proactive",
            )
            if not isinstance(body, str):
                chunks: list[str] = []
                async for chunk in body:
                    chunks.append(chunk)
                body = "".join(chunks)
            body = body.strip()

            header = f"À: {to_email}\nSujet: RE: {subject}"
            if thread_id:
                header += f"\n[THREAD_ID: {thread_id}]"
            return f"{header}\n---\n{body}"
        except Exception as e:
            logger.warning(f"Draft generation failed for {init.id}: {e}")
            return None

    async def rectify(self, initiative: Initiative, correction: str) -> Initiative | None:
        """Régénère une initiative en intégrant la correction utilisateur."""
        prompt = (
            f"Initiative originale :\n"
            f"Titre : {initiative.title}\n"
            f"Type : {initiative.type}\n"
            f"Contexte : {initiative.context}\n"
            f"Raisonnement : {initiative.reasoning}\n"
            f"Action : {initiative.action}\n"
            f"Priorité : {initiative.priority}\n"
            f"Mode : {initiative.execution_mode}\n"
            f"Brouillon : {initiative.draft_content or '(aucun)'}\n\n"
            f"Correction de l'utilisateur : {correction}\n\n"
            "Régénère cette initiative en intégrant la correction."
        )

        response = await self._llm.complete(
            messages=[{"role": "user", "content": prompt}],
            system=self._rectify_system,
            stream=False,
            context="proactive",
        )

        if not isinstance(response, str):
            chunks = []
            async for chunk in response:
                chunks.append(chunk)
            response = "".join(chunks)

        clean = re.sub(r"```json|```", "", response).strip()
        # Accepter objet seul ou tableau d'un élément
        if clean.startswith("["):
            try:
                items = json.loads(clean)
                clean = json.dumps(items[0]) if items else clean
            except Exception:
                pass

        try:
            item = json.loads(clean)
            return Initiative(
                id=initiative.id,  # garde le même id
                type=InitiativeType(item.get("type", initiative.type)),
                title=item.get("title", initiative.title),
                context=item.get("context", initiative.context),
                reasoning=item.get("reasoning", initiative.reasoning),
                action=item.get("action", initiative.action),
                priority=Priority(item.get("priority", initiative.priority)),
                execution_mode=ExecutionMode(item.get("execution_mode", initiative.execution_mode)),
                draft_content=item.get("draft_content") or None,
                mission_description=item.get("mission_description") or None,
                created_at=initiative.created_at,
            )
        except Exception as e:
            logger.error(f"Rectify parsing error: {e}")
            return None

    def _parse_initiatives(self, raw: str) -> list[Initiative]:
        clean = re.sub(r"```json|```", "", raw).strip()

        # Récupération défensive si JSON tronqué
        if clean and not _is_valid_json(clean):
            salvaged = _salvage_json(clean)
            if salvaged:
                clean = salvaged
                logger.warning("InitiativeGenerator: JSON tronqué, récupération partielle")

        try:
            data = json.loads(clean)
            initiatives = []

            for item in data.get("initiatives", [])[:MAX_INITIATIVES]:
                try:
                    init = Initiative(
                        id=f"init_{uuid.uuid4().hex[:8]}",
                        type=InitiativeType(item.get("type", "info")),
                        title=item.get("title", "")[:80],
                        context=item.get("context", "")[:150],
                        reasoning=item.get("reasoning", item.get("action", ""))[:150],
                        action=item.get("action", "")[:100],
                        priority=Priority(item.get("priority", "medium")),
                        execution_mode=ExecutionMode(item.get("execution_mode", "notify")),
                        draft_content=None,  # généré séparément
                        mission_description=(item.get("mission_description") or None),
                    )
                    # Stocker les champs email pour la génération du brouillon
                    init._to_email = item.get("to_email") or ""  # type: ignore[attr-defined]
                    init._email_subject = item.get("email_subject") or ""  # type: ignore[attr-defined]
                    init._thread_id = item.get("thread_id") or ""  # type: ignore[attr-defined]
                    initiatives.append(init)
                except (ValueError, KeyError) as e:
                    logger.warning(f"Skipping malformed initiative: {e}")

            # Dédup exact puis similitude > 70%
            seen: set[str] = set()
            exact_deduped = []
            for i in initiatives:
                k = _title_key(i.title)
                if k not in seen:
                    seen.add(k)
                    exact_deduped.append(i)

            unique = _dedup_similar(exact_deduped)
            capped = _apply_caps(unique)

            logger.info(
                "InitiativeGenerator: %d → %d (dédup) → %d (caps)",
                len(initiatives),
                len(unique),
                len(capped),
            )
            return capped

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Initiative parsing error: {e}\nRaw: {raw[:200]}")
            return []
