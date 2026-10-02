import os
import time

from google import genai
from google.genai import errors, types

RETRYABLE_CODES = {404, 429, 500, 503}


class Gemini:
    def __init__(self, models: list[str]):
        self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self.models = models

    def _call(self, prompt: str, config: types.GenerateContentConfig, rounds: int = 3) -> types.GenerateContentResponse:
        last_error: Exception | None = None
        for attempt in range(rounds):
            for model in self.models:
                try:
                    response = self.client.models.generate_content(model=model, contents=prompt, config=config)
                    if response.text:
                        print(f"Gemini: {model}")
                        return response
                except errors.APIError as e:
                    if e.code not in RETRYABLE_CODES:
                        raise
                    print(f"{model} no disponible ({e.code}), probando otro")
                    last_error = e
            time.sleep(30 * (attempt + 1))
        raise RuntimeError("Ningún modelo de Gemini disponible") from last_error

    def json(self, prompt: str, temperature: float = 0.9) -> str:
        config = types.GenerateContentConfig(response_mime_type="application/json", temperature=temperature)
        return self._call(prompt, config).text

    def text(self, prompt: str, temperature: float = 0.3) -> str:
        return self._call(prompt, types.GenerateContentConfig(temperature=temperature)).text

    def grounded(self, prompt: str) -> tuple[str, list[dict]]:
        config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.3,
        )
        response = self._call(prompt, config, rounds=2)
        sources: list[dict] = []
        metadata = response.candidates[0].grounding_metadata if response.candidates else None
        for chunk in (metadata.grounding_chunks or []) if metadata else []:
            if chunk.web and chunk.web.uri and all(s["uri"] != chunk.web.uri for s in sources):
                sources.append({"title": chunk.web.title or chunk.web.uri, "uri": chunk.web.uri})
        return response.text, sources
