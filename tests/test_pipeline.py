import asyncio
import json

import httpx

import app.core.pipeline as module
from app.config import Settings
from app.core.database import Database
from app.core.models import Metadata, Status, Topic
from app.core.pipeline import Pipeline
from app.media.base import Media
from app.tts.base import Speech


class FakeLLM:
    def __init__(self, *args):
        pass

    async def generate_topic(self, recent):
        return Topic(topic="Почему звёзды мерцают", category="космос")

    async def generate_script(self, topic):
        return self.script

    async def generate_metadata(self, script):
        return Metadata(
            title="Почему звёзды мерцают",
            description="Атмосфера влияет на свет звёзд.",
            hashtags=["#космос"],
        )


class FakeTTS:
    def __init__(self, *args):
        pass

    async def synthesize(self, text, path):
        path.write_bytes(b"fake-audio")
        return Speech(path, 36, [])


class FakeMedia:
    def __init__(self, *args):
        pass

    async def fetch(self, query, destination, used):
        destination.write_bytes(b"fake-media")
        return Media(destination, str(destination), "https://example.com/stock", "test")


class FakeComposer:
    calls = 0

    def __init__(self, *args):
        pass

    async def compose(self, media, durations, audio, captions, video, *args):
        self.__class__.calls += 1
        video.write_bytes(b"fake-mp4-for-unit-test")
        return video


def test_full_orchestration_and_daily_resume(tmp_path, monkeypatch, script):
    FakeLLM.script = script
    FakeComposer.calls = 0
    monkeypatch.setattr(module, "GeminiProvider", FakeLLM)
    monkeypatch.setattr(module, "EdgeTTSProvider", FakeTTS)
    monkeypatch.setattr(module, "PexelsVideoProvider", FakeMedia)
    monkeypatch.setattr(module, "VideoComposer", FakeComposer)
    monkeypatch.setattr(module, "check_ffmpeg", lambda: None)
    monkeypatch.setattr(Settings, "require_cloud", lambda self: None)
    settings = Settings(
        _env_file=None, base_dir=tmp_path, gemini_api_key="test", pexels_api_key="test"
    )
    video = asyncio.run(Pipeline(settings).run())
    assert video.exists()
    data = json.loads(video.with_name("metadata.json").read_text())
    assert data["youtube"] is None and data["instagram"] is None
    assert data["hook"] in data["script"] and data["ending"] in data["script"]
    assert not (tmp_path / "data/tmp" / video.parent.name).exists()
    asyncio.run(Pipeline(settings).run())
    assert FakeComposer.calls == 1


def test_publication_failure_isolated(tmp_path, monkeypatch):
    calls = []

    class BadYouTube:
        configured = True

        def __init__(self, *args):
            pass

        async def publish(self, *args):
            calls.append("youtube")
            raise RuntimeError("Simulated failure")

    class GoodInstagram:
        configured = True

        def __init__(self, *args):
            pass

        async def publish(self, *args):
            calls.append("instagram")
            return "ig-123"

    monkeypatch.setattr(module, "YouTubePublisher", BadYouTube)
    monkeypatch.setattr(module, "InstagramPublisher", GoodInstagram)
    settings = Settings(
        _env_file=None,
        base_dir=tmp_path,
        dry_run=False,
        auto_publish_youtube=True,
        auto_publish_instagram=True,
    )
    db = Database(tmp_path / "test.db")
    video_id = db.claim("2026-09-26")
    video = tmp_path / "reel.mp4"
    video.write_bytes(b"unit-test")
    meta = {
        "title": "Звёзды",
        "description": "Почему звёзды мерцают",
        "hashtags": ["#наука"],
        "youtube": None,
        "instagram": None,
    }

    async def check():
        async with httpx.AsyncClient() as client:
            pipeline = Pipeline(settings)
            await pipeline._publish(db, video_id, client, video, meta, True)
            await pipeline._publish(db, video_id, client, video, meta, True)

    asyncio.run(check())
    assert calls == ["youtube", "instagram"]
    assert video.exists() and meta["instagram"] == "ig-123"
    assert db.today("2026-09-26")["status"] == Status.PARTIALLY_PUBLISHED
    db.close()
