"""Small Mac background receiver. Never renders or publishes anything."""

import fcntl
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.launch import ROOT, download, gh, repository
from scripts.status_dashboard import update as update_dashboard


def write_status(message: str) -> None:
    folder = ROOT / "Готовые ролики"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "Статус.txt").write_text(
        datetime.now().strftime("%d.%m.%Y %H:%M") + "\n" + message + "\n", encoding="utf-8"
    )


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
                "databaseId,status,conclusion,createdAt",
            )
        )
        update_dashboard(repo, runs, ROOT)
        seen = set()
        known_ids = {
            p.read_text().strip(): p.parent.name
            for p in (ROOT / "Готовые ролики").glob("*/.cloud-run-id")
        }
        delivered = []
        for run in runs:
            # Download successful or failed jobs: a publication error must not hide a ready MP4.
            if not run.get("conclusion"):
                continue
            created = datetime.fromisoformat(run["createdAt"].replace("Z", "+00:00"))
            if created < datetime.now(ZoneInfo("Europe/Simferopol")) - timedelta(days=2):
                continue
            if str(run["databaseId"]) in known_ids:
                seen.add(known_ids[str(run["databaseId"])])
                continue
            marker = local / ("downloaded-run-" + str(run["databaseId"]))
            if marker.exists():
                seen.add(marker.read_text())
                continue
            try:
                video = download(repo, run["databaseId"])
            except RuntimeError:
                continue
            slot = video.parent.name
            if slot in seen:
                marker.write_text("superseded")
                continue
            seen.add(slot)
            result = deliver(video, run["databaseId"])
            marker.write_text(slot)
            delivered.append(str(result))
        update_dashboard(repo, runs, ROOT)
        if delivered:
            write_status("Сохранены новые выпуски:\n" + "\n".join(delivered))
        else:
            write_status(
                "Получатель работает. Проверка каждые пять минут.\n"
                "Подробности: откройте «Статус агента.command».\n"
                "https://github.com/" + repo + "/actions/workflows/daily-reel.yml"
            )


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
