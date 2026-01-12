from bridges.python.src.sdk.leon import leon
from bridges.python.src.sdk.types import ActionParams
from ..lib import Akinator, memory

def run(params: ActionParams) -> None:
    """Initialize new session"""

    leon.answer({'key': 'calling_akinator'})

    slots, lang = params['slots'], params['lang']
    thematic = slots['thematic']['resolution']['value']

    try:
        akinator = Akinator(
            lang=lang,
            theme=thematic
        )

        question = akinator.start_game()

        memory.upsert_session({
            'lang': lang,
            'theme': thematic,
            'cm': False,
            'sid': akinator.json['sid'],
            'question': akinator.question,
            'step': akinator.step,
            'progression': akinator.progression,
            'signature': akinator.json['signature'],
            'session': akinator.json['session'],
        })

        leon.answer({
            'key': question,
            'core': {
                'showNextActionSuggestions': True
            }
        })
    except:
        leon.answer({
            'key': 'network_error',
            'core': {
                'isInActionLoop': False
            }
        })
