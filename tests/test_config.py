import pytest
from pydantic import ValidationError

from app.config import Settings


def test_safe_defaults():
    s = Settings(_env_file=None)
    assert s.dry_run and not s.auto_publish_youtube and not s.auto_publish_instagram
    assert s.app_env == "local"


def test_env(monkeypatch):
    monkeypatch.setenv("TTS_VOICE", "ru-RU-SvetlanaNeural")
    monkeypatch.setenv("DRY_RUN", "false")
    s = Settings(_env_file=None)
    assert s.tts_voice == "ru-RU-SvetlanaNeural" and not s.dry_run


def test_secrets_hidden():
    assert "sensitive-value" not in repr(Settings(_env_file=None, gemini_api_key="sensitive-value"))


def test_dimensions():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, video_width=1001)


def test_duration():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, video_min_duration=50)


def test_local_render_blocked():
    with pytest.raises(ValueError, match="cloud-only"):
        Settings(_env_file=None).require_cloud()
