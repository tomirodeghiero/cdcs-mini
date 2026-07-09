from __future__ import annotations

import io
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from web.backend.app.dependencies import get_llm_client
from web.backend.app.main import app

from cdcs.synthesis.llm import RecordedLLMClient

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


# --- synthesis endpoint -------------------------------------------


_GOOD_IMPL = """\
def parse_port(value: str) -> int:
    stripped = value.strip()
    if not stripped.isdigit():
        raise ValueError("port must be base-10 digits")
    port = int(stripped)
    if not 1 <= port <= 65535:
        raise ValueError("port out of range")
    return port
"""

_GOOD_TESTS = """\
import pytest
from input_generated import parse_port

def test_valid() -> None:
    assert parse_port("80") == 80

def test_invalid() -> None:
    with pytest.raises(ValueError):
        parse_port("0")
"""


def _recorded_llm() -> RecordedLLMClient:
    llm = RecordedLLMClient()
    llm.register_kind("implementation", _GOOD_IMPL)
    llm.register_kind("test", _GOOD_TESTS)
    return llm


def test_synthesize_from_source_returns_impl_and_tests(
    read_fixture: Callable[[str], str],
) -> None:
    app.dependency_overrides[get_llm_client] = _recorded_llm
    try:
        source = read_fixture("valid_input.py")
        response = client.post(
            "/synthesize/from-source",
            json={"filename": "input.py", "source": source},
        )
    finally:
        app.dependency_overrides.pop(get_llm_client, None)

    assert response.status_code == 200
    body = response.json()
    assert body["errors"] == []
    assert body["language"] == "python"
    assert body["impl_filename"] == "input_generated.py"
    assert body["test_filename"] == "test_input_generated.py"
    assert len(body["functions"]) == 1
    fn = body["functions"][0]
    assert fn["status"] == "ok"
    assert fn["name"] == "parse_port"
    assert fn["implementation"].startswith("def parse_port")
    assert "import pytest" in fn["test"]
    assert fn["model"] == "recorded"
    assert fn["llm_calls"] == 2
    assert fn["repair_attempts"] == 0
    assert len(fn["contract_hash"]) == 64


def test_synthesize_autodetects_typescript_from_filename_extension() -> None:
    """``.ts`` upload → response carries ``language='typescript'`` and the
    TypeScript artifact filenames. Doesn't actually invoke the LLM on
    real TS contracts (that would require ts-runtime); just confirms the
    adapter selection landed in the response."""
    ts_llm = RecordedLLMClient()
    ts_llm.register_kind(
        "implementation",
        "export function parsePort(value: string): number { return Number(value); }\n",
    )
    ts_llm.register_kind(
        "test",
        'import { test, expect } from "vitest";\n'
        'import { parsePort } from "./input_generated.js";\n'
        'test("ok", () => { expect(parsePort("80")).toBe(80); });\n',
    )
    app.dependency_overrides[get_llm_client] = lambda: ts_llm
    try:
        # Source with no @generate contract → no LLM calls, but the
        # response still tells us which adapter the backend picked.
        response = client.post(
            "/synthesize/from-source",
            json={
                "filename": "ports.ts",
                "source": "export function parsePort(value: string): number { return 0; }\n",
            },
        )
    finally:
        app.dependency_overrides.pop(get_llm_client, None)

    assert response.status_code == 200
    body = response.json()
    assert body["language"] == "typescript"
    assert body["impl_filename"] == "ports_generated.ts"
    assert body["test_filename"] == "ports_generated.test.ts"


def test_synthesize_uses_pollinations_by_default_when_no_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Default factory must pick the keyless Pollinations backend when no
    # explicit provider, no API keys of any kind, and no local Ollama.
    from cdcs.synthesis import llm as llm_module
    from cdcs.synthesis.llm import PollinationsClient, default_llm_client

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    monkeypatch.delenv("CDCS_LLM_PROVIDER", raising=False)
    # Pretend Ollama isn't running — otherwise the factory prefers it.
    monkeypatch.setattr(llm_module, "_ollama_is_reachable", lambda: False)
    assert isinstance(default_llm_client(), PollinationsClient)


def test_synthesize_uses_anthropic_when_provider_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cdcs.synthesis.llm import AnthropicClient, default_llm_client

    monkeypatch.setenv("CDCS_LLM_PROVIDER", "anthropic")
    assert isinstance(default_llm_client(), AnthropicClient)


def test_synthesize_uses_cerebras_when_provider_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cdcs.synthesis.llm import CerebrasClient, default_llm_client

    monkeypatch.setenv("CDCS_LLM_PROVIDER", "cerebras")
    client = default_llm_client()
    assert isinstance(client, CerebrasClient)
    assert client.model == "qwen-3-coder-480b"


def test_synthesize_uses_cerebras_when_api_key_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # With CEREBRAS_API_KEY set and no Anthropic key, factory should pick
    # Cerebras before falling through to Ollama / Pollinations.
    from cdcs.synthesis import llm as llm_module
    from cdcs.synthesis.llm import CerebrasClient, default_llm_client

    monkeypatch.delenv("CDCS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CEREBRAS_API_KEY", "sk-fake")
    monkeypatch.setattr(llm_module, "_ollama_is_reachable", lambda: False)
    assert isinstance(default_llm_client(), CerebrasClient)


def test_synthesize_returns_upstream_diagnostics_when_contract_invalid() -> None:
    app.dependency_overrides[get_llm_client] = _recorded_llm
    try:
        # Missing examples section → MissingSamplesError flagged upstream,
        # the LLM is never called for this function.
        source = (
            "def total(values: list[int]) -> int:\n"
            '    """@generate\n'
            "    behavior:\n"
            "      return sum(values)\n"
            '    """\n'
            "    ...\n"
        )
        response = client.post(
            "/synthesize/from-source",
            json={"filename": "input.py", "source": source},
        )
    finally:
        app.dependency_overrides.pop(get_llm_client, None)

    assert response.status_code == 200
    body = response.json()
    fn = body["functions"][0]
    assert fn["status"] == "error"
    assert fn["implementation"] is None
    assert any(d["code"] == "MissingSamplesError" for d in fn["upstream_diagnostics"])
