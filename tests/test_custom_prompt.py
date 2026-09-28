import asyncio

import pytest

from app.config import Settings
from app.core.prompt_queue import WeeklyPlan
from app.media.commons import CommonsProvider, public_domain
from scripts.custom_prompt import EpisodeDraft, prepare_prompt


def test_plain_prompt_becomes_one_episode(monkeypatch, tmp_path):
    async def ask(self, prompt, model):
        assert model is EpisodeDraft
        return EpisodeDraft.model_validate(
            {
                "narration": {
                    "hook": "Почему кошки любят коробки?",
                    "body": " ".join(
                        ["Кошка спокойно изучает новое место и наблюдает за окружающим миром."] * 7
                    ),
                    "ending": "Вот такая кошачья привычка.",
                    "visual_query": "cat",
                },
                "copy": {
                    "title": "Секрет кошачьей коробки",
                    "keywords": ["кошки", "коробки", "животные"],
                    "hashtags": ["#кошки", "#животные", "#факты"],
                },
            }
        )

    monkeypatch.setattr("scripts.custom_prompt.PromptModel.ask", ask)
    settings, plan = asyncio.run(
        prepare_prompt(Settings(base_dir=tmp_path), "Сделай видео про кошек", "test123")
    )
    assert len(plan.entries) == 1
    assert plan.entries[0].media_source == "commons"
    assert WeeklyPlan.load(settings.prompt_queue_file) == plan
    with pytest.raises(ValueError):
        asyncio.run(prepare_prompt(settings, "коротко", "test"))


def test_no_images_produces_explicit_graphics_not_unrelated_photos(monkeypatch, tmp_path):
    provider = CommonsProvider(None, None)

    async def empty(query):
        return []

    monkeypatch.setattr(provider, "search", empty)
    media = asyncio.run(provider.fetch("a fictional story", tmp_path / "source", set()))
    assert media.source_url == "generated:abstract-gradient"
    assert media.path.read_bytes().startswith(b"P6\n540 960\n255\n")
    assert public_domain({"extmetadata": {"LicenseShortName": {"value": "CC0"}}})
    assert not public_domain({"extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}}})
    assert not public_domain({})
