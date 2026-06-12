'use strict';

// ═══════════════════════════════════════════════════════════════════════════
//  SPHERE_STYLE — source de vérité partagée entre orb.js (dashboard idle) et
//  wake_sequence.js (séquence de réveil).
//
//  Étape 1 du CDC « Séquence de réveil » (12 juin 2026, contrainte C1).
//  Toute valeur idle est extraite de l'implémentation effective de orb.js et
//  doit être respectée à l'identique en sortie de séquence (état ONLINE).
//
//  Convention d'échelle : R et ZCAM ci-dessous sont la base monde. Toutes les
//  grandeurs spatiales du CDC sont stockées dans WAKE_R sous forme NORMALISÉE
//  (ratios sans dimension, exprimés en multiples de R). À l'usage :
//      distance_monde = WAKE_R.<key> * R
//      pour un terme en exp(−k·d), k_normalisé = k_ref·R_ref, et on calcule
//      en pratique sur la distance normalisée d̃ = d/R.
//
//  Aucune chauffe transitoire ne survit à l'entrée ONLINE : applyHeat(0)
//  retourne strictement COLOR_BASE_VEC3 (#4A9EFF exact).
// ═══════════════════════════════════════════════════════════════════════════

(function () {
    const R    = 28;   // rayon nominal de la sphère (unités monde Three.js)
    const ZCAM = 95;   // position z de la caméra au repos

    // ── Géométrie particules (extrait de orb.js, état "idle") ──────────────
    const GEOMETRY = {
        PARTICLE_COUNT: 22000,
        R: R,
        SHELL_THICKNESS: 2,
        SHELL_R_MIN: R - 1,          // 27
        SHELL_R_MAX: R + 1,          // 29
        // theta uniforme sur [0, 2π) ; phi = acos(2·rand − 1) ; r = SHELL_R_MIN + rand·SHELL_THICKNESS
        DISTRIBUTION: 'uniform-spherical-shell',
    };

    // ── Sprite particule (CanvasTexture radial blanc, partagée vers la séquence) ──
    const SPRITE = {
        SIZE_PX: 128,
        STOPS: [
            [0.00, 'rgba(255,255,255,1)'],
            [0.18, 'rgba(255,255,255,0.95)'],
            [0.45, 'rgba(255,255,255,0.38)'],
            [0.75, 'rgba(255,255,255,0.09)'],
            [1.00, 'rgba(255,255,255,0)'],
        ],
    };

    // ── Matériau ──────────────────────────────────────────────────────────
    // Pendant la séquence : ShaderMaterial reproduisant ces valeurs (cf. arbitrage §6).
    // En ONLINE : bascule sur PointsMaterial avec ces valeurs exactes.
    const MATERIAL = {
        POINT_SIZE_IDLE: 0.58,           // mat.size en ONLINE (cible des lerps idle de orb.js)
        SIZE_ATTENUATION: true,          // shader équivalent : gl_PointSize *= (1.0 / -mvPosition.z) · scaleFactor
        ALPHA_TEST: 0.001,
        DEPTH_WRITE: false,
        TRANSPARENT: true,
        BLENDING: 'additive',            // THREE.AdditiveBlending
        OPACITY_IDLE: 0.72,              // mat.opacity en ONLINE (cible idle)
    };

    // ── Couleur ───────────────────────────────────────────────────────────
    // Signature visuelle mono-couleur. La chauffe pendant CONVERGE/IGNITE
    // est dérivée de cette base et y RETOURNE strictement à l'entrée ONLINE.
    const COLOR = {
        BASE_HEX: 0x4A9EFF,
        BASE_HEX_STRING: '#4A9EFF',
        BASE_RGB_255: [74, 158, 255],
        BASE_VEC3: [0x4A / 255, 0x9E / 255, 0xFF / 255], // ≈ [0.2902, 0.6196, 1.0000]
        HEAT_WHITE_VEC3: [1.0, 1.0, 1.0],
        HEAT_MIX_MAX: 0.70,              // mix(base, white, heat · 0.70) — heat ∈ [0,1]
    };

    // ── Animation idle (orb.js, en ONLINE) ────────────────────────────────
    const ANIM_IDLE = {
        // « Respiration » Z (drift cloud) — uniquement axe Z, faible amplitude
        DRIFT_Z_FREQ:    0.10,           // sin(t · 0.10), t en pseudo-secondes
        DRIFT_Z_AMPL:    0.8,            // unités monde
        DRIFT_Z_SPRING:  0.008,
        DRIFT_Z_DAMPING: 0.94,
        // Aucune respiration radiale en idle (effectiveRadius = R · (1 + audioLevel · 0.15), audioLevel = 0)
        BREATH_RADIAL_AMPL: 0.0,

        // Rotation idle — Y uniquement
        ROT_Y_PER_FRAME: 0.0015,         // +0.0015 rad / frame (≈ 0.094 rad/s @ 60 fps)
        ROT_X_AUTO:      0.0,            // pas de pitch automatique
        DRAG_DAMPING:    0.88,           // damping idle du drag manuel

        // Inter-particules (rails visibles uniquement en "thinking", quasi-nuls en idle)
        LINE_AMOUNT_IDLE: 0.12,
        LINE_OPACITY_K:   0.07,          // lineMat.opacity = LINE_AMOUNT · LINE_OPACITY_K → 0.0084 idle

        // Parallaxe souris : aucune (C1 prime sur §6.3 de la référence)
        MOUSE_PARALLAX: 0.0,
    };

    // ── Caméra ────────────────────────────────────────────────────────────
    const CAMERA = {
        FOV:  45,
        NEAR: 1,
        FAR:  1000,
        ZCAM: ZCAM,

        // Oscillation orbitale idle (orb.js) — GELÉE pendant boot/face/converge/ignite,
        // réactivée à l'entrée ONLINE par rampe d'amplitude × (0→1) sur OSC_RAMP_S.
        OSC_X_AMPL: 5,                   // sin(t · OSC_X_FREQ) · OSC_X_AMPL
        OSC_X_FREQ: 0.02,
        OSC_Y_AMPL: 3,                   // cos(t · OSC_Y_FREQ) · OSC_Y_AMPL
        OSC_Y_FREQ: 0.03,
        OSC_RAMP_S: 2.0,                 // courbe EASE, phase continue, aucun saut

        // Dolly ignition (proportionnel à ZCAM)
        // dz(t) = DOLLY_AMPL_FACTOR · ZCAM · t · (1 − t) · 4   → max ±0.038 · ZCAM ≈ ±3.61
        DOLLY_AMPL_FACTOR: 0.038,
    };

    // ── Pipeline de rendu ─────────────────────────────────────────────────
    const RENDER = {
        PIXEL_RATIO_MAX:    2,
        // orb.js peint sur canvas transparent ; la séquence pose son propre fond opaque.
        ORB_CLEAR_COLOR_HEX: 0x000000,
        ORB_CLEAR_ALPHA:     0,
        // Fond DOM aligné sur le dashboard (_shared.css :17, var(--bg-0)).
        // Le CDC mentionnait #04070e, amendé pour matcher l'existant et rendre
        // le cross-fade structurellement invisible.
        WAKE_BG_HEX:        '#06080D',
        // Vignette shader désactivée : la séquence reproduit la vignette CSS
        // du dashboard (atmo--vignette), pas de double couche.
        VIGNETTE_GAIN:       0.0,         // texel × (1 − VIGNETTE_GAIN · r²)
    };

    // ═════════════════════════════════════════════════════════════════════
    //  WAKE_R — grandeurs monde de la séquence, NORMALISÉES en multiples de R.
    //
    //  Convention : pour toute grandeur de dimension [longueur], la valeur ici
    //  est divisée par R_ref = 1.55 (celle de WakeSequence.tsx) puis appliquée
    //  comme `valeur · R` au moment de l'usage. Les coefficients de décroissance
    //  exponentielle exp(−k·d) sont stockés tels que k_normalisé = k_ref · R_ref,
    //  utilisés sur la distance normalisée d̃ = d / R.
    // ═════════════════════════════════════════════════════════════════════
    const WAKE_R = {
        // ── CONVERGE — rayon d'activation ─────────────────────────────────
        // y monde ∈ [−4.7, +4.7] dans la réf → ±3.03 · R
        BEAM_Y_MAX:        +3.03,
        BEAM_Y_MIN:        -3.03,
        BEAM_SIGMA:         0.290,        // σ = 0.45 / 1.55 = 0.29  (× R en monde)
        BEAM_T_END:         0.42,         // borne haute du balayage (CONVERGE)
        ACTIVATION_T_FRACT: 0.42,         // aT = 0.42 · (BEAM_Y_MAX − yStart_norm) / amplitude_norm
        ACTIVATION_WIDTH:   0.58,         // p = smootherstep((uConverge − aT) / 0.58)

        // ── CONVERGE — spirale ─────────────────────────────────────────────
        SPIRAL_DISP_MIN:   1.61,          // 2.5 / 1.55
        SPIRAL_DISP_MAX:   4.19,          // 6.5 / 1.55
        SPIRAL_TURNS_MIN:  0.8,
        SPIRAL_TURNS_MAX:  2.4,
        SPIRAL_VERT_DISP: 1.94,          // ±3 / 1.55
        TURBULENCE_AMPL:   0.168,         // 0.26 / 1.55
        TURBULENCE_FREQ_HZ_MIN: 0.31,
        TURBULENCE_FREQ_HZ_MAX: 0.44,
        MICRO_SETTLE_AMPL:    0.055,      // % du rayon, sans dimension
        MICRO_SETTLE_P_START: 0.72,
        MICRO_SETTLE_P_END:   1.00,

        // ── Effet comète (chauffe) en vol ──────────────────────────────────
        HOT_GAIN:           4.0,          // vHot ∝ p · k · 4 (CDC §5.3, comportement, pas couleur — la couleur reste contrainte par COLOR.HEAT_MIX_MAX)

        // ── CONVERGE — noyau d'énergie central (quad FX, ne croise pas la sphère) ──
        CORE_GAUSS_OUTER_K:  5.5,         // exp(−5.5 · r̃²)   (bleu chauffée selon applyHeat)
        CORE_GAUSS_INNER_K: 22.0,         // exp(−22 · r̃²)    (blanc additif)
        CORE_INTENSITY_EXP:  1.6,         // conv^1.6
        CORE_INTENSITY_GAIN: 0.9,
        CORE_PULSE_BASE:     0.94,
        CORE_PULSE_AMPL:     0.06,
        CORE_PULSE_FREQ:     4.0,

        // ── IGNITE — océan permanent (sol particules) ──────────────────────
        OCEAN_COUNT:         22000,       // préréglage Mac. Pi : 10 000 (cf. §8 du CDC, à exposer plus tard)
        OCEAN_DISK_RADIUS:   9.03,        // 14 / 1.55  → distribution r = √rand · 9.03 · R
        OCEAN_Y:            -1.32,        // -2.05 / 1.55
        OCEAN_TILT_RAD:      0.30,        // rotation.x (perspective d'horizon)
        OCEAN_ALPHA_BASE:    0.035,
        OCEAN_ALPHA_RAND:    0.030,
        // exp(−0.10 · r_monde) → exp(−(0.10 · 1.55) · r̃) = exp(−0.155 · r̃)
        OCEAN_HORIZON_DECAY: 0.155,
        OCEAN_SWELL_AMPL:    0.029,       // 0.045 / 1.55  (amplitude verticale × R en monde)
        OCEAN_SWELL_FREQ:    0.6,         // rad/s, temporel, pas de rescale par R

        // ── IGNITE — front de vague ────────────────────────────────────────
        WAVE_DURATION_S:     2.2,
        WAVE_FRONT_R:        9.35,        // R(t) = 9.35 · t^0.55 · R
        WAVE_FRONT_EXP:      0.55,
        // gaussienne crête : exp(−d²/1.20) en réf → exp(−d̃²/0.499)
        WAVE_CREST_SIGMA2:   0.499,
        WAVE_CREST_HEIGHT:   1.25,
        // train d'ondes : 0.38 · sin(2.6 · d⁻) · exp(−0.70 · d⁻), lissé sur 0.6 unité réf
        WAVE_TRAIN_GAIN:     0.38,
        WAVE_TRAIN_FREQ:     4.03,        // 2.6 · 1.55  (k_norm = k_ref · R_ref)
        WAVE_TRAIN_DECAY:    1.085,       // 0.70 · 1.55
        WAVE_TRAIN_SMOOTH:   0.387,       // 0.6 / 1.55
        // amplitude × 1 / (1 + 0.28 · R) en réf → 1 / (1 + 0.434 · R̃)
        WAVE_AMP_DECAY_K:    0.434,       // 0.28 · 1.55
        WAVE_ENV_EXP:        0.45,        // (1 − t)^0.45, temporel
        WAVE_ENV_GAIN:       1.1,
        WAVE_HOT_GAIN:       1.5,         // luminance de crête
        WAVE_TRAIL_LUM_GAIN: 0.35,
        WAVE_TRAIL_LUM_DECAY: 0.853,      // 0.55 · 1.55

        // ── IGNITE — kick radial sur la sphère ─────────────────────────────
        KICK_FRONT_R:        2.32,        // uWaveR = 3.6 · t^0.42 · R / 1.55
        KICK_FRONT_EXP:      0.42,
        KICK_ENV_NUM_EXP:    1.5,         // (1 − t)^1.5
        KICK_ENV_DEN_A:      0.6,         // 1 / (0.6 + 2t)
        KICK_ENV_DEN_B:      2.0,
        KICK_SIGMA:          0.20,        // 0.31 / 1.55 (largeur radiale × R en monde)

        // ── IGNITE — FX écran (clip space, indépendants de R) ──────────────
        FLASH_DECAY:    9.0,              // exp(−9t) · 0.12
        FLASH_AMPL:     0.12,
        STREAK_DECAY_Y: 30.0,             // exp(−30·|y|)
        STREAK_DECAY_X:  1.1,             // exp(−1.1·x²)
        STREAK_DECAY_T:  6.5,             // exp(−6.5·t)
        STREAK_AMPL:    0.85,

        // ── Replay vague (clic en ONLINE) ──────────────────────────────────
        WAVE_REPLAY_AMPL: 0.45,
    };

    // ── Helpers ───────────────────────────────────────────────────────────
    // Couleur dynamique pendant CONVERGE/IGNITE. heat = 0 → base #4A9EFF exact.
    function applyHeat(heat) {
        const m = Math.min(1, Math.max(0, heat)) * COLOR.HEAT_MIX_MAX;
        const b = COLOR.BASE_VEC3;
        return [
            b[0] + (1 - b[0]) * m,
            b[1] + (1 - b[1]) * m,
            b[2] + (1 - b[2]) * m,
        ];
    }

    // Conversion R-normalisé → monde, pour usage call-site explicite.
    function toWorld(normalized) { return normalized * R; }

    // ── Export global (cohérent avec window.JarvisOrb, window.THREE) ──────
    window.SPHERE_STYLE = Object.freeze({
        R: R,
        ZCAM: ZCAM,
        GEOMETRY: Object.freeze(GEOMETRY),
        SPRITE: Object.freeze({ SIZE_PX: SPRITE.SIZE_PX, STOPS: Object.freeze(SPRITE.STOPS.map(Object.freeze)) }),
        MATERIAL: Object.freeze(MATERIAL),
        COLOR: Object.freeze({
            BASE_HEX: COLOR.BASE_HEX,
            BASE_HEX_STRING: COLOR.BASE_HEX_STRING,
            BASE_RGB_255: Object.freeze(COLOR.BASE_RGB_255),
            BASE_VEC3: Object.freeze(COLOR.BASE_VEC3),
            HEAT_WHITE_VEC3: Object.freeze(COLOR.HEAT_WHITE_VEC3),
            HEAT_MIX_MAX: COLOR.HEAT_MIX_MAX,
        }),
        ANIM_IDLE: Object.freeze(ANIM_IDLE),
        CAMERA: Object.freeze(CAMERA),
        RENDER: Object.freeze(RENDER),
        WAKE_R: Object.freeze(WAKE_R),
        applyHeat: applyHeat,
        toWorld: toWorld,
    });
})();
