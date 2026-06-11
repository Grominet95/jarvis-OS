from __future__ import annotations

from skills.base import SkillBase


class GlobeViewSkill(SkillBase):
    SYSTEM_PROMPT = (
        'Vue "globe" installée : globe terrestre temps réel (vols, météo, navires). '
        'Pour l\'afficher : show_view(action="show", view_id="globe"). '
        'Pour la masquer : show_view(action="hide", view_id="globe"). '
        'Pour un lieu : show_view(action="fly_to", location="...").'
    )

    def get_tools(self) -> list:
        return []
