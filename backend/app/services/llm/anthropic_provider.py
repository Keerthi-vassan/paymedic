from anthropic import Anthropic

from app.config import settings
from app.models import FailedPayment
from app.services.llm.base import (
    CLASSIFICATION_SCHEMA,
    SYSTEM_PROMPT,
    LLMClassification,
    build_user_content,
    validate_classification,
)

TOOL_NAME = "emit_classification"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self):
        self._client = Anthropic(api_key=settings.anthropic_api_key)

    def classify_ambiguous(self, payment: FailedPayment) -> LLMClassification:
        response = self._client.messages.create(
            model=settings.anthropic_model,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            tools=[
                {
                    "name": TOOL_NAME,
                    "description": "Emit the root-cause classification for this failed payment.",
                    "input_schema": CLASSIFICATION_SCHEMA,
                }
            ],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[{"role": "user", "content": build_user_content(payment)}],
        )

        tool_use = next(block for block in response.content if block.type == "tool_use")
        return validate_classification(tool_use.input)
