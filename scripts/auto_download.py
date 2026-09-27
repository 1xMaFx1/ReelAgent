"""Small Mac background receiver. Never renders or publishes anything."""

import fcntl
import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.launch import ROOT, download, gh, repository


def deliver(video: Path) -> Path:
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
        if destination.exists():
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
            video = download(repo, run["databaseId"])
            if video.parent.name != today:
                continue
            result = deliver(video)
            shutil.rmtree(local / "downloads" / str(run["databaseId"]), ignore_errors=True)
            print(f"{datetime.now().isoformat()}: Сохранено {result}", flush=True)
            return


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
