import json

from google import genai
from google.genai import types

from app.config import settings
from app.models import FailedPayment
from app.services.llm.base import (
    ROOT_CAUSES,
    SYSTEM_PROMPT,
    LLMClassification,
    build_user_content,
    validate_classification,
)

# Gemini's response_schema is a stricter OpenAPI subset, not full JSON Schema --
# it rejects fields like additionalProperties/maxLength that CLASSIFICATION_SCHEMA
# uses, so this adapter builds its own compatible version.
GEMINI_SCHEMA = {
    "type": "object",
    "properties": {
        "root_cause": {"type": "string", "enum": ROOT_CAUSES},
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"},
    },
    "required": ["root_cause", "confidence", "reasoning"],
}


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
                response_schema=GEMINI_SCHEMA,
            ),
        )

        raw = json.loads(response.text)
        return validate_classification(raw)
