import json
from typing import Any

import pytest

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
