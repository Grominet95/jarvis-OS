# Attribution — Budget & Cost Control

Les fichiers `core/budget.py` et les extensions de `agent/project_store.py`
(claim atomique, pause budgétaire) s'inspirent de l'architecture du projet
**Paperclip** (https://github.com/paperclipai/paperclip).

## Licence source

```
MIT License

Copyright (c) 2024 Paperclip AI, Inc.

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

## Patterns réutilisés

| Pattern Paperclip (TypeScript)              | Adaptation Jarvis (Python)                         |
|---------------------------------------------|----------------------------------------------------|
| `budgetStatusFromObserved(obs, amount, pct)` | `BudgetGuard._scope_status(scope, spent)`          |
| `pauseScopeForBudget(policy)` DB update      | `ProjectStore.pause_for_budget(project, step_id)`  |
| `cancelWorkForScope` hook                    | `_BudgetExceeded` exception → pause propre         |
| `budgetIncidents` table (dédup warn)         | `BudgetGuard._warned: set[str]`                    |
| `resolveWindow(windowKind)` calendar_month   | `BudgetGuard._global_spent()` → JSONL mois courant |
| `approval` atomicity (`RETURNING`)           | `ProjectStore.claim_step()` via `fcntl.LOCK_EX`    |

## Différences notables

- Paperclip utilise PostgreSQL (Drizzle ORM) ; Jarvis utilise des fichiers JSONL/JSON.
- Le budget global mensuel est lu directement depuis les fichiers `memory_data/conso/`
  déjà écrits par `core/tracking.py` — pas de table `costEvents` séparée.
- Le verrou d'exclusivité mutuelle est `fcntl.flock(LOCK_EX)` sur un fichier
  `.jarvis/claims.lock` au lieu d'un `UPDATE … RETURNING` SQL.
- Les scopes supportés sont `global`, `project:<id>` et `run:<id>` (extensible).
