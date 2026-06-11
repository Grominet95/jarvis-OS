"""Fakes pour les tests + le smoke runtime — Phase F.

`tests/fakes/llm.py::FakeLLMProvider` est l'implémentation de référence
qui prouve que le Protocol `kernel.contracts.LLMProvider` est
substituable et qu'on peut injecter un provider déterministe via
`bootstrap.build(llm_override=...)`.
"""
