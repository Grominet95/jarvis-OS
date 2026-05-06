/* globe.js — Jarvis Globe v4 — Mapbox GL JS */
(function () {
  'use strict';

  // ── State ────────────────────────────────────────────────────────
  let _map = null;
  let _visible = false;
  let _mapReady = false;
  let _layersAdded = false;
  let _autoRotate = true;
  let _interacting = false;
  let _resumeTimer = null;

  let _fetchTimer = null;
  let _flightsCache = [];
  let _flightsOn = false;
  let _searchQuery = '';
  let _vesselMap = new Map();
  let _vesselOn = false;
  let _aisWs = null;
  let _aisTimer = null;

  // ── Dynamic Mapbox loader ────────────────────────────────────────
  async function _loadMapbox(token) {
    if (typeof mapboxgl !== 'undefined') { mapboxgl.accessToken = token; return; }
    await new Promise((resolve, reject) => {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = 'https://api.mapbox.com/mapbox-gl-js/v3.23.1/mapbox-gl.css';
      document.head.appendChild(link);
      const s = document.createElement('script');
      s.src = 'https://api.mapbox.com/mapbox-gl-js/v3.23.1/mapbox-gl.js';
      s.onload = () => { mapboxgl.accessToken = token; resolve(); };
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  // ── Init ─────────────────────────────────────────────────────────
  async function _init() {
    if (_map) return;

    let token = '';
    try {
      const r = await fetch('/api/globe/config');
      if (r.ok) { const cfg = await r.json(); token = cfg.mapbox_token || ''; }
    } catch { }
    if (!token) { console.warn('[Globe] MAPBOX_TOKEN absent'); return; }

    await _loadMapbox(token);

    _map = new mapboxgl.Map({
      container: 'globe-container',
      style: 'mapbox://styles/barth-95/cmosuocjv007801seho3g8r4y',
      projection: 'globe',
      zoom: 1.5,
      center: [10, 20],
      pitch: 0,
      bearing: 0,
      antialias: true,
      attributionControl: false,
    });

    _map.addControl(new mapboxgl.AttributionControl({ compact: true }), 'bottom-right');
    _map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'top-right');

    _map.on('mousedown',  () => { _interacting = true;  _map.stop(); _autoRotate = false; });
    _map.on('mouseup',    () => { _interacting = false; _scheduleResume(); });
    _map.on('touchstart', () => { _interacting = true;  _map.stop(); _autoRotate = false; });
    _map.on('touchend',   () => { _interacting = false; _scheduleResume(); });
    _map.on('wheel',      () => { _map.stop(); _autoRotate = false; _scheduleResume(); });
    _map.on('moveend',    () => { _spinGlobe(); });

    _map.on('style.load', () => {
      _map.setFog({
        color:            'rgb(6, 8, 13)',
        'high-color':     'rgb(20, 65, 150)',
        'horizon-blend':  0.04,
        'space-color':    'rgb(6, 8, 13)',
        'star-intensity': 0,
      });
      _addLayers();
      _mapReady = true;
      if (_visible) { _startData(); _spinGlobe(); }
    });
  }

  // ── Auto-rotation (pattern officiel Mapbox globe) ────────────────
  function _scheduleResume() {
    if (_resumeTimer) clearTimeout(_resumeTimer);
    _resumeTimer = setTimeout(() => { _autoRotate = true; _spinGlobe(); }, 5000);
  }

  function _spinGlobe() {
    if (!_map || !_autoRotate || _interacting || _map.getZoom() >= 4) return;
    const center = _map.getCenter();
    center.lng -= 1.5; // °/s (easeTo duration = 1000ms)
    _map.easeTo({ center, duration: 1000, easing: n => n });
  }

  function _startRotation() { _spinGlobe(); }

  function _stopRotation() {
    _autoRotate = false;
    if (_resumeTimer) { clearTimeout(_resumeTimer); _resumeTimer = null; }
    _map?.stop();
  }

  // ── GeoJSON layers ───────────────────────────────────────────────
  function _addLayers() {
    const emptyFC = { type: 'FeatureCollection', features: [] };

    _map.addSource('flights', { type: 'geojson', data: emptyFC });
    _map.addLayer({
      id: 'flights-layer', type: 'circle', source: 'flights',
      layout: { visibility: 'none' },
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 2, 4, 3.5, 10, 6],
        'circle-color': [
          'case',
          ['==', ['slice', ['get', 'callsign'], 0, 3], 'AFR'],
          '#FFD700',
          ['interpolate', ['linear'], ['get', 'alt'],
            0, '#4A9EFF', 4000, '#36D399', 8000, '#FFB547', 11000, '#FF6B4A'],
        ],
        'circle-opacity': 0.82,
        'circle-stroke-width': 0.5,
        'circle-stroke-color': 'rgba(74,158,255,0.2)',
      },
    });

    _map.addSource('vessels', { type: 'geojson', data: emptyFC });
    _map.addLayer({
      id: 'vessels-layer', type: 'circle', source: 'vessels',
      layout: { visibility: 'none' },
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 1.5, 5, 3, 10, 4],
        'circle-color': '#36D399',
        'circle-opacity': 0.7,
      },
    });

    _layersAdded = true;
  }

  // ── GeoJSON helpers ──────────────────────────────────────────────
  function _toFC(features) { return { type: 'FeatureCollection', features }; }

  function _flightsFC(flights) {
    return _toFC(flights.map(f => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [f.lon, f.lat] },
      properties: { callsign: f.callsign, alt: f.alt, speed: f.speed },
    })));
  }

  function _vesselsFC(vessels) {
    return _toFC(vessels.map(v => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [v.lon, v.lat] },
      properties: { name: v.name, mmsi: v.mmsi, speed: v.speed },
    })));
  }

  // ── Data ─────────────────────────────────────────────────────────
  function _startData() {
    _fetchAll();
    if (!_fetchTimer) _fetchTimer = setInterval(_fetchFlights, 65000);
    _connectAIS();
  }

  function _stopData() {
    if (_fetchTimer) { clearInterval(_fetchTimer); _fetchTimer = null; }
    _disconnectAIS();
  }

  async function _fetchAll() { await Promise.all([_fetchFlights(), _fetchWeather()]); }

  async function _fetchFlights() {
    const el = document.getElementById('gdp-flight-count');
    try {
      const r = await fetch('/api/globe/flights');
      if (!r.ok) throw 0;
      const d = await r.json();
      _flightsCache = d.flights || [];
      if (_layersAdded && _flightsOn)
        _map.getSource('flights')?.setData(_flightsFC(_flightsCache));
      if (el) el.textContent = d.total || _flightsCache.length;
    } catch { if (el) el.textContent = '—'; }
  }

  async function _fetchWeather() {
    try {
      const r = await fetch('/api/globe/weather');
      if (!r.ok) return;
      const { cities } = await r.json();
      Object.entries(cities).forEach(([k, c]) => {
        const t = document.getElementById(`gdp-w-${k}-temp`);
        const d = document.getElementById(`gdp-w-${k}-desc`);
        if (t) t.textContent = c.temp != null ? `${c.temp}°` : '—°';
        if (d) d.textContent = c.desc || '—';
      });
    } catch { }
  }

  // ── AISstream.io ─────────────────────────────────────────────────
  function _vesselStatus(msg) {
    const el = document.getElementById('gdp-vessel-status');
    if (el) el.textContent = msg;
  }

  function _connectAIS() {
    fetch('/api/globe/config').then(r => r.ok ? r.json() : {})
      .then(cfg => {
        if (cfg.aisstream_key) { _vesselStatus('Connexion…'); _openAIS(cfg.aisstream_key); }
        else _vesselStatus('Clé API manquante (.env)');
      }).catch(() => _vesselStatus('Erreur config'));
  }

  function _openAIS(apiKey) {
    if (_aisWs) return;
    try {
      _aisWs = new WebSocket('wss://stream.aisstream.io/v0/stream');
      _aisWs.onopen = () => {
        _vesselStatus('Connecté…');
        _aisWs.send(JSON.stringify({ APIKey: apiKey, BoundingBoxes: [[[-90, -180], [90, 180]]] }));
      };
      _aisWs.onmessage = e => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.error) { _vesselStatus(`Erreur: ${msg.error}`); return; }
          const meta = msg.MetaData || {};
          const pos = (msg.Message && msg.Message.PositionReport) || {};
          const lat = pos.Latitude ?? meta.latitude ?? null;
          const lon = pos.Longitude ?? meta.longitude ?? null;
          if (lat == null || lon == null || Math.abs(lat) > 90 || Math.abs(lon) > 180) return;
          const mmsi = String(meta.MMSI || pos.UserID || '');
          if (!mmsi) return;
          _vesselMap.set(mmsi, { lat, lon, mmsi, name: (meta.ShipName || '').trim() || mmsi, speed: pos.Sog || 0 });
        } catch { }
      };
      _aisWs.onerror = () => _vesselStatus('Erreur WebSocket');
      _aisWs.onclose = () => { _vesselStatus('Déconnecté'); _aisWs = null; };
      _aisTimer = setInterval(() => {
        if (!_visible || !_layersAdded) return;
        const vessels = [..._vesselMap.values()];
        if (_vesselOn) _map.getSource('vessels')?.setData(_vesselsFC(vessels));
        const cnt = document.getElementById('gdp-vessel-count');
        if (cnt) cnt.textContent = vessels.length;
        if (vessels.length > 0) _vesselStatus(`Live · ${vessels.length} navires`);
        else if (_aisWs?.readyState === WebSocket.OPEN) _vesselStatus('Connecté · en attente…');
      }, 2000);
    } catch { _vesselStatus('Erreur connexion'); }
  }

  function _disconnectAIS() {
    if (_aisTimer) { clearInterval(_aisTimer); _aisTimer = null; }
    if (_aisWs) { _aisWs.close(); _aisWs = null; }
    _vesselMap.clear();
  }

  // ── Toast ────────────────────────────────────────────────────────
  let _toastTimer = null;
  function _showToast(text) {
    let el = document.getElementById('globe-toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'globe-toast';
      Object.assign(el.style, {
        position: 'fixed', bottom: '80px', left: '50%', transform: 'translateX(-50%)',
        background: 'rgba(6,8,13,0.9)', border: '1px solid rgba(74,158,255,0.2)',
        color: 'rgba(220,232,255,0.7)', fontFamily: '"DM Mono",monospace', fontSize: '11px',
        letterSpacing: '.12em', padding: '6px 16px', borderRadius: '4px',
        pointerEvents: 'none', zIndex: '5000', opacity: '0', transition: 'opacity 300ms',
      });
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.style.opacity = '1';
    if (_toastTimer) clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => { el.style.opacity = '0'; }, 3000);
  }

  // ── Show / Hide ──────────────────────────────────────────────────
  async function showGlobe() {
    if (_visible) return;
    _visible = true;
    const sc = document.getElementById('three-canvas');
    const gc = document.getElementById('globe-container');
    document.getElementById('globe-toggle')?.classList.add('active');
    document.body.classList.add('globe-mode');
    if (sc) { sc.style.transition = 'opacity 350ms ease'; sc.style.opacity = '0'; sc.style.pointerEvents = 'none'; }
    if (gc) { gc.style.display = 'block'; gc.getBoundingClientRect(); gc.style.opacity = '1'; }
    await _init();
    if (_mapReady) { _map.resize(); _startData(); _startRotation(); }
  }

  function hideGlobe() {
    if (!_visible) return;
    _visible = false;
    const sc = document.getElementById('three-canvas');
    const gc = document.getElementById('globe-container');
    document.getElementById('globe-toggle')?.classList.remove('active');
    document.body.classList.remove('globe-mode');
    if (sc) { sc.style.transition = 'opacity 400ms ease 150ms'; sc.style.opacity = '1'; sc.style.pointerEvents = ''; }
    if (gc) { gc.style.opacity = '0'; setTimeout(() => { gc.style.display = 'none'; }, 400); }
    _stopRotation();
    _stopData();
  }

  function toggleGlobe() { _visible ? hideGlobe() : showGlobe(); }

  // ── Layer toggles ────────────────────────────────────────────────
  function toggleLayer() {
    _flightsOn = !_flightsOn;
    if (_layersAdded)
      _map.setLayoutProperty('flights-layer', 'visibility', _flightsOn ? 'visible' : 'none');
  }

  function toggleVessels() {
    _vesselOn = !_vesselOn;
    if (_layersAdded)
      _map.setLayoutProperty('vessels-layer', 'visibility', _vesselOn ? 'visible' : 'none');
  }

  function toggleClouds() { }

  // ── Flight search ────────────────────────────────────────────────
  function searchFlight(q) {
    _searchQuery = (q || '').trim().toUpperCase();
    if (!_layersAdded || !_searchQuery) return;
    const match = _flightsCache.find(f => (f.callsign || '').toUpperCase().includes(_searchQuery));
    if (match) {
      _map.flyTo({ center: [match.lon, match.lat], zoom: 5, duration: 2000 });
      _showToast(match.callsign);
    }
  }

  // ── Public API ───────────────────────────────────────────────────
  window.Globe = {
    toggle: toggleGlobe, show: showGlobe, hide: hideGlobe,
    toggleLayer, toggleVessels, toggleClouds, searchFlight,

    transitionToGlobe() {
      if (!_map) return;
      _autoRotate = true;
      _map.flyTo({ center: [10, 20], zoom: 1.5, duration: 1500, curve: 1.2 });
    },

    handleFlyTo(msg) {
      if (!_map) return;
      _autoRotate = false;
      _map.flyTo({ center: [msg.lon, msg.lat], zoom: msg.zoom || 10, duration: 2500, curve: 1.5 });
      if (msg.location_name) _showToast(msg.location_name);
    },

    mapZoomOut() { if (_map) _map.flyTo({ zoom: _map.getZoom() - 3, duration: 1000 }); },
    mapZoomIn() { if (_map) _map.flyTo({ zoom: _map.getZoom() + 3, duration: 1000 }); },
  };

})();
