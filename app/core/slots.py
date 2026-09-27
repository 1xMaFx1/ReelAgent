"""Three named publication slots, always interpreted in the owner's timezone."""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Europe/Simferopol")
HOURS = (8, 12, 17)


def slot_for(now: datetime, requested: str = "", schedule: str = "") -> str:
    local = now.astimezone(ZONE)
    if requested:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-(08|12|17)", requested):
            raise ValueError("Expected publication slot YYYY-MM-DD-08/12/17")
        datetime.strptime(requested, "%Y-%m-%d-%H")
        return requested
    scheduled = {
        "17 4 * * *": 8,
        "17 8 * * *": 12,
        "17 13 * * *": 17,
        "7 5 * * *": 8,
        "7 9 * * *": 12,
        "7 14 * * *": 17,
    }
    if schedule:
        if schedule not in scheduled:
            raise ValueError("Unknown schedule trigger")
        return f"{local.date().isoformat()}-{scheduled[schedule]:02}"
    for hour in HOURS:
        if local.hour < hour:
            return f"{local.date().isoformat()}-{hour:02}"
    return f"{(local.date() + timedelta(days=1)).isoformat()}-08"


def target_time(slot: str) -> datetime:
    return datetime.strptime(slot, "%Y-%m-%d-%H").replace(tzinfo=ZONE)
