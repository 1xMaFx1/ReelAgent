"""A read-only local dashboard refreshed by the lightweight Mac receiver."""

import html
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.launch import ROOT, gh, repository, safari


def collect(root: Path, repo: str, runs: list[dict], enabled: str, now: datetime) -> dict:
    newest = runs[0] if runs else {}
    state = newest.get("status")
    conclusion = newest.get("conclusion")
    if state in {"queued", "waiting", "pending", "requested"}:
        stage = "Ожидает запуска в облаке"
    elif state == "in_progress" or (newest and not conclusion):
        stage = "Работает в облаке"
    elif conclusion == "success":
        stage = "Последний запуск завершён"
    elif conclusion:
        stage = "Последний запуск требует проверки"
    else:
        stage = "Запусков пока нет"
    files = []
    for path in (root / "Готовые ролики").glob("*/metadata.json"):
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        video = path.with_name("reel.mp4")
        if video.is_file():
            files.append(
                {
                    "slot": path.parent.name,
                    "title": meta.get("title", "Ролик"),
                    "video": video.as_uri(),
                    "instagram": meta.get("instagram"),
                    "instagram_state": meta.get("instagram_state"),
                    "due_at": meta.get("instagram_due_at"),
                    "publication_errors": bool(meta.get("publication_errors")),
                }
            )
    files.sort(key=lambda item: item["slot"], reverse=True)
    upcoming = []
    try:
        from datetime import date, timedelta

        plan = json.loads((root / "prompts/current-week.json").read_text())
        for entry in plan["entries"]:
            day = date.fromisoformat(plan["start_date"]) + timedelta(days=entry["day"] - 1)
            target = datetime.combine(day, datetime.min.time()).replace(
                hour=entry.get("hour", 8), tzinfo=ZoneInfo("Europe/Simferopol")
            )
            if target > now:
                upcoming.append(target.isoformat())
        if not upcoming:
            stage = "Промпты закончились — нужен новый пакет"
    except (OSError, ValueError, KeyError):
        pass
    return {
        "next_release": min(upcoming) if upcoming else None,
        "remaining_slots": len(upcoming),
        "updated": now.isoformat(),
        "stage": stage,
        "schedule": {"true": "Включено", "false": "Выключено"}.get(enabled, "Не подтверждено"),
        "runs_url": f"https://github.com/{repo}/actions/workflows/daily-reel.yml",
        "run_id": newest.get("databaseId"),
        "conclusion": conclusion,
        "files": files[:21],
    }


def render(snapshot: dict) -> str:
    def esc(value):
        return html.escape(str(value), quote=True)

    cards = []
    for item in snapshot["files"]:
        publication = (
            "Instagram: опубликовано"
            if item["instagram"]
            else "Instagram: требуется проверка"
            if item["publication_errors"]
            else "Instagram: запланировано"
            if item.get("instagram_state") == "scheduled"
            else "Instagram: требуется проверка"
            if item.get("instagram_state") == "needs_review"
            else "Instagram: не подключён"
            if item.get("instagram_state") == "not_connected"
            else "Instagram: публикация не подтверждена"
        )
        cards.append(
            f"<article><small>{esc(item['slot'])}</small><h3>{esc(item['title'])}</h3>"
            f'<p>{publication}</p><a href="{esc(item["video"])}">Открыть видео →</a></article>'
        )
    return """<!doctype html><html lang="ru"><meta charset="utf-8"><meta http-equiv="refresh" content="60">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ReelAgent — состояние</title>
<style>body{background:#101820;color:#edf3f6;font:17px system-ui;margin:0;padding:6vw;max-width:1100px}
h1{font-size:46px;margin:12px 0}small,.note{color:#b6c7d3}a{color:#8be5c3}section{display:flex;gap:18px;flex-wrap:wrap}
article{background:#1c2b38;border:1px solid #334a59;border-radius:18px;padding:24px;min-width:230px;flex:1}
.banner{border-left:4px solid #8be5c3;padding:18px;background:#1c2b38;margin:24px 0}h3{font-size:22px}</style>
<small>REELAGENT / ПАНЕЛЬ СОСТОЯНИЯ</small><h1>Что делает агент</h1>""" + (
        f'<div class="banner"><h2>{esc(snapshot["stage"])}</h2>'
        f"<p>Расписание: <strong>{esc(snapshot['schedule'])}</strong></p>"
        f"<p>Ближайший выпуск: {esc(snapshot.get('next_release') or 'не назначен')} · Осталось выпусков по плану: {snapshot.get('remaining_slots', 0)}</p>"
        f'<p>Последняя проверка: <time id="checked">{esc(snapshot["updated"])}</time></p></div>'
        '<p id="stale" class="note">Это последний полученный статус, а не постоянное соединение с облаком. '
        "Mac обновляет данные примерно раз в пять минут.</p>"
        f'<p><a href="{esc(snapshot["runs_url"])}">Открыть живой журнал в GitHub →</a></p>'
        "<h2>Сохранённые ролики</h2><section>"
        + ("".join(cards) or "<p>Скачанных роликов пока нет.</p>")
        + '</section><script>const t=Date.parse(document.getElementById("checked").textContent);'
        'if(Date.now()-t>600000)document.getElementById("stale").textContent='
        '"Данные устарели: более 10 минут без обновления. Проверьте интернет и работу получателя на Mac.";'
        "</script></html>"
    )


def write_dashboard(snapshot: dict, root: Path = ROOT):
    folder = root / "Готовые ролики"
    folder.mkdir(parents=True, exist_ok=True)
    for name, body in (
        ("Статус агента.html", render(snapshot)),
        ("status.json", json.dumps(snapshot, ensure_ascii=False, indent=2)),
    ):
        temporary = folder / (name + ".part")
        temporary.write_text(body, encoding="utf-8")
        temporary.replace(folder / name)


def update(repo: str, runs: list[dict], root: Path = ROOT):
    try:
        enabled = gh("variable", "get", "DAILY_ENABLED", "--repo", repo).strip()
    except RuntimeError:
        enabled = "unknown"
    snapshot = collect(root, repo, runs, enabled, datetime.now(ZoneInfo("Europe/Simferopol")))
    write_dashboard(snapshot, root)


def main():
    repo = repository()
    try:
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
        update(repo, runs)
    except (RuntimeError, ValueError):
        snapshot = collect(ROOT, repo, [], "unknown", datetime.now(ZoneInfo("Europe/Simferopol")))
        snapshot["stage"] = "Не удалось связаться с GitHub. Работа в облаке не подтверждена."
        write_dashboard(snapshot)
    safari((ROOT / "Готовые ролики/Статус агента.html").as_uri())


if __name__ == "__main__":
    main()
