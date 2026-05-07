"""
Script de validation Phase 1 — appelle LLMProvider.complete() et affiche la réponse.
Usage : uv run python scripts/test_llm.py [--stream] [--provider anthropic|openai|mistral|ollama]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Assure que la racine du projet est dans le path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from llm.api import AnthropicProvider, MistralProvider, OpenAIProvider
from llm.factory import get_llm_provider
from llm.local import OllamaProvider


async def run(provider_name: str, stream: bool) -> None:
    providers = {
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
        "mistral": MistralProvider,
        "ollama": OllamaProvider,
        "auto": None,
    }

    if provider_name == "auto":
        provider = get_llm_provider()
        logger.info("Provider auto-sélectionné via .env")
    else:
        cls = providers.get(provider_name)
        if cls is None:
            logger.error("Provider inconnu", name=provider_name)
            sys.exit(1)
        provider = cls()

    logger.info("Health check…")
    ok = await provider.health_check()
    if not ok:
        logger.error("Provider non joignable — vérifier les clés API ou le serveur Ollama.")
        sys.exit(1)
    logger.info("Health check OK")

    messages = [{"role": "user", "content": "Dis-moi bonjour en une phrase, en français."}]
    system = "Tu es Jarvis, l'assistant personnel de Barth. Tu es direct et concis."

    logger.info("Envoi de la requête", stream=stream)

    result = await provider.complete(messages=messages, system=system, stream=stream)

    if stream:
        print("\n── Réponse (stream) ──")
        async for chunk in result:  # type: ignore[union-attr]
            print(chunk, end="", flush=True)
        print("\n──────────────────────")
    else:
        print(f"\n── Réponse ──\n{result}\n──────────────────────")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test LLM Provider — Jarvis Phase 1")
    parser.add_argument(
        "--provider",
        choices=["anthropic", "openai", "mistral", "ollama", "auto"],
        default="auto",
        help="Provider à tester (défaut: auto, lit LLM_PROVIDER dans .env)",
    )
    parser.add_argument("--stream", action="store_true", help="Tester le mode streaming")
    args = parser.parse_args()

    asyncio.run(run(provider_name=args.provider, stream=args.stream))


if __name__ == "__main__":
    main()
