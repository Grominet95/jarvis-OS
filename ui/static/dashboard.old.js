/* ================================================================
   JARVIS V3 — Dashboard Pilotage
   ================================================================ */
'use strict';

/* ── State ──────────────────────────────────────────────────────── */
const _dash = {
  section:     'initiatives',
  projFilter:  'all',
  projects:    [],
  initiatives: [],
  initFilter:  'all',
  briefData:   null,
  briefTimer:  null,
  analyticsDays: 7,
};

const DASH_STEP_ICON = { running:'↻', done:'✓', failed:'✗', waiting:'⏸', paused:'⏸', skipped:'—', pending:'○' };
const DASH_FILE_ICON = { md:'📄',txt:'📄',json:'{}',py:'🐍',js:'📜',ts:'📜',html:'🌐',css:'🎨',csv:'📊',pdf:'📋',png:'🖼',jpg:'🖼' };

function _dEsc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function _dFileIcon(name) {
  const ext = (name.split('.').pop() || '').toLowerCase();
  return DASH_FILE_ICON[ext] || '📄';
}
function _dFmtSize(b) {
  if (b < 1024) return b + ' B';
  if (b < 1024*1024) return (b/1024).toFixed(1) + ' KB';
  return (b/1024/1024).toFixed(2) + ' MB';
}
function _dMain() { return document.getElementById('dashboard-main'); }

/* ── Clock ──────────────────────────────────────────────────────── */
function _updateDashClock() {
  const el = document.getElementById('dash-datetime');
  if (!el) return;
  const now = new Date();
  const days = ['Dimanche','Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi'];
  const months = ['janvier','février','mars','avril','mai','juin','juillet','août','septembre','octobre','novembre','décembre'];
  const hh = String(now.getHours()).padStart(2,'0');
  const mm = String(now.getMinutes()).padStart(2,'0');
  el.textContent = `${days[now.getDay()]} ${now.getDate()} ${months[now.getMonth()]} · ${hh}:${mm}`;
}

/* ── Open / Close ───────────────────────────────────────────────── */
window.openDashboard = function () {
  if (window._currentView === 'dashboard') return;
  if (window._currentView === 'intel') { window.navigateFromIntel('dashboard'); return; }
  const settingsOverlay = document.getElementById('settings-overlay');
  if (settingsOverlay && settingsOverlay.style.display === 'block') window.closeSettings?.();
  const dash = document.getElementById('dashboard-view');
  if (!dash) return;
  window._previousView = window._currentView || 'sphere';
  if (window._setView) window._setView('dashboard');
  else { window._currentView = 'dashboard'; document.getElementById('dashboard-nav-btn')?.classList.add('active'); }

  dash.classList.add('visible');
  _updateDashClock();

  if (typeof gsap !== 'undefined') {
    gsap.fromTo(dash,
      { opacity: 0, scale: 0.97, filter: 'blur(8px)' },
      { opacity: 1, scale: 1, filter: 'blur(0px)', duration: 0.35, ease: 'power2.out' }
    );
  }

  // Start clock
  _updateDashClock();
  if (dash._clockTimer) clearInterval(dash._clockTimer);
  dash._clockTimer = setInterval(_updateDashClock, 10000);

  loadDashboardSection(_dash.section || 'initiatives');
};

window.closeDashboard = function () {
  const dash = document.getElementById('dashboard-view');
  if (!dash) return;

  if (dash._clockTimer) { clearInterval(dash._clockTimer); dash._clockTimer = null; }
  if (_dash.briefTimer) { clearTimeout(_dash.briefTimer); _dash.briefTimer = null; }

  const finish = () => {
    dash.classList.remove('visible');
    const restoreView = window._previousView || 'sphere';
    if (window._setView) window._setView(restoreView);
    else { window._currentView = restoreView; document.getElementById('dashboard-nav-btn')?.classList.remove('active'); }
  };

  if (typeof gsap !== 'undefined') {
    gsap.to(dash, {
      opacity: 0, scale: 1.02, filter: 'blur(8px)', duration: 0.2, ease: 'power2.in',
      onComplete: finish,
    });
  } else {
    finish();
  }
};

/* ── Section navigation ─────────────────────────────────────────── */
window.loadDashboardSection = function (section) {
  _dash.section = section;

  document.querySelectorAll('.dash-nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.section === section);
  });

  const main = _dMain();
  if (!main) return;

  const render = () => {
    switch (section) {
      case 'initiatives': _renderInitiatives(); break;
      case 'missions':    _renderDashMissions(); break;
      case 'domotique':   _renderDomotique(); break;
      case 'devices':     _renderDevices(); break;
      case 'analytics':   _renderAnalytics(); break;
      default:            main.innerHTML = '<div class="dash-empty">Section inconnue.</div>';
    }
  };

  if (typeof gsap !== 'undefined') {
    gsap.to(main, { opacity: 0, duration: 0.12, onComplete: () => {
      render();
      gsap.to(main, { opacity: 1, duration: 0.18 });
    }});
  } else {
    render();
  }
};

/* ================================================================
   SECTION — INITIATIVES
   ================================================================ */
async function _renderInitiatives() {
  const main = _dMain();
  main.innerHTML = '<div class="dash-loading">CHARGEMENT…</div>';

  // Fetch all data in parallel
  const [initsResult, projectsResult, consoResult] = await Promise.allSettled([
    fetch('/api/initiatives').then(r => r.json()),
    fetch('/api/projects').then(r => r.json()),
    fetch('/api/conso/session').then(r => r.json()),
  ]);

  const inits    = initsResult.status === 'fulfilled' ? initsResult.value : [];
  const projects = projectsResult.status === 'fulfilled' ? projectsResult.value : [];
  const conso    = consoResult.status === 'fulfilled' ? consoResult.value : {};

  _dash.initiatives = inits;
  _dash.projects = projects;

  const running = projects.filter(p => p.status === 'running' || p.status === 'planning').length;
  const costToday = (conso.total_cost_usd || 0).toFixed(2);
  const totalTokens = (conso.total_tokens || 0).toLocaleString('fr-FR');

  const lastUpdated = _briefLastUpdatedLabel();

  main.innerHTML = `
    <div class="dash-section-hd">
      <span class="dash-section-title">Initiatives</span>
      <span class="dash-section-meta">${lastUpdated}</span>
    </div>

    <!-- Brief bar -->
    <div class="brief-bar">
      <div class="brief-metric" onclick="loadDashboardSection('missions')">
        <span class="brief-metric-icon">⚙</span>
        <div class="brief-metric-value">${running}</div>
        <div class="brief-metric-label">Mission en cours</div>
      </div>
      <div class="brief-metric" onclick="loadDashboardSection('missions')">
        <span class="brief-metric-icon">✓</span>
        <div class="brief-metric-value">${projects.filter(p=>p.status==='done').length}</div>
        <div class="brief-metric-label">Terminées</div>
      </div>
      <div class="brief-metric">
        <span class="brief-metric-icon">⚡</span>
        <div class="brief-metric-value">${inits.length}</div>
        <div class="brief-metric-label">Initiatives</div>
      </div>
      <div class="brief-metric" onclick="loadDashboardSection('analytics')">
        <span class="brief-metric-icon">💰</span>
        <div class="brief-metric-value">$${costToday}</div>
        <div class="brief-metric-label">Coût session</div>
      </div>
      <div class="brief-metric" onclick="loadDashboardSection('analytics')">
        <span class="brief-metric-icon">🧠</span>
        <div class="brief-metric-value">${totalTokens}</div>
        <div class="brief-metric-label">Tokens session</div>
      </div>
      <div class="brief-metric">
        <span class="brief-metric-icon">🔮</span>
        <div class="brief-metric-value">${_proactiveStatus()}</div>
        <div class="brief-metric-label">Proactif</div>
      </div>
    </div>

    <!-- Initiatives list -->
    <div class="dash-subsection-hd">
      <span class="dash-subsection-title">INITIATIVES EN ATTENTE (${inits.length})</span>
      <button class="dash-btn" id="dash-analyze-btn" onclick="_dashRunProactive()">↻ Analyser</button>
    </div>

    <div class="dash-filter-bar" id="dash-init-filters">
      ${_initFilterBar(inits)}
    </div>

    <div id="dash-init-list">
      ${_renderInitList(inits, _dash.initFilter)}
    </div>

    ${inits.length === 0 ? `
    <div class="next-cycle-bar">
      <div class="next-cycle-label">Prochain cycle proactif dans quelques minutes</div>
      <div class="next-cycle-progress"><div class="next-cycle-fill" style="width:40%"></div></div>
    </div>` : ''}
  `;

  // Schedule next brief refresh in 5 min
  if (_dash.briefTimer) clearTimeout(_dash.briefTimer);
  _dash.briefTimer = setTimeout(() => {
    if (_dash.section === 'initiatives') _renderInitiatives();
  }, 5 * 60 * 1000);
}

function _briefLastUpdatedLabel() {
  const now = new Date();
  return `mis à jour à ${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
}

function _proactiveStatus() {
  return '●';
}

function _initFilterBar(inits) {
  const types = ['all', ...new Set(inits.map(i => i.type || 'autre'))];
  const counts = {};
  types.forEach(t => {
    counts[t] = t === 'all' ? inits.length : inits.filter(i => (i.type||'autre') === t).length;
  });
  return types.map(t => `
    <button class="dash-filter ${_dash.initFilter === t ? 'active' : ''}"
      onclick="_dashInitFilter('${_dEsc(t)}')">
      ${t === 'all' ? 'Tous' : t} (${counts[t]})
    </button>
  `).join('');
}

function _renderInitList(inits, filter) {
  const list = filter === 'all' ? inits : inits.filter(i => (i.type||'autre') === filter);
  if (!list.length) return '<div class="dash-empty">Aucune initiative en attente.</div>';
  return list.map(i => _initRow(i)).join('');
}

function _initRow(i) {
  const prio = (i.priority || 'moyen').toUpperCase();
  const dotClass = prio === 'HAUTE' ? 'high' : prio === 'MOYEN' ? 'medium' : 'low';
  return `
    <div class="initiative-row" id="init-row-${_dEsc(i.id)}" onclick="_dashToggleInit('${_dEsc(i.id)}')">
      <span class="init-dot ${dotClass}"></span>
      <span class="init-type">${_dEsc(i.type || '?')}</span>
      <span class="init-title">${_dEsc(i.title)}</span>
      <span class="init-priority ${prio}">${prio}</span>
      <button class="init-expand-btn" onclick="event.stopPropagation();_dashToggleInit('${_dEsc(i.id)}')">→</button>
    </div>
    <div class="initiative-detail" id="init-detail-${_dEsc(i.id)}" style="display:none">
      <div class="init-context">${_dEsc(i.context || i.reasoning || '')}</div>
      <div class="init-actions">
        <button class="init-action-btn approve" onclick="_dashApproveInit('${_dEsc(i.id)}')">✓ Valider</button>
        <button class="init-action-btn reject"  onclick="_dashRejectInit('${_dEsc(i.id)}')">✕ Rejeter</button>
      </div>
    </div>`;
}

window._dashInitFilter = (f) => {
  _dash.initFilter = f;
  document.getElementById('dash-init-filters').innerHTML = _initFilterBar(_dash.initiatives);
  document.getElementById('dash-init-list').innerHTML = _renderInitList(_dash.initiatives, f);
};

window._dashToggleInit = (id) => {
  const detail = document.getElementById('init-detail-' + id);
  const row = document.getElementById('init-row-' + id);
  if (!detail) return;
  const open = detail.style.display !== 'none';
  detail.style.display = open ? 'none' : 'block';
  row?.classList.toggle('expanded', !open);
};

window._dashRunProactive = async () => {
  const btn = document.getElementById('dash-analyze-btn');
  if (btn) { btn.disabled = true; btn.textContent = '↻ En cours…'; }
  try {
    await fetch('/api/proactive/run', { method: 'POST' });
    setTimeout(() => { if (_dash.section === 'initiatives') _renderInitiatives(); }, 3000);
  } catch { /* silent */ } finally {
    if (btn) { btn.disabled = false; btn.textContent = '↻ Analyser'; }
  }
};

window._dashApproveInit = async (id) => {
  try {
    await fetch(`/api/initiatives/${id}/approve`, { method: 'POST' });
    _dash.initiatives = _dash.initiatives.filter(i => i.id !== id);
    document.getElementById('init-row-' + id)?.remove();
    document.getElementById('init-detail-' + id)?.remove();
  } catch { /* silent */ }
};

window._dashRejectInit = async (id) => {
  try {
    await fetch(`/api/initiatives/${id}/reject`, { method: 'POST' });
    _dash.initiatives = _dash.initiatives.filter(i => i.id !== id);
    document.getElementById('init-row-' + id)?.remove();
    document.getElementById('init-detail-' + id)?.remove();
  } catch { /* silent */ }
};

/* ================================================================
   SECTION — MISSIONS
   ================================================================ */
async function _renderDashMissions() {
  const main = _dMain();
  main.innerHTML = '<div class="dash-loading">CHARGEMENT…</div>';
  try {
    const r = await fetch('/api/projects');
    _dash.projects = await r.json();
  } catch { _dash.projects = []; }
  _paintDashMissions();
}

function _paintDashMissions() {
  const f = _dash.projFilter;
  const list = f === 'all' ? _dash.projects : _dash.projects.filter(p => p.status === f);
  const main = _dMain();

  let html = `
    <div class="dash-section-hd">
      <span class="dash-section-title">Missions</span>
      <button class="dash-btn" onclick="_dashNewMission()">＋ Nouvelle</button>
    </div>
    <div class="dash-filter-row">
      ${['all','running','done','failed'].map(x => `
        <button class="dash-filter ${f===x?'active':''}" onclick="_dashProjFilter('${x}')">
          ${x==='all'?'Toutes':x==='running'?'En cours':x.charAt(0).toUpperCase()+x.slice(1)}
        </button>`).join('')}
    </div>`;

  if (!list.length) {
    html += '<div class="dash-empty">AUCUNE MISSION</div>';
  } else {
    list.forEach(p => { html += _dashProjCard(p); });
  }
  html += `<button class="dash-new-proj-btn" onclick="_dashNewMission()">＋ NOUVELLE MISSION</button>`;
  main.innerHTML = html;
}

function _dashProjCard(p) {
  const pct = p.steps_total > 0 ? Math.round(p.steps_done / p.steps_total * 100) : 0;
  const fc = p.status === 'done' ? 'done' : p.status === 'failed' ? 'failed' : '';
  return `
    <div class="dash-proj-card ${_dEsc(p.status)}" id="dcard-${_dEsc(p.id)}">
      <div class="dash-proj-hd" onclick="_dashToggleCard('${_dEsc(p.id)}')">
        <span class="dash-proj-title">${_dEsc(p.title)}</span>
        <span class="dash-status-badge ${_dEsc(p.status)}">${_dEsc(p.status).toUpperCase()}</span>
        ${(p.status==='running'||p.status==='planning') ? `
          <button class="dash-proj-kill" onclick="event.stopPropagation();_dashKill('${_dEsc(p.id)}')">✕</button>
        ` : ''}
      </div>
      <div class="dash-prog-row">
        <div class="dash-prog-bar"><div class="dash-prog-fill ${fc}" style="width:${pct}%"></div></div>
        <span class="dash-prog-meta">${p.steps_done}/${p.steps_total}</span>
      </div>
      <div class="dash-card-body" id="dbody-${_dEsc(p.id)}" style="display:none">
        <div class="dash-subsec-hd" onclick="_dashToggleSub('dbsteps-${_dEsc(p.id)}','dbarr-steps-${_dEsc(p.id)}')">
          <span class="dash-subsec-arrow" id="dbarr-steps-${_dEsc(p.id)}">▶</span>
          <span class="dash-subsec-lbl">ÉTAPES</span>
          <span class="dash-subsec-count">${p.steps_done}/${p.steps_total}</span>
        </div>
        <div id="dbsteps-${_dEsc(p.id)}" style="display:none"></div>
        <div class="dash-subsec-hd" onclick="_dashToggleSub('dbfiles-${_dEsc(p.id)}','dbarr-files-${_dEsc(p.id)}')">
          <span class="dash-subsec-arrow" id="dbarr-files-${_dEsc(p.id)}">▶</span>
          <span class="dash-subsec-lbl">FICHIERS</span>
          <span class="dash-subsec-count">${p.files_created}</span>
        </div>
        <div id="dbfiles-${_dEsc(p.id)}" style="display:none"></div>
      </div>
    </div>`;
}

window._dashProjFilter = (f) => { _dash.projFilter = f; _paintDashMissions(); };
window._dashNewMission = () => { window.closeDashboard(); };

window._dashToggleSub = (contentId, arrowId) => {
  const el = document.getElementById(contentId);
  const arrow = document.getElementById(arrowId);
  if (!el) return;
  const open = el.style.display !== 'none';
  el.style.display = open ? 'none' : 'block';
  arrow?.classList.toggle('open', !open);
};

window._dashToggleCard = async (id) => {
  const body = document.getElementById('dbody-' + id);
  if (!body) return;
  const vis = body.style.display !== 'none';
  body.style.display = vis ? 'none' : 'block';
  if (!vis) await _loadDashProjectDetail(id);
};

async function _loadDashProjectDetail(id) {
  try {
    const [dr, fr] = await Promise.allSettled([
      fetch(`/api/projects/${id}`).then(r => r.json()),
      fetch(`/api/projects/${id}/files`).then(r => r.json()),
    ]);
    const proj  = dr.status === 'fulfilled' ? dr.value : {};
    const files = fr.status === 'fulfilled' ? fr.value : [];
    _renderDashSteps(id, proj.steps || []);
    _renderDashFiles(id, files);
  } catch { /**/ }
}

function _renderDashSteps(id, steps) {
  const el = document.getElementById('dbsteps-' + id);
  if (!el) return;
  if (!steps.length) { el.innerHTML = '<div class="dash-empty">Aucune étape.</div>'; return; }
  let html = '<div class="dash-steps">';
  steps.forEach(s => {
    const ico = DASH_STEP_ICON[s.status] || '○';
    html += `<div class="dash-step">
      <span class="dash-step-icon ${_dEsc(s.status)}">${_dEsc(ico)}</span>
      <div class="dash-step-title ${_dEsc(s.status)}">${_dEsc(s.title || s.id)}</div>
    </div>`;
  });
  html += '</div>';
  el.innerHTML = html;
}

function _renderDashFiles(id, files) {
  const el = document.getElementById('dbfiles-' + id);
  if (!el) return;
  if (!files.length) { el.innerHTML = '<div class="dash-empty">Aucun fichier.</div>'; return; }
  let html = '<div class="dash-files">';
  files.forEach(f => {
    const name = typeof f === 'string' ? f : (f.path || f.name || String(f));
    const size = typeof f === 'object' && f.size ? _dFmtSize(f.size) : '';
    html += `<div class="dash-file-row">
      <span class="dash-file-ico">${_dFileIcon(name)}</span>
      <span class="dash-file-name" title="${_dEsc(name)}">${_dEsc(name)}</span>
      ${size ? `<span style="font-family:'DM Mono',monospace;font-size:10px;color:rgba(220,232,255,0.3)">${_dEsc(size)}</span>` : ''}
      <button class="dash-file-open" onclick="_dashOpenFile('${_dEsc(id)}','${_dEsc(name)}')">OUVRIR</button>
    </div>`;
  });
  html += '</div>';
  el.innerHTML = html;
}

window._dashKill = async (id) => {
  if (!confirm('Arrêter cette mission ?')) return;
  try {
    await fetch(`/api/projects/${id}/kill`, { method: 'POST' });
    await _renderDashMissions();
  } catch { /**/ }
};

window._dashOpenFile = async (projId, path) => {
  const modal = document.getElementById('dash-file-modal');
  if (!modal) return;
  document.getElementById('dash-file-modal-name').textContent = path;
  document.getElementById('dash-file-modal-body').innerHTML = '<div class="dash-loading">CHARGEMENT…</div>';
  modal.classList.add('open');
  try {
    const r = await fetch(`/api/projects/${projId}/files/${path}`);
    const d = await r.json();
    const ext = (path.split('.').pop() || '').toLowerCase();
    const isCode = ['py','js','ts','json','yaml','yml','sh','css','html','md','txt'].includes(ext);
    document.getElementById('dash-file-modal-body').innerHTML =
      isCode ? `<pre><code>${_dEsc(d.content||'')}</code></pre>` : `<p style="white-space:pre-wrap">${_dEsc(d.content||'')}</p>`;
  } catch(e) {
    document.getElementById('dash-file-modal-body').innerHTML = `<div class="dash-empty">Erreur : ${_dEsc(String(e))}</div>`;
  }
};

window._dashCloseFileModal = () => {
  document.getElementById('dash-file-modal')?.classList.remove('open');
};

/* ================================================================
   SECTION — DOMOTIQUE (placeholder)
   ================================================================ */
function _renderDomotique() {
  _dMain().innerHTML = `
    <div class="dash-section-hd">
      <span class="dash-section-title">Domotique</span>
    </div>
    <div class="dash-placeholder">
      <div class="dash-placeholder-icon">🏠</div>
      <div class="dash-placeholder-title">Domotique non configurée</div>
      <div class="dash-placeholder-desc">
        Connecte Home Assistant pour contrôler tes lumières,
        température et appareils depuis Jarvis.
      </div>
      <button class="dash-placeholder-btn" onclick="window.openSettings()">Configurer →</button>
    </div>`;
}

/* ================================================================
   SECTION — DEVICES (placeholder)
   ================================================================ */
function _renderDevices() {
  _dMain().innerHTML = `
    <div class="dash-section-hd">
      <span class="dash-section-title">Devices</span>
    </div>
    <div class="dash-placeholder">
      <div class="dash-placeholder-icon">🤖</div>
      <div class="dash-placeholder-title">Aucun device connecté</div>
      <div class="dash-placeholder-desc">
        Connecte des devices physiques (bras robotisé Alfred, ESP32, lunettes)
        pour les piloter depuis Jarvis.
      </div>
      <button class="dash-placeholder-btn" onclick="window.openSettings()">En savoir plus →</button>
    </div>`;
}

/* ================================================================
   SECTION — ANALYTICS
   ================================================================ */
async function _renderAnalytics() {
  const main = _dMain();
  main.innerHTML = '<div class="dash-loading">CHARGEMENT…</div>';

  const [jarvisResult, ytResult] = await Promise.allSettled([
    fetch(`/api/analytics/jarvis?days=30`).then(r => r.json()),
    fetch(`/api/analytics/youtube?days=7`).then(r => r.json()),
  ]);

  const jarvis = jarvisResult.status === 'fulfilled' ? jarvisResult.value : null;
  const yt     = ytResult.status === 'fulfilled' ? ytResult.value : null;

  const fNum = (n) => (n || 0).toLocaleString('fr-FR');

  // YouTube block
  let ytHtml = '';
  if (!yt || !yt.configured) {
    ytHtml = `
      <div class="analytics-not-configured">
        <span class="analytics-warn-icon">⚠</span>
        <span class="analytics-not-configured-text">API non configurée (YOUTUBE_API_KEY)</span>
        <button class="analytics-config-link" onclick="window.openSettings()">Configurer →</button>
      </div>`;
  } else {
    const topTitle = yt.top_video ? _dEsc(yt.top_video.title) : 'Non disponible';
    const topViews = yt.top_video ? fNum(yt.top_video.views) + ' vues' : '—';
    ytHtml = `
      <div class="analytics-grid">
        <div class="analytics-row">
          <span class="analytics-label">Abonnés</span>
          <span class="analytics-value">${fNum(yt.subscribers)}</span>
        </div>
        <div class="analytics-row">
          <span class="analytics-label">Vues totales</span>
          <span class="analytics-value">${fNum(yt.total_views)}</span>
        </div>
        <div class="analytics-row" style="grid-column:1/-1">
          <span class="analytics-label">Vidéo top</span>
          <span style="font-family:'DM Mono',monospace;font-size:11px;color:#DCE8FF">${topTitle} · ${topViews}</span>
        </div>
      </div>`;
  }

  // Jarvis stats block
  let jarvisHtml = '<div class="dash-empty">Données indisponibles.</div>';
  if (jarvis) {
    jarvisHtml = `
      <div class="analytics-grid">
        <div class="analytics-row">
          <span class="analytics-label">Conversations (30j)</span>
          <span class="analytics-value">${fNum(jarvis.sessions)}</span>
        </div>
        <div class="analytics-row">
          <span class="analytics-label">Missions lancées</span>
          <span class="analytics-value">${fNum(jarvis.missions)}</span>
        </div>
        <div class="analytics-row">
          <span class="analytics-label">Tokens utilisés</span>
          <span class="analytics-value">${fNum(jarvis.total_tokens)}</span>
        </div>
        <div class="analytics-row">
          <span class="analytics-label">Coût total</span>
          <span class="analytics-value" style="color:#C9A84C">$${(jarvis.total_cost_usd||0).toFixed(4)}</span>
        </div>
        <div class="analytics-row" style="grid-column:1/-1">
          <span class="analytics-label">Modèle principal</span>
          <span style="font-family:'DM Mono',monospace;font-size:11px;color:#DCE8FF">${_dEsc(jarvis.top_model)}</span>
        </div>
      </div>`;
  }

  main.innerHTML = `
    <div class="dash-section-hd">
      <span class="dash-section-title">Analytics</span>
    </div>

    <div class="analytics-block">
      <div class="analytics-block-title">YOUTUBE — BarthH95</div>
      ${ytHtml}
    </div>

    <div class="analytics-block">
      <div class="analytics-block-title">JARVIS — Activité (30 jours)</div>
      ${jarvisHtml}
    </div>`;
}

/* ================================================================
   INIT
   ================================================================ */
document.addEventListener('DOMContentLoaded', () => {
  // File modal backdrop click
  document.getElementById('dash-file-modal')?.addEventListener('click', e => {
    if (e.target.id === 'dash-file-modal') window._dashCloseFileModal();
  });

  // Escape closes dashboard or file modal
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      if (document.getElementById('dash-file-modal')?.classList.contains('open')) {
        window._dashCloseFileModal();
        return;
      }
      if (window._currentView === 'dashboard') {
        window.closeDashboard();
      }
    }
  });

  // WS bridge — live project updates
  window.addEventListener('jarvis:ws', (e) => {
    const msg = e.detail;
    if (!msg) return;
    const t = msg.type;
    if (['project_created','project_update','project_done','project_event'].includes(t)) {
      const proj = msg.project || msg;
      if (proj && proj.id) {
        const idx = _dash.projects.findIndex(p => p.id === proj.id);
        if (idx >= 0) Object.assign(_dash.projects[idx], proj);
        else _dash.projects.unshift(proj);
        if (_dash.section === 'missions' && document.getElementById('dashboard-view')?.classList.contains('visible')) {
          _paintDashMissions();
        }
      }
    }
  });
});
