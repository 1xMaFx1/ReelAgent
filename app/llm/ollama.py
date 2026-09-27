"""Open model running on the cloud runner, never on the user's Mac."""

import json
import logging

import httpx
from pydantic import ValidationError

from app.core.models import NarrationDraft, Scene, Script, Topic
from app.llm.gemini import GeminiProvider, T
from app.utils.text import parse_json


class OllamaProvider(GeminiProvider):
    async def generate_script(self, topic: Topic) -> Script:
        draft = await self.ask(
            "Напиши связный русский рассказ для короткого научного видео по предоставленному источнику. "
            f"Тема: {topic.topic}. hook: короткий вопрос из 3–6 слов. "
            "body: полноценный абзац из 70–80 слов, 5–7 предложений. Не сокращай его до нескольких фраз. "
            "Объясни только факты из источника простым и грамотным русским языком, без домыслов. "
            "ending: короткий вывод из 4–7 слов. visual_query: 2–3 английских слова об объекте съёмки. "
            "Не указывай технические поля сцен, не проси подписаться, не добавляй рекламу.",
            NarrationDraft,
        )
        words = draft.body.split()
        cuts = [round(len(words) * i / 4) for i in range(5)]
        script = Script(
            topic=topic.topic,
            hook=draft.hook,
            ending=draft.ending,
            scenes=[
                Scene(
                    id=i + 1,
                    narration=" ".join(words[cuts[i] : cuts[i + 1]]),
                    visual_query=draft.visual_query,
                    duration=8,
                )
                for i in range(4)
            ],
        )
        return await self.review_script(script)

    # Reuse the provider-independent prompts and public generation methods.
    async def ask(self, prompt: str, model: type[T]) -> T:
        self.settings.require_cloud()
        prompt += (
            "\nJSON schema (соблюдай все ограничения длины, числа сцен и полей): "
            + json.dumps(model.model_json_schema(), ensure_ascii=False)
        )
        instruction = prompt
        for attempt in range(3):
            try:
                response = await self.client.post(
                    "http://127.0.0.1:11434/api/generate",
                    timeout=900,
                    json={
                        "model": self.settings.ollama_model,
                        "system": self.context() + " Верни только JSON по заданной схеме.",
                        "prompt": instruction,
                        "format": model.model_json_schema(),
                        "stream": False,
                        "think": False,
                        "keep_alive": "30m",
                        "options": {"num_ctx": 8192, "num_predict": 2200, "temperature": 0.3},
                    },
                )
                response.raise_for_status()
                return parse_json(response.json()["response"], model)
            except (ValueError, KeyError) as error:
                details = (
                    json.dumps(error.errors(include_input=False, include_url=False), default=str)
                    if isinstance(error, ValidationError)
                    else type(error).__name__
                )
                instruction = prompt + " Исправь ошибки предыдущего ответа: " + details
                logging.getLogger(__name__).warning(
                    "Cloud model validation attempt %s/3: %s", attempt + 1, details
                )
            except httpx.HTTPError:
                if attempt == 2:
                    raise RuntimeError("Cloud model unavailable after 3 attempts") from None
        raise RuntimeError("Cloud model invalid JSON after 3 attempts")
