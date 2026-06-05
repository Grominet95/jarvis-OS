from skills.base import SkillBase


class AstronomySkill(SkillBase):
    SYSTEM_PROMPT = (
        "Vue \"astronomy\" : voûte céleste — constellations qui s'illuminent au focus.\n"
        "Afficher : show_view(action=\"show\", view_id=\"astronomy\").\n"
        "Masquer : show_view(action=\"hide\", view_id=\"astronomy\").\n"
        "\n"
        "COMMANDES SPÉCIFIQUES (à utiliser via show_view action=view_command) :\n"
        "- focus_constellation(name=\"...\") : illumine une constellation et zoome dessus.\n"
        "  Constellations disponibles : Orion, Cassiopée, Grande Ourse, Cygne.\n"
        "  Ex: show_view(action=\"view_command\", view_id=\"astronomy\", "
        "command=\"focus_constellation\", params={\"name\": \"Orion\"}).\n"
        "- overview / sky : retour vue d'ensemble (toutes les constellations).\n"
        "\n"
        "RÈGLES IMPORTANTES quand la vue astronomy est ouverte :\n"
        "- \"montre Orion\" / \"focus la Grande Ourse\" → view_command focus_constellation.\n"
        "- NE JAMAIS utiliser fly_to pour une constellation, planète, étoile (ce sont des "
        "objets célestes, pas des lieux terrestres).\n"
        "- Si l'utilisateur demande un objet absent de la liste ci-dessus (ex. Vénus, Mars, "
        "Sirius, Bételgeuse), répondre que cet objet n'est pas dans cette vue plutôt que "
        "de rediriger vers le globe."
    )

    def get_tools(self) -> list:
        return []
