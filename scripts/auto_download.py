"""Small Mac background receiver. Never renders or publishes anything."""

import fcntl
import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.launch import ROOT, download, gh, repository


def request_backup(repo: str, runs: list[dict], now: datetime, local: Path) -> None:
    """One morning recovery if GitHub skipped its timers; respect explicit pauses."""
    if not 390 <= now.hour * 60 + now.minute <= 420:
        return
    today = now.date().isoformat()
    marker = local / "backup-request-day"
    if marker.exists() and marker.read_text() == today:
        return
    if any(not run["conclusion"] for run in runs):
        return
    enabled = gh("variable", "get", "DAILY_ENABLED", "--repo", repo).strip()
    if enabled != "true":
        return
    workflow = json.loads(gh("api", f"repos/{repo}/actions/workflows/daily-reel.yml"))
    if workflow["state"] == "disabled_manually":
        return
    if workflow["state"] == "disabled_inactivity":
        gh("workflow", "enable", "daily-reel.yml", "--repo", repo)
    elif workflow["state"] != "active":
        return
    marker.write_text(today)
    gh(
        "workflow",
        "run",
        "daily-reel.yml",
        "--repo",
        repo,
        "--field",
        "mode=generate",
        "--field",
        "request_id=morning-backup-" + today,
    )
    print(f"{now.isoformat()}: Запрошена резервная облачная сборка", flush=True)


def deliver(video: Path, run_id: int | None = None) -> Path:
    metadata = json.loads(video.with_name("metadata.json").read_text(encoding="utf-8"))
    target = ROOT / "Готовые ролики" / video.parent.name
    target.mkdir(parents=True, exist_ok=True)
    for name in ("reel.mp4", "metadata.json", "subtitles.ass", "preview.jpg"):
        source = video.with_name(name)
        if source.exists():
            temporary = target / (name + ".part")
            shutil.copy2(source, temporary)
            temporary.replace(target / name)
    (target / "Название.txt").write_text(metadata["title"] + "\n", encoding="utf-8")
    (target / "Описание.txt").write_text(
        metadata["description"] + "\n" + " ".join(metadata["hashtags"]) + "\n", encoding="utf-8"
    )
    if run_id is not None:
        (target / ".cloud-run-id").write_text(str(run_id))
    return target / "reel.mp4"


def main() -> None:
    local = ROOT / ".local"
    local.mkdir(exist_ok=True)
    with (local / "receiver.lock").open("w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        today = datetime.now(ZoneInfo("Europe/Simferopol")).date().isoformat()
        destination = ROOT / "Готовые ролики" / today / "reel.mp4"
        repo = repository()
        runs = json.loads(
            gh(
                "run",
                "list",
                "--repo",
                repo,
                "--workflow",
                "daily-reel.yml",
                "--limit",
                "20",
                "--json",
                "databaseId,conclusion,createdAt",
            )
        )
        for run in runs:
            day = (
                datetime.fromisoformat(run["createdAt"].replace("Z", "+00:00"))
                .astimezone(ZoneInfo("Europe/Simferopol"))
                .date()
                .isoformat()
            )
            if run["conclusion"] != "success" or day != today:
                continue
            marker = destination.with_name(".cloud-run-id")
            if (
                destination.exists()
                and marker.exists()
                and marker.read_text() == str(run["databaseId"])
            ):
                return
            video = download(repo, run["databaseId"])
            if video.parent.name != today:
                continue
            result = deliver(video, run["databaseId"])
            shutil.rmtree(local / "downloads" / str(run["databaseId"]), ignore_errors=True)
            print(f"{datetime.now().isoformat()}: Сохранено {result}", flush=True)
            return
        request_backup(repo, runs, datetime.now(ZoneInfo("Europe/Simferopol")), local)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Do not print responses or credentials from subprocesses.
        print(
            f"{datetime.now().isoformat()}: Скачивание отложено ({type(error).__name__}); повтор через 5 минут",
            flush=True,
        )
        raise SystemExit(1)
