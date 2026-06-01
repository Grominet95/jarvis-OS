# Attributions — Routines & Audit (Jarvis V3)

## Inspiration de conception

Le moteur de routines de Jarvis V3 (`background/routines.py`, `background/scheduler.py`)
s'inspire des patterns architecturaux des projets open-source suivants.
Aucun code source n'a été copié ; seules les **idées de conception** (nommage, politiques,
structure des enregistrements) ont été adaptées en Python.

---

### Paperclip — paperclipai/paperclip

- **URL** : https://github.com/paperclipai/paperclip
- **Licence** : MIT
- **Commit de référence** : depth-1 clone, 2026-05-29
- **Concepts repris** :
  - Modèle `Routine` (name, trigger, concurrency_policy, catch_up_policy)
  - Modèle `RoutineRun` (id, status, started_at, finished_at, audit_log)
  - Valeurs de `ConcurrencyPolicy` : `skip_if_active`, `coalesce`, `always_enqueue`
  - Valeurs de `CatchUpPolicy` : `skip_missed`, `enqueue_missed_with_cap`
  - Concept de `RoutineTriggerKind` : `schedule` (→ `cron`), `webhook`, `api` (→ `interval`)
  - Pattern d'activité auditée (`logActivity`) → `AuditStep` + `RoutineRun.audit_log`

**Copyright notice Paperclip** :

```
MIT License

Copyright (c) Paperclip AI, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

### Hermes Agent — NousResearch/hermes-agent

- **URL** : https://github.com/NousResearch/hermes-agent
- **Licence** : MIT (voir dépôt)
- **Commit de référence** : depth-1 clone (dépôt privé / inaccessible au moment du clone)
- **Concepts repris** :
  - Idée de cron en langage naturel → implémentée ici via `next_cron_datetime(expr, after)`
    sur la base d'expressions 5-champs standard (sans dépendance externe)
  - Livraison de résultats sur n'importe quelle plateforme → `target_channel` dans `Routine`

---

## Fichiers concernés

| Fichier | Rôle |
|---|---|
| `background/routines.py` | Modèles Routine, RoutineRun, AuditStep + RoutineStore + fire_routine + next_cron_datetime |
| `background/scheduler.py` | Intégration des boucles de routines dans le Scheduler existant |
| `proactive/engine.py` | Audit trail ProactiveAuditEvent par décision proactive |
| `tests/test_routines.py` | Tests de couverture |

---

*Jarvis V3 est un projet personnel — Barth Houot, 2026.*
