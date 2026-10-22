"""Test doubles for the LLM SDKs: canned responses, API errors and scripted endpoints."""

import json
from typing import Any

import anthropic
import httpx2
import openai
import pytest
from anthropic.types.beta import BetaMessage
from openai.types.responses import Response

from src.features.reviews.anthropic_provider import AnthropicReviewProvider
from src.features.reviews.openai_provider import OpenAIReviewProvider

VALID_REVIEW: dict[str, Any] = {
    "summary": "Robotics rollout across two sites. Budget is plausible but the pilot is tight.",
    "tags": ["automation", "logistics", "capex"],
    "risks": ["Pilot date leaves little time after vendor selection", "Vendor lock-in"],
}

_REQUEST = httpx2.Request("POST", "https://api.example.test/v1/messages")


def make_message(
    text: str | None = None,
    *,
    stop_reason: str = "end_turn",
    stop_details: dict[str, Any] | None = None,
    request_id: str = "req_ok",
) -> BetaMessage:
    """A Claude response; by default its text is a valid review."""
    content = [{"type": "text", "text": json.dumps(VALID_REVIEW) if text is None else text}]
    message = BetaMessage.model_validate(
        {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-5-5",
            "content": content if text != "" else [],
            "stop_reason": stop_reason,
            "stop_details": stop_details,
            "stop_sequence": None,
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
    )
    message._request_id = request_id
    return message


def make_response(
    text: str | None = None,
    *,
    refusal: str | None = None,
    status: str = "completed",
    incomplete_reason: str | None = None,
    error_message: str | None = None,
    request_id: str = "req_ok",
) -> Response:
    """An OpenAI Responses API result; by default its text is a valid review."""
    content: list[dict[str, Any]] = []
    if refusal is not None:
        content.append({"type": "refusal", "refusal": refusal})
    elif text != "":
        output_text = json.dumps(VALID_REVIEW) if text is None else text
        content.append({"type": "output_text", "text": output_text, "annotations": []})
    response = Response.model_validate(
        {
            "id": "resp_test",
            "object": "response",
            "created_at": 0,
            "model": "gpt-5.5",
            "status": status,
            "output": [
                {
                    "type": "message",
                    "id": "msg_test",
                    "role": "assistant",
                    "status": "completed",
                    "content": content,
                }
            ],
            "incomplete_details": {"reason": incomplete_reason} if incomplete_reason else None,
            "error": {"code": "server_error", "message": error_message} if error_message else None,
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
                "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            },
        }
    )
    response._request_id = request_id
    return response


def api_error[E: anthropic.APIStatusError | openai.APIStatusError](
    error_cls: type[E], status_code: int, message: str = "boom", request_id: str = "req_err"
) -> E:
    """An SDK status error. Each SDK reads its request id from a different header, so set both."""
    response = httpx2.Response(
        status_code,
        request=_REQUEST,
        headers={"request-id": request_id, "x-request-id": request_id},
    )
    return error_cls(message, response=response, body=None)


class ScriptedEndpoint:
    """Replaces an SDK `create` method: returns or raises each scripted outcome in turn."""

    def __init__(self, *outcomes: object) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def scripted_anthropic(
    monkeypatch: pytest.MonkeyPatch, *outcomes: BetaMessage | Exception
) -> tuple[AnthropicReviewProvider, ScriptedEndpoint]:
    client = anthropic.AsyncAnthropic(api_key="sk-test", max_retries=0)
    script = ScriptedEndpoint(*outcomes)
    monkeypatch.setattr(client.beta.messages, "create", script.create)
    return AnthropicReviewProvider(client, "claude-sonnet-5-5"), script


def scripted_openai(
    monkeypatch: pytest.MonkeyPatch, *outcomes: Response | Exception
) -> tuple[OpenAIReviewProvider, ScriptedEndpoint]:
    client = openai.AsyncOpenAI(api_key="sk-test", max_retries=0)
    script = ScriptedEndpoint(*outcomes)
    monkeypatch.setattr(client.responses, "create", script.create)
    return OpenAIReviewProvider(client, "gpt-5.5"), script
