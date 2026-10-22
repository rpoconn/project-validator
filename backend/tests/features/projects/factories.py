from typing import Any


def project_payload(**overrides: Any) -> dict[str, Any]:
    """A valid `ProjectCreate` JSON body; pass keyword overrides to vary individual fields."""
    payload: dict[str, Any] = {
        "title": "Warehouse automation",
        "description": "Roll out picking robots across two distribution centres.",
        "budget_min": 100_000,
        "budget_max": 250_000,
        "industry": "Logistics",
        "timeline": [
            {"goal": "Vendor selected", "due_at": "2027-01-15T00:00:00Z"},
            {"goal": "Pilot live", "due_at": "2027-06-01T12:00:00Z"},
        ],
    }
    payload.update(overrides)
    return payload
