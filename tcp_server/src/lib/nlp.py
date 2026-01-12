import copy
from sys import argv
import spacy
import time
from geonamescache import GeonamesCache

lang = argv[1] or 'en'
spacy_nlp = None
spacy_model_mapping = {
    'en': {
        'model': 'en_core_web_trf',
        'exclude': ['tagger', 'parser', 'attribute_ruler', 'lemmatizer'],
        'entity_mapping': {
            'PERSON': 'person',
            'GPE': 'location',
            'ORG': 'organization'
        }
    },
    'fr': {
        'model': 'fr_core_news_md',
        'exclude': ['tok2vec', 'morphologizer', 'parser', 'senter', 'attribute_ruler', 'lemmatizer'],
        'entity_mapping': {
            'PER': 'person',
            'LOC': 'location',
            'ORG': 'organization'
        }
    }
}

geonamescache = GeonamesCache(min_city_population=5000)
countries = geonamescache.get_countries()
cities = geonamescache.get_cities()

"""
Functions called from TCPServer class
"""


def load_spacy_model() -> None:
    global spacy_nlp

    model = spacy_model_mapping[lang]['model']
    exclude = spacy_model_mapping[lang]['exclude']

    tic = time.perf_counter()
    log(f'Loading {model} spaCy model...')
    # Use CPU to leave more GPU VRAM for other matters
    spacy.require_cpu()
    spacy_nlp = spacy.load(model, exclude=exclude)
    log('spaCy model loaded')
    toc = time.perf_counter()
    log(f"Time taken to load spaCy model: {toc - tic:0.4f} seconds")


def delete_unneeded_country_data(data: dict) -> None:
    try:
        del data['geonameid']
        del data['neighbours']
        del data['languages']
        del data['iso3']
        del data['fips']
        del data['currencyname']
        del data['postalcoderegex']
        del data['areakm2']
    except BaseException:
        pass


def extract_spacy_entities(utterance: str) -> list[dict]:
    doc = spacy_nlp(utterance)
    entities: list[dict] = []

    for ent in doc.ents:
        if ent.label_ in spacy_model_mapping[lang]['entity_mapping']:
            entity = spacy_model_mapping[lang]['entity_mapping'][ent.label_]
            resolution = {
                'value': ent.text
            }

            if entity == 'location':
                for country in countries:
                    if countries[country]['name'].casefold() == ent.text.casefold():
                        entity += ':country'
                        resolution['data'] = copy.deepcopy(countries[country])
                        delete_unneeded_country_data(resolution['data'])
                        break

                if ':country' not in entity:
                    city_population = 0
                    for city in cities:
                        alternatenames = [name.casefold() for name in cities[city]['alternatenames']]
                        if cities[city]['name'].casefold() == ent.text.casefold() or ent.text.casefold() in alternatenames:
                            if city_population == 0:
                                entity += ':city'

                            if cities[city]['population'] > city_population:
                                resolution['data'] = copy.deepcopy(cities[city])
                                city_population = cities[city]['population']

                                for country in countries:
                                    if countries[country]['iso'] == cities[city]['countrycode']:
                                        resolution['data']['country'] = copy.deepcopy(countries[country])
                                        break
                                try:
                                    del resolution['data']['geonameid']
                                    del resolution['data']['alternatenames']
                                    del resolution['data']['admin1code']
                                    delete_unneeded_country_data(resolution['data']['country'])
                                except BaseException:
                                    pass
                            else:
                                continue

            entities.append({
                'start': ent.start_char,
                'end': ent.end_char,
                'len': len(ent.text),
                'sourceText': ent.text,
                'utteranceText': ent.text,
                'entity': entity,
                'resolution': resolution
            })

    return entities


def log(*args, **kwargs):
    print('[NLP]', *args, **kwargs)
