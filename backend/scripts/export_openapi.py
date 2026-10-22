"""Write the OpenAPI spec to a file so the frontend can generate types without a running server.

Usage: uv run python -m scripts.export_openapi [output_path]
"""

import json
import logging
import sys
from pathlib import Path

from src.main import create_app
from src.shared.config import REPO_ROOT

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = REPO_ROOT / "frontend" / "openapi.json"


def export_openapi(output: Path = DEFAULT_OUTPUT) -> Path:
    spec = create_app().openapi()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    logger.info("Wrote OpenAPI spec to %s", output)
    return output


if __name__ == "__main__":
    export_openapi(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT)
