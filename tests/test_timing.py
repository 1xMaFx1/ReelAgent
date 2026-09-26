import pytest

from app.core.timing import fit_timing
from app.tts.base import Speech


def test_timing_includes_hook_ending(script, tmp_path):
    target, speed, durations = fit_timing(script, Speech(tmp_path / "x.mp3", 36, []), 30, 45)
    assert target == 36 and speed == 1
    assert len(durations) == 4
    assert sum(durations) == pytest.approx(36)
    assert all(d > 0 for d in durations)


def test_short_speech_rejected(script, tmp_path):
    with pytest.raises(ValueError):
        fit_timing(script, Speech(tmp_path / "x.mp3", 5, []), 30, 45)
