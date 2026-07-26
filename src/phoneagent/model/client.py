"""OpenAI-compatible vision-language model client for PhoneAgent."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from phoneagent.config.messages import get_message


class ModelProtocolError(RuntimeError):
    """Raised when a model response is empty or violates the action protocol."""

    def __init__(self, message: str, *, raw_content: str | None = None):
        super().__init__(message)
        self.raw_content = raw_content


@dataclass(slots=True)
class ModelConfig:
    """Configuration for the OpenAI-compatible model endpoint."""

    base_url: str = field(
        default_factory=lambda: os.getenv("PHONE_AGENT_BASE_URL", "http://localhost:8000/v1")
    )
    api_key: str = field(default_factory=lambda: os.getenv("PHONE_AGENT_API_KEY", "EMPTY"))
    model_name: str = field(
        default_factory=lambda: os.getenv("PHONE_AGENT_MODEL", "autoglm-phone-9b")
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("PHONE_AGENT_MAX_TOKENS", "3000"))
    )
    temperature: float = field(
        default_factory=lambda: float(os.getenv("PHONE_AGENT_TEMPERATURE", "0"))
    )
    top_p: float = field(default_factory=lambda: float(os.getenv("PHONE_AGENT_TOP_P", "0.85")))
    frequency_penalty: float = field(
        default_factory=lambda: float(os.getenv("PHONE_AGENT_FREQUENCY_PENALTY", "0.2"))
    )
    timeout: float = field(
        default_factory=lambda: float(os.getenv("PHONE_AGENT_MODEL_TIMEOUT", "120"))
    )
    max_retries: int = field(
        default_factory=lambda: int(os.getenv("PHONE_AGENT_MODEL_RETRIES", "2"))
    )
    retry_backoff: float = field(
        default_factory=lambda: float(os.getenv("PHONE_AGENT_MODEL_RETRY_BACKOFF", "1"))
    )
    extra_body: dict[str, Any] = field(default_factory=dict)
    stream: bool = True
    capture_usage: bool = field(
        default_factory=lambda: (
            os.getenv("PHONE_AGENT_CAPTURE_USAGE", "1").strip().lower()
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
        return str(self.finish_reason or "").casefold() in {
            "length",
            "max_tokens",
            "max_output_tokens",
        }

    def to_assistant_message_content(self) -> str:
        """Serialize response back into the prompt-compatible format."""
        return f"<answer>{self.action}</answer>"


class StreamingBoundaryDetector:
    """Detect the transition from reasoning text to executable action text."""

    def __init__(self, markers: Iterable[str]):
        self.markers = tuple(markers)
        if not self.markers:
            raise ValueError("At least one boundary marker is required")
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
        matches = [(text.find(marker), marker) for marker in self.markers]
        matches = [(idx, marker) for idx, marker in matches if idx >= 0]
        return min(matches, key=lambda item: item[0]) if matches else None


class ModelResponseParser:
    """Split optional reasoning from the final executable answer.

    The only executable region is one terminal ``<answer>...</answer>`` block.
    Any preceding text is inert reasoning. No separate thinking envelope or
    unwrapped-action compatibility grammar is supported.
    """

    ANSWER_RE = re.compile(
        r"^(?P<thinking>.*?)<answer>(?P<action>.*?)</answer>\s*$",
        re.DOTALL | re.IGNORECASE,
    )
    ANSWER_OPEN_RE = re.compile(r"<answer>", re.IGNORECASE)
    ANSWER_CLOSE_RE = re.compile(r"</answer>", re.IGNORECASE)

    @classmethod
    def parse(cls, raw_content: str) -> tuple[str, str]:
        content = (raw_content or "").strip()
        if not content:
            raise ModelProtocolError("Model response content is empty")
        if (
            len(cls.ANSWER_OPEN_RE.findall(content)) != 1
            or len(cls.ANSWER_CLOSE_RE.findall(content)) != 1
        ):
            raise ModelProtocolError(
                "Model response must contain exactly one <answer>...</answer> block"
            )

        envelope = cls.ANSWER_RE.fullmatch(content)
        if not envelope:
            raise ModelProtocolError(
                "The <answer>...</answer> block must be complete and end the model response"
            )
        action = envelope.group("action").strip()
        if not action:
            raise ModelProtocolError("Model response did not contain an action")
        return envelope.group("thinking").strip(), action


StreamCallback = Callable[[str], None]


class ModelClient:
    """OpenAI-compatible client with bounded retries and protocol validation."""

    def __init__(self, config: ModelConfig | None = None):
        self.config = config or ModelConfig()
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
        self.boundary_detector = StreamingBoundaryDetector(markers=("<answer>",))

    def request(
        self,
        messages: list[dict[str, Any]],
        *,
        print_stream: bool = True,
        stream_callback: StreamCallback | None = None,
    ) -> ModelResponse:
        """Send a request and retry transient API failures with backoff."""
        if not messages:
            raise ValueError("messages cannot be empty")
        last_error: Exception | None = None
        attempts = self.config.max_retries + 1

        for attempt in range(1, attempts + 1):
            try:
                response = self._request_once(
                    messages,
                    print_stream=print_stream,
                    stream_callback=stream_callback,
                )
                response.attempts = attempt
                return response
            except Exception as exc:
                last_error = exc
                if attempt >= attempts or not self._is_retryable(exc):
                    raise
                time.sleep(self.config.retry_backoff * (2 ** (attempt - 1)))

        assert last_error is not None
        raise last_error

    def _request_once(
        self,
        messages: list[dict[str, Any]],
        *,
        print_stream: bool,
        stream_callback: StreamCallback | None,
    ) -> ModelResponse:
        start_time = time.monotonic()
        time_to_first_token: float | None = None
        time_to_thinking_end: float | None = None
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        finish_reason: str | None = None
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        total_tokens: int | None = None

        request_kwargs = {
            "messages": messages,
            "model": self.config.model_name,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "frequency_penalty": self.config.frequency_penalty,
            "extra_body": self.config.extra_body,
        }

        if self.config.stream:
            self.boundary_detector.reset()
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
            for chunk in stream:
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    prompt_tokens, completion_tokens, total_tokens = self._extract_usage(usage)
                if not getattr(chunk, "choices", None):
                    continue
                choice = chunk.choices[0]
                chunk_finish_reason = getattr(choice, "finish_reason", None)
                if chunk_finish_reason:
                    finish_reason = str(chunk_finish_reason)
                delta = choice.delta
                content = self._content_to_text(getattr(delta, "content", None))
                reasoning = self._content_to_text(getattr(delta, "reasoning_content", None))
                if reasoning:
                    reasoning_parts.append(reasoning)
                    if print_stream:
                        self._emit_text(reasoning, stream_callback)
                if not content:
                    continue
                if time_to_first_token is None:
                    time_to_first_token = time.monotonic() - start_time
                content_parts.append(content)
                printable, transitioned = self.boundary_detector.feed(content)
                if print_stream and printable:
                    self._emit_text(printable, stream_callback)
                if transitioned and time_to_thinking_end is None:
                    time_to_thinking_end = time.monotonic() - start_time
                    if print_stream and stream_callback is None:
                        print(flush=True)
            remaining = self.boundary_detector.finalize()
            if print_stream and remaining:
                self._emit_text(remaining, stream_callback)
        else:
            response = self.client.chat.completions.create(**request_kwargs, stream=False)
            if not response.choices:
                raise ModelProtocolError("Model API returned no choices")
            choice = response.choices[0]
            finish_reason = (
                str(choice.finish_reason) if getattr(choice, "finish_reason", None) else None
            )
            message = choice.message
            content_parts.append(self._content_to_text(message.content))
            reasoning = self._content_to_text(getattr(message, "reasoning_content", None))
            if reasoning:
                reasoning_parts.append(reasoning)
            time_to_first_token = time.monotonic() - start_time
            usage = getattr(response, "usage", None)
            if usage is not None:
                prompt_tokens, completion_tokens, total_tokens = self._extract_usage(usage)

        total_time = time.monotonic() - start_time
        raw_content = "".join(content_parts).strip()
        reasoning_content = "".join(reasoning_parts).strip()
        if not raw_content:
            raise ModelProtocolError(
                "Model returned an empty content payload",
                raw_content=raw_content,
            )

        try:
            thinking, action = ModelResponseParser.parse(raw_content)
        except ModelProtocolError as exc:
            raise ModelProtocolError(str(exc), raw_content=raw_content) from exc
        if not thinking and reasoning_content:
            thinking = reasoning_content
        if not action:
            raise ModelProtocolError(
                "Model response did not contain an action",
                raw_content=raw_content,
            )
        if time_to_thinking_end is None and thinking:
            time_to_thinking_end = total_time
        if print_stream:
            self._print_metrics(
                time_to_first_token,
                time_to_thinking_end,
                total_time,
                finish_reason=finish_reason,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )

        return ModelResponse(
            thinking=thinking,
            action=action,
            raw_content=raw_content,
            time_to_first_token=time_to_first_token,
            time_to_thinking_end=time_to_thinking_end,
            total_time=total_time,
            finish_reason=finish_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _extract_usage(usage: Any) -> tuple[int | None, int | None, int | None]:
        def read(name: str) -> int | None:
            value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        return read("prompt_tokens"), read("completion_tokens"), read("total_tokens")

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

    @staticmethod
    def _emit_text(text: str, callback: StreamCallback | None) -> None:
        if callback is not None:
            callback(text)
        else:
            print(text, end="", flush=True)

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        if isinstance(exc, ModelProtocolError):
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
