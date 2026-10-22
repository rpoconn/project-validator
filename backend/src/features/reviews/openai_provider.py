"""Reviews from OpenAI models via the Responses API."""

from typing import Any

from openai import AsyncOpenAI
from openai.types.responses import Response, ResponseTextConfigParam
from pydantic import BaseModel

from src.features.projects.schemas import ProjectReview
from src.features.reviews.provider import (
    MAX_OUTPUT_TOKENS,
    MalformedReviewError,
    ReviewRefusedError,
    log_usage,
    validate_review_text,
)
from src.features.reviews.schemas import ReviewPrompt


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """`model`'s JSON schema in the shape OpenAI's strict mode requires.

    Strict mode rejects open objects and optional properties, so every object (nested ones and
    `$defs` included) gets `additionalProperties: false` and lists all its properties as required.
    """
    schema = model.model_json_schema()
    _close_objects(schema)
    return schema


def _close_objects(node: Any) -> None:
    if isinstance(node, dict):
        properties = node.get("properties")
        if node.get("type") == "object" and isinstance(properties, dict):
            node["additionalProperties"] = False
            node["required"] = list(properties)
        for value in node.values():
            _close_objects(value)
    elif isinstance(node, list):
        for item in node:
            _close_objects(item)


TEXT_CONFIG: ResponseTextConfigParam = {
    "format": {
        "type": "json_schema",
        "name": "project_review",
        "strict": True,
        "schema": strict_json_schema(ProjectReview),
    }
}


def parse_response(response: Response) -> ProjectReview:
    request_id = response._request_id
    refusals = [
        part.refusal
        for item in response.output
        if item.type == "message"
        for part in item.content
        if part.type == "refusal"
    ]
    if refusals:
        raise ReviewRefusedError(
            f"The model declined to review this project: {' '.join(refusals)}",
            request_id=request_id,
        )
    if response.status == "incomplete":
        reason = response.incomplete_details.reason if response.incomplete_details else None
        if reason == "content_filter":
            raise ReviewRefusedError(
                "The model's content filter stopped this review", request_id=request_id
            )
        if reason == "max_output_tokens":
            raise MalformedReviewError(
                "Review was cut off at the output token limit", request_id=request_id
            )
        raise MalformedReviewError(
            f"Review was incomplete (reason={reason or 'unspecified'})", request_id=request_id
        )
    if response.status == "failed":
        message = response.error.message if response.error else "no details"
        raise MalformedReviewError(f"Response failed: {message}", request_id=request_id)
    return validate_review_text(response.output_text, request_id=request_id)


class OpenAIReviewProvider:
    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self.client = client
        self.model = model

    async def generate(self, prompt: ReviewPrompt) -> ProjectReview:
        response = await self.client.responses.create(
            model=self.model,
            instructions=prompt.system,
            input=prompt.user_message,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            text=TEXT_CONFIG,
            # Project data stays out of OpenAI's stored-response history.
            store=False,
        )
        review = parse_response(response)
        usage = response.usage
        log_usage(
            response.model,
            response._request_id,
            usage.input_tokens if usage else None,
            usage.output_tokens if usage else None,
        )
        return review
