from skills.base import SkillBase


class SystemMonitorSkill(SkillBase):
    SYSTEM_PROMPT = (
        'Vue "system-monitor" : Cockpit système temps réel — '
        "jauges CPU/RAM/disque, cerveau LLM, services, missions\n"
        'Afficher : show_view(action="show", view_id="system-monitor").\n'
        'Masquer : show_view(action="hide", view_id="system-monitor").\n'
        "\n"
        "RÈGLE : quand cette vue est ouverte, NE PAS utiliser fly_to "
        "(réservé au globe terrestre). Si la vue expose des commandes "
        "spécifiques, les invoquer via "
        'show_view(action="view_command", view_id="system-monitor", '
        "command=..., params={...})."
    )

    def get_tools(self) -> list:
        return []
