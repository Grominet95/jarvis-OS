# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Fakes pour les tests + le smoke runtime — Phase F.

`tests/fakes/llm.py::FakeLLMProvider` est l'implémentation de référence
qui prouve que le Protocol `kernel.contracts.LLMProvider` est
substituable et qu'on peut injecter un provider déterministe via
`bootstrap.build(llm_override=...)`.
"""
