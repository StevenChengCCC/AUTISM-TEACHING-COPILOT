from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

from app.core.config import settings

logger = logging.getLogger(__name__)


class AIProvider(ABC):
    @abstractmethod
    def generate_lesson_text(self, prompt: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_image_prompt(
        self, concept: str, variation: str, style: str = "realistic teaching card"
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def extract_profile_from_text(self, text: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def evaluate_lesson(self, lesson_package: dict) -> dict:
        raise NotImplementedError


class MockProvider(AIProvider):
    def generate_lesson_text(self, prompt: str) -> str:
        return f"Mock teacher-facing text: {prompt[:160]}"

    def generate_image_prompt(
        self, concept: str, variation: str, style: str = "realistic teaching card"
    ) -> str:
        return (
            f"A clear {style} image of {concept}, variation: {variation}. "
            "single main subject, low-distraction background, printable learning card, no text, no watermark."
        )

    def extract_profile_from_text(self, text: str) -> dict:
        return {
            "mock": True,
            "source_preview": text[:160],
            "interests": [],
            "reinforcers": [],
        }

    def evaluate_lesson(self, lesson_package: dict) -> dict:
        return {
            "mock": True,
            "quality": "not_evaluated",
            "notes": ["Mock mode: no external AI call."],
        }


class OpenAIProvider(AIProvider):
    def __init__(self):
        from openai import OpenAI

        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is missing")
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL

    def _complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""

    def generate_lesson_text(self, prompt: str) -> str:
        return self._complete(
            "Polish autism special education teacher-facing lesson language.", prompt
        )

    def generate_image_prompt(
        self, concept: str, variation: str, style: str = "realistic teaching card"
    ) -> str:
        return self._complete(
            "Write concise image prompts for special education teaching cards.",
            f"{concept}; {variation}; {style}",
        )

    def extract_profile_from_text(self, text: str) -> dict:
        content = self._complete("Extract structured learner profile JSON only.", text)
        return json.loads(content or "{}")

    def evaluate_lesson(self, lesson_package: dict) -> dict:
        content = self._complete(
            "Evaluate lesson package JSON for autism intervention planning. Return JSON.",
            json.dumps(lesson_package),
        )
        return json.loads(content or "{}")


class AzureOpenAIProvider(OpenAIProvider):
    def __init__(self):
        from openai import AzureOpenAI

        if (
            not settings.AZURE_OPENAI_ENDPOINT
            or not settings.AZURE_OPENAI_API_KEY
            or not settings.AZURE_OPENAI_DEPLOYMENT
        ):
            raise RuntimeError("Azure OpenAI credentials are missing")
        self.client = AzureOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
        )
        self.model = settings.AZURE_OPENAI_DEPLOYMENT


def get_ai_provider() -> AIProvider:
    provider = settings.AI_PROVIDER.lower()
    try:
        if provider == "openai":
            return OpenAIProvider()
        if provider == "azure_openai":
            return AzureOpenAIProvider()
    except Exception as exc:
        logger.info("Falling back to MockProvider: %s", exc)
    return MockProvider()
