import logging

from app.config import Settings
from app.core.logger import Redactor


def test_no_secret_or_url_in_logs():
    secret = "test-private-secret"
    record = logging.LogRecord(
        "test", logging.ERROR, "", 1, "Failed %s https://example.com/?token=other", (secret,), None
    )
    Redactor(Settings(_env_file=None, gemini_api_key=secret)).filter(record)
    assert secret not in record.getMessage()
    assert "other" not in record.getMessage()
