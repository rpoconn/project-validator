"""Test doubles for the Anthropic client: canned messages, API errors and a scripted endpoint."""

import json
from typing import Any

import httpx2
import pytest
from anthropic import APIStatusError, AsyncAnthropic
from anthropic.types.beta import BetaMessage

VALID_REVIEW: dict[str, Any] = {
    "summary": "Robotics rollout across two sites. Budget is plausible but the pilot is tight.",
    "tags": ["automation", "logistics", "capex"],
    "risks": ["Pilot date leaves little time after vendor selection", "Vendor lock-in"],
}

_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


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


def api_error[E: APIStatusError](
    error_cls: type[E], status_code: int, message: str = "boom", request_id: str = "req_err"
) -> E:
    response = httpx2.Response(status_code, request=_REQUEST, headers={"request-id": request_id})
    return error_cls(message, response=response, body=None)


class ScriptedMessages:
    """Replaces `client.beta.messages.create`: returns or raises each scripted outcome in turn."""

    def __init__(self, *outcomes: BetaMessage | Exception) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> BetaMessage:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def scripted_client(
    monkeypatch: pytest.MonkeyPatch, *outcomes: BetaMessage | Exception
) -> tuple[AsyncAnthropic, ScriptedMessages]:
    client = AsyncAnthropic(api_key="sk-test", max_retries=0)
    script = ScriptedMessages(*outcomes)
    monkeypatch.setattr(client.beta.messages, "create", script.create)
    return client, script
