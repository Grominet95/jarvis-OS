# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Test de mortalité — un secret ne doit jamais apparaître dans repr(Settings).

CDC G.0 (post-mortem 2026-06-11) : un AttributeError pytest a imprimé le
repr() complet du singleton Settings, exposant 9 clés réelles en clair dans
la trace. La cause structurelle : tous les champs secrets étaient typés
`str` dans `kernel/settings.py`, donc inclus tel quel dans le repr.

Ce test EXIGE que tout champ secret connu, peuplé avec un sentinel
ostensiblement reconnaissable, soit MASQUÉ dans le repr de l'instance.
Si un nouveau champ secret est ajouté à Settings et oublié dans la
liste des conversions `SecretStr`, ce test échoue.

Isolation : on construit une Settings vierge avec model_config qui
N'OUVRE PAS le .env du dev (env_file=None). Le test ne touche pas au
singleton global et ne risque pas d'imprimer les vraies clés.
"""

from __future__ import annotations

import re

from pydantic import SecretStr

from jarvis.kernel.settings import Settings

# Sentinelles ostensiblement reconnaissables : aucun risque d'être une vraie clé,
# mais chaque token de la forme `SENTINEL_<champ>_<random>` doit être absent
# du repr si SecretStr fonctionne.
_SENTINELS: dict[str, str] = {
    "anthropic_api_key": "SENTINEL_anthropic_sk-ant-xx111",
    "mistral_api_key": "SENTINEL_mistral_xx222",
    "api_token": "SENTINEL_api_token_xx333",
    "openai_api_key": "SENTINEL_openai_sk-proj-xx444",
    "deepgram_api_key": "SENTINEL_deepgram_xx555",
    "elevenlabs_api_key": "SENTINEL_elevenlabs_sk_xx666",
    "notion_token": "SENTINEL_notion_ntn_xx777",
    "aisstream_key": "SENTINEL_aisstream_xx888",
    "mapbox_token": "SENTINEL_mapbox_pk.xx999",
    "maptiler_key": "SENTINEL_maptiler_xxAAA",
    "spotify_client_secret": "SENTINEL_spotify_xxBBB",
    "deezer_app_secret": "SENTINEL_deezer_xxCCC",
}


def _fresh_settings_no_env() -> Settings:
    """Construit une Settings sans charger le .env du dev.

    Surcharge env_file=None pour pydantic-settings ne va PAS lire le .env
    racine. Surcharge case_sensitive=True pour que les vars d'environnement
    en majuscules (LLM_PROVIDER, etc.) ne soient pas mappées et ne polluent
    pas les sentinelles passées en kwargs.
    """
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        **_SENTINELS,
    )


def test_secrets_are_secretstr_typed() -> None:
    """Chaque champ secret connu doit être typé SecretStr (pas str)."""
    s = _fresh_settings_no_env()
    for name in _SENTINELS:
        value = getattr(s, name)
        assert isinstance(value, SecretStr), (
            f"Champ {name} n'est pas SecretStr — repr(settings) fuiterait."
        )


def test_no_sentinel_in_repr() -> None:
    """Aucune sentinelle ne doit apparaître dans repr(Settings)."""
    s = _fresh_settings_no_env()
    r = repr(s)
    leaked = [name for name, sentinel in _SENTINELS.items() if sentinel in r]
    assert not leaked, (
        f"Champs secrets fuités dans repr() : {leaked}. "
        f"Probablement non-typés SecretStr dans kernel/settings.py."
    )


def test_no_sk_prefix_in_repr() -> None:
    """Filet de sécurité indépendant du nom des champs : aucun préfixe de clé
    API courant (`sk-ant-`, `sk-proj-`, `sk_`, `ntn_`, `pk.`) ne doit apparaître
    dans repr(Settings) avec une partie alphanumérique attenante.

    Cf. CDC G.0 : ce test attrape AUSSI un futur champ secret qui aurait
    échappé à la liste des sentinelles ci-dessus (par exemple un nouveau
    fournisseur ajouté plus tard sans typer le champ en SecretStr).
    """
    s = _fresh_settings_no_env()
    r = repr(s)
    # `sk-` matche Anthropic ET OpenAI ; les autres préfixes restent stricts.
    patterns = [r"sk-[a-zA-Z]", r"sk_[a-zA-Z0-9]", r"ntn_[a-zA-Z0-9]", r"pk\.[a-zA-Z0-9]"]
    matched: list[str] = []
    for pat in patterns:
        if re.search(pat, r):
            matched.append(pat)
    assert not matched, (
        f"Préfixes secrets détectés dans repr() : {matched}. "
        "Filet de sécurité G.0 — un champ secret non listé fuite probablement."
    )


def test_get_secret_value_returns_brut() -> None:
    """`.get_secret_value()` doit retourner la valeur brute exacte (sans masque).

    Garantit que les call-sites consommateurs (clients HTTP Anthropic, OpenAI,
    Notion, etc.) reçoivent bien la clé en clair pour s'authentifier.
    """
    s = _fresh_settings_no_env()
    for name, sentinel in _SENTINELS.items():
        value = getattr(s, name).get_secret_value()
        assert value == sentinel, (
            f"Champ {name}.get_secret_value() = {value!r}, attendu {sentinel!r}"
        )
