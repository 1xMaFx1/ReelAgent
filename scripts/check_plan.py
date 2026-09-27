"""Validate the complete weekly packet before spending cloud render time."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import Settings
from app.core.prompt_queue import WeeklyPlan


def main():
    settings = Settings()
    if settings.content_mode != "prompt_queue":
        return
    plan = WeeklyPlan.load(settings.path(str(settings.prompt_queue_file)))
    slot = settings.run_slot
    day = slot[:10] if slot else datetime.now(ZoneInfo("Europe/Simferopol")).date().isoformat()
    entry = plan.for_date(day, int(slot[11:]) if slot else 8)
    for item in plan.entries:
        if item.mode != "anchor" and (item.script is None or item.social is None):
            raise ValueError(f"День {item.day}: подготовьте проверенный сценарий из промпта Claude")
    print(f"Пакет {plan.id}: день {entry.day}, {entry.topic}")


if __name__ == "__main__":
    main()
