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
4. Ouvre une pull request en décrivant le quoi et le pourquoi.

## En-tête de licence

Chaque nouveau fichier `.py` doit porter l'en-tête de licence court présent dans les
fichiers existants (copyright + référence AGPL-3.0 + lien vers `LICENSE`).
