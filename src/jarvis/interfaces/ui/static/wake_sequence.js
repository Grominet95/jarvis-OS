'use strict';

// ═══════════════════════════════════════════════════════════════════════════
//  wake_sequence.js — Séquence de réveil Jarvis (squelette étape 2b)
//
//  API publique :
//      window.createWakeSequence(rootEl, opts)
//          → { destroy(), getState() }
//
//  opts.onComplete    : callback à l'entrée en ONLINE (CDC §7.2)
//  opts.userName      : string, défaut 'BARTH'
//  opts.requireFace   : bool, défaut true (false saute la phase FACE)
//  opts.bootLines     : string[] (sinon DEFAULT_BOOT_LINES — étape 6 = brancher /system/health)
//  opts.statusLabel   : string, défaut 'SYSTÈMES EN LIGNE'
//  opts.skippable     : bool, défaut true (clic/touche skip)
//
//  Étape 2b — périmètre : machine à états traversée bout en bout, boot logs
//  statiques, scène Three avec sphère paramétrée SPHERE_STYLE affichée à
//  l'ÉTAT ASSEMBLÉ pendant TOUTE la durée (pas encore d'animation de
//  convergence ni d'ignition). Caméra fixe (ZCAM), pas d'oscillation, pas
//  de parallaxe, pas de dérive Z — conformément aux arbitrages §4 et §5.
//
//  ShaderMaterial option (a) : reproduction fidèle de PointsMaterial.
//  Three.js r158, formule effective :
//      size_uniform  = material.size * pixelRatio
//      scale_uniform = 0.5 * canvas_css_height
//      gl_PointSize  = size_uniform * (scale_uniform / -mvPosition.z)
//  La CanvasTexture est rebâtie à partir de SPHERE_STYLE.SPRITE (mêmes stops).
// ═══════════════════════════════════════════════════════════════════════════

(function () {
    const STATES = Object.freeze({
        BOOT:     'boot',
        FACE:     'face',
        CONVERGE: 'converge',
        IGNITE:   'ignite',
        ONLINE:   'online',
    });

    // Lignes par défaut (étape 6 → remplacer par /system/health)
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
        converge: 4200,
        ignite:   2200,
    });
    const EASE = 'cubic-bezier(0.32, 0.72, 0, 1)';

    // ── CSS keyframes (injectées une seule fois) ────────────────────────────
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
            + '}';
        document.head.appendChild(css);
    }

    // ── Sprite — identique pixel-à-pixel à orb.js ──────────────────────────
    function buildSprite(S, THREE) {
        const sz = S.SPRITE.SIZE_PX;
        const c = document.createElement('canvas');
        c.width = sz; c.height = sz;
        const cc = c.getContext('2d');
        const grad = cc.createRadialGradient(sz / 2, sz / 2, 0, sz / 2, sz / 2, sz / 2);
        S.SPRITE.STOPS.forEach(function (stop) { grad.addColorStop(stop[0], stop[1]); });
        cc.fillStyle = grad;
        cc.fillRect(0, 0, sz, sz);
        return new THREE.CanvasTexture(c);
    }

    // ── Distribution shell — identique à orb.js (θ uniforme, φ via acos) ────
    function buildShellPositions(N, S) {
        const pos   = new Float32Array(N * 3);
        const seeds = new Float32Array(N);
        for (let i = 0; i < N; i++) {
            const theta = Math.random() * Math.PI * 2;
            const phi   = Math.acos(2 * Math.random() - 1);
            const r     = S.GEOMETRY.SHELL_R_MIN + Math.random() * S.GEOMETRY.SHELL_THICKNESS;
            pos[i*3]   = r * Math.sin(phi) * Math.cos(theta);
            pos[i*3+1] = r * Math.sin(phi) * Math.sin(theta);
            pos[i*3+2] = r * Math.cos(phi);
            seeds[i]   = Math.random();
        }
        return { pos: pos, seeds: seeds };
    }

    // ─────────────────────────────────────────────────────────────────────────
    function createWakeSequence(rootEl, opts) {
        opts = opts || {};
        const onComplete  = typeof opts.onComplete === 'function' ? opts.onComplete : function () {};
        const userName    = opts.userName    || 'BARTH';
        const requireFace = opts.requireFace !== false;
        const bootLines   = opts.bootLines   || DEFAULT_BOOT_LINES.slice();
        const statusLabel = opts.statusLabel || 'SYSTÈMES EN LIGNE';
        const skippable   = opts.skippable   !== false;

        const S     = window.SPHERE_STYLE;
        const THREE = window.THREE;
        if (!S || !THREE) {
            console.error('[wake] SPHERE_STYLE ou THREE manquant — chargement aborté');
            return null;
        }

        injectCss();

        // ── DOM container ──────────────────────────────────────────────────
        rootEl.style.cssText = ''
            + 'position: fixed; inset: 0; z-index: 9000; overflow: hidden;'
            + 'background: ' + S.RENDER.WAKE_BG_HEX + ';'
            + 'color: rgba(160,195,255,0.55);'
            + 'font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;';

        // ── Couches atmosphère (miroir _shared.js mountAtmosphere) ─────────
        // Reproduit le décor du dashboard pour que le cross-fade final soit
        // structurellement invisible. Spotlight figé au centre (pas de mouse
        // tracking pendant la séquence — pointeur réservé au skip).
        const spotlight = document.createElement('div');
        spotlight.className = 'spotlight';
        // --mx, --my forcés à 50% (vs tracking dans home.js)
        spotlight.style.cssText = '--mx: 50%; --my: 50%;';
        rootEl.appendChild(spotlight);

        const aurora = document.createElement('div');
        aurora.className = 'atmo atmo--aurora';
        rootEl.appendChild(aurora);

        const canvas = document.createElement('canvas');
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

        // ── Boot logs container (bas gauche) ───────────────────────────────
        const bootLogEl = document.createElement('div');
        bootLogEl.style.cssText = ''
            + 'position: absolute; left: 32px; bottom: 32px; z-index: 10;'
            + 'font-size: 11px; line-height: 1.9; letter-spacing: 0.18em;'
            + 'text-transform: uppercase; color: rgba(160,195,255,0.55);'
            + 'pointer-events: none;';
        rootEl.appendChild(bootLogEl);

        // ── Skip hint (bas droite, visible toute la séquence) ──────────────
        const skipHintEl = document.createElement('div');
        skipHintEl.style.cssText = ''
            + 'position: absolute; right: 32px; bottom: 32px; z-index: 10;'
            + 'font-size: 10px; letter-spacing: 0.18em; text-transform: uppercase;'
            + 'color: rgba(160,195,255,0.35); pointer-events: none;'
            + 'opacity: 0; animation: wakeLogIn 0.8s ' + EASE + ' 0.4s forwards;';
        skipHintEl.textContent = 'CLIQUER POUR PASSER';
        if (skippable) rootEl.appendChild(skipHintEl);

        // ── Three : renderer / camera / scene ──────────────────────────────
        const w0 = rootEl.clientWidth  || window.innerWidth;
        const h0 = rootEl.clientHeight || window.innerHeight;

        const renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: false });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, S.RENDER.PIXEL_RATIO_MAX));
        renderer.setSize(w0, h0, false);
        renderer.setClearColor(new THREE.Color(S.RENDER.WAKE_BG_HEX), 1);

        const camera = new THREE.PerspectiveCamera(S.CAMERA.FOV, w0 / h0, S.CAMERA.NEAR, S.CAMERA.FAR);
        // Caméra fixe — pas d'oscillation pendant la séquence (arbitrage §4)
        camera.position.set(0, 0, S.CAMERA.ZCAM);
        camera.lookAt(0, 0, 0);

        const scene = new THREE.Scene();

        // ── Particles ──────────────────────────────────────────────────────
        const sprite = buildSprite(S, THREE);
        const { pos, seeds } = buildShellPositions(S.GEOMETRY.PARTICLE_COUNT, S);

        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
        geo.setAttribute('aSeed',    new THREE.BufferAttribute(seeds, 1));

        const baseColor = new THREE.Color(S.COLOR.BASE_HEX);

        // Reproduction PointsMaterial Three.js r158 (sizeAttenuation=true) :
        //   size_uniform  = material.size * pixelRatio
        //   scale_uniform = 0.5 * canvas_css_height
        //   gl_PointSize  = size_uniform * (scale_uniform / -mvPosition.z)
        const HEAT_MIX_MAX = S.COLOR.HEAT_MIX_MAX.toFixed(4);
        const ALPHA_TEST   = S.MATERIAL.ALPHA_TEST.toFixed(4);

        const mat = new THREE.ShaderMaterial({
            uniforms: {
                uMap:        { value: sprite },
                uSize:       { value: S.MATERIAL.POINT_SIZE_IDLE * renderer.getPixelRatio() },
                uScale:      { value: 0.5 * h0 },
                uColor:      { value: baseColor },
                uOpacity:    { value: S.MATERIAL.OPACITY_IDLE },
                uHeat:       { value: 0.0 },
            },
            vertexShader: ''
                + 'attribute float aSeed;\n'
                + 'uniform float uSize;\n'
                + 'uniform float uScale;\n'
                + 'varying float vSeed;\n'
                + 'void main() {\n'
                + '  vSeed = aSeed;\n'
                + '  vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);\n'
                + '  gl_Position = projectionMatrix * mvPosition;\n'
                + '  gl_PointSize = uSize * (uScale / max(-mvPosition.z, 0.0001));\n'
                + '}\n',
            // Reproduction fidèle de ShaderLib.points (Three.js r158) :
            //   diffuseColor = vec4(diffuse, opacity) * tex
            //   alphaTest sur diffuseColor.a
            //   colorspace_fragment encode linear → sRGB via linearToOutputTexel
            //     (fonction injectée par WebGLProgram selon renderer.outputColorSpace,
            //      identique à celle utilisée par PointsMaterial)
            fragmentShader: ''
                + 'uniform sampler2D uMap;\n'
                + 'uniform vec3 uColor;\n'
                + 'uniform float uOpacity;\n'
                + 'uniform float uHeat;\n'
                + 'void main() {\n'
                + '  vec4 tex = texture2D(uMap, gl_PointCoord);\n'
                + '  vec3 heated = mix(uColor, vec3(1.0), clamp(uHeat, 0.0, 1.0) * ' + HEAT_MIX_MAX + ');\n'
                + '  vec4 diffuseColor = vec4(heated, uOpacity) * tex;\n'
                + '  if (diffuseColor.a < ' + ALPHA_TEST + ') discard;\n'
                + '  gl_FragColor = diffuseColor;\n'
                + '  #include <colorspace_fragment>\n'
                + '}\n',
            transparent: S.MATERIAL.TRANSPARENT,
            blending: THREE.AdditiveBlending,
            depthWrite: S.MATERIAL.DEPTH_WRITE,
        });

        const points = new THREE.Points(geo, mat);
        scene.add(points);

        // Continuité d'angle : démarrage à 0, géré par le tick (la bascule
        // PointsMaterial à l'entrée ONLINE héritera de cet angle — étape 6).
        // Vitesse exprimée en rad/s = ROT_Y_PER_FRAME · 60 (cf. arbitrage §7).
        const ROT_Y_RAD_PER_S = S.ANIM_IDLE.ROT_Y_PER_FRAME * 60;

        // ── État machine ───────────────────────────────────────────────────
        let state          = STATES.BOOT;
        let onCompleteFired = false;
        let phaseTimers    = [];
        let bootTimer      = null;
        let rafId          = null;
        let lastFrameTs    = performance.now();
        let destroyed      = false;

        function clearPhaseTimers() {
            phaseTimers.forEach(function (id) { clearTimeout(id); });
            phaseTimers.length = 0;
            if (bootTimer) { clearTimeout(bootTimer); bootTimer = null; }
        }

        function setState(next) {
            if (destroyed) return;
            if (state === next) return;
            clearPhaseTimers();
            state = next;
            onStateEnter(next);
        }

        function onStateEnter(s) {
            switch (s) {
                case STATES.BOOT:
                    renderBootLines();
                    break;
                case STATES.FACE:
                    // Étape 5 — saut immédiat (squelette)
                    phaseTimers.push(setTimeout(function () { setState(STATES.CONVERGE); }, 0));
                    break;
                case STATES.CONVERGE:
                    // Étape 3 — sphère reste à l'état assemblé, durée nominale.
                    // Boot logs fondent à l'entrée CONVERGE (EASE 0.8 s). Hint
                    // skip reste visible (CDC §9 : visible toute la séquence).
                    bootLogEl.style.transition = 'opacity 0.8s ' + EASE;
                    bootLogEl.style.opacity = '0';
                    phaseTimers.push(setTimeout(function () { setState(STATES.IGNITE); }, PHASE_DURATION_MS.converge));
                    break;
                case STATES.IGNITE:
                    // Étape 4 — pas d'effet visuel, durée nominale (climax incompressible)
                    phaseTimers.push(setTimeout(function () { setState(STATES.ONLINE); }, PHASE_DURATION_MS.ignite));
                    break;
                case STATES.ONLINE:
                    if (skipHintEl.parentNode) skipHintEl.parentNode.removeChild(skipHintEl);
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
            // Curseur ▌ — fondu d'entrée puis clignotement 1 s steps
            const cursor = document.createElement('span');
            cursor.textContent = '▌';
            const cursorDelay = (bootLines.length * BOOT_LINE_INTERVAL_MS / 1000).toFixed(3);
            const blinkDelay  = (bootLines.length * BOOT_LINE_INTERVAL_MS / 1000 + BOOT_LINE_ANIM_MS / 1000).toFixed(3);
            cursor.style.cssText = ''
                + 'opacity: 0;'
                + 'animation: wakeLogIn ' + (BOOT_LINE_ANIM_MS / 1000) + 's ' + EASE + ' ' + cursorDelay + 's forwards,'
                + '           wakeCursorBlink 1s steps(2) ' + blinkDelay + 's infinite;';
            bootLogEl.appendChild(cursor);

            // Sortie BOOT après la dernière ligne affichée + 1 tick (CDC §4)
            const totalMs = (bootLines.length - 1) * BOOT_LINE_INTERVAL_MS + BOOT_LINE_ANIM_MS + BOOT_LINE_INTERVAL_MS;
            bootTimer = setTimeout(function () {
                if (state === STATES.BOOT) {
                    setState(requireFace ? STATES.FACE : STATES.CONVERGE);
                }
            }, totalMs);
        }

        // ── Skip ───────────────────────────────────────────────────────────
        function skip() {
            if (!skippable || destroyed) return;
            if (state === STATES.BOOT || state === STATES.FACE) {
                setState(STATES.CONVERGE);
            } else if (state === STATES.CONVERGE) {
                setState(STATES.IGNITE);
            }
            // IGNITE jamais sauté — climax (CDC §4)
        }

        function onPointerDown() { skip(); }
        function onKeyDown()     { skip(); }
        rootEl.addEventListener('pointerdown', onPointerDown);
        window.addEventListener('keydown', onKeyDown);

        // ── Resize ─────────────────────────────────────────────────────────
        function onResize() {
            if (destroyed) return;
            const nw = rootEl.clientWidth  || window.innerWidth;
            const nh = rootEl.clientHeight || window.innerHeight;
            renderer.setSize(nw, nh, false);
            camera.aspect = nw / nh;
            camera.updateProjectionMatrix();
            mat.uniforms.uSize.value  = S.MATERIAL.POINT_SIZE_IDLE * renderer.getPixelRatio();
            mat.uniforms.uScale.value = 0.5 * nh;
        }
        window.addEventListener('resize', onResize);

        // ── prefers-reduced-motion ─────────────────────────────────────────
        const prefersReduced = window.matchMedia
            && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        // ── Animation loop ─────────────────────────────────────────────────
        function tick() {
            if (destroyed) return;
            rafId = requestAnimationFrame(tick);
            const now = performance.now();
            const dt  = Math.min(0.050, (now - lastFrameTs) / 1000);
            lastFrameTs = now;

            // Rotation Y en dt (séquence) — pas d'oscillation caméra (gel §4)
            points.rotation.y += ROT_Y_RAD_PER_S * dt;

            renderer.render(scene, camera);
        }

        if (prefersReduced) {
            setState(STATES.ONLINE);
        } else {
            onStateEnter(STATES.BOOT);
        }
        tick();

        // ── API publique ───────────────────────────────────────────────────
        return {
            getState: function () { return state; },
            destroy: function () {
                if (destroyed) return;
                destroyed = true;
                if (rafId) cancelAnimationFrame(rafId);
                clearPhaseTimers();
                rootEl.removeEventListener('pointerdown', onPointerDown);
                window.removeEventListener('keydown', onKeyDown);
                window.removeEventListener('resize', onResize);
                geo.dispose();
                mat.dispose();
                sprite.dispose();
                renderer.dispose();
                if (rootEl.firstChild) {
                    while (rootEl.firstChild) rootEl.removeChild(rootEl.firstChild);
                }
            },
        };
    }

    window.createWakeSequence = createWakeSequence;
})();
