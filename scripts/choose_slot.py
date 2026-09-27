import os
from datetime import datetime, timezone

from app.core.slots import slot_for

slot = slot_for(
    datetime.now(timezone.utc),
    os.environ.get("REQUESTED_SLOT", ""),
    os.environ.get("SCHEDULE_EVENT", ""),
)
with open(os.environ["GITHUB_ENV"], "a") as handle:
    handle.write("RUN_SLOT=" + slot + "\n")
print("Выпуск: " + slot + " UTC+3")
