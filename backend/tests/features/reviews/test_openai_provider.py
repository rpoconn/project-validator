import json

import pytest
from openai.types.responses import Response

from src.features.projects.schemas import ProjectReview
from src.features.reviews.openai_provider import parse_response
from src.features.reviews.provider import MalformedReviewError, ReviewRefusedError
from src.features.reviews.schemas import ReviewPrompt
from src.features.reviews.service import is_retryable
from tests.features.reviews.fakes import VALID_REVIEW, make_response, scripted_openai

PROMPT = ReviewPrompt(system="system", user_message="user")


def test_parse_response_success() -> None:
    assert parse_response(make_response()) == ProjectReview.model_validate(VALID_REVIEW)


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (
            make_response(refusal="I can't help with that."),
            "The model declined to review this project: I can't help with that.",
        ),
        (
            make_response("", status="incomplete", incomplete_reason="content_filter"),
            "The model's content filter stopped this review",
        ),
    ],
)
def test_parse_response_refusal_is_not_retryable(response: Response, expected: str) -> None:
    with pytest.raises(ReviewRefusedError) as excinfo:
        parse_response(response)

    assert str(excinfo.value) == expected
    assert excinfo.value.request_id == "req_ok"
    assert not is_retryable(excinfo.value)


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (
            make_response(
                '{"summary": "cut', status="incomplete", incomplete_reason="max_output_tokens"
            ),
            "output token limit",
        ),
        (make_response("", status="incomplete"), r"incomplete \(reason=unspecified\)"),
        (
            make_response("", status="failed", error_message="server hiccup"),
            "failed: server hiccup",
        ),
        (make_response(""), "no review text"),
        (make_response("not json"), "did not match the expected format"),
        (
            make_response(json.dumps({**VALID_REVIEW, "tags": ["a", "A", "b"]})),
            "tags: Value error, tags must contain 3 distinct",
        ),
    ],
)
def test_parse_response_malformed_output_is_retryable(response: Response, expected: str) -> None:
    with pytest.raises(MalformedReviewError, match=expected) as excinfo:
        parse_response(response)

    assert excinfo.value.request_id == "req_ok"
    assert is_retryable(excinfo.value)


async def test_generate_sends_expected_request(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, script = scripted_openai(monkeypatch, make_response())

    review = await provider.generate(PROMPT)

    assert review.tags == VALID_REVIEW["tags"]
    [call] = script.calls
    assert call["model"] == "gpt-5.5"
    assert call["instructions"] == "system"
    assert call["input"] == "user"
    assert call["store"] is False
    response_format = call["text"]["format"]
    assert response_format["type"] == "json_schema"
    assert response_format["strict"] is True
    assert response_format["schema"]["additionalProperties"] is False
    assert set(response_format["schema"]["required"]) == {"summary", "tags", "risks"}
