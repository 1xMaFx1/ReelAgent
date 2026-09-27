"""Store owner-approved public MP4 assets in GitHub Releases, never in git history."""

import hashlib
import json
import os
import re
import subprocess

from app.config import Settings
from app.utils.files import save_json


def run(*args):
    result = subprocess.run(["gh", *args], check=True, capture_output=True, text=True)
    return result.stdout


def main():
    settings = Settings()
    settings.require_cloud()
    slot = settings.run_slot
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-(08|12|17)", slot):
        raise ValueError("Missing publication slot")
    repo = os.environ["GITHUB_REPOSITORY"]
    video = settings.path(f"output/{slot}/reel.mp4")
    meta_path = video.with_name("metadata.json")
    meta = json.loads(meta_path.read_text())
    tag = "reel-" + slot
    found = subprocess.run(
        ["gh", "release", "view", tag, "--repo", repo, "--json", "assets"],
        capture_output=True,
        text=True,
    )
    if found.returncode:
        run(
            "release",
            "create",
            tag,
            "--repo",
            repo,
            "--target",
            os.environ["GITHUB_SHA"],
            "--title",
            "ReelAgent " + slot,
            "--notes",
            "Готовый ролик ReelAgent. Источники изображений и фактов: NASA.",
        )
        assets = []
    else:
        assets = json.loads(found.stdout)["assets"]
    if not any(asset["name"] == "reel.mp4" for asset in assets):
        run("release", "upload", tag, str(video), "--repo", repo)
    meta["public_video_url"] = f"https://github.com/{repo}/releases/download/{tag}/reel.mp4"
    meta["video_sha256"] = hashlib.sha256(video.read_bytes()).hexdigest()
    save_json(meta_path, meta)
    print("Публичная копия MP4 сохранена в Releases")


if __name__ == "__main__":
    main()
