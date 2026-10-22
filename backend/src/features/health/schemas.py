from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    anthropic_configured: bool
    # True when reviews come from the offline mock (`LLM_MOCK`), whatever the key says.
    llm_mock: bool
