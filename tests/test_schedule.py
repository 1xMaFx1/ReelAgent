from datetime import datetime, timezone

import pytest

from app.config import Settings
from app.core.schedule import publication_time


def test_eight_am_local_is_five_utc():
    now = datetime(2026, 9, 27, 2, 17, tzinfo=timezone.utc)
    target = publication_time("2026-09-27", Settings(_env_file=None), now)
    assert target.isoformat() == "2026-09-27T05:00:00+00:00"


def test_delayed_job_does_not_post_late_or_move_to_tomorrow():
    now = datetime(2026, 9, 27, 5, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="deadline missed"):
        publication_time("2026-09-27", Settings(_env_file=None), now)


def test_three_slots_and_delayed_schedule():
    from datetime import datetime

    from app.core.slots import ZONE, slot_for, target_time

    morning = datetime(2026, 9, 28, 7, 17, tzinfo=ZONE)
    assert slot_for(morning) == "2026-09-28-08"
    assert slot_for(morning.replace(hour=10)) == "2026-09-28-12"
    assert slot_for(morning.replace(hour=18)) == "2026-09-29-08"
    # A delayed morning cron must never consume the midday script.
    assert slot_for(morning.replace(hour=11), schedule="17 4 * * *") == "2026-09-28-08"
    assert target_time("2026-09-28-17").hour == 17
