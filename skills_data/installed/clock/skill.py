from skills.base import SkillBase


class ClockSkill(SkillBase):
    SYSTEM_PROMPT = (
        'Vue "clock" installée : Horloge solaire — cadran 24 h, '
        "course du soleil, fuseaux Tokyo/New York/Londres "
        'Pour l\'afficher : show_view(action="show", view_id="clock"). '
        'Pour la masquer : show_view(action="hide", view_id="clock").'
    )

    def get_tools(self) -> list:
        return []
