## Description

<!-- Quoi et pourquoi -->

## Checklist

- [ ] `uv run ruff check`
- [ ] `uv run pytest -m "not integration"`
- [ ] **Registre JRV** : si j'ai ajouté ou modifié des chemins d'erreur (`raise`, `except`, réponses HTTP), j'ai mis à jour `scripts/error_audit/error-codes.yaml`, regénéré `_error_codes_generated.py`, et `uv run python scripts/error_audit/check_pr.py` passe
- [ ] En-tête de licence sur les nouveaux fichiers `.py`

## Licence

Je confirme que ma contribution est soumise sous AGPL-3.0-or-later (voir [CONTRIBUTING.md](../CONTRIBUTING.md)).
