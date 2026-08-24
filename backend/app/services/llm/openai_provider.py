import json

from openai import OpenAI

from app.config import settings
from app.models import FailedPayment
from app.services.llm.base import (
    CLASSIFICATION_SCHEMA,
    SYSTEM_PROMPT,
    LLMClassification,
    build_user_content,
    validate_classification,
)


class OpenAIProvider:
    name = "openai"

    def __init__(self):
        self._client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )

    def classify_ambiguous(self, payment: FailedPayment) -> LLMClassification:
        response = self._client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_content(payment)},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "classification",
                    "schema": CLASSIFICATION_SCHEMA,
                    "strict": True,
                },
            },
        )

        raw = json.loads(response.choices[0].message.content)
        return validate_classification(raw)

    def draft_text(self, system_prompt: str, user_content: str, max_tokens: int) -> str:
        response = self._client.chat.completions.create(
            model=settings.openai_model,
            max_completion_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        return response.choices[0].message.content or ""
