import pytest

from app.core.models import Script
from app.utils.text import normalize_topic, parse_json


def test_json(script):
    assert parse_json(script.model_dump_json(), Script) == script


def test_fence_repair(script):
    assert parse_json("```json\n" + script.model_dump_json() + "\n```", Script) == script


def test_surrounding_prose_repair(script):
    assert parse_json("Here is JSON: " + script.model_dump_json(), Script) == script


def test_invalid_json():
    with pytest.raises(ValueError):
        parse_json("Not valid JSON", Script)


def test_normalization():
    assert normalize_topic("КОСМОС: звёзды!") == normalize_topic("космос звёзды")
