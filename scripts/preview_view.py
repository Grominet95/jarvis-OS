#!/usr/bin/env python3
# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Prévisualise une vue Jarvis sans lancer le core complet (cf. CDC §2).

Usage :
    python scripts/preview_view.py ../jarvis-skills/views/ma-vue

Sert une page HTML qui charge le vrai _shared.js (donc le vrai contrat
Jarvis.views.register / activate / dispatch / deactivate), le view.js
cible, et expose une mini-UI pour envoyer les mêmes messages que Jarvis
en prod : `{type: "show_view"|"hide_view"|"view_command", view_id,
command, params}`. Un WebSocket local broadcast les messages — fidèle
au chemin home.js:696-705. Une commande inconnue est silencieusement
ignorée par le standard des vues.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, Response

REPO = Path(__file__).parent.parent
SHARED_JS = REPO / "src" / "jarvis" / "interfaces" / "ui" / "static" / "_shared.js"


def _index_html(view_id: str) -> str:
    return f"""<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8"><title>preview · {view_id}</title>
<style>
  :root {{
    --bg:#06080d; --fg:#dce8ff; --line:rgba(220,232,255,.1);
    --accent:#4A9EFF; --green:#36D399; --gold:#B8963E;
    --sans:"Geist",system-ui,sans-serif; --mono:"Geist Mono",monospace;
  }}
  html,body {{ height:100%; margin:0; background:var(--bg); color:var(--fg);
    font-family:var(--sans); }}
  body {{ display:grid; grid-template-columns:1fr 320px; }}
  #stage {{ position:relative; overflow:hidden; }}
  #panel {{
    background:#0a0d14; border-left:1px solid var(--line); padding:18px;
    display:flex; flex-direction:column; gap:14px;
    font-family:var(--mono); font-size:12px;
  }}
  #panel h2 {{
    font-size:11px; letter-spacing:.2em; text-transform:uppercase;
    color:rgba(220,232,255,.4); margin:0;
  }}
  #panel label {{ display:flex; flex-direction:column; gap:4px; }}
  #panel input, #panel textarea, #panel button {{
    background:#06080d; color:var(--fg); border:1px solid var(--line);
    border-radius:4px; padding:6px 8px; font:inherit;
  }}
  #panel textarea {{ min-height:80px; resize:vertical; }}
  #panel button {{ cursor:pointer; }}
  #panel button:hover {{ border-color:var(--accent); color:var(--accent); }}
  #panel .row {{ display:flex; gap:6px; }}
  #panel .row > * {{ flex:1; }}
  #log {{
    flex:1; overflow:auto; background:#06080d; border:1px solid var(--line);
    border-radius:4px; padding:8px; font-size:11px; white-space:pre-wrap;
  }}
  .muted {{ color:rgba(220,232,255,.4); }}
</style>
</head><body>
<div id="stage"></div>
<aside id="panel">
  <h2>preview · {view_id}</h2>
  <div class="row">
    <button data-action="show_view">show</button>
    <button data-action="hide_view">hide</button>
  </div>
  <label>command (view_command)
    <input id="cmd" type="text" placeholder="ex. fly_to" />
  </label>
  <label>params (JSON)
    <textarea id="params">{{}}</textarea>
  </label>
  <button id="send_cmd">send view_command</button>
  <h2 style="margin-top:4px">log</h2>
  <div id="log" class="muted">en attente…</div>
</aside>

<!-- Contrat Jarvis.views (vrai _shared.js, source unique de vérité) -->
<script src="/_shared.js"></script>
<!-- Vue à prévisualiser -->
<script src="/view.js"></script>

<script>
(function () {{
  const VIEW_ID = {view_id!r};
  const log = (msg) => {{
    const el = document.getElementById('log');
    el.classList.remove('muted');
    el.textContent = (new Date().toISOString().slice(11,19)) + '  ' + msg + '\\n' + el.textContent;
  }};

  // Reproduit fidèlement home.js:696-705 : dispatch des messages serveur.
  function applyServerMessage(data) {{
    if (data.type === 'show_view') {{
      window.Jarvis.views.activate(data.view_id, data.params || {{}});
      log('activate ' + data.view_id); return;
    }}
    if (data.type === 'hide_view') {{
      window.Jarvis.views.deactivate(data.view_id);
      log('deactivate ' + data.view_id); return;
    }}
    if (data.type === 'view_command') {{
      window.Jarvis.views.dispatch(data.view_id, data.command, data.params || {{}});
      log('dispatch ' + data.command + ' params=' + JSON.stringify(data.params || {{}}));
      return;
    }}
    log('ignored: ' + JSON.stringify(data));
  }}

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(proto + '://' + location.host + '/ws/preview');
  ws.onopen    = () => log('ws open');
  ws.onclose   = () => log('ws closed');
  ws.onmessage = (e) => {{
    try {{ applyServerMessage(JSON.parse(e.data)); }}
    catch (err) {{ log('parse error: ' + err); }}
  }};

  const send = (obj) => ws.readyState === 1
    ? ws.send(JSON.stringify(obj))
    : log('ws not ready, dropped: ' + JSON.stringify(obj));

  document.querySelectorAll('button[data-action]').forEach(btn => {{
    btn.onclick = () => send({{ type: btn.dataset.action, view_id: VIEW_ID, params: {{}} }});
  }});
  document.getElementById('send_cmd').onclick = () => {{
    const cmd = document.getElementById('cmd').value.trim();
    if (!cmd) {{ log('command vide, ignoré'); return; }}
    let params = {{}};
    try {{ params = JSON.parse(document.getElementById('params').value || '{{}}'); }}
    catch (e) {{ log('params JSON invalide : ' + e.message); return; }}
    send({{ type: 'view_command', view_id: VIEW_ID, command: cmd, params }});
  }};
}})();
</script>
</body></html>
"""


def build_app(view_dir: Path, view_id: str) -> FastAPI:
    """Construit l'app FastAPI de preview. Exposé pour les tests."""
    app = FastAPI(title=f"preview-view:{view_id}")
    clients: set[WebSocket] = set()

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse(_index_html(view_id))

    @app.get("/_shared.js")
    async def shared_js() -> FileResponse:
        return FileResponse(SHARED_JS, media_type="application/javascript")

    @app.get("/view.js")
    async def view_js() -> FileResponse:
        return FileResponse(view_dir / "view.js", media_type="application/javascript")

    @app.get("/view.css")
    async def view_css() -> Response:
        path = view_dir / "view.css"
        if not path.exists():
            return Response(status_code=404)
        return FileResponse(path, media_type="text/css")

    @app.websocket("/ws/preview")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        clients.add(ws)
        try:
            while True:
                msg = await ws.receive_text()
                # Loopback : on relay à tous les clients connectés (en pratique
                # un seul, l'onglet preview), donc équivalent à un echo. C'est
                # exactement ce que fait home.js quand le serveur push.
                stale: list[WebSocket] = []
                for c in clients:
                    try:
                        await c.send_text(msg)
                    except Exception:  # noqa: BLE001 — best-effort broadcast
                        stale.append(c)
                for c in stale:
                    clients.discard(c)
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(ws)

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prévisualise une vue Jarvis sans lancer le core.")
    parser.add_argument(
        "view_dir",
        type=Path,
        help="Dossier source de la vue (../jarvis-skills/views/<name>).",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-open", action="store_true", help="Ne pas ouvrir le navigateur.")
    args = parser.parse_args(argv)

    view_dir: Path = args.view_dir.resolve()
    if not view_dir.is_dir() or not (view_dir / "view.js").exists():
        sys.stderr.write(f"Vue invalide : {view_dir} (view.js attendu)\n")
        return 2

    # view_id : priorité au frontmatter VIEW.md (champ id), fallback nom de dossier.
    view_id = view_dir.name
    view_md = view_dir / "VIEW.md"
    if view_md.exists():
        import yaml

        text = view_md.read_text(encoding="utf-8")
        if text.startswith("---"):
            _, _, rest = text.partition("---")
            yaml_block, _, _ = rest.partition("---")
            meta = yaml.safe_load(yaml_block) or {}
            view_id = meta.get("id") or meta.get("name") or view_id

    app = build_app(view_dir, view_id)
    url = f"http://{args.host}:{args.port}"
    print(f"Preview : {url}  (vue '{view_id}' depuis {view_dir})")
    if not args.no_open:
        webbrowser.open(url)

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
