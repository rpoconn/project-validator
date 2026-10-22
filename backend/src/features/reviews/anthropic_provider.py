"""Reviews from Claude via the Anthropic Messages API."""

from typing import Final

from anthropic import AsyncAnthropic, transform_schema
from anthropic.types.beta import BetaMessage, BetaMessageParam, BetaOutputConfigParam

from src.features.projects.schemas import ProjectReview
from src.features.reviews.provider import (
    MAX_OUTPUT_TOKENS,
    MalformedReviewError,
    ReviewRefusedError,
    log_usage,
    validate_review_text,
)
from src.features.reviews.schemas import ReviewPrompt

EFFORT: Final = "medium"
# Policy declines are re-run server-side on Anthropic's recommended fallback model.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

OUTPUT_CONFIG: BetaOutputConfigParam = {
    "effort": EFFORT,
    "format": {"type": "json_schema", "schema": transform_schema(ProjectReview)},
}


def parse_message(response: BetaMessage) -> ProjectReview:
    request_id = response._request_id
    if response.stop_reason == "refusal":
        details = response.stop_details
        category = (details.category if details else None) or "unspecified"
        explanation = f": {details.explanation}" if details and details.explanation else ""
        raise ReviewRefusedError(
            f"Claude declined to review this project (category={category}){explanation}",
            request_id=request_id,
        )
    if response.stop_reason == "max_tokens":
        raise MalformedReviewError(
            "Review was cut off at the output token limit", request_id=request_id
        )
    text = "".join(block.text for block in response.content if block.type == "text")
    return validate_review_text(text, request_id=request_id)


class AnthropicReviewProvider:
    def __init__(self, client: AsyncAnthropic, model: str) -> None:
        self.client = client
        self.model = model

    async def generate(self, prompt: ReviewPrompt) -> ProjectReview:
        messages: list[BetaMessageParam] = [{"role": "user", "content": prompt.user_message}]
        response = await self.client.beta.messages.create(
            model=self.model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=prompt.system,
            messages=messages,
            output_config=OUTPUT_CONFIG,
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        review = parse_message(response)
        log_usage(
            response.model,
            response._request_id,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        return review
