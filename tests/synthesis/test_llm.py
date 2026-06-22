from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import patch

import pytest

from cdcs_mini.synthesis.llm import (
    LLMError,
    PollinationsClient,
    RecordedLLMClient,
    prompt_fingerprint,
    strip_code_fences,
)
from cdcs_mini.synthesis.prompt import Prompt


def _prompt(system: str = "sys", user: str = "user", kind: str = "implementation") -> Prompt:
    # kind is constrained by Literal at type-check time; cast at the boundary
    return Prompt(system=system, user=user, kind=kind)  # type: ignore[arg-type]


def test_fingerprint_changes_with_any_field() -> None:
    base = _prompt()
    assert prompt_fingerprint(base) != prompt_fingerprint(_prompt(system="other"))
    assert prompt_fingerprint(base) != prompt_fingerprint(_prompt(user="other"))
    assert prompt_fingerprint(base) != prompt_fingerprint(_prompt(kind="test"))


def test_recorded_client_returns_registered_response_by_fingerprint() -> None:
    client = RecordedLLMClient()
    prompt = _prompt()
    client.register(prompt, "def x(): pass\n")
    assert client.complete(prompt) == "def x(): pass\n"
    assert client.calls == [prompt]


def test_recorded_client_falls_back_to_kind() -> None:
    client = RecordedLLMClient()
    client.register_kind("implementation", "def x(): pass")
    assert client.complete(_prompt()).strip() == "def x(): pass"


def test_recorded_client_raises_when_no_recording_matches() -> None:
    client = RecordedLLMClient()
    with pytest.raises(LLMError):
        client.complete(_prompt())


def test_strip_code_fences_removes_python_fence() -> None:
    text = "```python\ndef x():\n    pass\n```"
    assert strip_code_fences(text) == "def x():\n    pass\n"


def test_strip_code_fences_removes_bare_fence() -> None:
    text = "```\ndef x():\n    pass\n```"
    assert strip_code_fences(text) == "def x():\n    pass\n"


def test_strip_code_fences_passthrough_when_no_fence() -> None:
    assert strip_code_fences("def x(): pass") == "def x(): pass\n"


# --- PollinationsClient ---------------------------------------------


class _FakeResponse:
    """Mimics the context-manager shape returned by urlopen."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._buf = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._buf.read()


def test_pollinations_client_posts_chat_payload_and_returns_text() -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> _FakeResponse:
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({"choices": [{"message": {"content": "def x(): pass\n"}}]})

    client = PollinationsClient()
    prompt = Prompt(system="sys", user="hi", kind="implementation")
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = client.complete(prompt)

    assert result == "def x(): pass\n"
    assert captured["url"] == "https://text.pollinations.ai/openai"
    assert captured["body"]["model"] == "openai"
    assert captured["body"]["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]


def test_pollinations_client_strips_markdown_fence() -> None:
    def fake_urlopen(*_: Any, **__: Any) -> _FakeResponse:
        return _FakeResponse(
            {"choices": [{"message": {"content": "```python\ndef x(): pass\n```"}}]}
        )

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = PollinationsClient().complete(Prompt(system="s", user="u", kind="implementation"))
    assert result == "def x(): pass\n"


def test_pollinations_client_raises_on_empty_choice() -> None:
    def fake_urlopen(*_: Any, **__: Any) -> _FakeResponse:
        return _FakeResponse({"choices": []})

    with (
        patch("urllib.request.urlopen", side_effect=fake_urlopen),
        pytest.raises(LLMError, match="empty completion"),
    ):
        PollinationsClient().complete(Prompt(system="s", user="u", kind="implementation"))


def test_pollinations_client_retries_on_429_then_succeeds() -> None:
    import urllib.error

    calls = {"count": 0}

    def fake_urlopen(*_: Any, **__: Any) -> _FakeResponse:
        calls["count"] += 1
        if calls["count"] == 1:
            # Simulate the "queue full" 429 on the first attempt
            raise urllib.error.HTTPError(
                "https://text.pollinations.ai/openai",
                429,
                "Too Many Requests",
                {},  # type: ignore[arg-type]
                io.BytesIO(b'{"error":"queue full"}'),
            )
        return _FakeResponse({"choices": [{"message": {"content": "def ok(): pass"}}]})

    # ``retry_backoff_seconds=0`` keeps the test fast; the loop logic is
    # what we care about, not real-world wall time.
    client = PollinationsClient(max_retries=2, retry_backoff_seconds=0.0)
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = client.complete(Prompt(system="s", user="u", kind="implementation"))
    assert result.startswith("def ok")
    assert calls["count"] == 2
