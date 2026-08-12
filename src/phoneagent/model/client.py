"""OpenAI-compatible vision-language model client for PhoneAgent."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from contextlib import suppress
import inspect
import json
import os
import re
from threading import Event, Thread
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from phoneagent.config.messages import get_message


_TRUNCATION_FINISH_REASONS = frozenset({"length", "max_tokens", "max_output_tokens"})


def _is_truncation_finish_reason(finish_reason: str | None) -> bool:
    return str(finish_reason or "").casefold() in _TRUNCATION_FINISH_REASONS


class ModelProtocolError(RuntimeError):
    """Raised when a model response is empty or violates the action protocol."""

    def __init__(
        self,
        message: str,
        *,
        raw_content: str | None = None,
        finish_reason: str | None = None,
        metrics: dict[str, Any] | None = None,
        error_code: str = "model_protocol_error",
    ):
        super().__init__(message)
        self.raw_content = raw_content
        self.finish_reason = finish_reason
        self.metrics = dict(metrics or {})
        self.error_code = error_code

    @property
    def truncated(self) -> bool:
        """Whether generation stopped because the provider's output limit was reached."""
        return _is_truncation_finish_reason(self.finish_reason)


class ModelRequestCancelled(RuntimeError):
    """Raised when a caller cancels an in-flight model request."""


@dataclass(slots=True)
class ModelConfig:
    """Configuration for the OpenAI-compatible model endpoint."""

    base_url: str = field(
        default_factory=lambda: os.getenv("BASE_URL", "http://localhost:8000/v1")
    )
    api_key: str = field(default_factory=lambda: os.getenv("API_KEY", "EMPTY"))
    model_name: str = field(
        default_factory=lambda: os.getenv("MODEL", "autoglm-phone-9b")
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("MAX_TOKENS", "3000"))
    )
    temperature: float = field(
        default_factory=lambda: float(os.getenv("TEMPERATURE", "0"))
    )
    top_p: float = field(default_factory=lambda: float(os.getenv("TOP_P", "0.85")))
    frequency_penalty: float = field(
        default_factory=lambda: float(os.getenv("FREQUENCY_PENALTY", "0.0"))
    )
    timeout: float = field(
        default_factory=lambda: float(os.getenv("MODEL_TIMEOUT", "120"))
    )
    max_retries: int = field(
        default_factory=lambda: int(os.getenv("MODEL_RETRIES", "2"))
    )
    retry_backoff: float = field(
        default_factory=lambda: float(os.getenv("MODEL_RETRY_BACKOFF", "1"))
    )
    extra_body: dict[str, Any] = field(default_factory=dict)
    capture_usage: bool = field(
        default_factory=lambda: (
            os.getenv("CAPTURE_USAGE", "1").strip().lower()
            not in {"0", "false", "no", "off"}
        )
    )

    def __post_init__(self) -> None:
        self.base_url = self.base_url.strip()
        self.model_name = self.model_name.strip()
        if not self.base_url:
            raise ValueError("Model base_url cannot be empty")
        if not self.model_name:
            raise ValueError("Model name cannot be empty")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if self.retry_backoff < 0:
            raise ValueError("retry_backoff cannot be negative")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature must be in the range 0..2")
        if not 0 < self.top_p <= 1:
            raise ValueError("top_p must be in the range (0, 1]")


@dataclass(slots=True)
class ModelResponse:
    """Parsed model response returned to the agent runtime."""

    thinking: str
    action: str
    raw_content: str
    time_to_first_token: float | None = None
    time_to_thinking_end: float | None = None
    total_time: float | None = None
    attempts: int = 1
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    @property
    def truncated(self) -> bool:
        """Whether the provider stopped generation because the output limit was hit."""
        return _is_truncation_finish_reason(self.finish_reason)

    def to_assistant_message_content(self) -> str:
        """Serialize response back into the prompt-compatible format."""
        return self.action


class StreamingBoundaryDetector:
    """Detect the transition from reasoning text to executable action text."""

    def __init__(self, markers: Iterable[str]):
        self.markers = tuple(markers)
        if not self.markers:
            raise ValueError("At least one boundary marker is required")
        self._marker_patterns = tuple(
            (marker, re.compile(re.escape(marker), re.IGNORECASE)) for marker in self.markers
        )
        self.max_marker_len = max(len(marker) for marker in self.markers)
        self.reset()

    def reset(self) -> None:
        self._pending = ""
        self.in_action = False

    def feed(self, text: str) -> tuple[str, bool]:
        if self.in_action:
            return "", False
        self._pending += text
        marker_index = self._find_first_marker(self._pending)
        if marker_index is not None:
            idx, _marker = marker_index
            printable = self._pending[:idx]
            self._pending = ""
            self.in_action = True
            return printable, True
        keep = self.max_marker_len - 1
        if len(self._pending) <= keep:
            return "", False
        printable = self._pending[:-keep]
        self._pending = self._pending[-keep:]
        return printable, False

    def finalize(self) -> str:
        if self.in_action:
            self._pending = ""
            return ""
        remaining = self._pending
        self._pending = ""
        return remaining

    def _find_first_marker(self, text: str) -> tuple[int, str] | None:
        matches = [
            (match.start(), marker)
            for marker, pattern in self._marker_patterns
            if (match := pattern.search(text)) is not None
        ]
        return min(matches, key=lambda item: item[0]) if matches else None


class ModelResponseParser:
    """Split optional reasoning from the final executable action.

    The only executable region is one terminal ``do(...)`` or ``finish(...)``
    call. Any preceding text is inert reasoning. XML envelopes, JSON, Markdown
    fences, multiple calls and trailing text are not part of the protocol.
    """

    ACTION_CALL_RE = re.compile(r"(?<![A-Za-z0-9_])(?:do|finish)\s*\(")
    LEGACY_ACTION_TAG_RE = re.compile(r"</?action(?:\s|>)", re.IGNORECASE)

    @classmethod
    def parse(cls, raw_content: str) -> tuple[str, str]:
        content = (raw_content or "").strip()
        if not content:
            raise ModelProtocolError(
                "Model response content is empty",
                error_code="missing_action",
            )
        if cls.LEGACY_ACTION_TAG_RE.search(content):
            raise ModelProtocolError(
                "XML action envelopes are not supported",
                error_code="legacy_action_envelope",
            )

        candidates = list(cls.ACTION_CALL_RE.finditer(content))
        if not candidates:
            raise ModelProtocolError(
                "Model response did not contain a do(...) or finish(...) call",
                error_code="missing_action",
            )
        terminal: list[tuple[int, int]] = []
        for candidate in candidates:
            end = cls._balanced_call_end(content, candidate.start())
            if end is not None and not content[end:].strip():
                terminal.append((candidate.start(), end))
        if terminal:
            action_start, action_end = terminal[0]
            if any(candidate.start() < action_start for candidate in candidates):
                raise ModelProtocolError(
                    "Model response contained multiple do(...) or finish(...) calls",
                    error_code="multiple_actions",
                )
            return content[:action_start].strip(), content[action_start:action_end].strip()

        first_start = candidates[0].start()
        first_end = cls._balanced_call_end(content, first_start)
        if first_end is None:
            raise ModelProtocolError(
                "Model response ended with an incomplete action call",
                error_code="incomplete_action",
            )
        if len(candidates) > 1:
            raise ModelProtocolError(
                "Model response contained multiple do(...) or finish(...) calls",
                error_code="multiple_actions",
            )
        raise ModelProtocolError(
            "Model response contained text after the action call",
            error_code="trailing_content",
        )

    @staticmethod
    def _balanced_call_end(text: str, start: int) -> int | None:
        """Return the end of one balanced call without evaluating model text."""
        open_paren = text.find("(", start)
        if open_paren < 0:
            return None
        depth = 0
        quote: str | None = None
        escaped = False
        for index in range(open_paren, len(text)):
            char = text[index]
            if quote is not None:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                continue
            if char in {'"', "'"}:
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index + 1
                if depth < 0:
                    return None
        return None


def _extract_usage(usage: Any) -> tuple[int | None, int | None, int | None]:
    """Normalize provider usage objects and dictionaries."""

    def read(name: str) -> int | None:
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    return read("prompt_tokens"), read("completion_tokens"), read("total_tokens")


def _content_to_text(content: Any) -> str:
    """Normalize the content shapes returned by OpenAI-compatible providers."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
            else:
                text = getattr(item, "text", None)
                if text:
                    parts.append(str(text))
        return "".join(parts)
    return str(content)


@dataclass(slots=True)
class _StreamResponseState:
    """Transport-neutral state for one streamed model response."""

    started_at: float = field(default_factory=time.monotonic)
    boundary_detector: StreamingBoundaryDetector = field(
        default_factory=lambda: StreamingBoundaryDetector(markers=("do(", "finish("))
    )
    content_parts: list[str] = field(default_factory=list)
    reasoning_parts: list[str] = field(default_factory=list)
    time_to_first_token: float | None = None
    time_to_thinking_end: float | None = None
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    def consume(self, chunk: Any) -> tuple[str, str, bool]:
        """Consume one provider chunk and return reasoning/printable boundary output."""
        usage = getattr(chunk, "usage", None)
        if usage is not None:
            self.prompt_tokens, self.completion_tokens, self.total_tokens = _extract_usage(usage)
        if not getattr(chunk, "choices", None):
            return "", "", False

        choice = chunk.choices[0]
        chunk_finish_reason = getattr(choice, "finish_reason", None)
        if chunk_finish_reason:
            self.finish_reason = str(chunk_finish_reason)
        delta = choice.delta
        content = _content_to_text(getattr(delta, "content", None))
        reasoning = _content_to_text(getattr(delta, "reasoning_content", None))
        if self.time_to_first_token is None and (reasoning or content):
            self.time_to_first_token = time.monotonic() - self.started_at
        if reasoning:
            self.reasoning_parts.append(reasoning)
        if not content:
            return reasoning, "", False

        self.content_parts.append(content)
        printable, transitioned = self.boundary_detector.feed(content)
        if transitioned and self.time_to_thinking_end is None:
            self.time_to_thinking_end = time.monotonic() - self.started_at
        return reasoning, printable, transitioned

    def remaining_printable(self) -> str:
        return self.boundary_detector.finalize()

    def build_response(self) -> ModelResponse:
        """Parse one completed stream and preserve diagnostics on protocol failure."""
        total_time = time.monotonic() - self.started_at
        error_metrics = {
            "time_to_first_token": self.time_to_first_token,
            "time_to_thinking_end": self.time_to_thinking_end,
            "total_time": total_time,
            "finish_reason": self.finish_reason,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "truncated": _is_truncation_finish_reason(self.finish_reason),
        }
        raw_content = "".join(self.content_parts).strip()
        reasoning_content = "".join(self.reasoning_parts).strip()
        if not raw_content:
            raise ModelProtocolError(
                "Model returned an empty content payload",
                raw_content=raw_content,
                finish_reason=self.finish_reason,
                metrics=error_metrics,
                error_code="missing_action",
            )
        try:
            thinking, action = ModelResponseParser.parse(raw_content)
        except ModelProtocolError as exc:
            raise ModelProtocolError(
                str(exc),
                raw_content=raw_content,
                finish_reason=self.finish_reason,
                metrics=error_metrics,
                error_code=exc.error_code,
            ) from exc
        if not thinking and reasoning_content:
            thinking = reasoning_content
        if not action:
            raise ModelProtocolError(
                "Model response did not contain an action",
                raw_content=raw_content,
                finish_reason=self.finish_reason,
                metrics=error_metrics,
                error_code="missing_action",
            )
        if self.time_to_thinking_end is None and thinking:
            self.time_to_thinking_end = total_time
        return ModelResponse(
            thinking=thinking,
            action=action,
            raw_content=raw_content,
            time_to_first_token=self.time_to_first_token,
            time_to_thinking_end=self.time_to_thinking_end,
            total_time=total_time,
            finish_reason=self.finish_reason,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=self.total_tokens,
        )


StreamCallback = Callable[[str], None]


class BaseModelClient(ABC):
    """Protocol for a model client that the agent runtime can call.

    Subclasses encapsulate provider-specific initialisation, streaming,
    retry policies and response parsing.  The runtime only depends on this
    interface, so swapping providers (OpenAI-compatible, Anthropic, Gemini,
    local vLLM, …) does not touch the agent loop.
    """

    def __init__(self, config: ModelConfig | None = None):
        self.config = config or ModelConfig()

    @abstractmethod
    def request(
        self,
        messages: list[dict[str, Any]],
        *,
        print_stream: bool = True,
        stream_callback: StreamCallback | None = None,
        cancel_event: Event | None = None,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        """Send a request and return a parsed, protocol-conformant response."""


class OpenAIModelClient(BaseModelClient):
    """Streaming OpenAI-compatible client with retries and protocol validation."""

    def __init__(self, config: ModelConfig | None = None):
        super().__init__(config)
        try:
            from openai import OpenAI, DefaultHttpxClient
        except ImportError as exc:
            raise RuntimeError(
                "The openai package is required. Install dependencies with: pip install -e ."
            ) from exc
        self.client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            timeout=self.config.timeout,
            http_client=DefaultHttpxClient(trust_env=False),
        )

    def request(
        self,
        messages: list[dict[str, Any]],
        *,
        print_stream: bool = True,
        stream_callback: StreamCallback | None = None,
        cancel_event: Event | None = None,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        """Send a request and retry transient API failures with backoff."""
        if not messages:
            raise ValueError("messages cannot be empty")
        last_error: Exception | None = None
        attempts = self.config.max_retries + 1

        for attempt in range(1, attempts + 1):
            self._raise_if_cancelled(cancel_event)
            try:
                response = self._request_once(
                    messages,
                    print_stream=print_stream,
                    stream_callback=stream_callback,
                    cancel_event=cancel_event,
                    max_tokens=max_tokens,
                )
                response.attempts = attempt
                return response
            except Exception as exc:
                last_error = exc
                if attempt >= attempts or not self._is_retryable(exc):
                    raise
                delay = self.config.retry_backoff * (2 ** (attempt - 1))
                if cancel_event is not None and cancel_event.wait(delay):
                    raise ModelRequestCancelled("Model request cancelled") from exc
                if cancel_event is None:
                    time.sleep(delay)

        assert last_error is not None
        raise last_error

    def _request_once(
        self,
        messages: list[dict[str, Any]],
        *,
        print_stream: bool,
        stream_callback: StreamCallback | None,
        cancel_event: Event | None,
        max_tokens: int | None,
    ) -> ModelResponse:
        self._raise_if_cancelled(cancel_event)
        stream_state = _StreamResponseState(started_at=time.monotonic())

        request_kwargs = {
            "messages": messages,
            "model": self.config.model_name,
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "frequency_penalty": self.config.frequency_penalty,
            "extra_body": self.config.extra_body,
        }

        stream_kwargs = dict(request_kwargs)
        if self.config.capture_usage:
            stream_kwargs["stream_options"] = {"include_usage": True}
        try:
            stream = self.client.chat.completions.create(**stream_kwargs, stream=True)
        except Exception as exc:
            if "stream_options" not in stream_kwargs or not self._usage_option_unsupported(exc):
                raise
            stream_kwargs.pop("stream_options", None)
            stream = self.client.chat.completions.create(**stream_kwargs, stream=True)
        watcher_stop: Event | None = None
        if cancel_event is not None:
            watcher_stop = Event()
            Thread(
                target=self._close_stream_when_cancelled,
                args=(stream, cancel_event, watcher_stop),
                name="phoneagent-model-cancel",
                daemon=True,
            ).start()
        try:
            for chunk in stream:
                self._raise_if_cancelled(cancel_event)
                reasoning, printable, transitioned = stream_state.consume(chunk)
                if print_stream and reasoning:
                    self._emit_text(reasoning, stream_callback)
                if print_stream and printable:
                    self._emit_text(printable, stream_callback)
                if transitioned and print_stream and stream_callback is None:
                    print(flush=True)
            self._raise_if_cancelled(cancel_event)
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set():
                raise ModelRequestCancelled("Model request cancelled") from exc
            raise
        finally:
            if watcher_stop is not None:
                watcher_stop.set()
            self._close_sync_stream(stream)
        remaining = stream_state.remaining_printable()
        if print_stream and remaining:
            self._emit_text(remaining, stream_callback)
        response = stream_state.build_response()
        if print_stream:
            self._print_metrics(
                response.time_to_first_token,
                response.time_to_thinking_end,
                response.total_time or 0.0,
                finish_reason=response.finish_reason,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                total_tokens=response.total_tokens,
            )
        return response

    @staticmethod
    def _extract_usage(usage: Any) -> tuple[int | None, int | None, int | None]:
        return _extract_usage(usage)

    @staticmethod
    def _usage_option_unsupported(exc: Exception) -> bool:
        text = str(exc).casefold()
        status_code = getattr(exc, "status_code", None)
        return status_code in {400, 404, 422} and any(
            marker in text
            for marker in ("stream_options", "include_usage", "unsupported", "unknown field")
        )

    @staticmethod
    def _content_to_text(content: Any) -> str:
        return _content_to_text(content)

    @staticmethod
    def _emit_text(text: str, callback: StreamCallback | None) -> None:
        if callback is not None:
            callback(text)
        else:
            print(text, end="", flush=True)

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        if isinstance(exc, (ModelProtocolError, ModelRequestCancelled)):
            return False
        status_code = getattr(exc, "status_code", None)
        if status_code in {408, 409, 429} or (isinstance(status_code, int) and status_code >= 500):
            return True
        name = type(exc).__name__.casefold()
        return any(
            marker in name for marker in ("timeout", "connection", "ratelimit", "internalserver")
        )

    def _print_metrics(
        self,
        time_to_first_token: float | None,
        time_to_thinking_end: float | None,
        total_time: float,
        *,
        finish_reason: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
    ) -> None:
        print()
        print("=" * 50)
        print(f"{get_message('performance_metrics')}:")
        print("-" * 50)
        if time_to_first_token is not None:
            print(f"{get_message('time_to_first_token')}: {time_to_first_token:.3f}s")
        if time_to_thinking_end is not None:
            print(f"{get_message('time_to_thinking_end')}: {time_to_thinking_end:.3f}s")
        print(f"{get_message('total_inference_time')}: {total_time:.3f}s")
        if finish_reason:
            print(f"Finish Reason: {finish_reason}")
        if prompt_tokens is not None:
            print(f"Prompt Tokens: {prompt_tokens}")
        if completion_tokens is not None:
            print(f"Completion Tokens: {completion_tokens}")
        if total_tokens is not None:
            print(f"Total Tokens: {total_tokens}")
        print("=" * 50)

    @staticmethod
    def _raise_if_cancelled(cancel_event: Event | None) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise ModelRequestCancelled("Model request cancelled")

    @staticmethod
    def _close_sync_stream(stream: Any) -> None:
        close = getattr(stream, "close", None)
        if callable(close):
            with suppress(Exception):
                close()

    @classmethod
    def _close_stream_when_cancelled(
        cls,
        stream: Any,
        cancel_event: Event,
        watcher_stop: Event,
    ) -> None:
        while not watcher_stop.is_set():
            if cancel_event.wait(0.05):
                if not watcher_stop.is_set():
                    cls._close_sync_stream(stream)
                return


class MessageBuilder:
    """Helpers for building OpenAI-compatible chat messages."""

    @staticmethod
    def create_system_message(content: str) -> dict[str, Any]:
        return {"role": "system", "content": content}

    @staticmethod
    def create_user_message(
        text: str,
        image_base64: str | None = None,
        image_mime_type: str = "image/png",
    ) -> dict[str, Any]:
        content: list[dict[str, Any]] = []
        if image_base64:
            mime_type = image_mime_type or "image/png"
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{image_base64}"},
                }
            )
        content.append({"type": "text", "text": text})
        return {"role": "user", "content": content}

    @staticmethod
    def create_assistant_message(content: str) -> dict[str, Any]:
        return {"role": "assistant", "content": content}

    @staticmethod
    def remove_images_from_message(message: dict[str, Any]) -> dict[str, Any]:
        if isinstance(message.get("content"), list):
            return {
                **message,
                "content": [
                    item
                    for item in message["content"]
                    if isinstance(item, dict) and item.get("type") == "text"
                ],
            }
        return dict(message)

    @staticmethod
    def build_screen_info(**info: Any) -> str:
        return json.dumps(info, ensure_ascii=False, separators=(",", ":"))


class AsyncOpenAIModelClient(BaseModelClient):
    """Async OpenAI-compatible client using ``AsyncOpenAI`` for non-blocking streaming.

    Cancellation is cooperative: every yielded chunk is an opportunity for the
    event loop to service a cancel request.
    """

    def __init__(self, config: ModelConfig | None = None):
        super().__init__(config)
        try:
            from openai import AsyncOpenAI, DefaultAsyncHttpxClient
        except ImportError as exc:
            raise RuntimeError(
                "The openai package is required. Install dependencies with: pip install -e ."
            ) from exc
        self.client = AsyncOpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            timeout=self.config.timeout,
            http_client=DefaultAsyncHttpxClient(trust_env=False),
        )

    async def request(
        self,
        messages: list[dict[str, Any]],
        *,
        print_stream: bool = True,
        stream_callback: StreamCallback | None = None,
        cancel_event: Event | None = None,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        """Send an async request and retry transient API failures with backoff."""
        if not messages:
            raise ValueError("messages cannot be empty")
        last_error: Exception | None = None
        attempts = self.config.max_retries + 1

        for attempt in range(1, attempts + 1):
            OpenAIModelClient._raise_if_cancelled(cancel_event)
            try:
                response = await self._request_once(
                    messages,
                    print_stream=print_stream,
                    stream_callback=stream_callback,
                    cancel_event=cancel_event,
                    max_tokens=max_tokens,
                )
                response.attempts = attempt
                return response
            except Exception as exc:
                last_error = exc
                if attempt >= attempts or not self._is_retryable(exc):
                    raise
                delay = self.config.retry_backoff * (2 ** (attempt - 1))
                await self._sleep_with_cancellation(delay, cancel_event)

        assert last_error is not None
        raise last_error

    async def _request_once(
        self,
        messages: list[dict[str, Any]],
        *,
        print_stream: bool,
        stream_callback: StreamCallback | None,
        cancel_event: Event | None,
        max_tokens: int | None,
    ) -> ModelResponse:
        OpenAIModelClient._raise_if_cancelled(cancel_event)
        stream_state = _StreamResponseState(started_at=time.monotonic())

        request_kwargs = {
            "messages": messages,
            "model": self.config.model_name,
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "frequency_penalty": self.config.frequency_penalty,
            "extra_body": self.config.extra_body,
        }

        stream_kwargs = dict(request_kwargs)
        if self.config.capture_usage:
            stream_kwargs["stream_options"] = {"include_usage": True}
        try:
            stream = await self.client.chat.completions.create(**stream_kwargs, stream=True)
        except Exception as exc:
            if "stream_options" not in stream_kwargs or not self._usage_option_unsupported(exc):
                raise
            stream_kwargs.pop("stream_options", None)
            stream = await self.client.chat.completions.create(**stream_kwargs, stream=True)
        try:
            async for chunk in stream:
                OpenAIModelClient._raise_if_cancelled(cancel_event)
                reasoning, printable, transitioned = stream_state.consume(chunk)
                if print_stream and reasoning:
                    self._emit_text(reasoning, stream_callback)
                if print_stream and printable:
                    self._emit_text(printable, stream_callback)
                if transitioned and print_stream and stream_callback is None:
                    print(flush=True)
            OpenAIModelClient._raise_if_cancelled(cancel_event)
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set():
                raise ModelRequestCancelled("Model request cancelled") from exc
            raise
        finally:
            await self._close_async_stream(stream)
        remaining = stream_state.remaining_printable()
        if print_stream and remaining:
            self._emit_text(remaining, stream_callback)
        response = stream_state.build_response()
        if print_stream:
            self._print_metrics(
                response.time_to_first_token,
                response.time_to_thinking_end,
                response.total_time or 0.0,
                finish_reason=response.finish_reason,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                total_tokens=response.total_tokens,
            )
        return response

    @staticmethod
    def _emit_text(text: str, callback: StreamCallback | None) -> None:
        if callback is not None:
            callback(text)
        else:
            print(text, end="", flush=True)

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        return OpenAIModelClient._is_retryable(exc)

    @staticmethod
    def _usage_option_unsupported(exc: Exception) -> bool:
        return OpenAIModelClient._usage_option_unsupported(exc)

    @staticmethod
    def _content_to_text(content: Any) -> str:
        return OpenAIModelClient._content_to_text(content)

    @staticmethod
    def _extract_usage(usage: Any) -> tuple[int | None, int | None, int | None]:
        return OpenAIModelClient._extract_usage(usage)

    def _print_metrics(self, *args: Any, **kwargs: Any) -> None:
        OpenAIModelClient._print_metrics(self, *args, **kwargs)

    @staticmethod
    async def _close_async_stream(stream: Any) -> None:
        close = getattr(stream, "close", None)
        if not callable(close):
            return
        with suppress(Exception):
            result = close()
            if inspect.isawaitable(result):
                await result

    @staticmethod
    async def _sleep_with_cancellation(seconds: float, cancel_event: Event | None) -> None:
        if cancel_event is None:
            await asyncio.sleep(seconds)
            return
        deadline = time.monotonic() + seconds
        while True:
            OpenAIModelClient._raise_if_cancelled(cancel_event)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            await asyncio.sleep(min(0.05, remaining))


# Backward-compatible alias – existing code that references ``ModelClient``
# continues to work and receives an OpenAI-compatible implementation.
ModelClient = OpenAIModelClient
