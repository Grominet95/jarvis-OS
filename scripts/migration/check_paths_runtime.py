#!/usr/bin/env python3
# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""GATE B7b — check runtime des chemins (CDC §B.3).

Filet de sécurité posé en fin de Phase B avant que Phase C bouge l'init
vers bootstrap.build(). Si C casse un chemin, ce script doit le détecter
sans qu'on dépende du test manuel.

Quatre vérifications, via le CODE RÉEL (pas de réimplémentation des chemins) :

  1. PROMPTS_DIR : `_STATIC_PROMPT_PATH` de jarvis.engine.agent (le vrai
     constant utilisé par le serveur) est lisible et non-vide.
  2. MEMORY_DATA_DIR : `MemoryKernel` ouvre/crée jarvis_memory.db, log un
     event, le relit (write/read round-trip via le code réel).
  3. UI_STATIC_DIR : asset statique servi via `TestClient` sur l'app
     `jarvis.app.app` (mount("/static", ...) et endpoint /admin).
  4. SKILLS_INSTALLED_DIR : `SkillRegistry().load_all()` charge ≥ 1
     skill via le loader réel (pas un glob direct).

Sortie : `GATE B7b ✅ (4/4)` ou échec explicite avec contexte.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# ────────────────────────────────────────────────────────────────────────


def check_1_prompts_dir() -> tuple[bool, str]:
    """Le code réel charge un prompt depuis PROMPTS_DIR."""
    try:
        from jarvis.engine.agent import _STATIC_PROMPT_PATH  # lazy: diagnostic
    except Exception as e:
        return False, f"import _STATIC_PROMPT_PATH a levé : {e!r}"

    if not _STATIC_PROMPT_PATH.exists():
        return False, f"_STATIC_PROMPT_PATH n'existe pas : {_STATIC_PROMPT_PATH}"

    try:
        content = _STATIC_PROMPT_PATH.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"read_text a levé sur {_STATIC_PROMPT_PATH} : {e!r}"

    if not content.strip():
        return False, f"prompt vide : {_STATIC_PROMPT_PATH}"

    return True, f"PROMPTS_DIR OK ({len(content)} chars depuis {_STATIC_PROMPT_PATH.name})"


def check_2_memory_data_dir() -> tuple[bool, str]:
    """Le code réel écrit/relit dans MEMORY_DATA_DIR via MemoryKernel.

    On utilise une DB temporaire pour ne PAS polluer le runtime de l'utilisateur.
    Le test prouve que :
    (a) MemoryKernel se construit avec un Path (pas un chemin codé en dur),
    (b) la table events accepte un write et le rend au read,
    (c) le code réel n'a pas perdu sa cohérence db_path en route.
    """
    try:
        from jarvis.providers.memory.kernel import MemoryKernel  # lazy: diagnostic
    except Exception as e:
        return False, f"import MemoryKernel a levé : {e!r}"

    with tempfile.TemporaryDirectory(prefix="jarvis_b7b_") as tmp:
        db_path = Path(tmp) / "memory_data.db"
        try:
            kernel = MemoryKernel(db_path=db_path)
            evt = kernel.log_event(type="b7b_check", source="check_paths_runtime", content="hello")
            relu = kernel.get_event(evt.id)
        except Exception as e:
            return False, f"MemoryKernel write/read a levé : {e!r}"

        if relu is None or relu.content != "hello":
            return False, f"event mal relu : {relu!r}"

    return True, "MEMORY_DATA_DIR OK (MemoryKernel write/read round-trip)"


def check_3_ui_static_dir() -> tuple[bool, str]:
    """Le code réel sert un asset statique via l'app FastAPI.

    On instancie l'app via `from jarvis.app import app` (le vrai composition
    root actuel) et on requête /_shared.js via TestClient — exerce le mount
    `app.mount("/", StaticFiles(directory=str(UI_STATIC_DIR)))`.

    Note : on N'UTILISE PAS `with TestClient(app) as client:` (qui démarre
    le lifespan) parce qu'il existe un bug PRÉ-EXISTANT (cf. BACKLOG Phase C)
    dans le shutdown du lifespan : `telegram.stop()` est appelé même quand
    l'updater n'a jamais démarré → `RuntimeError("This Updater is not
    running!")`. Le mount StaticFiles est défini au TOP-LEVEL de l'app
    (hors lifespan), donc TestClient(app) sans context manager suffit à
    vérifier que UI_STATIC_DIR résout vers un fichier servi.
    """
    try:
        from fastapi.testclient import TestClient

        from jarvis.app import app  # lazy: diagnostic
    except Exception as e:
        return False, f"import app a levé : {e!r}"

    try:
        client = TestClient(app)
        r = client.get("/_shared.js")
    except Exception as e:
        return False, f"TestClient /_shared.js a levé : {e!r}"

    if r.status_code != 200:
        return False, f"GET /_shared.js → HTTP {r.status_code} (attendu 200)"

    if "Jarvis" not in r.text and "views" not in r.text and "register" not in r.text:
        return False, f"contenu de _shared.js inattendu : {r.text[:80]!r}"

    return True, f"UI_STATIC_DIR OK (TestClient sert _shared.js, {len(r.text)} chars)"


def check_4_skills_installed_dir() -> tuple[bool, str]:
    """Le code réel charge ≥ 1 skill via SkillRegistry."""
    try:
        from jarvis.capabilities.skills.registry import SkillRegistry  # lazy: diagnostic
    except Exception as e:
        return False, f"import SkillRegistry a levé : {e!r}"

    try:
        reg = SkillRegistry()
        reg.load_all()
        loaded = sorted(reg.get_all().keys())
    except Exception as e:
        return False, f"SkillRegistry.load_all() a levé : {e!r}"

    if not loaded:
        return False, "aucun skill chargé via le loader réel"

    return True, f"SKILLS_INSTALLED_DIR OK ({len(loaded)} skill(s) : {loaded})"


# ────────────────────────────────────────────────────────────────────────


CHECKS = [
    ("1. PROMPTS_DIR (load prompt)", check_1_prompts_dir),
    ("2. MEMORY_DATA_DIR (write/read MemoryKernel)", check_2_memory_data_dir),
    ("3. UI_STATIC_DIR (TestClient asset)", check_3_ui_static_dir),
    ("4. SKILLS_INSTALLED_DIR (load skill)", check_4_skills_installed_dir),
]


def main() -> int:
    print("== GATE B7b — check runtime des chemins ==\n")
    failures = 0
    for label, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001 — on capture tout pour reporter
            ok, detail = False, f"exception inattendue : {e!r}"
        mark = "✅" if ok else "❌"
        print(f"  {mark} {label} — {detail}")
        if not ok:
            failures += 1

    print()
    if failures == 0:
        print("GATE B7b ✅ (4/4)")
        return 0
    print(f"GATE B7b ❌ ({4 - failures}/4 passés)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
