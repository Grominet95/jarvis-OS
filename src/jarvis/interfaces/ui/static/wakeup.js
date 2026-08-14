'use strict';

// ═══════════════════════════════════════════════════════════════════════════
//  Jarvis Wake Up — Phases 0 → 5
//
//  WAKEUP_ENABLED=false dans .env pour désactiver pendant le dev.
//
//  Console de test :
//    enterSleepMode()   → veille immédiate
//    triggerWakeUp()    → séquence complète (son → sphère → scan → UI)
// ═══════════════════════════════════════════════════════════════════════════

window._jarvisSleeping   = false;
window._wakeupInProgress = false;

const _INACTIVITY_MS = 10 * 60 * 1000;
let _inactivityTimer  = null;
let _scanCamStream    = null;
let _userFirstname    = '';

// ── Bootstrap ────────────────────────────────────────────────────────────────

(async function _initWakeup() {
    try {
        const r   = await fetch('/api/wakeup/status');
        const cfg = await r.json();
        if (!cfg.enabled) {
            console.log('[WakeUp] Désactivé (WAKEUP_ENABLED=false dans .env)');
            return;
        }
        _userFirstname = cfg.user_firstname || '';
    } catch {
        console.warn('[WakeUp] /api/wakeup/status inaccessible — désactivé');
        return;
    }
    console.log('[WakeUp] Initialisé — veille automatique après 10 min d\'inactivité');
    _registerActivityListeners();
    resetInactivityTimer();
    _preloadFaceMesh(); // charge MediaPipe en background pendant que l'UI est prête
})();

// ── Timer d'inactivité ────────────────────────────────────────────────────────

function resetInactivityTimer() {
    clearTimeout(_inactivityTimer);
    if (window._jarvisSleeping) return;
    _inactivityTimer = setTimeout(enterSleepMode, _INACTIVITY_MS);
}

function _registerActivityListeners() {
    ['mousemove', 'keydown', 'click', 'touchstart'].forEach(ev =>
        document.addEventListener(ev, resetInactivityTimer, { passive: true })
    );
}

window.resetInactivityTimer = resetInactivityTimer;

// ═══════════════════════════════════════════════════════════════════════════
//  PHASE 0 — Mode veille
// ═══════════════════════════════════════════════════════════════════════════

async function enterSleepMode() {
    if (window._jarvisSleeping) return;
    window._jarvisSleeping = true;
    console.log('[WakeUp] → Veille');

    gsap.to('#panel-left',  { opacity: 0, x: -30, duration: 1.2, ease: 'power2.inOut' });
    gsap.to('#panel-right', { opacity: 0, x:  30, duration: 1.2, ease: 'power2.inOut' });
    gsap.to(['#jarvis-toggle', '#globe-toggle', '#intel-toggle',
             '#dashboard-nav-btn', '#settings-nav-btn', '#panels-toggle'],
            { opacity: 0, duration: 1.0, ease: 'power2.inOut' });
    gsap.to('.ticker', { opacity: 0, duration: 0.8 });

    if (window.sphereSetSleepMode) window.sphereSetSleepMode(true);

    await _delay(1200);
    _showSleepIndicator();
}

window.enterSleepMode = enterSleepMode;

function _showSleepIndicator() {
    const el = document.getElementById('sleep-indicator');
    if (!el) return;
    el.style.display = 'flex';
    el.style.opacity = '0';
    gsap.to(el, { opacity: 1, duration: 1.5, ease: 'power2.inOut' });
}

// ═══════════════════════════════════════════════════════════════════════════
//  PHASE 1 — Son d'activation
// ═══════════════════════════════════════════════════════════════════════════

function playActivationSound() {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();

    // Bourdonnement grave montant
    const osc1 = ctx.createOscillator(), g1 = ctx.createGain();
    osc1.type = 'sine';
    osc1.frequency.setValueAtTime(55, ctx.currentTime);
    osc1.frequency.exponentialRampToValueAtTime(220, ctx.currentTime + 0.5);
    g1.gain.setValueAtTime(0, ctx.currentTime);
    g1.gain.linearRampToValueAtTime(0.35, ctx.currentTime + 0.1);
    g1.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.8);
    osc1.connect(g1); g1.connect(ctx.destination);
    osc1.start(ctx.currentTime); osc1.stop(ctx.currentTime + 0.8);

    // Blip électronique haut
    const osc2 = ctx.createOscillator(), g2 = ctx.createGain();
    osc2.type = 'square';
    osc2.frequency.setValueAtTime(880, ctx.currentTime + 0.3);
    osc2.frequency.exponentialRampToValueAtTime(1760, ctx.currentTime + 0.5);
    g2.gain.setValueAtTime(0.06, ctx.currentTime + 0.3);
    g2.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);
    osc2.connect(g2); g2.connect(ctx.destination);
    osc2.start(ctx.currentTime + 0.3); osc2.stop(ctx.currentTime + 0.6);
}

function playValidationSound() {
    const ctx = new AudioContext();
    [523, 659, 784].forEach((freq, i) => {
        const osc = ctx.createOscillator(), g = ctx.createGain();
        osc.frequency.value = freq; osc.type = 'sine';
        g.gain.setValueAtTime(0.15, ctx.currentTime + i * 0.12);
        g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + i * 0.12 + 0.3);
        osc.connect(g); g.connect(ctx.destination);
        osc.start(ctx.currentTime + i * 0.12); osc.stop(ctx.currentTime + i * 0.12 + 0.3);
    });
}

function playDeniedSound() {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator(), g = ctx.createGain();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(220, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(55, ctx.currentTime + 0.4);
    g.gain.setValueAtTime(0.2, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
    osc.connect(g); g.connect(ctx.destination);
    osc.start(); osc.stop(ctx.currentTime + 0.5);
}

// ═══════════════════════════════════════════════════════════════════════════
//  PHASE 2 — Formation de la sphère
// ═══════════════════════════════════════════════════════════════════════════

function animateSphereFormation() {
    return new Promise(resolve => {
        // Flash lumineux au centre
        const flash = document.createElement('div');
        flash.style.cssText = `
            position:fixed; inset:0; z-index:900; pointer-events:none;
            background:radial-gradient(circle at center, rgba(74,158,255,0.18) 0%, transparent 55%);
        `;
        document.body.appendChild(flash);
        gsap.to(flash, { opacity: 0, duration: 0.9, delay: 0.15, onComplete: () => flash.remove() });

        // Sortir du sleep mode sphère
        if (window.sphereSetSleepMode) window.sphereSetSleepMode(false);

        // Animation de formation (scatter → spring back)
        if (window.spherePlayFormationAnim) {
            window.spherePlayFormationAnim(() => resolve());
        } else {
            setTimeout(resolve, 1500);
        }
    });
}

// ═══════════════════════════════════════════════════════════════════════════
//  PHASE 3 — Scan facial
// ═══════════════════════════════════════════════════════════════════════════

async function runFaceScan() {
    const overlay     = document.getElementById('scan-overlay');
    const progressBar = document.getElementById('scan-progress-bar');
    const pctLabel    = document.getElementById('scan-percentage');
    const statusText  = document.getElementById('scan-status-text');
    const videoEl     = document.getElementById('scan-webcam-feed');

    // Feed caméra via browser (visuel uniquement — la reco se fait côté backend)
    try {
        _scanCamStream = await navigator.mediaDevices.getUserMedia(
            { video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } }, audio: false }
        );
        if (videoEl) { videoEl.srcObject = _scanCamStream; }
    } catch {
        console.warn('[WakeUp] Caméra browser indisponible — overlay sans feed');
    }

    // Overlay landmarks faciaux (démarre dès que la vidéo tourne)
    _startLandmarkOverlay(videoEl);

    // Reset progress bar
    progressBar.style.width = '0%';
    pctLabel.textContent = '0%';

    // Afficher l'overlay
    overlay.style.display = 'flex';
    overlay.style.opacity = '0';
    gsap.to(overlay, { opacity: 1, duration: 0.4 });

    // Vérification backend en parallèle dès le début
    const verifyPromise = _requestFaceVerification();

    // Étapes de progression — durée totale ~2s
    const stages = [
        { progress: 15, text: 'DÉTECTION VISAGE...',             duration: 400 },
        { progress: 35, text: 'CARTOGRAPHIE FACIALE...',         duration: 500 },
        { progress: 60, text: 'ANALYSE BIOMÉTRIQUE...',          duration: 400 },
        { progress: 80, text: 'COMPARAISON BASE DE DONNÉES...', duration: 400 },
        { progress: 95, text: 'VÉRIFICATION FINALE...',          duration: 300 },
    ];

    for (const stage of stages) {
        if (statusText) statusText.textContent = stage.text;
        await _animateProgress(progressBar, pctLabel, stage.progress, stage.duration);
    }

    const result = await verifyPromise;
    await _animateProgress(progressBar, pctLabel, 100, 200);

    return result;
}

async function _animateProgress(bar, label, target, duration) {
    return new Promise(resolve => {
        const start     = parseFloat(bar.style.width) || 0;
        const startTime = performance.now();
        function step() {
            const t    = Math.min((performance.now() - startTime) / duration, 1);
            const ease = 1 - Math.pow(1 - t, 2);
            const cur  = start + (target - start) * ease;
            bar.style.width    = cur + '%';
            label.textContent = Math.round(cur) + '%';
            if (t < 1) requestAnimationFrame(step); else resolve();
        }
        requestAnimationFrame(step);
    });
}

async function _requestFaceVerification() {
    try {
        const r = await fetch('/api/vision/verify-face', { method: 'POST' });
        return await r.json();
    } catch {
        return { recognized: false, name: 'error', confidence: 0.0 };
    }
}

function _stopScanCamera() {
    _stopLandmarkOverlay();
    if (_scanCamStream) {
        _scanCamStream.getTracks().forEach(t => t.stop());
        _scanCamStream = null;
        const v = document.getElementById('scan-webcam-feed');
        if (v) v.srcObject = null;
    }
}

// ═══════════════════════════════════════════════════════════════════════════
//  FACE MESH — MediaPipe 468 landmarks, chargé en background
// ═══════════════════════════════════════════════════════════════════════════

let _faceMesh        = null;
let _faceMeshReady   = false;
let _faceMeshLoading = false;
let _faceLandmarks   = null; // derniers landmarks détectés

function _preloadFaceMesh() {
    if (_faceMeshLoading || _faceMeshReady) return;
    _faceMeshLoading = true;
    const s = document.createElement('script');
    s.crossOrigin = 'anonymous';
    s.src = 'https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh@0.4/face_mesh.js';
    s.onload = () => {
        _faceMesh = new window.FaceMesh({
            locateFile: f => `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh@0.4/${f}`
        });
        _faceMesh.setOptions({
            maxNumFaces: 1,
            refineLandmarks: true,   // 478 pts dont iris
            minDetectionConfidence: 0.5,
            minTrackingConfidence: 0.5,
        });
        _faceMesh.onResults(r => {
            _faceLandmarks = (r.multiFaceLandmarks && r.multiFaceLandmarks.length > 0)
                ? r.multiFaceLandmarks[0] : null;
        });
        _faceMesh.initialize()
            .then(() => { _faceMeshReady = true; _faceMeshLoading = false; })
            .catch(() => { _faceMeshLoading = false; });
    };
    s.onerror = () => { _faceMeshLoading = false; };
    document.head.appendChild(s);
}

// ── Overlay canvas ────────────────────────────────────────────────────────────

let _lmActive   = false;
let _lmOrder    = null; // ordre de révélation (shufflé une fois)
let _lmScatter  = null; // offsets satellites pré-calculés [dx0,dy0,dx1,dy1,...] × 5 par landmark
let _lmRevealed = 0;

function _startLandmarkOverlay(videoEl) {
    const canvas = document.getElementById('scan-landmarks-canvas');
    if (!canvas || !videoEl) return;
    _lmActive   = true;
    _lmOrder    = null;
    _lmScatter  = null;
    _lmRevealed = 0;

    const ctx      = canvas.getContext('2d');
    const pctLabel = document.getElementById('scan-percentage');

    async function frame() {
        if (!_lmActive) { ctx.clearRect(0, 0, canvas.width, canvas.height); return; }

        // Sync pixels avec le flux vidéo
        const vw = videoEl.videoWidth  || 640;
        const vh = videoEl.videoHeight || 480;
        if (canvas.width !== vw || canvas.height !== vh) { canvas.width = vw; canvas.height = vh; }

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Envoyer frame à MediaPipe si prêt
        if (_faceMeshReady && _faceMesh && videoEl.readyState >= 2) {
            try { await _faceMesh.send({ image: videoEl }); } catch {}
        }

        if (_faceLandmarks) {
            const N = _faceLandmarks.length;

            // Construire ordre + offsets satellites une seule fois
            if (!_lmOrder) {
                _lmOrder = Array.from({ length: N }, (_, i) => i);
                for (let i = N - 1; i > 0; i--) {
                    const j = Math.floor(Math.random() * (i + 1));
                    [_lmOrder[i], _lmOrder[j]] = [_lmOrder[j], _lmOrder[i]];
                }
                // 5 satellites par landmark [dx,dy] × 5
                _lmScatter = new Float32Array(N * 10);
                for (let i = 0; i < N; i++) {
                    for (let s = 0; s < 5; s++) {
                        const a = Math.random() * Math.PI * 2;
                        const d = (s < 2 ? 2.5 : s < 4 ? 5.5 : 9.0) + Math.random() * 2.5;
                        _lmScatter[i*10 + s*2]   = Math.cos(a) * d;
                        _lmScatter[i*10 + s*2+1] = Math.sin(a) * d;
                    }
                }
            }

            // Nombre de points affichés = pourcentage du scan
            const pct    = parseFloat(pctLabel?.textContent) || 0;
            const target = Math.floor(pct / 100 * N);
            if (target > _lmRevealed) _lmRevealed = target;

            const now = performance.now() * 0.001;
            ctx.save();
            ctx.shadowColor = '#4A9EFF';

            // Passe 1 — points principaux avec glow
            for (let i = 0; i < _lmRevealed; i++) {
                const idx   = _lmOrder[i];
                const lm    = _faceLandmarks[idx];
                const x     = lm.x * canvas.width;
                const y     = lm.y * canvas.height;
                const alpha = 0.5 + 0.3 * Math.sin(now * 2.8 + idx * 0.21);
                ctx.shadowBlur = 7;
                ctx.fillStyle  = `rgba(74,158,255,${alpha.toFixed(2)})`;
                ctx.beginPath();
                ctx.arc(x, y, 1.6, 0, Math.PI * 2);
                ctx.fill();
            }

            // Passe 2 — satellites (pas de shadow pour les perfs)
            ctx.shadowBlur = 0;
            for (let i = 0; i < _lmRevealed; i++) {
                const idx   = _lmOrder[i];
                const lm    = _faceLandmarks[idx];
                const x     = lm.x * canvas.width;
                const y     = lm.y * canvas.height;
                const alpha = 0.22 + 0.12 * Math.sin(now * 1.9 + idx * 0.17);
                ctx.fillStyle = `rgba(74,158,255,${alpha.toFixed(2)})`;
                for (let s = 0; s < 5; s++) {
                    ctx.beginPath();
                    ctx.arc(
                        x + _lmScatter[idx*10 + s*2],
                        y + _lmScatter[idx*10 + s*2+1],
                        0.85, 0, Math.PI * 2
                    );
                    ctx.fill();
                }
            }

            ctx.restore();
        }

        requestAnimationFrame(frame);
    }

    frame();
}

function _stopLandmarkOverlay() {
    _lmActive      = false;
    _faceLandmarks = null;
    _lmOrder       = null;
    _lmScatter     = null;
    _lmRevealed    = 0;
    const canvas = document.getElementById('scan-landmarks-canvas');
    if (canvas) canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
}

// ═══════════════════════════════════════════════════════════════════════════
//  PHASE 4 — Résultat du scan
// ═══════════════════════════════════════════════════════════════════════════

async function showScanResult(result) {
    const scanContainer = document.getElementById('scan-hud');
    const scanResult    = document.getElementById('scan-result');

    gsap.to(scanContainer, { opacity: 0, scale: 0.95, duration: 0.3 });
    await _delay(300);

    _stopScanCamera();

    const icon = document.getElementById('scan-result-icon');
    const text = document.getElementById('scan-result-text');
    const name = document.getElementById('scan-result-name');

    if (result.recognized) {
        icon.textContent = '✓';
        text.textContent = 'IDENTITÉ CONFIRMÉE';
        name.textContent = (_userFirstname || result.name || (window.JARVIS_ASSISTANT_NAME || 'JARVIS')).toUpperCase();
        scanResult.className = 'success';
        _flashScreen('#36D399', 0.12);
        playValidationSound();
    } else {
        icon.textContent = '✗';
        text.textContent = 'ACCÈS REFUSÉ';
        name.textContent = 'IDENTITÉ NON RECONNUE';
        scanResult.className = 'denied';
        _flashScreen('#ef4444', 0.15);
        playDeniedSound();
    }

    scanResult.style.display = 'flex';
    gsap.from(scanResult, { opacity: 0, scale: 0.8, duration: 0.4, ease: 'back.out(1.7)' });

    await _delay(1200);
    return result.recognized;
}

function _flashScreen(color, maxOpacity) {
    const flash = document.createElement('div');
    flash.style.cssText = `
        position:fixed; inset:0; z-index:9999;
        background:${color}; opacity:0; pointer-events:none;
    `;
    document.body.appendChild(flash);
    gsap.timeline()
        .to(flash, { opacity: maxOpacity, duration: 0.08 })
        .to(flash, { opacity: 0, duration: 0.35, ease: 'power2.out' })
        .call(() => flash.remove());
}

// ═══════════════════════════════════════════════════════════════════════════
//  PHASE 5 — Déploiement UI + voix Jarvis
// ═══════════════════════════════════════════════════════════════════════════

async function deployUI() {
    // Masquer overlay scan + reset pour la prochaine fois
    const overlay = document.getElementById('scan-overlay');
    gsap.to(overlay, {
        opacity: 0, duration: 0.5,
        onComplete: () => {
            overlay.style.display = 'none';
            const res = document.getElementById('scan-result');
            const cnt = document.getElementById('scan-hud');
            if (res) res.style.display = 'none';
            if (cnt) gsap.set(cnt, { opacity: 1, scale: 1 });
        },
    });

    // Masquer l'indicateur de veille
    const ind = document.getElementById('sleep-indicator');
    if (ind) {
        gsap.to(ind, { opacity: 0, duration: 0.3, onComplete: () => { ind.style.display = 'none'; } });
    }

    // Slide-in éléments UI avec stagger
    const tl = gsap.timeline();
    tl.to('#panel-left',  { opacity: 1, x: 0, duration: 0.6, ease: 'power2.out' }, 0.1);
    tl.to('#panel-right', { opacity: 1, x: 0, duration: 0.6, ease: 'power2.out' }, 0.2);
    tl.to(['#jarvis-toggle', '#globe-toggle', '#intel-toggle',
            '#dashboard-nav-btn', '#settings-nav-btn', '#panels-toggle'],
           { opacity: 1, duration: 0.5, ease: 'power2.out' }, 0.3);
    tl.to('.ticker', { opacity: 1, duration: 0.5 }, 0.4);
    tl.call(() => { if (window.sphereTriggerShockwave) window.sphereTriggerShockwave(); }, [], 0.2);

    // Voix Jarvis (après 0.8s pour que l'UI soit visible)
    await _delay(800);
    try {
        const r = await fetch('/api/voice/speak', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: _userFirstname ? 'Systèmes en ligne. Bonjour ' + _userFirstname + '.' : 'Systèmes en ligne.' }),
        });
        const data = await r.json();
        if (data.audio_b64) await _playBase64Audio(data.audio_b64);
    } catch (e) {
        console.warn('[WakeUp] TTS indisponible', e);
    }

    window._jarvisSleeping = false;
    resetInactivityTimer();
}

async function _playBase64Audio(b64) {
    try {
        const raw = atob(b64);
        const buf = new Uint8Array(raw.length);
        for (let i = 0; i < raw.length; i++) buf[i] = raw.charCodeAt(i);
        const ctx      = new (window.AudioContext || window.webkitAudioContext)();
        const audioBuf = await ctx.decodeAudioData(buf.buffer);
        const src      = ctx.createBufferSource();
        src.buffer = audioBuf;
        src.connect(ctx.destination);
        src.start();
    } catch (e) {
        console.warn('[WakeUp] Lecture audio échouée', e);
    }
}

// ═══════════════════════════════════════════════════════════════════════════
//  Orchestrateur
// ═══════════════════════════════════════════════════════════════════════════

async function triggerWakeUp() {
    if (window._wakeupInProgress) return;
    if (!window._jarvisSleeping)  return;
    window._wakeupInProgress = true;
    console.log('[WakeUp] Séquence démarrée');

    try {
        // Phase 1 — Son
        playActivationSound();

        // Phase 2 — Formation sphère (0.2s après le son)
        await _delay(200);
        await animateSphereFormation();

        // Phase 3 — Scan facial
        const scanResult = await runFaceScan();

        // Phase 4 — Résultat
        const granted = await showScanResult(scanResult);

        if (granted) {
            // Phase 5 — Déployer UI
            await deployUI();
            console.log('[WakeUp] Accès accordé — Jarvis actif');
        } else {
            // Accès refusé → fade out overlay puis retour en veille
            await _delay(2000);
            const ov = document.getElementById('scan-overlay');
            await new Promise(r => gsap.to(ov, {
                opacity: 0, duration: 0.5,
                onComplete: () => {
                    ov.style.display = 'none';
                    const res = document.getElementById('scan-result');
                    const cnt = document.getElementById('scan-hud');
                    if (res) res.style.display = 'none';
                    if (cnt) gsap.set(cnt, { opacity: 1, scale: 1 });
                    r();
                },
            }));
            window._jarvisSleeping = false;
            enterSleepMode();
            console.log('[WakeUp] Accès refusé — retour en veille');
        }
    } catch (e) {
        console.error('[WakeUp] Erreur séquence', e);
        _stopScanCamera();
        window._jarvisSleeping = false;
        resetInactivityTimer();
    } finally {
        window._wakeupInProgress = false;
    }
}

window.triggerWakeUp = triggerWakeUp;

// ── Helper ────────────────────────────────────────────────────────────────────

function _delay(ms) { return new Promise(r => setTimeout(r, ms)); }
