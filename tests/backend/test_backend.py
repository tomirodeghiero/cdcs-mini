from __future__ import annotations

import io
from collections.abc import Callable

from fastapi.testclient import TestClient
from web.backend.app.main import app

client = TestClient(app)


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_report_from_source_matches_cli_output(read_fixture: Callable[[str], str]) -> None:
    source = read_fixture("valid_input.py")
    response = client.post(
        "/reports/from-source",
        json={"filename": "valid_input.py", "source": source},
    )
    assert response.status_code == 200
    report = response.json()["report"]
    assert report["functions"][0]["name"] == "parse_port"
    assert report["functions"][0]["status"] == "ok"
    assert report["errors"] == []


def test_report_from_file_accepts_uploads(read_fixture: Callable[[str], str]) -> None:
    source = read_fixture("valid_input.py").encode("utf-8")
    response = client.post(
        "/reports/from-file",
        files={"file": ("valid_input.py", io.BytesIO(source), "text/x-python")},
    )
    assert response.status_code == 200
    report = response.json()["report"]
    assert report["functions"][0]["name"] == "parse_port"


def test_report_from_file_rejects_non_python_files() -> None:
    response = client.post(
        "/reports/from-file",
        files={"file": ("foo.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert response.status_code == 400
