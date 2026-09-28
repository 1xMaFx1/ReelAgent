"""Shared, credential-free release catalog. GitHub CLI handles authentication."""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = re.compile(r"<!-- reelagent:(.*?) -->", re.DOTALL)
REQUIRED = {"reel.mp4", "metadata.json", "recap.mp4"}


def gh(*args, root=ROOT):
    binary = root / ".local/bin/gh"
    result = subprocess.run(
        [str(binary) if binary.exists() else "gh", *args], capture_output=True, text=True, cwd=root
    )
    if result.returncode:
        raise RuntimeError("GitHub не выполнил запрос. Проверьте вход и подключение к интернету.")
    return result.stdout


def repository(root=ROOT):
    repo = json.loads((root / "launcher.json").read_text())["repository"]
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        raise ValueError("Некорректное имя репозитория")
    return repo


def release_info(release):
    match = MARKER.search(release.get("body") or "")
    if not match or release.get("draft"):
        return None
    try:
        meta = json.loads(match.group(1))
    except ValueError:
        return None
    if not re.fullmatch(r"reel-[a-f0-9]{16}", release.get("tag_name", "")):
        return None
    assets = {asset["name"]: asset for asset in release.get("assets", [])}
    if not REQUIRED <= assets.keys():
        return None
    return {
        **meta,
        "tag": release["tag_name"],
        "title": release["name"],
        "url": release["html_url"],
        "created_at": release["published_at"],
        "assets": assets,
    }


def releases(repo, root=ROOT):
    pages = json.loads(
        gh("api", f"repos/{repo}/releases?per_page=100", "--paginate", "--slurp", root=root)
    )
    return [item for page in pages for item in page]


def ready_releases(repo, root=ROOT):
    return sorted(
        [info for release in releases(repo, root) if (info := release_info(release))],
        key=lambda item: item.get("created_at") or "",
        reverse=True,
    )
