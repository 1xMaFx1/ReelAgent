import asyncio
import json
import logging
from typing import TypeVar
from urllib.parse import quote

import httpx
from pydantic import BaseModel

from app.config import Settings
from app.core.models import Metadata, SafetyReview, SceneQueries, Script, SocialCopy, Topic
from app.utils.retry import transient
from app.utils.text import parse_json

T = TypeVar("T", bound=BaseModel)
POLICY = (
    "Пиши по-русски. Только проверенные общеизвестные факты о науке, космосе, "
    "технологиях, природе или автомобилях. Никакой политики, медицинских советов, "
    "финансовых обещаний, опасных инструкций, ненависти и контента для взрослых. "
    "Не выдумывай факты, исследования и источники. Если сомневаешься, выбери другой факт. "
)


class GeminiProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings, self.client = settings, client

    def context(self) -> str:
        brief = getattr(self, "source_brief", "")
        if not brief and self.settings.content_brief_file:
            brief = self.settings.path(str(self.settings.content_brief_file)).read_text(
                encoding="utf-8"
            )
        if not brief:
            return POLICY
        return (
            POLICY + " Выбирай тему и пиши сценарий ТОЛЬКО по фактам ниже. "
            "Не добавляй числа, причинные объяснения или выводы, которых нет в источнике. "
            "Не повторяй одну мысль разными словами.\n" + brief + "\nЗАДАНИЕ:\n"
        )

    async def ask(self, prompt: str, model: type[T]) -> T:
        if not self.settings.gemini_api_key.get_secret_value():
            raise ValueError("GEMINI_API_KEY is required")
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            + quote(self.settings.gemini_model, safe="")
            + ":generateContent"
        )
        instruction = self.context() + prompt
        # One budget across transport retries and invalid JSON repairs.
        from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

        class InvalidOutput(Exception):
            pass

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, max=8),
                retry=retry_if_exception(lambda e: isinstance(e, InvalidOutput) or transient(e)),
                sleep=asyncio.sleep,
                reraise=True,
            ):
                with attempt:
                    try:
                        response = await self.client.post(
                            url,
                            headers={
                                "x-goog-api-key": self.settings.gemini_api_key.get_secret_value()
                            },
                            json={
                                "contents": [{"role": "user", "parts": [{"text": instruction}]}],
                                "generationConfig": {
                                    "responseMimeType": "application/json",
                                    "responseJsonSchema": model.model_json_schema(),
                                },
                            },
                        )
                        response.raise_for_status()
                        parts = response.json()["candidates"][0]["content"]["parts"]
                        return parse_json(
                            "".join(p.get("text", "") for p in parts if not p.get("thought")), model
                        )
                    except (ValueError, KeyError, IndexError) as error:
                        instruction = (
                            self.context()
                            + prompt
                            + (
                                " Предыдущий ответ не прошел проверку. Верни корректный JSON строго по схеме."
                            )
                        )
                        logging.getLogger(__name__).warning(
                            "Gemini JSON validation failed; retry budget: 3 total"
                        )
                        raise InvalidOutput() from error
        except httpx.HTTPError as error:
            if not transient(error):
                raise RuntimeError(
                    "Gemini rejected request: check API key, model, region and quota"
                ) from None
            raise RuntimeError("Gemini failed after 3 attempts (network)") from None
        except InvalidOutput:
            raise RuntimeError("Gemini failed after 3 attempts (invalid JSON)") from None
        raise RuntimeError("Gemini returned no result")

    async def generate_topic(self, recent: list[str]) -> Topic:
        return await self.ask(
            "Выбери одну короткую конкретную тему для Shorts. Не повторяй ни одну из "
            "последних тем, включая переформулировки: " + json.dumps(recent, ensure_ascii=False),
            Topic,
        )

    async def generate_script(self, topic: Topic) -> Script:
        script = await self.ask(
            f"Тема: {topic.topic}. Создай сценарий на 75–90 русских слов, примерно 36 секунд. "
            "Hook 3–6 слов (1–3 секунды), затем 4–7 коротких сцен BODY, затем короткий ending. "
            "Hook и ending НЕ повторять внутри сцен. ID сцен 1,2,... . duration — оценка секунд. "
            "visual_query — конкретный английский запрос для stock video, 2–4 слова. "
            + (
                "Призыв к действию разрешён."
                if self.settings.allow_cta
                else "Без просьб подписаться и поставить лайк."
            ),
            Script,
        )
        review = await self.ask(
            "Проверь сценарий: обычные научные факты, описание устройства техники и космоса "
            "разрешены. safe=true, если нет запрещённого содержания. safe=false только при "
            "наличии политики, медицинских советов, финансовых обещаний, инструкций "
            "причинения вреда, ненависти или контента для взрослых. В reason объясни решение. "
            "Сценарий: " + script.text,
            SafetyReview,
        )
        if not review.safe:
            logging.getLogger(__name__).warning("Script review rejected: %s", review.reason)
            raise ValueError("Script rejected by content review")
        return script

    async def generate_metadata(self, script: Script) -> Metadata:
        copy = await self.ask(
            "Создай короткое цепляющее название: 3–7 слов, максимум 55 символов. "
            "Используй любопытство, вопрос или конкретный факт из сценария, без обмана, "
            "ложных обещаний, крика заглавными буквами и просьб подписаться. "
            "keywords: 3–8 ключевых слов или коротких фраз, не предложения. "
            "hashtags: 3–6 релевантных хэштегов. Никакой рекламы. Сценарий: " + script.text,
            SocialCopy,
        )
        return Metadata(
            title=copy.title, description=", ".join(copy.keywords), hashtags=copy.hashtags
        )

    async def generate_scene_queries(self, script: Script) -> SceneQueries:
        result = await self.ask(
            "Верни ровно по одному английскому поисковому запросу из 2–4 слов "
            "на каждую сцену, в исходном порядке: " + script.model_dump_json(),
            SceneQueries,
        )
        if len(result.queries) != len(script.scenes):
            raise ValueError("Gemini returned wrong scene query count")
        return result
