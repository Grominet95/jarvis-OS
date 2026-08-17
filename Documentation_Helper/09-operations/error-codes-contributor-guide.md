# Codes erreur JRV — guide contributeur (humains)

Ce guide s'adresse aux développeurs et ops qui maintiennent les codes erreur **sans passer par une IA**.

## Lire un code dans le terminal

Format :

```text
[JRV-XXX-NNN] ERROR: Titre — message détaillé
[JRV-XXX-NNN] WARN: ...
```

Où chercher :

| Emplacement | Contenu |
|-------------|---------|
| Terminal (stderr) | Affichage immédiat au lancement ou à l'échec |
| `%TEMP%\jarvis\api.log` | Historique API (Windows) |
| Réponse HTTP | Header `X-Jarvis-Error-Code` + JSON `code` |

Catalogue complet : [error-codes.md](error-codes.md)  
Symptômes fréquents : [error-catalog.md](../playbooks/error-catalog.md)

## Deux niveaux de codes

| Niveau | Exemple | Usage |
|--------|---------|-------|
| **Générique domaine** | `JRV-TOL-001` | Catch-all outil, autofix |
| **Spécifique symptôme** | `JRV-TOL-002` Spotify | Diagnostic ops précis |

Un warning `JRV-PRO-001` est souvent **normal** si un service externe (email, news) est offline.

## Quand ajouter un nouveau code

Ouvrez une PR si :

- Un symptôme récurrent n'a pas d'entrée dans le catalogue
- Les ops perdent du temps sans code distinct
- Un nouvel outil/skill/API expose un chemin d'échec utilisateur

Un ticket suffit si c'est un one-shot debug sans impact ops.

## Checklist PR (7 étapes)

1. Identifier le site d'échec (`scan.py --check` ou `inventory.json`)
2. Choisir le domaine (`TOL`, `API`, `MEM`, …) et le prochain `NNN` libre
3. Ajouter l'entrée dans `scripts/error_audit/error-codes.yaml` (français **avec accents**)
4. Régénérer :
   ```bash
   uv run python scripts/error_audit/generate_registry.py
   uv run python scripts/error_audit/generate_docs.py
   ```
5. Câbler le code Python (`collector`, `raise_api_error`, ou `# jrv:` si intentional)
6. Vérifier :
   ```bash
   uv run python scripts/error_audit/scan.py --check
   uv run pytest tests/test_error_codes_registry.py -q
   ```
7. Mettre à jour `playbooks/error-catalog.md` si symptôme user-facing

## Table des domaines (raccourci)

| Préfixe | Signification | Exemple terminal |
|---------|---------------|------------------|
| JRV-KRN | Kernel, preflight, bundle | Port occupé, deps cassées |
| JRV-LLM | Providers LLM | 429, clé invalide |
| JRV-API | Routes HTTP | 404, 503 service down |
| JRV-TOL | Outils (Spotify, Gmail…) | `[JRV-TOL-002]` sur stderr |
| JRV-GWY | Gateway chat | Chat silencieux |
| JRV-BGT | Budget | BudgetGuard dépassé |
| JRV-VOI | Voix LiveKit | Port 7880 refusé |
| JRV-UNK | Exception non gérée | Bug non intercepté |

## Cas fréquents

**Warning PRO-001 en boucle**  
Collecteur proactive offline. Vérifiez credentials ; non bloquant pour le chat.

**HTTP 401 + JRV-API-002**  
Token Bearer manquant ou invalide. Voir `API_AUTH_TOKEN` dans `.env`.

**Tool Spotify + JRV-TOL-002**  
Reconnectez Spotify dans Réglages ; vérifiez `SPOTIFY_*` dans `.env`.

**Preflight JRV-KRN-010**  
Port déjà utilisé. Fermez l'instance Jarvis précédente ou changez `PORT`.

## Fichiers à ne pas éditer à la main

- `src/jarvis/kernel/_error_codes_generated.py`
- `Documentation_Helper/09-operations/error-codes.md`

## Guides complémentaires

- [error-collector-guide.md](../00-meta/error-collector-guide.md) — API Python (`collector`, `raise_api_error`)
- [error-codes-ai-instructions.md](../00-meta/error-codes-ai-instructions.md) — workflow pour agents IA
- [troubleshooting.md](troubleshooting.md) — diagnostic général
- [logs-and-doctor.md](logs-and-doctor.md) — logs et doctor
