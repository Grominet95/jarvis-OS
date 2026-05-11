"""
mode-streameur — Preset Jarvis.

Lance l'environnement stream : OBS, Ne pas déranger, Twitch, recommandation de jeu.
Déclencheurs : "lance le mode streameur", "démarre le stream", "on stream"
Plateformes : mac, windows
"""
from skills.base import PresetSkill


class ModeStreameur(PresetSkill):
    """
    Lance l'environnement de streaming.
    Ouvre OBS, active Ne pas déranger, ouvre le dashboard Twitch,
    recommande un jeu et ouvre sa page Steam.
    """
