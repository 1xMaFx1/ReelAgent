"""Explicit manual editorial replacement; previous cloud artifact remains available."""

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def main():
    day = datetime.now(ZoneInfo("Europe/Simferopol")).date().isoformat()
    output = Path("output") / day
    metadata = output / "metadata.json"
    if metadata.exists():
        meta = json.loads(metadata.read_text())
        if meta.get("youtube") or meta.get("instagram") or meta.get("publication_attempts"):
            raise RuntimeError("Cannot replace a draft with publication activity")
    if output.exists():
        backup = Path("data/tmp/replaced") / day
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(output), str(backup))
    with sqlite3.connect("data/reelagent.db") as database:
        database.execute("DELETE FROM videos WHERE day=?", (day,))
    print("Unpublished draft prepared for explicit editorial replacement")


if __name__ == "__main__":
    main()
