from typing import Literal

from pydantic import BaseModel

from src.shared.config import LLMProvider


class HealthResponse(BaseModel):
    status: Literal["ok"]
    # The provider reviews are sent to, and whether it has an API key.
    llm_provider: LLMProvider
    llm_configured: bool
    # True when reviews come from the offline mock (`LLM_MOCK`), whatever the key says.
    llm_mock: bool
