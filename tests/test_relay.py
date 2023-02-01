import json

FIXTURES_PATH = "tests/extensions/nostrrelay/fixture"

class EventFixture(BaseModel):
    name: str
    data: NostrEvent


def test_function_with_scenario_one():
    print("Testing function with scenario one")
    assert 1 + 1 == 2, f"Check addition value {1 + 1} does not match {2}"
    data = get_fixture(f"{FIXTURES_PATH}/events.json")
    print("### data", data)


def get_fixture(file):
    """
    Read the content of the JSON file.
    """

    with open(file) as f:
        raw_data = json.load(f)
    return raw_data
