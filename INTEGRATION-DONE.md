# Handoff Integration — DONE

Date: 2026-05-07  
Source: `/Users/barthhouot/Downloads/handoff/`

---

## Files created / replaced

| File | Action |
|---|---|
| `ui/static/dashboard.html` | New — copied from handoff, paths made absolute |
| `ui/static/dashboard.js` | New — copied from handoff, API wired (see below) |
| `ui/static/dashboard.css` | New — copied from handoff |
| `ui/static/settings.html` | New — copied from handoff, paths absolute + modals added |
| `ui/static/settings.js` | New — copied from handoff, API wired (see below) |
| `ui/static/settings.css` | New — copied from handoff |
| `ui/static/_shared.css` | New — copied from handoff |
| `ui/static/_shared.js` | New — copied from handoff |
| `ui/static/settings-charts.js` | New — copied from handoff |

## Backups

| Backup | Original |
|---|---|
| `ui/static/dashboard.old.css` | old dashboard.css |
| `ui/static/dashboard.old.js` | old dashboard.js |
| `ui/static/settings.old.html` | old settings.html |
| `ui/static/settings.old.css` | old settings.css |
| `ui/static/settings.old.js` | old settings.js |

## Backend changes

### `api/http.py`
- Added `_versioned_html()` helper — injects `?v=<mtime>` cache-busting on all asset URLs
- Added `GET /dashboard` route — serves `dashboard.html` with cache-busting headers
- Added `GET /settings` route — serves `settings.html` with cache-busting headers
- Assets covered: `_shared.css`, `_shared.js`, `dashboard.css`, `dashboard.js`, `settings.css`, `settings-charts.js`, `settings.js`

### `api/websocket.py`
- Added `WS /ws/logs` — streams log lines from `_log_buffer` in real time
- Format pushed: `{ lv: "ok"|"info"|"warn"|"err", parts: [{t: string, cls?: "accent"|"dim"}] }`
- On connect: replays last 50 buffered lines, then polls every 0.8s for new entries

### `ui/static/index.html`
- Removed `<link>` and `<script>` tags for old `dashboard.css` / `dashboard.js`
- Removed entire `#dashboard-view` DOM overlay block
- Removed `#dash-file-modal` DOM block
- Changed `#dashboard-nav-btn` onclick to `window.location.href='/dashboard'`
- Removed `openDashboard` / `closeDashboard` stubs
- Removed all `_currentView === 'dashboard'` guards from `handleGlobeClick`, `handleIntelClick`, `handleSphereClick`
- Updated `navigateFromIntel('dashboard')` to `window.location.href = '/dashboard'`

---

## API shape transformations

### `dashboard.js` — `loadInitiatives()`
**Endpoint:** `GET /api/initiatives`  
```
// SHAPE EXPECTED: [{id, title, tags:[], progress:0-100, priority:"high"|"med"|"low"}]
// Backend returns: [{id, title, tags, progress, priority:"haute"|"moyen"|"basse"}]
// Transform: priority "haute"→"high", "moyen"→"med", "basse"→"low"
```

### `dashboard.js` — `loadMissions()`
**Endpoint:** `GET /api/projects`  
```
// SHAPE EXPECTED: [{id, title, status:"run"|"wait"|"queue", agent, steps:[]}]
// Backend returns: [{id, title, status:"running"|"planning"|"waiting"|"queued"|"done"|"failed"|"killed", agent, steps}]
// Transform: filter out done/failed/killed; running|planning→"run", waiting→"wait", queued→"queue"
```

### `dashboard.js` — `loadAnalytics()`
**Endpoints:** `GET /api/analytics/jarvis?days=30`, `GET /api/analytics/youtube?days=7`  
```
// SHAPE EXPECTED: kpis:[{label,value,delta,unit}], sources:[{label,pct}], top:[{label,value}]
// Backend: /api/analytics/jarvis → {sessions, messages, tokens_used, tts_chars, ...}
//          /api/analytics/youtube → {views, subs_gained, watch_hours, ...}
// Transforms documented in loadAnalytics() inline comments
```

### `settings.js` — `renderSessions()`
**Endpoint:** `GET /api/sessions`  
```
// SHAPE EXPECTED: [{id(6 chars), agent, start, calls}]
// Backend returns: [{id, date, preview, title, message_count}]
// Transform: id→id.slice(0,6), title→agent, date→start, message_count→calls
```

### `settings.js` — `renderMemory()`
**Endpoint:** `GET /api/memory/topics`  
```
// SHAPE EXPECTED: [{id, group, name, path, size, pin, body}]
// Backend returns: [{name, size, mtime}]
// Transform: name→id&name, "global"→group, size kept, pin=false, body=null (loaded on-demand)
// On-demand viewer: GET /api/memory/topics/{name}
```

### `settings.js` — `renderTools()`
**Endpoint:** `GET /api/tools`  
```
// SHAPE EXPECTED: [{glyph(3 chars), name, sub, calls, lat, on}]
// Backend returns: [{name, description}]
// Transform: name.slice(0,3).toUpperCase()→glyph, description→sub, calls=0, lat="—", on=true
```

### `settings.js` — `renderConso()`
**Endpoints:** `GET /api/conso/session`, `GET /api/conso/monthly`, `GET /api/conso/daily`  
```
// SHAPE EXPECTED: single /api/conso?range=30d with {total, budget, pct, today, tokens, forecast, series:[{label,usd}], providers:[{name,pct}]}
// Backend: three separate endpoints; merged in renderConso()
// Hero vars (heroTotal, heroBudget, heroPct, heroToday, heroTokens, heroForecast) computed from merged data
```

---

## TODOs / mocks left

| Section | Mock constant | Reason left |
|---|---|---|
| `dashboard.js` loadDevices() | `MOCK_DEVICES` | No `/api/devices` endpoint exists yet |
| `dashboard.js` loadAnalytics() | `MOCK_TOP`, `MOCK_SOURCES` | Top queries / source breakdown not in analytics API |

---

## Navigation changes

| Old | New |
|---|---|
| `window.openDashboard()` (overlay) | `window.location.href = '/dashboard'` |
| `"dashboard.html"` in sidebar links | `"/dashboard"` |
| `"settings.html"` in sidebar links | `"/settings"` |
