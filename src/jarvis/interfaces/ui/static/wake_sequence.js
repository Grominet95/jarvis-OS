'use strict';

// ═══════════════════════════════════════════════════════════════════════════
//  wake_sequence.js — Séquence de réveil Jarvis (étape A)
//
//  Pivot architectural (cf. amendement CDC) :
//  - La sphère est LE VRAI orb.js monté en mode { frozen: true, onTick: ... }.
//    Aucune duplication, aucune bascule de matériau.
//  - La convergence (BOOT → CONVERGE → IGNITE → ONLINE) est animée EN CPU :
//    la séquence écrit positions[] dans le BufferAttribute d'orb.js à chaque
//    frame, via le hook onTick injecté avant renderer.render().
//  - Le rayon de balayage et le noyau d'énergie sont des overlays ShaderMaterial
//    ajoutés à orb.getScene() (quad NDC plein écran, additif, depthTest=false).
//
//  API publique :
//      window.createWakeSequence(rootEl, opts) → { destroy(), getState(), getOrb() }
//
//  Choix internes (notés ici, non arbitrables) :
//  - BOOT : positions = spawn figées (alpha 0.14). Pas de drift CPU pour
//    économiser le budget — la sphère apparaît comme un nuage très diffus et
//    immobile, conforme à CDC §5.1 (« dérive lente » remise à plus tard).
//  - FACE : étape 5 du CDC — sauté immédiatement vers CONVERGE en étape A.
//  - Spirale : lerp cylindrique en r/az/y avec courbe quintique C² unique,
//    micro-settle radial 5.5% sur [0.72, 1], turbulence (1−p) qui s'éteint.
//  - Activation : seuil aT par particule = 0.42 · (yMaxBeam − yStart) / range.
//  - IGNITE étape A : sphère figée à targets, opacité 0.72, nucleus fade out
//    sur 2.2 s. Vague océanique = étape B.
//  - ONLINE étape A : positions = targets exactes, opacité 0.72, FX off.
//    Pas de drift dashboard ici — restauré à l'étape C via setFrozen(false).
//  - Rotation Y pendant la séquence : 0.0015 · 60 = 0.09 rad/s en dt réel.
// ═══════════════════════════════════════════════════════════════════════════

(function () {
    const STATES = Object.freeze({
        BOOT: 'boot', FACE: 'face', CONVERGE: 'converge', IGNITE: 'ignite', ONLINE: 'online',
    });

    const DEFAULT_BOOT_LINES = Object.freeze([
        'MEMORY KERNEL .......... OK',
        'MISSION ENGINE ......... OK',
        'PIPELINE VOIX .......... OK',
        'MODULE BIOMÉTRIQUE ..... OK',
        'JARVIS RUNTIME ......... OK',
    ]);

    const BOOT_LINE_INTERVAL_MS = 180;
    const BOOT_LINE_ANIM_MS     = 800;
    const PHASE_DURATION_MS = Object.freeze({
        converge: 2800,   // raccourci pour transition plus snappy vers dashboard
        ignite:   1200,
    });
    const EASE = 'cubic-bezier(0.32, 0.72, 0, 1)';
    const BOOT_OPACITY = 0.40;  // bien au-dessus du CDC 0.10-0.18 : combiné à la dispersion
                                 // réduite (sphereStyle.WAKE_R.SPIRAL_DISP_*), les particules sont
                                 // visibles ET dispersées en arrière de la face frame, pas un centre vide.

    // ── CSS keyframes injection ──────────────────────────────────────────
    function injectCss() {
        if (document.getElementById('wake-sequence-css')) return;
        const css = document.createElement('style');
        css.id = 'wake-sequence-css';
        css.textContent = ''
            + '@keyframes wakeLogIn {'
            + '  from { opacity: 0; filter: blur(4px); transform: translateY(7px); }'
            + '  to   { opacity: 1; filter: blur(0);   transform: translateY(0); }'
            + '}'
            + '@keyframes wakeCursorBlink {'
            + '  from { opacity: 1; } to { opacity: 0; }'
            + '}'
            + '@keyframes wakeFaceEnter {'
            + '  from { opacity: 0; filter: blur(10px); transform: translate(-50%, -50%) scale(0.965); }'
            + '  to   { opacity: 1; filter: blur(0);    transform: translate(-50%, -50%) scale(1); }'
            + '}'
            // (Les bandes laser des coins sont stylées inline depuis JS pour
            // garantir l'application — cf. runFacePhase.)
            ;
        document.head.appendChild(css);
    }

    // ─────────────────────────────────────────────────────────────────────
    //  FACE phase — caméra + MediaPipe FaceLandmarker + backend verify
    //  Laser descend 1.3 s puis remonte 1.3 s. Verdict 1.3 s. Total ≈ 3.9 s.
    //  Dégradation gracieuse : caméra refusée → simulation ; backend down
    //  → verdict positif (CDC §C4, jamais bloquant).
    // ─────────────────────────────────────────────────────────────────────
    const FACE_FRAME_W       = 480;
    const FACE_FRAME_H       = 600;
    const FACE_SCAN_DESCENT  = 1.3;   // s
    const FACE_SCAN_ASCENT   = 1.3;   // s
    const FACE_VERDICT_HOLD  = 1.3;   // s
    const FACE_BACKEND_TIMEOUT = 2500; // ms (au-delà : verdict simulation)
    // Bord arrondi du cadre + bandes laser positionnées sur les segments
    // droits (offset = rayon, sinon elles tombent dans la courbe et sont clippées).
    const FACE_FRAME_RADIUS  = 14;    // px
    const FACE_LASER_LEN     = 110;   // px
    const FACE_LASER_THICK   = 1.5;
    const FACE_WASM_BASE     = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.6/wasm';
    const FACE_MODEL_URL     = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task';
    const FACE_VISION_BUNDLE = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.6/vision_bundle.mjs';

    function runFacePhase(rootEl, opts, onDone) {
        const userName    = opts.userName    || '';
        const wasmBase    = opts.wasmBase    || FACE_WASM_BASE;
        const modelUrl    = opts.modelUrl    || FACE_MODEL_URL;
        const visionBundle = opts.visionBundle || FACE_VISION_BUNDLE;

        let disposed = false;

        // ── DOM cadre central ──────────────────────────────────────────
        // border-radius arrondit ; overflow:hidden clippe le canvas vidéo
        // au contour arrondi (sinon ses coins dépassent du rectangle visible).
        const wrap = document.createElement('div');
        wrap.style.cssText = ''
            + 'position:absolute; top:50%; left:50%; z-index:12;'
            + 'width:' + FACE_FRAME_W + 'px; height:' + FACE_FRAME_H + 'px;'
            + 'border-radius:' + FACE_FRAME_RADIUS + 'px;'
            + 'overflow:hidden;'
            + 'opacity:0; transform:translate(-50%, -50%) scale(0.965); filter:blur(10px);'
            + 'animation:wakeFaceEnter 0.9s ' + EASE + ' forwards;'
            + 'pointer-events:none;';
        rootEl.appendChild(wrap);

        // 4 L courbés (un par coin) au lieu de 8 bandes droites.
        // Chaque L est un div carré de taille FACE_LASER_LEN avec 2 bords colorés,
        // un border-radius sur le coin correspondant (suit la courbe du cadre),
        // et un mask-image dégradé qui fade en diagonale vers le centre du cadre.
        // Continuité parfaite : la courbe du L correspond à la courbe du cadre.
        const R = FACE_FRAME_RADIUS;
        const LASER_COLOR_SCAN = '#4A9EFF';
        const CORNER_CONFIGS = [
            // pos, borders, radius corner, mask diagonal (start at corner, fade toward center)
            { pos: 'top:0;left:0;',     bd: 'border-top-width:1.5px;border-left-width:1.5px;',     br: 'border-top-left-radius:'    +R+'px;', maskDir: '135deg' },
            { pos: 'top:0;right:0;',    bd: 'border-top-width:1.5px;border-right-width:1.5px;',    br: 'border-top-right-radius:'   +R+'px;', maskDir: '225deg' },
            { pos: 'bottom:0;left:0;',  bd: 'border-bottom-width:1.5px;border-left-width:1.5px;',  br: 'border-bottom-left-radius:' +R+'px;', maskDir: '45deg'  },
            { pos: 'bottom:0;right:0;', bd: 'border-bottom-width:1.5px;border-right-width:1.5px;', br: 'border-bottom-right-radius:'+R+'px;', maskDir: '315deg' },
        ];
        function buildCorner(cfg, col) {
            const mask = 'linear-gradient(' + cfg.maskDir + ', black 0%, black 28%, transparent 88%)';
            return 'position:absolute;pointer-events:none;z-index:5;box-sizing:border-box;'
                + cfg.pos
                + 'width:' + FACE_LASER_LEN + 'px; height:' + FACE_LASER_LEN + 'px;'
                + 'border-style:solid;border-color:' + col + ';border-width:0;'
                + cfg.bd
                + cfg.br
                + 'box-shadow: 0 0 14px ' + col + ';'
                + '-webkit-mask-image:' + mask + ';mask-image:' + mask + ';'
                + 'transition: border-color 0.35s ease, box-shadow 0.35s ease;';
        }
        const lasers = [];
        CORNER_CONFIGS.forEach(function (cfg) {
            const c = document.createElement('div');
            c.style.cssText = buildCorner(cfg, LASER_COLOR_SCAN);
            wrap.appendChild(c);
            lasers.push({ el: c, cfg: cfg });
        });

        // Video caché — drawImage sur canvas pour alignement parfait
        const video = document.createElement('video');
        video.autoplay = true; video.muted = true; video.playsInline = true;
        video.style.cssText = 'position:absolute; opacity:0; pointer-events:none;';
        wrap.appendChild(video);

        const canvas = document.createElement('canvas');
        canvas.width  = FACE_FRAME_W;
        canvas.height = FACE_FRAME_H;
        canvas.style.cssText = 'position:absolute; top:0; left:0; width:100%; height:100%;';
        wrap.appendChild(canvas);
        const ctx2d = canvas.getContext('2d');

        const status = document.createElement('div');
        status.textContent = 'INITIALISATION CAPTEUR…';
        status.style.cssText = ''
            + 'position:absolute; top:calc(100% + 20px); left:50%; transform:translateX(-50%);'
            + 'white-space:nowrap; font-size:11px; letter-spacing:0.22em; text-transform:uppercase;'
            + 'color:rgba(160,195,255,0.65); pointer-events:none;'
            + 'transition:color 0.35s ease;';
        wrap.appendChild(status);

        // ── État pipeline ──────────────────────────────────────────────
        let stream       = null;
        let landmarker   = null;
        let lastLm       = null;
        let detectedFrames = 0;
        let simulationMode = false;
        let scanStart    = null;   // performance.now() au démarrage du scan
        let verdictShown = false;
        let backendResult = null;
        let backendDone  = false;
        let cleanedUp    = false;
        let raf          = 0;

        // Backend POST : déclenché DEPUIS la boucle tick quand on a une frame
        // exploitable (caméra prête + idéalement quelques landmarks détectés).
        // On envoie la frame en base64 JPEG vers /verify-face-frame qui la
        // passe au FaceRecognizer (compare avec référence.jpg). Évite le
        // conflit caméra navigateur ↔ backend cv2.VideoCapture.
        let backendStart   = 0;
        let backendStarted = false;
        let cameraReadyAt  = 0;

        function tryCaptureAndPost() {
            if (backendStarted || simulationMode) return;
            if (!video || video.readyState < 2 || !video.videoWidth) return;
            // Conditions de capture : assez de frames détectées OU >1 s depuis caméra prête
            const longEnough = cameraReadyAt > 0 && (performance.now() - cameraReadyAt > 1000);
            if (detectedFrames < 5 && !longEnough) return;

            backendStarted = true;
            backendStart   = performance.now();

            // Capture frame brute (pas de miroir — backend a besoin de l'orientation naturelle)
            const c2 = document.createElement('canvas');
            c2.width  = video.videoWidth;
            c2.height = video.videoHeight;
            c2.getContext('2d').drawImage(video, 0, 0);
            const dataUrl = c2.toDataURL('image/jpeg', 0.85);
            const b64     = dataUrl.split(',')[1] || '';

            fetch('/api/vision/verify-face-frame', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ image_b64: b64 }),
            })
                .then(function (r) { return r.json(); })
                .then(function (r) {
                    backendResult = r;
                    backendDone   = true;
                    console.log('[wake][face] backend verdict', r);
                })
                .catch(function (e) {
                    console.warn('[wake][face] backend error', e);
                    backendDone = true;
                });
        }

        // ── Init caméra + MediaPipe (asynchrone, parallèle) ─────────────
        (async function initSensors() {
            try {
                stream = await navigator.mediaDevices.getUserMedia({
                    video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
                    audio: false,
                });
                if (disposed) { stream.getTracks().forEach(function (t) { t.stop(); }); return; }
                video.srcObject = stream;
                try { await video.play(); } catch (e) {}

                try {
                    const vision  = await import(visionBundle);
                    const fileset = await vision.FilesetResolver.forVisionTasks(wasmBase);
                    landmarker = await vision.FaceLandmarker.createFromOptions(fileset, {
                        baseOptions: { modelAssetPath: modelUrl, delegate: 'GPU' },
                        runningMode: 'VIDEO',
                        numFaces: 1,
                    });
                } catch (e) {
                    console.warn('[wake][face] MediaPipe non disponible — vidéo brute sans landmarks', e);
                    landmarker = null;
                }
                if (disposed) return;
                cameraReadyAt = performance.now();
                scanStart = performance.now();
                status.textContent = simulationMode ? 'SIMULATION · ANALYSE BIOMÉTRIQUE' : 'ANALYSE BIOMÉTRIQUE…';
                startScanSfx();
            } catch (e) {
                console.warn('[wake][face] caméra refusée — mode SIMULATION', e);
                simulationMode = true;
                backendDone = true;          // pas de backend en simulation
                scanStart = performance.now();
                status.textContent = 'SIMULATION · ANALYSE BIOMÉTRIQUE';
                startScanSfx();
            }
        })();

        // SFX scan : un coup à la descente, un coup à la remontée.
        function startScanSfx() {
            SFX.play('scan');
            setTimeout(function () {
                if (!disposed) SFX.play('scan');
            }, FACE_SCAN_DESCENT * 1000);
        }

        // ── Landmarks SIMULATION (silhouette stylisée, ~75 points) ──────
        // Layout simple : ovale visage + yeux + sourcils + nez + bouche.
        function buildSimLandmarks() {
            const cx = 0.5, cy = 0.50, rx = 0.30, ry = 0.40;
            const pts = [];
            // ovale 30 points
            for (let i = 0; i < 30; i++) {
                const a = (i / 30) * Math.PI * 2;
                pts.push({ x: cx + Math.cos(a) * rx, y: cy + Math.sin(a) * ry });
            }
            // yeux (8 pts chacun)
            for (let side = 0; side < 2; side++) {
                const ex = cx + (side === 0 ? -0.12 : 0.12);
                const ey = cy - 0.08;
                for (let i = 0; i < 8; i++) {
                    const a = (i / 8) * Math.PI * 2;
                    pts.push({ x: ex + Math.cos(a) * 0.04, y: ey + Math.sin(a) * 0.022 });
                }
            }
            // sourcils
            for (let side = 0; side < 2; side++) {
                const bx = cx + (side === 0 ? -0.15 : 0.05);
                const by = cy - 0.18;
                for (let i = 0; i < 5; i++) pts.push({ x: bx + i * 0.025, y: by - Math.sin(i / 4 * Math.PI) * 0.012 });
            }
            // nez
            for (let i = 0; i < 6; i++) pts.push({ x: cx, y: cy - 0.05 + i * 0.025 });
            // lèvres
            for (let i = 0; i < 9; i++) {
                const a = (i / 9) * Math.PI;
                pts.push({ x: cx - 0.08 + (i / 9) * 0.16, y: cy + 0.18 + Math.sin(a) * 0.015 });
                pts.push({ x: cx - 0.08 + (i / 9) * 0.16, y: cy + 0.20 - Math.sin(a) * 0.012 });
            }
            return pts;
        }
        const simLandmarks = buildSimLandmarks();

        // ── Animation tick (boucle dédiée) ──────────────────────────────
        function tick() {
            if (disposed) return;
            raf = requestAnimationFrame(tick);

            const W = canvas.width, H = canvas.height;
            ctx2d.clearRect(0, 0, W, H);

            // Géométrie cover — partagée entre le dessin vidéo ET les landmarks.
            // Le mode cover en X crée un débordement horizontal qui doit être
            // pris en compte pour aligner les points sur le visage affiché.
            let vCoverDx = 0, vCoverDy = 0, vCoverDw = W, vCoverDh = H;
            const vReady = !simulationMode && video.readyState >= 2 && video.videoWidth > 0;
            if (vReady) {
                const vw = video.videoWidth, vh = video.videoHeight;
                const ratio = Math.max(W / vw, H / vh);
                vCoverDw = vw * ratio;
                vCoverDh = vh * ratio;
                vCoverDx = (W - vCoverDw) / 2;
                vCoverDy = (H - vCoverDh) / 2;
            }

            // Couche vidéo (cover, miroir)
            if (vReady) {
                ctx2d.save();
                ctx2d.translate(W, 0); ctx2d.scale(-1, 1); // miroir horizontal
                ctx2d.drawImage(video, W - vCoverDx - vCoverDw, vCoverDy, vCoverDw, vCoverDh);
                ctx2d.restore();
                // Voile bleu — opacité réduite vs CDC (0.62 → 0.35) pour garder le visage lisible
                ctx2d.fillStyle = 'rgba(6, 14, 32, 0.35)';
                ctx2d.fillRect(0, 0, W, H);
            } else {
                ctx2d.fillStyle = '#04070e';
                ctx2d.fillRect(0, 0, W, H);
            }

            // Détection MediaPipe (live uniquement)
            if (!simulationMode && landmarker && video.readyState >= 2) {
                try {
                    const r = landmarker.detectForVideo(video, performance.now());
                    if (r && r.faceLandmarks && r.faceLandmarks[0]) {
                        lastLm = r.faceLandmarks[0];
                        detectedFrames++;
                    }
                } catch (e) {}
            }

            // Capture+POST vers backend dès qu'on a une frame exploitable
            tryCaptureAndPost();
            // Wiggle simulation
            const now = performance.now();
            const lm = simulationMode
                ? simLandmarks.map(function (p, i) {
                    return {
                        x: p.x + Math.sin(now / 900 + i) * 0.0015,
                        y: p.y + Math.cos(now / 1100 + i) * 0.0015,
                    };
                })
                : lastLm;

            // Scan animation
            if (scanStart !== null) {
                const elapsed = (now - scanStart) / 1000;
                let scanY = -1;
                let sweeping = false;

                if (elapsed < FACE_SCAN_DESCENT) {
                    const t = elapsed / FACE_SCAN_DESCENT;
                    scanY    = smoothstep(t) * H;
                    sweeping = true;
                } else if (elapsed < FACE_SCAN_DESCENT + FACE_SCAN_ASCENT) {
                    const t = (elapsed - FACE_SCAN_DESCENT) / FACE_SCAN_ASCENT;
                    scanY    = (1 - smoothstep(t)) * H;
                    sweeping = true;
                } else {
                    scanY    = -1;
                    sweeping = false;
                    if (!verdictShown) maybeShowVerdict();
                }

                // Landmarks — projetés via le SAME mapping cover que la vidéo,
                // puis mirrorés en X (la vidéo est affichée en miroir).
                //   px_normal = vCoverDx + lm.x * vCoverDw
                //   px_mirror = W - px_normal  (le débordement cover est ainsi correctement annulé)
                //   py        = vCoverDy + lm.y * vCoverDh
                // En simulation, lm est déjà dans le repère canvas (pas de cover).
                if (lm && lm.length) {
                    const phaseDescent = elapsed < FACE_SCAN_DESCENT;
                    const useCover = vReady && !simulationMode;
                    for (let i = 0; i < lm.length; i++) {
                        const p = lm[i];
                        let px, py;
                        if (useCover) {
                            const pxNormal = vCoverDx + p.x * vCoverDw;
                            px = W - pxNormal;
                            py = vCoverDy + p.y * vCoverDh;
                        } else {
                            px = p.x * W;
                            py = p.y * H;
                        }
                        if (phaseDescent && py > scanY) continue;
                        const near = sweeping ? Math.exp(-Math.pow((py - scanY) / 26, 2)) : 0;
                        const r = (110 + near * 130) | 0;
                        const g = (190 + near * 60) | 0;
                        ctx2d.fillStyle = 'rgba(' + r + ',' + g + ',255,' + (0.5 + near * 0.5).toFixed(3) + ')';
                        ctx2d.beginPath();
                        ctx2d.arc(px, py, 1.3 + near * 1.7, 0, Math.PI * 2);
                        ctx2d.fill();
                    }
                    // Maillage en simulation (chaînes proches d'ovale)
                    if (simulationMode && sweeping) {
                        ctx2d.lineWidth = 1;
                        ctx2d.strokeStyle = 'rgba(90,170,255,0.22)';
                        ctx2d.beginPath();
                        for (let i = 0; i < 30; i++) {
                            const a = lm[i], b = lm[(i + 1) % 30];
                            if (phaseDescent && (a.y * H > scanY || b.y * H > scanY)) continue;
                            ctx2d.moveTo(a.x * W, a.y * H);
                            ctx2d.lineTo(b.x * W, b.y * H);
                        }
                        ctx2d.stroke();
                    }
                }

                // Rayon (trait + halo) — uniquement pendant sweep
                if (sweeping) {
                    const grad = ctx2d.createLinearGradient(0, scanY - 36, 0, scanY + 6);
                    grad.addColorStop(0,    'rgba(110,230,255,0)');
                    grad.addColorStop(0.85, 'rgba(110,230,255,0.16)');
                    grad.addColorStop(1,    'rgba(110,230,255,0)');
                    ctx2d.fillStyle = grad;
                    ctx2d.fillRect(0, scanY - 36, W, 42);
                    ctx2d.fillStyle = 'rgba(170,240,255,0.95)';
                    ctx2d.fillRect(0, scanY - 1, W, 2);
                }
            }
        }

        function maybeShowVerdict() {
            // Cas 1 : backend démarré, pas encore répondu, timeout pas atteint → attendre.
            // Cas 2 : pas de backend (simulation, ou jamais démarré faute de caméra utile) → verdict immédiat.
            if (backendStarted && !backendDone && (performance.now() - backendStart) < FACE_BACKEND_TIMEOUT) {
                return;
            }
            verdictShown = true;

            // Verdict positif si :
            //   - mode simulation (toujours), ou
            //   - backend a confirmé recognized=true, ou
            //   - mode live mais pas assez de frames détectées → dérogation (CDC §C4 : jamais bloquant)
            let recognized = false;
            if (simulationMode) {
                recognized = true;
            } else if (backendResult && backendResult.recognized) {
                recognized = true;
            }

            // Bascule la couleur des 4 L courbés (transition CSS prend le relais)
            const verdictCol = recognized ? '#6EFFD2' : '#FF6E6E';
            lasers.forEach(function (l) {
                l.el.style.borderColor = verdictCol;
                l.el.style.boxShadow   = '0 0 14px ' + verdictCol;
            });

            if (recognized) {
                status.textContent = userName
                    ? 'IDENTITÉ CONFIRMÉE · BONJOUR ' + userName.toUpperCase()
                    : 'IDENTITÉ CONFIRMÉE';
                status.style.color = 'rgba(110,255,210,0.95)';
                SFX.play('correct');
                // TTS — Jarvis dit "Identité vérifiée, bonjour {userName}"
                // Fire-and-forget : pas d'await, on n'aligne pas la fin de la séquence
                // sur le TTS (sinon variable selon le provider).
                speakIdentityConfirmed(userName);
            } else {
                // CDC §C4 : on ne bloque jamais. Message dérogation, on enchaîne.
                status.textContent = 'VISAGE NON RECONNU · DÉROGATION MANUELLE';
                status.style.color = 'rgba(255,110,110,0.95)';
                SFX.play('wrong');
            }

            setTimeout(function () { finish(recognized); }, FACE_VERDICT_HOLD * 1000);
        }

        async function speakIdentityConfirmed(name) {
            try {
                const r = await fetch('/api/voice/speak', {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body:    JSON.stringify({ text: name ? 'Identité vérifiée, bonjour ' + name : 'Identité vérifiée' }),
                });
                const data = await r.json();
                // Gain 1.5x : la voix wake est volontairement plus présente.
                if (data && data.audio_b64) await SFX.playB64(data.audio_b64, 1.5);
            } catch (e) { console.warn('[wake][face] TTS error', e); }
        }

        function finish(recognized) {
            if (cleanedUp) return;
            cleanedUp = true;
            // Fondu enchaîné : déclenche onDone IMMÉDIATEMENT pour que la
            // phase suivante (CONVERGE) démarre pendant que le cadre face
            // s'efface. Pas de noir entre les deux.
            if (onDone) {
                try { onDone(recognized); } catch (e) { console.error('[wake][face] onDone error', e); }
            }
            // Fade out cadre sur 0.5s (matché avec le ramp d'opacité orbe)
            wrap.style.transition = 'opacity 0.5s ' + EASE;
            wrap.style.opacity = '0';
            setTimeout(cleanup, 550);
        }

        function cleanup() {
            disposed = true;
            if (raf) cancelAnimationFrame(raf);
            if (stream) {
                stream.getTracks().forEach(function (t) { t.stop(); });
                stream = null;
            }
            if (landmarker && typeof landmarker.close === 'function') {
                try { landmarker.close(); } catch (e) {}
            }
            if (wrap.parentNode) wrap.parentNode.removeChild(wrap);
        }

        tick();

        // API interne pour skip externe (clic / touche)
        return {
            skip: function () { if (!cleanedUp) { cleanup(); if (onDone) onDone(); } },
            isActive: function () { return !cleanedUp; },
        };
    }

    // ── Overlay shaders (beam + nucleus) ─────────────────────────────────
    function buildBeamOverlay(THREE, sigmaNdc) {
        const geo = new THREE.PlaneGeometry(2, 2);
        const mat = new THREE.ShaderMaterial({
            uniforms: {
                uBeamNdcY:  { value: 2.0 },
                uIntensity: { value: 0.0 },
                uSigma:     { value: sigmaNdc },
            },
            vertexShader: ''
                + 'varying vec2 vNdc;\n'
                + 'void main() {\n'
                + '  vNdc = position.xy;\n'
                + '  gl_Position = vec4(position.xy, 0.0, 1.0);\n'
                + '}\n',
            fragmentShader: ''
                + 'uniform float uBeamNdcY;\n'
                + 'uniform float uIntensity;\n'
                + 'uniform float uSigma;\n'
                + 'varying vec2 vNdc;\n'
                + 'void main() {\n'
                + '  float dy = vNdc.y - uBeamNdcY;\n'
                + '  float halo = exp(-(dy*dy) / max(uSigma * uSigma, 0.0001));\n'
                + '  float line = smoothstep(0.006, 0.0, abs(dy));\n'
                + '  float k = (halo * 0.55 + line * 0.95) * uIntensity;\n'
                + '  vec3 col = vec3(0.667, 0.941, 1.0);\n'  // rgba(170,240,255)
                + '  gl_FragColor = vec4(col * k, k);\n'
                + '  #include <colorspace_fragment>\n'
                + '}\n',
            transparent: true,
            depthTest: false,
            depthWrite: false,
            blending: THREE.AdditiveBlending,
        });
        const mesh = new THREE.Mesh(geo, mat);
        mesh.frustumCulled = false;
        mesh.renderOrder   = 10;
        return mesh;
    }

    function buildNucleusOverlay(THREE, S, aspect) {
        const geo = new THREE.PlaneGeometry(2, 2);
        const baseCol = S.COLOR.BASE_VEC3;
        const mat = new THREE.ShaderMaterial({
            uniforms: {
                uTime:      { value: 0.0 },
                uIntensity: { value: 0.0 },
                uAspect:    { value: aspect },
            },
            vertexShader: ''
                + 'varying vec2 vNdc;\n'
                + 'void main() {\n'
                + '  vNdc = position.xy;\n'
                + '  gl_Position = vec4(position.xy, 0.0, 1.0);\n'
                + '}\n',
            fragmentShader: ''
                + 'uniform float uTime;\n'
                + 'uniform float uIntensity;\n'
                + 'uniform float uAspect;\n'
                + 'varying vec2 vNdc;\n'
                + 'void main() {\n'
                + '  vec2 p = vec2(vNdc.x * uAspect, vNdc.y);\n'
                + '  float r2 = dot(p, p);\n'
                + '  float blue  = exp(-5.5 * r2);\n'
                + '  float white = exp(-22.0 * r2);\n'
                + '  vec3 col = vec3(' + baseCol[0].toFixed(4) + ', '
                                       + baseCol[1].toFixed(4) + ', '
                                       + baseCol[2].toFixed(4) + ') * blue + vec3(1.0) * white;\n'
                + '  float k = uIntensity;\n'
                + '  gl_FragColor = vec4(col * k, k);\n'
                + '  #include <colorspace_fragment>\n'
                + '}\n',
            transparent: true,
            depthTest: false,
            depthWrite: false,
            blending: THREE.AdditiveBlending,
        });
        const mesh = new THREE.Mesh(geo, mat);
        mesh.frustumCulled = false;
        mesh.renderOrder   = 11;
        return mesh;
    }

    function smoothstep(x) {
        const t = Math.max(0, Math.min(1, x));
        return t * t * (3 - 2 * t);
    }

    // ─────────────────────────────────────────────────────────────────────
    //  SFX — samples préchargés depuis /sfx/* + lecture TTS b64.
    //  Samples : correct.mp3, wrong.mp3, scan.wav, particles.wav.
    //  AudioContext lazy + resume() automatique. Si suspended (autoplay
    //  policy), les .play() échouent en silence, la séquence visuelle continue.
    // ─────────────────────────────────────────────────────────────────────
    const SFX = (function () {
        let ctx = null;
        const samples = {};   // name → AudioBuffer
        const pending = {};   // name → Promise (en cours de chargement)

        function getCtx() {
            if (ctx) {
                if (ctx.state === 'suspended') { try { ctx.resume(); } catch (e) {} }
                return ctx;
            }
            try {
                const C = window.AudioContext || window.webkitAudioContext;
                if (!C) return null;
                ctx = new C();
                if (ctx.state === 'suspended') { try { ctx.resume(); } catch (e) {} }
            } catch (e) { ctx = null; }
            return ctx;
        }

        return {
            // Charge un sample depuis une URL. Idempotent.
            load: function (name, url) {
                if (samples[name]) return Promise.resolve(samples[name]);
                if (pending[name]) return pending[name];
                const c = getCtx();
                if (!c) return Promise.reject(new Error('no AudioContext'));
                pending[name] = fetch(url)
                    .then(function (r) {
                        if (!r.ok) throw new Error('HTTP ' + r.status);
                        return r.arrayBuffer();
                    })
                    .then(function (buf) { return c.decodeAudioData(buf); })
                    .then(function (audioBuf) {
                        samples[name] = audioBuf;
                        delete pending[name];
                        return audioBuf;
                    })
                    .catch(function (e) {
                        delete pending[name];
                        console.warn('[wake][sfx] load failed: ' + name, e);
                        throw e;
                    });
                return pending[name];
            },

            // Joue un sample préchargé. No-op si non chargé. Retourne handle .stop().
            play: function (name, volume) {
                const c = getCtx(); if (!c) return null;
                const buf = samples[name];
                if (!buf) return null;
                try {
                    const src = c.createBufferSource();
                    src.buffer = buf;
                    const g = c.createGain();
                    g.gain.value = (typeof volume === 'number') ? volume : 1.0;
                    src.connect(g); g.connect(c.destination);
                    src.start();
                    return { stop: function () { try { src.stop(); } catch (e) {} } };
                } catch (e) { return null; }
            },

            playB64: async function (b64, gain) {
                const c = getCtx(); if (!c || !b64) return;
                try {
                    const raw = atob(b64);
                    const buf = new Uint8Array(raw.length);
                    for (let i = 0; i < raw.length; i++) buf[i] = raw.charCodeAt(i);
                    const audioBuf = await c.decodeAudioData(buf.buffer);
                    const src = c.createBufferSource();
                    src.buffer = audioBuf;
                    // Gain optionnel : pour la voix wake on booste à ~1.5x
                    // pour qu'elle soit plus présente / puissante.
                    if (typeof gain === 'number' && gain !== 1.0) {
                        const g = c.createGain();
                        g.gain.value = gain;
                        src.connect(g); g.connect(c.destination);
                    } else {
                        src.connect(c.destination);
                    }
                    src.start();
                    return new Promise(function (resolve) { src.onended = resolve; });
                } catch (e) { console.warn('[wake][sfx] decode error', e); }
            },
        };
    })();

    // Préchargement déclenché à l'init du module (pas par séquence —
    // évite de recharger à chaque mount).
    SFX.load('correct',   '/sfx/correct.mp3').catch(function () {});
    SFX.load('wrong',     '/sfx/wrong.mp3').catch(function () {});
    SFX.load('scan',      '/sfx/scan.wav').catch(function () {});
    SFX.load('particles', '/sfx/particles.wav').catch(function () {});

    // ═════════════════════════════════════════════════════════════════════
    function createWakeSequence(rootEl, opts) {
        opts = opts || {};
        const onComplete     = (typeof opts.onComplete === 'function') ? opts.onComplete : function () {};
        const userName       = opts.userName    || '';
        const requireFace    = opts.requireFace !== false;
        const bootLines      = opts.bootLines   || DEFAULT_BOOT_LINES.slice();
        const statusLabel    = opts.statusLabel || 'SYSTÈMES EN LIGNE';
        const skippable      = opts.skippable   !== false;
        const debugBenchmark = !!opts.debugBenchmark;
        // Mode "cold boot dashboard" : on réutilise le canvas et les atmosphères
        // déjà mountés par home.js. La séquence n'ajoute ni canvas, ni spotlight,
        // ni aurora, ni vignette, ni grain. À l'entrée ONLINE elle setFrozen(false)
        // sur l'orbe partagé → drift dashboard reprend sans cross-fade.
        const targetCanvas       = opts.targetCanvas || null;
        const useExternalCanvas  = !!targetCanvas;

        const S     = window.SPHERE_STYLE;
        const THREE = window.THREE;
        if (!S || !THREE || !window.createJarvisOrb) {
            console.error('[wake] dépendances manquantes (SPHERE_STYLE / THREE / createJarvisOrb)');
            return null;
        }

        injectCss();

        // ── DOM root ────────────────────────────────────────────────────
        // Standalone : fond opaque + atmosphères + canvas internes.
        // External  : fond transparent, atmosphères déjà sur le dashboard,
        //             on n'ajoute que les UI (logs boot, hint skip, face frame).
        rootEl.style.cssText = ''
            + 'position: fixed; inset: 0; z-index: 9000; overflow: hidden;'
            + 'background: ' + (useExternalCanvas ? 'transparent' : S.RENDER.WAKE_BG_HEX) + ';'
            + 'color: rgba(160,195,255,0.55);'
            + 'font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;';

        let canvas;
        if (useExternalCanvas) {
            canvas = targetCanvas;
        } else {
            const spotlight = document.createElement('div');
            spotlight.className = 'spotlight';
            spotlight.style.cssText = '--mx: 50%; --my: 50%;';
            rootEl.appendChild(spotlight);

            const aurora = document.createElement('div');
            aurora.className = 'atmo atmo--aurora';
            rootEl.appendChild(aurora);

            canvas = document.createElement('canvas');
            canvas.style.cssText = 'position:absolute; inset:0; width:100%; height:100%; display:block; z-index:1;';
            rootEl.appendChild(canvas);

            const vignette = document.createElement('div');
            vignette.className = 'atmo atmo--vignette';
            vignette.style.zIndex = '2';
            rootEl.appendChild(vignette);

            const grain = document.createElement('div');
            grain.className = 'atmo atmo--grain';
            grain.style.zIndex = '3';
            rootEl.appendChild(grain);
        }

        const bootLogEl = document.createElement('div');
        bootLogEl.style.cssText = ''
            + 'position: absolute; left: 32px; bottom: 32px; z-index: 10;'
            + 'font-size: 11px; line-height: 1.9; letter-spacing: 0.18em;'
            + 'text-transform: uppercase; color: rgba(160,195,255,0.55);'
            + 'pointer-events: none;';
        rootEl.appendChild(bootLogEl);

        // (Plus de hint « cliquer pour passer » : la séquence n'est plus
        //  skippable au pointeur/clavier. Pilotage uniquement via les
        //  méthodes exposées sur le handle, pour la dev page wake.html.)
        const skipHintEl = null;

        // ── Canvas dimensionnement initial ─────────────────────────────
        // En external, le canvas est celui du dashboard, déjà mountné et
        // taillé. On laisse home.js + ResizeObserver d'orb.js piloter.
        const _w0 = rootEl.clientWidth  || window.innerWidth;
        const _h0 = rootEl.clientHeight || window.innerHeight;
        if (!useExternalCanvas) {
            canvas.style.width  = _w0 + 'px';
            canvas.style.height = _h0 + 'px';
        }

        // ── Constantes échelle ─────────────────────────────────────────
        const R    = S.GEOMETRY.R;
        const ZCAM = S.CAMERA.ZCAM;
        const W_R  = S.WAKE_R;
        const TAN_HALF_FOV    = Math.tan(S.CAMERA.FOV * Math.PI / 360);
        const NDC_PER_WORLD_Y = 1 / (ZCAM * TAN_HALF_FOV);

        // ── État machine + bench ───────────────────────────────────────
        let state          = STATES.BOOT;
        let phaseStartedAt = performance.now();
        let lastTickAt     = performance.now();
        const bench = { sum: 0, n: 0, max: 0, lastLog: 0 };

        // ── Montage orbe réel ──────────────────────────────────────────
        const orb = window.createJarvisOrb(canvas, {
            frozen: true,
            onTick: onOrbTick,
        });
        if (!orb) {
            console.error('[wake] échec création orbe');
            return null;
        }

        const N         = orb.getParticleCount();
        const positions = orb.getPositions();
        const orbMat    = orb.getMaterial();

        // Sauvegarde targets = positions shell initiales d'orb.js
        const targets = new Float32Array(N * 3);
        targets.set(positions);

        // ── Pré-calcul convergence ────────────────────────────────────
        const spawn = new Float32Array(N * 3);
        const rs    = new Float32Array(N);
        const rt    = new Float32Array(N);
        const azs   = new Float32Array(N);
        const azt   = new Float32Array(N);
        const aT    = new Float32Array(N);
        const seed  = new Float32Array(N);

        const BEAM_Y_MAX_W = W_R.BEAM_Y_MAX * R;
        const BEAM_Y_MIN_W = W_R.BEAM_Y_MIN * R;
        const BEAM_RANGE   = BEAM_Y_MAX_W - BEAM_Y_MIN_W;

        for (let i = 0; i < N; i++) {
            const i3 = i * 3;
            const xt = targets[i3], yt = targets[i3+1], zt = targets[i3+2];

            seed[i] = Math.random();

            const rt_v  = Math.sqrt(xt * xt + zt * zt);
            const azt_v = Math.atan2(zt, xt);
            rt[i]  = rt_v;
            azt[i] = azt_v;

            const disp_R   = W_R.SPIRAL_DISP_MIN + Math.random() * (W_R.SPIRAL_DISP_MAX - W_R.SPIRAL_DISP_MIN);
            const turns    = W_R.SPIRAL_TURNS_MIN + Math.random() * (W_R.SPIRAL_TURNS_MAX - W_R.SPIRAL_TURNS_MIN);
            const turnSign = Math.random() < 0.5 ? -1 : 1;
            const vertDisp = (Math.random() * 2 - 1) * W_R.SPIRAL_VERT_DISP * R;

            const rs_v  = rt_v + disp_R * R;
            const azs_v = azt_v + turnSign * turns * Math.PI * 2;
            const ys_v  = yt + vertDisp;
            rs[i]  = rs_v;
            azs[i] = azs_v;

            spawn[i3]   = rs_v * Math.cos(azs_v);
            spawn[i3+1] = ys_v;
            spawn[i3+2] = rs_v * Math.sin(azs_v);

            // aT par particule (CDC §5.3)
            let f = (BEAM_Y_MAX_W - ys_v) / BEAM_RANGE;
            if (f < 0) f = 0; else if (f > 1) f = 1;
            aT[i] = W_R.ACTIVATION_T_FRACT * f;
        }

        // Init positions = spawn ; matériau opacité BOOT
        positions.set(spawn);
        orb.commitPositions();
        orbMat.opacity = BOOT_OPACITY;

        // ── FX overlays ────────────────────────────────────────────────
        const beamSigmaNdc = W_R.BEAM_SIGMA * R * NDC_PER_WORLD_Y;
        const beamMesh     = buildBeamOverlay(THREE, beamSigmaNdc);
        const nucleusMesh  = buildNucleusOverlay(THREE, S, _w0 / _h0);
        beamMesh.visible    = false;
        nucleusMesh.visible = false;
        orb.getScene().add(beamMesh);
        orb.getScene().add(nucleusMesh);

        // ── Constantes hot loop (pulls hors switch) ────────────────────
        const WIDTH        = W_R.ACTIVATION_WIDTH;
        const SETTLE_START = W_R.MICRO_SETTLE_P_START;
        const SETTLE_RANGE = W_R.MICRO_SETTLE_P_END - W_R.MICRO_SETTLE_P_START;
        const SETTLE_AMPL  = W_R.MICRO_SETTLE_AMPL;
        const TURB_AMPL_W  = W_R.TURBULENCE_AMPL * R;
        const TURB_F0      = W_R.TURBULENCE_FREQ_HZ_MIN;
        const TURB_DF      = W_R.TURBULENCE_FREQ_HZ_MAX - W_R.TURBULENCE_FREQ_HZ_MIN;

        // ── Machine à états ───────────────────────────────────────────
        let onCompleteFired = false;
        let phaseTimers     = [];
        let bootTimer       = null;
        let destroyed       = false;
        let faceHandle      = null;  // handle FACE phase (cleanup au skip / destroy)

        function clearPhaseTimers() {
            phaseTimers.forEach(function (id) { clearTimeout(id); });
            phaseTimers.length = 0;
            if (bootTimer) { clearTimeout(bootTimer); bootTimer = null; }
        }

        function setState(next) {
            if (destroyed || state === next) return;
            clearPhaseTimers();
            state = next;
            phaseStartedAt = performance.now();
            onStateEnter(next);
        }

        function onStateEnter(s) {
            switch (s) {
                case STATES.BOOT:
                    renderBootLines();
                    break;
                case STATES.FACE:
                    // Lance la phase faciale réelle (caméra + MediaPipe + backend).
                    // onDone(recognized) fire AU DÉBUT du fondu sortant du cadre,
                    // pour que CONVERGE démarre pendant que le cadre s'efface.
                    // Si recognized === false → BLOCAGE : on n'avance pas. Le
                    // caller peut s'abonner via opts.onFailure pour retourner
                    // en sleep mode (ex. cold boot).
                    faceHandle = runFacePhase(rootEl, {
                        userName:     userName,
                        wasmBase:     opts.wasmBase,
                        modelUrl:     opts.modelUrl,
                        visionBundle: opts.visionBundle,
                    }, function (recognized) {
                        faceHandle = null;
                        // Face phase never blocks access (CDC C4). An unrecognized face
                        // -- or a backend error (no cv2/model, timeout, face not enrolled)
                        // -- already showed the manual override verdict. We proceed to the
                        // dashboard regardless: otherwise the user stays trapped on the
                        // standby screen with the mic unreachable.
                        if (state === STATES.FACE) setState(STATES.CONVERGE);
                    });
                    break;
                case STATES.CONVERGE:
                    positions.set(spawn);
                    bootLogEl.style.transition = 'opacity 0.8s ' + EASE;
                    bootLogEl.style.opacity = '0';
                    beamMesh.visible    = true;
                    nucleusMesh.visible = true;
                    SFX.play('particles');
                    phaseTimers.push(setTimeout(function () { setState(STATES.IGNITE); }, PHASE_DURATION_MS.converge));
                    break;
                case STATES.IGNITE:
                    positions.set(targets);
                    orb.commitPositions();
                    orbMat.opacity = S.MATERIAL.OPACITY_IDLE;
                    beamMesh.visible = false;
                    phaseTimers.push(setTimeout(function () { setState(STATES.ONLINE); }, PHASE_DURATION_MS.ignite));
                    break;
                case STATES.ONLINE:
                    nucleusMesh.visible = false;
                    // Bascule du drift dashboard. L'orbe partagé enchaîne sans
                    // cross-fade : positions à targets (déjà fait à IGNITE),
                    // setFrozen(false) → drift, breath Z, oscillation caméra,
                    // drag réactivés ; rotation Y reprise au point courant.
                    if (orb && typeof orb.setFrozen === 'function') {
                        try { orb.setFrozen(false); } catch (e) {}
                    }
                    if (!onCompleteFired) {
                        onCompleteFired = true;
                        try { onComplete(); } catch (e) { console.error('[wake] onComplete error', e); }
                    }
                    break;
            }
        }

        function renderBootLines() {
            bootLogEl.innerHTML = '';
            bootLines.forEach(function (line, i) {
                const div = document.createElement('div');
                div.textContent = line;
                div.style.cssText = ''
                    + 'opacity: 0;'
                    + 'animation: wakeLogIn ' + (BOOT_LINE_ANIM_MS / 1000) + 's ' + EASE + ' '
                    + (i * BOOT_LINE_INTERVAL_MS / 1000).toFixed(3) + 's forwards;';
                bootLogEl.appendChild(div);
            });
            const cursor = document.createElement('span');
            cursor.textContent = '▌';
            const cursorDelay = (bootLines.length * BOOT_LINE_INTERVAL_MS / 1000).toFixed(3);
            const blinkDelay  = (bootLines.length * BOOT_LINE_INTERVAL_MS / 1000 + BOOT_LINE_ANIM_MS / 1000).toFixed(3);
            cursor.style.cssText = ''
                + 'opacity: 0;'
                + 'animation: wakeLogIn ' + (BOOT_LINE_ANIM_MS / 1000) + 's ' + EASE + ' ' + cursorDelay + 's forwards,'
                + '           wakeCursorBlink 1s steps(2) ' + blinkDelay + 's infinite;';
            bootLogEl.appendChild(cursor);

            const totalMs = (bootLines.length - 1) * BOOT_LINE_INTERVAL_MS + BOOT_LINE_ANIM_MS + BOOT_LINE_INTERVAL_MS;
            bootTimer = setTimeout(function () {
                if (state === STATES.BOOT) {
                    setState(requireFace ? STATES.FACE : STATES.CONVERGE);
                }
            }, totalMs);
        }

        // ── Skip programmatique (dev page) — plus de listener pointeur/clavier ─
        // Le clic ne fait plus avancer les phases. Les méthodes ci-dessous
        // sont exposées sur le handle pour la dev page wake.html.
        function skipTo(target) {
            if (destroyed) return;
            if (target === 'converge' && (state === STATES.BOOT || state === STATES.FACE)) {
                if (faceHandle) { faceHandle.skip(); faceHandle = null; }
                setState(STATES.CONVERGE);
            } else if (target === 'ignite' && state === STATES.CONVERGE) {
                setState(STATES.IGNITE);
            } else if (target === 'online' && state === STATES.IGNITE) {
                setState(STATES.ONLINE);
            }
        }

        // ── Resize ─────────────────────────────────────────────────────
        function onResize() {
            if (destroyed) return;
            const nw = rootEl.clientWidth  || window.innerWidth;
            const nh = rootEl.clientHeight || window.innerHeight;
            canvas.style.width  = nw + 'px';
            canvas.style.height = nh + 'px';
            orb.resize(nw, nh);
            nucleusMesh.material.uniforms.uAspect.value = nw / nh;
        }
        window.addEventListener('resize', onResize);

        // ── prefers-reduced-motion ─────────────────────────────────────
        const prefersReduced = window.matchMedia
            && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        if (prefersReduced) {
            setState(STATES.ONLINE);
        } else {
            onStateEnter(STATES.BOOT);
        }

        // ═════════════════════════════════════════════════════════════════
        //  onTick — appelé par orb.animate() AVANT renderer.render().
        //  Mutation autorisée sur positions, material.opacity, points.rotation,
        //  camera.position, FX uniforms.
        // ═════════════════════════════════════════════════════════════════
        function onOrbTick(ctx) {
            const pos    = ctx.positions;
            const mat    = ctx.material;
            const points = ctx.points;
            const ti     = ctx.t;
            const now    = performance.now();
            const dt     = Math.min(0.050, (now - lastTickAt) / 1000);
            lastTickAt = now;

            // Rotation Y séquence en dt réel (arbitrage §7)
            points.rotation.y += S.ANIM_IDLE.ROT_Y_PER_FRAME * 60 * dt;

            const phaseElapsed = (now - phaseStartedAt) / 1000;
            const benchStart   = debugBenchmark ? performance.now() : 0;
            let didWrite = false;

            switch (state) {
                case STATES.BOOT:
                case STATES.FACE:
                    // Positions = spawn figées (déjà en buffer). Aucun write.
                    break;

                case STATES.CONVERGE: {
                    const dur = PHASE_DURATION_MS.converge / 1000;
                    const uConverge = Math.min(1, phaseElapsed / dur);
                    writeConvergePositions(pos, uConverge, ti);
                    didWrite = true;

                    // Opacité : crossfade rapide ease-out sur 0.5s (matche le
                    // fondu sortant du cadre face). À mi-fondu (0.25s), face à 0.5
                    // et particules à ~0.6 → particules nettement visibles dès le début.
                    const xfade = Math.min(1, phaseElapsed / 0.5);
                    const easedFade = 1 - Math.pow(1 - xfade, 3);
                    mat.opacity = BOOT_OPACITY + easedFade * (S.MATERIAL.OPACITY_IDLE - BOOT_OPACITY);

                    if (uConverge <= W_R.BEAM_T_END) {
                        const bt  = uConverge / W_R.BEAM_T_END;
                        const be  = smoothstep(bt);
                        const beamY    = BEAM_Y_MAX_W + (BEAM_Y_MIN_W - BEAM_Y_MAX_W) * be;
                        const beamNdcY = beamY * NDC_PER_WORLD_Y;
                        const fade     = 1 - Math.abs(be * 2 - 1);
                        beamMesh.material.uniforms.uBeamNdcY.value  = beamNdcY;
                        beamMesh.material.uniforms.uIntensity.value = fade;
                    } else {
                        beamMesh.material.uniforms.uIntensity.value = 0;
                    }

                    const pulse = W_R.CORE_PULSE_BASE + W_R.CORE_PULSE_AMPL * Math.sin(W_R.CORE_PULSE_FREQ * ti);
                    nucleusMesh.material.uniforms.uIntensity.value = Math.pow(uConverge, W_R.CORE_INTENSITY_EXP) * W_R.CORE_INTENSITY_GAIN * pulse;
                    nucleusMesh.material.uniforms.uTime.value = ti;
                    break;
                }

                case STATES.IGNITE: {
                    const ignDur  = PHASE_DURATION_MS.ignite / 1000;
                    const ignFrac = Math.min(1, phaseElapsed / ignDur);
                    nucleusMesh.material.uniforms.uIntensity.value = (1 - ignFrac) * W_R.CORE_INTENSITY_GAIN;
                    nucleusMesh.material.uniforms.uTime.value = ti;
                    break;
                }

                case STATES.ONLINE:
                    // En v1 étape A : sphère figée à targets, opacité 0.72.
                    // Le retour au drift dashboard est différé à l'étape C.
                    break;
            }

            if (didWrite) ctx.geometry.attributes.position.needsUpdate = true;

            if (debugBenchmark) {
                const d = performance.now() - benchStart;
                bench.sum += d; bench.n += 1;
                if (d > bench.max) bench.max = d;
                if (now - bench.lastLog > 1000) {
                    console.log('[wake][bench] state=' + state
                        + ' loop avg=' + (bench.sum / Math.max(1, bench.n)).toFixed(3)
                        + 'ms max=' + bench.max.toFixed(3) + 'ms (n=' + bench.n + ')');
                    bench.sum = 0; bench.n = 0; bench.max = 0; bench.lastLog = now;
                }
            }
        }

        function writeConvergePositions(pos, uConverge, ti) {
            for (let i = 0; i < N; i++) {
                const i3 = i * 3;

                const p_raw = (uConverge - aT[i]) / WIDTH;
                if (p_raw <= 0) {
                    pos[i3]   = spawn[i3];
                    pos[i3+1] = spawn[i3+1];
                    pos[i3+2] = spawn[i3+2];
                    continue;
                }
                if (p_raw >= 1) {
                    pos[i3]   = targets[i3];
                    pos[i3+1] = targets[i3+1];
                    pos[i3+2] = targets[i3+2];
                    continue;
                }

                // Smootherstep ordre 5 (courbe quintique C²)
                const p  = p_raw * p_raw * p_raw * (p_raw * (p_raw * 6 - 15) + 10);
                const op = 1 - p;

                let r     = rs[i] * op + rt[i] * p;
                const az  = azs[i] * op + azt[i] * p;
                const y_v = spawn[i3+1] * op + targets[i3+1] * p;

                if (p >= SETTLE_START) {
                    const pS = (p - SETTLE_START) / SETTLE_RANGE;
                    r *= 1 - SETTLE_AMPL * Math.sin(Math.PI * pS);
                }

                const s   = seed[i];
                const f   = TURB_F0 + s * TURB_DF;
                const ph  = s * 6.28318;
                const wt  = 2 * Math.PI * f * ti;
                const amp = TURB_AMPL_W * op;
                const tx  = amp * Math.sin(wt + ph);
                const ty  = amp * Math.sin(wt * 0.7 + ph * 2);
                const tz  = amp * Math.cos(wt + ph);

                pos[i3]   = r * Math.cos(az) + tx;
                pos[i3+1] = y_v + ty;
                pos[i3+2] = r * Math.sin(az) + tz;
            }
        }

        // ═════════════════════════════════════════════════════════════════
        return {
            getState: function () { return state; },
            getOrb:   function () { return orb; },
            skipTo: skipTo,
            destroy:  function () {
                if (destroyed) return;
                destroyed = true;
                clearPhaseTimers();
                if (faceHandle)   { try { faceHandle.skip(); } catch (e) {} faceHandle = null; }
                window.removeEventListener('resize',      onResize);
                // Retire les overlays FX de la scène (l'orbe vit potentiellement
                // au-delà). Dispose les ressources Three des overlays.
                try {
                    if (beamMesh.parent)    beamMesh.parent.remove(beamMesh);
                    if (nucleusMesh.parent) nucleusMesh.parent.remove(nucleusMesh);
                } catch (e) {}
                if (beamMesh.material)    beamMesh.material.dispose();
                if (beamMesh.geometry)    beamMesh.geometry.dispose();
                if (nucleusMesh.material) nucleusMesh.material.dispose();
                if (nucleusMesh.geometry) nucleusMesh.geometry.dispose();
                // En mode external, l'orbe est partagé avec le dashboard : on NE
                // le détruit pas (le dashboard reprend la main via setFrozen).
                if (!useExternalCanvas) {
                    try { orb.destroy(); } catch (e) {}
                }
                while (rootEl.firstChild) rootEl.removeChild(rootEl.firstChild);
            },
        };
    }

    window.createWakeSequence = createWakeSequence;

    // ═════════════════════════════════════════════════════════════════════
    //  Sleep screen — affichage en veille avant trigger clap.
    //
    //  Le backend (clap_detector + proactive_queue) broadcast un message
    //  WebSocket {type: "wake_up", trigger: "clap"}. home.js le relaie via
    //  un CustomEvent 'jarvis-wake' sur window. Le sleep screen écoute ça.
    //
    //  Pour dev / test sans micro : window.triggerWake() fire le même event.
    // ═════════════════════════════════════════════════════════════════════
    function injectSleepCss() {
        if (document.getElementById('wake-sleep-css')) return;
        const css = document.createElement('style');
        css.id = 'wake-sleep-css';
        css.textContent = ''
            + '.wake-sleep-content { text-align: center; }'
            + '.wake-sleep-title {'
            + '  font-family: Geist, Inter, system-ui, sans-serif;'
            + '  font-size: 34px; font-weight: 500;'
            + '  letter-spacing: 0.34em; text-transform: uppercase;'
            + '  color: rgba(220,232,255,0.55);'
            + '  animation: wakeSleepBreath 4.2s ease-in-out infinite;'
            + '}'
            + '.wake-sleep-status {'
            + '  margin-top: 18px;'
            + '  font-family: ui-monospace, "SF Mono", Menlo, monospace;'
            + '  font-size: 11px; letter-spacing: 0.42em; text-transform: uppercase;'
            + '  color: rgba(170,205,255,0.35);'
            + '}'
            + '.wake-sleep-hint {'
            + '  margin-top: 80px;'
            + '  font-family: ui-monospace, "SF Mono", Menlo, monospace;'
            + '  font-size: 10px; letter-spacing: 0.32em; text-transform: uppercase;'
            + '  color: rgba(160,195,255,0.22);'
            + '}'
            + '@keyframes wakeSleepBreath {'
            + '  0%, 100% { opacity: 0.45; }'
            + '  50%      { opacity: 1.0; }'
            + '}';
        document.head.appendChild(css);
    }

    function createSleepScreen(rootEl, opts) {
        opts = opts || {};
        const onWake = (typeof opts.onWake === 'function') ? opts.onWake : function () {};

        injectSleepCss();

        rootEl.style.cssText = ''
            + 'position: fixed; inset: 0; z-index: 9500;'
            + 'background: #06080D;'
            + 'display: flex; align-items: center; justify-content: center;'
            + 'transition: opacity 0.9s cubic-bezier(0.32,0.72,0,1);'
            + 'opacity: 1;';

        rootEl.innerHTML = ''
            + '<div class="wake-sleep-content">'
            + '  <div class="wake-sleep-title">JARVIS</div>'
            + '  <div class="wake-sleep-status">· STANDBY ·</div>'
            + '  <div class="wake-sleep-hint">DOUBLE CLAP OU CLIC POUR RÉVEILLER</div>'
            + '</div>';

        let triggered = false;
        function handleWake() {
            if (triggered) return;
            triggered = true;
            onWake();
        }
        window.addEventListener('jarvis-wake', handleWake);
        // Échappatoire manuel : un clic ou une touche réveillent aussi. Sans ça,
        // sur une install sans micro/clap (VPS, headless), l'écran de veille est
        // un cul-de-sac (le seul déclencheur serait l'event clap, indisponible).
        rootEl.addEventListener('click', handleWake);
        window.addEventListener('keydown', handleWake);

        return {
            fadeOut: function (durationMs, then) {
                const d = typeof durationMs === 'number' ? durationMs : 900;
                rootEl.style.transition = 'opacity ' + (d / 1000) + 's cubic-bezier(0.32,0.72,0,1)';
                rootEl.style.opacity = '0';
                setTimeout(then || function () {}, d + 50);
            },
            destroy: function () {
                window.removeEventListener('jarvis-wake', handleWake);
                rootEl.removeEventListener('click', handleWake);
                window.removeEventListener('keydown', handleWake);
                if (rootEl.parentNode) rootEl.parentNode.removeChild(rootEl);
            },
        };
    }

    // Helper console : window.triggerWake() — utile pour tester sans micro.
    if (!window.triggerWake) {
        window.triggerWake = function () {
            window.dispatchEvent(new CustomEvent('jarvis-wake', { detail: { trigger: 'manual' } }));
        };
    }

    window.createSleepScreen = createSleepScreen;
})();
