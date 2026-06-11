"""Smoke runtime — exerce le câblage du Container de bout en bout.

CDC §C.1 tâche 7 — le scénario runtime sur le graphe câblé. Les tests
unitaires ne couvrent pas l'ordre d'init, la durée de vie des singletons
ni le câblage bootstrap. Ce script :

  1. Boote via `bootstrap.build(llm_override=FakeLLMProvider())` — PAS
     via uvicorn, PAS via un Container mocké. Le graphe complet est
     construit dans son ordre réel, avec ses 30+ objets, ses callbacks
     et son bus d'événements.
  2. Exerce les 3 hot paths qui prouvent que l'injection a marché :
     A. LLM    : Gateway.handle("ping") → Agent → LLM → FakeLLM reçoit
                 et répond "pong (fake-llm)". Si le wiring LLM est cassé,
                 la session ne reçoit pas la réponse attendue.
     B. Bus    : publish(BudgetThresholdReached(ratio=1.0, ...)) →
                 handler bootstrap → ProactiveQueue.broadcast_event +
                 NotificationQueue.add. Si le bus est cassé ou le
                 handler non câblé, aucun de ces deux side-effects
                 n'arrive.
     C. Tool   : tool_registry.call_str("memory_load_topic", ...) →
                 MemoryLoadTopicTool → TopicStore (provider injecté).
                 Si l'injection topic_store n'a pas eu lieu, le tool
                 plante au constructeur ou ne lit pas le bon fichier.

  3. Si les 3 passent, imprime BOOT OK et exit 0.
     Si l'un FAIL, imprime FAIL: <quelle étape> et exit 1.

Modes :
  --fake-llm     : injecte FakeLLMProvider via bootstrap.build (gate auto).
  --real         : utilise la clé Anthropic réelle (validation humaine,
                   pas en CI).
  --process=api|voice : Phase F MVP : le scénario est le même quel que
                        soit le process (le bootstrap diffère uniquement
                        sur le câblage voice/agent). Le smoke teste API.
                        Voice = à compléter quand le voice loop sera
                        runnable hors-LiveKit.

Mortalité prouvée : casser le wiring d'un provider dans bootstrap (ex.
remplacer `llm` par `None`, ou commenter `bus.subscribe(...)`) fait
échouer le smoke. C'est exactement ce qu'aucune autre gate n'attrape.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jarvis.bootstrap import Container
    from tests.fakes.llm import FakeLLMProvider

# `tests/fakes/` n'est pas un package installé : ajoute la racine repo
# au sys.path pour pouvoir l'importer depuis ce script lancé en CLI.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _exit(code: int, message: str) -> None:
    print(message, flush=True)
    sys.exit(code)


async def _scenario_llm(container: Container, fake_llm: FakeLLMProvider) -> str | None:
    """Hot path A — LLM via Gateway. Retourne None si OK, sinon un détail."""
    try:
        # Gateway.handle stream=False pour récupérer le texte concaténé.
        session, route, response = await container.gateway.handle(
            message="ping",
            session_id=None,
            stream=False,
        )
    except Exception as exc:  # noqa: BLE001 — on capte tout, c'est un smoke
        return f"gateway.handle a levé : {exc!r}\n{traceback.format_exc()[:600]}"
    if not isinstance(response, str):
        return f"gateway.handle a renvoyé {type(response).__name__}, attendu str"
    if "pong" not in response.lower():
        return f"réponse inattendue, attendu 'pong' : {response[:80]!r}"
    # Le FakeLLM doit avoir vu au moins un appel via le streaming + synthèse.
    if not fake_llm.calls:
        return "FakeLLM.calls est vide — l'injection LLM n'a pas pris"
    return None


async def _scenario_bus(container: Container) -> str | None:
    """Hot path B — Bus d'événements. Retourne None si OK."""
    from jarvis.kernel.events import BudgetThresholdReached

    # On vide la file de notifications avant pour observer l'effet seul.
    container.notifications._queue.clear() if hasattr(
        container.notifications, "_queue"
    ) else None

    # On capture aussi les broadcasts UI via abonnement custom au queue.
    captured_broadcasts: list[dict] = []
    original_broadcast = container.proactive_queue.broadcast_event

    def _spy_broadcast(event: dict) -> None:
        captured_broadcasts.append(event)
        original_broadcast(event)

    container.proactive_queue.broadcast_event = _spy_broadcast  # type: ignore[method-assign]

    try:
        await container.bus.publish(
            BudgetThresholdReached(ratio=1.0, provider="global", scope="global")
        )
    except Exception as exc:  # noqa: BLE001
        return f"bus.publish a levé : {exc!r}"
    finally:
        container.proactive_queue.broadcast_event = original_broadcast  # type: ignore[method-assign]

    if not captured_broadcasts:
        return (
            "aucun broadcast après bus.publish(BudgetThresholdReached) — "
            "handler _on_budget_threshold non câblé ?"
        )
    hard_stops = [e for e in captured_broadcasts if e.get("type") == "budget_hard_stop"]
    if not hard_stops:
        return (
            f"broadcast reçu mais sans type 'budget_hard_stop' : "
            f"{[e.get('type') for e in captured_broadcasts]}"
        )
    return None


async def _scenario_tool(container: Container, topics_dir: Path) -> str | None:
    """Hot path C — Tool dépendant d'un provider injecté. Retourne None si OK.

    On écrit un fichier dans le topics_dir réel utilisé par le bootstrap
    (`{memory_dir}/topics/_smoke.md`), puis on demande à
    `memory_load_topic` de le relire. Le tool est instancié par bootstrap
    avec `topic_store=container.topic_store` — si l'injection n'a pas eu
    lieu, l'instance n'existerait pas dans le registry.
    """
    # Crée le fichier dans le topics_dir réel pour que TopicStore le voie.
    smoke_md = topics_dir / "_smoke.md"
    topics_dir.mkdir(parents=True, exist_ok=True)
    smoke_md.write_text("# Smoke topic\n\nSmoke runtime test marker.\n", encoding="utf-8")

    try:
        result = await container.tool_registry.call_str(
            "memory_load_topic",
            {"filename": "_smoke.md"},
        )
    except Exception as exc:  # noqa: BLE001
        return f"tool_registry.call_str a levé : {exc!r}"
    finally:
        # Nettoyage best-effort.
        try:
            smoke_md.unlink()
        except OSError:
            pass

    if "Smoke topic" not in result and "marker" not in result.lower():
        return (
            f"tool memory_load_topic a renvoyé un contenu inattendu : "
            f"{result[:120]!r}"
        )
    return None


async def _run(container: Container, fake_llm: FakeLLMProvider, topics_dir: Path) -> None:
    fail_a = await _scenario_llm(container, fake_llm)
    if fail_a:
        _exit(1, f"FAIL hot-path A (LLM/Gateway) : {fail_a}")

    fail_b = await _scenario_bus(container)
    if fail_b:
        _exit(1, f"FAIL hot-path B (bus) : {fail_b}")

    fail_c = await _scenario_tool(container, topics_dir)
    if fail_c:
        _exit(1, f"FAIL hot-path C (tool/topic_store) : {fail_c}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke runtime — exerce le câblage du Container")
    parser.add_argument(
        "--fake-llm",
        action="store_true",
        help="Injecter FakeLLMProvider via bootstrap (mode gate automatique).",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Utiliser le LLM réel (clé Anthropic requise — validation humaine).",
    )
    parser.add_argument(
        "--process",
        choices=["api", "voice"],
        default="api",
        help="Process à smoker (Phase F MVP : seul 'api' est implémenté).",
    )
    args = parser.parse_args()

    if not (args.fake_llm or args.real):
        _exit(2, "ERREUR : précise --fake-llm OU --real")
    if args.fake_llm and args.real:
        _exit(2, "ERREUR : --fake-llm et --real sont mutuellement exclusifs")
    if args.process == "voice":
        _exit(
            0,
            "SKIP : --process=voice non implémenté en F MVP ; "
            "le voice loop dépend de LiveKit en runtime — à reprendre en G.",
        )

    # Bootstrap : on construit avec un memory_dir temporaire pour isoler le
    # smoke des données utilisateur. Le bootstrap réel utilise settings.memory_dir.
    tmp_memory = tempfile.mkdtemp(prefix="smoke_jarvis_")
    import os

    os.environ["MEMORY_DIR"] = tmp_memory

    # Recharge settings pour que pydantic relise MEMORY_DIR (force fresh import).
    from jarvis.kernel.settings import Settings

    settings_obj = Settings()

    llm_override = None
    if args.fake_llm:
        from tests.fakes.llm import FakeLLMProvider

        llm_override = FakeLLMProvider()

    from jarvis.bootstrap import build

    try:
        container = build(settings=settings_obj, llm_override=llm_override)
    except Exception as exc:
        _exit(1, f"FAIL bootstrap.build : {exc!r}\n{traceback.format_exc()[:1200]}")
        return  # pour le type-checker

    topics_dir = Path(settings_obj.memory_dir) / "topics"

    try:
        asyncio.run(_run(container, llm_override, topics_dir))
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        _exit(1, f"FAIL inattendu : {exc!r}\n{traceback.format_exc()[:1200]}")

    _exit(0, "BOOT OK")


if __name__ == "__main__":
    main()
