from bridges.python.src.sdk.leon import leon
from bridges.python.src.sdk.types import ActionParams
from ..lib import Akinator, memory

def run(params: ActionParams) -> None:
    """Guess according to the given thematic"""

    resolvers = params['resolvers']
    answer = None

    for resolver in resolvers:
        if resolver['name'] == 'answer':
            answer = resolver['value']

    # Return no speech if no value has been found
    if answer is None:
        return leon.answer({'core': {'isInActionLoop': False}})

    session = memory.get_session()

    akinator = Akinator(
        lang=session['lang'],
        theme=session['theme']
    )

    # Retrieve the current session progress
    akinator.json = {
        'step': session['step'],
        'progression': session['progression'],
        'sid': session['sid'],
        'cm': session['cm'],
        'session': session['session'],
        'signature': session['signature']
    }

    new_progress_response = akinator.post_answer(answer)

    if 'name_proposition' in new_progress_response:
        leon.answer({
            'key': 'guessed',
            'data': {
                'name': new_progress_response['name_proposition'],
                'description': new_progress_response['description_proposition']
            }
        })

        leon.answer({
            'key': 'guessed_img',
            'data': {
                'name': new_progress_response['name_proposition'],
                'url': new_progress_response['photo']
            }
        })

        return leon.answer({
            'key': 'ask_for_retry',
            'core': {
                'isInActionLoop': False,
                'showNextActionSuggestions': True
            }
        })

    memory.upsert_session({
        'lang': session['lang'],
        'theme': session['theme'],
        'sid': session['sid'],
        'cm': session['cm'],
        'signature': session['signature'],
        'session': session['session'],
        'question': new_progress_response['question'],
        'step': int(new_progress_response['step']),
        'progression': float(new_progress_response['progression'])
    })

    # TODO: widget with image

    leon.answer({
        'key': akinator.question,
        'core': {
            'showSuggestions': True
        }
    })
