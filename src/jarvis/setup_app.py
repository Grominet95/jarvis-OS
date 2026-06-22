# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import threading
import webbrowser

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from jarvis.interfaces.api.setup_wizard import router as setup_router
from jarvis.kernel.paths import PROJECT_ROOT, UI_STATIC_DIR
from jarvis.kernel.setup_layout import ensure_runtime_layout

SETUP_PORT = 8765
SETUP_HOST = "127.0.0.1"

load_dotenv(PROJECT_ROOT / ".env", override=False)
ensure_runtime_layout()

app = FastAPI(title="Jarvis Setup", docs_url=None, redoc_url=None)
app.include_router(setup_router)


@app.get("/setup")
async def setup_page() -> FileResponse:
    return FileResponse(UI_STATIC_DIR / "setup.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "setup"}


app.mount("/static", StaticFiles(directory=str(UI_STATIC_DIR)), name="setup-static")


def _open_browser() -> None:
    webbrowser.open(f"http://{SETUP_HOST}:{SETUP_PORT}/setup", new=1)


def main() -> None:
    threading.Timer(1.0, _open_browser).start()
    uvicorn.run(
        "jarvis.setup_app:app",
        host=SETUP_HOST,
        port=SETUP_PORT,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
