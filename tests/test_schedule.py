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
