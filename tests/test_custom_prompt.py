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


def test_narration_has_no_spoken_hashtags_and_requires_english_search():
    from pydantic import ValidationError

    from scripts.custom_prompt import SpokenNarration

    data = {
        "hook": "Почему кошки любят коробки? 🐱",
        "body": " ".join(
            ["Кошка спокойно изучает новое место и наблюдает за окружающим миром."] * 7
        )
        + " #кошки 📦",
        "ending": "Это место для отдыха. ✨",
        "visual_query": "cat cardboard box",
    }
    narration = SpokenNarration.model_validate(data)
    assert "#" not in narration.body and "📦" not in narration.body
    assert "🐱" not in narration.hook
    with pytest.raises(ValidationError):
        SpokenNarration.model_validate({**data, "visual_query": "кошка коробка"})


def test_thumbnail_host_is_downloaded_and_unrelated_titles_are_skipped(tmp_path):
    import httpx

    def respond(request):
        if request.url.host == "commons.wikimedia.org":
            pages = {}
            for number, title in [
                (1, "File:Adventure of cardboard box.jpg"),
                (2, "File:Cat into the box.jpg"),
            ]:
                pages[str(number)] = {
                    "pageid": number,
                    "title": title,
                    "imageinfo": [
                        {
                            "mime": "image/jpeg",
                            "thumburl": "https://thumb.wikimedia.org/cat.jpg",
                            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Cat_into_the_box.jpg",
                            "extmetadata": {"LicenseShortName": {"value": "Public domain"}},
                        }
                    ],
                }
            return httpx.Response(200, json={"query": {"pages": pages}})
        assert request.url.host == "thumb.wikimedia.org"
        return httpx.Response(200, content=b"photo-data")

    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            media = await CommonsProvider(None, client).fetch(
                "cat cardboard box", tmp_path / "cat", set()
            )
            assert media.source_id == "2"
            assert media.path.read_bytes() == b"photo-data"

    asyncio.run(check())


def test_truncated_ending_is_removed():
    from scripts.custom_prompt import SpokenNarration

    assert (
        SpokenNarration.spoken_words_only(
            "Коробка — уютное укрытие. Пусть кошка чувствует себя и в"
        )
        == "Коробка — уютное укрытие."
    )
