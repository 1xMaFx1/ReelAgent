import os
from datetime import datetime, timezone

from app.config import Settings
from app.core.prompt_queue import WeeklyPlan
from app.core.slots import slot_for

slot = slot_for(
    datetime.now(timezone.utc),
    os.environ.get("REQUESTED_SLOT", ""),
    os.environ.get("SCHEDULE_EVENT", ""),
)
with open(os.environ["GITHUB_ENV"], "a") as handle:
    handle.write("RUN_SLOT=" + slot + "\n")
print("Выпуск: " + slot + " UTC+3")


settings = Settings()
plan = WeeklyPlan.load(settings.path(str(settings.prompt_queue_file)))
try:
    plan.for_date(slot[:10], int(slot[11:]))
    active = True
except ValueError:
    active = False
    print("На этот слот нет задания. Ожидается начало плана или новый пакет промптов.")
with open(os.environ["GITHUB_ENV"], "a") as handle:
    handle.write("PLAN_ACTIVE=" + str(active).lower() + "\n")
