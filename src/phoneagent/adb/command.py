"""Shared helpers for checked ADB command execution."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Sequence
from typing import Any


class ADBCommandError(RuntimeError):
    """Raised when an ADB command cannot be executed successfully."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        returncode: int | None = None,
        stdout: str | bytes | None = None,
        stderr: str | bytes | None = None,
        reason: str | None = None,
        attempts: int = 1,
    ):
        self.command = list(command)
        self.returncode = returncode
        self.stdout = _to_text(stdout)
        self.stderr = _to_text(stderr)
        self.reason = reason
        self.attempts = attempts
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        command = " ".join(self.command)
        if self.reason:
            parts = [f"ADB command failed: {command}", f"Reason: {self.reason}"]
        elif self.returncode is None:
            parts = [f"ADB command failed: {command}"]
        else:
            parts = [f"ADB command failed with exit code {self.returncode}: {command}"]
        if self.attempts > 1:
            parts.append(f"attempts: {self.attempts}")
        stdout = self.stdout.strip()
        stderr = self.stderr.strip()
        if stdout:
            parts.append(f"stdout: {_truncate(stdout)}")
        if stderr:
            parts.append(f"stderr: {_truncate(stderr)}")
        return " | ".join(parts)


def build_adb_command(
    args: Sequence[Any],
    *,
    device_id: str | None = None,
    adb_path: str = "adb",
) -> list[str]:
    """Build an adb command with an optional device selector."""
    command = [adb_path]
    if device_id:
        command.extend(["-s", device_id])
    command.extend(str(arg) for arg in args)
    return command


def run_adb(
    args: Sequence[Any],
    *,
    device_id: str | None = None,
    adb_path: str = "adb",
    timeout: float | None = None,
    check: bool = True,
    text: bool = True,
    retries: int = 0,
    retry_delay: float = 0.35,
) -> subprocess.CompletedProcess[str | bytes]:
    """Run an ADB command.

    ``retries`` should normally be used only for read-only/query commands. ADB
    transport failures are retried; semantic command failures are returned or
    raised immediately to avoid duplicating state-changing input operations.
    """
    command = build_adb_command(args, device_id=device_id, adb_path=adb_path)
    attempts = max(1, int(retries) + 1)
    last_result: subprocess.CompletedProcess[str | bytes] | None = None
    last_reason: str | None = None

    for attempt in range(1, attempts + 1):
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=text,
                encoding="utf-8" if text else None,
                errors="replace" if text else None,
                timeout=timeout,
            )
            last_result = result
        except FileNotFoundError as exc:
            raise ADBCommandError(
                command, reason="adb executable not found", attempts=attempt
            ) from exc
        except subprocess.TimeoutExpired as exc:
            last_reason = f"timed out after {timeout}s"
            if attempt < attempts:
                time.sleep(max(0.0, retry_delay) * attempt)
                continue
            raise ADBCommandError(
                command,
                stdout=exc.stdout,
                stderr=exc.stderr,
                reason=last_reason,
                attempts=attempt,
            ) from exc

        if result.returncode == 0:
            return result

        output = f"{_to_text(result.stdout)}\n{_to_text(result.stderr)}".casefold()
        if attempt < attempts and _is_retryable_transport_failure(output):
            last_reason = "transient adb transport failure"
            time.sleep(max(0.0, retry_delay) * attempt)
            continue
        if not check:
            return result

        raise ADBCommandError(
            command,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            attempts=attempt,
        )

    # Defensive fallback. The loop always returns or raises.
    assert last_result is not None
    raise ADBCommandError(
        command,
        returncode=last_result.returncode,
        stdout=last_result.stdout,
        stderr=last_result.stderr,
        reason=last_reason,
        attempts=attempts,
    )


def _is_retryable_transport_failure(output: str) -> bool:
    markers = (
        "device offline",
        "device not found",
        "closed",
        "cannot connect to daemon",
        "daemon not running",
        "protocol fault",
        "connection reset",
        "transport error",
    )
    return any(marker in output for marker in markers)


def _to_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _truncate(text: str, limit: int = 1000) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
