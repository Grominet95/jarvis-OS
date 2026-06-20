# Cahier des charges — Séquence de réveil « Wake Sequence » Jarvis

**Version** 1.0 · **Date** 12 juin 2026 · **Destinataire** Claude Code
**Fichiers de référence joints** : `WakeSequence.tsx` (implémentation de référence validée), `demo.html` (démo autonome du rendu attendu)

---

## 1. Objet

Implémenter dans le frontend Jarvis (Next.js + Three.js) une séquence de réveil cinématique jouée au lancement de l'interface, avant l'affichage du dashboard. La séquence enchaîne cinq phases : boot système, scan facial, convergence d'énergie, ignition avec vague, état en ligne. Elle se termine **exactement sur l'état visuel actuel de l'interface** (sphère de particules idle + HUD horloge), de sorte que la transition vers le dashboard soit invisible.

L'implémentation de référence (`WakeSequence.tsx`) est validée visuellement et fonctionnellement par le product owner. Elle fait foi pour les comportements, les shaders et les timings. **Elle doit cependant être adaptée, pas copiée aveuglément** : voir contrainte C1.

## 2. Périmètre

**Inclus** : composant React de la séquence, intégration au point d'entrée de l'app, branchement des logs de boot sur l'API de santé FastAPI, callback de fin pour le pipeline voix, mode simulation sans caméra, accessibilité, performance.

**Exclus** (phases ultérieures, ne pas implémenter) : reconnaissance d'identité réelle par embeddings (section 9.3 décrit le hook), son/musique, wake word vocal, persistance de préférences.

---

## 3. Contraintes impératives

### C1 — Préservation du style de la sphère existante (CRITIQUE)

L'application possède déjà une sphère de particules Three.js avec un style propre (densité, taille des points, couleurs, opacités, vitesse de rotation, respiration, réaction à la souris). **Ce style est la signature visuelle du produit et ne doit pas changer.**

Protocole obligatoire, dans cet ordre :

1. **Avant toute écriture de code**, localiser le composant de la sphère existante dans le repo et en extraire les paramètres effectifs : nombre de particules, rayon, distribution (fibonacci ou autre), taille des points (base + variance), couleur(s) exactes (valeurs RGB/hex), opacités, type de blending, vitesse de rotation idle, amplitude/fréquence de la respiration, coefficients de parallaxe souris, position et FOV de la caméra.
2. Consigner ces valeurs dans un objet de configuration unique `SPHERE_STYLE` (fichier `config/sphereStyle.ts` ou équivalent) qui devient la **source de vérité partagée** entre la sphère du dashboard et la séquence de réveil.
3. Dans la séquence, remplacer les valeurs correspondantes de l'implémentation de référence (`PARTICLE_COUNT = 16000`, `SPHERE_RADIUS = 1.55`, couleurs `vec3(0.345, 0.604, 1.0)` / `vec3(0.70, 0.94, 1.0)`, tailles `1.2 + 1.5·rand`, rotation `0.035 rad/s`, respiration `0.011`, parallaxe `0.12/0.08`, caméra `z = 5.2`, FOV 50) par les valeurs extraites.
4. **Critère d'acceptation C1** : une capture d'écran de la dernière frame de la séquence (état ONLINE, souris immobile) doit être visuellement indiscernable de l'état idle actuel du dashboard. Si la sphère existante utilise une géométrie ou un matériau incompatible avec l'animation de convergence (ex. positions non exposées en attributs), adapter la *séquence* à la sphère, jamais l'inverse. Tout écart doit être signalé au product owner avant implémentation.

### C2 — Aucune régression du dashboard

La séquence est un composant additif. Le dashboard, ses routes et ses composants existants ne sont pas modifiés, à l'exception du point de montage (section 7.1) et de l'éventuelle extraction de `SPHERE_STYLE` (refactor sans changement de comportement).

### C3 — Confidentialité

Le flux caméra est traité exclusivement en local (MediaPipe WASM dans le navigateur). Aucune image, frame ou landmark ne transite par le réseau, n'est loggé ni stocké. Le flux est arrêté (`MediaStreamTrack.stop()`) dès la fin de la phase FACE.

### C4 — La séquence n'est jamais bloquante

Tout échec (caméra refusée, modèle indisponible, WebGL dégradé) dégrade gracieusement et la séquence aboutit toujours à l'état ONLINE. Détail en section 10.

---

## 4. Machine à états et timeline

États : `boot → face → converge → ignite → online`. Transitions strictement séquentielles ; `face` est sautée si `requireFace = false`.

| Phase | Durée nominale | Déclencheur de sortie |
|---|---|---|
| `boot` | ~1.1 s (180 ms × 5 lignes + 1 tick) | dernière ligne affichée |
| `face` | variable : init capteur + scan 2.6 s + verdict 1.3 s (succès) ou 1.2–1.4 s (échec/retry) | verdict rendu |
| `converge` | 4.2 s | progression = 1 |
| `ignite` | 2.2 s | vague terminée |
| `online` | permanent | — |

Skip : tout clic ou touche pendant `boot`/`face` saute à `converge` ; pendant `converge`, avance la progression à 1 (déclenche l'ignition). Le skip ne saute jamais l'ignition : c'est le climax, il dure 2.2 s incompressibles.

`prefers-reduced-motion: reduce` : saut direct à `online` (sphère assemblée, HUD affiché, aucune animation de séquence).

`onComplete()` est appelé une seule fois, à l'entrée en `online`.

---

## 5. Spécification par phase

### 5.1 BOOT

Écran fond `#04070e`. Logs en bas à gauche, monospace 11 px, lettrage 0.18 em, majuscules, couleur `rgba(160,195,255,0.55)`, interligne 1.9. Une ligne apparaît toutes les 180 ms avec l'animation `wakeLogIn` (fondu + translateY 7 px + blur 4 px → net, 0.8 s, courbe `EASE` — voir 6.4). Curseur `▌` clignotant (1 s steps) pendant la frappe.

**Contenu des lignes — intégration FastAPI** : les lignes par défaut sont remplacées par l'état réel du système. Au montage, appeler l'endpoint de santé du backend (`GET /system/health` ou l'endpoint équivalent existant dans jarvis-OS — le vérifier dans le repo) et construire les lignes au format `nom du module .......... OK|KO`. Modules attendus a minima : memory kernel, mission engine, pipeline voix, module biométrique. Timeout de 800 ms : au-delà, utiliser les lignes par défaut (la séquence ne doit pas attendre le réseau). Un module KO s'affiche en `rgba(255,140,140,0.7)` mais ne bloque pas la séquence.

En arrière-plan, la sphère est à l'état « nuage ambiant » : particules dispersées (uConverge = 0), alpha faible (~0.10–0.18), dérive lente. L'océan de particules (5.4) est visible en sol discret.

### 5.2 FACE — scan biométrique

Cadre central 360 × 460 px, coins lumineux HUD (26 px, 2 px d'épaisseur), couleur d'état : bleu `rgba(110,200,255,0.55)` pendant le scan, vert `rgba(110,255,210,0.8)` si accordé, rouge `rgba(255,110,110,0.8)` si refusé. Entrée du cadre : opacité + scale 0.965 → 1 + blur 10 px → 0, 0.9 s, courbe `EASE`.

Pipeline caméra :

1. `getUserMedia({ video: { width: 640, height: 480, facingMode: 'user' } })`.
2. Chargement de MediaPipe `FaceLandmarker` (import dynamique de `@mediapipe/tasks-vision`, `runningMode: 'VIDEO'`, `numFaces: 1`, `delegate: 'GPU'`).
3. Rendu sur un unique canvas 2D : vidéo en miroir (cover), voile bleu `rgba(6,14,32,0.62)`, landmarks, maillage, rayon de scan. Pas de `<video>` visible — tout passe par le canvas pour un alignement parfait.

Le rayon de scan descend du haut vers le bas du cadre en 2.6 s (easing smoothstep) : trait net 2 px `rgba(170,240,255,0.95)` + halo dégradé 42 px au-dessus. Les landmarks ne sont dessinés que **au-dessus** du rayon (révélation progressive) ; les points proches du rayon (gaussienne σ ≈ 26 px) sont plus gros et plus chauds. Maillage : segments fins `rgba(90,170,255,0.22)` entre points consécutifs (sous-échantillonné à ~140 segments en mode live).

Verdict en fin de descente : succès si un visage a été détecté sur plus de 12 frames pendant le scan. Succès → cadre vert, message `IDENTITÉ CONFIRMÉE · BONJOUR {userName}`, hold 1.3 s, puis `converge`. Échec → cadre rouge, `VISAGE NON DÉTECTÉ · NOUVELLE TENTATIVE`, un retry automatique ; second échec → `VISAGE NON DÉTECTÉ · DÉROGATION MANUELLE`, hold 1.4 s, puis `converge` (cf. C4).

Modes dégradés : caméra refusée/indisponible → mode SIMULATION : silhouette stylisée de ~75 points (ovale, yeux, sourcils, nez, lèvres — coordonnées dans l'implémentation de référence), maillage par chaînes prédéfinies, micro-animation de vie (±0.0015 en x/y, périodes 900/1100 ms), message suffixé `· SIMULATION`, verdict toujours positif. Caméra OK mais modèle MediaPipe indisponible → vidéo réelle sans points (ne jamais dessiner de faux landmarks sur un vrai visage), présence supposée, verdict positif.

URLs MediaPipe (wasm + modèle `.task`) : props avec défauts CDN, **mais en production auto-héberger les deux dans `/public/mediapipe/`** (cohérence offline/souveraineté du projet). Documenter la copie dans le README du composant. Rappel : `getUserMedia` exige un contexte sécurisé (localhost ou HTTPS).

### 5.3 CONVERGE — rayon d'activation + spirale d'énergie

Deux sous-temps sur 4.2 s :

**Balayage (0 → 42 %)** : un rayon horizontal plein écran descend de y monde +4.7 à −4.7 (easing smoothstep, fondu d'intensité aux extrémités du balayage). Rendu : trait fin + halo dans le quad FX (uBeamNdcY = yMonde / (z_caméra · tan(FOV/2))), bande chaude sur les particules à ±, gaussienne σ ≈ 0.45 unité monde. **Le rayon active les particules** : chaque particule démarre sa trajectoire quand le rayon croise sa hauteur de départ (seuil d'activation aT = 0.42 · (4.7 − yStart)/9.4, progression locale p = smootherstep((uConverge − aT)/0.58)).

**Spirale (jusqu'à 100 %)** : trajectoire en spirale logarithmique — rayon cylindrique, azimut et hauteur convergent avec **la même courbe quintique C²** (`smootherstep` ordre 5, aucune rupture de vitesse ni d'accélération). Paramètres par particule (dérivés du seed) : dispersion de départ 2.5–6.5 unités, 0.8–2.4 tours, dispersion verticale ±3. Turbulence basse fréquence (0.26 d'amplitude, fréquences 0.31–0.44 Hz) qui s'éteint linéairement à l'arrivée. **Micro-settle** à l'arrivée : creux radial de 5.5 % en demi-sinus sur p ∈ [0.72, 1] (inspiration puis relâche, zéro overshoot extérieur). Effet comète : vHot ∝ p·k·4 (chaud en plein vol, refroidit posé).

Noyau d'énergie central (quad FX) : deux gaussiennes radiales additives (`exp(−5.5r²)` bleue + `exp(−22r²)` blanche), intensité = conv^1.6 · 0.9, pulsation 0.94 + 0.06·sin(4t).

### 5.4 IGNITE — vague océanique

Au passage à `ignite` : l'énergie se libère dans **une ondulation circulaire qui traverse un sol de particules**, de la sphère jusqu'à sortir de l'écran. Interdictions formelles issues des itérations précédentes : **pas d'anneau émissif screen-space, pas de coquille sphérique, rien qui croise visuellement la sphère**.

Le sol (« océan ») : 22 000 particules en disque uniforme (r = √rand · 14), objet positionné à y = −2.05 (sous la sphère) et incliné rotation.x = +0.30 (perspective d'horizon). Au repos : alpha 0.035 + 0.030·rand, fondu d'horizon `exp(−0.10·r)`, micro-houle 0.045·sin(0.6t + seed). Le sol est **permanent** (présent de boot à online) : c'est le plancher holodeck de l'interface.

La vague (2.2 s) : front R(t) = 14.5 · t^0.55 (sort de l'écran avant la fin). Forme au passage du front, pour chaque particule à distance d = r − R :

- crête principale : gaussienne `exp(−d²/1.20)`, hauteur ×1.25 ;
- train d'ondes secondaires derrière : `0.38 · sin(2.6·d⁻) · exp(−0.70·d⁻)` lissé sur 0.6 unité (les ronds dans l'eau qui suivent la crête) ;
- décroissance d'énergie : amplitude × 1/(1 + 0.28·R) — la vague s'apaise en s'étendant ;
- amplitude globale = waveAmp · (1−t)^0.45 · 1.1 ;
- lumière : embrasement blanc-chaud à la crête (vHot = crête·decay·amp·1.5), traîne lumineuse `0.35·exp(−0.55·d⁻)`, retour au calme après passage.

Accompagnement : kick radial gaussien sur les particules de la sphère (uWaveR = 3.6·t^0.42, amplitude (1−t)^1.5/(0.6+2t), largeur σ ≈ 0.31) ; flash plein écran bref `exp(−9t)·0.12` ; streak anamorphique horizontal `exp(−30|y|)·exp(−1.1x²)·exp(−6.5t)·0.85` ; micro-dolly caméra z = 5.2 + t(1−t)·4·0.20 (recul puis retour, **aucun shake**) ; le noyau FX s'éteint en (1−t)·0.9.

En `online`, un clic sur la scène rejoue la vague à amplitude 0.45.

### 5.5 ONLINE — HUD

Entrée du HUD (haut droite) façon « Hello » macOS, délai 0.25 s après l'entrée en `online` : opacité 0→1, translateY 18 px→0, scale 0.985→1, blur 16 px→0, le tout en 1.5 s courbe `EASE` ; le **letter-spacing de l'horloge se resserre de 0.09 em à 0.02 em en 1.8 s**. Composition : horloge `clamp(48px, 7vw, 96px)` graisse 700, `--font-display` ; date complète FR majuscules lettrage 0.32 em ; statut `SYSTÈMES EN LIGNE` avec pastille 6 px `#6de6ff` pulsante (2.4 s). Typographies mappées sur les variables CSS existantes de l'app (`--font-display`, `--font-mono`) — aucune fonte nouvelle.

---

## 6. Spécifications techniques de rendu

### 6.1 Pipeline

Un seul `WebGLRenderer` (antialias, alpha false, clearColor `#04070e`, pixelRatio plafonné à 2). Deux passes par frame : scène → `WebGLRenderTarget` (taille = viewport × pixelRatio, redimensionné au resize), puis quad de post plein écran (clip space, `gl_Position = vec4(position.xy, 0, 1)`) qui échantillonne la texture : flash + streak pendant la vague, **vignette permanente** `× (1 − 0.15 r²)`.

### 6.2 Systèmes de particules

Trois draw calls : sphère (ShaderMaterial, AdditiveBlending, depthWrite false), océan (idem), quad FX noyau+rayon (AdditiveBlending, depthTest false, renderOrder 10). Tous les mouvements sont calculés **dans les vertex shaders** à partir d'attributs statiques (seed, position cible, rayon/angle) et d'uniforms scalaires — zéro réécriture de buffer par frame, zéro allocation dans la boucle rAF.

### 6.3 Boucle d'animation

Une seule boucle rAF pilote tout (uniforms, machine à états temporelle, dolly). dt borné à 50 ms (onglet en arrière-plan). Parallaxe souris avec inertie : `mouseSm += (mouse − mouseSm) · 0.045` ; rotation idle `0.035·t + 0.12·mouseSm.x` / `0.08·mouseSm.y` (à remplacer par les valeurs `SPHERE_STYLE`, cf. C1).

### 6.4 Langage d'animation (DOM)

Courbe unique `EASE = cubic-bezier(0.32, 0.72, 0, 1)` pour toutes les transitions CSS. Toute entrée d'élément combine opacité + légère translation + blur→net. Aucune animation linéaire, aucun élément qui apparaît à pleine opacité instantanément.

### 6.5 Cycle de vie

Cleanup exhaustif au démontage : cancelAnimationFrame, removeEventListener (pointermove, pointerdown, keydown, resize), dispose de toutes les géométries/matériaux/renderTarget/renderer, arrêt des tracks caméra, `landmarker.close()`. Compatible StrictMode (double montage dev sans fuite ni double canvas).

---

## 7. Intégration

### 7.1 Point de montage

```tsx
const WakeSequence = dynamic(() => import('@/components/wake/WakeSequence'), { ssr: false });
// dans la page racine :
{!booted && <WakeSequence onComplete={() => setBooted(true)} userName={user.firstName} bootLines={healthLines} />}
```

Transition vers le dashboard : au `onComplete`, monter le dashboard **sous** la séquence (opacité 0) puis cross-fader sur ~1 s (courbe `EASE`) avant de démonter la séquence. Grâce à C1, le raccord sphère/HUD est invisible.

### 7.2 API du composant

| Prop | Type | Défaut | Rôle |
|---|---|---|---|
| `onComplete` | `() => void` | — | entrée en `online` (déclencher le pipeline voix LiveKit ici) |
| `userName` | `string` | `'BARTH'` | nom affiché à la validation |
| `requireFace` | `boolean` | `true` | `false` = saute la phase FACE |
| `bootLines` | `string[]` | logs par défaut | lignes de boot (brancher sur /system/health) |
| `statusLabel` | `string` | `'SYSTÈMES EN LIGNE'` | statut HUD |
| `skippable` | `boolean` | `true` | clic/touche pour passer |
| `wasmBase` / `modelUrl` | `string` | CDN | URLs MediaPipe auto-hébergées |

### 7.3 Hook reconnaissance d'identité (ne pas implémenter, préparer)

Le verdict est isolé dans un unique prédicat (`detectedFrames > 12`). Le structurer en fonction `evaluateIdentity(): Promise<boolean>` injectable, afin qu'une phase ultérieure la remplace par une comparaison d'embeddings côté FastAPI (insightface, distance cosinus contre une référence enrôlée).

---

## 8. Performance

Budgets : 60 fps sur MacBook Apple Silicon, 30 fps minimum sur Raspberry Pi 5 en kiosk. Pour le Pi : exposer deux constantes `PARTICLE_COUNT` et `OCEAN_COUNT` et documenter le préréglage Pi (8 000 / 10 000, pixelRatio 1). Trois draw calls particules maximum, une render target, aucune allocation ni création d'objet THREE dans la boucle. Le canvas 2D du scan facial tourne dans sa propre rAF, détection MediaPipe une frame sur une (GPU delegate) — si le Pi peine, passer à une frame sur deux.

## 9. Accessibilité

`prefers-reduced-motion` → état final direct (section 4). La séquence est entièrement skippable au clic et au clavier (toute touche). Le hint `cliquer pour passer` est visible pendant toute la séquence. Aucune information critique n'est portée uniquement par l'animation.

## 10. Cas limites

| Cas | Comportement attendu |
|---|---|
| Caméra refusée / absente | mode SIMULATION étiqueté, verdict positif |
| Modèle MediaPipe inaccessible (offline, CDN down) | vidéo réelle sans landmarks, verdict positif |
| `/system/health` lent (> 800 ms) ou KO | lignes de boot par défaut |
| WebGL indisponible | fallback : saut direct à `online` avec HUD seul (pas d'écran noir) |
| Onglet en arrière-plan pendant la séquence | dt borné, pas de saut d'état incohérent au retour |
| Double montage StrictMode | aucun double canvas, aucune fuite |
| Resize pendant la séquence | caméra, renderer, render target et aspect mis à jour |

## 11. Plan d'implémentation (étapes avec validation)

Travailler en étapes courtes, chacune compilable et validée avant la suivante (discipline stop-and-validate) :

1. **Extraction du style** : localiser la sphère existante, produire `SPHERE_STYLE`, refactorer la sphère du dashboard pour le consommer (zéro changement visuel — valider par comparaison avant/après). *Point de validation avec le product owner : présenter les valeurs extraites.*
2. **Squelette du composant** : machine à états, boot logs (statiques), montage Three avec la sphère paramétrée par `SPHERE_STYLE` en état assemblé. Valider le critère C1 (frame finale ≡ dashboard).
3. **Convergence** : rayon d'activation + spirale + noyau. Valider fluidité et raccord.
4. **Océan + vague** : sol permanent + ondulation d'ignition + flash/streak/dolly. Valider le rendu contre `demo.html`.
5. **Scan facial** : caméra, MediaPipe, simulation, verdicts, retries.
6. **Intégrations** : health endpoint, cross-fade dashboard, `onComplete`, props finales, préréglage Pi.
7. **Recette** : checklist section 12, test StrictMode, test reduced-motion, test caméra refusée, test offline.

À chaque étape : `tsc --noEmit` propre, lint propre, et capture/enregistrement présenté pour validation visuelle avant de continuer.

## 12. Checklist de recette

La frame finale est indiscernable du dashboard idle (C1). Aucun élément ne coupe visuellement la sphère à aucun moment. La vague part du pied de la sphère et sort de l'écran. Le rayon de convergence active visiblement les particules ligne à ligne. Le scan facial fonctionne en live (Mac, caméra accordée), en simulation (caméra refusée) et en dégradé (modèle absent). Skip opérationnel à chaque phase, ignition jamais sautée. `prefers-reduced-motion` respecté. 60 fps Mac / 30 fps Pi (préréglage). Aucune fuite mémoire après 5 montages/démontages. Aucune requête réseau contenant des données caméra. Cross-fade final invisible.

## 13. Annexes — réglages fins exposés

Regrouper en tête de fichier, commentés : durées des phases ; hauteur de crête (1.25), longueur du train d'ondes (0.70), visibilité du sol au repos (0.035), portée de la vague (14.5), inclinaison du sol (0.30) ; tours et dispersion de la spirale (0.8–2.4 tours, 2.5–6.5) ; amplitude du micro-settle (0.055) ; intensités flash (0.12) et streak (0.85) ; amplitude du dolly (0.20) ; courbe `EASE`.
