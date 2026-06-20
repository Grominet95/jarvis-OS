'use client';

/**
 * WakeSequence — séquence de réveil Jarvis
 * ----------------------------------------
 * BOOT → SCAN FACIAL (rayon + landmarks + validation)
 *      → CONVERGENCE (rayon d'activation + spirale d'énergie)
 *      → IGNITION (vague cinématique de particules) → ONLINE
 *
 * Dépendances : three, @mediapipe/tasks-vision (optionnelle au runtime :
 * bascule en simulation si caméra/modèle indisponibles).
 * Confidentialité : tout le traitement caméra est local (WASM navigateur).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import * as THREE from 'three';

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const PARTICLE_COUNT = 16000;
const WAVE_COUNT = 22000;
const SPHERE_RADIUS = 1.55;
const CONVERGE_DURATION = 4.2;  // s (42 % balayage du rayon, 58 % spirale)
const IGNITE_DURATION = 2.2;    // s : la vague court jusqu'au bord de l'écran
const FACE_SCAN_DURATION = 2.6; // s
const EASE = 'cubic-bezier(0.32, 0.72, 0, 1)'; // courbe signature Apple

const MEDIAPIPE_WASM_BASE =
  'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm';
const FACE_MODEL_URL =
  'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task';

type Phase = 'boot' | 'face' | 'converge' | 'ignite' | 'online';
type FaceStatus = 'init' | 'scanning' | 'granted' | 'denied' | 'sim';

export interface WakeSequenceProps {
  onComplete?: () => void;
  userName?: string;
  requireFace?: boolean;
  bootLines?: string[];
  statusLabel?: string;
  skippable?: boolean;
  wasmBase?: string;
  modelUrl?: string;
}

const DEFAULT_BOOT_LINES = [
  'JARVIS OS — séquence de réveil',
  'memory kernel ............ OK',
  'mission engine ........... OK',
  'pipeline voix (livekit) .. OK',
  'module biométrique ....... OK',
];

// ---------------------------------------------------------------------------
// Shaders
// ---------------------------------------------------------------------------

// Sphère : spirale logarithmique activée par le rayon, micro-settle à
// l'arrivée, kick radial au passage de la vague.
const PARTICLE_VERT = /* glsl */ `
  attribute vec3 aEnd;
  attribute float aSeed;

  uniform float uConverge;
  uniform float uBeamY;
  uniform float uBeamOn;
  uniform float uWaveR;
  uniform float uWaveAmp;
  uniform float uIgnite;
  uniform float uAmbient;
  uniform float uTime;
  uniform float uPixelRatio;

  varying float vAlpha;
  varying float vHot;

  // Quintique C2 : aucune cassure de vitesse ni d'accélération
  float smootherstep(float x) {
    x = clamp(x, 0.0, 1.0);
    return x * x * x * (x * (x * 6.0 - 15.0) + 10.0);
  }

  void main() {
    float s1 = fract(aSeed * 5.73), s2 = fract(aSeed * 9.17), s3 = fract(aSeed * 3.31);

    float er = length(aEnd.xz);
    float ea = atan(aEnd.z, aEnd.x);
    float spread = 2.5 + 4.0 * s1;
    float swirl  = 6.2831 * (0.8 + 1.6 * s2);
    float y0off  = (s3 - 0.5) * 6.0;
    float yStart = aEnd.y + y0off;

    // Activation par le rayon : balayage sur les premiers 42 % de la phase
    float aT = 0.42 * clamp((4.7 - yStart) / 9.4, 0.0, 1.0);
    float p = smootherstep((uConverge - aT) / 0.58);
    float k = 1.0 - p;

    // Micro-settle : légère inspiration vers l'intérieur puis relâche
    float settle = 0.055 * sin(clamp((p - 0.72) / 0.28, 0.0, 1.0) * 3.14159);
    float radius = er * (1.0 - settle) + spread * k;
    float angle  = ea + swirl * k;
    float height = aEnd.y + y0off * k;
    vec3 pos = vec3(radius * cos(angle), height, radius * sin(angle));

    // Turbulence basse fréquence, éteinte à l'arrivée
    pos += k * 0.26 * vec3(
      sin(uTime * 0.38 + aSeed * 31.0),
      cos(uTime * 0.31 + aSeed * 17.0),
      sin(uTime * 0.44 + aSeed * 23.0)
    );

    // Respiration idle, très subtile
    pos *= 1.0 + 0.011 * sin(uTime * 0.7 + aSeed * 6.2831) * p;

    // Kick radial au passage du front de la vague
    float rr = max(length(pos), 0.0001);
    float kick = exp(-pow((rr - uWaveR) * 3.2, 2.0)) * uWaveAmp;
    pos += (pos / rr) * kick * 0.55;

    float band = exp(-pow((pos.y - uBeamY) * 2.2, 2.0)) * uBeamOn;
    float comet = p * k * 4.0;
    vHot = clamp(band * 1.2 + comet + kick * 2.5, 0.0, 1.5) + uIgnite * 0.6;

    float drift = uAmbient * (1.0 - uConverge);
    vAlpha = mix(0.10 + 0.08 * s2, 0.35 + 0.65 * p, max(p, 1.0 - drift))
           * (0.55 + 0.45 * fract(aSeed * 7.31));

    vec4 mv = modelViewMatrix * vec4(pos, 1.0);
    float size = (1.2 + 1.5 * fract(aSeed * 3.77)) * (1.0 + band * 1.6 + comet * 1.2 + kick * 1.5);
    gl_PointSize = size * uPixelRatio * (3.4 / -mv.z);
    gl_Position = projectionMatrix * mv;
  }
`;

const PARTICLE_FRAG = /* glsl */ `
  precision highp float;
  varying float vAlpha;
  varying float vHot;

  void main() {
    vec2 uv = gl_PointCoord - 0.5;
    float disc = smoothstep(0.5, 0.12, length(uv));
    vec3 col = mix(vec3(0.345, 0.604, 1.0), vec3(0.70, 0.94, 1.0), clamp(vHot, 0.0, 1.0));
    float a = disc * vAlpha;
    if (a < 0.003) discard;
    gl_FragColor = vec4(col * (0.85 + vHot * 1.7), a);
  }
`;

// Océan de particules : un sol discret sous la sphère, étendu au-delà de
// l'écran. À l'ignition, une ondulation circulaire le traverse depuis la
// sphère jusqu'à sortir du cadre : crête gaussienne + train d'ondes
// secondaires amorties (comme les ronds dans l'eau), amplitude qui décroît
// avec la distance. La vague ne coupe jamais la sphère.
const WAVE_VERT = /* glsl */ `
  attribute float aR;       // rayon dans le disque
  attribute float aTheta;
  attribute float aSeed;
  uniform float uWaveR;     // rayon du front (-5 = inactif)
  uniform float uAmp;
  uniform float uTime;
  uniform float uPixelRatio;
  varying float vA;
  varying float vHot;

  void main() {
    float s1 = fract(aSeed * 7.31);
    float s2 = fract(aSeed * 3.77);

    vec3 pos = vec3(aR * cos(aTheta), 0.0, aR * sin(aTheta));

    // Micro-vie ambiante du sol
    pos.y += 0.045 * sin(uTime * 0.6 + aSeed * 40.0);

    float glow = 0.0;
    if (uWaveR > -1.0) {
      float d = aR - uWaveR;

      // Crête principale : gaussienne qui voyage
      float crest = exp(-d * d / 1.20);

      // Train d'ondes secondaires derrière le front, amorti
      float behind = max(-d, 0.0);
      float trail = sin(behind * 2.6) * exp(-behind * 0.70);

      // L'énergie s'étale : l'amplitude décroît avec le rayon
      float decay = 1.0 / (1.0 + uWaveR * 0.28);

      float h = uAmp * decay * (crest * 1.25 + 0.38 * trail * smoothstep(0.0, 0.6, behind));
      pos.y += h;

      glow = (crest + 0.35 * exp(-behind * 0.55) * step(0.001, behind)) * decay * uAmp;
      vHot = crest * decay * uAmp * 1.5;
    } else {
      vHot = 0.0;
    }

    // Sol à peine visible au repos, embrasé au passage de la vague,
    // fondu vers l'horizon
    float horizon = exp(-aR * 0.10);
    vA = (0.035 + 0.030 * s1 + glow * 0.85) * horizon;

    vec4 mv = modelViewMatrix * vec4(pos, 1.0);
    float size = (1.1 + 1.6 * s2) * (1.0 + vHot * 1.6 + glow * 0.8);
    gl_PointSize = size * uPixelRatio * (3.4 / -mv.z);
    gl_Position = projectionMatrix * mv;
  }
`;

const WAVE_FRAG = /* glsl */ `
  precision highp float;
  varying float vA;
  varying float vHot;
  void main() {
    vec2 uv = gl_PointCoord - 0.5;
    float disc = smoothstep(0.5, 0.10, length(uv));
    vec3 col = mix(vec3(0.30, 0.55, 1.0), vec3(0.98, 0.99, 1.0), clamp(vHot, 0.0, 1.0));
    float a = disc * vA;
    if (a < 0.003) discard;
    gl_FragColor = vec4(col * (0.9 + vHot * 1.5), a);
  }
`;

// Quad plein écran (clip space) : noyau d'énergie + rayon d'activation
const FX_VERT = /* glsl */ `
  varying vec2 vUv;
  void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }
`;

const FX_FRAG = /* glsl */ `
  precision highp float;
  varying vec2 vUv;
  uniform float uCore;
  uniform float uBeamNdcY;
  uniform float uBeamOn;
  uniform float uAspect;
  uniform float uTime;

  void main() {
    vec2 ndc = vUv * 2.0 - 1.0;
    vec2 c = vec2(ndc.x * uAspect, ndc.y);
    float r = length(c);
    vec3 col = vec3(0.0);

    float pulse = 0.94 + 0.06 * sin(uTime * 4.0);
    col += vec3(0.35, 0.62, 1.0) * exp(-r * r * 5.5) * uCore * pulse * 0.9;
    col += vec3(0.75, 0.92, 1.0) * exp(-r * r * 22.0) * uCore * pulse * 0.8;

    float dy = ndc.y - uBeamNdcY;
    float lcore = exp(-pow(dy * 220.0, 2.0));
    float lhalo = exp(-pow(dy * 16.0, 2.0)) * 0.30;
    float edgeF = 1.0 - 0.35 * pow(abs(ndc.x), 3.0);
    col += vec3(0.55, 0.95, 1.0) * (lcore * 1.4 + lhalo) * uBeamOn * edgeF;

    float a = clamp(max(max(col.r, col.g), col.b), 0.0, 1.0);
    if (a < 0.003) discard;
    gl_FragColor = vec4(col, a);
  }
`;

// Post : réfraction subtile au front de la vague (lentille + aberration
// chromatique), flash bref, streak anamorphique, vignette permanente.
const POST_FRAG = /* glsl */ `
  precision highp float;
  varying vec2 vUv;
  uniform sampler2D tDiffuse;
  uniform float uWaveT;
  uniform float uWaveAmp;
  uniform float uAspect;
  uniform float uTime;

  void main() {
    vec2 ndc = vUv * 2.0 - 1.0;
    vec2 c = vec2(ndc.x * uAspect, ndc.y);
    float r = length(c);
    vec3 col;

    col = texture2D(tDiffuse, vUv).rgb;

    if (uWaveT > 0.0 && uWaveT < 1.0) {
      // Flash initial, bref et doux
      col += vec3(0.90, 0.95, 1.0) * exp(-uWaveT * 9.0) * 0.12 * uWaveAmp;

      // Streak anamorphique horizontal : la signature cinéma de la détonation
      float streak = exp(-abs(c.y) * 30.0) * exp(-c.x * c.x * 1.1) * exp(-uWaveT * 6.5);
      col += vec3(0.62, 0.84, 1.0) * streak * 0.85 * uWaveAmp;
    }

    col *= 1.0 - 0.15 * r * r;
    gl_FragColor = vec4(col, 1.0);
  }
`;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildSphereAttributes() {
  const end = new Float32Array(PARTICLE_COUNT * 3);
  const seed = new Float32Array(PARTICLE_COUNT);
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const t = (i + 0.5) / PARTICLE_COUNT;
    const phi = Math.acos(1 - 2 * t);
    const theta = Math.PI * (1 + Math.sqrt(5)) * i;
    const r = SPHERE_RADIUS * (0.92 + Math.random() * 0.08);
    end[i * 3 + 0] = r * Math.sin(phi) * Math.cos(theta);
    end[i * 3 + 1] = r * Math.cos(phi);
    end[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta);
    seed[i] = Math.random();
  }
  return { end, seed };
}

function buildWaveAttributes() {
  const pos = new Float32Array(WAVE_COUNT * 3);
  const r = new Float32Array(WAVE_COUNT);
  const theta = new Float32Array(WAVE_COUNT);
  const seed = new Float32Array(WAVE_COUNT);
  for (let i = 0; i < WAVE_COUNT; i++) {
    r[i] = Math.sqrt(Math.random()) * 14;   // disque uniforme, bien au-delà de l'écran
    theta[i] = Math.random() * Math.PI * 2;
    seed[i] = Math.random();
    pos[i * 3 + 0] = r[i] * Math.cos(theta[i]);
    pos[i * 3 + 2] = r[i] * Math.sin(theta[i]);
  }
  return { pos, r, theta, seed };
}

function buildSimLandmarks(): { x: number; y: number }[] {
  const pts: { x: number; y: number }[] = [];
  const oval = (cx: number, cy: number, rx: number, ry: number, n: number, a0 = 0, a1 = Math.PI * 2) => {
    for (let i = 0; i < n; i++) {
      const a = a0 + (i / n) * (a1 - a0);
      pts.push({ x: cx + rx * Math.cos(a), y: cy + ry * Math.sin(a) });
    }
  };
  oval(0.5, 0.52, 0.21, 0.30, 26);
  oval(0.41, 0.45, 0.052, 0.028, 8);
  oval(0.59, 0.45, 0.052, 0.028, 8);
  oval(0.41, 0.385, 0.07, 0.022, 6, Math.PI, 2 * Math.PI);
  oval(0.59, 0.385, 0.07, 0.022, 6, Math.PI, 2 * Math.PI);
  for (let i = 0; i < 5; i++) pts.push({ x: 0.5, y: 0.46 + i * 0.032 });
  oval(0.5, 0.61, 0.035, 0.012, 5, 0, Math.PI);
  oval(0.5, 0.70, 0.075, 0.032, 12);
  return pts;
}

const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
const easeInOut = (x: number) => x * x * (3 - 2 * x);

// ---------------------------------------------------------------------------
// Composant
// ---------------------------------------------------------------------------

export default function WakeSequence({
  onComplete,
  userName = 'BARTH',
  requireFace = true,
  bootLines = DEFAULT_BOOT_LINES,
  statusLabel = 'SYSTÈMES EN LIGNE',
  skippable = true,
  wasmBase = MEDIAPIPE_WASM_BASE,
  modelUrl = FACE_MODEL_URL,
}: WakeSequenceProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const faceCanvasRef = useRef<HTMLCanvasElement>(null);

  const [phase, setPhase] = useState<Phase>('boot');
  const [visibleLogs, setVisibleLogs] = useState(0);
  const [faceStatus, setFaceStatus] = useState<FaceStatus>('init');
  const [faceMessage, setFaceMessage] = useState('INITIALISATION CAPTEUR…');
  const [clock, setClock] = useState('');
  const [dateStr, setDateStr] = useState('');

  const phaseRef = useRef<Phase>('boot');
  const skipRef = useRef(false);
  const completedRef = useRef(false);
  const convergeStartRef = useRef<number | null>(null);

  const goto = useCallback((p: Phase) => {
    if (phaseRef.current === p) return;
    phaseRef.current = p;
    setPhase(p);
    if (p === 'converge') convergeStartRef.current = performance.now();
    if (p === 'online' && !completedRef.current) {
      completedRef.current = true;
      onComplete?.();
    }
  }, [onComplete]);

  // Horloge
  useEffect(() => {
    const tick = () => {
      const n = new Date();
      setClock(n.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }));
      setDateStr(n.toLocaleDateString('fr-FR', {
        weekday: 'long', day: '2-digit', month: 'long', year: 'numeric',
      }).toUpperCase());
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  // ------------------------------------------------------------------
  // BOOT
  // ------------------------------------------------------------------
  useEffect(() => {
    if (phase !== 'boot') return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      goto('online');
      return;
    }
    let i = 0;
    const id = setInterval(() => {
      i += 1;
      setVisibleLogs(Math.min(i, bootLines.length));
      if (i > bootLines.length) {
        clearInterval(id);
        goto(requireFace ? 'face' : 'converge');
      }
    }, 180);
    return () => clearInterval(id);
  }, [phase, bootLines.length, requireFace, goto]);

  // ------------------------------------------------------------------
  // FACE : caméra + landmarks + rayon de scan
  // ------------------------------------------------------------------
  useEffect(() => {
    if (phase !== 'face') return;
    const canvas = faceCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;
    const W = canvas.width, H = canvas.height;

    let video: HTMLVideoElement | null = null;
    let stream: MediaStream | null = null;
    let landmarker: any = null;
    let raf = 0;
    let disposed = false;
    let mode: 'live' | 'sim' = 'sim';

    const simPoints = buildSimLandmarks();
    let livePoints: { x: number; y: number }[] = [];
    let detectedFrames = 0;
    let scanStart: number | null = null;
    let attempt = 0;
    let resolved = false;

    const SIM_LINKS: [number, number][] = [];
    const chain = (from: number, n: number, close: boolean) => {
      for (let i = 0; i < n - 1; i++) SIM_LINKS.push([from + i, from + i + 1]);
      if (close) SIM_LINKS.push([from + n - 1, from]);
    };
    chain(0, 26, true); chain(26, 8, true); chain(34, 8, true);
    chain(42, 6, false); chain(48, 6, false); chain(54, 5, false);
    chain(59, 5, false); chain(64, 12, true);

    const succeed = () => {
      if (resolved || disposed) return;
      resolved = true;
      setFaceStatus(mode === 'sim' ? 'sim' : 'granted');
      setFaceMessage(
        mode === 'sim'
          ? `IDENTITÉ CONFIRMÉE · BONJOUR ${userName} · SIMULATION`
          : `IDENTITÉ CONFIRMÉE · BONJOUR ${userName}`
      );
      setTimeout(() => !disposed && goto('converge'), 1300);
    };

    const fail = () => {
      if (resolved || disposed) return;
      attempt += 1;
      setFaceStatus('denied');
      if (attempt >= 2) {
        setFaceMessage('VISAGE NON DÉTECTÉ · DÉROGATION MANUELLE');
        resolved = true;
        setTimeout(() => !disposed && goto('converge'), 1400);
      } else {
        setFaceMessage('VISAGE NON DÉTECTÉ · NOUVELLE TENTATIVE');
        setTimeout(() => {
          if (disposed || resolved) return;
          detectedFrames = 0;
          scanStart = performance.now();
          setFaceStatus('scanning');
          setFaceMessage('SCAN BIOMÉTRIQUE EN COURS');
        }, 1200);
      }
    };

    const setup = async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { width: 640, height: 480, facingMode: 'user' },
        });
        video = document.createElement('video');
        video.srcObject = stream;
        video.muted = true;
        video.playsInline = true;
        await video.play();
        mode = 'live';
        try {
          const vision = await import('@mediapipe/tasks-vision');
          const files = await vision.FilesetResolver.forVisionTasks(wasmBase);
          landmarker = await vision.FaceLandmarker.createFromOptions(files, {
            baseOptions: { modelAssetPath: modelUrl, delegate: 'GPU' },
            runningMode: 'VIDEO',
            numFaces: 1,
          });
        } catch {
          landmarker = null;
        }
      } catch {
        mode = 'sim';
      }
      if (disposed) return;
      scanStart = performance.now();
      setFaceStatus('scanning');
      setFaceMessage(mode === 'sim' ? 'SCAN BIOMÉTRIQUE · MODE SIMULATION' : 'SCAN BIOMÉTRIQUE EN COURS');
    };

    const draw = (now: number) => {
      raf = requestAnimationFrame(draw);
      ctx.clearRect(0, 0, W, H);

      if (mode === 'live' && video && video.readyState >= 2) {
        ctx.save();
        ctx.translate(W, 0); ctx.scale(-1, 1);
        const vw = video.videoWidth, vh = video.videoHeight;
        const s = Math.max(W / vw, H / vh);
        ctx.drawImage(video, (W - vw * s) / 2, (H - vh * s) / 2, vw * s, vh * s);
        ctx.restore();
        ctx.fillStyle = 'rgba(6, 14, 32, 0.62)';
        ctx.fillRect(0, 0, W, H);
      } else {
        ctx.fillStyle = '#060d1d';
        ctx.fillRect(0, 0, W, H);
      }

      let pts = simPoints;
      if (mode === 'live' && landmarker && video) {
        try {
          const res = landmarker.detectForVideo(video, now);
          const lm = res?.faceLandmarks?.[0];
          if (lm) {
            detectedFrames += 1;
            livePoints = lm.map((p: any) => ({ x: 1 - p.x, y: p.y }));
          }
        } catch { /* frame ratée */ }
        pts = livePoints;
      } else if (mode === 'live' && !landmarker) {
        pts = [];
        detectedFrames += 1;
      } else {
        detectedFrames += 1;
        pts = simPoints.map((p, i) => ({
          x: p.x + Math.sin(now / 900 + i) * 0.0015,
          y: p.y + Math.cos(now / 1100 + i) * 0.0015,
        }));
      }

      if (scanStart !== null && !resolved) {
        const t = (now - scanStart) / 1000 / FACE_SCAN_DURATION;
        const scanY = easeInOut(clamp01(t)) * H;
        const revealed = pts.filter(p => p.y * H <= scanY);

        ctx.lineWidth = 1;
        ctx.strokeStyle = 'rgba(90, 170, 255, 0.22)';
        if (mode !== 'live') {
          ctx.beginPath();
          for (const [a, b] of SIM_LINKS) {
            const pa = pts[a], pb = pts[b];
            if (pa.y * H <= scanY && pb.y * H <= scanY) {
              ctx.moveTo(pa.x * W, pa.y * H);
              ctx.lineTo(pb.x * W, pb.y * H);
            }
          }
          ctx.stroke();
        } else if (revealed.length > 1) {
          ctx.beginPath();
          const step = Math.max(1, Math.floor(revealed.length / 140));
          for (let i = step; i < revealed.length; i += step) {
            ctx.moveTo(revealed[i - step].x * W, revealed[i - step].y * H);
            ctx.lineTo(revealed[i].x * W, revealed[i].y * H);
          }
          ctx.stroke();
        }

        for (const p of revealed) {
          const px = p.x * W, py = p.y * H;
          const near = Math.exp(-Math.pow((py - scanY) / 26, 2));
          ctx.fillStyle = `rgba(${110 + near * 130}, ${190 + near * 60}, 255, ${0.5 + near * 0.5})`;
          ctx.beginPath();
          ctx.arc(px, py, 1.3 + near * 1.7, 0, Math.PI * 2);
          ctx.fill();
        }

        const grad = ctx.createLinearGradient(0, scanY - 36, 0, scanY + 6);
        grad.addColorStop(0, 'rgba(110, 230, 255, 0)');
        grad.addColorStop(0.85, 'rgba(110, 230, 255, 0.16)');
        grad.addColorStop(1, 'rgba(110, 230, 255, 0)');
        ctx.fillStyle = grad;
        ctx.fillRect(0, scanY - 36, W, 42);
        ctx.fillStyle = 'rgba(170, 240, 255, 0.95)';
        ctx.fillRect(0, scanY - 1, W, 2);

        if (t >= 1) {
          scanStart = null;
          const ok = mode === 'sim' ? true : detectedFrames > 12;
          ok ? succeed() : fail();
        }
      } else if (resolved) {
        for (const p of pts) {
          ctx.fillStyle = 'rgba(140, 230, 255, 0.75)';
          ctx.beginPath();
          ctx.arc(p.x * W, p.y * H, 1.4, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    };

    setup();
    raf = requestAnimationFrame(draw);

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      stream?.getTracks().forEach(t => t.stop());
      landmarker?.close?.();
    };
  }, [phase, userName, wasmBase, modelUrl, goto]);

  // ------------------------------------------------------------------
  // Scène Three : sphère + vague + FX + post
  // ------------------------------------------------------------------
  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(mount.clientWidth, mount.clientHeight);
    renderer.setClearColor(0x04070e, 1);
    mount.appendChild(renderer.domElement);

    const prx = renderer.getPixelRatio();
    const rt = new THREE.WebGLRenderTarget(mount.clientWidth * prx, mount.clientHeight * prx);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(50, mount.clientWidth / mount.clientHeight, 0.1, 100);
    camera.position.z = 5.2;

    // --- Sphère ---
    const { end, seed } = buildSphereAttributes();
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(end.slice(), 3));
    geo.setAttribute('aEnd', new THREE.BufferAttribute(end, 3));
    geo.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1));

    const pu = {
      uConverge: { value: 0 },
      uBeamY: { value: 10 },
      uBeamOn: { value: 0 },
      uWaveR: { value: -10 },
      uWaveAmp: { value: 0 },
      uIgnite: { value: 0 },
      uAmbient: { value: 1 },
      uTime: { value: 0 },
      uPixelRatio: { value: prx },
    };
    const particleMat = new THREE.ShaderMaterial({
      uniforms: pu, vertexShader: PARTICLE_VERT, fragmentShader: PARTICLE_FRAG,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    const points = new THREE.Points(geo, particleMat);
    scene.add(points);

    // --- Vague cinématique ---
    const wAttrs = buildWaveAttributes();
    const waveGeo = new THREE.BufferGeometry();
    waveGeo.setAttribute('position', new THREE.BufferAttribute(wAttrs.pos, 3));
    waveGeo.setAttribute('aR', new THREE.BufferAttribute(wAttrs.r, 1));
    waveGeo.setAttribute('aTheta', new THREE.BufferAttribute(wAttrs.theta, 1));
    waveGeo.setAttribute('aSeed', new THREE.BufferAttribute(wAttrs.seed, 1));
    const wu = {
      uWaveR: { value: -5 }, uAmp: { value: 0 },
      uTime: { value: 0 }, uPixelRatio: { value: prx },
    };
    const waveMat = new THREE.ShaderMaterial({
      uniforms: wu, vertexShader: WAVE_VERT, fragmentShader: WAVE_FRAG,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    const wavePoints = new THREE.Points(waveGeo, waveMat);
    wavePoints.position.y = -2.05;  // sous la sphère : la vague ne la coupe jamais
    wavePoints.rotation.x = 0.30;   // perspective vers l'horizon
    scene.add(wavePoints);

    // --- FX (noyau + rayon) ---
    const fu = {
      uCore: { value: 0 }, uBeamNdcY: { value: 10 }, uBeamOn: { value: 0 },
      uAspect: { value: mount.clientWidth / mount.clientHeight }, uTime: { value: 0 },
    };
    const fxMat = new THREE.ShaderMaterial({
      uniforms: fu, vertexShader: FX_VERT, fragmentShader: FX_FRAG,
      transparent: true, depthTest: false, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    const fx = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), fxMat);
    fx.frustumCulled = false;
    fx.renderOrder = 10;
    scene.add(fx);

    // --- Post ---
    const postUniforms = {
      tDiffuse: { value: rt.texture },
      uWaveT: { value: 0 }, uWaveAmp: { value: 1 },
      uAspect: { value: mount.clientWidth / mount.clientHeight }, uTime: { value: 0 },
    };
    const postMat = new THREE.ShaderMaterial({
      uniforms: postUniforms, vertexShader: FX_VERT, fragmentShader: POST_FRAG,
      depthTest: false, depthWrite: false,
    });
    const postScene = new THREE.Scene();
    const postQuad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), postMat);
    postQuad.frustumCulled = false;
    postScene.add(postQuad);

    // --- Interactions ---
    const mouse = { x: 0, y: 0 };
    const mouseSm = { x: 0, y: 0 };
    let waveT: number | null = null;
    let waveAmp = 1;
    let igniteFired = false;

    const onMove = (e: PointerEvent) => {
      mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.y = (e.clientY / window.innerHeight) * 2 - 1;
    };
    const onDown = () => {
      if (phaseRef.current === 'online') { waveT = 0; waveAmp = 0.45; }
      else if (skippable) skipRef.current = true;
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerdown', onDown);
    const onResize = () => {
      camera.aspect = mount.clientWidth / mount.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(mount.clientWidth, mount.clientHeight);
      rt.setSize(mount.clientWidth * prx, mount.clientHeight * prx);
      fu.uAspect.value = camera.aspect;
      postUniforms.uAspect.value = camera.aspect;
    };
    window.addEventListener('resize', onResize);

    const NDC_HALF_H = camera.position.z * Math.tan((camera.fov * Math.PI) / 360);
    let raf = 0;
    let last = performance.now();

    const animate = (now: number) => {
      raf = requestAnimationFrame(animate);
      const dt = Math.min((now - last) / 1000, 0.05);
      last = now;
      const time = now / 1000;
      pu.uTime.value = time;
      fu.uTime.value = time;
      postUniforms.uTime.value = time;

      // Parallaxe avec inertie
      mouseSm.x += (mouse.x - mouseSm.x) * 0.045;
      mouseSm.y += (mouse.y - mouseSm.y) * 0.045;

      // Skip
      if (skipRef.current) {
        skipRef.current = false;
        if (phaseRef.current === 'boot' || phaseRef.current === 'face') goto('converge');
        else if (phaseRef.current === 'converge' && convergeStartRef.current !== null) {
          convergeStartRef.current = now - CONVERGE_DURATION * 1000;
        }
      }

      // Convergence
      let conv = 0;
      if (phaseRef.current === 'converge' && convergeStartRef.current !== null) {
        conv = clamp01((now - convergeStartRef.current) / (CONVERGE_DURATION * 1000));
        if (conv >= 1 && !igniteFired) {
          igniteFired = true;
          waveT = 0; waveAmp = 1;
          goto('ignite');
        }
      } else if (phaseRef.current === 'ignite' || phaseRef.current === 'online') {
        conv = 1;
      }
      pu.uConverge.value = conv;
      pu.uAmbient.value = phaseRef.current === 'boot' || phaseRef.current === 'face' ? 1 : 0;
      if (phaseRef.current === 'converge') fu.uCore.value = Math.pow(conv, 1.6) * 0.9;

      // Rayon d'activation : balaye de +4.7 à -4.7 sur les premiers 42 %
      const sweepP = clamp01(conv / 0.42);
      const beamWorldY = 4.7 - 9.4 * easeInOut(sweepP);
      const beamOn = conv > 0 && sweepP < 1
        ? Math.min(1, sweepP * 12) * Math.min(1, (1 - sweepP) * 12)
        : 0;
      pu.uBeamY.value = beamWorldY;
      pu.uBeamOn.value = beamOn;
      fu.uBeamNdcY.value = beamWorldY / NDC_HALF_H;
      fu.uBeamOn.value = beamOn;

      // Vague (ignition ou pulse de clic)
      if (waveT !== null) {
        waveT += dt / IGNITE_DURATION;
        if (waveT >= 1) {
          waveT = null;
          pu.uWaveAmp.value = 0;
          postUniforms.uWaveT.value = 0;
          wu.uWaveR.value = -5;
          wu.uAmp.value = 0;
          camera.position.z = 5.2;
          if (phaseRef.current === 'ignite') goto('online');
        } else {
          // Micro-dolly : léger recul puis retour — du poids, pas de tremblement
          camera.position.z = 5.2 + waveT * (1 - waveT) * 4 * 0.20 * waveAmp;
          // Le front court de la sphère jusqu'à sortir de l'écran
          wu.uWaveR.value = 14.5 * Math.pow(waveT, 0.55);
          wu.uAmp.value = waveAmp * Math.pow(1 - waveT, 0.45) * 1.1;
          wu.uTime.value = time;
          const sedov = Math.pow(waveT, 0.42);
          postUniforms.uWaveT.value = waveT;
          postUniforms.uWaveAmp.value = waveAmp;
          pu.uWaveR.value = sedov * 3.6;
          pu.uWaveAmp.value = Math.pow(1 - waveT, 1.5) * waveAmp / (0.6 + 2.0 * waveT);
          pu.uIgnite.value = Math.sin(waveT * Math.PI) * waveAmp * 0.4;
          if (phaseRef.current === 'ignite') fu.uCore.value = (1 - waveT) * 0.9;
        }
      } else {
        pu.uIgnite.value = 0;
        if (phaseRef.current === 'online') fu.uCore.value = 0;
      }

      points.rotation.y = time * 0.035 + mouseSm.x * 0.12;
      points.rotation.x = mouseSm.y * 0.08;

      // Deux passes : scène → texture, puis post (réfraction + vignette)
      renderer.setRenderTarget(rt);
      renderer.render(scene, camera);
      renderer.setRenderTarget(null);
      renderer.render(postScene, camera);
    };
    raf = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerdown', onDown);
      window.removeEventListener('resize', onResize);
      geo.dispose();
      waveGeo.dispose();
      particleMat.dispose();
      waveMat.dispose();
      fxMat.dispose();
      postMat.dispose();
      rt.dispose();
      renderer.dispose();
      mount.removeChild(renderer.domElement);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ------------------------------------------------------------------
  // Rendu DOM — chorégraphie Apple
  // ------------------------------------------------------------------
  const hudVisible = phase === 'online';
  const faceVisible = phase === 'face';
  const frameColor =
    faceStatus === 'granted' || faceStatus === 'sim' ? 'rgba(110, 255, 210, 0.8)'
    : faceStatus === 'denied' ? 'rgba(255, 110, 110, 0.8)'
    : 'rgba(110, 200, 255, 0.55)';

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: '#04070e', overflow: 'hidden',
        cursor: hudVisible ? 'default' : 'pointer',
        fontFamily: 'var(--font-mono, ui-monospace, "JetBrains Mono", monospace)',
        userSelect: 'none',
      }}
    >
      <div ref={mountRef} style={{ position: 'absolute', inset: 0 }} />

      {/* Logs de boot */}
      <div
        style={{
          position: 'absolute', left: 28, bottom: 24,
          color: 'rgba(160, 195, 255, 0.55)', fontSize: 11,
          letterSpacing: '0.18em', lineHeight: 1.9, textTransform: 'uppercase',
          opacity: phase === 'boot' || phase === 'face' ? 1 : 0,
          transition: `opacity 0.8s ${EASE}`, pointerEvents: 'none',
        }}
      >
        {bootLines.slice(0, visibleLogs).map((l, i) => (
          <div key={i} style={{ animation: `wakeLogIn 0.8s ${EASE} both` }}>{l}</div>
        ))}
        {phase === 'boot' && <span style={{ animation: 'wakeBlink 1s steps(1) infinite' }}>▌</span>}
      </div>

      {/* Cadre de scan facial */}
      <div
        style={{
          position: 'absolute', inset: 0, display: 'flex',
          alignItems: 'center', justifyContent: 'center',
          opacity: faceVisible ? 1 : 0,
          transform: faceVisible ? 'scale(1)' : 'scale(0.965)',
          filter: faceVisible ? 'blur(0px)' : 'blur(10px)',
          transition: `opacity 0.9s ${EASE}, transform 0.9s ${EASE}, filter 0.9s ${EASE}`,
          pointerEvents: 'none',
        }}
      >
        <div style={{ position: 'relative' }}>
          <canvas
            ref={faceCanvasRef}
            width={360}
            height={460}
            style={{ display: 'block', borderRadius: 10, boxShadow: '0 0 60px rgba(60, 120, 255, 0.18)' }}
          />
          {([['top', 'left'], ['top', 'right'], ['bottom', 'left'], ['bottom', 'right']] as const)
            .map(([v, h], i) => (
            <div key={i} style={{
              position: 'absolute',
              top: v === 'top' ? -2 : 'auto', bottom: v === 'bottom' ? -2 : 'auto',
              left: h === 'left' ? -2 : 'auto', right: h === 'right' ? -2 : 'auto',
              width: 26, height: 26,
              borderTop: v === 'top' ? `2px solid ${frameColor}` : 'none',
              borderBottom: v === 'bottom' ? `2px solid ${frameColor}` : 'none',
              borderLeft: h === 'left' ? `2px solid ${frameColor}` : 'none',
              borderRight: h === 'right' ? `2px solid ${frameColor}` : 'none',
              transition: 'border-color 0.4s ease',
            }} />
          ))}
          <div style={{
            position: 'absolute', left: 0, right: 0, bottom: -36, textAlign: 'center',
            fontSize: 10, letterSpacing: '0.32em', color: frameColor,
            transition: 'color 0.4s ease', whiteSpace: 'nowrap',
          }}>
            {faceMessage}
          </div>
        </div>
      </div>

      {/* HUD final — entrée « Hello » macOS */}
      <div
        style={{
          position: 'absolute', top: 40, right: 48, textAlign: 'right',
          opacity: hudVisible ? 1 : 0,
          transform: hudVisible ? 'translateY(0) scale(1)' : 'translateY(18px) scale(0.985)',
          filter: hudVisible ? 'blur(0px)' : 'blur(16px)',
          transition: `opacity 1.5s ${EASE} 0.25s, transform 1.5s ${EASE} 0.25s, filter 1.5s ${EASE} 0.25s`,
          pointerEvents: 'none',
        }}
      >
        <div style={{
          fontSize: 'clamp(48px, 7vw, 96px)', fontWeight: 700, color: '#f2f7ff',
          lineHeight: 1,
          letterSpacing: hudVisible ? '0.02em' : '0.09em',
          transition: `letter-spacing 1.8s ${EASE} 0.25s`,
          textShadow: '0 0 32px rgba(120, 180, 255, 0.45)',
          fontFamily: 'var(--font-display, inherit)',
        }}>
          {clock}
        </div>
        <div style={{ marginTop: 10, fontSize: 11, letterSpacing: '0.32em', color: 'rgba(170, 200, 255, 0.6)' }}>
          {dateStr}
        </div>
        <div style={{
          marginTop: 18, fontSize: 10, letterSpacing: '0.4em',
          color: 'rgba(110, 230, 255, 0.85)', display: 'inline-flex', alignItems: 'center', gap: 10,
        }}>
          <span style={{
            width: 6, height: 6, borderRadius: '50%', background: '#6de6ff',
            boxShadow: '0 0 10px #6de6ff', animation: 'wakePulse 2.4s ease-in-out infinite',
          }} />
          {statusLabel}
        </div>
      </div>

      {skippable && !hudVisible && (
        <div style={{
          position: 'absolute', bottom: 24, right: 28, fontSize: 9,
          letterSpacing: '0.3em', color: 'rgba(140, 170, 220, 0.35)',
          textTransform: 'uppercase', pointerEvents: 'none',
          transition: `opacity 0.8s ${EASE}`,
        }}>
          cliquer pour passer
        </div>
      )}

      <style>{`
        @keyframes wakeBlink { 0%, 49% { opacity: 1; } 50%, 100% { opacity: 0; } }
        @keyframes wakePulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
        @keyframes wakeLogIn {
          from { opacity: 0; transform: translateY(7px); filter: blur(4px); }
          to   { opacity: 1; transform: translateY(0);   filter: blur(0); }
        }
      `}</style>
    </div>
  );
}
