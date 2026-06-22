"""LLM client abstraction.

The synthesizer is agnostic to **how** generation happens. Everything
flows through the ``LLMClient`` Protocol so we can:

  * default to the public, keyless **Pollinations.ai** endpoint
    (``PollinationsClient``) — best for thesis demos and CI;
  * plug in the real Anthropic SDK for production-grade runs;
  * replay canned responses in tests (``RecordedLLMClient``) — no
    network, deterministic byte-for-byte;
  * stub completely for unit tests of individual gates.

Both network-backed clients are import-only-when-used: the package keeps
working for analysis-only flows without external HTTP or SDK installs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Final, Literal, Protocol

from cdcs_mini.synthesis.prompt import Prompt

DEFAULT_MODEL: Final[str] = "claude-opus-4-7"
DEFAULT_POLLINATIONS_MODEL: Final[str] = "openai"  # = GPT-4o on Pollinations
POLLINATIONS_ENDPOINT: Final[str] = "https://text.pollinations.ai/openai"
DEFAULT_OLLAMA_MODEL: Final[str] = "qwen2.5-coder:7b"
OLLAMA_ENDPOINT: Final[str] = "http://localhost:11434/api/chat"

ProviderName = Literal["pollinations", "anthropic", "ollama"]


class LLMError(Exception):
    """Raised when the LLM backend itself fails (network, auth, parsing)."""


class LLMClient(Protocol):
    """Tiny synchronous interface — one prompt in, one string out.

    The orchestrator handles retries and repair; ``complete`` does the
    raw call once. Implementations are responsible for stripping any
    markdown fences before returning, so callers always get importable
    Python source.
    """

    @property
    def model(self) -> str: ...

    def complete(self, prompt: Prompt) -> str: ...


# --- AnthropicClient (real backend) ---------------------------------


@dataclass(frozen=True, slots=True)
class AnthropicClient:
    """Wraps ``anthropic.Anthropic.messages.create``.

    Lazy-imports ``anthropic`` so the package keeps working without the
    SDK when only the analyzer/reporter is used. Reads the API key from
    ``ANTHROPIC_API_KEY`` (handled by the SDK itself).
    """

    model: str = DEFAULT_MODEL
    max_tokens: int = 4096
    temperature: float = 0.0  # deterministic-ish; we want reproducibility

    def complete(self, prompt: Prompt) -> str:
        try:
            from anthropic import Anthropic  # type: ignore[import-not-found,unused-ignore]
        except ImportError as exc:
            raise LLMError(
                "anthropic SDK not installed. Install with: pip install anthropic"
            ) from exc
        client = Anthropic()
        # Prompt caching on the system message: same shape across impl/test/repair
        # so the prefix is reused across the three calls of one synthesis.
        message = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=[
                {
                    "type": "text",
                    "text": prompt.system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": prompt.user}],
        )
        text_parts: list[str] = []
        for block in message.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(getattr(block, "text", ""))
        if not text_parts:
            raise LLMError("LLM returned no text content")
        return strip_code_fences("\n".join(text_parts))


# --- PollinationsClient (keyless public default) --------------------


@dataclass(frozen=True, slots=True)
class PollinationsClient:
    """OpenAI-compatible client against ``text.pollinations.ai``.

    Public service with no API key required (anonymous rate limit:
    roughly 1 request every 15 seconds). Each synthesis run does two
    calls (impl + tests), so a single function takes ~30 seconds end-to-
    end on the free tier — fine for thesis demos, slow for batch.

    Uses ``urllib.request`` from the stdlib so the cdcs_mini package
    doesn't grow a runtime dependency on ``httpx``/``requests``.
    """

    model: str = DEFAULT_POLLINATIONS_MODEL
    endpoint: str = POLLINATIONS_ENDPOINT
    timeout_seconds: float = 90.0
    temperature: float = 0.2
    # Anonymous tier has a per-IP "1 request queued" cap; bursts hit 429 even
    # when the previous request is just finishing. Retry with backoff so the
    # orchestrator's two-call flow (impl + tests) survives the cap.
    max_retries: int = 4
    retry_backoff_seconds: float = 6.0

    def complete(self, prompt: Prompt) -> str:
        body = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
        }
        payload = json.dumps(body).encode("utf-8")
        # Cloudflare in front of Pollinations rejects the stdlib default UA
        # ("Python-urllib/...") with HTTP 403 / error 1010. Identifying as a
        # named client gets through the bot filter.
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "cdcs-mini/0.1.0 (+https://github.com/tomirodeghiero/cdcs-mini)",
            },
            method="POST",
        )
        raw = self._post_with_retry(request)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Pollinations response was not JSON: {raw[:200]!r}") from exc
        text = _extract_openai_text(parsed)
        if not text:
            raise LLMError("Pollinations returned an empty completion")
        return strip_code_fences(text)

    def _post_with_retry(self, request: urllib.request.Request) -> str:
        last_error: LLMError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    body: bytes = response.read()
                    return body.decode("utf-8")
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                if exc.code in {429, 502, 503, 504} and attempt < self.max_retries:
                    wait = self.retry_backoff_seconds * (2**attempt)
                    time.sleep(wait)
                    last_error = LLMError(
                        f"Pollinations HTTP {exc.code} (retrying): "
                        f"{detail.strip()[:120] or exc.reason}"
                    )
                    continue
                raise LLMError(
                    f"Pollinations returned HTTP {exc.code}: {detail.strip() or exc.reason}"
                ) from exc
            except urllib.error.URLError as exc:
                if attempt < self.max_retries:
                    time.sleep(self.retry_backoff_seconds * (2**attempt))
                    last_error = LLMError(f"Pollinations URL error: {exc.reason}")
                    continue
                raise LLMError(f"Pollinations request failed: {exc.reason}") from exc
        # Should be unreachable because the final attempt either returns or raises
        raise last_error or LLMError("Pollinations: retry budget exhausted")


# --- OllamaClient (local, reliable, keyless) ------------------------


@dataclass(frozen=True, slots=True)
class OllamaClient:
    """Calls a local ``ollama serve`` instance at ``localhost:11434``.

    Truly offline, no rate limits, no signup. Requires:

      1. Ollama installed (``brew install ollama`` on macOS).
      2. The model pulled once: ``ollama pull qwen2.5-coder:7b``.
      3. ``ollama serve`` running (it auto-starts on first ``ollama run``).

    Preferred backend for thesis defenses where reliability matters more
    than zero setup.
    """

    model: str = DEFAULT_OLLAMA_MODEL
    endpoint: str = OLLAMA_ENDPOINT
    timeout_seconds: float = 180.0
    # 0.0 mirrors AnthropicClient — we want reproducible synth, not creative.
    temperature: float = 0.0
    seed: int = 0

    def complete(self, prompt: Prompt) -> str:
        body = {
            "model": self.model,
            "stream": False,
            "options": {"temperature": self.temperature, "seed": self.seed},
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
        }
        payload = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise LLMError(f"Ollama returned HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(
                f"Ollama unreachable at {self.endpoint}: {exc.reason}. "
                "Start it with `ollama serve` and pull the model: "
                f"`ollama pull {self.model}`."
            ) from exc
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Ollama response was not JSON: {raw[:200]!r}") from exc
        if isinstance(parsed, dict):
            message = parsed.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content:
                    return strip_code_fences(content)
        raise LLMError("Ollama returned an empty completion")


def _ollama_is_reachable() -> bool:
    try:
        request = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(request, timeout=0.5) as response:
            status: int = response.status
            return 200 <= status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return False


def _extract_openai_text(parsed: object) -> str:
    if not isinstance(parsed, dict):
        return ""
    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    # Some completions endpoints place the body in ``text`` directly
    text = first.get("text")
    if isinstance(text, str):
        return text
    return ""


# --- factory --------------------------------------------------------


def default_llm_client(model: str | None = None) -> LLMClient:
    """Pick the right client for the current environment.

    Resolution order:

    1. ``CDCS_LLM_PROVIDER`` env var (``anthropic`` | ``ollama`` |
       ``pollinations``) takes precedence if set explicitly.
    2. ``ANTHROPIC_API_KEY`` in env → Anthropic (caller went out of
       their way to configure it).
    3. ``ollama serve`` running locally → Ollama (offline, no limits).
    4. Fallback: Pollinations. Public, keyless, works out of the box,
       but rate-limited and occasionally flaky.

    The model can be overridden with ``CDCS_MODEL`` or the explicit
    ``model`` argument (the argument wins over the env var).
    """
    provider = os.environ.get("CDCS_LLM_PROVIDER", "").strip().lower()
    explicit_model = (model or os.environ.get("CDCS_MODEL", "")).strip()
    if provider == "anthropic":
        return AnthropicClient(model=explicit_model or DEFAULT_MODEL)
    if provider == "ollama":
        return OllamaClient(model=explicit_model or DEFAULT_OLLAMA_MODEL)
    if provider == "pollinations":
        return PollinationsClient(model=explicit_model or DEFAULT_POLLINATIONS_MODEL)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicClient(model=explicit_model or DEFAULT_MODEL)
    if _ollama_is_reachable():
        return OllamaClient(model=explicit_model or DEFAULT_OLLAMA_MODEL)
    return PollinationsClient(model=explicit_model or DEFAULT_POLLINATIONS_MODEL)


# --- RecordedLLMClient (for tests / deterministic replay) -----------


@dataclass(slots=True)
class RecordedLLMClient:
    """Replays pre-recorded responses keyed by prompt hash.

    Use to build hermetic end-to-end tests of the synthesis pipeline.
    A test sets up the expected prompts → responses, runs the
    orchestrator, and asserts on the produced artifacts.
    """

    recordings: dict[str, str] = field(default_factory=dict)
    model: str = "recorded"
    calls: list[Prompt] = field(default_factory=list)

    def register(self, prompt: Prompt, response: str) -> None:
        self.recordings[prompt_fingerprint(prompt)] = response

    def register_kind(self, kind: str, response: str) -> None:
        """Bind a response to any prompt of a given kind.

        Useful when the exact prompt body isn't stable across test
        edits but the kind (implementation/test/repair) is.
        """
        self.recordings[f"kind:{kind}"] = response

    def complete(self, prompt: Prompt) -> str:
        self.calls.append(prompt)
        fingerprint = prompt_fingerprint(prompt)
        if fingerprint in self.recordings:
            return strip_code_fences(self.recordings[fingerprint])
        kind_key = f"kind:{prompt.kind}"
        if kind_key in self.recordings:
            return strip_code_fences(self.recordings[kind_key])
        raise LLMError(
            f"RecordedLLMClient: no recording for {prompt.kind!r} "
            f"prompt (fingerprint={fingerprint[:12]})"
        )


# --- helpers --------------------------------------------------------


def prompt_fingerprint(prompt: Prompt) -> str:
    """Stable hash of a prompt — system + user + kind."""
    blob = f"{prompt.kind}\0{prompt.system}\0{prompt.user}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# Match a leading ```python (or ```py / ```) fence and the matching
# trailing ``` fence. Tolerant of leading whitespace and surrounding blank lines.
_FENCE_RE = re.compile(
    r"^\s*```(?:python|py)?\s*\n(?P<body>.*?)\n```\s*$",
    re.DOTALL,
)


def strip_code_fences(text: str) -> str:
    """Remove a single wrapping ``` fence if the LLM added one.

    Idempotent: leaves fence-less text untouched. Multiple stacked
    fences are not supported — synthesizer output should be one code
    block, and we'd rather not silently merge multiple blocks.
    """
    match = _FENCE_RE.match(text.strip())
    if match is None:
        return text.strip() + "\n"
    body = match.group("body")
    return body.rstrip() + "\n"
