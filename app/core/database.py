import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.core.models import Status
from app.utils.text import normalize_topic


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY, day TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
            topic TEXT, title TEXT, script TEXT, status TEXT NOT NULL,
            video_path TEXT, youtube_video_id TEXT, instagram_media_id TEXT, error_message TEXT
        );
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY, topic TEXT NOT NULL, normalized TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        """)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def today(self, day: str) -> dict | None:
        row = self.connection.execute("SELECT * FROM videos WHERE day=?", (day,)).fetchone()
        return dict(row) if row else None

    def claim(self, day: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO videos(day,created_at,status) VALUES(?,?,?)",
                (day, now, Status.CREATED),
            )
        return self.today(day)["id"]

    def update(self, video_id: int, **values) -> None:
        allowed = {
            "topic",
            "title",
            "script",
            "status",
            "video_path",
            "youtube_video_id",
            "instagram_media_id",
            "error_message",
        }
        if not values.keys() <= allowed:
            raise ValueError("Invalid database columns")
        with self.connection:
            self.connection.execute(
                "UPDATE videos SET " + ",".join(f"{k}=?" for k in values) + " WHERE id=?",
                (*values.values(), video_id),
            )

    def recent_topics(self) -> list[str]:
        return [
            row[0]
            for row in self.connection.execute(
                "SELECT topic FROM topics ORDER BY id DESC LIMIT 100"
            )
        ]

    def add_topic(self, topic: str) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO topics(topic,normalized,created_at) VALUES(?,?,?)",
                (topic, normalize_topic(topic), datetime.now(timezone.utc).isoformat()),
            )
