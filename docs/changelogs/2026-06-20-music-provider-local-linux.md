# Provider musique « local » sous Linux (MPRIS / D-Bus)

**Date :** 2026-06-20
**Branche :** `feat/local-music-linux-mpris`
**Commits :** `feat(music): support du provider local sous Linux (MPRIS via D-Bus)`,
`feat(music): embarque la pochette MPRIS file:// en data: URI`

---

## Contexte

Le provider musique `MUSIC_PROVIDER=local` ne fonctionnait que sous **macOS**
(via le binaire `nowplaying-cli`). Sous Linux, l'UI affichait « non connecté »
quel que soit le réglage : `nowplaying-cli` est absent et aucune alternative
n'était câblée.

## Ce qui change

Ajout d'une **branche Linux** dans
[`src/jarvis/interfaces/api/local_music.py`](../../src/jarvis/interfaces/api/local_music.py)
qui lit le « now playing » via le standard **MPRIS2 sur le bus D-Bus session**,
avec la lib **`jeepney`** (pur Python, aucun binaire système).

- `_backend()` : macOS (`nowplaying-cli`) → sinon Linux (MPRIS) → sinon `None`.
- Lecture de l'état : titre, artiste, album, pochette, position, durée,
  statut lecture/pause — via les propriétés MPRIS `org.mpris.MediaPlayer2.Player`.
- Contrôles : `play` / `pause` / `next` / `previous` (méthodes MPRIS).
- Sélection du lecteur : préfère un lecteur en cours de lecture, sinon le premier.
- **Pochette** : `mpris:artUrl` en `file://` (que le navigateur refuse de charger
  depuis une page `http://`) est lu côté serveur et embarqué en **`data:` URI**
  (sniff PNG/JPEG/GIF/WebP, plafond 5 Mo). Les URL `http(s)`/`data:` passent
  telles quelles. C'est la même image que la zone média du bureau (même propriété).

Aucune route HTTP ajoutée : les 5 endpoints existants
(`GET /api/local-music/player`, `POST .../play|pause|next|previous`) sont conservés.
Le chemin macOS est strictement inchangé.

## Dépendance

`jeepney>=0.8.0` ajouté à `pyproject.toml` + `uv.lock` → **embarqué automatiquement
dans le bundle** au prochain `build_bundle.sh` (pur Python, pas de binaire à
télécharger). Conforme à la logique « tout embarqué » du déploiement offline.

## Compatibilité

- **Toutes les distros desktop** (Ubuntu, Debian, Fedora, Arch, openSUSE, Mint…) :
  MPRIS2 + D-Bus session sont des standards FreeDesktop, indépendants de la distro,
  du bureau (GNOME/KDE/XFCE/Cinnamon) et de X11/Wayland.
- Players pris en charge : navigateurs (Chromium/Firefox/Vivaldi…), Spotify, VLC,
  mpv, etc. — y compris en Flatpak/Snap (MPRIS exposé sur le bus session).
- **Pré-requis hôte** (non embarquables, présents par défaut sur un bureau Linux) :
  une session **D-Bus** (`/run/user/<uid>/bus`) + un player exposant **MPRIS2**.
- Headless / SSH sans session D-Bus → renvoie proprement `connected: false`.
- ⚠️ glibc (le Python du bundle est glibc x86_64) — pas Alpine/musl (limite du
  bundle, pas de `jeepney`).

## Validation

- Tests unitaires `tests/test_local_music.py` (10) : détection backend, parsing
  des propriétés MPRIS, résolution de pochette (http passthrough, `file://` →
  `data:` URI, fichier absent, schéma inconnu) — **passent**.
- Suite rapide `pytest -m "not integration"` : **719 passent**, 0 régression.
- `ruff check` + `ruff format` : clean.
- `lint-imports` : 4 contrats de couches **KEPT**.
- Snapshot des routes : inchangé (aucune route ajoutée).
- **Vérifié en live** : lecture YouTube dans Vivaldi remontée dans l'UI
  (titre + pochette), `provider: local`, backend `linux`, sans `playerctl`.

---

## Annexe — à résoudre : placeholders de clés API faussement « connectés » au déploiement

**Découvert pendant cette session, hors périmètre du patch musique.**

### Symptôme

Sur une installation fraîche (`.env` issu de `.env.example`), la page des
intégrations affiche **« CONNECTÉ »** pour Anthropic, OpenAI, Google et
ElevenLabs alors qu'**aucune vraie clé** n'est renseignée — uniquement des
placeholders d'exemple.

### Cause

La détection « connecté » de
[`src/jarvis/interfaces/api/config/devices.py`](../../src/jarvis/interfaces/api/config/devices.py)
(`get_connectors` → `_env_ok`) considère une clé valide si elle est **non vide**,
ne **commence pas** par `...` et n'est pas `—` :

```python
def _valid(v: str) -> bool:
    v = v.strip()
    return bool(v) and not v.startswith("...") and v != "—"
```

Or les placeholders de `.env.example` ne respectent pas tous cette convention de
sentinelle. Incohérence :

| Clé (`.env.example`) | Placeholder | `_env_ok` | Affichage |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | `sk-ant-...` | ✅ valide | **CONNECTÉ** (faux) |
| `OPENAI_API_KEY` | `sk-proj-...` | ✅ valide | **CONNECTÉ** (faux) |
| `GOOGLE_API_KEY` | `AIza...` | ✅ valide | **CONNECTÉ** (faux) |
| `ELEVENLABS_API_KEY` | `sk_...` | ✅ valide | **CONNECTÉ** (faux) |
| `DEEPGRAM_API_KEY` | `...` | ❌ sentinelle | off (correct) |
| `MISTRAL_API_KEY` | `...` | ❌ sentinelle | off (correct) |

Seuls Deepgram et Mistral utilisent la sentinelle `...` reconnue comme « non
configuré » ; les autres commencent par un préfixe réaliste (`sk-`, `AIza`) qui
passe le test → faux positif.

### Pistes de résolution

1. **Minimal (recommandé)** — aligner `.env.example` : mettre **toutes** les clés
   non renseignées sur une valeur reconnue comme « non configuré » (vide, ou la
   sentinelle `...`). Les badges refléteront alors la réalité sur un déploiement
   neuf. Aucun code à toucher.
2. **Plus robuste** — durcir `_env_ok` pour reconnaître les préfixes de placeholder
   courants (`sk-ant-...`, `sk-proj-...`, `AIza...`, `sk_...`, se terminant par
   `...`) comme non configurés. Heuristique, à maintenir.
3. **De fond** — ne plus déduire l'état « connecté » d'une chaîne sentinelle :
   suivre explicitement les clés réellement saisies (l'assistant `/setup` n'écrit
   que les vraies valeurs ; champ vide = non configuré). Refacto plus large.

> Contournement appliqué en dev cette session : les clés inutilisées du `.env`
> local ont été mises sur la sentinelle `...` (Ollama étant le backend réel), ce
> qui rend les badges corrects localement — mais ne corrige pas `.env.example`.

---

## Annexe — à faire : `compute_type` Whisper non adapté au CPU (déploiement sans GPU)

**Identifié pendant la prépa de la VM de dev (CPU only), hors périmètre du patch.**

### Symptôme

Sur un déploiement **sans GPU** (VM de dev, serveur headless), la transcription
Whisper « directe » est lente : `compute_type="float16"` est orienté GPU et n'est
pas supporté en calcul CPU par CTranslate2 (repli float32, lent).

### Cause

[`src/jarvis/providers/audio/stt.py`](../../src/jarvis/providers/audio/stt.py) force :

```python
WhisperModel(settings.whisper_model, device="auto", compute_type="float16")
```

À noter : le chemin **temps réel** ([`receiver.py`](../../src/jarvis/providers/audio/receiver.py),
RealtimeSTT) utilise **déjà** `compute_type="int8"` → seul `stt.py` est concerné.

### Piste de résolution

Rendre `compute_type` **adaptatif** : `float16` si GPU disponible, sinon `int8`
(rapide sur CPU). Permettrait `small`, voire `medium`, à une latence acceptable en
VM. Alternative : exposer `compute_type` en réglage (`.env`).

> Note d'usage : pour la voix **conversationnelle**, `tiny`/`small` suffisent même
> sur GPU ; `medium` reste pertinent surtout pour la transcription **batch** de
> fichiers, à garder sur un poste équipé d'un GPU (hors Jarvis).
