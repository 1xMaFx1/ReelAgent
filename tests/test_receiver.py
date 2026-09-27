import json
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts import auto_download as receiver


def test_deliver(tmp_path, monkeypatch):
    monkeypatch.setattr(receiver, "ROOT", tmp_path)
    source = tmp_path / "output/2026-09-27"
    source.mkdir(parents=True)
    (source / "reel.mp4").write_bytes(b"example")
    (source / "metadata.json").write_text(
        json.dumps(
            {
                "title": "Почему Юпитер полосатый?",
                "description": "Юпитер, космос",
                "hashtags": ["#космос"],
            }
        )
    )
    result = receiver.deliver(source / "reel.mp4")
    assert result.read_bytes() == b"example"
    assert result.with_name("Описание.txt").read_text() == "Юпитер, космос\n#космос\n"


def test_no_stale_run(tmp_path, monkeypatch):
    monkeypatch.setattr(receiver, "request_backup", lambda *args: None)
    monkeypatch.setattr(receiver, "ROOT", tmp_path)
    monkeypatch.setattr(receiver, "repository", lambda: "owner/repo")
    monkeypatch.setattr(
        receiver,
        "gh",
        lambda *args: json.dumps(
            [{"databaseId": 1, "conclusion": "success", "createdAt": "2020-01-01T06:00:00Z"}]
        ),
    )
    monkeypatch.setattr(
        receiver, "download", lambda *args: (_ for _ in ()).throw(AssertionError("stale download"))
    )
    monkeypatch.setattr(receiver, "update_dashboard", lambda *args: None)
    receiver.main()


def test_backup_respects_pause_and_requests_once(tmp_path, monkeypatch):
    now = datetime(2026, 9, 27, 6, 35, tzinfo=ZoneInfo("Europe/Simferopol"))
    calls = []
    enabled = "false"

    def fake_gh(*args):
        calls.append(args)
        if args[0] == "variable":
            return enabled
        return json.dumps({"state": "active"})

    monkeypatch.setattr(receiver, "gh", fake_gh)
    receiver.request_backup("a/b", [], now, tmp_path)
    assert not (tmp_path / "backup-request-day").exists()
    enabled = "true"
    receiver.request_backup("a/b", [], now, tmp_path)
    receiver.request_backup("a/b", [], now, tmp_path)
    assert sum(args[:2] == ("workflow", "run") for args in calls) == 1


def test_idle_after_delivery(tmp_path, monkeypatch):
    monkeypatch.setattr(receiver, "ROOT", tmp_path)
    today = datetime.now(ZoneInfo("Europe/Simferopol")).date().isoformat()
    target = tmp_path / "Готовые ролики" / today / "reel.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"ready")
    target.with_name(".cloud-run-id").write_text("1")
    monkeypatch.setattr(receiver, "repository", lambda: "owner/repo")
    monkeypatch.setattr(
        receiver,
        "gh",
        lambda *args: json.dumps(
            [{"databaseId": 1, "conclusion": "success", "createdAt": today + "T06:00:00Z"}]
        ),
    )
    monkeypatch.setattr(
        receiver,
        "download",
        lambda *args: (_ for _ in ()).throw(AssertionError("duplicate download")),
    )
    monkeypatch.setattr(receiver, "update_dashboard", lambda *args: None)
    receiver.main()
