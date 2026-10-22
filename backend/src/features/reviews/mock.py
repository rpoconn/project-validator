"""Offline stand-in for the Anthropic Messages API, enabled with `LLM_MOCK=1`.

The mock is an HTTP transport under a real `AsyncAnthropic` client, so request building, response
parsing, SDK error classes, retry classification and error recording all run unchanged. It keeps
the e2e suite deterministic and free, and lets the app be demoed without an API key.

- Every review succeeds with a canned `ProjectReview` that names the project and says how many
  existing projects it was compared against.
- A project whose title contains `MOCK_FAIL_MARKER` fails its first review with a 401 (which is
  not retried), so the error panel and "Retry review" can be exercised. Later reviews of a project
  with the same title succeed.
"""

import asyncio
import re
from functools import lru_cache
from html import unescape

import httpx2
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from src.features.projects.schemas import ProjectReview

MOCK_FAIL_MARKER = "[mock-fail]"
MOCK_MODEL = "claude-mock"
# Long enough for the UI to show the pending state, short enough to keep e2e runs quick.
MOCK_LATENCY_SECONDS = 1.0

_PROJECT_TITLE = re.compile(r"<project_input>\s*<title>(.*?)</title>", re.DOTALL)
_EXISTING_COUNT = re.compile(r'<existing_projects count="(\d+)"')


class _MockMessageParam(BaseModel):
    role: str
    content: str


class _MockRequest(BaseModel):
    """The parts of a Messages API request body the mock reads."""

    messages: list[_MockMessageParam]


def canned_review(title: str, existing_count: int) -> ProjectReview:
    noun = "project" if existing_count == 1 else "projects"
    return ProjectReview(
        summary=(
            f"Mock review of “{title}”, generated offline because LLM_MOCK is enabled. "
            f"It was compared against {existing_count} existing {noun}."
        ),
        tags=["mock review", "offline", "deterministic"],
        risks=[
            f"Portfolio overlap was not assessed: {existing_count} existing {noun} were "
            "provided to this mock review.",
            "Budget and timeline were not assessed because the review is mocked.",
        ],
    )


class MockMessagesTransport(httpx2.AsyncBaseTransport):
    """Answers `POST /v1/messages` with a canned review or a scripted authentication error."""

    def __init__(self, *, latency_seconds: float = MOCK_LATENCY_SECONDS) -> None:
        self.latency_seconds = latency_seconds
        self.request_count = 0
        self._failed_titles: set[str] = set()

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(self.latency_seconds)
        self.request_count += 1
        request_id = f"req_mock_{self.request_count}"
        prompt = _MockRequest.model_validate_json(request.content).messages[-1].content

        title_match = _PROJECT_TITLE.search(prompt)
        title = unescape(title_match.group(1)) if title_match else "Untitled"
        if MOCK_FAIL_MARKER in title and title not in self._failed_titles:
            self._failed_titles.add(title)
            return httpx2.Response(
                401,
                headers={"request-id": request_id},
                json={
                    "type": "error",
                    "error": {
                        "type": "authentication_error",
                        "message": f"Mock failure for titles containing {MOCK_FAIL_MARKER}",
                    },
                    "request_id": request_id,
                },
            )

        count_match = _EXISTING_COUNT.search(prompt)
        review = canned_review(title, int(count_match.group(1)) if count_match else 0)
        return httpx2.Response(
            200,
            headers={"request-id": request_id},
            json={
                "id": f"msg_mock_{self.request_count}",
                "type": "message",
                "role": "assistant",
                "model": MOCK_MODEL,
                "content": [{"type": "text", "text": review.model_dump_json()}],
                "stop_reason": "end_turn",
                "stop_details": None,
                "stop_sequence": None,
                "usage": {"input_tokens": len(prompt) // 4, "output_tokens": 100},
            },
        )


def create_mock_client(*, latency_seconds: float = MOCK_LATENCY_SECONDS) -> AsyncAnthropic:
    transport = MockMessagesTransport(latency_seconds=latency_seconds)
    return AsyncAnthropic(
        api_key="mock", max_retries=0, http_client=httpx2.AsyncClient(transport=transport)
    )


@lru_cache
def get_mock_client() -> AsyncAnthropic:
    """Process-wide mock client, so "fail once" state lasts for the server's lifetime."""
    return create_mock_client()
