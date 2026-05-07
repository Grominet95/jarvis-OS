/* ================================================================
   JARVIS V3 — Settings Page (settings.js)
   ================================================================ */
'use strict';

/* ── State ──────────────────────────────────────────────────── */
const _s = {
  tab:           'sessions',
  memTopics:     [],
  memIndexOpen:  false,
  sessions:      [],
  transcript:    null,
  tools:         [],
  skills:        [],
  sysStats:      null,
  sysLogs:       [],
  logsInterval:  null,
  consoData:     null,
  paramsData:    null,
  paramsDevices: { audio_input: [], audio_output: [], video: [] },
  apiKeysVisible: {},
  unsavedCount:  0,
};

/* ── Utils ──────────────────────────────────────────────────── */
const STEP_ICON = { running:'↻', done:'✓', failed:'✗', waiting:'⏸', paused:'⏸', skipped:'—', pending:'○' };
const FILE_ICON = { md:'📄',txt:'📄',json:'{}',py:'🐍',js:'📜',ts:'📜',html:'🌐',css:'🎨',csv:'📊',pdf:'📋',png:'🖼',jpg:'🖼' };

function _esc(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function _fileIcon(name) {
  const ext = (name.split('.').pop() || '').toLowerCase();
  return FILE_ICON[ext] || '📄';
}
function _fmtSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
  return (bytes/1024/1024).toFixed(2) + ' MB';
}
function _fmtCost(usd) {
  return '$' + (usd || 0).toFixed(4);
}
function _fmtNum(n) {
  if (!n) return '0';
  return n.toLocaleString('fr-FR');
}
function _content() { return document.getElementById('tab-content'); }

/* ── Toast ──────────────────────────────────────────────────── */
function toast(msg, type) {
  const wrap = document.getElementById('toast-container');
  if (!wrap) return;
  const el = document.createElement('div');
  el.className = 'toast-msg' + (type ? ' ' + type : '');
  el.textContent = msg;
  wrap.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateY(4px)'; el.style.transition = '0.2s'; setTimeout(() => el.remove(), 200); }, 2800);
}

/* ── Navigation ─────────────────────────────────────────────── */
function goBack() {
  const inIframe = window.self !== window.top;
  if (inIframe) {
    window.parent.postMessage('jarvis:close-settings', '*');
    return;
  }
  if (typeof gsap === 'undefined') { window.location.href = '/'; return; }
  gsap.timeline({ onComplete: () => { window.location.href = '/'; } })
    .to('body', { duration: 0.25, opacity: 0, scale: 1.03, filter: 'blur(8px)', ease: 'power2.in' });
}

/* ── Tab switching ──────────────────────────────────────────── */
function switchTab(name) {
  if (_s.logsInterval) { clearInterval(_s.logsInterval); _s.logsInterval = null; }
  _s.tab = name;
  document.querySelectorAll('.sidebar-item').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === name);
  });
  const c = _content();
  if (typeof gsap !== 'undefined') {
    gsap.to(c, { duration: 0.1, opacity: 0, onComplete: () => { _renderTab(name); gsap.to(c, { duration: 0.15, opacity: 1 }); } });
  } else {
    _renderTab(name);
  }
}

function _renderTab(name) {
  switch (name) {
    case 'memoire':  renderMemoire();  break;
    case 'sessions': renderSessions(); break;
    case 'outils':   renderOutils();   break;
    case 'conso':    renderConso();    break;
    case 'params':   renderParams();   break;
    case 'systeme':  renderSysteme();  break;
  }
}

/* ================================================================
   MISSIONS — déplacées dans dashboard.js
   (kept as no-op stub for any legacy callers)
   ================================================================ */
async function renderMissions() {
  _content().innerHTML = '<div class="empty">Les missions sont maintenant dans le Dashboard Pilotage (bouton ⚡).</div>';
}

function closeFileModal() { document.getElementById('file-modal').style.display = 'none'; }

/* ================================================================
   MÉMOIRE TAB
   ================================================================ */
async function renderMemoire() {
  _content().innerHTML = '<div class="loading">CHARGEMENT…</div>';
  try { const r = await fetch('/api/memory/topics'); _s.memTopics = await r.json(); }
  catch { _s.memTopics = []; }
  paintMemoire();
}

function paintMemoire() {
  let html = `
    <div class="tab-header">
      <span class="tab-title">MÉMOIRE</span>
      <button class="autodream-btn" id="autodream-btn" onclick="window._sAutoDream()">✦ AUTODREAM</button>
    </div>
    <div class="card-section-hd" style="border:1px solid rgba(74,158,255,0.10);border-radius:3px;padding:8px 12px;margin-bottom:10px;cursor:pointer"
         onclick="window._sToggleMemIndex()">
      <span class="card-section-arrow ${_s.memIndexOpen?'open':''}" id="memindex-arrow">▶</span>
      <span class="card-section-lbl">MEMORY.md</span>
      <span class="mem-edit" style="padding:2px 8px;border:1px solid rgba(74,158,255,0.1);border-radius:2px;cursor:pointer">INDEX</span>
    </div>
    <div id="memindex-wrap" style="display:${_s.memIndexOpen?'block':'none'}">
      <div class="inline-editor" id="memindex-editor">
        <div class="inline-editor-hd">
          <span class="inline-editor-name">MEMORY.md</span>
          <button class="editor-save" onclick="window._sSaveMemIndex()">Enregistrer</button>
          <span class="editor-saved" id="memindex-saved" style="display:none">✓</span>
        </div>
        <textarea class="editor-textarea" id="memindex-ta" spellcheck="false" placeholder="Chargement…"></textarea>
      </div>
    </div>
    <div class="sep"></div>
    <span class="section-lbl">TOPICS (${_s.memTopics.length})</span>`;

  if (!_s.memTopics.length) {
    html += '<div class="empty">AUCUN TOPIC</div>';
  } else {
    _s.memTopics.forEach(t => {
      const kb = (t.size / 1024).toFixed(1);
      const mtime = t.mtime ? t.mtime.slice(0, 10) : '';
      html += `
        <div class="mem-row">
          <span class="mem-name">${_esc(t.name)}</span>
          <span class="mem-meta">${_esc(kb)}k · ${_esc(mtime)}</span>
          <button class="mem-edit" onclick="window._sEditTopic('${_esc(t.name)}')">édit</button>
        </div>
        <div id="memeditor-${_esc(t.name)}" style="display:none"></div>`;
    });
  }
  _content().innerHTML = html;
  if (_s.memIndexOpen) _loadMemIndex();
}

window._sToggleMemIndex = async () => {
  _s.memIndexOpen = !_s.memIndexOpen;
  const wrap = document.getElementById('memindex-wrap');
  const arrow = document.getElementById('memindex-arrow');
  if (!wrap) return;
  wrap.style.display = _s.memIndexOpen ? 'block' : 'none';
  if (arrow) arrow.classList.toggle('open', _s.memIndexOpen);
  if (_s.memIndexOpen) await _loadMemIndex();
};

async function _loadMemIndex() {
  const ta = document.getElementById('memindex-ta');
  if (!ta) return;
  try { const r = await fetch('/api/memory/index'); const d = await r.json(); ta.value = d.content || ''; }
  catch { ta.value = ''; }
}

window._sSaveMemIndex = async () => {
  const ta = document.getElementById('memindex-ta');
  const saved = document.getElementById('memindex-saved');
  if (!ta) return;
  try {
    await fetch('/api/memory/index', { method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({content:ta.value}) });
    if (saved) { saved.style.display = ''; setTimeout(() => { saved.style.display = 'none'; }, 1500); }
    toast('Index enregistré', 'success');
  } catch { toast('Erreur sauvegarde', 'error'); }
};

window._sEditTopic = async (name) => {
  const wrap = document.getElementById('memeditor-' + name);
  if (!wrap) return;
  if (wrap.style.display !== 'none') { wrap.style.display = 'none'; return; }
  wrap.innerHTML = '<div class="loading">CHARGEMENT…</div>';
  wrap.style.display = 'block';
  try {
    const r = await fetch(`/api/memory/topics/${encodeURIComponent(name)}`);
    const d = await r.json();
    wrap.innerHTML = `<div class="inline-editor" style="margin-bottom:8px">
      <div class="inline-editor-hd">
        <span class="inline-editor-name">${_esc(name)}</span>
        <button class="editor-cancel" onclick="document.getElementById('memeditor-${_esc(name)}').style.display='none'">✕</button>
        <button class="editor-save" onclick="window._sSaveTopic('${_esc(name)}')">Enregistrer</button>
        <span class="editor-saved" id="saved-${_esc(name)}" style="display:none">✓</span>
      </div>
      <textarea class="editor-textarea" id="topicta-${_esc(name)}" spellcheck="false">${_esc(d.content||'')}</textarea>
    </div>`;
  } catch { wrap.innerHTML = '<div class="empty">Erreur chargement</div>'; }
};

window._sSaveTopic = async (name) => {
  const ta = document.getElementById('topicta-' + name);
  const saved = document.getElementById('saved-' + name);
  if (!ta) return;
  try {
    await fetch(`/api/memory/topics/${encodeURIComponent(name)}`, { method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({content:ta.value}) });
    if (saved) { saved.style.display=''; setTimeout(() => { saved.style.display='none'; }, 1500); }
    toast('Topic enregistré', 'success');
  } catch { toast('Erreur sauvegarde', 'error'); }
};

window._sAutoDream = async () => {
  const btn = document.getElementById('autodream-btn');
  if (btn) btn.classList.add('running');
  try { await fetch('/api/memory/autodream', {method:'POST'}); toast('AutoDream déclenché', 'success'); }
  catch { toast('Erreur AutoDream', 'error'); }
  setTimeout(() => { if (btn) btn.classList.remove('running'); }, 3000);
};

/* ================================================================
   SESSIONS TAB
   ================================================================ */
async function renderSessions() {
  if (_s.transcript) { paintTranscript(); return; }
  _content().innerHTML = '<div class="loading">CHARGEMENT…</div>';
  try { const r = await fetch('/api/sessions'); _s.sessions = await r.json(); }
  catch { _s.sessions = []; }
  paintSessions();
}

function paintSessions() {
  let html = `<div class="tab-header"><span class="tab-title">SESSIONS</span></div>`;
  const past = _s.sessions;
  if (!past.length) {
    html += '<div class="empty">AUCUNE SESSION</div>';
  } else {
    html += '<span class="section-lbl">HISTORIQUE</span>';
    past.forEach(s => {
      const displayTitle = _esc(s.title || s.preview);
      const safeTitle = (s.title || s.preview).replace(/\\/g,'\\\\').replace(/'/g,"\\'");
      html += `<div class="sess-past" id="sess-past-${_esc(s.id)}">
        <span class="sess-past-dot"></span>
        <div class="sess-past-info">
          <div class="sess-past-date" id="sess-title-${_esc(s.id)}">${displayTitle}</div>
          <div class="sess-past-meta">${_esc(s.date)} · ${s.message_count} msg</div>
        </div>
        <button class="mem-edit" style="flex-shrink:0" onclick="window._sRenameSession('${_esc(s.id)}','${safeTitle}')">renommer</button>
        <button class="sess-view-btn" onclick="window._sViewSession('${_esc(s.id)}','${safeTitle}',${s.message_count})">VOIR</button>
      </div>
      <div id="sess-rename-wrap-${_esc(s.id)}" style="display:none;padding:0 0 8px"></div>`;
    });
  }
  _content().innerHTML = html;
}

window._sRenameSession = (id, currentTitle) => {
  const wrap = document.getElementById('sess-rename-wrap-' + id);
  const titleEl = document.getElementById('sess-title-' + id);
  const pastRow = document.getElementById('sess-past-' + id);
  if (!wrap) return;
  if (wrap.style.display !== 'none' && wrap.querySelector('input')) { wrap.querySelector('input').focus(); return; }
  if (pastRow) pastRow.style.display = 'none';
  wrap.style.display = 'block';
  wrap.innerHTML = `<div class="inline-editor" style="margin:0">
    <div class="inline-editor-hd">
      <span class="inline-editor-name">TITRE</span>
      <button class="editor-cancel">✕</button>
      <button class="editor-save">Enregistrer</button>
    </div>
    <input style="width:100%;background:none;border:none;outline:none;font:400 12px/1.4 'DM Sans',sans-serif;color:rgba(200,220,255,0.85);padding:10px 12px" placeholder="Nom de la session…">
  </div>`;
  const inp = wrap.querySelector('input');
  inp.value = currentTitle;
  inp.focus(); inp.select();
  const cancel = () => { wrap.innerHTML=''; wrap.style.display='none'; if (pastRow) pastRow.style.display=''; };
  wrap.querySelector('.editor-cancel').onclick = cancel;
  inp.addEventListener('keydown', e => { if (e.key==='Escape') cancel(); });
  const save = async () => {
    const newTitle = inp.value.trim();
    if (!newTitle) return;
    try {
      await fetch(`/api/sessions/${encodeURIComponent(id)}/title`, { method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({title:newTitle}) });
      if (titleEl) titleEl.textContent = newTitle;
      const sess = _s.sessions.find(s => s.id === id);
      if (sess) sess.title = newTitle;
      toast('Session renommée', 'success');
    } catch { toast('Erreur renommage', 'error'); }
    cancel();
  };
  wrap.querySelector('.editor-save').onclick = save;
  inp.addEventListener('keydown', e => { if (e.key==='Enter') save(); });
};

window._sViewSession = async (id, date, count) => {
  _content().innerHTML = '<div class="loading">CHARGEMENT…</div>';
  try {
    const r = await fetch(`/api/sessions/${id}/messages?limit=50`);
    const messages = await r.json();
    _s.transcript = { id, date, count, messages };
    paintTranscript();
  } catch { toast('Erreur chargement session', 'error'); paintSessions(); }
};

function paintTranscript() {
  const t = _s.transcript;
  const sess = _s.sessions.find(s => s.id === t.id);
  const displayTitle = (sess && sess.title) ? sess.title : t.date;
  let html = `
    <button class="back-btn" onclick="window._sBackSessions()">← RETOUR</button>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:2px">
      <div class="transcript-hd" id="sess-title-${_esc(t.id)}" style="flex:1">${_esc(displayTitle)}</div>
      <button class="mem-edit" onclick="window._sRenameSession('${_esc(t.id)}','${_esc(displayTitle.replace(/'/g,"\\'"))}')">renommer</button>
    </div>
    <div id="sess-rename-wrap-${_esc(t.id)}"></div>
    <div class="transcript-meta">${t.count} messages · ${_esc(t.date)}</div>`;
  if (!t.messages || !t.messages.length) {
    html += '<div class="empty">AUCUN MESSAGE</div>';
  } else {
    t.messages.forEach(m => {
      const role = m.role === 'user' ? 'user' : 'jarvis';
      const content = typeof m.content === 'string' ? m.content
        : (Array.isArray(m.content) ? m.content.filter(c => c.type==='text').map(c => c.text).join('\n') : '');
      const ts = m.ts ? String(m.ts).slice(11,16) : '';
      html += `<div class="tx-msg">
        <div class="tx-hd">
          <span class="tx-role ${role}">${role==='user'?'VOUS':'JARVIS'}</span>
          ${ts ? `<span class="tx-ts">${_esc(ts)}</span>` : ''}
        </div>
        <div class="tx-body">${_esc(content.slice(0,600))}${content.length>600?'…':''}</div>
      </div>`;
    });
  }
  _content().innerHTML = html;
}

window._sBackSessions = () => { _s.transcript = null; paintSessions(); };

/* ================================================================
   OUTILS TAB
   ================================================================ */
async function renderOutils() {
  _content().innerHTML = '<div class="loading">CHARGEMENT…</div>';
  const [tr, sr] = await Promise.allSettled([
    fetch('/api/tools').then(r => r.json()),
    fetch('/api/skills').then(r => r.json()),
  ]);
  _s.tools  = tr.status === 'fulfilled' ? tr.value : [];
  _s.skills = sr.status === 'fulfilled' ? sr.value : [];
  paintOutils();
}

function paintOutils() {
  let html = `<div class="tab-header"><span class="tab-title">OUTILS</span></div>
    <span class="section-lbl">OUTILS ACTIFS (${_s.tools.length})</span>`;
  if (!_s.tools.length) {
    html += '<div class="empty">AUCUN OUTIL</div>';
  } else {
    _s.tools.forEach(t => {
      html += `<div class="tool-row">
        <span class="tool-dot"></span>
        <div style="flex:1">
          <div class="tool-name">${_esc(t.name)}</div>
          <div class="tool-desc">${_esc((t.description||'').slice(0,100))}</div>
        </div>
      </div>`;
    });
  }
  html += `<div class="sep"></div><span class="section-lbl">SKILLS ACTIFS (${_s.skills.length})</span>`;
  if (!_s.skills.length) {
    html += '<div class="empty">AUCUN SKILL</div>';
  } else {
    _s.skills.forEach(sk => {
      html += `<div class="tool-row">
        <span class="tool-dot" style="background:#B8963E;box-shadow:0 0 5px rgba(184,150,62,0.4)"></span>
        <div style="flex:1">
          <div class="tool-name">${_esc(sk.name)}</div>
          <div class="tool-desc">${_esc((sk.description||'').slice(0,100))}</div>
        </div>
        <button class="skill-del" onclick="window._sDeleteSkill('${_esc(sk.name)}')" title="Supprimer">✕</button>
      </div>`;
    });
  }
  html += `<button class="install-btn" onclick="window._sOpenClawHub()">✦ INSTALLER DEPUIS CLAWHUB</button>`;
  _content().innerHTML = html;
}

window._sDeleteSkill = async (name) => {
  if (!confirm(`Supprimer le skill "${name}" ?`)) return;
  try { await fetch(`/api/skills/${encodeURIComponent(name)}`, {method:'DELETE'}); toast(`Skill "${name}" supprimé`, 'success'); await renderOutils(); }
  catch { toast('Erreur suppression', 'error'); }
};

window._sOpenClawHub = async () => {
  const modal = document.getElementById('clawhub-modal');
  if (!modal) return;
  modal.style.display = 'flex';
  await _clawHubSearch('');
  const inp = document.getElementById('clawhub-search');
  if (inp) { inp.value=''; inp.oninput=() => _clawHubSearch(inp.value); inp.focus(); }
};

function closeClawHub() { document.getElementById('clawhub-modal').style.display='none'; }

async function _clawHubSearch(q) {
  const results = document.getElementById('clawhub-results');
  if (!results) return;
  results.innerHTML = '<div class="loading" style="padding:12px 16px">RECHERCHE…</div>';
  try {
    const r = await fetch(`/api/skills/clawhub/search?q=${encodeURIComponent(q)}`);
    const items = await r.json();
    if (!items.length) { results.innerHTML = '<div class="empty" style="padding:12px 16px">AUCUN RÉSULTAT</div>'; return; }
    results.innerHTML = items.map(item => `<div class="ch-item">
      <div class="ch-info">
        <div class="ch-slug">${_esc(item.slug)}</div>
        <div class="ch-desc">${_esc(item.description||'')}</div>
        <div class="ch-stars">★ ${_esc(String(item.stars||''))} · ${_esc(String(item.installs||''))} installs</div>
      </div>
      <button class="ch-install" id="ch-install-${_esc(item.slug)}" onclick="window._sInstallSkill('${_esc(item.slug)}')">INSTALL</button>
    </div>`).join('');
  } catch { results.innerHTML = '<div class="empty" style="padding:12px 16px">ERREUR</div>'; }
}

window._sInstallSkill = async (slug) => {
  const btn = document.getElementById('ch-install-' + slug);
  if (btn) btn.textContent = '…';
  try {
    const r = await fetch('/api/skills/install', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({source:'clawhub',value:slug}) });
    const d = await r.json();
    if (d.success) { if (btn) { btn.textContent='✓'; btn.classList.add('done'); } toast(`Skill "${slug}" installé`, 'success'); }
    else { if (btn) btn.textContent='INSTALL'; toast(d.message||'Erreur installation','error'); }
  } catch { if (btn) btn.textContent='INSTALL'; toast('Erreur réseau','error'); }
};

/* ================================================================
   CONSO TAB — Chart.js
   ================================================================ */

const _cjsInstances = {};

function _cjsDestroy(id) {
  if (_cjsInstances[id]) { _cjsInstances[id].destroy(); delete _cjsInstances[id]; }
}

const _PROV_NAMES  = { anthropic: 'Anthropic', elevenlabs: 'ElevenLabs', openai: 'OpenAI', deepgram: 'Deepgram' };
const _PROV_COLORS = {
  anthropic:  { bg: 'rgba(74,158,255,0.75)',  border: 'rgba(74,158,255,1)' },
  openai:     { bg: 'rgba(0,200,130,0.75)',   border: 'rgba(0,200,130,1)'  },
  elevenlabs: { bg: 'rgba(255,196,0,0.75)',   border: 'rgba(255,196,0,1)'  },
  deepgram:   { bg: 'rgba(180,100,255,0.75)', border: 'rgba(180,100,255,1)'},
};

const _GRID_COLOR  = 'rgba(74,158,255,0.06)';
const _TICK_COLOR  = 'rgba(255,255,255,0.35)';
const _FONT_MONO   = "'JetBrains Mono', monospace";

function _cjsScales(stacked = false) {
  return {
    x: { grid: { color: _GRID_COLOR }, ticks: { color: _TICK_COLOR, font: { size: 10, family: _FONT_MONO } }, stacked },
    y: { grid: { color: _GRID_COLOR }, ticks: { color: _TICK_COLOR, font: { size: 10, family: _FONT_MONO } }, stacked },
  };
}

function _cjsTooltip(extra = {}) {
  return {
    backgroundColor: 'rgba(8,14,28,0.95)',
    borderColor: 'rgba(74,158,255,0.3)',
    borderWidth: 1,
    titleColor: 'rgba(74,158,255,0.9)',
    bodyColor: 'rgba(255,255,255,0.85)',
    titleFont: { size: 11, family: _FONT_MONO },
    bodyFont: { size: 11, family: _FONT_MONO },
    ...extra,
  };
}

async function renderConso() {
  _content().innerHTML = '<div class="loading">Chargement…</div>';
  try {
    const [sessR, monthR, dailyR, callsR, dpR] = await Promise.allSettled([
      fetch('/api/conso/session').then(r => r.json()),
      fetch('/api/conso/monthly').then(r => r.json()),
      fetch('/api/conso/daily').then(r => r.json()),
      fetch('/api/conso/calls').then(r => r.json()),
      fetch('/api/conso/daily_providers').then(r => r.json()),
    ]);
    _s.consoData = {
      session:     sessR.status  === 'fulfilled' ? sessR.value  : {},
      monthly:     monthR.status === 'fulfilled' ? monthR.value : {},
      daily:       dailyR.status === 'fulfilled' ? dailyR.value : [],
      calls:       callsR.status === 'fulfilled' ? callsR.value : [],
      dailyByProv: dpR.status    === 'fulfilled' ? dpR.value    : [],
    };
  } catch {
    _s.consoData = { session: {}, monthly: {}, daily: [], calls: [], dailyByProv: [] };
  }
  paintConso();
}

const _PROV_COLORS_DOT = {
  anthropic:  '#4A9EFF',
  openai:     '#10A37F',
  elevenlabs: '#F5C842',
  deepgram:   '#A855F7',
};

function paintConso() {
  const { session, monthly, daily, calls, dailyByProv } = _s.consoData || {};

  const todayTokens  = (session || {}).total_tokens    || 0;
  const todayCalls   = (session || {}).total_api_calls || 0;
  const todayCost    = (session || {}).total_cost_usd  || 0;
  const todayChars   = (session || {}).total_tts_chars || 0;
  const providers    = (session || {}).providers       || {};

  const monthCost    = (monthly || {}).total_cost_usd  || 0;
  const monthLabel   = (monthly || {}).month           || '';

  let directCost = 0, indirectCost = 0;
  for (const c of (calls || [])) {
    const ctx = c.context || '';
    if (!ctx || ctx === 'conversation') directCost  += c.cost_usd || 0;
    else                                indirectCost += c.cost_usd || 0;
  }

  /* ── en-tête ── */
  let html = `
    <div class="tab-header">
      <span class="tab-title">Consommation & Coûts</span>
      <button class="btn" onclick="renderConso()" title="Actualiser" style="gap:6px">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
        </svg>
        Actualiser
      </button>
    </div>`;

  /* ── KPIs ── */
  html += `
    <div class="conso-kpi-grid">
      <div class="conso-kpi kpi-accent">
        <div class="conso-kpi-label">Aujourd'hui</div>
        <div class="conso-kpi-value cost">${_fmtCost(todayCost)}</div>
        <div class="conso-kpi-sub">${_fmtNum(todayCalls)} appels</div>
      </div>
      <div class="conso-kpi kpi-accent">
        <div class="conso-kpi-label">Ce mois</div>
        <div class="conso-kpi-value cost">${_fmtCost(monthCost)}</div>
        <div class="conso-kpi-sub">${_esc(monthLabel)}</div>
      </div>
      <div class="conso-kpi">
        <div class="conso-kpi-label">Tokens LLM</div>
        <div class="conso-kpi-value">${_fmtNum(todayTokens)}</div>
        <div class="conso-kpi-sub">aujourd'hui</div>
      </div>
      <div class="conso-kpi">
        <div class="conso-kpi-label">Chars TTS</div>
        <div class="conso-kpi-value">${_fmtNum(todayChars)}</div>
        <div class="conso-kpi-sub">aujourd'hui</div>
      </div>
      <div class="conso-kpi">
        <div class="conso-kpi-label">Appels API</div>
        <div class="conso-kpi-value">${_fmtNum(todayCalls)}</div>
        <div class="conso-kpi-sub">aujourd'hui</div>
      </div>
    </div>`;

  /* ── par provider ── */
  html += `<div class="conso-section-hd"><span class="conso-section-label">Par provider</span><div class="conso-section-rule"></div></div>`;

  const provEntries = Object.entries(providers);
  if (provEntries.length) {
    for (const [pk, pd] of provEntries) {
      const name  = _PROV_NAMES[pk] || pk;
      const dot   = _PROV_COLORS_DOT[pk] || '#8CA8CC';
      const color = pk === 'anthropic' ? '#4A9EFF'
                  : pk === 'openai'    ? '#10A37F'
                  : pk === 'elevenlabs'? '#F5C842'
                  : pk === 'deepgram'  ? '#A855F7'
                  : '#8CA8CC';

      html += `<div class="conso-provider-card">
        <div class="conso-provider-hd">
          <span class="conso-provider-dot" style="background:${dot};box-shadow:0 0 6px ${dot}80"></span>
          <span class="conso-provider-name" style="color:${color}">${_esc(name)}</span>
          <span class="conso-provider-subtotal">${_fmtCost(pd.total_cost)}</span>
        </div>`;

      for (const [mk, md] of Object.entries(pd.models || {})) {
        const stats = [];
        if (md.input_tokens)  stats.push(`<span class="conso-stat-pair"><span class="conso-stat-key">Input</span><span class="conso-stat-val">${_fmtNum(md.input_tokens)} tok</span></span>`);
        if (md.output_tokens) stats.push(`<span class="conso-stat-pair"><span class="conso-stat-key">Output</span><span class="conso-stat-val">${_fmtNum(md.output_tokens)} tok</span></span>`);
        if (md.characters)    stats.push(`<span class="conso-stat-pair"><span class="conso-stat-key">Chars</span><span class="conso-stat-val">${_fmtNum(md.characters)}</span></span>`);
        if (md.audio_minutes) stats.push(`<span class="conso-stat-pair"><span class="conso-stat-key">Audio</span><span class="conso-stat-val">${md.audio_minutes.toFixed(1)} min</span></span>`);
        if (md.images)        stats.push(`<span class="conso-stat-pair"><span class="conso-stat-key">Images</span><span class="conso-stat-val">${md.images}</span></span>`);
        stats.push(`<span class="conso-stat-pair"><span class="conso-stat-key">Appels</span><span class="conso-stat-val">${md.calls}</span></span>`);

        html += `<div class="conso-model-block">
          <div class="conso-model-name">${_esc(mk)}</div>
          <div class="conso-model-stats">${stats.join('')}</div>
        </div>`;
      }
      html += `</div>`;
    }
  } else {
    html += `<div class="empty">Aucune consommation enregistrée aujourd'hui.</div>`;
  }

  /* ── graphes ── */
  html += `
    <div class="conso-section-hd"><span class="conso-section-label">Analytiques</span><div class="conso-section-rule"></div></div>
    <div class="conso-charts-grid">
      <div class="conso-chart-card">
        <div class="conso-chart-title">Coût par jour — 7 jours</div>
        <div class="conso-chart-canvas-wrap"><canvas id="cjsCostDay"></canvas></div>
      </div>
      <div class="conso-chart-card">
        <div class="conso-chart-title">Direct / Indirect</div>
        <div class="conso-chart-canvas-wrap"><canvas id="cjsSplit"></canvas></div>
      </div>
      <div class="conso-chart-card conso-chart-wide">
        <div class="conso-chart-title">Tokens par provider — 7 jours</div>
        <div class="conso-chart-canvas-wrap"><canvas id="cjsProvTokens"></canvas></div>
      </div>
    </div>`;

  /* ── tableau appels ── */
  html += `<div class="conso-section-hd"><span class="conso-section-label">Appels récents</span><div class="conso-section-rule"></div></div>`;
  html += _renderCallsTable(calls || []);

  _content().innerHTML = html;

  requestAnimationFrame(() => {
    _initCostDayChart(daily || []);
    _initSplitDonut(directCost, indirectCost);
    _initProvTokensChart(dailyByProv || []);
  });
}

function _renderCallsTable(calls) {
  if (!calls.length) return '<div class="empty">Aucun appel enregistré aujourd\'hui</div>';
  const rows = calls.slice(0, 150).map(c => {
    const t  = (c.timestamp || '').replace('T', ' ').slice(11, 19);
    const tok = (c.input_tokens || c.output_tokens)
      ? `${_fmtNum(c.input_tokens || 0)}/${_fmtNum(c.output_tokens || 0)}`
      : c.characters ? `${_fmtNum(c.characters)}c`
      : c.audio_minutes ? `${c.audio_minutes.toFixed(2)}min`
      : '—';
    return `<tr>
      <td class="ct-time">${_esc(t)}</td>
      <td class="ct-prov">${_esc(c.provider || '')}</td>
      <td class="ct-model">${_esc((c.model || '').slice(0,22))}</td>
      <td class="ct-ctx">${_esc(c.context || 'conversation')}</td>
      <td class="ct-tok">${tok}</td>
      <td class="ct-cost">${_fmtCost(c.cost_usd || 0)}</td>
    </tr>`;
  }).join('');
  return `<div class="calls-table-wrap"><table class="calls-table">
    <thead><tr><th>HEURE</th><th>PROVIDER</th><th>MODÈLE</th><th>CONTEXTE</th><th>TOKENS/CHARS</th><th>COÛT</th></tr></thead>
    <tbody>${rows}</tbody>
  </table></div>`;
}

function _initCostDayChart(daily) {
  _cjsDestroy('cjsCostDay');
  const el = document.getElementById('cjsCostDay');
  if (!el) return;
  _cjsInstances['cjsCostDay'] = new Chart(el, {
    type: 'bar',
    data: {
      labels: daily.map(d => d.day),
      datasets: [{
        label: 'Coût USD',
        data: daily.map(d => d.cost_usd),
        backgroundColor: 'rgba(74,158,255,0.65)',
        borderColor: 'rgba(74,158,255,1)',
        borderWidth: 1,
        borderRadius: 3,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { ..._cjsTooltip(), callbacks: { label: ctx => ` $${(ctx.raw||0).toFixed(5)}` } },
      },
      scales: _cjsScales(),
    },
  });
}

function _initSplitDonut(direct, indirect) {
  _cjsDestroy('cjsSplit');
  const el = document.getElementById('cjsSplit');
  if (!el) return;
  const noData = direct === 0 && indirect === 0;
  _cjsInstances['cjsSplit'] = new Chart(el, {
    type: 'doughnut',
    data: {
      labels: ['Direct', 'Indirect'],
      datasets: [{
        data: noData ? [1, 0] : [direct, indirect],
        backgroundColor: noData
          ? ['rgba(255,255,255,0.08)', 'rgba(255,255,255,0.04)']
          : ['rgba(74,158,255,0.75)', 'rgba(255,196,0,0.75)'],
        borderColor: noData
          ? ['rgba(255,255,255,0.1)', 'transparent']
          : ['rgba(74,158,255,1)', 'rgba(255,196,0,1)'],
        borderWidth: 1,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      cutout: '62%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: 'rgba(255,255,255,0.45)', font: { size: 10, family: _FONT_MONO }, boxWidth: 10, padding: 12 },
        },
        tooltip: {
          ..._cjsTooltip(),
          callbacks: {
            label: ctx => noData ? ' Aucune donnée' : ` ${ctx.label}: $${(ctx.raw||0).toFixed(5)}`,
          },
        },
      },
    },
  });
}

function _initProvTokensChart(dailyByProv) {
  _cjsDestroy('cjsProvTokens');
  const el = document.getElementById('cjsProvTokens');
  if (!el) return;
  const labels = dailyByProv.map(d => d.day);
  const provKeys = ['anthropic', 'openai', 'elevenlabs', 'deepgram'];
  const datasets = provKeys
    .filter(p => dailyByProv.some(d => (d[p] || 0) > 0))
    .map(p => ({
      label: _PROV_NAMES[p] || p,
      data: dailyByProv.map(d => d[p] || 0),
      backgroundColor: (_PROV_COLORS[p] || { bg: 'rgba(200,200,200,0.5)' }).bg,
      borderColor:     (_PROV_COLORS[p] || { border: 'rgba(200,200,200,1)' }).border,
      borderWidth: 1,
      stack: 'tokens',
      borderRadius: 2,
    }));

  if (!datasets.length) {
    datasets.push({
      label: 'Aucune donnée',
      data: dailyByProv.map(() => 0),
      backgroundColor: 'rgba(255,255,255,0.06)',
      borderWidth: 0,
      stack: 'tokens',
    });
  }

  _cjsInstances['cjsProvTokens'] = new Chart(el, {
    type: 'bar',
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: 'rgba(255,255,255,0.45)', font: { size: 10, family: _FONT_MONO }, boxWidth: 10, padding: 10 },
        },
        tooltip: {
          ..._cjsTooltip(),
          callbacks: { label: ctx => ` ${ctx.dataset.label}: ${_fmtNum(ctx.raw||0)} tokens` },
        },
      },
      scales: _cjsScales(true),
    },
  });
}

/* ================================================================
   PARAMÈTRES TAB  — NOUVEAU
   ================================================================ */
async function renderParams() {
  _content().innerHTML = '<div class="loading">CHARGEMENT…</div>';
  try {
    const r = await fetch('/api/settings');
    _s.paramsData = await r.json();
  } catch { _s.paramsData = {}; }

  try {
    const allDevices = await navigator.mediaDevices.enumerateDevices();
    _s.paramsDevices = {
      audio_input:  allDevices.filter(d => d.kind === 'audioinput'),
      audio_output: allDevices.filter(d => d.kind === 'audiooutput'),
      video:        allDevices.filter(d => d.kind === 'videoinput'),
    };
  } catch { /**/ }

  paintParams();
}

function _toggle(key, initial) {
  const on = initial ? 'on' : '';
  return `<button class="toggle ${on}" id="toggle-${_esc(key)}" onclick="window._sToggleSetting('${_esc(key)}', this)"></button>`;
}

function _select(key, options, current) {
  return `<select class="params-select" onchange="window._sUpdateSetting('${_esc(key)}', this.value)">
    ${options.map(([v,l]) => `<option value="${_esc(v)}" ${v===current?'selected':''}>${_esc(l)}</option>`).join('')}
  </select>`;
}

function _numInput(key, value, width) {
  return `<input type="number" class="params-input" style="${width?`width:${width}px`:''}" value="${_esc(String(value))}"
    onchange="window._sUpdateSetting('${_esc(key)}', this.value)" onblur="window._sUpdateSetting('${_esc(key)}', this.value)">`;
}

function _row(label, control) {
  return `<div class="params-row"><span class="params-label">${_esc(label)}</span>${control}</div>`;
}

function _apiKeyRow(key, maskedValue) {
  const hasValue = maskedValue && maskedValue.length > 0;
  return `<div class="params-row">
    <span class="params-label">${_esc(key)}</span>
    <div class="params-key-wrap" id="key-wrap-${_esc(key)}">
      <span class="params-key-value">${_esc(hasValue ? maskedValue : '—')}</span>
      <button class="params-key-btn" onclick="window._sEditKey('${_esc(key)}')" title="Modifier">✎</button>
      <button class="params-key-btn" onclick="window._sRevealKey('${_esc(key)}')" title="${_s.apiKeysVisible[key] ? 'Masquer' : 'Voir'}">${_s.apiKeysVisible[key] ? '◎' : '👁'}</button>
    </div>
  </div>`;
}

function _section(id, title, open, rows) {
  return `<div class="params-section" id="psec-${_esc(id)}">
    <div class="params-section-hd" onclick="toggleParamsSection('${_esc(id)}')">
      <span class="params-section-arrow ${open?'open':''}" id="psec-arrow-${_esc(id)}">${open?'▼':'▶'}</span>
      <span class="params-section-title">${_esc(title)}</span>
    </div>
    <div class="params-section-body" id="psec-body-${_esc(id)}" style="display:${open?'block':'none'}">
      ${rows}
    </div>
  </div>`;
}

function toggleParamsSection(id) {
  const body = document.getElementById('psec-body-' + id);
  const arrow = document.getElementById('psec-arrow-' + id);
  if (!body) return;
  const open = body.style.display !== 'none';
  body.style.display = open ? 'none' : 'block';
  if (arrow) { arrow.textContent = open ? '▶' : '▼'; arrow.classList.toggle('open', !open); }
}

function paintParams() {
  const p = _s.paramsData || {};
  const audio   = p.audio   || {};
  const llm     = p.llm     || {};
  const apiKeys = p.api_keys || {};
  const docker  = p.docker  || {};
  const proact  = p.proactive || {};
  const vision  = p.vision  || {};
  const jarvis  = p.jarvis  || {};
  const devs    = _s.paramsDevices;

  const micOptions = [['default','Par défaut']].concat((devs.audio_input||[]).map(d => [d.deviceId, d.label||d.deviceId.slice(0,20)]));
  const spkOptions = [['default','Par défaut']].concat((devs.audio_output||[]).map(d => [d.deviceId, d.label||d.deviceId.slice(0,20)]));
  const camOptions = [['default','Par défaut']].concat((devs.video||[]).map(d => [d.deviceId, d.label||d.deviceId.slice(0,20)]));

  let html = `<div class="tab-header"><span class="tab-title">PARAMÈTRES</span></div>`;

  html += _section('audio', '▼ AUDIO & VOIX', true, [
    _row('Microphone',       _select('MICROPHONE', micOptions, 'default')),
    _row('Haut-parleurs',    _select('SPEAKERS', spkOptions, 'default')),
    _row('Caméra',           _select('CAMERA_DEVICE', camOptions, 'default')),
    _row('Provider TTS',     _select('TTS_PROVIDER', [['elevenlabs','ElevenLabs'],['piper','Piper']], audio.tts_provider||'piper')),
    _row('Modèle ElevenLabs', _select('ELEVENLABS_MODEL', [['eleven_flash_v2_5','Flash v2.5 (~75ms)'],['eleven_turbo_v2_5','Turbo v2.5 (~300ms)']], audio.elevenlabs_model||'eleven_flash_v2_5')),
    _row('Modèle STT',       _select('WHISPER_MODEL', [['nova-2','Deepgram Nova-2'],['tiny','Whisper Tiny'],['small','Whisper Small'],['medium','Whisper Medium']], audio.whisper_model||'tiny')),
  ].join(''));

  html += _section('llm', '▼ MODÈLES IA', false, [
    _row('Provider LLM',     _select('LLM_PROVIDER', [['api','Anthropic'],['local','Local (Ollama)']], llm.llm_provider||'api')),
    _row('Modèle principal', _select('ANTHROPIC_MODEL', [['claude-sonnet-4-6','Claude Sonnet 4.6'],['claude-haiku-4-5-20251001','Claude Haiku 4.5'],['claude-opus-4-7','Claude Opus 4.7']], llm.anthropic_model||'claude-sonnet-4-6')),
    _row('Modèle vocal',     _select('VOICE_ANTHROPIC_MODEL', [['claude-haiku-4-5-20251001','Claude Haiku 4.5'],['claude-sonnet-4-6','Claude Sonnet 4.6']], llm.voice_anthropic_model||'claude-haiku-4-5-20251001')),
    _row('Modèle vision',    _select('VISION_MODEL', [['gpt-4o','GPT-4o'],['gpt-4o-mini','GPT-4o Mini']], llm.vision_model||'gpt-4o')),
  ].join(''));

  html += _section('apikeys', '▼ CLÉS API', false,
    Object.entries(apiKeys).map(([key, val]) => _apiKeyRow(key, val)).join('')
  );

  html += _section('docker', '▼ AGENT WORKER', false, [
    _row('Docker activé',    _toggle('DOCKER_ENABLED', docker.docker_enabled)),
    _row('Image Docker',     `<input type="text" class="params-input-text" value="${_esc(docker.docker_base_image||'python:3.11-slim')}" onchange="window._sUpdateSetting('DOCKER_BASE_IMAGE', this.value)">`),
    _row('Mémoire max',      _select('DOCKER_MEMORY_LIMIT', [['256m','256 MB'],['512m','512 MB'],['1g','1 GB'],['2g','2 GB']], docker.docker_memory_limit||'512m')),
    _row('CPU max',          _select('DOCKER_CPU_LIMIT', [['0.5','0.5'],['1.0','1.0'],['2.0','2.0']], String(docker.docker_cpu_limit||'1.0'))),
    _row('Timeout par step', _numInput('DOCKER_TIMEOUT_SECONDS', docker.docker_timeout_seconds||300, 80)),
  ].join(''));

  html += _section('proactive', '▼ PROACTIVITÉ', false, [
    _row('Heure briefing',   _numInput('BRIEFING_HOUR', proact.briefing_hour||9, 60)),
    _row('Rappel calendrier',_numInput('CALENDAR_REMINDER_MINUTES', proact.calendar_reminder_minutes||10, 60)),
  ].join(''));

  html += _section('vision', '▼ VISION', false, [
    _row('Détection objets YOLO', _toggle('VISION_OBJECT_DETECTION', vision.vision_object_detection)),
    _row('Index webcam',          _numInput('VISION_WEBCAM_INDEX', vision.vision_webcam_index||0, 60)),
    _row('Seuil confiance YOLO',  `<input type="range" class="params-slider" min="0.1" max="1.0" step="0.05" value="${_esc(String(vision.vision_yolo_confidence||0.5))}" onchange="window._sUpdateSetting('VISION_YOLO_CONFIDENCE', this.value)">`),
  ].join(''));

  html += _section('jarvis', '▼ JARVIS', false, [
    _row('Mode Québécois 🍁', _toggle('QUEBEC_MODE', jarvis.quebec_mode)),
    _row('Niveau log',  _select('LOG_LEVEL', [['DEBUG','DEBUG'],['INFO','INFO'],['WARNING','WARNING'],['ERROR','ERROR']], jarvis.log_level||'INFO')),
    _row('Environnement', `<span style="font-family:'DM Mono',monospace;font-size:10px;color:var(--text-dim)">${_esc(jarvis.environment||'development')}</span>`),
  ].join(''));

  const appr = p.approvals || {};
  const _appr = (cat, label) => _row(label, _approvalSelect(cat, appr[cat] || 'ask'));
  html += _section('approvals', '▼ APPROBATIONS', false, [
    '<div class="params-subsection">Système</div>',
    _appr('system_shutdown', 'Éteindre / Veille'),
    _appr('system_restart',  'Redémarrage'),
    '<div class="params-subsection">Fichiers</div>',
    _appr('file_write',  'Écrire des fichiers'),
    _appr('file_delete', 'Supprimer des fichiers'),
    '<div class="params-subsection">Communications</div>',
    _appr('email_draft', 'Rédiger un email'),
    _appr('email_send',  'Envoyer un email'),
    '<div class="params-subsection">Web</div>',
    _appr('web_agent', 'Automatisation browser'),
    '<div class="params-subsection">Matériel</div>',
    _appr('printer_slice', 'Slicer un modèle 3D'),
    _appr('printer_print', 'Lancer une impression'),
    _appr('fusion_create', 'Créer dans Fusion 360'),
    _appr('fusion_modify', 'Modifier dans Fusion 360'),
    _appr('fusion_delete', 'Supprimer dans Fusion 360'),
    '<div class="params-subsection">Code / Agent</div>',
    _appr('code_write',    'Écrire du code'),
    _appr('agent_mission', 'Lancer une mission agent'),
  ].join(''));

  _content().innerHTML = html;
}

function _approvalSelect(category, value) {
  const opts = [['always','Toujours'],['ask','Demander'],['never','Jamais']];
  const sel = opts.map(([v, l]) =>
    `<option value="${v}" ${v === value ? 'selected' : ''}>${l}</option>`
  ).join('');
  return `<select class="params-select" onchange="window._sUpdateApproval('${_esc(category)}', this.value)">${sel}</select>`;
}

window._sUpdateApproval = async (category, mode) => {
  try {
    const r = await fetch(`/api/approvals/config/${encodeURIComponent(category)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    });
    if (!r.ok) throw new Error(await r.text());
    toast(`${category} → ${mode}`, 'success');
  } catch (e) { toast(`Erreur: ${e.message}`, 'error'); }
};

window._sUpdateSetting = async (key, value) => {
  try {
    const r = await fetch('/api/settings/update', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({key, value: String(value)}) });
    const d = await r.json();
    toast(`${key} mis à jour${d.needs_restart ? ' · Restart requis' : ''}`, 'success');
  } catch { toast(`Erreur mise à jour de ${key}`, 'error'); }
};

window._sToggleSetting = async (key, btn) => {
  const isOn = btn.classList.toggle('on');
  await window._sUpdateSetting(key, isOn ? 'true' : 'false');
};

window._sEditKey = (key) => {
  const wrap = document.getElementById('key-wrap-' + key);
  if (!wrap) return;
  wrap.innerHTML = `<div class="params-key-edit-wrap">
    <input type="password" class="params-key-input" id="key-input-${_esc(key)}" placeholder="Nouvelle valeur…">
    <button class="params-key-save" onclick="window._sSaveKey('${_esc(key)}')">Sauvegarder</button>
    <button class="params-key-cancel" onclick="window._sCancelKey('${_esc(key)}')">✕</button>
  </div>`;
  const inp = document.getElementById('key-input-' + key);
  if (inp) { inp.focus(); inp.addEventListener('keydown', e => { if (e.key==='Enter') window._sSaveKey(key); if (e.key==='Escape') window._sCancelKey(key); }); }
};

window._sSaveKey = async (key) => {
  const inp = document.getElementById('key-input-' + key);
  if (!inp || !inp.value.trim()) { window._sCancelKey(key); return; }
  await window._sUpdateSetting(key, inp.value.trim());
  // Re-fetch masked value and repaint
  const r = await fetch('/api/settings');
  _s.paramsData = await r.json();
  paintParams();
};

window._sCancelKey = (key) => {
  const r = async () => { const res = await fetch('/api/settings'); _s.paramsData = await res.json(); paintParams(); };
  r();
};

window._sRevealKey = async (key) => {
  // Toggle visibility flag — for now just re-render (real reveal needs server support)
  _s.apiKeysVisible[key] = !_s.apiKeysVisible[key];
  paintParams();
};

/* ================================================================
   SYSTÈME TAB  (porté depuis panel.js → _renderSys)
   ================================================================ */
async function renderSysteme() {
  _content().innerHTML = '<div class="loading">CHARGEMENT…</div>';
  try { const r = await fetch('/api/system/stats'); _s.sysStats = await r.json(); }
  catch { _s.sysStats = null; }
  await _fetchSysLogs();
  paintSysteme();
  _startLogsPolling();
}

async function _fetchSysLogs() {
  try { const r = await fetch('/api/system/logs'); _s.sysLogs = await r.json(); }
  catch { _s.sysLogs = []; }
}

function _startLogsPolling() {
  if (_s.logsInterval) clearInterval(_s.logsInterval);
  _s.logsInterval = setInterval(async () => {
    if (_s.tab !== 'systeme') { clearInterval(_s.logsInterval); _s.logsInterval = null; return; }
    await _fetchSysLogs();
    const el = document.getElementById('sys-logs');
    if (el) _renderLogsInto(el);
  }, 3000);
}

function _renderLogsInto(el) {
  el.innerHTML = _s.sysLogs.slice(-60).map(line => {
    const lvl = /WARNING|ERROR|CRITICAL/.test(line) ? 'level-WARNING' : /INFO/.test(line) ? 'level-INFO' : '';
    return `<div class="sys-log-line ${lvl}">${_esc(line)}</div>`;
  }).join('');
  el.scrollTop = el.scrollHeight;
}

function paintSysteme() {
  const st  = _s.sysStats;
  const cfg  = st ? st.config   : {};
  const mem  = st ? st.memory   : {};
  const sess = st ? st.sessions : {};
  const proj = st ? st.projects : {};

  let html = `
    <div class="tab-header"><span class="tab-title">SYSTÈME</span></div>

    <span class="section-lbl">CONFIGURATION ACTIVE</span>
    <div class="sys-grid">
      <span class="sys-key">LLM Provider</span><span class="sys-val">${_esc(cfg.llm_provider||'—')}</span>
      <span class="sys-key">Modèle</span><span class="sys-val">${_esc(cfg.model||'—')}</span>
      <span class="sys-key">Voice LLM</span><span class="sys-val">${_esc(cfg.voice_model||'—')}</span>
      <span class="sys-key">Vision</span><span class="sys-val">${_esc(cfg.vision_model||'—')}</span>
      <span class="sys-key">TTS</span><span class="sys-val">${_esc(cfg.tts_provider||'—')}</span>
      <span class="sys-key">STT</span><span class="sys-val">${_esc(cfg.whisper_model||'—')}</span>
    </div>
    <div class="sep"></div>

    <span class="section-lbl">RESSOURCES</span>
    <div class="sys-grid">
      <span class="sys-key">Mémoire topics</span><span class="sys-val">${mem.topics??'—'} fichiers · ${mem.size_kb??'—'} KB</span>
      <span class="sys-key">Sessions</span><span class="sys-val">${sess.total??'—'} · ${sess.size_mb??'—'} MB</span>
      <span class="sys-key">Projets</span><span class="sys-val">${proj.total??'—'} total (${proj.running??0} en cours)</span>
      <span class="sys-key">Workspace</span><span class="sys-val" style="font-size:9px">${_esc(st?.workspace||'workspace/projects/')}</span>
    </div>
    <div class="sep"></div>

    <span class="section-lbl">SANTÉ DU SYSTÈME</span>
    <div class="health-row"><span class="health-dot"></span><span class="health-name">FastAPI</span><span class="health-desc">En ligne · port 8000</span></div>
    <div class="health-row"><span class="health-dot"></span><span class="health-name">Memory</span><span class="health-desc">${mem.topics??0} topics chargés</span></div>
    <div class="health-row"><span class="health-dot off"></span><span class="health-name">Voice Agent</span><span class="health-desc">Voir logs LiveKit</span></div>
    <div class="sep"></div>

    <span class="section-lbl">ACTIONS</span>
    <button class="action-btn" onclick="window._sSysAutodream()">✦ Déclencher AutoDream</button>
    <button class="action-btn" onclick="window._sSysReloadSkills()">↻ Recharger les Skills</button>
    <button class="action-btn" onclick="window._sSysCleanup()">🗑 Nettoyer projets terminés</button>
    <button class="action-btn danger" onclick="window._sSysRestart()">⚡ Redémarrer Jarvis</button>
    <div class="sep"></div>

    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
      <span class="section-lbl" style="margin:0">LOGS SYSTÈME EN DIRECT</span>
      <button class="btn" style="padding:3px 8px;font-size:8px" onclick="window._sRefreshLogs()">↺ Refresh</button>
    </div>
    <div class="sys-logs" id="sys-logs"></div>`;

  _content().innerHTML = html;
  const logsEl = document.getElementById('sys-logs');
  if (logsEl) _renderLogsInto(logsEl);
}

window._sSysAutodream = async () => {
  try { await fetch('/api/memory/autodream', {method:'POST'}); toast('AutoDream déclenché', 'success'); }
  catch { toast('Erreur', 'error'); }
};

window._sSysReloadSkills = async () => {
  try { const r = await fetch('/api/skills/reload', {method:'POST'}); const d = await r.json(); toast(`${d.count} skills rechargés`, 'success'); }
  catch { toast('Erreur', 'error'); }
};

window._sSysCleanup = async () => {
  if (!confirm('Supprimer tous les projets terminés ?')) return;
  try { const r = await fetch('/api/system/projects/done', {method:'DELETE'}); const d = await r.json(); toast(`${d.removed} projet(s) supprimé(s)`, 'success'); }
  catch { toast('Erreur', 'error'); }
};

window._sSysRestart = async () => {
  if (!confirm('Redémarrer Jarvis ?')) return;
  try { await fetch('/api/system/restart', {method:'POST'}); toast('Redémarrage en cours…', ''); }
  catch { toast('Erreur', 'error'); }
};

window._sRefreshLogs = async () => {
  await _fetchSysLogs();
  const el = document.getElementById('sys-logs');
  if (el) _renderLogsInto(el);
};

/* ================================================================
   INIT
   ================================================================ */
document.addEventListener('DOMContentLoaded', () => {
  // Entry animation
  if (typeof gsap !== 'undefined') {
    gsap.from('body', { duration: 0.4, opacity: 0, scale: 0.97, filter: 'blur(10px)', ease: 'power2.out' });
  }

  // Wire modal backdrop clicks
  document.getElementById('file-modal')?.addEventListener('click', e => {
    if (e.target.id === 'file-modal') closeFileModal();
  });
  document.getElementById('clawhub-modal')?.addEventListener('click', e => {
    if (e.target.id === 'clawhub-modal') closeClawHub();
  });

  // Keyboard
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { closeFileModal(); closeClawHub(); }
  });

  // Load initial tab
  switchTab(_s.tab);
});
