import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from test_pipeline import FakeComposer, FakeMedia, FakeTTS

from app.config import Settings
from app.core import weekly_pipeline as module
from app.core.database import Database
from app.core.pipeline import Pipeline
from app.core.prompt_queue import WeeklyPlan

PLAN = Path(__file__).resolve().parent / "fixtures/weekly-seven.json"


def test_plan_calendar_and_expiration():
    plan = WeeklyPlan.load(PLAN)
    for index, entry in enumerate(plan.entries):
        assert plan.for_date((plan.start_date + timedelta(days=index)).isoformat()) == entry
    for day in (plan.start_date - timedelta(days=1), plan.start_date + timedelta(days=7)):
        with pytest.raises(ValueError, match="нет промпта"):
            plan.for_date(day.isoformat())
    assert plan.entries[6].recap_days == [1, 2, 3, 4, 5, 6]
    assert plan.entries[2].social.title == "Почему небо не фиолетовое?"
    assert all(e.script and e.social for e in plan.entries[1:])


def test_reject_duplicate_and_incomplete_week():
    data = json.loads(PLAN.read_text())
    data["entries"][2] = {**data["entries"][1], "day": 3}
    with pytest.raises(ValidationError, match="Duplicate"):
        WeeklyPlan.model_validate(data)
    data["entries"].pop()
    with pytest.raises(ValidationError):
        WeeklyPlan.model_validate(data)


def test_assignment_cannot_change_or_repeat(tmp_path):
    db = Database(tmp_path / "state.db")
    db.assign_prompt("2026-01-01", "a", "week", "{}")
    db.assign_prompt("2026-01-01", "a", "week", "{}")
    with pytest.raises(ValueError):
        db.assign_prompt("2026-01-01", "b", "week", "{}")
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        db.assign_prompt("2026-01-02", "a", "week", "{}")
    assert db.assigned_prompt("2026-01-01")["prompt_key"] == "a"
    db.close()


def prepare(tmp_path, monkeypatch, day_number):
    plan = WeeklyPlan.load(PLAN)
    today = datetime.now(ZoneInfo("Europe/Simferopol")).date()
    plan.start_date = today - timedelta(days=day_number - 1)
    plan_file = tmp_path / "week.json"
    plan_file.write_text(plan.model_dump_json())
    settings = Settings(
        _env_file=None,
        base_dir=tmp_path,
        content_mode="prompt_queue",
        prompt_queue_file=plan_file,
    )
    monkeypatch.setattr(Settings, "require_cloud", lambda self: None)
    monkeypatch.setattr(module, "EdgeTTSProvider", FakeTTS)
    monkeypatch.setattr(module, "NasaVideoProvider", FakeMedia)
    monkeypatch.setattr(module, "VideoComposer", FakeComposer)
    FakeComposer.calls = 0

    async def cache(source, destination, **kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"cached-real-footage-placeholder")

    monkeypatch.setattr(module, "cache_clip", cache)
    anchor = module.cache_path(settings, plan, plan.entries[0])
    anchor.parent.mkdir(parents=True)
    anchor.write_bytes(b"anchor")
    return settings, plan, today


def test_weekly_render_preserves_prompt_and_does_not_publish(tmp_path, monkeypatch):
    settings, plan, today = prepare(tmp_path, monkeypatch, 3)

    assert not hasattr(Pipeline, "_publish")
    video = asyncio.run(Pipeline(settings).run())
    meta = json.loads(video.with_name("metadata.json").read_text())
    entry = plan.entries[2]
    assert meta["script"] == entry.script.text
    assert meta["description"] == ", ".join(entry.social.keywords)
    assert meta["prompt_key"] == entry.key
    assert meta["youtube"] is None
    assert video.parent.name == today.isoformat()
    assert module.cache_path(settings, plan, entry).exists()
    asyncio.run(Pipeline(settings).run())
    assert FakeComposer.calls == 1


def test_changed_prompt_rejected_on_retry(tmp_path, monkeypatch):
    settings, plan, today = prepare(tmp_path, monkeypatch, 3)
    asyncio.run(Pipeline(settings).run())
    plan.entries[2].prompt += " Changed after first render."
    settings.prompt_queue_file.write_text(plan.model_dump_json())
    with pytest.raises(ValueError, match="закреплён"):
        asyncio.run(Pipeline(settings).run())
    assert FakeComposer.calls == 1


def test_recap_requires_all_earlier_days(tmp_path, monkeypatch):
    settings, plan, _ = prepare(tmp_path, monkeypatch, 7)
    with pytest.raises(ValueError, match="не хватает готового дня 2"):
        asyncio.run(Pipeline(settings).run())
    assert FakeComposer.calls == 0
    for entry in plan.entries[1:6]:
        module.cache_path(settings, plan, entry).write_bytes(b"earlier-footage")
    asyncio.run(Pipeline(settings).run())
    assert FakeComposer.calls == 1


def test_unreviewed_prompt_stops_before_render(tmp_path, monkeypatch):
    settings, plan, _ = prepare(tmp_path, monkeypatch, 3)
    plan.entries[2].script = None
    plan.entries[2].social = None
    plan.entries[2].overlays = []
    settings.prompt_queue_file.write_text(plan.model_dump_json())
    with pytest.raises(ValueError, match="проверенный сценарий"):
        asyncio.run(Pipeline(settings).run())
    assert FakeComposer.calls == 0


def test_resume_after_archive_failure_does_not_rerender(tmp_path, monkeypatch):
    settings, plan, _ = prepare(tmp_path, monkeypatch, 3)
    normal_cache = module.cache_clip

    async def fail_cache(*args, **kwargs):
        raise RuntimeError("Temporary archive failure")

    monkeypatch.setattr(module, "cache_clip", fail_cache)
    with pytest.raises(RuntimeError, match="archive failure"):
        asyncio.run(Pipeline(settings).run())
    assert FakeComposer.calls == 1
    monkeypatch.setattr(module, "cache_clip", normal_cache)
    asyncio.run(Pipeline(settings).run())
    assert FakeComposer.calls == 1
    assert module.cache_path(settings, plan, plan.entries[2]).is_file()


def test_anchor_redirect_does_not_leak_token(tmp_path, monkeypatch):
    import io
    import zipfile

    import httpx

    settings = Settings(_env_file=None, base_dir=tmp_path)
    entry = WeeklyPlan.load(PLAN).entries[0]
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GH_TOKEN", "unit-test-secret")
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as archive:
        archive.writestr(f"output/{entry.anchor_date}/reel.mp4", b"anchor-video")
        archive.writestr("../../unwanted", b"never-extract")

    def handler(request):
        if request.url.host == "objects.example.com":
            assert "authorization" not in request.headers
            return httpx.Response(200, content=body.getvalue())
        assert request.headers["authorization"] == "Bearer unit-test-secret"
        if request.url.path == "/zip":
            return httpx.Response(302, headers={"location": "https://objects.example.com/a"})
        return httpx.Response(
            200,
            json={
                "artifacts": [
                    {
                        "name": "reelagent-state",
                        "expired": False,
                        "archive_download_url": "https://api.github.com/zip",
                    }
                ]
            },
        )

    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            path = await module.anchor_file(settings, entry, client)
            assert path.read_bytes() == b"anchor-video"

    asyncio.run(check())
    assert not (tmp_path / "unwanted").exists()


def test_production_plan_has_21_distinct_editions():
    plan = WeeklyPlan.load(Path(__file__).resolve().parents[1] / "prompts/current-week.json")
    assert len(plan.entries) == 21
    for day in range(1, 8):
        editions = [plan.entry(day, hour) for hour in (8, 12, 17)]
        assert len({entry.script.text for entry in editions}) == 3
        assert all(entry.social and entry.script for entry in editions)
    assert all(plan.entry(7, hour).mode == "recap" for hour in (8, 12, 17))
