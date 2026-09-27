"""Restore the latest completed state artifact; fail closed if existing history was lost."""

import asyncio
import io
import os
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx


def allowed_state_file(name: str, today: str, cache_files: set[str]) -> bool:
    return (
        name == "data/reelagent.db"
        or name in cache_files
        or name
        in {
            f"output/{today}/reel.mp4",
            f"output/{today}/metadata.json",
            f"output/{today}/subtitles.ass",
        }
    )


async def main() -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    headers = {
        "Authorization": "Bearer " + os.environ["GH_TOKEN"],
        "Accept": "application/vnd.github+json",
    }
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.get(
            f"https://api.github.com/repos/{repo}/actions/artifacts",
            headers=headers,
            params={"name": "reelagent-state", "per_page": 100},
        )
        response.raise_for_status()
        artifacts = response.json()["artifacts"]
        available = [a for a in artifacts if not a["expired"]]
        if not available:
            runs = await client.get(
                f"https://api.github.com/repos/{repo}/actions/workflows/daily-reel.yml/runs",
                headers=headers,
                params={"per_page": 100},
            )
            runs.raise_for_status()
            prior = [
                r
                for r in runs.json()["workflow_runs"]
                if str(r["id"]) != os.environ["GITHUB_RUN_ID"] and r["conclusion"] == "success"
            ]
            if artifacts or prior:
                raise RuntimeError(
                    "History artifact missing/expired. Restore a backup before generating more videos."
                )
            print("First run: starting new history")
            return
        artifact = max(available, key=lambda a: (a["created_at"], a["id"]))
        response = await client.get(artifact["archive_download_url"], headers=headers)
        if response.is_redirect:
            # Never forward the GitHub token to the signed object-storage URL.
            response = await client.get(response.headers["location"], follow_redirects=True)
        response.raise_for_status()
        today = (
            os.environ.get("RUN_SLOT")
            or datetime.now(ZoneInfo("Europe/Simferopol")).date().isoformat()
        )
        cache_files = set()
        plan_path = Path(os.environ.get("PROMPT_QUEUE_FILE", "prompts/current-week.json"))
        if plan_path.is_file():
            from app.core.prompt_queue import WeeklyPlan

            plan = WeeklyPlan.load(plan_path)
            cache_files = {f"data/week-cache/{plan.id}/{e.key}.mp4" for e in plan.entries}
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            if "data/reelagent.db" not in archive.namelist():
                raise RuntimeError("State artifact does not contain SQLite history")
            for item in archive.infolist():
                name = item.filename
                if allowed_state_file(name, today, cache_files):
                    path = Path(name)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(archive.read(item))
        print("Restored SQLite history and any current-day reel")


if __name__ == "__main__":
    asyncio.run(main())
    if os.environ.get("GITHUB_OUTPUT"):
        today = (
            os.environ.get("RUN_SLOT")
            or datetime.now(ZoneInfo("Europe/Simferopol")).date().isoformat()
        )
        ready = Path(f"output/{today}/reel.mp4").is_file()
        with open(os.environ["GITHUB_OUTPUT"], "a") as handle:
            handle.write(f"ready={str(ready).lower()}\n")
