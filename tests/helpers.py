import json

FIXTURES_PATH = "./tests/fixture"


def get_fixtures(file):
    """
    Read the content of the JSON file.
    """

    with open(f"{FIXTURES_PATH}/{file}.json") as f:
        raw_data = json.load(f)
    return raw_data
