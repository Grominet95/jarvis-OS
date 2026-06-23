'use strict';

// ═════════════════════════════════════════════════════════════════════════════
//  MediaPipe Vision — landmarks en temps réel sur le feed caméra.
//  - FaceDetector  : bounding box + coin accents du visage
//  - GestureRecognizer : squelette de la main + reconnaissance de geste
//  Tout tourne dans le browser (WebGL/WASM). Seuls les événements discrets
//  sont envoyés à Jarvis via le WebSocket existant.
// ═════════════════════════════════════════════════════════════════════════════

const _MP_CDN = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14';

let _faceDetector = null;
let _gestureRec   = null;
let _rafId        = null;
let _lastDetect   = 0;
let _canvasCtx    = null;
const _DETECT_FPS = 15; // fps de détection
const _DETECT_MS  = 1000 / _DETECT_FPS;

// ── Présence ──────────────────────────────────────────────────────────────────
let _facePresent   = false;
let _presenceSince = 0;
const _PRESENCE_ON_MS  = 2000;
const _PRESENCE_OFF_MS = 5000;

// ── Gestes ────────────────────────────────────────────────────────────────────
// Ce module est un CAPTEUR : il détecte des gestes et émet des événements neutres
// vers le GestureRouter. Le SENS (Spotify, LLM, vues…) vit dans les bindings,
// pas ici. Le seul mapping conservé est l'affichage à l'écran.
const _GESTURE_LABELS = {
  Thumb_Up:    'POUCE HAUT',
  Thumb_Down:  'POUCE BAS',
  Open_Palm:   'PAUME OUVERTE',
  Victory:     'VICTOIRE',
  Pointing_Up: 'POINTER',
};

// Mapping global (fallback hors vue) — reproduit EXACTEMENT le comportement
// historique : paume/victoire → Spotify direct, pouces/pointer → LLM,
// pincement vertical → volume.
if (window.Jarvis?.gestures) {
  Jarvis.gestures.registerGlobal({
    Open_Palm:   { type: 'ws',  event: 'gesture_direct', gesture: 'Open_Palm' },  // play/pause
    Victory:     { type: 'ws',  event: 'gesture_direct', gesture: 'Victory' },    // piste suivante
    Thumb_Up:    { type: 'llm', gesture: 'Thumb_Up',    label: _GESTURE_LABELS.Thumb_Up },
    Thumb_Down:  { type: 'llm', gesture: 'Thumb_Down',  label: _GESTURE_LABELS.Thumb_Down },
    Pointing_Up: { type: 'llm', gesture: 'Pointing_Up', label: _GESTURE_LABELS.Pointing_Up },
    pinch_y:     { type: 'ws',  event: 'gesture_volume' },
  });
}

// Connexions de la main (indices MediaPipe)
const _HAND_CONN = [
  [0,1],[1,2],[2,3],[3,4],
  [0,5],[5,6],[6,7],[7,8],
  [5,9],[9,10],[10,11],[11,12],
  [9,13],[13,14],[14,15],[15,16],
  [13,17],[0,17],[17,18],[18,19],[19,20],
];
const _HAND_TIPS = new Set([0, 4, 8, 12, 16, 20]);

let _lastGestureSeen  = null;
let _lastGestureSince = 0;
let _lastGestureSent  = 0;
const _GESTURE_HOLD_MS     = 1200;
const _GESTURE_COOLDOWN_MS = 4000;

// ── YOLO objects (reçus du daemon Python via WS) ──────────────────────────────
let _yoloObjects = [];
let _yoloExpireAt = 0;
const _YOLO_TTL_MS = 2000; // les boxes expirent si pas de nouvelle frame en 2s

window.mpSetYoloObjects = (objects, now) => {
  _yoloObjects  = objects;
  _yoloExpireAt = now + _YOLO_TTL_MS;
};

function _drawYoloObjects(ctx, cw, ch, now) {
  if (!_yoloObjects.length || now > _yoloExpireAt) return;
  _yoloObjects.forEach(obj => {
    const [x1n, y1n, x2n, y2n] = obj.bbox;
    const x = x1n * cw, y = y1n * ch;
    const w = (x2n - x1n) * cw, h = (y2n - y1n) * ch;

    // Rectangle orange
    ctx.strokeStyle = 'rgba(255, 180, 30, 0.88)';
    ctx.lineWidth = 2;
    ctx.strokeRect(x, y, w, h);

    // Label — ctx.scale(-1,1) annule le CSS scaleX(-1) pour que le texte soit lisible
    const label = `${obj.label} ${Math.round(obj.conf * 100)}%`;
    ctx.font = 'bold 12px monospace';
    const tw = ctx.measureText(label).width;
    ctx.save();
    ctx.scale(-1, 1);
    ctx.translate(-cw, 0);
    ctx.fillStyle = 'rgba(255, 180, 30, 0.88)';
    ctx.fillRect(x, y - 20, tw + 10, 20);
    ctx.fillStyle = '#000';
    ctx.fillText(label, x + 5, y - 6);
    ctx.restore();
  });
}

// ── Pincement (volume) ────────────────────────────────────────────────────────
let _pinchActive   = false;
let _pinchRefY     = 0;
let _pinchLastSent = 0;
const _PINCH_DIST    = 0.09;  // distance normalisée pouce-index
const _PINCH_STEP    = 0.035; // déplacement Y par palier
const _PINCH_COOL_MS = 280;   // ms entre deux envois volume

// ── Zoom à deux mains (manipulation spatiale — pas de fallback global) ─────────
let _twoHandRefDist  = null;  // distance de référence (glissante) entre les 2 mains
let _twoHandLastSent = 0;
const _TWO_HAND_STEP    = 0.04; // variation min de distance avant d'émettre
const _TWO_HAND_SCALE   = 300;  // distance normalisée → delta de zoom
const _TWO_HAND_COOL_MS = 80;   // ms entre deux émissions

// ── Navigation au poing fermé (pan — pas de fallback global) ───────────────────
let _fistRef      = null;   // position de référence (glissante) du poignet
let _fistLastSent = 0;
const _FIST_PAN_SCALE = 600; // déplacement normalisé → dx/dy de pan
const _FIST_STEP      = 1.0;  // déplacement min (unités scaled) avant d'émettre
const _FIST_COOL_MS   = 50;   // ms entre deux émissions

// Réinitialise les détecteurs de bas niveau quand un niveau supérieur prend la
// main (exclusion mutuelle stricte — un seul actif par frame).
function _resetPinchAndDiscrete() {
  _pinchActive = false;
  _lastGestureSeen = null; _lastGestureSince = 0;
}

// ── Helpers DOM ───────────────────────────────────────────────────────────────
const _$ = id => document.getElementById(id);

function _ctx() {
  if (_canvasCtx) return _canvasCtx;
  const c = _$('cam-canvas');
  if (c) _canvasCtx = c.getContext('2d');
  return _canvasCtx;
}

function _syncCanvas() {
  const v = _$('cam-video'), c = _$('cam-canvas');
  if (v && c && v.videoWidth && (c.width !== v.videoWidth || c.height !== v.videoHeight)) {
    c.width  = v.videoWidth;
    c.height = v.videoHeight;
    _canvasCtx = null; // reset context after resize
  }
}

function _setStatus(text, ok) {
  const el = _$('mp-status');
  if (!el) return;
  el.textContent = text;
  el.className = 'mp-status' + (ok ? ' active' : ok === false ? ' error' : '');
}

function _showGesture(label, final) {
  const el = _$('mp-gesture-label');
  if (!el) return;
  el.textContent = label;
  el.style.opacity = '1';
  el.classList.toggle('triggered', !!final);
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.style.opacity = '0'; el.classList.remove('triggered'); }, final ? 2200 : 800);
}

// ── Boucle de détection ───────────────────────────────────────────────────────
function _detect(now) {
  _rafId = requestAnimationFrame(_detect);
  if (now - _lastDetect < _DETECT_MS) return;
  _lastDetect = now;

  const video = _$('cam-video');
  if (!video || video.readyState < 2 || !video.videoWidth) return;

  _syncCanvas();
  const ctx = _ctx();
  if (!ctx) return;

  const { width: cw, height: ch } = _$('cam-canvas');
  ctx.clearRect(0, 0, cw, ch);

  // ── Visage ──────────────────────────────────────────────────────
  let faceDetected = false;
  try {
    const fr = _faceDetector.detectForVideo(video, now);
    if (fr.detections.length) {
      faceDetected = true;
      _drawFace(ctx, fr.detections, cw, ch);
    }
  } catch (_) {}

  // ── Mains + gestes (0..2 mains) ─────────────────────────────────
  let hands = [];           // landmarks par main
  let gesture = null;       // geste discret de la 1re main
  let handLandmarks = null; // 1re main (pincement / poing)
  let fistCount = 0;        // nb de poings fermés détectés (0..2)
  try {
    const gr = _gestureRec.recognizeForVideo(video, now);
    hands = gr.landmarks || [];
    hands.forEach(h => _drawHand(ctx, h, cw, ch));
    handLandmarks = hands[0] || null;
    // Geste discret par main (null si None ou score insuffisant). Avec
    // numHands:2, gr.gestures[i] correspond à gr.landmarks[i].
    const handGestures = (gr.gestures || []).map(gg => {
      const top = gg?.[0];
      return (top && top.categoryName !== 'None' && top.score >= 0.60) ? top.categoryName : null;
    });
    gesture   = handGestures[0] || null;       // 1re main (inchangé pour la suite)
    fistCount = handGestures.filter(g => g === 'Closed_Fist').length;
  } catch (_) {}

  _handlePresence(faceDetected, now);

  // ── Exclusion mutuelle : UN SEUL détecteur actif par frame ──────
  // Priorité : 2 POINGS (zoom) > 1 poing (pan) > 1 main ouverte (pincement/
  // discrets) > rien.
  if (hands.length >= 2 && fistCount >= 2) {
    // ZOOM — uniquement deux poings fermés
    _resetPinchAndDiscrete(); _fistRef = null;
    _handleTwoHandZoom(hands[0], hands[1], now);
  } else if (hands.length === 1 && gesture === 'Closed_Fist' && handLandmarks) {
    // PAN — un seul poing
    _twoHandRefDist = null; _resetPinchAndDiscrete();
    _handleFistPan(handLandmarks, now);
  } else if (hands.length === 1) {
    // Une main ouverte — gestes discrets + pincement (volume)
    _twoHandRefDist = null; _fistRef = null;
    _handleGesture(gesture, now);
    _handlePinch(handLandmarks, now);
  } else {
    // 0 main, ou 2 mains qui ne sont PAS deux poings → ne rien déclencher
    _twoHandRefDist = null; _fistRef = null;
    _resetPinchAndDiscrete();
  }

  _drawYoloObjects(ctx, cw, ch, now);

  // Dot de présence dans le header
  const el = _$('mp-status');
  if (el && _faceDetector) {
    if (!el.textContent || el.textContent === 'ACTIF') {
      el.classList.toggle('active', faceDetected);
    }
  }
}

// ── Dessin ────────────────────────────────────────────────────────────────────
function _drawFace(ctx, detections, cw, ch) {
  detections.forEach(d => {
    const b = d.boundingBox;
    if (!b) return;
    const x = b.originX * cw, y = b.originY * ch;
    const w = b.width  * cw, h = b.height * ch;
    const s = Math.min(w, h) * 0.18;

    // Cadre plein transparent
    ctx.strokeStyle = 'rgba(74, 158, 255, 0.22)';
    ctx.lineWidth = 1;
    ctx.strokeRect(x, y, w, h);

    // Coins accentués
    ctx.strokeStyle = 'rgba(74, 158, 255, 0.90)';
    ctx.lineWidth = 2;
    const corners = [[x, y, s, 0, 0, s], [x+w, y, -s, 0, 0, s], [x, y+h, s, 0, 0, -s], [x+w, y+h, -s, 0, 0, -s]];
    corners.forEach(([ox, oy, dx1, dy1, dx2, dy2]) => {
      ctx.beginPath(); ctx.moveTo(ox, oy); ctx.lineTo(ox+dx1, oy+dy1); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(ox, oy); ctx.lineTo(ox+dx2, oy+dy2); ctx.stroke();
    });

  });
}

function _drawHand(ctx, landmarks, cw, ch) {
  // Connexions
  ctx.strokeStyle = 'rgba(74, 158, 255, 0.75)';
  ctx.lineWidth = 2.5;
  _HAND_CONN.forEach(([a, b]) => {
    const la = landmarks[a], lb = landmarks[b];
    if (!la || !lb) return;
    ctx.beginPath();
    ctx.moveTo(la.x * cw, la.y * ch);
    ctx.lineTo(lb.x * cw, lb.y * ch);
    ctx.stroke();
  });

  // Segment pouce-index mis en valeur si pincement actif
  if (_pinchActive) {
    const t = landmarks[4], i = landmarks[8];
    if (t && i) {
      ctx.strokeStyle = 'rgba(255, 200, 60, 0.95)';
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.moveTo(t.x * cw, t.y * ch);
      ctx.lineTo(i.x * cw, i.y * ch);
      ctx.stroke();
    }
  }

  // Points
  landmarks.forEach((lm, idx) => {
    const tip = _HAND_TIPS.has(idx);
    const pinchPt = _pinchActive && (idx === 4 || idx === 8);
    ctx.beginPath();
    ctx.arc(lm.x * cw, lm.y * ch, tip ? 7 : 5, 0, Math.PI * 2);
    ctx.fillStyle   = pinchPt ? 'rgba(255, 200, 60, 0.95)' : tip ? 'rgba(255, 255, 255, 0.95)' : 'rgba(74, 158, 255, 0.90)';
    ctx.strokeStyle = pinchPt ? 'rgba(255, 200, 60, 0.70)' : 'rgba(74, 158, 255, 0.70)';
    ctx.lineWidth   = 1.5;
    ctx.fill();
    if (tip) ctx.stroke();
  });
}

// ── Présence ──────────────────────────────────────────────────────────────────
function _handlePresence(detected, now) {
  if (detected) {
    if (_facePresent)  { _presenceSince = 0; return; }
    if (!_presenceSince) _presenceSince = now;
    if (now - _presenceSince >= _PRESENCE_ON_MS) {
      _facePresent = true; _presenceSince = 0;
      _sendEvent({ event: 'presence', active: true });
    }
  } else {
    if (!_facePresent) { _presenceSince = 0; return; }
    if (!_presenceSince) _presenceSince = now;
    if (now - _presenceSince >= _PRESENCE_OFF_MS) {
      _facePresent = false; _presenceSince = 0;
      _sendEvent({ event: 'presence', active: false });
    }
  }
}

// ── Geste ─────────────────────────────────────────────────────────────────────
function _handleGesture(gesture, now) {
  if (_pinchActive) { _lastGestureSeen = null; _lastGestureSince = 0; return; }
  const known = gesture && _GESTURE_LABELS[gesture];
  if (!known) { _lastGestureSeen = null; _lastGestureSince = 0; return; }

  if (gesture !== _lastGestureSeen) {
    _lastGestureSeen = gesture; _lastGestureSince = now;
    _showGesture(_GESTURE_LABELS[gesture], false);
    return;
  }
  const held = now - _lastGestureSince;
  if (held < _GESTURE_HOLD_MS) {
    const pct = Math.round((held / _GESTURE_HOLD_MS) * 100);
    _showGesture(_GESTURE_LABELS[gesture] + ' ' + pct + '%', false);
    return;
  }
  if (now - _lastGestureSent < _GESTURE_COOLDOWN_MS) return;

  // Déclenchement — émission d'un événement neutre, le routeur décide du sens
  // (vue active sinon fallback global). La bulle de chat LLM est gérée par le
  // binding `type:'llm'` (champ label), plus ici.
  _lastGestureSent  = now;
  _lastGestureSince = now;
  _showGesture('→ ' + _GESTURE_LABELS[gesture], true);

  Jarvis.gestures?.route({
    source: 'mediapipe', type: 'gesture', name: gesture,
    phase: 'confirmed', confidence: 1, ts: now,
  });
}

// ── Pincement ─────────────────────────────────────────────────────────────────
function _handlePinch(landmarks, now) {
  if (!landmarks || landmarks.length < 9) { _pinchActive = false; return; }
  const t = landmarks[4]; // pouce
  const i = landmarks[8]; // index
  const dist = Math.hypot(t.x - i.x, t.y - i.y);

  if (dist >= _PINCH_DIST) { _pinchActive = false; return; }

  const midY = (t.y + i.y) / 2;
  if (!_pinchActive) {
    _pinchActive = true;
    _pinchRefY   = midY;
    _showGesture('PINCEMENT', false);
    return;
  }

  if (now - _pinchLastSent < _PINCH_COOL_MS) return;

  const delta = _pinchRefY - midY; // positif = main montée
  if (Math.abs(delta) >= _PINCH_STEP) {
    const dir = delta > 0 ? 10 : -10;
    _pinchRefY     = midY;
    _pinchLastSent = now;
    _showGesture(dir > 0 ? '▲ VOL' : '▼ VOL', false);
    Jarvis.gestures?.route({
      source: 'mediapipe', type: 'pinch', name: 'pinch_y',
      phase: 'continuous', axis: 'y', delta: dir, ts: now,
    });
  }
}

// ── Zoom à deux mains ───────────────────────────────────────────────────────
// Mesure l'écart entre les poignets des deux mains. S'écarter = zoom in (delta>0),
// se rapprocher = zoom out (delta<0). Référence glissante. Aucun fallback global :
// inerte hors d'une vue qui binde two_hand_zoom.
function _handleTwoHandZoom(h0, h1, now) {
  const p0 = h0?.[0], p1 = h1?.[0]; // poignets
  if (!p0 || !p1) { _twoHandRefDist = null; return; }
  const d = Math.hypot(p0.x - p1.x, p0.y - p1.y);

  if (_twoHandRefDist === null) {
    _twoHandRefDist = d;
    _showGesture('ZOOM ✊✊', false);
    return;
  }
  if (now - _twoHandLastSent < _TWO_HAND_COOL_MS) return;

  const diff = d - _twoHandRefDist;
  if (Math.abs(diff) >= _TWO_HAND_STEP) {
    const delta = diff * _TWO_HAND_SCALE; // + = mains qui s'écartent = zoom in
    _twoHandRefDist  = d;
    _twoHandLastSent = now;
    _showGesture(delta > 0 ? '⊕ ZOOM' : '⊖ ZOOM', false);
    Jarvis.gestures?.route({
      source: 'mediapipe', type: 'two_hand', name: 'two_hand_zoom',
      phase: 'continuous', delta, ts: now,
    });
  }
}

// ── Navigation au poing fermé ────────────────────────────────────────────────
// Suit le déplacement du poignet poing fermé → pan (dx/dy). Référence glissante.
// Aucun fallback global : inerte hors d'une vue qui binde fist_pan.
function _handleFistPan(landmarks, now) {
  const p = landmarks?.[0]; // poignet
  if (!p) { _fistRef = null; return; }

  if (_fistRef === null) {
    _fistRef = { x: p.x, y: p.y };
    _showGesture('POING ✊', false);
    return;
  }
  if (now - _fistLastSent < _FIST_COOL_MS) return;

  const dx = (p.x - _fistRef.x) * _FIST_PAN_SCALE;
  const dy = (p.y - _fistRef.y) * _FIST_PAN_SCALE;
  if (Math.abs(dx) >= _FIST_STEP || Math.abs(dy) >= _FIST_STEP) {
    _fistRef      = { x: p.x, y: p.y };
    _fistLastSent = now;
    Jarvis.gestures?.route({
      source: 'mediapipe', type: 'fist', name: 'fist_pan',
      phase: 'continuous', dx, dy, axis: 'xy', ts: now,
    });
  }
}

function _sendEvent(payload) {
  const sid = window._jarvisSessionId?.();
  window._jarvisWsSend?.({ type: 'vision_event', session_id: sid, ...payload });
}

// ── API publique ──────────────────────────────────────────────────────────────
async function mpInit() {
  if (_faceDetector && _gestureRec) return;
  _setStatus('CHARGEMENT…', null);
  try {
    // Attend que le module script ait exposé MediaPipe sur window
    const lib = await _waitForLib();
    const { FilesetResolver, FaceDetector, GestureRecognizer } = lib;
    const vision = await FilesetResolver.forVisionTasks(_MP_CDN + '/wasm');
    [_faceDetector, _gestureRec] = await Promise.all([
      FaceDetector.createFromOptions(vision, {
        baseOptions: {
          modelAssetPath: 'https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite',
          delegate: 'GPU',
        },
        runningMode: 'VIDEO',
        minDetectionConfidence: 0.45,
      }),
      GestureRecognizer.createFromOptions(vision, {
        baseOptions: {
          modelAssetPath: 'https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task',
          delegate: 'GPU',
        },
        runningMode: 'VIDEO',
        numHands: 2,
        minHandDetectionConfidence: 0.5,
        minHandPresenceConfidence: 0.5,
        minTrackingConfidence: 0.5,
      }),
    ]);
    _setStatus('ACTIF', true);
    console.log('[MediaPipe] OK — face + gestes prêts');
  } catch (e) {
    _setStatus('ERREUR', false);
    console.error('[MediaPipe] Init échouée :', e);
  }
}

function _waitForLib() {
  if (window._MediaPipeVision) return Promise.resolve(window._MediaPipeVision);
  if (window._mpLibPromise)    return window._mpLibPromise;

  window._mpLibPromise = import(_MP_CDN + '/vision_bundle.mjs').then(mod => {
    window._MediaPipeVision = {
      FilesetResolver:   mod.FilesetResolver,
      FaceDetector:      mod.FaceDetector,
      GestureRecognizer: mod.GestureRecognizer,
    };
    return window._MediaPipeVision;
  });
  return window._mpLibPromise;
}

function mpStart() {
  if (_rafId) return;
  _syncCanvas();
  _rafId = requestAnimationFrame(_detect);
  console.log('[MediaPipe] Démarré');
}

function mpStop() {
  if (_rafId) { cancelAnimationFrame(_rafId); _rafId = null; }
  const ctx = _ctx();
  const c = _$('cam-canvas');
  if (ctx && c) ctx.clearRect(0, 0, c.width, c.height);
  _canvasCtx = null;
  _facePresent = false; _presenceSince = 0;
  _lastGestureSeen = null; _lastGestureSince = 0;
  _pinchActive = false; _pinchRefY = 0;
  _twoHandRefDist = null; _fistRef = null;
  _setStatus('', null);
  console.log('[MediaPipe] Arrêté');
}

window.mpInit  = mpInit;
window.mpStart = mpStart;
window.mpStop  = mpStop;
