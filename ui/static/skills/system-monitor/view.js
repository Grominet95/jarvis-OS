/**
 * Vue System Monitor — jarvis-skills
 * Dashboard cockpit temps réel : CPU, RAM, disque, cerveau LLM, services Jarvis,
 * missions, mémoire, sessions, uptime. Parti pris « Cockpit » : jauges radiales
 * à coloration par charge, cartes de service, badge LOCAL/CLOUD, sparklines.
 *
 * Données RÉELLES (inchangées) via l'API Jarvis :
 *   /api/system/perf · /api/system/stats · /api/proactive/status · /api/config/llm-status
 * Cross-platform : la batterie est masquée si absente (desktop sans batterie).
 *
 * Dépend de : _shared.js. Chrome commun via <style> partagé (#jx-chrome-css).
 */
(function () {
  if (!window.Jarvis?.views) return;

  const VIEW_ID = 'system-monitor';
  const STYLE_ID = 'sm-styles';
  const PERF_MS = 1500;   // polling /api/system/perf
  const SLOW_MS = 7000;   // polling stats / proactive / llm-status
  const HIST_LEN = 60;    // points historique sparkline (mémoire JS uniquement)

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
    .jx-context .live { display:flex; align-items:center; gap:6px; color:var(--green,#36D399); letter-spacing:.18em; text-transform:uppercase; font-size:9px; }
    .jx-context .live::before { content:""; width:6px; height:6px; border-radius:50%; background:var(--green,#36D399); box-shadow:0 0 8px rgba(54,211,153,.55); animation:jx-pulse 2.4s ease-in-out infinite; }
    @keyframes jx-pulse { 0%,100%{ opacity:1 } 50%{ opacity:.45 } }
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

  /* ─── Coloration par charge (parti pris figé) ───────────────────────────── */
  function loadHex(v) { return v < 55 ? '#4A9EFF' : v < 80 ? '#B8963E' : '#E5484D'; }

  /* ─── Jauges radiales SVG ───────────────────────────────────────────────── */
  const R_SZ = 150, R_SW = 8, R_RAD = R_SZ / 2 - R_SW / 2 - 1, R_CIRC = 2 * Math.PI * R_RAD;
  function mkRing() {
    const ns = 'http://www.w3.org/2000/svg', c = R_SZ / 2;
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', `0 0 ${R_SZ} ${R_SZ}`);
    function el(tag, a) { const e = document.createElementNS(ns, tag); for (const k in a) e.setAttribute(k, a[k]); return e; }
    svg.appendChild(el('circle', { cx: c, cy: c, r: R_RAD, fill: 'none', stroke: 'rgba(220,232,255,.06)', 'stroke-width': R_SW }));
    const glow = el('circle', { cx: c, cy: c, r: R_RAD, fill: 'none', 'stroke-width': 14, opacity: '.14', 'stroke-linecap': 'round', 'stroke-dasharray': `0 ${R_CIRC}`, transform: `rotate(-90 ${c} ${c})` });
    const arc = el('circle', { cx: c, cy: c, r: R_RAD, fill: 'none', 'stroke-width': R_SW, 'stroke-linecap': 'round', 'stroke-dasharray': `0 ${R_CIRC}`, transform: `rotate(-90 ${c} ${c})` });
    arc.style.transition = 'stroke-dasharray .7s cubic-bezier(.4,0,.2,1), stroke .5s';
    glow.style.transition = 'stroke-dasharray .7s cubic-bezier(.4,0,.2,1), stroke .5s';
    svg.appendChild(glow); svg.appendChild(arc);
    return { svg, arc, glow };
  }
  function setRing(ring, pct) {
    if (!ring) return;
    const p = Math.max(0, Math.min(100, pct || 0));
    const dash = `${((p / 100) * R_CIRC).toFixed(2)} ${(R_CIRC - (p / 100) * R_CIRC).toFixed(2)}`;
    const col = loadHex(p);
    ring.arc.setAttribute('stroke-dasharray', dash); ring.arc.setAttribute('stroke', col);
    ring.glow.setAttribute('stroke-dasharray', dash); ring.glow.setAttribute('stroke', col);
  }

  /* ─── Sparklines (Canvas 2D) ────────────────────────────────────────────── */
  function drawSpark(canvas, data, stroke, fillRgba) {
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.offsetWidth || 150, h = canvas.offsetHeight || 30;
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    const ctx = canvas.getContext('2d'); ctx.scale(dpr, dpr); ctx.clearRect(0, 0, w, h);
    const n = data.length; if (n < 2) return;
    ctx.beginPath();
    for (let i = 0; i < n; i++) { const x = (i / (n - 1)) * w, y = h - (data[i] / 100) * (h - 2) - 1; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
    ctx.strokeStyle = stroke; ctx.lineWidth = 1.5; ctx.lineJoin = 'round'; ctx.lineCap = 'round'; ctx.stroke();
    ctx.lineTo(w, h); ctx.lineTo(0, h); ctx.closePath(); ctx.fillStyle = fillRgba; ctx.fill();
  }

  /* ─── État interne ──────────────────────────────────────────────────────── */
  let container = null, perfTimer = null, slowTimer = null, clockTimer = null;
  let _visible = false, _domBuilt = false;
  const hist = { cpu: new Array(HIST_LEN).fill(0), ram: new Array(HIST_LEN).fill(0) };
  const rings = { cpu: null, ram: null, disk: null };

  /* ─── CSS de la vue ─────────────────────────────────────────────────────── */
  /* Cockpit dense (3 paliers) — comme la maquette validée :
     [ jauges CPU/RAM/DISQUE + cerveau ] / [ services + missions ] / [ bandeau bas ] */
  const CSS = `
    #system-monitor-container { font-family:var(--sans,"Geist",system-ui,sans-serif); color:var(--fg-1,rgba(220,232,255,.78)); background:var(--bg-0,#06080D); overflow:hidden; }
    .sm-content { position:absolute; left:36px; right:36px; top:84px; bottom:84px; display:flex; flex-direction:column; gap:16px; z-index:3; }
    .sm-card { border:1px solid var(--line-1,rgba(220,232,255,.06)); border-radius:var(--r-3,12px); background:var(--bg-1,#0A0E16); position:relative; transition:background .3s, border-color .3s, transform .3s; }
    .sm-eyebrow { font-family:var(--mono,monospace); font-size:9px; letter-spacing:.2em; text-transform:uppercase; color:var(--fg-3,rgba(220,232,255,.4)); }

    /* Palier 1 — jauges + cerveau */
    .sm-top { display:grid; grid-template-columns:1fr 1fr 1fr 1.22fr; gap:16px; height:248px; flex-shrink:0; margin-right:280px; }
    .sm-gauge { display:flex; flex-direction:column; align-items:center; justify-content:center; gap:12px; padding:18px 14px; }
    .sm-gauge-label { position:absolute; top:16px; left:18px; }
    .sm-ringwrap { position:relative; width:150px; height:150px; flex-shrink:0; }
    .sm-ringwrap svg { position:absolute; inset:0; width:100%; height:100%; }
    .sm-ringval { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; }
    .sm-ringpct { font-family:var(--serif,"Geist"); font-weight:300; font-size:42px; letter-spacing:-.04em; color:var(--fg-0,#DCE8FF); line-height:1; font-variant-numeric:tabular-nums; }
    .sm-ringpct .u { font-family:var(--mono,monospace); font-size:13px; color:var(--fg-2,rgba(220,232,255,.58)); margin-left:2px; }
    .sm-ringsub { font-family:var(--mono,monospace); font-size:10.5px; color:var(--fg-3,rgba(220,232,255,.4)); letter-spacing:.04em; text-align:center; }
    .sm-focused { background:var(--accent-soft,rgba(74,158,255,.06)); border-color:var(--accent-line,rgba(74,158,255,.28)); }
    /* Cerveau */
    .sm-brain { display:flex; flex-direction:column; justify-content:center; gap:0; padding:22px; }
    .sm-brain .sm-eyebrow { margin-bottom:8px; }
    .sm-brain-row { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
    .sm-brain-provider { font-size:17px; font-weight:500; color:var(--fg-0,#DCE8FF); letter-spacing:-.015em; }
    .sm-brain-model { font-family:var(--mono,monospace); font-size:11px; color:var(--fg-2,rgba(220,232,255,.5)); margin-top:5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .sm-brain-div { height:1px; background:var(--line-1,rgba(220,232,255,.06)); margin:14px 0; }
    .sm-route { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:4px 0; }
    .sm-route-k { font-family:var(--mono,monospace); font-size:9.5px; color:var(--fg-3,rgba(220,232,255,.32)); letter-spacing:.06em; }
    .sm-route-v { font-family:var(--mono,monospace); font-size:9.5px; color:var(--fg-2,rgba(220,232,255,.58)); text-align:right; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:190px; }

    /* Palier 2 — services + missions (remplit le milieu) */
    .sm-mid { flex:1; display:grid; grid-template-columns:1fr 1fr; gap:16px; min-height:0; }
    .sm-panel { padding:20px 22px; display:flex; flex-direction:column; }
    .sm-panel > .sm-eyebrow { margin-bottom:4px; flex-shrink:0; }
    .sm-rows { display:flex; flex-direction:column; justify-content:center; flex:1; }
    .sm-row { display:grid; grid-template-columns:1fr auto; align-items:center; gap:14px; padding:13px 0; border-top:1px solid var(--line-1,rgba(220,232,255,.06)); }
    .sm-row:first-child { border-top:none; }
    .sm-row-name { font-size:13px; color:var(--fg-1,rgba(220,232,255,.82)); }
    .sm-row-name .sub { display:block; font-family:var(--mono,monospace); font-size:9px; letter-spacing:.1em; text-transform:uppercase; color:var(--fg-3,rgba(220,232,255,.36)); margin-top:3px; }
    .sm-row-v { font-family:var(--mono,monospace); font-size:12px; color:var(--fg-2,rgba(220,232,255,.62)); text-align:right; font-variant-numeric:tabular-nums; }
    /* Missions hero */
    .sm-mis-hero { display:flex; align-items:flex-end; gap:12px; margin:6px 0 14px; }
    .sm-mis-num { font-family:var(--serif,"Geist"); font-weight:300; font-size:64px; line-height:.9; letter-spacing:-.04em; color:var(--fg-0,#DCE8FF); font-variant-numeric:tabular-nums; }
    .sm-mis-lbl { font-family:var(--mono,monospace); font-size:10px; letter-spacing:.14em; text-transform:uppercase; color:var(--fg-3,rgba(220,232,255,.4)); padding-bottom:8px; }
    .sm-mis-track { height:3px; background:var(--bg-3,#161B26); border-radius:2px; overflow:hidden; margin:4px 0 16px; }
    .sm-mis-fill { height:100%; width:0%; border-radius:2px; background:linear-gradient(90deg,var(--accent,#4A9EFF),#6BB0FF); transition:width .6s cubic-bezier(.4,0,.2,1); }
    .sm-mis-stats { display:grid; grid-template-columns:1fr 1fr 1fr; gap:14px; }
    .sm-mis-stat .k { font-family:var(--mono,monospace); font-size:9px; letter-spacing:.12em; text-transform:uppercase; color:var(--fg-3,rgba(220,232,255,.4)); }
    .sm-mis-stat .v { font-family:var(--serif,"Geist"); font-weight:300; font-size:24px; color:var(--fg-0,#DCE8FF); margin-top:5px; font-variant-numeric:tabular-nums; }

    /* Palier 3 — bandeau bas (sparklines + valeurs) */
    .sm-bot { height:104px; display:grid; grid-template-columns:repeat(4,1fr); gap:16px; flex-shrink:0; }
    .sm-cell { padding:12px 16px; display:flex; flex-direction:column; gap:6px; justify-content:center; }
    .sm-cell-l { font-family:var(--mono,monospace); font-size:9px; letter-spacing:.12em; text-transform:uppercase; color:var(--fg-3,rgba(220,232,255,.4)); }
    .sm-cell-v { font-family:var(--serif,"Geist"); font-weight:300; font-size:22px; color:var(--fg-0,#DCE8FF); font-variant-numeric:tabular-nums; }
    .sm-cell-v .u { font-family:var(--mono,monospace); font-size:11px; color:var(--fg-2,rgba(220,232,255,.58)); margin-left:2px; }
    .sm-cell-sub { font-family:var(--mono,monospace); font-size:9.5px; color:var(--fg-3,rgba(220,232,255,.34)); }
    .sm-spark { width:100%; height:26px; display:block; }
    /* batterie (ligne service, masquée si absente) */
    .sm-bat-bg { width:54px; height:4px; background:rgba(220,232,255,.06); border-radius:2px; overflow:hidden; display:inline-block; vertical-align:middle; margin-left:8px; }
    .sm-bat-fg { height:100%; border-radius:2px; background:var(--green,#36D399); transition:width .55s ease, background .3s; }
    .sm-bat-fg.warn { background:var(--gold,#B8963E); } .sm-bat-fg.crit { background:var(--red,#E5484D); }
  `;

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const s = document.createElement('style'); s.id = STYLE_ID; s.textContent = CSS;
    document.head.appendChild(s);
  }

  /* ─── Construction du DOM ───────────────────────────────────────────────── */
  function gaugeCard(id, label) {
    return `<div class="sm-card sm-gauge" id="sm-panel-${id}">
      <span class="sm-gauge-label sm-eyebrow">${label}</span>
      <div class="sm-ringwrap" id="sm-rw-${id}">
        <div class="sm-ringval"><span class="sm-ringpct"><span id="sm-v-${id}">0</span><span class="u">%</span></span></div>
      </div>
      <div class="sm-ringsub" id="sm-s-${id}">—</div>
    </div>`;
  }

  function buildDOM() {
    // chrome (langage commun aux 4 vues)
    const chrome = document.createElement('div');
    chrome.className = 'jx-chrome';
    chrome.innerHTML = `
      <div class="jx-context">
        <span class="muted" id="sm-uptime">UPTIME —</span>
        <span class="sep"></span>
        <span class="live">Live</span>
        <span class="sep"></span>
        <span id="sm-clock">—</span>
      </div>
      <div class="jx-navhint"><span class="k">↵</span> focus métrique</div>`;

    const content = document.createElement('div');
    content.className = 'sm-content';
    content.innerHTML = `
      <!-- Palier 1 : jauges + cerveau -->
      <div class="sm-top">
        ${gaugeCard('cpu', 'CPU')}
        ${gaugeCard('ram', 'RAM')}
        ${gaugeCard('disk', 'DISQUE')}
        <div class="sm-card sm-brain" id="sm-panel-llm">
          <span class="sm-eyebrow">Cerveau Jarvis · provider actif</span>
          <div class="sm-brain-row">
            <span class="sm-brain-provider" id="sm-llm-provider">—</span>
            <span id="sm-llm-badge" class="jx-badge" style="display:none"></span>
          </div>
          <div class="sm-brain-model" id="sm-llm-model">—</div>
          <div class="sm-brain-div"></div>
          <span class="sm-eyebrow">Routes actives</span>
          <div id="sm-llm-routes"><div class="sm-route"><span class="sm-route-k">—</span></div></div>
        </div>
      </div>

      <!-- Palier 2 : services + missions (remplit le milieu) -->
      <div class="sm-mid">
        <div class="sm-card sm-panel" id="sm-panel-services">
          <span class="sm-eyebrow">Services · écosystème Jarvis</span>
          <div class="sm-rows">
            <div class="sm-row"><div class="sm-row-name">Backend API<span class="sub">noyau</span></div><span class="jx-badge green" id="sm-svc-api"><span class="dot"></span>Online</span></div>
            <div class="sm-row"><div class="sm-row-name">Moteur proactif<span class="sub">missions auto</span></div><span class="jx-badge" id="sm-svc-proactive-badge"><span class="dot"></span><span id="sm-svc-proactive">—</span></span></div>
            <div class="sm-row"><div class="sm-row-name">Mémoire<span class="sub" id="sm-svc-mem-sub">—</span></div><span class="sm-row-v" id="sm-svc-mem">—</span></div>
            <div class="sm-row"><div class="sm-row-name">Sessions<span class="sub">historique</span></div><span class="sm-row-v" id="sm-svc-sessions">—</span></div>
            <div class="sm-row" id="sm-bat-cell" style="display:none"><div class="sm-row-name">Batterie<span class="sub">alimentation</span></div><span class="sm-row-v"><span id="sm-svc-bat">—</span><span class="sm-bat-bg"><span class="sm-bat-fg" id="sm-bat-bar"></span></span></span></div>
          </div>
        </div>
        <div class="sm-card sm-panel" id="sm-panel-missions">
          <span class="sm-eyebrow">Missions · pilotage</span>
          <div class="sm-mis-hero">
            <span class="sm-mis-num" id="sm-mis-running">0</span>
            <span class="sm-mis-lbl">en cours</span>
          </div>
          <div class="sm-mis-track"><div class="sm-mis-fill" id="sm-mis-fill"></div></div>
          <div class="sm-mis-stats">
            <div class="sm-mis-stat"><div class="k">Terminées</div><div class="v" id="sm-mis-done">—</div></div>
            <div class="sm-mis-stat"><div class="k">Total</div><div class="v" id="sm-mis-total">—</div></div>
            <div class="sm-mis-stat"><div class="k">File</div><div class="v" id="sm-mis-queue">—</div></div>
          </div>
        </div>
      </div>

      <!-- Palier 3 : bandeau bas (sparklines + valeurs) -->
      <div class="sm-bot">
        <div class="sm-card sm-cell">
          <span class="sm-cell-l">CPU · 60 s</span>
          <canvas id="sm-spark-cpu" class="sm-spark"></canvas>
        </div>
        <div class="sm-card sm-cell">
          <span class="sm-cell-l">RAM · 60 s</span>
          <canvas id="sm-spark-ram" class="sm-spark"></canvas>
        </div>
        <div class="sm-card sm-cell">
          <span class="sm-cell-l">Uptime</span>
          <span class="sm-cell-v" id="sm-cell-uptime">—</span>
          <span class="sm-cell-sub">sans incident</span>
        </div>
        <div class="sm-card sm-cell">
          <span class="sm-cell-l">Processus Jarvis</span>
          <span class="sm-cell-v"><span id="sm-proc-cpu">—</span></span>
          <span class="sm-cell-sub"><span id="sm-proc-ram">—</span> · RAM</span>
        </div>
      </div>`;

    container.appendChild(content);
    container.appendChild(chrome);

    // injecter les anneaux SVG
    rings.cpu = mkRing(); rings.ram = mkRing(); rings.disk = mkRing();
    [['sm-rw-cpu', rings.cpu], ['sm-rw-ram', rings.ram], ['sm-rw-disk', rings.disk]].forEach(([id, r]) => {
      const w = document.getElementById(id); if (w) w.insertBefore(r.svg, w.firstChild);
    });
    _domBuilt = true;
  }

  /* ─── Helpers ───────────────────────────────────────────────────────────── */
  function setText(id, v) { const el = document.getElementById(id); if (el) el.textContent = v; }
  function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function fmtUptime(s) {
    if (s == null) return '—';
    const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
    if (d > 0) return `${d}j ${h}h`; if (h > 0) return `${h}h ${m}m`; return `${m}m`;
  }
  function apiFetch(path) {
    return fetch(window.location.origin + path).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });
  }

  /* ─── Mise à jour (parsing INCHANGÉ vs version d'origine) ───────────────── */
  function updatePerf(d) {
    if (!d) return;
    const cpu = d.cpu_pct ?? 0;
    hist.cpu.shift(); hist.cpu.push(cpu);
    setText('sm-v-cpu', Math.round(cpu)); setRing(rings.cpu, cpu);
    if (d.cpu_cores != null) setText('sm-s-cpu', `${d.cpu_cores} cœurs · ${d.cpu_threads ?? '—'} threads`);

    const ram = d.ram_pct ?? 0;
    hist.ram.shift(); hist.ram.push(ram);
    setText('sm-v-ram', Math.round(ram)); setRing(rings.ram, ram);
    if (d.ram_used_gb != null && d.ram_total_gb != null) setText('sm-s-ram', `${d.ram_used_gb.toFixed(1)} / ${d.ram_total_gb.toFixed(1)} Go`);

    const diskPct = d.disk_pct ?? d.disk_used_pct ?? 0;
    setText('sm-v-disk', Math.round(diskPct)); setRing(rings.disk, diskPct);
    const du = d.disk_used_gb ?? d.disk_used, dt = d.disk_total_gb ?? d.disk_total;
    if (du != null && dt != null) setText('sm-s-disk', `${Number(du).toFixed(0)} / ${Number(dt).toFixed(0)} Go`);

    if (d.uptime_s != null) {
      setText('sm-uptime', `UPTIME ${fmtUptime(d.uptime_s)}`);
      setText('sm-cell-uptime', fmtUptime(d.uptime_s));
    }

    const proc = Array.isArray(d.proc) ? d.proc[0] : d.proc;
    if (proc) {
      setText('sm-proc-cpu', proc.cpu_pct != null ? `${proc.cpu_pct.toFixed(1)} %` : '—');
      setText('sm-proc-ram', proc.ram_mb != null ? `${Math.round(proc.ram_mb)} Mo` : '—');
    }

    const bat = d.battery, batCell = document.getElementById('sm-bat-cell');
    if (bat && batCell) {
      batCell.style.display = '';
      const pct = bat.percent ?? bat.pct ?? null;
      if (pct != null) {
        setText('sm-svc-bat', `${Math.round(pct)} %`);
        const bar = document.getElementById('sm-bat-bar');
        if (bar) { bar.style.width = `${Math.min(100, pct)}%`; bar.className = 'sm-bat-fg' + (pct < 15 ? ' crit' : pct < 30 ? ' warn' : ''); }
      }
    } else if (batCell) { batCell.style.display = 'none'; }

    requestAnimationFrame(() => {
      drawSpark(document.getElementById('sm-spark-cpu'), hist.cpu, '#4A9EFF', 'rgba(74,158,255,.08)');
      drawSpark(document.getElementById('sm-spark-ram'), hist.ram, '#4A9EFF', 'rgba(74,158,255,.08)');
    });
  }

  function updateStats(d) {
    if (!d) return;
    const p = d.projects;
    if (p) {
      const running = p.running ?? 0, done = p.done ?? 0, total = p.total ?? 0;
      const queue = Math.max(0, total - done - running);
      setText('sm-mis-running', running);
      setText('sm-mis-done', done);
      setText('sm-mis-total', total);
      setText('sm-mis-queue', queue);
      const fill = document.getElementById('sm-mis-fill');
      if (fill) fill.style.width = (total > 0 ? Math.round((done / total) * 100) : 0) + '%';
    }
    const m = d.memory;
    if (m) {
      setText('sm-svc-mem', m.topics != null ? `${m.topics} sujets` : '—');
      if (m.size_kb != null) setText('sm-svc-mem-sub', `${(m.size_kb / 1024).toFixed(1)} Mo`);
    }
    const sess = d.sessions;
    if (sess && sess.total != null) setText('sm-svc-sessions', sess.size_mb != null ? `${sess.total} (${sess.size_mb.toFixed(1)} Mo)` : `${sess.total}`);
  }

  function updateProactive(d) {
    if (!d) return;
    const badge = document.getElementById('sm-svc-proactive-badge');
    const txt = document.getElementById('sm-svc-proactive');
    if (!badge || !txt) return;
    const active = d.running ?? d.enabled ?? d.active ?? (d.status === 'running');
    txt.textContent = active ? 'Actif' : 'Inactif';
    badge.className = 'jx-badge ' + (active ? 'green' : '');
  }

  function updateLLM(d) {
    if (!d) return;
    const LOCAL_KW = ['ollama', 'lmstudio', 'lm_studio', 'llamacpp', 'llama_cpp', 'mistral.rs', 'vllm', 'local'];
    const ROUTE_KEYS = ['gateway', 'voice', 'worker', 'main', 'default'];
    let provider = null, model = null, isLocal = false; const routes = [];
    let hasRoutes = false;
    for (const key of ROUTE_KEYS) {
      const r = d[key];
      if (r && typeof r === 'object') {
        hasRoutes = true;
        if (!provider) { provider = r.provider ?? r.class ?? r.name ?? null; model = r.model ?? r.model_id ?? null; }
        routes.push({ key, val: `${r.provider ?? r.class ?? r.name ?? key} / ${r.model ?? r.model_id ?? '?'}` });
      }
    }
    if (!hasRoutes) { provider = d.provider ?? d.class ?? d.name ?? null; model = d.model ?? d.model_id ?? null; }
    if (!provider) return;
    isLocal = LOCAL_KW.some((k) => String(provider).toLowerCase().includes(k));
    setText('sm-llm-provider', provider);
    setText('sm-llm-model', model || '—');
    const badge = document.getElementById('sm-llm-badge');
    if (badge) { badge.style.display = ''; badge.className = 'jx-badge ' + (isLocal ? 'green' : 'accent'); badge.innerHTML = `<span class="dot"></span>${isLocal ? 'Local' : 'Cloud'}`; }
    const routesEl = document.getElementById('sm-llm-routes');
    if (routesEl && routes.length) routesEl.innerHTML = routes.map((r) => `<div class="sm-route"><span class="sm-route-k">${esc(r.key)}</span><span class="sm-route-v">${esc(r.val)}</span></div>`).join('');
  }

  /* ─── Fetch / timers (inchangé) ─────────────────────────────────────────── */
  async function fetchPerf() { try { updatePerf(await apiFetch('/api/system/perf')); } catch (_) {} }
  async function fetchSlow() {
    const [s, p, l] = await Promise.allSettled([apiFetch('/api/system/stats'), apiFetch('/api/proactive/status'), apiFetch('/api/config/llm-status')]);
    if (s.status === 'fulfilled') updateStats(s.value);
    if (p.status === 'fulfilled') updateProactive(p.value);
    if (l.status === 'fulfilled') updateLLM(l.value);
  }
  function startPolling() { stopPolling(); fetchPerf(); fetchSlow(); perfTimer = setInterval(fetchPerf, PERF_MS); slowTimer = setInterval(fetchSlow, SLOW_MS); }
  function stopPolling() { clearInterval(perfTimer); perfTimer = null; clearInterval(slowTimer); slowTimer = null; }
  function startClock() {
    stopClock();
    const tick = () => { const el = document.getElementById('sm-clock'); if (el) el.textContent = new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }); };
    tick(); clockTimer = setInterval(tick, 1000);
  }
  function stopClock() { clearInterval(clockTimer); clockTimer = null; }

  /* ─── Focus métrique ────────────────────────────────────────────────────── */
  const FOCUS_MAP = { cpu: 'sm-panel-cpu', ram: 'sm-panel-ram', disk: 'sm-panel-disk', disque: 'sm-panel-disk', llm: 'sm-panel-llm', cerveau: 'sm-panel-llm', services: 'sm-panel-services', missions: 'sm-panel-missions' };
  function setFocus(metric) {
    document.querySelectorAll('.sm-focused').forEach((el) => { el.classList.remove('sm-focused'); el.style.transform = ''; });
    if (!metric) return;
    const id = FOCUS_MAP[String(metric).toLowerCase()]; if (!id) return;
    const panel = document.getElementById(id);
    if (panel) { panel.classList.add('sm-focused'); if (panel.classList.contains('sm-gauge')) panel.style.transform = 'scale(1.04)'; }
  }

  /* ─── Container ─────────────────────────────────────────────────────────── */
  function ensureContainer() {
    if (container) return;
    jxEnsureChromeCss(); injectStyle();
    container = document.createElement('div');
    container.id = `${VIEW_ID}-container`;
    Object.assign(container.style, { position: 'fixed', inset: '0', zIndex: '2', display: 'none', opacity: '0', transition: 'opacity .35s ease' });
    document.body.appendChild(container);
  }

  /* ─── Enregistrement ────────────────────────────────────────────────────── */
  Jarvis.views.register(VIEW_ID, {
    meta: {
      name: 'System Monitor',
      desc: 'Cockpit système temps réel — CPU, RAM, disque, cerveau LLM, services',
      glyph: 'SYS',
      tags: ['système', 'monitoring', 'dashboard', 'performance'],
    },

    show(params = {}) {
      ensureContainer();
      if (_visible) return;
      _visible = true;
      if (!_domBuilt) buildDOM();
      container.style.display = 'block';
      container.getBoundingClientRect();
      container.style.opacity = '1';
      startClock(); startPolling();
    },

    hide() {
      if (!container) return;
      _visible = false;
      container.style.opacity = '0';
      stopPolling(); stopClock();
      setTimeout(() => { if (!_visible && container) container.style.display = 'none'; }, 360);
    },

    command(cmd, params = {}) {
      switch (cmd) {
        case 'show': this.show(params); break;
        case 'hide': this.hide(); break;
        case 'focus_metric': if (!_visible) this.show({}); setFocus(params.metric || null); break;
        case 'overview': setFocus(null); break;
        case 'refresh': fetchPerf(); fetchSlow(); break;
        // commandes inconnues ignorées silencieusement
      }
    },
  });
})();
