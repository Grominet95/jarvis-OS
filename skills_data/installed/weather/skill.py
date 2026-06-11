from skills.base import SkillBase


class WeatherSkill(SkillBase):
    SYSTEM_PROMPT = (
        'Vue "weather" : Météo immersive — scène de ciel animée, '
        "conditions et prévisions horaires (Open-Meteo)\n"
        'Afficher : show_view(action="show", view_id="weather").\n'
        'Masquer : show_view(action="hide", view_id="weather").\n'
        "\n"
        "RÈGLE : quand cette vue est ouverte, NE PAS utiliser fly_to "
        "(réservé au globe terrestre). Si la vue expose des commandes "
        "spécifiques, les invoquer via "
        'show_view(action="view_command", view_id="weather", '
        "command=..., params={...})."
    )

    def get_tools(self) -> list:
        return []
