"""Cloud rendering only. Social publishing is intentionally absent."""

import httpx

from app.core.database import Database
from app.core.weekly_pipeline import run_weekly
from app.utils.files import pipeline_lock


class Pipeline:
    def __init__(self, settings):
        self.settings = settings

    async def run(self):
        s = self.settings
        with pipeline_lock(s.path("data/pipeline.lock")):
            db = Database(s.path("data/reelagent.db"))
            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    return await run_weekly(s, db, client)
            finally:
                db.close()
