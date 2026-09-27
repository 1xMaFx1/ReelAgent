import json
from pathlib import Path

import pytest

from app.core.prompt_queue import WeeklyPlan
from scripts import desktop
from scripts.create_next import release_body, select_entry
from scripts.library import release_info

PLAN = Path(__file__).resolve().parents[1] / "prompts/current-week.json"


def test_next_reel_is_independent_of_dates_and_retries():
    plan = WeeklyPlan.load(PLAN)
    entry, previous = select_entry(plan, [], "request1")
    assert entry == plan.entries[0] and previous is None
    ready = [{"prompt_key": entry.key, "request_id": "request1", "url": "https://github.com/a/b"}]
    assert select_entry(plan, ready, "request2")[0] == plan.entries[1]
    assert select_entry(plan, ready, "request1") == (None, ready[0])
    all_ready = [{"prompt_key": e.key, "request_id": str(i)} for i, e in enumerate(plan.entries)]
    assert select_entry(plan, all_ready, "finished") == (None, None)


def test_incomplete_release_never_appears_ready():
    plan = WeeklyPlan.load(PLAN)
    entry = plan.entries[0]
    release = {
        "body": release_body(entry, plan, "request"),
        "tag_name": "reel-" + entry.key,
        "name": "Title",
        "html_url": "https://github.com/a/b",
        "published_at": "2026-01-01",
        "assets": [{"name": "reel.mp4"}, {"name": "recap.mp4"}],
    }
    assert release_info(release) is None
    release["assets"].append({"name": "metadata.json"})
    assert release_info(release)["prompt_key"] == entry.key
    release["draft"] = True
    assert release_info(release) is None


def test_download_only_explicit_and_safe(tmp_path, monkeypatch):
    (tmp_path / "launcher.json").write_text('{"repository":"owner/repo"}')
    controller = desktop.Controller(tmp_path)
    tag = "reel-" + "a" * 16
    record = {"tag": tag, "prompt_key": "a" * 16, "assets": {"reel.mp4": {}}}
    monkeypatch.setattr(desktop, "ready_releases", lambda *args: [record])
    calls = []

    def fake_gh(*args, **kwargs):
        calls.append(args)
        folder = Path(args[args.index("--dir") + 1])
        (folder / "reel.mp4").write_bytes(b"unit test video")
        (folder / "metadata.json").write_text(
            json.dumps(
                {
                    "prompt_key": "a" * 16,
                    "title": "Звёзды",
                    "description": "космос, наука",
                    "hashtags": ["#наука"],
                }
            )
        )
        return ""

    monkeypatch.setattr(desktop, "gh", fake_gh)
    assert not (tmp_path / "Готовые ролики").exists()
    with pytest.raises(ValueError):
        controller.download("../../escape")
    assert not calls
    result = controller.download(tag)
    assert Path(result["path"]).read_bytes() == b"unit test video"
    assert Path(result["path"]).with_name("Описание.txt").read_text() == "космос, наука\n#наука\n"


def test_busy_cloud_prevents_second_dispatch(tmp_path, monkeypatch):
    (tmp_path / "launcher.json").write_text('{"repository":"owner/repo"}')
    controller = desktop.Controller(tmp_path)
    monkeypatch.setattr(controller, "snapshot", lambda **kwargs: {"busy": True, "remaining": 20})
    monkeypatch.setattr(desktop, "gh", lambda *args, **kwargs: pytest.fail("duplicate dispatch"))
    with pytest.raises(ValueError, match="уже создаётся"):
        controller.generate()
