import json
from typing import Any

import pytest
from anthropic.types.beta import BetaMessage

from src.features.projects.schemas import ProjectReview
from src.features.reviews.anthropic_provider import FALLBACK_BETA, parse_message
from src.features.reviews.provider import MalformedReviewError, ReviewRefusedError
from src.features.reviews.schemas import ReviewPrompt
from src.features.reviews.service import is_retryable
from tests.features.reviews.fakes import VALID_REVIEW, make_message, scripted_anthropic

PROMPT = ReviewPrompt(system="system", user_message="user")


def test_parse_message_success() -> None:
    assert parse_message(make_message()) == ProjectReview.model_validate(VALID_REVIEW)


def test_parse_message_refusal_is_not_retryable() -> None:
    message = make_message(
        "",
        stop_reason="refusal",
        stop_details={"type": "refusal", "category": "cyber", "explanation": "Declined."},
        request_id="req_refused",
    )

    with pytest.raises(ReviewRefusedError) as excinfo:
        parse_message(message)

    assert str(excinfo.value) == (
        "Claude declined to review this project (category=cyber): Declined."
    )
    assert excinfo.value.request_id == "req_refused"
    assert not is_retryable(excinfo.value)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (make_message('{"summary": "cut', stop_reason="max_tokens"), "output token limit"),
        (make_message(""), "no review text"),
        (make_message("not json"), "did not match the expected format"),
        (
            make_message(json.dumps({**VALID_REVIEW, "tags": ["a", "A", "b"]})),
            "tags: Value error, tags must contain 3 distinct",
        ),
    ],
)
def test_parse_message_malformed_output_is_retryable(message: Any, expected: str) -> None:
    with pytest.raises(MalformedReviewError, match=expected) as excinfo:
        parse_message(message)

    assert excinfo.value.request_id == "req_ok"
    assert is_retryable(excinfo.value)


async def test_generate_sends_expected_request(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, script = scripted_anthropic(monkeypatch, make_message())

    review = await provider.generate(PROMPT)

    assert review.tags == VALID_REVIEW["tags"]
    [call] = script.calls
    assert call["model"] == "claude-sonnet-5-5"
    assert call["system"] == "system"
    assert call["messages"] == [{"role": "user", "content": "user"}]
    assert call["output_config"]["effort"] == "medium"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert set(call["output_config"]["format"]["schema"]["properties"]) == {
        "summary",
        "tags",
        "risks",
    }
    assert call["betas"] == [FALLBACK_BETA]
    assert call["fallbacks"] == "default"
    assert "thinking" not in call


# --- edge cases ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stop_details", "expected"),
    [
        (None, "Claude declined to review this project (category=unspecified)"),
        (
            {"type": "refusal", "category": "cyber", "explanation": None},
            "Claude declined to review this project (category=cyber)",
        ),
    ],
)
def test_parse_message_refusal_without_full_details(
    stop_details: dict[str, Any] | None, expected: str
) -> None:
    message = make_message("", stop_reason="refusal", stop_details=stop_details)

    with pytest.raises(ReviewRefusedError) as excinfo:
        parse_message(message)

    assert str(excinfo.value) == expected


def _message_with_content(content: list[dict[str, Any]]) -> BetaMessage:
    data: dict[str, Any] = make_message().model_dump()
    data["content"] = content
    message = BetaMessage.model_validate(data)
    message._request_id = "req_ok"
    return message


def test_parse_message_joins_text_blocks_and_skips_other_blocks() -> None:
    text = json.dumps(VALID_REVIEW)
    cut = len(text) // 2
    message = _message_with_content(
        [
            {"type": "text", "text": text[:cut]},
            {"type": "tool_use", "id": "toolu_1", "name": "noop", "input": {}},
            {"type": "text", "text": text[cut:]},
        ]
    )

    assert parse_message(message) == ProjectReview.model_validate(VALID_REVIEW)


async def test_generate_logs_usage(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    provider, _ = scripted_anthropic(monkeypatch, make_message(request_id="req_usage"))

    with caplog.at_level("INFO", logger="src.features.reviews.provider"):
        await provider.generate(PROMPT)

    assert "(request_id=req_usage, input_tokens=100, output_tokens=50)" in caplog.text
