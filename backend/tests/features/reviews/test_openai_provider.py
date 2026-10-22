import json
from typing import Any, cast

import pytest
from openai.types.responses import Response, ResponseOutputRefusal
from pydantic import BaseModel

from src.features.projects.schemas import ProjectReview
from src.features.reviews.openai_provider import (
    TEXT_CONFIG,
    _close_objects,
    parse_response,
    strict_json_schema,
)
from src.features.reviews.provider import MalformedReviewError, ReviewRefusedError
from src.features.reviews.schemas import ReviewPrompt
from src.features.reviews.service import is_retryable
from tests.features.reviews.fakes import VALID_REVIEW, make_response, scripted_openai

PROMPT = ReviewPrompt(system="system", user_message="user")


class _Owner(BaseModel):
    name: str
    email: str | None = None


class _Team(BaseModel):
    lead: _Owner
    members: list[_Owner] = []


def test_strict_json_schema_closes_review_object() -> None:
    schema = strict_json_schema(ProjectReview)

    assert schema["additionalProperties"] is False
    assert schema["required"] == ["summary", "tags", "risks"]
    assert schema["properties"]["tags"]["minItems"] == 3
    assert schema["properties"]["tags"]["maxItems"] == 3


def test_strict_json_schema_closes_nested_objects_and_requires_optional_fields() -> None:
    schema = strict_json_schema(_Team)

    assert schema["additionalProperties"] is False
    assert schema["required"] == ["lead", "members"]
    owner = schema["$defs"]["_Owner"]
    assert owner["additionalProperties"] is False
    assert owner["required"] == ["name", "email"]


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


# --- edge cases ---------------------------------------------------------------------------------


def _with_reasoning_item(response: Response) -> Response:
    """The same response, preceded by a non-message output item the parser must skip."""
    data: dict[str, Any] = response.model_dump()
    data["output"].insert(0, {"type": "reasoning", "id": "rs_1", "summary": []})
    rebuilt = Response.model_validate(data)
    rebuilt._request_id = response._request_id
    return rebuilt


def test_parse_response_skips_non_message_items() -> None:
    review = parse_response(_with_reasoning_item(make_response()))

    assert review == ProjectReview.model_validate(VALID_REVIEW)


def test_parse_response_joins_several_refusals() -> None:
    response = make_response(refusal="One.")
    message = cast(Any, response.output[0])
    message.content.append(ResponseOutputRefusal(type="refusal", refusal="Two."))

    with pytest.raises(ReviewRefusedError, match=r"declined to review this project: One\. Two\."):
        parse_response(response)


def test_parse_response_refusal_wins_over_incomplete_status() -> None:
    response = make_response(
        refusal="No.", status="incomplete", incomplete_reason="max_output_tokens"
    )

    with pytest.raises(ReviewRefusedError):
        parse_response(response)


def test_parse_response_failed_without_error_details() -> None:
    with pytest.raises(MalformedReviewError, match="Response failed: no details"):
        parse_response(make_response("", status="failed"))


async def test_generate_tolerates_missing_usage(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    response = make_response()
    response.usage = None
    provider, _ = scripted_openai(monkeypatch, response)

    with caplog.at_level("INFO", logger="src.features.reviews.provider"):
        review = await provider.generate(PROMPT)

    assert review.tags == VALID_REVIEW["tags"]
    assert "input_tokens=None, output_tokens=None" in caplog.text


def test_close_objects_recurses_through_items_and_any_of() -> None:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "members": {"type": "array", "items": {"type": "object", "properties": {"b": {}}}},
            "lead": {"anyOf": [{"type": "object", "properties": {"d": {}}}, {"type": "null"}]},
            "open": {"type": "object"},
        },
    }

    _close_objects(schema)

    assert schema["required"] == ["members", "lead", "open"]
    member = schema["properties"]["members"]["items"]
    assert member["additionalProperties"] is False and member["required"] == ["b"]
    lead = schema["properties"]["lead"]["anyOf"][0]
    assert lead["additionalProperties"] is False and lead["required"] == ["d"]
    assert schema["properties"]["open"] == {"type": "object"}


def test_text_config_names_the_schema() -> None:
    assert TEXT_CONFIG["format"]["name"] == "project_review"  # type: ignore[typeddict-item]
