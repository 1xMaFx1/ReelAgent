import asyncio
import io
import zipfile
from datetime import datetime, timezone

import httpx

from scripts import cloud_state


def test_restore_redirect_and_current_day_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "22")
    monkeypatch.setenv("GH_TOKEN", "private-test-token")
    today = datetime.now(timezone.utc).date().isoformat()
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as archive:
        archive.writestr("data/reelagent.db", b"fake-state")
        archive.writestr(f"output/{today}/reel.mp4", b"today")
        archive.writestr("output/2000-01-01/reel.mp4", b"old")
        archive.writestr("../../bad", b"bad")

    def handler(request):
        if request.url.host == "objects.example.com":
            assert "Authorization" not in request.headers
            return httpx.Response(200, content=body.getvalue())
        assert request.headers["Authorization"] == "Bearer private-test-token"
        if request.url.path.endswith("/zip"):
            return httpx.Response(302, headers={"location": "https://objects.example.com/file"})
        return httpx.Response(
            200,
            json={
                "artifacts": [
                    {
                        "expired": False,
                        "id": 5,
                        "created_at": "2026-01-01",
                        "archive_download_url": "https://api.github.com/zip",
                    }
                ]
            },
        )

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        cloud_state.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    asyncio.run(cloud_state.main())
    assert (tmp_path / "data/reelagent.db").read_bytes() == b"fake-state"
    assert (tmp_path / f"output/{today}/reel.mp4").exists()
    assert not (tmp_path / "output/2000-01-01").exists()
