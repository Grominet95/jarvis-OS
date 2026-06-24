/**
 * Vue Globe — jarvis-skills
 * Enregistre la vue "globe" dans Jarvis.views.
 * Dépend de : _shared.js (Jarvis.views), Mapbox GL JS (chargé dynamiquement)
 */
(function () {
  if (!window.Jarvis?.views) return;

  const VIEW_ID = 'globe';
  const MAPBOX_VERSION = '3.23.1';
  const MAPBOX_CDN = `https://api.mapbox.com/mapbox-gl-js/v${MAPBOX_VERSION}`;
  const MAPBOX_STYLE = 'mapbox://styles/barth-95/cmosuocjv007801seho3g8r4y';

  let map = null;
  let rotationTimer = null;
  let container = null;
  let toastTimer = null;
  let autoRotateOn = false;
  let mapReady = false;      // true une fois map.on('load') passé
  let pendingCmds = [];      // commandes reçues avant que la carte soit prête

  // ── Helpers ───────────────────────────────────────────────────────────────

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      if (document.querySelector(`script[src="${src}"]`)) return resolve();
      const s = document.createElement('script');
      s.src = src;
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  function loadStyle(href) {
    if (document.querySelector(`link[href="${href}"]`)) return;
    const l = document.createElement('link');
    l.rel = 'stylesheet';
    l.href = href;
    document.head.appendChild(l);
  }

  async function loadMapbox() {
    loadStyle(`${MAPBOX_CDN}/mapbox-gl.css`);
    await loadScript(`${MAPBOX_CDN}/mapbox-gl.js`);
  }

  async function fetchToken() {
    const res = await fetch('/api/globe/config');
    if (!res.ok) throw new Error('globe config unavailable');
    const data = await res.json();
    return data.mapbox_token || data.token;
  }

  function showToast(msg) {
    clearTimeout(toastTimer);
    let toast = container.querySelector('.globe-toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.className = 'globe-toast';
      Object.assign(toast.style, {
        position: 'absolute',
        bottom: '32px',
        left: '50%',
        transform: 'translateX(-50%)',
        background: 'var(--bg-0, rgba(14,14,14,.85))',
        color: 'var(--fg-1, #e8e8e8)',
        border: '1px solid var(--line-1, rgba(255,255,255,.08))',
        backdropFilter: 'blur(8px)',
        padding: '8px 20px',
        borderRadius: '999px',
        fontSize: '13px',
        letterSpacing: '.03em',
        pointerEvents: 'none',
        zIndex: '3',
        opacity: '0',
        transition: 'opacity .2s',
      });
      container.appendChild(toast);
    }
    toast.textContent = msg;
    toast.style.opacity = '1';
    toastTimer = setTimeout(() => { toast.style.opacity = '0'; }, 3000);
  }

  function startAutoRotation() {
    stopAutoRotation();
    autoRotateOn = true;
    rotationTimer = setInterval(() => {
      if (!map) return;
      map.setBearing((map.getBearing() + 0.1) % 360);
    }, 16);
  }

  function stopAutoRotation() {
    clearInterval(rotationTimer);
    rotationTimer = null;
    autoRotateOn = false;
  }

  function ensureContainer() {
    if (container) return container;
    container = document.createElement('div');
    container.id = `${VIEW_ID}-container`;
    Object.assign(container.style, {
      position: 'fixed',
      inset: '0',
      zIndex: '2',
      background: 'var(--bg-0, #0e0e0e)',
      opacity: '0',
      transition: 'opacity .35s ease',
      display: 'none',
    });
    document.body.appendChild(container);
    return container;
  }

  // ── Command execution ──────────────────────────────────────────────────────
  // Exécution réelle d'une commande (carte supposée prête). Le routage / la mise
  // en file est gérée par la méthode command() ci-dessous.

  function runCommand(cmd, params = {}) {
    switch (cmd) {
      case 'fly_to': {
        if (!map) return;
        stopAutoRotation();
        const lat = params.lat ?? null;
        const lon = params.lon ?? null;
        const zoom = params.zoom ?? 4;
        const label = params.location_name || params.location || '';

        if (lat !== null && lon !== null) {
          map.flyTo({ center: [lon, lat], zoom, duration: 2500, essential: true });
        } else if (typeof params.location === 'string') {
          // location can be "lat,lon" fallback
          const parts = params.location.split(',').map(Number);
          if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
            map.flyTo({ center: [parts[1], parts[0]], zoom, duration: 2500, essential: true });
          }
        }
        if (label) showToast(label);
        break;
      }

      case 'zoom_in': {
        if (!map) return;
        map.flyTo({ zoom: map.getZoom() + 3, duration: 800, essential: true });
        break;
      }

      case 'zoom_out': {
        if (!map) return;
        map.flyTo({ zoom: Math.max(0, map.getZoom() - 3), duration: 800, essential: true });
        break;
      }

      case 'globe_view': {
        if (!map) return;
        stopAutoRotation();
        map.flyTo({ center: [10, 20], zoom: 1.5, duration: 2000, essential: true });
        map.once('moveend', startAutoRotation);
        break;
      }

      case 'zoom_by': {
        if (!map) return;
        stopAutoRotation();
        const delta = Number(params.delta || 0);          // ± (alimenté par two_hand_zoom)
        const next = Math.max(0, Math.min(22, map.getZoom() + delta * 0.04));
        map.easeTo({ zoom: next, duration: 0, essential: true });   // instantané (était 90 ms)
        break;
      }

      case 'pan_by': {
        if (!map) return;
        stopAutoRotation();
        const SENS = 2.5;                            // gain de navigation — ↑ = plus sensible
        const dx =  Number(params.dx || 0) * SENS;
        const dy = -Number(params.dy || 0) * SENS;   // ⟵ corrige l'inversion verticale
        map.panBy([dx, dy], { duration: 0 });        // pan INSTANTANÉ : 1:1, précis (fini le lag 90 ms)
        break;
      }

      case 'toggle_rotation': {
        if (!map) return;
        autoRotateOn ? stopAutoRotation() : startAutoRotation();
        break;
      }

      // Unknown commands are silently ignored
    }
  }

  // ── View registration ─────────────────────────────────────────────────────

  Jarvis.views.register(VIEW_ID, {
    meta: {
      name: 'Globe',
      desc: 'Globe terrestre interactif avec navigation vocale',
      glyph: 'GLB',
      tags: ['geo', 'realtime', 'map', 'globe'],
    },

    // Bindings gestuels lus par le routeur jarvis-OS quand la vue a le focus.
    // Clé = geste standard (vocabulaire jarvis-OS), valeur = commande ou action.
    gestures: {
      two_hand_zoom: 'zoom_by',          // continu — delta (mains qui s'écartent/rapprochent)
      fist_pan:      'pan_by',           // continu — dx, dy (poing déplacé)
      Open_Palm:     'toggle_rotation',  // discret
      Victory:       'globe_view',       // discret — réutilise la commande existante
      Thumb_Down:    { type: 'hide' },   // discret — ferme la vue
      // pinch_y volontairement non bindé ici → retombe sur le volume global (jarvis-OS)
    },

    async show(params = {}) {
      ensureContainer();

      // Already visible — skip
      if (container.style.display !== 'none') return;

      container.style.display = 'block';
      // Force reflow before opacity transition
      container.getBoundingClientRect();
      container.style.opacity = '1';

      if (map) {
        startAutoRotation();
        return;
      }

      try {
        await loadMapbox();
        const token = await fetchToken();
        mapboxgl.accessToken = token;

        const mapEl = document.createElement('div');
        mapEl.style.cssText = 'width:100%;height:100%;';
        container.appendChild(mapEl);

        map = new mapboxgl.Map({
          container: mapEl,
          style: MAPBOX_STYLE,
          projection: 'globe',
          center: [10, 20],
          zoom: 1.5,
          fadeDuration: 0,
        });

        map.on('load', () => {
          map.setFog({
            color: 'rgb(4, 4, 14)',
            'high-color': 'rgb(10, 10, 40)',
            'horizon-blend': 0.02,
            'space-color': 'rgb(4, 4, 14)',
            'star-intensity': 0.8,
          });
          startAutoRotation();

          // Carte prête : vider la file des commandes reçues pendant le chargement
          // (ex. « montre Paris » au tout premier affichage à froid).
          mapReady = true;
          const queued = pendingCmds;
          pendingCmds = [];
          queued.forEach(({ cmd, params }) => runCommand(cmd, params));
        });

        // Stop rotation while user interacts
        map.on('mousedown', stopAutoRotation);
        map.on('touchstart', stopAutoRotation);
        map.on('mouseup', startAutoRotation);
        map.on('touchend', startAutoRotation);

      } catch (err) {
        container.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--fg-1,#e8e8e8);font-family:monospace;font-size:13px;">${err.message}</div>`;
      }
    },

    hide() {
      if (!container) return;
      container.style.opacity = '0';
      stopAutoRotation();
      // Jeter les commandes encore en file (cas d'un masquage pendant un chargement
      // à froid interrompu). On NE remet PAS mapReady à false : la carte n'est pas
      // détruite ici (show() la réutilise sans relancer 'load'), donc la repasser à
      // false bloquerait définitivement les commandes au prochain affichage.
      pendingCmds = [];
      setTimeout(() => {
        if (container) container.style.display = 'none';
      }, 360);
    },

    command(cmd, params = {}) {
      // Carte pas encore prête → mettre en file (sauf globe_view, applicable même
      // pendant le chargement). Vidée par le handler map.on('load').
      if (!mapReady && cmd !== 'globe_view') {
        pendingCmds.push({ cmd, params });
        return;
      }
      runCommand(cmd, params);
    },
  });
})();
