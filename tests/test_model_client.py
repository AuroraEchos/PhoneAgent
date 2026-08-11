from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

import phoneagent.model.client as client_module
from phoneagent.model import (
    ModelClient,
    ModelConfig,
    ModelProtocolError,
    ModelRequestCancelled,
    StreamingBoundaryDetector,
)


def _chunk(
    *,
    content: str | None = None,
    reasoning: str | None = None,
    finish_reason: str | None = None,
    usage: dict[str, int] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=content,
                    reasoning_content=reasoning,
                ),
                finish_reason=finish_reason,
            )
        ],
        usage=usage,
    )


class _FakeCompletions:
    def __init__(self, chunks: list[SimpleNamespace]):
        self.chunks = chunks
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object):
        self.calls.append(kwargs)
        return iter(self.chunks)


class _BlockingStream:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.closed = threading.Event()

    def __iter__(self):
        return self

    def __next__(self):
        self.entered.set()
        self.closed.wait(timeout=2)
        raise RuntimeError("stream closed")

    def close(self) -> None:
        self.closed.set()


class _BlockingCompletions:
    def __init__(self, stream: _BlockingStream) -> None:
        self.stream = stream

    def create(self, **_kwargs: object):
        return self.stream


def test_boundary_detector_matches_case_insensitively_across_chunks() -> None:
    detector = StreamingBoundaryDetector(markers=("do(", "finish("))
    printed: list[str] = []

    text, transitioned = detector.feed("分析D")
    printed.append(text)
    assert transitioned is False

    text, transitioned = detector.feed('o(action="Back")')
    printed.append(text)
    assert transitioned is True
    printed.append(detector.finalize())

    assert "".join(printed) == "分析"
def test_streaming_ttft_includes_reasoning_and_detector_is_request_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completions = _FakeCompletions(
        [
            _chunk(reasoning="先分析"),
            _chunk(content="do"),
            _chunk(content='(action="Back")', finish_reason="stop"),
        ]
    )
    client = ModelClient(ModelConfig(capture_usage=False))
    client.client.close()
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    timestamps = iter((10.0, 10.2, 10.5, 10.8))
    monkeypatch.setattr(client_module.time, "monotonic", lambda: next(timestamps))

    response = client.request(
        [{"role": "user", "content": "test"}],
        print_stream=False,
    )

    assert completions.calls[0]["stream"] is True
    assert not hasattr(client, "boundary_detector")
    assert response.thinking == "先分析"
    assert response.action == 'do(action="Back")'
    assert response.time_to_first_token == pytest.approx(0.2)
    assert response.time_to_thinking_end == pytest.approx(0.5)
    assert response.total_time == pytest.approx(0.8)


def test_protocol_error_preserves_truncation_finish_reason() -> None:
    completions = _FakeCompletions(
        [
            _chunk(
                content='do(action="Back"',
                finish_reason="length",
                usage={"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
            )
        ]
    )
    client = ModelClient(ModelConfig(capture_usage=False, max_retries=0))
    client.client.close()
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    with pytest.raises(ModelProtocolError) as captured:
        client.request([{"role": "user", "content": "test"}], print_stream=False)

    assert captured.value.finish_reason == "length"
    assert captured.value.truncated is True
    assert captured.value.raw_content == 'do(action="Back"'
    assert captured.value.metrics["prompt_tokens"] == 120
    assert captured.value.metrics["completion_tokens"] == 30
    assert captured.value.metrics["total_tokens"] == 150
    assert captured.value.metrics["total_time"] is not None


def test_sync_stream_is_closed_when_request_is_cancelled() -> None:
    stream = _BlockingStream()
    client = ModelClient(ModelConfig(capture_usage=False, max_retries=0))
    client.client.close()
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=_BlockingCompletions(stream)))
    cancel_event = threading.Event()
    captured: list[BaseException] = []

    def request() -> None:
        try:
            client.request(
                [{"role": "user", "content": "test"}],
                print_stream=False,
                cancel_event=cancel_event,
            )
        except BaseException as exc:  # noqa: BLE001 - asserting exact cancellation below
            captured.append(exc)

    thread = threading.Thread(target=request)
    thread.start()
    assert stream.entered.wait(timeout=1)
    cancel_event.set()
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert stream.closed.is_set()
    assert len(captured) == 1
    assert isinstance(captured[0], ModelRequestCancelled)
