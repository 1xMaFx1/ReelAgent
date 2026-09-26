import sqlite3

import pytest

from app.core.database import Database
from app.core.models import Status


def test_daily_uniqueness_and_persistence(tmp_path):
    path = tmp_path / "test.db"
    db = Database(path)
    first = db.claim("2026-09-26")
    assert db.claim("2026-09-26") == first
    db.update(first, status=Status.READY)
    db.add_topic("Почему звёзды мерцают?")
    with pytest.raises(sqlite3.IntegrityError):
        db.add_topic("почему звёзды мерцают")
    db.close()
    db = Database(path)
    assert db.today("2026-09-26")["status"] == Status.READY
    assert len(db.recent_topics()) == 1
    db.close()
