import asyncio
import logging
from typing import Any, Coroutine

import httpx
import typer
from pydantic import ValidationError

from app.config import Settings
from app.core.logger import setup_logging
from app.core.pipeline import Pipeline
from app.llm.gemini import GeminiProvider
from app.llm.ollama import OllamaProvider
from app.media.pexels import PexelsVideoProvider
from app.tts.edge_tts import EdgeTTSProvider

app = typer.Typer(
    help="ReelAgent: daily cloud-rendered Shorts/Reels",
    no_args_is_help=False,
    pretty_exceptions_enable=False,
)


def settings() -> Settings:
    try:
        value = Settings()
    except ValidationError as error:
        fields = ", ".join(".".join(map(str, e["loc"])) for e in error.errors())
        typer.echo("Invalid configuration fields: " + fields, err=True)
        raise typer.Exit(1) from None
    setup_logging(value)
    return value


def execute(coroutine: Coroutine[Any, Any, Any]) -> None:
    try:
        asyncio.run(coroutine)
    except Exception as error:
        logging.getLogger(__name__).error("%s: %s", type(error).__name__, error)
        raise typer.Exit(1) from None


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        run()


@app.command()
def generate() -> None:
    """Create MP4 + metadata in the cloud, never publish."""
    execute(Pipeline(settings()).run(publish=False))


@app.command()
def run() -> None:
    """Create one daily MP4; publish only when enabled and DRY_RUN=false."""
    execute(Pipeline(settings()).run(publish=True))


@app.command("test-llm")
def test_llm() -> None:
    """Test the selected model without rendering or publishing."""
    s = settings()

    async def check():
        async with httpx.AsyncClient(timeout=90) as client:
            provider = OllamaProvider if s.llm_provider == "ollama" else GeminiProvider
            topic = await provider(s, client).generate_topic([])
            typer.echo(topic.model_dump_json(indent=2))

    execute(check())


@app.command("test-pexels")
def test_pexels() -> None:
    """Test stock search without downloading or rendering."""
    s = settings()

    async def check():
        if not s.pexels_api_key.get_secret_value():
            raise ValueError("PEXELS_API_KEY is required")
        async with httpx.AsyncClient(timeout=30) as client:
            videos = await PexelsVideoProvider(s, client).search("space stars")
            typer.echo(f"Pexels: {len(videos)} results")

    execute(check())


@app.command("test-tts")
def test_tts() -> None:
    """Create a short speech sample via the remote TTS service."""
    s = settings()

    async def check():
        speech = await EdgeTTSProvider(s.tts_voice).synthesize(
            "Привет! Это проверка русской озвучки проекта ReelAgent.",
            s.path("data/tmp/tts-test.mp3"),
        )
        typer.echo(f"TTS: {speech.duration:.2f}s — {speech.path}")

    execute(check())


if __name__ == "__main__":
    app()
