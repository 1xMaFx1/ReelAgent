import pytest
from pydantic import ValidationError

from app.core.models import Metadata, Script


def test_complete_narration(script):
    assert script.text.startswith(script.hook)
    assert script.text.endswith(script.ending)
    assert len(script.segments) == 6


def test_reject_nonsequential_ids(script):
    value = script.model_dump()
    value["scenes"][1]["id"] = 1
    with pytest.raises(ValidationError):
        Script.model_validate(value)


def test_reject_short_body(script):
    value = script.model_dump()
    value["scenes"] = value["scenes"][:3]
    with pytest.raises(ValidationError):
        Script.model_validate(value)


def test_hashtags():
    with pytest.raises(ValidationError):
        Metadata(title="Title", description="Long description", hashtags=["bad tag"])
