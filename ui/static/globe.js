/* globe.js — Jarvis Globe v19 — night-only — three-globe@2.24.13 + three@0.128 */
(function () {
  'use strict';

  const IMG_BASE = '//cdn.jsdelivr.net/npm/three-globe/example/img/';

  // ── State ────────────────────────────────────────────────────────
  let _globe = null, _scene, _camera, _renderer;
  let _animId = null;
  let _visible = false;
  let _autoRot = true;
  let _dragging = false;
  let _prev = { x: 0, y: 0 };
  let _mousePos = { x: 0, y: 0 };
  let _rotVelX = 0, _rotVelY = 0;
  let _targetZ = 360;
  let _lastDrag = 0;

  let _fetchTimer = null;
  let _flightsCache = [];
  let _flightsOn = true;
  let _searchQuery = '';
  let _vesselMap = new Map();
  let _vesselOn = true;
  let _aisWs = null;
  let _aisTimer = null;
  let _cloudMesh = null;
  let _cloudsOn = false;
  let _cloudDrift = 0;

  // ── Plane textures ───────────────────────────────────────────────
  let _planeTex = null, _goldTex = null;
  function _getPlaneTex() {
    if (_planeTex) return _planeTex;
    const c = document.createElement('canvas'); c.width = c.height = 64;
    const ctx = c.getContext('2d');
    ctx.font = '48px Arial'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.shadowColor = 'rgba(255,255,255,0.8)'; ctx.shadowBlur = 8;
    ctx.fillStyle = '#ffffff'; ctx.fillText('✈', 32, 32);
    _planeTex = new THREE.CanvasTexture(c); return _planeTex;
  }
  function _getGoldTex() {
    if (_goldTex) return _goldTex;
    const c = document.createElement('canvas'); c.width = c.height = 64;
    const ctx = c.getContext('2d');
    ctx.font = '48px Arial'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.shadowColor = 'rgba(255,215,0,1)'; ctx.shadowBlur = 18;
    ctx.fillStyle = '#FFD700'; ctx.fillText('✈', 32, 32);
    _goldTex = new THREE.CanvasTexture(c); return _goldTex;
  }

  // ── Event helpers ────────────────────────────────────────────────
  // Returns true if the pointer event lands on a known UI panel (not globe area)
  function _onUI(e) {
    let node = e.target;
    while (node && node !== document.documentElement) {
      const id = node.id || '';
      const cls = (typeof node.className === 'string') ? node.className : '';
      if (
        id === 'globe-toggle' ||
        id === 'globe-data-panel' ||
        id === 'globe-tooltip' ||
        cls.includes('gdp-') ||
        cls.includes('left-scroll') ||
        cls.includes('left-panel') ||
        cls.includes('right-panel') ||
        cls.includes('right-chat') ||
        cls.includes('chat-') ||
        cls.includes('music-') ||
        cls.includes('voice-') ||
        cls.includes('session-') ||
        cls.includes('skill-') ||
        cls.includes('bottom-bar') ||
        cls.includes('brand-')
      ) return true;
      node = node.parentElement;
    }
    return false;
  }

  // ── Document-level pointer events (bypass z-index issues) ────────
  // Attached once, guard-checked against _visible
  function _onPointerDown(e) {
    if (!_visible || _onUI(e)) return;
    e.preventDefault();
    _dragging = true; _autoRot = false; _lastDrag = Date.now();
    _rotVelX = 0; _rotVelY = 0;
    _prev = { x: e.clientX, y: e.clientY };
    document.body.style.cursor = 'grabbing';
    _hideTooltip();
  }
  function _onPointerMove(e) {
    if (!_visible) return;
    _mousePos = { x: e.clientX, y: e.clientY };
    if (_dragging && _globe) {
      const dx = e.clientX - _prev.x, dy = e.clientY - _prev.y;
      const vx = dx * 0.006, vy = dy * 0.006;
      _globe.rotation.y += vx;
      _globe.rotation.x = Math.max(-Math.PI / 2.2, Math.min(Math.PI / 2.2,
        _globe.rotation.x + vy));
      _rotVelY = vx * 0.75; _rotVelX = vy * 0.75;
      _prev = { x: e.clientX, y: e.clientY };
    } else if (!_onUI(e)) {
      _checkHover(e);
    }
  }
  function _onPointerUp() {
    if (!_visible || !_dragging) return;
    _dragging = false;
    document.body.style.cursor = '';
    _lastDrag = Date.now();
  }
  function _onWheel(e) {
    if (!_visible || _onUI(e)) return;
    e.preventDefault();
    _targetZ = Math.max(160, Math.min(360, _targetZ * (e.deltaY > 0 ? 1.07 : 0.93)));
  }
  function _onCtxMenu(e) {
    if (_visible && !_onUI(e)) e.preventDefault();
  }

  // Register all document-level events once at module load
  document.addEventListener('pointerdown', _onPointerDown, false);
  document.addEventListener('pointermove', _onPointerMove, false);
  document.addEventListener('pointerup', _onPointerUp, false);
  document.addEventListener('pointercancel', _onPointerUp, false);
  document.addEventListener('wheel', _onWheel, { passive: false });
  document.addEventListener('contextmenu', _onCtxMenu, false);

  // Keyboard: zoom with +/-/numpad/arrows
  window.addEventListener('keydown', e => {
    if (!_visible) return;
    if (e.key === 'Escape') { hideGlobe(); return; }
    const zIn = e.code === 'NumpadAdd' || e.keyCode === 107 ||
      e.key === '+' || e.key === '=' || e.key === 'ArrowUp';
    const zOut = e.code === 'NumpadSubtract' || e.keyCode === 109 ||
      e.key === '-' || e.key === 'ArrowDown';
    if (zIn) { e.preventDefault(); _targetZ = Math.max(160, _targetZ * 0.90); }
    if (zOut) { e.preventDefault(); _targetZ = Math.min(360, _targetZ * 1.10); }
  });

  // ── Init ─────────────────────────────────────────────────────────
  function _init() {
    if (_renderer) return;
    const GlobeClass = window.ThreeGlobe;
    if (!GlobeClass) { console.error('[Globe] ThreeGlobe not loaded'); return; }

    const canvas = document.getElementById('globe-canvas');
    const W = window.innerWidth, H = window.innerHeight;

    _renderer = new THREE.WebGLRenderer({ antialias: true, canvas, alpha: true });
    _renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    _renderer.setSize(W, H);
    _renderer.setClearColor(0x000000, 0);

    _scene = new THREE.Scene();
    _camera = new THREE.PerspectiveCamera(50, W / H, 0.1, 2000);
    _camera.position.z = _targetZ;

    _scene.add(new THREE.AmbientLight(0xffffff, 2.5));

    _globe = new GlobeClass()
      .globeImageUrl(IMG_BASE + 'earth-night.jpg')
      .atmosphereColor('#1a3a6a')
      .atmosphereAltitude(0.12)
      .showGraticules(true)
      .customLayerData([])
      .customThreeObject(_makeFlightSprite)
      .customThreeObjectUpdate(_updateFlightSprite)
      .pointsData([])
      .pointLat('lat').pointLng('lon')
      .pointColor(() => '#B8963E')
      .pointAltitude(0.003).pointRadius(0.25)
      .labelsData([])
      .labelLat('lat').labelLng('lng')
      .labelText('label').labelColor('color')
      .labelSize(0.55).labelDotRadius(0.40).labelAltitude(0.014);

    _globe.onGlobeReady(() => {
      const mat = _globe.globeMaterial();
      mat.emissiveMap = mat.map;
      mat.emissive = new THREE.Color(1, 1, 1);
      mat.emissiveIntensity = 0.92;
      mat.color = new THREE.Color(0.08, 0.08, 0.12);
      mat.shininess = 0;
      mat.needsUpdate = true;

      _globe.traverse(obj => {
        if (obj.isLineSegments && obj.material) {
          obj.material.color = new THREE.Color(0x4A9EFF);
          obj.material.opacity = 0.04;
          obj.material.transparent = true;
          obj.material.needsUpdate = true;
        }
      });
      _loadClouds();
    });

    _scene.add(_globe);
  }

  // ── Cloud layer ───────────────────────────────────────────────────
  function _makeProceduralClouds() {
    const W = 2048, H = 1024;
    const cvs = document.createElement('canvas');
    cvs.width = W; cvs.height = H;
    const ctx = cvs.getContext('2d');

    const blob = (x, y, r, op) => {
      x = ((x % W) + W) % W;
      const g = ctx.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, `rgba(255,255,255,${Math.min(op, 1)})`);
      g.addColorStop(0.4, `rgba(255,255,255,${Math.min(op * 0.7, 1)})`);
      g.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    };

    // Storm systems
    for (let i = 0; i < 35; i++) {
      const cx = Math.random() * W, cy = (0.05 + Math.random() * 0.9) * H;
      const sr = 40 + Math.random() * 90;
      blob(cx, cy, sr * 0.5, 0.95);
      for (let j = 0; j < 22; j++) {
        const a = (j / 22) * Math.PI * 2;
        const d = sr * (0.4 + Math.random() * 0.6);
        blob(cx + Math.cos(a) * d, cy + Math.sin(a) * d * 0.65,
          20 + Math.random() * 45, 0.6 + Math.random() * 0.35);
      }
    }
    // Frontal bands
    for (let i = 0; i < 12; i++) {
      const sx = Math.random() * W, sy = (0.08 + Math.random() * 0.84) * H;
      const len = 300 + Math.random() * 600;
      const ang = (Math.random() - 0.5) * Math.PI * 0.55;
      const n = 70 + Math.floor(Math.random() * 50);
      for (let j = 0; j < n; j++) {
        const t = j / n;
        blob(sx + Math.cos(ang) * t * len + (Math.random() - 0.5) * 40,
          sy + Math.sin(ang) * t * len + (Math.random() - 0.5) * 25,
          18 + Math.random() * 38, 0.45 + Math.random() * 0.45);
      }
    }
    // Scattered cells
    for (let i = 0; i < 1200; i++)
      blob(Math.random() * W, Math.random() * H, 10 + Math.random() * 35, 0.20 + Math.random() * 0.35);
    // Haze
    for (let i = 0; i < 200; i++)
      blob(Math.random() * W, Math.random() * H, 60 + Math.random() * 120, 0.08 + Math.random() * 0.12);

    const tex = new THREE.CanvasTexture(cvs); tex.needsUpdate = true;
    return tex;
  }

  function _buildCloudMesh(tex) {
    if (_cloudMesh) { _cloudMesh.material.map = tex; _cloudMesh.material.needsUpdate = true; return; }
    _cloudMesh = new THREE.Mesh(
      new THREE.SphereGeometry(102, 64, 64),
      new THREE.MeshPhongMaterial({
        map: tex, transparent: true, opacity: 0.95,
        depthWrite: false, blending: THREE.AdditiveBlending,
      }),
    );
    _cloudMesh.visible = _cloudsOn;
    _scene.add(_cloudMesh);
  }

  function _loadClouds() {
    _buildCloudMesh(_makeProceduralClouds());
    new THREE.TextureLoader().load(IMG_BASE + 'earth-clouds.png', tex => {
      if (_cloudMesh) { _cloudMesh.material.map = tex; _cloudMesh.material.needsUpdate = true; }
    });
  }

  // ── Flight sprites ───────────────────────────────────────────────
  function _makeFlightSprite() {
    const s = new THREE.Sprite(new THREE.SpriteMaterial({
      map: _getPlaneTex(), transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending,
    }));
    s.scale.set(3, 3, 1); return s;
  }
  function _updateFlightSprite(obj, d) {
    const altFrac = 0.005 + Math.min(Math.max(d.alt, 0) / 15000, 1) * 0.07;
    const c = _globe.getCoords(d.lat, d.lng, altFrac);
    obj.position.set(c.x, c.y, c.z);
    obj.material.rotation = ((d.heading || 0) - 90) * Math.PI / 180;
    const matched = _searchQuery && (d.callsign || '').toUpperCase().includes(_searchQuery.toUpperCase());
    obj.material.map = matched ? _getGoldTex() : _getPlaneTex();
    obj.scale.set(matched ? 9 : 3, matched ? 9 : 3, 1);
    obj.material.needsUpdate = true;
  }

  // ── Tooltip ──────────────────────────────────────────────────────
  const _v3 = new THREE.Vector3();
  function _checkHover(e) {
    if (!_globe || !_camera || !_flightsCache.length || !_flightsOn) return;
    const canvas = document.getElementById('globe-canvas');
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const W = rect.width, H = rect.height;
    let best = 22, found = null;
    for (const f of _flightsCache) {
      const af = 0.005 + Math.min(Math.max(f.alt, 0) / 15000, 1) * 0.07;
      const c = _globe.getCoords(f.lat, f.lng, af);
      _v3.set(c.x, c.y, c.z).applyMatrix4(_globe.matrixWorld);
      _v3.project(_camera);
      if (_v3.z > 1) continue;
      const d = Math.hypot((_v3.x + 1) * W / 2 - mx, (-_v3.y + 1) * H / 2 - my);
      if (d < best) { best = d; found = f; }
    }
    found ? _showTooltip(found) : _hideTooltip();
  }
  function _showTooltip(d) {
    const el = document.getElementById('globe-tooltip');
    if (!el) return;
    el.innerHTML = `✈ <b>${_esc(d.callsign || '—')}</b><br>`
      + `${_esc(d.country || '—')} · ${d.alt || 0} m · ${d.speed || 0} km/h`;
    el.style.left = (_mousePos.x + 14) + 'px';
    el.style.top = (_mousePos.y - 10) + 'px';
    el.classList.add('visible');
  }
  function _hideTooltip() {
    const el = document.getElementById('globe-tooltip');
    if (el) el.classList.remove('visible');
  }

  // ── Toggles ──────────────────────────────────────────────────────
  function toggleLayer(name) {
    if (name !== 'flights') return;
    _flightsOn = !_flightsOn;
    if (_globe) _globe.customLayerData(_flightsOn ? _flightsCache : []);
    if (!_flightsOn) _hideTooltip();
  }
  function toggleVessels() {
    _vesselOn = !_vesselOn;
    if (_globe) _globe.pointsData(_vesselOn ? [..._vesselMap.values()] : []);
  }
  function toggleClouds() {
    _cloudsOn = !_cloudsOn;
    if (_cloudMesh) _cloudMesh.visible = _cloudsOn;
  }

  // ── Render loop ──────────────────────────────────────────────────
  function _loop() {
    if (!_visible) return;
    _animId = requestAnimationFrame(_loop);

    // Smooth zoom lerp
    const dz = _targetZ - _camera.position.z;
    if (Math.abs(dz) > 0.05) _camera.position.z += dz * 0.10;

    if (_autoRot && _globe) {
      _globe.rotation.y += 0.0008;
    } else if (_globe && !_dragging) {
      if (Math.abs(_rotVelY) > 0.00004 || Math.abs(_rotVelX) > 0.00004) {
        _globe.rotation.y += _rotVelY;
        _globe.rotation.x = Math.max(-Math.PI / 2, Math.min(Math.PI / 2,
          _globe.rotation.x + _rotVelX));
        _rotVelY *= 0.94; _rotVelX *= 0.94;
      } else if (Date.now() - _lastDrag > 8000) {
        _autoRot = true; _rotVelX = 0; _rotVelY = 0;
      }
    }

    if (_cloudMesh) {
      _cloudDrift += 0.00012;
      _cloudMesh.rotation.x = _globe.rotation.x;
      _cloudMesh.rotation.y = _globe.rotation.y + _cloudDrift;
    }

    _renderer.render(_scene, _camera);
  }

  // ── Data ─────────────────────────────────────────────────────────
  function _startData() {
    _fetchAll();
    if (!_fetchTimer) _fetchTimer = setInterval(_fetchFlights, 65000);
    _connectAIS();
  }
  function _stopData() {
    if (_fetchTimer) { clearInterval(_fetchTimer); _fetchTimer = null; }
    if (_aisTimer) { clearInterval(_aisTimer); _aisTimer = null; }
    if (_globe) { _globe.customLayerData([]); _globe.pointsData([]); _globe.labelsData([]); }
    _hideTooltip(); _flightsCache = []; _disconnectAIS();
  }
  async function _fetchAll() { await Promise.all([_fetchFlights(), _fetchWeather()]); }

  async function _fetchFlights() {
    const el = document.getElementById('gdp-flight-count');
    try {
      const r = await fetch('/api/globe/flights');
      if (!r.ok) throw 0;
      const d = await r.json();
      _flightsCache = (d.flights || []).map(f => ({
        lat: f.lat, lng: f.lon, callsign: f.callsign || '—',
        country: f.country || '—', alt: f.alt || 0, speed: f.speed || 0, heading: f.heading || 0,
      }));
      if (_globe && _flightsOn) _globe.customLayerData(_flightsCache);
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
      if (_globe) _globe.labelsData(
        Object.values(cities).filter(c => c.lat != null).map(c => ({
          lat: c.lat, lng: c.lon,
          label: c.temp != null ? `${c.temp}°` : '—°',
          color: _tempColor(c.temp),
        }))
      );
    } catch { }
  }
  function _tempColor(t) {
    if (t == null) return '#4A9EFF'; if (t < 0) return '#88CCFF';
    if (t < 15) return '#4A9EFF'; if (t < 25) return '#36D399';
    if (t < 35) return '#FFB547'; return '#FF4D4D';
  }

  // ── AISstream.io ─────────────────────────────────────────────────
  function _setVesselStatus(msg) {
    const el = document.getElementById('gdp-vessel-status'); if (el) el.textContent = msg;
  }
  function _connectAIS() {
    fetch('/api/globe/config').then(r => r.ok ? r.json() : {})
      .then(cfg => {
        if (cfg.aisstream_key) { _setVesselStatus('Connexion…'); _openAIS(cfg.aisstream_key); }
        else _setVesselStatus('Clé API manquante (.env)');
      }).catch(() => _setVesselStatus('Erreur config'));
  }
  function _openAIS(apiKey) {
    if (_aisWs) return;
    try {
      _aisWs = new WebSocket('wss://stream.aisstream.io/v0/stream');
      _aisWs.onopen = () => {
        _setVesselStatus('Connecté…');
        _aisWs.send(JSON.stringify({ APIKey: apiKey, BoundingBoxes: [[[-90, -180], [90, 180]]] }));
      };
      _aisWs.onmessage = e => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.error) { _setVesselStatus(`Erreur: ${msg.error}`); return; }
          const meta = msg.MetaData || {};
          const pos = (msg.Message && msg.Message.PositionReport) || {};
          const lat = pos.Latitude ?? meta.latitude ?? null;
          const lon = pos.Longitude ?? meta.longitude ?? null;
          if (lat == null || lon == null) return;
          if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return;
          const mmsi = String(meta.MMSI || pos.UserID || '');
          if (!mmsi) return;
          _vesselMap.set(mmsi, {
            lat, lon, mmsi,
            name: (meta.ShipName || '').trim() || mmsi, speed: pos.Sog || 0
          });
        } catch { }
      };
      _aisWs.onerror = () => _setVesselStatus('Erreur WebSocket');
      _aisWs.onclose = () => { _setVesselStatus('Déconnecté'); _aisWs = null; };
      _aisTimer = setInterval(() => {
        if (!_globe || !_visible) return;
        const vessels = [..._vesselMap.values()];
        if (_vesselOn) _globe.pointsData(vessels);
        const cnt = document.getElementById('gdp-vessel-count');
        if (cnt) cnt.textContent = vessels.length;
        if (vessels.length > 0) _setVesselStatus(`Live · ${vessels.length} navires`);
        else if (_aisWs?.readyState === WebSocket.OPEN) _setVesselStatus('Connecté · en attente…');
      }, 2000);
    } catch { _setVesselStatus('Erreur connexion'); }
  }
  function _disconnectAIS() {
    if (_aisTimer) { clearInterval(_aisTimer); _aisTimer = null; }
    if (_aisWs) { _aisWs.close(); _aisWs = null; }
    _vesselMap.clear();
  }

  // ── Show / Hide ──────────────────────────────────────────────────
  function showGlobe() {
    if (_visible) return; _visible = true;
    const sc = document.getElementById('three-canvas');
    const gc = document.getElementById('globe-canvas');
    document.getElementById('globe-toggle').classList.add('active');
    document.body.classList.add('globe-mode');
    if (sc) { sc.style.pointerEvents = 'none'; sc.style.transition = 'opacity 350ms ease'; sc.style.opacity = '0'; }
    gc.style.display = 'block'; gc.getBoundingClientRect(); gc.style.opacity = '1';
    _init(); _loop(); _startData();
  }
  function hideGlobe() {
    if (!_visible) return;
    _dragging = false; document.body.style.cursor = '';
    const sc = document.getElementById('three-canvas');
    const gc = document.getElementById('globe-canvas');
    document.getElementById('globe-toggle').classList.remove('active');
    document.body.classList.remove('globe-mode');
    if (sc) { sc.style.pointerEvents = ''; sc.style.transition = 'opacity 400ms ease 150ms'; sc.style.opacity = '1'; }
    gc.style.opacity = '0';
    setTimeout(() => {
      gc.style.display = 'none'; _visible = false;
      if (_animId) { cancelAnimationFrame(_animId); _animId = null; }
    }, 400);
    _stopData();
  }
  function toggleGlobe() { _visible ? hideGlobe() : showGlobe(); }

  window.addEventListener('resize', () => {
    if (!_renderer || !_camera) return;
    const W = window.innerWidth, H = window.innerHeight;
    _camera.aspect = W / H; _camera.updateProjectionMatrix(); _renderer.setSize(W, H);
  });

  // ── Flight search ────────────────────────────────────────────────
  function searchFlight(q) {
    _searchQuery = (q || '').trim();
    if (_globe && _flightsOn && _flightsCache.length) _globe.customLayerData([..._flightsCache]);
    if (_searchQuery) {
      const m = _flightsCache.find(f => (f.callsign || '').toUpperCase().includes(_searchQuery.toUpperCase()));
      m ? _showTooltip(m) : _hideTooltip();
    } else { _hideTooltip(); }
  }

  function _esc(s) {
    return String(s).replace(/[&<>"']/g,
      c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  window.Globe = {
    toggle: toggleGlobe, show: showGlobe, hide: hideGlobe,
    toggleLayer, toggleVessels, toggleClouds, searchFlight,
  };
})();
