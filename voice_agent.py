# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Shim de compatibilité racine — voir CDC §B.2 (4).

Le vrai code vit dans `src/jarvis/interfaces/voice/agent.py`. Ce shim
existe pour les appelants externes qui font encore `python voice_agent.py
dev`. Retrait → BACKLOG (post-refonte).

À partir de la Phase B.4, le CLI `jarvis` et le Makefile invoquent
`python -m jarvis.interfaces.voice.agent` directement et ne dépendent
plus de ce shim.
"""

from __future__ import annotations

from jarvis.interfaces.voice.agent import main

if __name__ == "__main__":
    main()
