import logging
import re
from logging.handlers import RotatingFileHandler

from pydantic import SecretStr

from app.config import Settings


class Redactor(logging.Filter):
    def __init__(self, settings: Settings):
        super().__init__()
        self.secrets = [
            v.get_secret_value()
            for v in settings.__dict__.values()
            if isinstance(v, SecretStr) and v.get_secret_value()
        ]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self.secrets:
            message = message.replace(secret, "[REDACTED]")
        record.msg = re.sub(r"https?://[^\s]+", "[URL]", message)
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        return True


def setup_logging(settings: Settings) -> None:
    settings.path("logs").mkdir(parents=True, exist_ok=True)
    handlers = [
        logging.StreamHandler(),
        RotatingFileHandler(
            settings.path("logs/reelagent.log"), maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        ),
    ]
    for handler in handlers:
        handler.addFilter(Redactor(settings))
    logging.basicConfig(
        level=settings.log_level,
        handlers=handlers,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    for name in ("httpx", "httpcore", "aiohttp"):
        logging.getLogger(name).setLevel(logging.WARNING)
