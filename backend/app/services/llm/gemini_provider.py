import json

from google import genai
from google.genai import types

from app.config import settings
from app.models import FailedPayment
from app.services.llm.base import (
    CLASSIFICATION_SCHEMA,
    SYSTEM_PROMPT,
    LLMClassification,
    build_user_content,
    validate_classification,
)


class GeminiProvider:
    name = "gemini"

    def __init__(self):
        self._client = genai.Client(api_key=settings.gemini_api_key)

    def classify_ambiguous(self, payment: FailedPayment) -> LLMClassification:
        response = self._client.models.generate_content(
            model=settings.gemini_model,
            contents=build_user_content(payment),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=CLASSIFICATION_SCHEMA,
            ),
        )

        raw = json.loads(response.text)
        return validate_classification(raw)
