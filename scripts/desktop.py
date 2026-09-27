"""Small localhost control panel. Cloud renders; downloads happen only on a click."""

import argparse
import hashlib
import json
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

from scripts.library import ROOT, gh, ready_releases, repository

PORT = 8766
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.Lock()


class Controller:
    def __init__(self, root=ROOT):
        self.root = root
        self.repo = repository(root)
        self.pending = None
        self.cache = None
        self.cached_at = 0

    def runs(self):
        return json.loads(
            gh(
                "run",
                "list",
                "--repo",
                self.repo,
                "--workflow",
                "create-reel.yml",
                "--limit",
                "10",
                "--json",
                "databaseId,displayTitle,status,conclusion,url",
                root=self.root,
            )
        )

    def snapshot(self, force=False):
        if not force and self.cache and time.monotonic() - self.cached_at < 15:
            return self.cache
        runs = self.runs()
        ready = ready_releases(self.repo, self.root)
        active = next((r for r in runs if r["status"] != "completed"), None)
        if self.pending and any(self.pending in r["displayTitle"] for r in runs):
            self.pending = None
        plan = json.loads((self.root / "prompts/current-week.json").read_text())
        remaining = max(
            0, len(plan["entries"]) - sum(r.get("plan_id") == plan["id"] for r in ready)
        )
        state = (
            "Создаётся в облаке"
            if active
            else "Запуск принят, ожидаем облако"
            if self.pending
            else "Готов к работе"
        )
        if not active and not self.pending and not remaining:
            state = "Промпты закончились — добавьте новый пакет"
        if (
            not active
            and not self.pending
            and runs
            and runs[0]["conclusion"] not in {"success", ""}
        ):
            state = "Последняя попытка не завершилась. Можно повторить."
        result = {
            "stage": state,
            "busy": bool(active or self.pending),
            "remaining": remaining,
            "run_url": (active or (runs[0] if runs else {})).get(
                "url", f"https://github.com/{self.repo}/actions/workflows/create-reel.yml"
            ),
            "files": [
                {
                    "tag": r["tag"],
                    "title": r["title"],
                    "url": r["url"],
                    "saved": (self.root / "Готовые ролики" / r["tag"] / "reel.mp4").is_file(),
                }
                for r in ready
            ],
        }
        self.cache, self.cached_at = result, time.monotonic()
        return result

    def generate(self):
        with LOCK:
            state = self.snapshot(force=True)
            if state["busy"]:
                raise ValueError("Ролик уже создаётся. Дождитесь завершения.")
            if not state["remaining"]:
                raise ValueError("Нужен новый пакет промптов")
            request = uuid.uuid4().hex
            gh(
                "workflow",
                "run",
                "create-reel.yml",
                "--repo",
                self.repo,
                "--field",
                "request_id=" + request,
                root=self.root,
            )
            self.pending = request
            self.cache = None
            return {"message": "Запуск принят. Компьютер можно выключить — GitHub пришлёт письмо."}

    def download(self, tag):
        if not re.fullmatch(r"reel-[a-f0-9]{16}", tag):
            raise ValueError("Некорректный выпуск")
        with LOCK:
            ready = next((r for r in ready_releases(self.repo, self.root) if r["tag"] == tag), None)
            if ready is None:
                raise ValueError("Выпуск ещё не готов")
            target = self.root / "Готовые ролики" / tag
            temp_root = self.root / ".local/downloads"
            temp_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=temp_root) as temp:
                folder = Path(temp)
                gh(
                    "release",
                    "download",
                    tag,
                    "--repo",
                    self.repo,
                    "--pattern",
                    "reel.mp4",
                    "--pattern",
                    "metadata.json",
                    "--pattern",
                    "subtitles.ass",
                    "--dir",
                    temp,
                    root=self.root,
                )
                meta = json.loads((folder / "metadata.json").read_text())
                if meta.get("prompt_key") != ready["prompt_key"]:
                    raise ValueError("Метаданные не соответствуют выпуску")
                digest = ready["assets"]["reel.mp4"].get("digest")
                if (
                    digest
                    and digest
                    != "sha256:" + hashlib.sha256((folder / "reel.mp4").read_bytes()).hexdigest()
                ):
                    raise ValueError("Ошибка проверки скачанного MP4")
                target.mkdir(parents=True, exist_ok=True)
                for name in ("reel.mp4", "metadata.json", "subtitles.ass"):
                    if (folder / name).exists():
                        part = target / (name + ".part")
                        shutil.copyfile(folder / name, part)
                        part.replace(target / name)
                (target / "Название.txt").write_text(meta["title"] + "\n", encoding="utf-8")
                (target / "Описание.txt").write_text(
                    meta["description"] + "\n" + " ".join(meta["hashtags"]) + "\n", encoding="utf-8"
                )
            self.cache = None
            return {
                "message": "Сохранено на рабочем столе: ReelAgent → Готовые ролики → " + tag,
                "path": str(target / "reel.mp4"),
            }


CONTROL = None


def html_page():
    return (ROOT / "assets/panel.html").read_text().replace("__TOKEN__", TOKEN)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def authorized_host(self):
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

    def respond(self, value, code=200, content_type="application/json"):
        body = (
            value.encode()
            if isinstance(value, str)
            else json.dumps(value, ensure_ascii=False).encode()
        )
        self.send_response(code)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'unsafe-inline'; script-src 'nonce-"
            + TOKEN
            + "'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.authorized_host():
            return self.respond({"error": "Local access only"}, 403)
        try:
            if self.path == "/":
                return self.respond(html_page(), content_type="text/html")
            if self.path == "/health":
                return self.respond({"app": "ReelAgent", "root": str(ROOT)})
            if self.path == "/api/status":
                return self.respond(CONTROL.snapshot())
            self.respond({"error": "Not found"}, 404)
        except Exception as error:
            self.respond(
                {
                    "error": str(error)
                    if isinstance(error, (ValueError, RuntimeError))
                    else "Не удалось проверить облако. Проверьте интернет."
                },
                503,
            )

    def do_POST(self):
        origin = self.headers.get("Origin")
        expected = f"http://127.0.0.1:{self.server.server_port}"
        if (
            not self.authorized_host()
            or self.headers.get("X-ReelAgent-Token") != TOKEN
            or (origin and origin != expected)
        ):
            return self.respond({"error": "Недопустимый запрос"}, 403)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 2048:
                raise ValueError("Некорректный запрос")
            data = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/generate":
                return self.respond(CONTROL.generate())
            if self.path == "/api/download":
                return self.respond(CONTROL.download(data.get("tag", "")))
            self.respond({"error": "Not found"}, 404)
        except Exception as error:
            self.respond(
                {
                    "error": str(error)
                    if isinstance(error, (ValueError, RuntimeError))
                    else "Операция не завершена. Можно повторить."
                },
                400,
            )


def main():
    global CONTROL
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    if args.serve:
        CONTROL = Controller()
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
        return
    url = f"http://127.0.0.1:{PORT}"
    running = False
    try:
        with urlopen(url + "/health", timeout=2) as response:
            state = json.load(response)
        running = state == {"app": "ReelAgent", "root": str(ROOT)}
        if not running:
            raise RuntimeError("Порт панели занят другим приложением")
    except OSError:
        pass
    if not running:
        local = ROOT / ".local"
        local.mkdir(exist_ok=True)
        with (local / "panel.log").open("a") as log:
            subprocess.Popen(
                [sys.executable, "-m", "scripts.desktop", "--serve"],
                cwd=ROOT,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        for _ in range(40):
            try:
                with urlopen(url + "/health", timeout=1) as response:
                    running = json.load(response).get("app") == "ReelAgent"
                if running:
                    break
            except OSError:
                time.sleep(0.1)
        if not running:
            raise RuntimeError("Панель не запустилась. Проверьте .local/panel.log")
    if not args.no_open:
        subprocess.run(["open", "-a", "Safari", url], check=True)
    print(url)


if __name__ == "__main__":
    main()
