from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import Settings


def publication_time(day: str, settings: Settings, now: datetime | None = None) -> datetime:
    target = (
        datetime.combine(date.fromisoformat(day), datetime.min.time())
        .replace(
            hour=settings.publication_hour,
            minute=settings.publication_minute,
            tzinfo=ZoneInfo(settings.publication_timezone),
        )
        .astimezone(timezone.utc)
    )
    current = now or datetime.now(timezone.utc)
    if target <= current + timedelta(minutes=5):
        raise ValueError("08:00 publication deadline missed; MP4 kept, no late post created")
    return target
