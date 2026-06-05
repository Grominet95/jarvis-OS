/**
 * Vue Weather — jarvis-skills
 * Météo / Climat — parti pris « Plein ciel » : une scène météo animée (Canvas)
 * occupe tout l'écran ; température géante en bas-gauche, bandeau de prévisions
 * horaires en bas, widget « Conditions » (ressenti, vent, humidité, visibilité)
 * en haut-droite. Données réelles via Open-Meteo (gratuit, sans clé API).
 *
 * Dépend de : _shared.js (Jarvis.views doit être chargé avant ce fichier).
 * Chrome commun injecté via <style> partagé idempotent (#jx-chrome-css).
 */
(function () {
  if (!window.Jarvis?.views) return;

  const VIEW_ID = 'weather';
  const STYLE_ID = 'weather-css';

  /* ─── CHROME PARTAGÉ (identique sur les 4 vues) ─────────────────────────── */
  const JX_CHROME_CSS_ID = 'jx-chrome-css';
  const JX_CHROME_CSS = `
    .jx-chrome { position:absolute; inset:0; z-index:6; pointer-events:none; font-family:var(--sans,"Geist",system-ui,sans-serif); }
    .jx-chrome > * { pointer-events:auto; }
    .jx-brand { position:absolute; top:28px; left:32px; display:flex; align-items:center; gap:12px; }
    .jx-brand svg { display:block; flex-shrink:0; }
    .jx-brand-txt { display:flex; flex-direction:column; gap:4px; line-height:1; }
    .jx-brand-word { font-family:var(--display-mark,"Landasans",var(--serif,"Geist")); font-weight:500; font-size:14px; letter-spacing:.22em; color:var(--fg-0,#DCE8FF); }
    .jx-brand-status { font-family:var(--mono,"Geist Mono",monospace); font-size:9px; letter-spacing:.14em; text-transform:uppercase; color:var(--fg-3,rgba(220,232,255,.4)); display:flex; align-items:center; gap:6px; }
    .jx-brand-status::before { content:""; width:4px; height:4px; border-radius:50%; background:var(--green,#36D399); box-shadow:0 0 5px var(--green,#36D399); }
    .jx-eyebrow { position:absolute; top:30px; left:50%; transform:translateX(-50%); display:flex; align-items:center; gap:10px; font-family:var(--mono,monospace); font-size:10px; letter-spacing:.2em; text-transform:uppercase; color:var(--fg-2,rgba(220,232,255,.58)); white-space:nowrap; }
    .jx-eyebrow .vn { color:var(--accent,#4A9EFF); }
    .jx-eyebrow .sep { color:var(--fg-4,rgba(220,232,255,.22)); }
    .jx-context { position:absolute; top:28px; right:32px; display:flex; align-items:center; gap:14px; font-family:var(--mono,monospace); font-size:10.5px; letter-spacing:.06em; color:var(--fg-2,rgba(220,232,255,.58)); font-variant-numeric:tabular-nums; }
    .jx-context .sep { width:1px; height:11px; background:var(--line-2,rgba(220,232,255,.1)); }
    .jx-context .muted { color:var(--fg-3,rgba(220,232,255,.4)); letter-spacing:.12em; text-transform:uppercase; font-size:9.5px; }
    .jx-voice { position:absolute; bottom:26px; left:50%; transform:translateX(-50%); display:flex; align-items:center; gap:10px; padding:7px 14px 7px 12px; border-radius:999px; background:rgba(6,8,13,.62); border:1px solid var(--line-2,rgba(220,232,255,.1)); backdrop-filter:blur(14px) saturate(140%); -webkit-backdrop-filter:blur(14px) saturate(140%); }
    .jx-voice .vbars { display:flex; align-items:center; gap:2px; height:14px; }
    .jx-voice .vbars i { width:2px; border-radius:1px; background:var(--accent,#4A9EFF); box-shadow:0 0 5px var(--accent,#4A9EFF); animation:jx-vbar 1s ease-in-out infinite; }
    .jx-voice .vbars i:nth-child(1){ height:5px; animation-delay:0s; }
    .jx-voice .vbars i:nth-child(2){ height:11px; animation-delay:.12s; }
    .jx-voice .vbars i:nth-child(3){ height:7px; animation-delay:.24s; }
    .jx-voice .vbars i:nth-child(4){ height:13px; animation-delay:.36s; }
    .jx-voice .vbars i:nth-child(5){ height:6px; animation-delay:.48s; }
    @keyframes jx-vbar { 0%,100%{ transform:scaleY(.5); opacity:.6; } 50%{ transform:scaleY(1); opacity:1; } }
    .jx-voice .vtxt { font-family:var(--mono,monospace); font-size:10px; letter-spacing:.08em; color:var(--fg-1,rgba(220,232,255,.78)); }
    .jx-voice .vtxt b { color:var(--fg-0,#DCE8FF); font-weight:500; }
    .jx-navhint { position:absolute; bottom:28px; right:32px; display:flex; align-items:center; gap:14px; font-family:var(--mono,monospace); font-size:9.5px; letter-spacing:.08em; color:var(--fg-3,rgba(220,232,255,.4)); }
    .jx-navhint b { color:var(--fg-1,rgba(220,232,255,.78)); font-weight:400; }
    .jx-navhint .k { border:1px solid var(--line-2,rgba(220,232,255,.1)); border-radius:3px; padding:1px 5px; color:var(--fg-2,rgba(220,232,255,.58)); }
    .jx-badge { display:inline-flex; align-items:center; gap:6px; font-family:var(--mono,monospace); font-size:9.5px; letter-spacing:.12em; text-transform:uppercase; padding:3px 7px; border-radius:var(--r-1,4px); border:1px solid var(--line-2,rgba(220,232,255,.1)); color:var(--fg-2,rgba(220,232,255,.58)); }
    .jx-badge.green  { color:var(--green,#36D399); border-color:rgba(54,211,153,.32); background:var(--green-soft,rgba(54,211,153,.1)); }
    .jx-badge.accent { color:var(--accent,#4A9EFF); border-color:var(--accent-line,rgba(74,158,255,.3)); background:var(--accent-soft,rgba(74,158,255,.1)); }
    .jx-badge.gold   { color:var(--gold,#B8963E); border-color:rgba(184,150,62,.32); background:var(--gold-soft,rgba(184,150,62,.1)); }
    .jx-badge .dot { width:5px; height:5px; border-radius:50%; background:currentColor; }
  `;
  function jxEnsureChromeCss() {
    if (document.getElementById(JX_CHROME_CSS_ID)) return;
    const s = document.createElement('style');
    s.id = JX_CHROME_CSS_ID; s.textContent = JX_CHROME_CSS;
    document.head.appendChild(s);
  }
  function jxBrandMark(size) {
    return `<svg width="${size}" height="${size}" viewBox="0 0 26 26" aria-hidden="true">
      <circle cx="13" cy="13" r="10.5" fill="none" stroke="var(--accent,#4A9EFF)" stroke-width="1"/>
      <circle cx="13" cy="13" r="6.5" fill="none" stroke="var(--accent,#4A9EFF)" stroke-width="1" opacity=".55"/>
      <circle cx="13" cy="13" r="2" fill="var(--accent,#4A9EFF)"/></svg>`;
  }
  function jxBuildChrome(opts) {
    const c = document.createElement('div');
    c.className = 'jx-chrome';
    c.innerHTML = `
      ${opts.context ? `<div class="jx-context">${opts.context.map((x, i) =>
        (i ? '<span class="sep"></span>' : '') + `<span class="${x.muted ? 'muted' : ''}">${x.t}</span>`).join('')}</div>` : ''}
      ${opts.nav ? `<div class="jx-navhint">${opts.nav}</div>` : ''}
    `;
    return c;
  }

  /* ─── Données : Open-Meteo + mapping WMO ────────────────────────────────── */
  const GEO_URL = 'https://geocoding-api.open-meteo.com/v1/search';
  const FC_URL = 'https://api.open-meteo.com/v1/forecast';

  // code WMO → { scene, label }
  function wmo(code, isDay) {
    const c = Number(code);
    const night = !isDay;
    if (c === 0) return { scene: night ? 'night' : 'clear', label: night ? 'Ciel clair' : 'Dégagé' };
    if (c === 1) return { scene: night ? 'night' : 'clear', label: 'Plutôt dégagé' };
    if (c === 2) return { scene: 'clouds', label: 'Partiellement nuageux' };
    if (c === 3) return { scene: 'clouds', label: 'Couvert' };
    if (c === 45 || c === 48) return { scene: 'clouds', label: 'Brouillard' };
    if (c >= 51 && c <= 57) return { scene: 'rain', label: 'Bruine' };
    if (c >= 61 && c <= 65) return { scene: 'rain', label: c >= 65 ? 'Forte pluie' : 'Pluie' };
    if (c === 66 || c === 67) return { scene: 'rain', label: 'Pluie verglaçante' };
    if (c >= 71 && c <= 77) return { scene: 'clouds', label: 'Neige' };
    if (c >= 80 && c <= 82) return { scene: 'rain', label: 'Averses' };
    if (c >= 85 && c <= 86) return { scene: 'clouds', label: 'Averses de neige' };
    if (c >= 95) return { scene: 'rain', label: 'Orage' };
    return { scene: 'clouds', label: '—' };
  }

  // Données de repli (Paris) — affichées instantanément, écrasées par le fetch.
  const FALLBACK = {
    name: 'Paris', region: 'Île-de-France', lat: 48.8566, lon: 2.3522,
    temp: 11, feel: 9, humidity: 88, wind: 18, visibility: 9, code: 61, isDay: 1,
    hours: [['13h', 11, 61], ['14h', 11, 61], ['15h', 10, 63], ['16h', 10, 61],
            ['17h', 9, 61], ['18h', 9, 3], ['19h', 8, 3], ['20h', 8, 3]],
  };

  const CITIES = ['Paris', 'Tokyo', 'New York', 'Londres', 'Sydney', 'Berlin', 'Dubaï', 'Los Angeles'];

  /* ─── Scènes de ciel (Canvas) ───────────────────────────────────────────── */
  const SKY = {
    rain:   { g: ['#070a12', '#0c1320', '#101a28'], glow: null, rain: 110, clouds: 6, cloudA: .16, stars: 0 },
    clouds: { g: ['#080b12', '#10141d', '#171d28'], glow: ['rgba(220,232,255,.06)', 0.32, 0.30], rain: 0, clouds: 8, cloudA: .20, stars: 0 },
    clear:  { g: ['#060912', '#0a1428', '#122444'], glow: ['rgba(184,150,62,.18)', 0.74, 0.74], rain: 0, clouds: 1, cloudA: .08, stars: 30 },
    night:  { g: ['#04060a', '#070b14', '#0a1018'], glow: ['rgba(174,196,255,.12)', 0.26, 0.22], rain: 0, clouds: 1, cloudA: .07, stars: 160 },
  };

  /* ─── État ──────────────────────────────────────────────────────────────── */
  let container = null, canvas = null, ctx = null, animFrame = null, ro = null;
  let chromeEl = null, hero = null, band = null, widget = null;
  let _visible = false, W = 0, H = 0, dpr = 1;
  let data = Object.assign({}, FALLBACK);
  let scene = 'rain', clouds = [], rain = [], stars = [];
  let reqId = 0;

  function buildParticles() {
    const cfg = SKY[scene] || SKY.clouds;
    clouds = []; rain = []; stars = [];
    for (let i = 0; i < cfg.clouds; i++) clouds.push({ x: Math.random(), y: 0.1 + Math.random() * 0.42, s: 0.7 + Math.random() * 1.3, sp: 0.004 + Math.random() * 0.008, a: cfg.cloudA * (0.6 + Math.random() * 0.7) });
    for (let i = 0; i < cfg.rain; i++) rain.push({ x: Math.random(), y: Math.random(), l: 10 + Math.random() * 13, sp: 0.5 + Math.random() * 0.35 });
    for (let i = 0; i < cfg.stars; i++) stars.push({ x: Math.random(), y: Math.random() * 0.72, r: Math.random() * 1.1 + 0.4, b: Math.random() * 0.5 + 0.3, ph: Math.random() * 6.28, sp: Math.random() * 1.5 + 0.4 });
  }

  function drawCloud(x, y, s, a) {
    ctx.save(); ctx.globalAlpha = a; ctx.translate(x, y); ctx.scale(s, s);
    for (const [dx, dy, r] of [[0, 0, 46], [40, 6, 34], [-40, 8, 32], [16, -16, 30], [-18, -12, 26]]) {
      const g = ctx.createRadialGradient(dx, dy, 2, dx, dy, r);
      g.addColorStop(0, 'rgba(150,166,190,.9)'); g.addColorStop(1, 'rgba(150,166,190,0)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(dx, dy, r, 0, 6.2832); ctx.fill();
    }
    ctx.restore();
  }

  function render(ts) {
    if (!ctx) return;
    const t = (ts || 0) / 1000;
    const cfg = SKY[scene] || SKY.clouds;
    const g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, cfg.g[0]); g.addColorStop(0.5, cfg.g[1]); g.addColorStop(1, cfg.g[2]);
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    if (cfg.glow) {
      const gx = W * cfg.glow[1], gy = H * cfg.glow[2];
      const rg = ctx.createRadialGradient(gx, gy, 4, gx, gy, Math.max(W, H) * 0.55);
      rg.addColorStop(0, cfg.glow[0]); rg.addColorStop(1, 'transparent');
      ctx.fillStyle = rg; ctx.fillRect(0, 0, W, H);
      if (scene === 'clear' || scene === 'night') {
        ctx.beginPath(); ctx.arc(gx, gy, scene === 'clear' ? 30 : 22, 0, 6.2832);
        ctx.fillStyle = scene === 'clear' ? 'rgba(214,196,150,.5)' : 'rgba(220,230,255,.55)'; ctx.fill();
      }
    }
    for (const s of stars) { ctx.globalAlpha = Math.max(0.05, s.b + 0.3 * Math.sin(t * s.sp + s.ph)); ctx.fillStyle = '#DCE8FF'; ctx.beginPath(); ctx.arc(s.x * W, s.y * H, s.r, 0, 6.2832); ctx.fill(); }
    ctx.globalAlpha = 1;
    for (const cl of clouds) { let x = ((cl.x + t * cl.sp) % 1.25) * W - 0.12 * W; drawCloud(x, cl.y * H, cl.s, cl.a); }
    if (cfg.rain) {
      ctx.strokeStyle = 'rgba(150,180,230,.22)'; ctx.lineWidth = 1.1;
      for (const r of rain) {
        let y = ((r.y + t * r.sp) % 1.05) * H;
        let x = r.x * W + y * 0.16;
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - r.l * 0.16, y - r.l); ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
    animFrame = requestAnimationFrame(render);
  }

  /* ─── Chrome dynamique : hero + bandeau + widget ────────────────────────── */
  function num(t, big) { return `<span style="font-family:var(--serif,'Geist');font-weight:300;line-height:.92;letter-spacing:-.04em;color:var(--fg-0,#DCE8FF);font-variant-numeric:tabular-nums;font-size:${big}px">${t}</span>`; }

  function rebuild() {
    [chromeEl, hero, band, widget].forEach((e) => e && e.remove());
    const cond = wmo(data.code, data.isDay);
    scene = cond.scene;
    buildParticles();

    chromeEl = jxBuildChrome({
      viewNum: '02', viewName: 'MÉTÉO',
      voice: `Jarvis · <b>quel temps à ${data.name}</b>`,
      context: [{ muted: true, t: (data.region ? data.region.toUpperCase() + ' · ' : '') + data.name.toUpperCase() }],
      nav: '<b>dis</b> un autre lieu · <span class="k">↵</span> 7 jours',
    });
    container.appendChild(chromeEl);

    // hero bas-gauche (remonté pour laisser respirer au-dessus du bandeau)
    hero = document.createElement('div');
    Object.assign(hero.style, { position: 'absolute', left: '44px', bottom: '188px', zIndex: '7', display: 'flex', flexDirection: 'column', gap: '8px' });
    hero.innerHTML = `
      <div style="font-family:var(--mono,monospace);font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--fg-3,rgba(220,232,255,.4))">${data.name.toUpperCase()} · ${cond.label.toUpperCase()}</div>
      <div style="display:flex;align-items:flex-start;gap:4px">${num(Math.round(data.temp), 132)}<span style="font-family:var(--serif,'Geist');font-weight:300;font-size:44px;color:var(--fg-1,rgba(220,232,255,.78));margin-top:10px">°</span></div>
      <div style="font-family:var(--mono,monospace);font-size:12px;letter-spacing:.04em;color:var(--fg-2,rgba(220,232,255,.58))">Ressenti ${Math.round(data.feel)}°</div>`;
    container.appendChild(hero);

    // widget Conditions haut-droite
    widget = document.createElement('div');
    Object.assign(widget.style, { position: 'absolute', right: '32px', top: '230px', zIndex: '7', width: '266px',
      background: 'rgba(10,14,22,.7)', border: '1px solid var(--line-2,rgba(220,232,255,.1))', borderRadius: 'var(--r-4,16px)',
      backdropFilter: 'blur(18px) saturate(150%)', webkitBackdropFilter: 'blur(18px) saturate(150%)', padding: '18px',
      boxShadow: '0 24px 60px -24px rgba(0,0,0,.6)' });
    const cells = [['RESSENTI', Math.round(data.feel) + '°'], ['VENT', Math.round(data.wind) + ' km/h'],
      ['HUMIDITÉ', Math.round(data.humidity) + '%'], ['VISIBILITÉ', (data.visibility != null ? Math.round(data.visibility) : '—') + ' km']];
    widget.innerHTML = `
      <div style="font-family:var(--mono,monospace);font-size:9.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--fg-3,rgba(220,232,255,.4));margin-bottom:14px">CONDITIONS · MAINTENANT</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px 18px">
        ${cells.map(([l, v]) => `<div>
          <div style="font-family:var(--mono,monospace);font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--fg-3,rgba(220,232,255,.4))">${l}</div>
          <div style="font-family:var(--serif,'Geist');font-weight:300;font-size:24px;color:var(--fg-0,#DCE8FF);margin-top:4px;font-variant-numeric:tabular-nums">${v}</div>
        </div>`).join('')}
      </div>`;
    container.appendChild(widget);

    // sélecteur de villes
    const _pickerSep = document.createElement('div');
    _pickerSep.style.cssText = 'margin-top:18px;padding-top:16px;border-top:1px solid rgba(220,232,255,.06)';
    const _pickerLbl = document.createElement('div');
    _pickerLbl.style.cssText = 'font-family:var(--mono,monospace);font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:rgba(220,232,255,.4);margin-bottom:10px';
    _pickerLbl.textContent = 'CHANGER DE VILLE';
    _pickerSep.appendChild(_pickerLbl);
    const _chips = document.createElement('div');
    _chips.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px';
    CITIES.forEach(function(city) {
      const active = city.toLowerCase() === (data.name || '').toLowerCase();
      const chip = document.createElement('button');
      chip.style.cssText = 'font-family:var(--mono,monospace);font-size:10px;letter-spacing:.06em;padding:5px 11px;border-radius:999px;cursor:pointer;transition:all .15s;border:1px solid '
        + (active ? 'rgba(74,158,255,.35)' : 'rgba(220,232,255,.1)') + ';background:'
        + (active ? 'rgba(74,158,255,.12)' : 'transparent') + ';color:'
        + (active ? '#4A9EFF' : 'rgba(220,232,255,.58)');
      chip.textContent = city;
      chip.addEventListener('click', function() { geocodeAndFetch(city); });
      chip.addEventListener('mouseenter', function() { if (!active) { chip.style.borderColor = 'rgba(74,158,255,.2)'; chip.style.color = 'rgba(220,232,255,.82)'; } });
      chip.addEventListener('mouseleave', function() { if (!active) { chip.style.borderColor = 'rgba(220,232,255,.1)'; chip.style.color = 'rgba(220,232,255,.58)'; } });
      _chips.appendChild(chip);
    });
    _pickerSep.appendChild(_chips);
    const _inputRow = document.createElement('div');
    _inputRow.style.cssText = 'display:flex;gap:6px';
    const _input = document.createElement('input');
    _input.type = 'text'; _input.placeholder = 'Autre ville…';
    _input.style.cssText = 'flex:1;font-family:var(--mono,monospace);font-size:11px;background:rgba(220,232,255,.04);border:1px solid rgba(220,232,255,.1);border-radius:8px;padding:7px 10px;color:rgba(220,232,255,.78);outline:none';
    const _btn = document.createElement('button');
    _btn.textContent = '→';
    _btn.style.cssText = 'font-size:14px;background:rgba(74,158,255,.1);border:1px solid rgba(74,158,255,.25);border-radius:8px;padding:7px 13px;color:#4A9EFF;cursor:pointer';
    function _submit() { const v = _input.value.trim(); if (v) { geocodeAndFetch(v); _input.value = ''; } }
    _btn.addEventListener('click', _submit);
    _input.addEventListener('keydown', function(e) { if (e.key === 'Enter') _submit(); });
    _inputRow.appendChild(_input); _inputRow.appendChild(_btn);
    _pickerSep.appendChild(_inputRow);
    widget.appendChild(_pickerSep);

    // bandeau horaire bas
    band = document.createElement('div');
    Object.assign(band.style, { position: 'absolute', left: '44px', right: '44px', bottom: '74px', zIndex: '7',
      background: 'rgba(6,8,13,.5)', border: '1px solid var(--line-1,rgba(220,232,255,.06))', borderRadius: 'var(--r-3,12px)',
      backdropFilter: 'blur(14px)', webkitBackdropFilter: 'blur(14px)', padding: '0 12px',
      display: 'flex', alignItems: 'stretch' });
    const temps = data.hours.map((h) => h[1]);
    const mx = Math.max.apply(null, temps), mn = Math.min.apply(null, temps);
    band.innerHTML = data.hours.map(([hh, tv], i) => {
      const bh = 4 + (tv - mn + 1) / (mx - mn + 1) * 22;
      return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:8px;padding:12px 0;${i ? 'border-left:1px solid var(--line-1,rgba(220,232,255,.06))' : ''}">
        <div style="font-family:var(--mono,monospace);font-size:10px;color:var(--fg-3,rgba(220,232,255,.4));letter-spacing:.06em">${hh}</div>
        <div style="font-family:var(--serif,'Geist');font-weight:300;font-size:20px;color:var(--fg-0,#DCE8FF);font-variant-numeric:tabular-nums">${Math.round(tv)}°</div>
        <div style="width:3px;height:${bh}px;border-radius:2px;background:var(--line-3,rgba(220,232,255,.16))"></div>
      </div>`;
    }).join('');
    container.appendChild(band);
  }

  /* ─── Fetch Open-Meteo ──────────────────────────────────────────────────── */
  function applyForecast(j, place) {
    const cur = j.current || {};
    const isDay = cur.is_day != null ? cur.is_day : 1;
    const hourly = j.hourly || {};
    // index horaire courant
    let startIdx = 0;
    if (hourly.time && cur.time) { const k = hourly.time.indexOf(cur.time); if (k >= 0) startIdx = k; }
    const hours = [];
    if (hourly.time) {
      for (let i = startIdx; i < Math.min(startIdx + 8, hourly.time.length); i++) {
        const d = new Date(hourly.time[i]);
        hours.push([d.getHours() + 'h', hourly.temperature_2m ? hourly.temperature_2m[i] : 0,
          hourly.weather_code ? hourly.weather_code[i] : 0]);
      }
    }
    let vis = null;
    if (hourly.visibility && hourly.visibility[startIdx] != null) vis = hourly.visibility[startIdx] / 1000;
    data = {
      name: place.name, region: place.region, lat: place.lat, lon: place.lon,
      temp: cur.temperature_2m != null ? cur.temperature_2m : data.temp,
      feel: cur.apparent_temperature != null ? cur.apparent_temperature : data.feel,
      humidity: cur.relative_humidity_2m != null ? cur.relative_humidity_2m : data.humidity,
      wind: cur.wind_speed_10m != null ? cur.wind_speed_10m : data.wind,
      visibility: vis,
      code: cur.weather_code != null ? cur.weather_code : data.code,
      isDay: isDay,
      hours: hours.length ? hours : data.hours,
    };
    rebuild();
  }

  function fetchWeather(place) {
    const id = ++reqId;
    const u = `${FC_URL}?latitude=${place.lat}&longitude=${place.lon}`
      + `&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,is_day`
      + `&hourly=temperature_2m,weather_code,visibility&forecast_days=2&timezone=auto`;
    fetch(u).then((r) => r.json()).then((j) => { if (id === reqId) applyForecast(j, place); }).catch(() => {});
  }

  function geocodeAndFetch(city) {
    const u = `${GEO_URL}?name=${encodeURIComponent(city)}&count=1&language=fr&format=json`;
    fetch(u).then((r) => r.json()).then((j) => {
      const g = j && j.results && j.results[0];
      if (!g) return;
      fetchWeather({ name: g.name, region: g.admin1 || g.country || '', lat: g.latitude, lon: g.longitude });
    }).catch(() => {});
  }

  /* ─── Container ─────────────────────────────────────────────────────────── */
  function resize() {
    W = container.offsetWidth || window.innerWidth;
    H = container.offsetHeight || window.innerHeight;
    dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function ensureContainer() {
    if (container) return;
    jxEnsureChromeCss();
    const s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent = `#weather-container { background:var(--bg-0,#06080D); overflow:hidden; } #weather-container canvas { width:100%; height:100%; display:block; }`;
    document.head.appendChild(s);
    container = document.createElement('div');
    container.id = `${VIEW_ID}-container`;
    Object.assign(container.style, { position: 'fixed', inset: '0', zIndex: '2', background: 'var(--bg-0,#06080D)', opacity: '0', transition: 'opacity .35s ease', display: 'none', overflow: 'hidden' });
    canvas = document.createElement('canvas');
    container.appendChild(canvas);
    document.body.appendChild(container);
    resize();
    ro = new ResizeObserver(resize);
    ro.observe(container);
  }

  /* ─── Enregistrement ────────────────────────────────────────────────────── */
  Jarvis.views.register(VIEW_ID, {
    meta: {
      name: 'Weather',
      desc: 'Météo immersive — scène de ciel animée, conditions et prévisions (Open-Meteo)',
      glyph: 'MTO',
      tags: ['météo', 'climat', 'prévisions', 'ciel'],
    },

    show(params = {}) {
      ensureContainer();
      if (_visible) return;
      _visible = true;
      container.style.display = 'block';
      container.getBoundingClientRect();
      container.style.opacity = '1';

      rebuild();
      if (!animFrame) render();

      // données réelles : par ville, par coordonnées, ou lieu par défaut
      if (params.city) geocodeAndFetch(params.city);
      else if (params.lat != null && params.lon != null) fetchWeather({ name: params.name || 'Lieu', region: params.region || '', lat: params.lat, lon: params.lon });
      else fetchWeather({ name: FALLBACK.name, region: FALLBACK.region, lat: FALLBACK.lat, lon: FALLBACK.lon });
    },

    hide() {
      if (!container) return;
      _visible = false;
      container.style.opacity = '0';
      if (animFrame) { cancelAnimationFrame(animFrame); animFrame = null; }
      setTimeout(() => { if (!_visible && container) container.style.display = 'none'; }, 360);
    },

    command(cmd, params = {}) {
      switch (cmd) {
        case 'set_location':
          if (params.city) geocodeAndFetch(params.city);
          else if (params.lat != null && params.lon != null) fetchWeather({ name: params.name || 'Lieu', region: params.region || '', lat: params.lat, lon: params.lon });
          break;
        case 'refresh':
          fetchWeather({ name: data.name, region: data.region, lat: data.lat, lon: data.lon });
          break;
        // commandes inconnues ignorées silencieusement
      }
    },
  });
})();
