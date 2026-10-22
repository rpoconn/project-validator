import json
from pathlib import Path

from scripts.export_openapi import export_openapi


def test_export_openapi_writes_spec_and_creates_parent_dirs(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "deeper" / "openapi.json"

    result = export_openapi(output)

    assert result == output
    text = output.read_text(encoding="utf-8")
    assert text.endswith("}\n")
    spec = json.loads(text)
    assert spec["openapi"].startswith("3.")
    assert "/api/projects" in spec["paths"]
    assert "/api/health" in spec["paths"]


def test_export_openapi_overwrites_existing_file(tmp_path: Path) -> None:
    output = tmp_path / "openapi.json"
    output.write_text("stale", encoding="utf-8")

    export_openapi(output)

    assert json.loads(output.read_text(encoding="utf-8"))["info"]["title"] == "Project Tracker API"
