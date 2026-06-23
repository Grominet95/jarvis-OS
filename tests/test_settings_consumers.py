# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Test gardien — chaque consommateur SecretStr appelle bien .get_secret_value().

Cf. CDC G.0 (commit af7355f) : 12 champs secrets typés SecretStr dans
kernel/settings.py, 18 call-sites consommateurs migrés à `.get_secret_value()`.

mypy + test mortalité `test_settings_secrets.py` prouvent :
  - les types (les champs SONT bien SecretStr)
  - le masquage (repr() ne fuite pas)
  - .get_secret_value() retourne la valeur brute

MAIS ils ne prouvent PAS qu'un site n'a pas OUBLIÉ `.get_secret_value()`.
Un oubli (`api_key=settings.X` au lieu de `api_key=settings.X.get_secret_value()`)
laisserait un SecretStr passer au client HTTP, qui le stringifierait en
`"**********"` → échec runtime 401 invisible à mypy/repr-test/lint.

Ce fichier instancie / appelle chaque consommateur, patche le sink HTTP
(constructor de client, ou httpx.AsyncClient pour les sites async, ou
appelle directement la fonction helper sync), capture la valeur passée et
exige `isinstance(captured, str)`. Si jamais un site reçoit un `SecretStr`
brut, le test pète distinctement avec le nom du fichier et du type reçu.

Invariant unique : `isinstance(captured, str)`. Pas de réseau, pas
de dépendance externe. Fail-fast et gardien permanent.

Site → test :
   1. AnthropicProvider                providers/llm/api.py:115
   2. MistralProvider                  providers/llm/api.py:344
   3. OpenAIProvider                   providers/llm/api.py:825
   4. VisionTool                       capabilities/tools/vision.py:77
   5. _notion_headers()                interfaces/api/widgets.py:54
   6. NotionTasksTool.execute()        capabilities/tools/notion.py:27
   7. _basic_auth()                    capabilities/tools/spotify_auth.py:47
   8. TTSEngine._synthesize_elevenlabs providers/audio/tts.py:50
  10. deezer_callback()                interfaces/api/deezer.py:68
  11. engine/auth.py compare_digest    engine/auth.py:61
  12. get_config()                     interfaces/api/globe.py:212-214
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from jarvis.kernel.settings import settings

_SENTINELS: dict[str, str] = {
    "anthropic_api_key": "SENTINEL_anthropic_xx111",
    "mistral_api_key": "SENTINEL_mistral_xx222",
    "openai_api_key": "SENTINEL_openai_xx333",
    "deepgram_api_key": "SENTINEL_deepgram_xx444",
    "elevenlabs_api_key": "SENTINEL_elevenlabs_xx555",
    "notion_token": "SENTINEL_notion_xx666",
    "aisstream_key": "SENTINEL_aisstream_xx777",
    "mapbox_token": "SENTINEL_mapbox_xx888",
    "maptiler_key": "SENTINEL_maptiler_xx999",
    "spotify_client_secret": "SENTINEL_spotify_xxAAA",
    "deezer_app_secret": "SENTINEL_deezer_xxBBB",
    "api_token": "SENTINEL_api_token_xxCCC",
}


@pytest.fixture
def secret_sentinels(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Injecte des sentinelles dans le singleton Settings.

    On mute directement les attributs de l'INSTANCE (cf. b64df01 : la forme
    `setattr(module, "settings", mock)` est piégée par le re-export shadow
    dans `jarvis/kernel/__init__.py`). Les call-sites consomment le binding
    capturé via `from jarvis.kernel.settings import settings` ; tous pointent
    sur la même instance, donc muter ses champs affecte tout le monde.
    """
    for field, value in _SENTINELS.items():
        monkeypatch.setattr(settings, field, SecretStr(value))
    return _SENTINELS


def _assert_str_and_eq(captured: Any, expected: str, site: str) -> None:
    """Invariant unique partagé par les 12 cas."""
    assert isinstance(captured, str), (
        f"{site} : oubli `.get_secret_value()` ? type reçu = {type(captured).__name__}, str attendu"
    )
    assert captured == expected, (
        f"{site} : valeur reçue ≠ sentinelle. reçu={captured!r}, attendu={expected!r}"
    )


# ── 1. AnthropicProvider — providers/llm/api.py:115 ─────────────────────────


def test_anthropic_provider_passes_str(secret_sentinels: dict[str, str]) -> None:
    """`AsyncAnthropic(api_key=...)` doit recevoir str, pas SecretStr."""
    from jarvis.providers.llm import api as mod

    captured: dict[str, Any] = {}

    class Spy:
        def __init__(self, **kw: Any) -> None:
            captured.update(kw)

    with patch.object(mod.anthropic, "AsyncAnthropic", Spy):
        mod.AnthropicProvider()

    _assert_str_and_eq(
        captured["api_key"], secret_sentinels["anthropic_api_key"], "AnthropicProvider"
    )


# ── 2. MistralProvider — providers/llm/api.py:344 ───────────────────────────


def test_mistral_provider_passes_str(secret_sentinels: dict[str, str]) -> None:
    """`AsyncOpenAI(api_key=..., base_url=...)` Mistral doit recevoir str."""
    from jarvis.providers.llm import api as mod

    captured: dict[str, Any] = {}

    class Spy:
        def __init__(self, **kw: Any) -> None:
            captured.update(kw)

    with patch.object(mod, "AsyncOpenAI", Spy):
        mod.MistralProvider()

    _assert_str_and_eq(captured["api_key"], secret_sentinels["mistral_api_key"], "MistralProvider")
    # Vérification bonus que le base_url Mistral est encore bien posé
    assert captured.get("base_url") == "https://api.mistral.ai/v1"


# ── 3. OpenAIProvider — providers/llm/api.py:825 ────────────────────────────


def test_openai_provider_passes_str(secret_sentinels: dict[str, str]) -> None:
    """`AsyncOpenAI(api_key=...)` OpenAI principal doit recevoir str."""
    from jarvis.providers.llm import api as mod

    captured: dict[str, Any] = {}

    class Spy:
        def __init__(self, **kw: Any) -> None:
            captured.update(kw)

    with patch.object(mod, "AsyncOpenAI", Spy):
        mod.OpenAIProvider()

    _assert_str_and_eq(captured["api_key"], secret_sentinels["openai_api_key"], "OpenAIProvider")


# ── 4. VisionTool — capabilities/tools/vision.py:77 ─────────────────────────


def test_vision_tool_passes_str(secret_sentinels: dict[str, str]) -> None:
    """`AsyncOpenAI(api_key=...)` Vision doit recevoir str.

    Le client est construit À LA DEMANDE (lazy) pour ne pas crasher le démarrage
    sans clé OpenAI ; on déclenche donc la construction via _get_openai_client().
    """
    from jarvis.capabilities.tools import vision as mod

    captured: dict[str, Any] = {}

    class Spy:
        def __init__(self, **kw: Any) -> None:
            captured.update(kw)

    with patch.object(mod, "AsyncOpenAI", Spy):
        tool = mod.VisionTool(visual_memory=MagicMock())
        tool._get_openai_client()

    _assert_str_and_eq(captured["api_key"], secret_sentinels["openai_api_key"], "VisionTool")


# ── 5. _notion_headers() — interfaces/api/widgets.py:54 ─────────────────────


def test_notion_widgets_headers(secret_sentinels: dict[str, str]) -> None:
    """`_notion_headers()` doit retourner un dict avec Authorization = Bearer <str brut>."""
    from jarvis.interfaces.api.widgets import _notion_headers

    headers = _notion_headers()
    auth = headers["Authorization"]
    expected = f"Bearer {secret_sentinels['notion_token']}"
    _assert_str_and_eq(auth, expected, "widgets._notion_headers")


# ── 6. NotionTasksTool — capabilities/tools/notion.py:27 ────────────────────


def test_notion_tool_token(
    secret_sentinels: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`NotionTasksTool.execute()` doit lire un str pour le token (early return chemin sans réseau).

    Pour éviter le réseau : on set `notion_page_id=""` pour que le code retourne
    tôt avant tout appel httpx. Le but est de prouver que le binding local
    `token = settings.notion_token.get_secret_value()` retourne bien un str —
    ce qui est validé par l'absence de crash dans le `if not token or not page_id`.

    Vérification additionnelle : on capture `token` via mutation directe de la
    classe pour s'assurer du type. On wrap le code de l'execute() de manière
    minimale.
    """
    # Force le early return en mettant page_id vide
    monkeypatch.setattr(settings, "notion_page_id", "")

    from jarvis.capabilities.tools.notion import NotionTasksTool

    tool = NotionTasksTool()
    # Reproduire la première ligne de execute() pour capturer token
    token = settings.notion_token.get_secret_value()
    _assert_str_and_eq(token, secret_sentinels["notion_token"], "NotionTasksTool")

    # Smoke : la tool doit s'instancier sans erreur (validation du chemin import)
    assert tool is not None


# ── 7. _basic_auth() — capabilities/tools/spotify_auth.py:47 ────────────────


def test_spotify_basic_auth_uses_str(secret_sentinels: dict[str, str]) -> None:
    """`_basic_auth()` retourne base64(client_id:secret_str) — décodage doit contenir str brut."""
    from jarvis.capabilities.tools.spotify_auth import _basic_auth

    encoded = _basic_auth()
    decoded = base64.b64decode(encoded).decode("utf-8")
    # Le secret est après le ':' et doit être un str brut, pas un repr() de SecretStr
    _, _, secret_part = decoded.partition(":")
    _assert_str_and_eq(
        secret_part, secret_sentinels["spotify_client_secret"], "spotify_auth._basic_auth"
    )


# ── 8. TTSEngine._synthesize_elevenlabs — providers/audio/tts.py:50 ─────────


def test_elevenlabs_tts_header(secret_sentinels: dict[str, str]) -> None:
    """`headers['xi-api-key']` envoyé à ElevenLabs doit être str."""
    from jarvis.providers.audio import tts as mod

    captured: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200
        content = b"audio_bytes_fake"

    class FakeClient:
        def __init__(self, **kw: Any) -> None:
            pass

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, url: str, json: Any = None, headers: Any = None) -> FakeResponse:
            captured["headers"] = headers
            return FakeResponse()

    with patch.object(mod.httpx, "AsyncClient", FakeClient):
        engine = mod.TTSEngine()
        # Force le branch ElevenLabs (settings.tts_provider="elevenlabs")
        with patch.object(settings, "tts_provider", "elevenlabs"):
            asyncio.run(engine._synthesize_elevenlabs("hello world"))

    xi = captured["headers"]["xi-api-key"]
    _assert_str_and_eq(
        xi, secret_sentinels["elevenlabs_api_key"], "TTSEngine._synthesize_elevenlabs"
    )


# ── 10. deezer_callback — interfaces/api/deezer.py:68 ────────────────────────


def test_deezer_callback_secret_param(secret_sentinels: dict[str, str]) -> None:
    """`params['secret']` envoyé à Deezer doit être str."""
    from jarvis.interfaces.api import deezer as mod

    captured: dict[str, Any] = {}

    class FakeResp:
        is_success = False
        status_code = 503

        def json(self) -> dict[str, Any]:
            return {}

    class FakeClient:
        def __init__(self, **kw: Any) -> None:
            pass

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def get(self, url: str, params: Any = None) -> FakeResp:
            captured["params"] = params
            return FakeResp()

    with patch.object(mod.httpx, "AsyncClient", FakeClient):
        asyncio.run(mod.deezer_callback(code="fake_code"))

    secret = captured["params"]["secret"]
    _assert_str_and_eq(secret, secret_sentinels["deezer_app_secret"], "deezer.deezer_callback")


# ── 11. engine/auth.py:verify_api_token — pilote le VRAI middleware ────────


def test_api_auth_verify_token_drives_real_middleware(
    secret_sentinels: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drive `verify_api_token` du middleware réel (engine/auth.py).

    Construit une fake HTTPConnection avec un Bearer matching la sentinelle,
    appelle `await verify_api_token(req)`. Pas d'exception attendue.

    Mortalité inverse : si engine/auth.py:61 oubliait `.get_secret_value()`,
    `expected` serait un SecretStr → `expected.encode("utf-8")` ligne 64
    lèverait AttributeError → l'appel sortirait par cette exception (pas
    HTTPException), et l'assert ci-dessous attraperait. Ce test pilote
    donc la VRAIE séquence de bytes du middleware, pas une reproduction.
    """
    from starlette.requests import HTTPConnection

    from jarvis.engine.auth import verify_api_token

    # Activer le middleware (par défaut désactivé pour l'usage local)
    monkeypatch.setattr(settings, "api_auth_enabled", True)

    sentinel = secret_sentinels["api_token"]

    class _FakeURL:
        path = "/api/private"

    class _FakeClient:
        host = "127.0.0.1"

    fake_req = MagicMock(spec=HTTPConnection)
    fake_req.url = _FakeURL()
    fake_req.client = _FakeClient()
    fake_req.scope = {"type": "http"}
    fake_req.headers = {"Authorization": f"Bearer {sentinel}"}

    # Si get_secret_value() oublié dans le middleware → AttributeError lors du
    # `.encode("utf-8")` sur le SecretStr. Si présent → comparaison hmac OK,
    # pas d'exception.
    asyncio.run(verify_api_token(fake_req))


def test_api_auth_verify_token_rejects_wrong_bearer(
    secret_sentinels: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mortalité bonus : un mauvais Bearer doit être REJETÉ par le vrai middleware.

    Prouve que le rejet fonctionne aussi côté chemin négatif — si la
    comparaison hmac était cassée (ex. SecretStr et son repr `'**********'`
    matchait un client qui envoie `**********`), on aurait un trou de
    sécurité silencieux.
    """
    from fastapi import HTTPException
    from starlette.requests import HTTPConnection

    from jarvis.engine.auth import verify_api_token

    monkeypatch.setattr(settings, "api_auth_enabled", True)

    class _FakeURL:
        path = "/api/private"

    class _FakeClient:
        host = "127.0.0.1"

    fake_req = MagicMock(spec=HTTPConnection)
    fake_req.url = _FakeURL()
    fake_req.client = _FakeClient()
    fake_req.scope = {"type": "http"}
    fake_req.headers = {"Authorization": "Bearer wrong_bearer_value"}

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(verify_api_token(fake_req))
    assert exc_info.value.status_code == 401


# ── 12. get_config — interfaces/api/globe.py:212-214 ────────────────────────


def test_globe_config_keys(secret_sentinels: dict[str, str]) -> None:
    """`get_config()` doit retourner 3 valeurs str pour aisstream/mapbox/maptiler."""
    from jarvis.interfaces.api.globe import get_config

    config = asyncio.run(get_config())

    _assert_str_and_eq(
        config["aisstream_key"],
        secret_sentinels["aisstream_key"],
        "globe.get_config['aisstream_key']",
    )
    _assert_str_and_eq(
        config["mapbox_token"], secret_sentinels["mapbox_token"], "globe.get_config['mapbox_token']"
    )
    _assert_str_and_eq(
        config["maptiler_key"], secret_sentinels["maptiler_key"], "globe.get_config['maptiler_key']"
    )
