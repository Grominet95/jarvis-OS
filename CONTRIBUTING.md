# Contribuer à Jarvis OS

Merci de l'intérêt que tu portes au projet ! Les contributions sont les bienvenues :
issues, pull requests, documentation, tests, idées.

## Licence des contributions (inbound = outbound)

Jarvis OS est distribué sous **GNU Affero General Public License v3.0 ou ultérieure**
(AGPL-3.0-or-later), voir [LICENSE](./LICENSE).

En soumettant une contribution (pull request, patch, ou tout autre apport de code,
de documentation ou de contenu), **tu acceptes que ta contribution soit licenciée
sous les mêmes termes que le projet, à savoir l'AGPL-3.0-or-later** (principe
*inbound = outbound*). Tu confirmes également avoir le droit de soumettre ce code
sous cette licence (que tu en es l'auteur, ou qu'il est compatible AGPL-3.0).

Aucun accord de cession de droits (CLA) n'est requis : le simple fait de contribuer
vaut accord sur cette base.

## Implications de l'AGPL-3.0

- Toute redistribution (modifiée ou non) doit rester sous AGPL-3.0 et fournir le code source.
- **Usage réseau (clause §13)** : si tu fais tourner une version modifiée sur un serveur
  accessible à des utilisateurs distants, tu dois leur proposer le code source correspondant.

## Workflow

1. Forke le dépôt et crée une branche dédiée (`feat/...`, `fix/...`).
2. Garde les commits atomiques et descriptifs.
3. Avant d'ouvrir la PR, vérifie que ça passe :
   - `uv run ruff check`
   - `uv run pytest -m "not integration"`
   - `uv run python scripts/error_audit/check_pr.py` (registre JRV — voir ci-dessous)
4. Ouvre une pull request en décrivant le quoi et le pourquoi (la checklist PR rappelle le registre JRV).

## Codes d'erreur JRV

Chaque chemin d'échec visible (terminal, API, logs) doit être mappé à un code
`JRV-{DOMAINE}-{NNN}` documenté dans le registre.

### Quand mettre à jour le registre

- Nouveau `raise`, bloc `except` avec message utilisateur, ou réponse HTTP d'erreur
- Changement de message, sévérité, résolution, ou domaine d'un échec existant

### Workflow contributeur

1. Ajouter ou modifier l'entrée dans `scripts/error_audit/error-codes.yaml`
   (titres et messages en français avec accents).
2. Regénérer le module Python :
   `uv run python scripts/error_audit/generate_registry.py`
   → met à jour `src/jarvis/kernel/_error_codes_generated.py`.
3. Émettre l'erreur via `error_emit`, `raise_api_error`, ou `JarvisError` avec le code.
4. Vérifier la couverture :
   `uv run python scripts/error_audit/check_pr.py`

Après modification du YAML, resynchroniser Documentation_Helper :

`uv run python scripts/error_audit/sync_doc_helper.py`

(`error-codes.md`, `error_codes.json`, table SQLite `error_codes` dans `doc_index.sqlite`.)

`check_pr.py` vérifie que le YAML et le fichier généré sont synchronisés, puis que
100 % des sites d'erreur sous `src/jarvis/` sont mappés (`scan.py --check`).
La CI exécute ce script à chaque push et pull request.

### Domaines courants

| Préfixe | Zone |
|---|---|
| `JRV-KRN-*` | Kernel, bootstrap, preflight |
| `JRV-API-*` | Routes FastAPI (`interfaces/api/`) |
| `JRV-TOL-*` | Outils (`capabilities/tools/`) |
| `JRV-SKL-*` | Skills |
| `JRV-LLM-*` | Providers LLM |
| `JRV-MEM-*` | Mémoire |
| `JRV-MSN-*` | Mission engine |

Liste complète : `scripts/error_audit/error-codes.yaml`.

## En-tête de licence

Chaque nouveau fichier `.py` doit porter l'en-tête de licence court présent dans les
fichiers existants (copyright + référence AGPL-3.0 + lien vers `LICENSE`).
