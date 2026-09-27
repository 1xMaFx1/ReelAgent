from datetime import datetime, timezone

from scripts.status_dashboard import collect, render


def test_dashboard_does_not_claim_schedule_or_publication(tmp_path):
    snapshot = collect(
        tmp_path,
        "a/b",
        [{"status": "completed", "conclusion": "success"}],
        "unknown",
        datetime.now(timezone.utc),
    )
    assert snapshot["schedule"] == "Не подтверждено"
    assert snapshot["stage"] == "Последний запуск завершён"
    assert snapshot["files"] == []


def test_dashboard_escapes_titles_and_labels_stale_snapshot(tmp_path):
    snapshot = collect(tmp_path, "a/b", [], "false", datetime.now(timezone.utc))
    snapshot["files"] = [
        {
            "slot": "2026-09-28-08",
            "title": "<script>alert(1)</script>",
            "video": "file:///tmp/video.mp4",
            "instagram": None,
            "publication_errors": True,
        }
    ]
    page = render(snapshot)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
    assert "Данные устарели" in page
    assert "требуется проверка" in page
