'use strict';
// Runner de preset de briefing post-wakeup.
//
// Perf : prepareBriefing() est appelé PENDANT le wakeup — il résout le preset et
// pré-synthétise EN PARALLÈLE l'audio de tous les segments `say`. Quand le wakeup
// se termine, runBriefing() rejoue l'audio déjà prêt → enchaînement immédiat,
// plus d'attente de synthèse entre les phrases.
//
// Autonome : décodage audio inclus, aucune dépendance à wake_sequence.js. Le
// timing vit ici ; le backend ne fait que résoudre les segments (data déclarative).
(function () {
  let _prepared = null; // { presetId, segments, audio: {index -> b64} }

  function _auth() {
    return window.Jarvis && Jarvis.authHeaders ? Jarvis.authHeaders() : {};
  }

  // Synthèse TTS d'un texte -> base64 (sans jouer). Retourne null si échec.
  async function _synth(text) {
    if (!text) return null;
    try {
      const r = await fetch('/api/voice/speak', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ..._auth() },
        body: JSON.stringify({ text }),
      });
      const d = await r.json();
      return d && d.audio_b64 ? d.audio_b64 : null;
    } catch (e) { console.warn('[briefing] synth', e); return null; }
  }

  // Décode + joue un base64 audio, en ATTENDANT la fin (sinon les phrases se
  // chevauchent). Même décodage que _playBase64Audio de wake_sequence.
  async function _playB64(b64) {
    if (!b64) return;
    try {
      const raw = atob(b64);
      const buf = new Uint8Array(raw.length);
      for (let i = 0; i < raw.length; i++) buf[i] = raw.charCodeAt(i);
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const audioBuf = await ctx.decodeAudioData(buf.buffer);
      const src = ctx.createBufferSource();
      src.buffer = audioBuf;
      src.connect(ctx.destination);
      await new Promise((resolve) => { src.onended = resolve; src.start(); });
      try { ctx.close(); } catch (e) { /* déjà fermé */ }
    } catch (e) { console.warn('[briefing] audio', e); }
  }

  async function openUrl(url, bounds) {
    try {
      await fetch('/api/briefing/open-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ..._auth() },
        body: JSON.stringify({ url, bounds }),
      });
    } catch (e) { console.warn('[briefing] open', e); }
  }

  const delay = (ms) => new Promise((r) => setTimeout(r, ms));

  // ── Préchauffage (appelé PENDANT le wakeup) ─────────────────────────────────
  // Résout le preset + pré-synthétise tous les `say` en parallèle. Stocke le
  // résultat dans _prepared pour que runBriefing() enchaîne sans latence.
  window.prepareBriefing = async function (presetId = 'morning') {
    try {
      const preset = await (
        await fetch('/api/briefing/preset/' + encodeURIComponent(presetId), { headers: _auth() })
      ).json();
      if (!preset || !preset.enabled || !Array.isArray(preset.segments)) {
        _prepared = null;
        return;
      }
      const audio = {};
      await Promise.all(
        preset.segments.map(async (seg, i) => {
          if (seg.type === 'say') audio[i] = await _synth(seg.text);
        })
      );
      _prepared = { presetId, segments: preset.segments, audio };
    } catch (e) {
      console.warn('[briefing] prepare', e);
      _prepared = null;
    }
  };

  // ── Lecture (appelée à la fin du wakeup) ────────────────────────────────────
  window.runBriefing = async function (presetId = 'morning') {
    // Utilise le préchauffage si dispo ; sinon le fait à la volée (repli).
    if (!_prepared || _prepared.presetId !== presetId) {
      await window.prepareBriefing(presetId);
    }
    const prep = _prepared;
    _prepared = null; // consommé
    if (!prep) return;

    for (let i = 0; i < prep.segments.length; i++) {
      const seg = prep.segments[i];
      switch (seg.type) {
        case 'say':
          await _playB64(prep.audio[i] || (await _synth(seg.text)));
          break;
        case 'open_url':
          await openUrl(seg.url, seg.bounds);
          await delay(500);
          break;
        case 'view':
          if (window.Jarvis && Jarvis.views && Jarvis.views.activate) {
            Jarvis.views.activate(seg.view, seg.params || {});
          }
          await delay(seg.dwell_ms || 3000);
          break;
        case 'wait':
          await delay(seg.ms || 500);
          break;
      }
    }
  };
})();
