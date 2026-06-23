'use strict';
// ═════════════════════════════════════════════════════════════════════════════
//  Gesture Router — couche d'entrée gestuelle de Jarvis OS.
//  MediaPipe (et demain macropad, gamepad, voix…) émettent des ÉVÉNEMENTS NEUTRES.
//  Le routeur décide du SENS selon la vue active, sinon retombe sur le mapping
//  global (musique / assistant). Aucune connaissance de Spotify ni du globe ici :
//  uniquement de la résolution name → commande.
// ═════════════════════════════════════════════════════════════════════════════
(function () {
  if (!window.Jarvis) return;
  const Views = Jarvis.views;

  // Normalise un binding (string | fn | objet) en descripteur exécutable.
  function resolve(binding, ev) {
    if (typeof binding === 'function') return { type: 'view', command: binding(ev.delta) };
    if (typeof binding === 'string')   return { type: 'view', command: binding };
    return binding || null;
  }

  function sendWs(extra, ev) {
    window._jarvisWsSend?.({
      type: 'vision_event',
      session_id: window._jarvisSessionId?.(),
      ...extra,
      ...(ev.delta !== undefined ? { delta: ev.delta } : {}),
    });
  }

  // Exécute un binding résolu. Retourne true si traité.
  function apply(b, viewId, ev) {
    if (!b) return false;
    switch (b.type) {
      case 'view':
        if (!viewId || !b.command) return false;
        Views.dispatch(viewId, b.command, {
          delta: ev.delta, dx: ev.dx, dy: ev.dy,
          axis: ev.axis, confidence: ev.confidence, phase: ev.phase,
        });
        return true;
      case 'hide':
        if (!viewId) return false;
        Views.deactivate(viewId);
        return true;
      case 'llm':
        // Reproduit la bulle de chat de l'ancien comportement LLM.
        if (b.label && typeof window.addMsg === 'function') window.addMsg('vous', '/ ' + b.label);
        sendWs({ event: 'gesture', gesture: b.gesture }, ev);
        return true;
      case 'ws':
        sendWs({ event: b.event, ...(b.gesture ? { gesture: b.gesture } : {}) }, ev);
        return true;
      default:
        return false;
    }
  }

  Jarvis.gestures = {
    _global: {},

    // Fusionne des bindings globaux (fallback hors vue).
    registerGlobal(map) { Object.assign(this._global, map || {}); },

    // POINT D'ENTRÉE UNIQUE de toute source gestuelle.
    route(ev) {
      if (!ev || !ev.name) return false;
      const viewId  = Views?._active || null;
      const viewMap = viewId ? Views._registry?.[viewId]?.gestures : null;

      // 1) la vue active capte-t-elle ce geste ?
      if (viewMap && viewMap[ev.name] != null && apply(resolve(viewMap[ev.name], ev), viewId, ev)) {
        return true;
      }
      // 2) fallback global (musique / assistant)
      const g = this._global[ev.name];
      return g != null ? apply(resolve(g, ev), viewId, ev) : false;
    },
  };
})();
