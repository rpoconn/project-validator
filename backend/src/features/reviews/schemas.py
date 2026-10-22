from pydantic import BaseModel


class ReviewPrompt(BaseModel):
    """The rendered request for one review: a static system prompt plus the per-project message."""

    system: str
    user_message: str
