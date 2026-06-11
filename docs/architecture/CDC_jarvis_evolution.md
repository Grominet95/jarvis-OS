# Cahier des charges — Évolution de jarvis-OS

**Destinataire : agent de code (Claude Code).**
**Auteur : Barthélemy Houot.**
**Objet : transformer jarvis-OS d'un assistant à mémoire plate en un système à couches — mémoire vivante, exécution de missions vérifiées, auto-apprentissage et prise d'initiative gouvernée.**

---

## 0. COMMENT UTILISER CE DOCUMENT

Lis intégralement ce document AVANT d'écrire la moindre ligne. Il décrit une pile de couches dépendantes. Tu ne dois pas tout implémenter d'un bloc.

Règles de travail impératives :

1. **Respecte l'ordre des phases.** Chaque phase consomme les artefacts de la précédente. Ne commence PHASE N+1 que lorsque la Definition of Done de PHASE N est satisfaite et les tests verts.
2. **La PHASE 0 (contrat de schémas) est sacrée.** Une fois figée et commitée, tu ne modifies plus ces types sans le signaler explicitement comme un changement de contrat. Tout le reste s'y branche.
3. **Tu n'inventes pas de structures de données concurrentes.** S'il te faut un "fait", un "événement", une "étape" ou un "verdict", tu utilises les types du contrat. Jamais une variante locale.
4. **Tu ne touches JAMAIS au core runtime en auto-modification.** Le périmètre auto-modifiable est : skills, prompts, workflows, connecteurs sandboxés. Le reste exige une intervention humaine.
5. **Tu écris les tests en même temps que le code, pas après.** En particulier pour la vérification (PHASE 1) et la réconciliation mémoire (PHASE 3) : ce sont les zones où du code plausible mais faux passe inaperçu.
6. **Quand une décision d'implémentation n'est pas tranchée par ce document, tu t'arrêtes et tu demandes.** Tu ne combles pas un trou de spec par une hypothèse silencieuse.

---

## 1. CONTEXTE DU REPO EXISTANT

jarvis-OS est un serveur FastAPI async, self-hosted, multi-LLM (Anthropic principal, Mistral/Gemini/Ollama en fallback), avec pipeline vocal LiveKit. Modules pertinents pour ce CDC :

- `agent/` — agent projet/code autonome. Contient déjà : `schemas.py` (`Project`, `Step`, `StepStatus`, `ProjectStatus`, `LogEntry`), `orchestrator.py`, `worker_agent.py`, `project_manager.py`, `project_store.py`, `quality_checker.py` (`QualityChecker`), `docker_executor.py`, `file_tool.py`. **C'est ici qu'est le Mission Engine en germe. On l'étend, on ne le recrée pas.**
- `memory/` — `sessions/` (jsonl), `topics/` (notes thématiques, écrites par `TopicStore.write()` qui **écrase** le fichier), `conso/`, `initiatives/`. Consolidation nocturne via `AutoDream` + `ConsolidationAgent`. `user_model.py` (modèle utilisateur dialectique inspiré de Honcho, plafonné à `_MAX_MODEL_WORDS = 300`).
- `skills/` — système de skills pluggables. `SkillSynthesizer` génère des skills au format agentskills.io (`SKILL.md`, `skill.yaml`, `skill.py`) depuis des tâches réussies.
- `proactive/` — moteur proactif + `collectors/`. Pousse des notifications via WebSocket.
- `llm/` — abstraction providers. **Toute interaction LLM passe par là.** Tu ne hardcodes jamais un client Anthropic en dur.
- `background/` — scheduler, worker, file de notifications.
- `config/` — `settings.py` (pydantic-settings), `tools.yaml`.

Conventions du repo à respecter : Python 3.11+, `async`/FastAPI, `dataclass` + `StrEnum`, `loguru` pour le logging structuré, `uv` pour les dépendances, `ruff` pour lint+format. Commentaires en français.

---

## 2. PRINCIPES DIRECTEURS

- **Architecture en couches, chaque couche nourrit la suivante.** Mémoire = fondation (continuité). Mission Engine = premier chantier utile, et il GÉNÈRE les données que la mémoire consomme.
- **La complexité suit l'usage, elle ne le précède pas.** À chaque phase, on livre un MVP qui tourne en usage réel avant d'enrichir. Pas de cathédrale.
- **Périmètre étroit au départ, élargissement piloté par l'usage réel.**
- **Sécurité non optionnelle et transversale.** La gouvernance (§9) existe AVANT toute action qui touche au filesystem ou au réseau. Ce n'est pas une phase finale.
- **Fiabilité > élégance théorique.** Vocabulaires fermés, vérifications déterministes d'abord, échec par défaut en cas de doute.

---

## 3. PHASE 0 — CONTRAT DE SCHÉMAS PARTAGÉS

**À faire en premier, en solo, sans aucun agent parallèle.** C'est la frontière sur laquelle plusieurs agents pourront ensuite travailler sans collision sémantique.

### Objectif
Figer les types de données et vocabulaires partagés par toutes les couches.

### Fichiers concernés
- Étendre `agent/schemas.py` (Mission Engine).
- Créer `memory/schemas.py` (Memory Kernel).
- Créer `core/vocab.py` (vocabulaires fermés + niveaux d'accès + niveaux d'autonomie).

### Spécification détaillée

**3.1 — Vocabulaires fermés (`core/vocab.py`).** Imposés à tout extracteur. Tout terme hors vocabulaire est rejeté ou mis en `needs_review`. Jamais de prédicat/catégorie libre dans la base principale.

- `PREDICATES` (liste fermée) : `is`, `has`, `prefers`, `dislikes`, `uses`, `works_on`, `targets`, `plans`, `believes`, `needs`, `struggles_with`, `decided`, `changed`, `values`, `communicates_as`, `requires_validation_for`.
- `CATEGORIES` (liste fermée) : `identity`, `preference`, `project`, `goal`, `habit`, `constraint`, `belief`, `relationship`, `tool`, `persona`, `decision`, `health_fitness`, `work_style`, `memory_correction`.

**3.2 — Niveaux d'accès (`core/vocab.py`, `IntEnum`).** Ordonnés par risque croissant :
`READ_ONLY=0`, `WRITE_LOCAL=1`, `EXECUTE_CODE=2`, `NETWORK=3`, `INSTALL_PACKAGE=4`, `MODIFY_CORE=5`.
Constante `AUTO_MAX_LEVEL = EXECUTE_CODE` (tout ce qui est ≤ ce niveau peut s'exécuter sans validation humaine).

**3.3 — Niveaux d'autonomie (`core/vocab.py`, `IntEnum`).** Pour les initiatives proactives :
`0` répondre seulement, `1` suggérer, `2` préparer un brouillon/patch, `3` exécuter en sandbox, `4` modifier des fichiers projet, `5` publier/payer/contacter/supprimer (validation humaine obligatoire).

**3.4 — Extension de `Step` (`agent/schemas.py`).** Ajouter aux champs existants, sans casser l'existant :
- `success_criterion: str` — définition de "done", lisible par un grader. **Champ obligatoire** : un `Step` sans critère est invalide.
- `verification_command: str | None = None` — commande déterministe (test/lint/build), exit 0 = succès.
- `access_level: AccessLevel = AccessLevel.WRITE_LOCAL`.
- `verified: bool = False`.
- `verification_notes: str | None = None`.

**3.5 — Types mémoire (`memory/schemas.py`).** Définir `Event`, `Fact`, `FactObservation`, `FactRelation` (détaillés en §6), plus les enums `FactStatus` (`active`, `superseded`, `conflicted`, `archived`, `needs_review`) et `DecayPolicy` (`none`, `very_slow`, `slow`, `medium`, `fast`).

### Erreurs à éviter
- Ne mets PAS de chaîne libre là où un enum du vocabulaire est attendu.
- Ne duplique pas `StepStatus`/`ProjectStatus` existants : réutilise-les.
- N'ajoute pas de logique dans `schemas.py` : ce sont des structures de données pures.

### Tests à écrire
- Un fait/step construit avec un prédicat ou une catégorie hors vocabulaire lève une erreur ou tombe en `needs_review`.
- Sérialisation/désérialisation round-trip de chaque type (vers/depuis dict/JSON) sans perte.
- `Step` sans `success_criterion` est rejeté à la construction ou à la validation du plan.

### Definition of Done
Types et vocabulaires commités, importables, couverts par tests de round-trip. Aucune autre couche n'a encore commencé.

---

## 4. PHASE 1 — MISSION ENGINE

### Objectif
Transformer une demande vague en mission persistante, exécutée étape par étape, **avec vérification réelle de l'atteinte de l'objectif** et gouvernance en amont. Premier chantier, le plus utile au quotidien.

### Fichiers concernés
- Étendre : `agent/orchestrator.py`, `agent/worker_agent.py`, `agent/project_store.py`, `agent/quality_checker.py`.
- Créer : `agent/verifier.py` (vérification deux temps), `agent/governance.py` (gate composite à 3 axes — cf. §9).

### Spécification détaillée

**4.1 — Objet Mission persistant.** Une mission = `Project` (objectif + plan + `Step`s + état + `workspace_path` + artefacts + logs + verdict). Elle doit survivre à un redémarrage : `project_store` persiste l'état complet pour reprise le lendemain sans repartir de zéro. Statuts via `ProjectStatus` existant.

**4.2 — Planification.** L'orchestrator décompose la mission en `Step`s. **Chaque Step DOIT porter un `success_criterion` explicite et, si possible, une `verification_command`.** L'orchestrator REFUSE de lancer un plan dont un step n'a pas de critère.

**4.3 — Self-verification en deux temps (`agent/verifier.py`).** C'est le cœur dur de cette phase. Le `QualityChecker` actuel vérifie que l'artefact est **bien formé** (fichier non vide, syntaxe Python qui parse, refs HTML présentes) — il ne vérifie JAMAIS que l'artefact **atteint l'objectif**. Il faut donc :
- **Couche 1 — structurelle** : réutiliser `QualityChecker.check_step_output()` tel quel. Déterministe, gratuit. Si l'artefact est mal formé, on s'arrête là (pas d'appel LLM).
- **Couche 2 — déterministe** : si le step a une `verification_command`, l'exécuter via `docker_executor`. Exit ≠ 0 → échec. Cette couche fait foi quand elle existe.
- **Couche 3 — sémantique** : seulement si 1 et 2 passent. Un appel LLM (via `llm/`) qui compare l'artefact produit au `success_criterion` ET à la mission globale, et rend un verdict JSON `{verified: bool, issues: [str], notes: str}`. Le prompt doit demander au grader d'être **strict et sceptique** : `verified=true` seulement si le critère est réellement atteint, pas si le fichier existe ou compile.
- **En cas de doute, on NE valide PAS.** Verdict LLM illisible / non parsable → `verified=false`. Un échec de parse n'est jamais un succès.

**4.4 — Règle de progression.** Une étape non vérifiée NE passe PAS à la suivante. Retry borné (ex. 2 essais) ; au-delà → step `FAILED`, mission `PAUSED` ou `FAILED`, et une leçon écrite (cf. PHASE 2). C'est ce qui empêche les erreurs de composer sur une mission longue.

**4.5 — Gouvernance en amont (`agent/governance.py`).** AVANT d'exécuter un step, appeler le **gate composite** spécifié au §9. Il compose **trois axes orthogonaux** : risque technique (`access_level` du Step), catégorie d'approbation (`ApprovalChecker` existant), budget (`BudgetGuard` existant). Le filtre le plus restrictif gagne (OU côté refus/demande). `gate()` renvoie `auto` | `dry_run` | `approval`. `approval` → step en `WAITING_APPROVAL` (statut déjà existant), on attend l'humain. La gouvernance n'est pas un ajout postérieur : elle encadre chaque step dès cette phase.

### Erreurs à éviter
- **Ne JAMAIS considérer "le fichier existe / compile" comme une vérification de succès.** C'est le piège central : un livrable plausible et faux.
- Ne pas confondre couche structurelle et sémantique. La structurelle ne doit pas appeler le LLM ; la sémantique ne doit pas re-vérifier la syntaxe.
- Ne JAMAIS exécuter un step sans passer par `gate()` — qu'il dépasse `AUTO_MAX_LEVEL` (axe risque), qu'il tombe sur une catégorie d'`ApprovalConfig` en `ASK`/`NEVER` (axe sémantique), ou que le `BudgetGuard` soit en `hard_stop` (axe coût). Le gate composite est la seule porte d'entrée (cf. §9).
- Ne pas avancer "en parallèle" sur les steps d'une mission s'ils ont des dépendances : respecter l'ordre du plan.
- Ne pas perdre l'état de mission au redémarrage : tout passe par `project_store`.

### Tests à écrire
- Un step dont l'artefact compile mais ne répond PAS au critère est rejeté par la couche sémantique (test avec un faux grader déterministe + un cas réel).
- Un step avec `verification_command` qui sort exit≠0 échoue avant même la couche sémantique.
- Un verdict LLM non parsable → `verified=false`.
- Un step `MODIFY_CORE` ou `INSTALL_PACKAGE` déclenche systématiquement `approval`.
- Reprise de mission : on tue le process en plein milieu, on relance, l'état est intact et la mission reprend au bon step.
- Une étape non vérifiée bloque la progression (le step suivant ne démarre pas).

### Definition of Done
Une mission réelle de bout en bout (ex. "réorganise ce dossier" ou "audite ce composant React") : planifiée avec critères, exécutée, chaque step vérifié aux 3 couches, gouvernance respectée, état persistant, verdict final. Tests verts.

---

## 5. PHASE 2 — REFLEXION POST-MISSION

### Objectif
Faire en sorte que chaque mission rende l'agent légèrement meilleur. Chaînon entre exécution et apprentissage. **Branche-toi sur le Memory Kernel (PHASE 3) — n'invente pas de stockage séparé.** Si PHASE 3 n'est pas encore prête, écris la leçon dans l'event log brut et marque le hook pour consolidation ultérieure.

### Fichiers concernés
- Créer : `agent/reflexion.py`.
- Consommé par : `memory/` (la leçon devient un fact `decision`).

### Spécification détaillée
**5.1** À la fin de chaque mission (succès, échec ou partiel), produire une **leçon d'exécution** structurée : ce qui a marché, ce qui a échoué, cause probable, quoi faire différemment, et — point clé — **est-ce que cette mission contient un pattern réutilisable ?** (drapeau `skill_candidate: bool` + description).
**5.2** La leçon est écrite comme `Event` (type `mission_lesson`) puis consolidée en `Fact` de catégorie `decision` dans le Memory Kernel.
**5.3** Si `skill_candidate=true`, émettre un signal vers le Skill Lab (PHASE 4) — ne crée PAS la skill ici.

### Erreurs à éviter
- Ne pas créer de table/fichier de leçons parallèle à la mémoire : la leçon EST de la mémoire.
- Ne pas générer une skill automatiquement depuis la reflexion : ici on ne fait que la PROPOSER.

### Tests à écrire
- Une mission échouée produit une leçon avec cause et action corrective non vides.
- Une mission contenant un pattern répété lève `skill_candidate=true`.
- La leçon est bien ingérée comme fact `decision` (test d'intégration avec PHASE 3).

### Definition of Done
Toute mission terminée produit une leçon traçable, ingérée en mémoire, avec proposition de skill le cas échéant.

---

## 6. PHASE 3 — MEMORY KERNEL

### Objectif
Remplacer les `topics/` plats par une mémoire structurée, datée, sourcée, renforçable, oubliable et corrigeable. **SQLite comme source de vérité unique ; Markdown comme miroir en lecture seule.**

### Fichiers concernés
- Créer : `memory/kernel.py` (couche d'accès SQLite), `memory/ingest.py` (extraction + réconciliation), `memory/mirror.py` (export Markdown), `memory/retrieval.py`.
- Adapter : `memory/user_model.py`, `AutoDream`/`ConsolidationAgent` (deviennent producteurs de facts, plus seulement de notes thématiques).
- Conserver : `memory_data/topics/` peut rester comme vault lisible, mais n'est plus la source de vérité.

### Spécification détaillée

**6.1 — Base unique.** Un seul fichier `memory_data/jarvis_memory.db` (SQLite), embeddings via l'extension `sqlite-vec` dans la MÊME base. **Pas de Neo4j, pas de Qdrant, pas de Chroma en PHASE 3.** On ne les introduira que le jour où des requêtes multi-sauts réelles l'exigent — ce qui pour un mono-utilisateur peut ne jamais arriver.

**6.2 — Quatre tables.**
- `events` : log immuable de tout ce qui arrive. Champs : `id`, `type`, `source`, `content`, `metadata_json`, `created_at`. **On ne supprime jamais un event brut.**
- `facts` : claims atomiques (une idée par fact). Champs : `id`, `subject`, `predicate` (∈ PREDICATES), `object`, `category` (∈ CATEGORIES), `status` (∈ FactStatus), `confidence` (float), `support_count` (int), `decay_policy` (∈ DecayPolicy), `valid_from`, `valid_to`, `source_event_id`, `created_at`, `last_seen_at`, `updated_at`.
- `fact_observations` : renforcement sans duplication. Champs : `id`, `fact_id`, `event_id`, `observation_type` (`confirm`|`weaken`|`correct`), `confidence_delta`, `created_at`. **Indispensable pour tracer l'historique des confirmations.**
- `fact_relations` : `id`, `from_fact_id`, `to_fact_id`, `relation_type` (`supersedes`|`contradicts`|`supports`|`related_to`), `created_at`.

**6.3 — Atomicité.** Une note = une idée. Pas de bloc "Projet X" contenant dix infos. "Barth vise sub-3h" est un fact ; "Barth court depuis un an" en est un autre. Sans atomicité, la datation et le decay sont inopérants.

**6.4 — Pipeline d'ingestion (`memory/ingest.py`).** À chaque échange/observation important :
1. Logger l'`Event` brut (immuable).
2. Extraire **0 à 5 facts maximum** via LLM, avec prédicat/catégorie **imposés depuis le vocabulaire fermé**. Hors vocabulaire → `needs_review`, jamais en base principale.
3. Normaliser `subject`/`predicate`/`category`.
4. Chercher un fact actif similaire (même `subject`+`predicate`+`category`).
5. Trois cas de réconciliation :
   - **Identique/quasi-identique** → ne pas dupliquer : créer une `FactObservation` `confirm`, augmenter `confidence`, incrémenter `support_count`, mettre à jour `last_seen_at`.
   - **Contradictoire** (même subject+predicate+category, object différent sur catégorie stable) → ne pas supprimer l'ancien : passer l'ancien en `superseded`, créer une `FactRelation` `supersedes`, garder la source.
   - **Nouveau compatible** → créer le fact.
6. Exporter les vues Markdown (cf. 6.7).

**6.5 — Confiance dynamique.** Init : `0.55` inférence faible, `0.75` énoncé explicite de l'utilisateur, `0.9` correction/confirmation directe. Monte à chaque ré-observation compatible. La **réconciliation est 90 % de la difficulté, pas le schéma** : commence par une policy minimaliste, élargis ensuite.

**6.6 — Decay par catégorie.** `identity` → `none` ; `values` → `very_slow` ; `decision` → `none` (mais superseable) ; `preference` → `medium` ; `project`/`habit` → `medium` ; `goal` → `fast` (surtout après `valid_to` dépassé). Le decay réduit la saillance au retrieval, il ne supprime pas le fact.

**6.7 — Miroir Markdown UNIDIRECTIONNEL (`memory/mirror.py`).** SQLite → Markdown, **lecture seule côté humain**. Génère ex. `user/preferences.md`, `user/projects.md`, `user/goals.md`, `jarvis/persona.md`, `jarvis/uncertain-beliefs.md`. Lisible (compatible Obsidian) pour inspecter/visualiser. **Aucune édition directe des .md ne modifie la mémoire.** Pour corriger un souvenir, l'utilisateur passe par une commande Jarvis qui crée un `Event` `human_correction` (catégorie `memory_correction`) → la DB se met à jour. Le bidirectionnel propre est hors scope MVP.

**6.8 — Périmètre d'extraction étroit.** Au départ, ne consolide en facts QUE : préférences, projets actifs, objectifs, contraintes, décisions, habitudes stables, persona, corrections explicites. Tout le reste reste dans `events` sans devenir fact. Sinon : grenier algorithmique.

**6.9 — Retrieval (`memory/retrieval.py`).** À la réponse, ne récupère pas seulement des chunks vectoriels : récupère les facts **actifs, récents, confiants, pertinents**, plus les contradictions connues. Score = combinaison `importance × récence × pertinence × confidence` (importance notée par LLM à l'ingestion, façon Generative Agents).

### Erreurs à éviter
- **Prédicats/catégories libres** : tueur silencieux. "vise"/"veut"/"target" non normalisés ne matchent jamais → doublons → grenier. Vocabulaire fermé OBLIGATOIRE.
- **Oublier la confirmation** : ne gérer que la contradiction crée des doublons à chaque répétition. Le cas le plus fréquent est la ré-observation, pas la contradiction.
- **Markdown bidirectionnel** : merge conflict permanent. Reste unidirectionnel en MVP.
- **Tout extraire** : périmètre étroit d'abord.
- **Supprimer un event ou un fact contredit** : on archive/supersede, on ne détruit jamais la provenance.
- **Introduire Neo4j/Qdrant "pour bien faire"** : sur-ingénierie. SQLite + sqlite-vec suffit longtemps.

### Tests à écrire
- Un fact ré-observé n'est pas dupliqué : `support_count` et `confidence` augmentent, une `FactObservation` est créée.
- "objectif = sub-3h" puis "objectif = 3h10" → l'ancien passe `superseded`, relation `supersedes` créée, ancien conservé.
- "Barth court" + "Barth fait du vélo" → coexistence, pas de supersession.
- Un prédicat hors vocabulaire → `needs_review`, jamais en base principale.
- Édition manuelle d'un .md miroir → AUCUN effet sur la DB ; régénération écrase l'édition.
- Une `human_correction` via commande → fact mis à jour + event tracé.
- Decay : un `goal` non réactivé après `valid_to` voit sa saillance chuter au retrieval ; une `identity` non.

### Definition of Done
Ingestion réelle sur deux semaines d'usage simulé/réel sans explosion de doublons, réconciliation correcte sur les 3 cas, miroir Markdown lisible et inerte, retrieval qui remonte les bons facts actifs.

---

## 7. PHASE 4 — SKILL LAB

### Objectif
Les skills naissent de l'usage, jamais d'un backlog codé à la main. Une skill = mémoire procédurale : même infra de cycle de vie que les facts.

### Fichiers concernés
- Étendre : `skills/` + `SkillSynthesizer` existant (format agentskills.io conservé).
- Créer : `skills/lab.py` (génération + test sandbox + versioning), `skills/registry.py` (cycle de vie).

### Spécification détaillée
**7.1** Sur signal `skill_candidate` (PHASE 2) ou détection de pattern récurrent, le Skill Lab : génère le code de la skill, crée un **test minimal**, l'exécute en **sandbox Docker** (`docker_executor`), compare à une baseline, et **n'installe que si les tests passent**. C'est Voyager + Darwin Gödel Machine, version sécurisée.
**7.2** Cycle de vie d'une skill (registry) : champs analogues aux facts — `confidence`, `support_count`, `last_used_at`, `status` (`candidate`|`active`|`stale`|`archived`). Une skill non utilisée passe `stale` puis `archived` (passe Curator, PHASE 6).
**7.3** **Validation humaine obligatoire avant première installation** en MVP. L'auto-installation autonome ne viendra qu'avec un périmètre whitelisté (PHASE 5).

### Erreurs à éviter
- **Ne PAS pré-coder une liste de skills.** Elles émergent des missions réussies. Une bibliothèque maintenue à la main = le piège "Obsidian read-only" : du mort.
- Ne pas installer une skill sans test vert en sandbox.
- Ne pas laisser une skill modifier le core.

### Tests à écrire
- Une skill candidate qui échoue son test sandbox n'est jamais installée.
- Une skill non utilisée X jours passe `stale` puis `archived`.
- Une skill générée depuis une mission réussie réutilise correctement le pattern sur un nouveau cas.

### Definition of Done
Une mission réussie génère une skill candidate, testée en sandbox, validée par l'humain, installée, réutilisée sur un cas suivant, et soumise au cycle de vie.

---

## 8. PHASE 5 — CAPABILITY ENGINE (AUTO-EXTENSION)

### Objectif
Le niveau au-dessus du Skill Lab : combler un manque de capacité détecté. C'est le "coup du vocal". **Vient en dernier des couches de capacité** car responsable seulement quand sandbox + gate + human-in-the-loop sont en place.

### Fichiers concernés
- Créer : `agent/capability_engine.py`. S'appuie sur Skill Lab (PHASE 4) + gouvernance (§9).

### Spécification détaillée
Boucle contrôlée, jamais "se bricoler au hasard" :
1. Input ou mission non traitable → **détection du capability gap** (ex. MIME type audio inconnu, pas de skill `transcribe_audio`).
2. Chercher une skill existante, puis une lib/outil externe.
3. Générer une skill candidate (délègue au Skill Lab).
4. Test sandbox.
5. **Validation** : auto seulement si le gate composite (§9) renvoie `auto` ET dans un périmètre whitelisté ; sinon demande humaine ("j'ai fabriqué un outil pour transcrire les vocaux, je l'installe ?").
6. Installation → exécution → mémorisation ("quand input audio → utiliser `transcribe_audio`").

### Erreurs à éviter
- **C'est le moment le plus dangereux du projet.** Un agent qui s'écrit ses outils peut exfiltrer des tokens, installer un paquet compromis, se casser. La capacité et le garde-fou sont le MÊME sujet.
- Jamais d'auto-installation hors périmètre whitelisté.
- Jamais `INSTALL_PACKAGE` ou `MODIFY_CORE` en auto.

### Tests à écrire
- Un input inconnu déclenche bien la détection de gap (pas un échec silencieux).
- Une skill auto-générée hors whitelist exige validation humaine.
- Une tentative d'action `INSTALL_PACKAGE` en auto est bloquée par le gate.

### Definition of Done
Un input non géré (ex. vocal) déclenche la boucle, propose une skill, la teste, demande validation, l'installe et répond — avec la gouvernance respectée à chaque étape.

---

## 9. GOUVERNANCE — COUCHE TRANSVERSALE (PRÉREQUIS, PAS UNE PHASE)

**À implémenter dès PHASE 1, enrichie ensuite.** Elle existe AVANT toute action touchant filesystem ou réseau.

### Fichiers concernés
- `agent/governance.py` (gate), `core/audit.py` (log d'audit), `config/permissions.yaml` (whitelists).

### Spécification
- **Gate composite** : `gate(access_level, action_category, estimated_cost_usd, dry_run_available) -> "auto" | "dry_run" | "approval" | "refused"`. Le gate compose **trois axes orthogonaux** dont **le plus restrictif gagne** (OU logique côté refus/demande). La 4e valeur `refused` est un refus déterministe : l'humain n'a PAS la main (catégorie `NEVER` ou budget `hard_stop` — aucune approbation ne peut sauver l'action). À distinguer d'`approval` qui demande à l'humain qui peut accorder.
  1. **Risque technique** (`AccessLevel` de `core/vocab.py`, ordonné 0–5) — "quel dégât technique possible". `> AUTO_MAX_LEVEL` → `approval` ; `INSTALL_PACKAGE`/`MODIFY_CORE` → toujours `approval`.
  2. **Catégorie d'approbation** (`ApprovalConfig` + `ApprovalChecker` existants dans `config/approvals.py` + `core/approval_checker.py`) — "quelle sorte d'action" (sémantique : `email_send`, `file_delete`, etc.). Mode `ASK` → `approval` ; mode `NEVER` → refus ; mode `ALWAYS` → passe.
  3. **Budget** (`BudgetGuard` existant dans `core/budget.py`) — quota USD. Retour `hard_stop` → refus ; `warning` → tracer mais autoriser.
  
  Ces axes mesurent des choses différentes et ne doivent **PAS être fusionnés ni mappés** : un email = `NETWORK` techniquement mais `email_send/ASK` sémantiquement — les deux infos sont nécessaires séparément. Annoter chaque catégorie d'approbation avec un `AccessLevel` natif est un raffinement optionnel pour plus tard, pas une fusion.

- **Niveau intermédiaire avec dry-run dispo** → `dry_run` (montre le diff/la requête, n'exécute pas), uniquement si aucun des trois axes ne déclenche `approval`/refus.
- **Sandbox obligatoire** pour toute exécution de code (`docker_executor`).
- **Dry-run** disponible pour les modifications de fichiers et appels réseau quand c'est possible.
- **Audit log complet** : toute action (les trois axes consultés, décision du gate, résultat) tracée, immuable.
- **Rollback** : toute modification de fichier projet doit être réversible (snapshot/diff avant application).
- **Règle absolue** : auto-modification autorisée uniquement sur skills, prompts, workflows, connecteurs sandboxés. **JAMAIS le core runtime** sans tests + review + rollback.

### Tests à écrire
- Chaque niveau d'accès produit la bonne décision de gate **toutes choses égales par ailleurs** sur les deux autres axes.
- Chaque mode d'`ApprovalConfig` (`ALWAYS`/`ASK`/`NEVER`) produit la bonne décision **toutes choses égales par ailleurs** sur les deux autres axes.
- Un budget `hard_stop` refuse l'action même si risque et catégorie sont permissifs.
- Le filtre le plus restrictif gagne : une action `READ_ONLY` mais en catégorie `NEVER` est refusée ; une action `NETWORK` mais catégorie `ALWAYS` reste en `approval` à cause du risque.
- Une action `MODIFY_CORE` est toujours refusée en auto.
- Toute action laisse une entrée d'audit avec les trois axes consultés.
- Un échec d'action déclenche le rollback de fichiers.

---

## 10. PHASE 6 — PROACTIVE ENGINE & CURATOR

### Objectif
Passer de "pousser des notifs" à "entreprendre des missions". Dernière couche : présuppose missions vérifiables + apprentissage + gouvernance.

### Fichiers concernés
- Étendre : `proactive/` + `collectors/`.
- Créer : `proactive/curator.py`, `proactive/command_center.py`.

### Spécification
**10.1 — Initiatives gouvernées.** Surveiller des signaux → détecter opportunité/risque → proposer ou agir selon le niveau d'autonomie (0–5, §3.3). Chaque initiative porte : déclencheur, objectif, permission requise, coût max (tokens/temps/argent), risque, deadline, état, prochaine action, besoin de validation.
**10.2 — Command Center.** Vue de toutes les initiatives/missions en cours avec objectifs, budgets, permissions, états, heartbeat, coûts. Jarvis ne "fait pas des trucs" : il gère des workstreams.
**10.3 — Curator nocturne (inspiré Hermes).** Job cron qui produit un rapport et des patches : facts ajoutés/modifiés, contradictions détectées, souvenirs archivés (decay), skills utilisées / à promouvoir / à passer `stale`/`archived`, prompts qui ont dérivé, routines proactives inutiles, coûts, erreurs récurrentes. C'est l'AutoDream élargi à la maintenance de tout le système (mémoire + skills + prompts + tools).

### Erreurs à éviter
- Ne pas activer un niveau d'autonomie ≥ 3 sans gouvernance complète en place.
- Ne pas laisser le Curator auto-appliquer des patches risqués : il PROPOSE, l'humain valide pour tout ce qui fait trébucher le gate composite (§9) — risque, catégorie `ASK`/`NEVER`, ou budget `hard_stop`.

### Tests à écrire
- Une initiative niveau 5 (publier/payer/contacter) exige toujours validation.
- Le Curator détecte une skill inutilisée et la propose à l'archivage.
- Un budget dépassé met l'initiative en pause.

### Definition of Done
Jarvis propose une initiative pertinente non sollicitée, la gère via le Command Center avec budget et permissions, et un Curator nocturne produit un rapport de maintenance exploitable.

---

## 11. PERSONNALITÉ — DEUX COUCHES (transversal, à poser tôt)

- **Noyau immuable** (jamais modifié automatiquement) : valeurs, mission, règles de sécurité, style profond. Stocké comme document versionné, modifiable uniquement par l'humain.
- **Persona adaptative** : ton, humour, niveau de détail, types de conseils préférés. Modifiable par Jarvis (facts de catégorie `persona`) **mais avec validation**, et exposée dans le miroir Markdown (`jarvis/persona.md`) pour inspection.
- **Garde-fou anti-complaisance** : une personnalité hardcodée est morte ; totalement mutable, elle dérive vers "te plaire". L'identité tient par le noyau fixe, le reste s'adapte. Tout patch de persona qui toucherait le noyau est refusé.

**Test** : une tentative de patch automatique du noyau de valeurs est refusée et loggée.

---

## 12. STRATÉGIE DE TESTS GLOBALE

- **Tests d'abord sur la vérification et la réconciliation** : ce sont les zones où du code plausible mais faux passe. Écris-les avant ou avec le code.
- **Tests d'intégration entre couches** aux jonctions du contrat (PHASE 0) : Mission→Reflexion→Mémoire, Reflexion→Skill Lab, Capability→Skill Lab→Gouvernance.
- **Test de reprise après crash** pour toute couche à état persistant (missions, mémoire).
- **Tests de non-régression de sécurité** : couvrir chacun des trois axes du gate (§9) — risque technique (chaque `AccessLevel` produit la bonne décision), catégorie d'approbation (chaque `ApprovalMode` produit la bonne décision), budget (`hard_stop` refuse). Plus un test croisé : le filtre le plus restrictif gagne. Vérifier qu'aucun chemin ne permet `MODIFY_CORE`/`INSTALL_PACKAGE` en auto ni une action en catégorie `NEVER`.
- `ruff check` + `ruff format` propres. `uv run pytest` vert avant chaque fin de phase.

---

## 13. ANTI-PATTERNS GLOBAUX (à éviter partout)

1. **La cathédrale** : tout implémenter d'un bloc. → MVP par couche, élargi par l'usage.
2. **"Existe/compile = réussi"** : la pire erreur du Mission Engine. → vérification sémantique de l'atteinte.
3. **Vocabulaire libre** en mémoire. → prédicats/catégories fermés.
4. **Doublons par non-confirmation** : gérer la contradiction mais pas la ré-observation. → `fact_observations` + renforcement.
5. **Skills pré-codées à la main.** → skills émergentes de l'usage.
6. **Gouvernance en dernier.** → transversale, dès PHASE 1.
7. **Auto-modification du core.** → jamais sans tests + review + rollback.
8. **Markdown bidirectionnel** en MVP. → miroir unidirectionnel + commande de correction.
9. **Sur-ingénierie du stockage** (Neo4j/Qdrant trop tôt). → SQLite + sqlite-vec.
10. **Structures de données concurrentes** inventées par un agent. → contrat PHASE 0 unique.

---

## 14. ORDRE D'EXÉCUTION & PARALLÉLISATION

**Règle d'or : parallélise À L'INTÉRIEUR d'une couche, séquentialise ENTRE les couches.**

1. **PHASE 0 — solo, en premier.** Contrat de schémas figé et commité. Aucun parallélisme avant ça.
2. Puis dans l'ordre : **PHASE 1 (Mission Engine + Gouvernance) → PHASE 2 (Reflexion) → PHASE 3 (Memory Kernel) → PHASE 4 (Skill Lab) → PHASE 5 (Capability Engine) → PHASE 6 (Proactive/Curator).** Personnalité (§11) posée tôt, en parallèle léger de PHASE 1.
3. **Parallélisme autorisé dans une couche, sur fichiers disjoints partageant le contrat** :
   - PHASE 1 : un agent sur `verifier.py`, un sur `governance.py`, un sur la persistance des missions.
   - PHASE 3 : un agent sur `ingest.py`, un sur `mirror.py`, un sur `retrieval.py`.
4. **Garde-fous anti-dérive sémantique** : contrat PHASE 0 figé ; une spec courte par couche que tous les agents de cette couche lisent ; revue humaine des points de jonction (les interfaces où deux agents se rencontrent), pas de tout le code.

**Le vrai risque du multi-agent n'est pas la collision de fichiers (git gère) mais la dérive sémantique** : deux agents implémentant correctement leur bout avec des hypothèses incompatibles. Le contrat figé et les specs de couche sont la parade.

---

## 15. DEFINITION OF DONE GLOBALE

Le système est "v1" quand :
- une demande vague devient une mission planifiée, exécutée, **vérifiée à l'atteinte** (pas seulement bien formée), gouvernée, persistante ;
- chaque mission produit une leçon ingérée en mémoire ;
- la mémoire est une base SQLite atomique, datée, sourcée, sans doublons, avec contradiction/confirmation/decay, miroir Markdown inerte ;
- les skills émergent des missions, testées en sandbox, avec cycle de vie ;
- un input inconnu peut déclencher une auto-extension sûre et validée ;
- Jarvis propose des initiatives gouvernées et un Curator maintient le système ;
- aucun chemin ne permet l'auto-modification du core ni une action privilégiée sans validation.

**Cap final :** Jarvis se souvient comme un organisme, travaille comme un chef de projet, apprend comme un développeur, agit comme un exécutif, évolue comme un système modulaire — avec une continuité intérieure : il sait ce qu'il a vu, ce qu'il croit, pourquoi, ce qui a changé, ce qu'il doit oublier, et quand il doit demander l'accord de l'utilisateur.
