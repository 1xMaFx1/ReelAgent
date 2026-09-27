"""One-click Mac controller: credentials stay in Keychain/GitHub, render stays in the cloud."""

import argparse
import fcntl
import getpass
import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def repository() -> str:
    value = json.loads((ROOT / "launcher.json").read_text())["repository"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("Некорректное имя репозитория в launcher.json")
    return value


def executable() -> str:
    bundled = ROOT / ".local/bin/gh"
    if bundled.is_file():
        return str(bundled)
    installed = shutil.which("gh")
    if installed:
        return installed
    raise RuntimeError("GitHub CLI не найден. Требуется однократная установка GitHub CLI.")


def gh(*args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        [executable(), *args], input=input_text, text=True, capture_output=True, cwd=ROOT
    )
    if result.returncode:
        # Never echo input_text: it may contain an API key.
        raise RuntimeError("GitHub: " + result.stderr.strip()[-1500:])
    return result.stdout


def safari(url: str) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", "-a", "Safari", url], check=False)
    else:
        print(url)


def connect_buffer(repo: str, key: str) -> None:
    def query(text: str, variables: dict | None = None) -> dict:
        req = Request(
            "https://api.buffer.com",
            data=json.dumps({"query": text, "variables": variables or {}}).encode(),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        )
        with urlopen(req, timeout=60) as response:
            result = json.load(response)
        if result.get("errors"):
            raise RuntimeError("Buffer отклонил запрос. Проверьте ключ и подключение канала.")
        return result["data"]

    organizations = query("{account{organizations{id}}}")["account"]["organizations"]
    matches = []
    for organization in organizations:
        result = query(
            "query($input:ChannelsInput!){channels(input:$input){id service serviceId isDisconnected}}",
            {"input": {"organizationId": organization["id"]}},
        )
        matches.extend(
            channel
            for channel in result["channels"]
            if channel["service"] == "youtube"
            and channel["serviceId"] == "UCr74LNUyePqX4CLS9sI5IPg"
            and not channel["isDisconnected"]
        )
    if len(matches) != 1:
        raise RuntimeError("В Buffer не найден однозначно ваш подключённый YouTube-канал.")
    gh("variable", "set", "BUFFER_CHANNEL_ID", "--repo", repo, "--body", matches[0]["id"])
    print("YouTube-канал проверен и выбран автоматически.")


def setup(repo: str) -> None:
    print("Для создания роликов ключи не нужны: облачная модель Ollama и библиотека NASA.")
    print("GitHub подключён. Автопубликация выключена.")
    return
    print("Ключи будут отправлены только в GitHub Secrets вашего ReelAgent.")
    print("Ввод скрыт. Ключи не сохраняются в файлах и не попадают в публичный код.")
    variables = json.loads(gh("variable", "list", "--repo", repo, "--json", "name,value"))
    provider = next((v["value"] for v in variables if v["name"] == "LLM_PROVIDER"), "gemini")
    keys = [("PEXELS_API_KEY", "https://www.pexels.com/api/")]
    keys.extend(
        [
            ("BUFFER_API_KEY", "https://publish.buffer.com/settings/api"),
            ("CLOUDINARY_CLOUD_NAME", "https://console.cloudinary.com/"),
            ("CLOUDINARY_API_KEY", "https://console.cloudinary.com/"),
            ("CLOUDINARY_API_SECRET", "https://console.cloudinary.com/"),
        ]
    )
    if provider != "ollama":
        print("Для Gemini используйте проект Free tier без подключённого биллинга.")
        keys.insert(0, ("GEMINI_API_KEY", "https://aistudio.google.com/apikey"))
    else:
        print("Облачной модели Ollama не нужен API-ключ.")
    for name, url in keys:
        print(f"\n{name}: {url}")
        value = getpass.getpass("Вставьте ключ (Enter — оставить существующий): ").strip()
        if value:
            gh("secret", "set", name, "--repo", repo, input_text=value)
            print("Сохранено в GitHub Secrets.")
            if name == "BUFFER_API_KEY":
                connect_buffer(repo, value)
    print("\nГотово. Запуск: файл «Запустить ReelAgent.command».")


def find_run(repo: str, request_id: str) -> dict:
    title = f"ReelAgent {request_id}"
    for _ in range(40):
        runs = json.loads(
            gh(
                "run",
                "list",
                "--repo",
                repo,
                "--workflow",
                "daily-reel.yml",
                "--limit",
                "30",
                "--json",
                "databaseId,displayTitle,url,status,conclusion",
            )
        )
        for run in runs:
            if run["displayTitle"] == title:
                return run
        time.sleep(3)
    raise RuntimeError("GitHub принял запрос, но запуск ещё не появился. Проверьте Actions.")


def wait_run(repo: str, run: dict) -> dict:
    previous = None
    deadline = time.monotonic() + 50 * 60
    while time.monotonic() < deadline:
        state = json.loads(
            gh(
                "run",
                "view",
                str(run["databaseId"]),
                "--repo",
                repo,
                "--json",
                "status,conclusion,url",
            )
        )
        if state["status"] != previous:
            labels = {
                "queued": "В очереди",
                "in_progress": "Создаётся в облаке",
                "completed": "Завершено",
            }
            print(labels.get(state["status"], state["status"]), flush=True)
            previous = state["status"]
        if state["status"] == "completed":
            return state
        time.sleep(10)
    raise RuntimeError("Ожидание завершено; запуск продолжает работать в GitHub Actions.")


def download(repo: str, run_id: int) -> Path:
    destination = ROOT / ".local/downloads" / str(run_id)
    destination.mkdir(parents=True, exist_ok=True)
    gh(
        "run",
        "download",
        str(run_id),
        "--repo",
        repo,
        "--pattern",
        "reel-*",
        "--dir",
        str(destination),
    )
    candidates = list(destination.rglob("reel.mp4"))
    if len(candidates) != 1:
        raise RuntimeError("Готовый MP4 не найден. Откройте журнал запуска в Actions.")
    source = candidates[0]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", source.parent.name):
        raise RuntimeError("Неожиданная структура архива ролика")
    target = ROOT / "output" / source.parent.name
    target.mkdir(parents=True, exist_ok=True)
    for name in ("reel.mp4", "metadata.json", "subtitles.ass", "preview.jpg"):
        if (source.parent / name).exists():
            shutil.copy2(source.parent / name, target / name)
    return target / "reel.mp4"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--generate-only", action="store_true")
    parser.add_argument("--no-open", action="store_true", help="Download without opening a browser")
    args = parser.parse_args()
    repo = repository()
    gh("api", "user", "--jq", ".login")
    if args.setup:
        setup(repo)
        return
    (ROOT / ".local").mkdir(exist_ok=True)
    with (ROOT / ".local/launch.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                "ReelAgent уже запущен. Дождитесь результата в открытом окне."
            ) from None
        request_id = uuid.uuid4().hex[:12]
        print("ReelAgent — создаём ролик в облаке. На Mac рендер не выполняется.", flush=True)
        gh(
            "workflow",
            "run",
            "daily-reel.yml",
            "--repo",
            repo,
            "--field",
            "mode=generate",
            "--field",
            f"request_id={request_id}",
        )
        run = find_run(repo, request_id)
        print("Ход работы: " + run["url"], flush=True)
        state = wait_run(repo, run)
        if state["conclusion"] != "success":
            if not args.no_open:
                safari(state["url"])
            raise RuntimeError("Облачный запуск завершился с ошибкой. Журнал открыт в Safari.")
        video = download(repo, run["databaseId"])
        meta = json.loads(video.with_name("metadata.json").read_text())
        print("\nГотово: " + str(video))
        for name in ("youtube", "instagram"):
            if meta.get(name):
                if str(meta[name]).startswith("buffer:"):
                    print(f"{name}: поставлено в расписание на 08:00, ещё не опубликовано")
                else:
                    print(f"{name}: опубликовано ({meta[name]})")
            elif meta.get("publication_errors", {}).get(name):
                print(f"{name}: публикация требует проверки; готовый MP4 сохранён")
            else:
                print(f"{name}: публикация не настроена или отключена")
        if not args.no_open:
            safari(video.as_uri())


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError) as error:
        print("\n" + str(error), file=sys.stderr)
        sys.exit(1)
