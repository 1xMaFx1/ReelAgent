"""Open model running on the cloud runner, never on the user's Mac."""

import json
import logging

import httpx
from pydantic import ValidationError

from app.llm.gemini import GeminiProvider, T
from app.utils.text import parse_json


class OllamaProvider(GeminiProvider):
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
                        "options": {"num_ctx": 8192, "num_predict": 2200, "temperature": 0.6},
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
