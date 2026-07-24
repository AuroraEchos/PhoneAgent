"""Thread-safe session orchestration for the local PhoneAgent web console."""

from __future__ import annotations

import io
import json
import math
import os
import re
import threading
import time
import traceback
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from phoneagent import AgentConfig, PhoneAgent
from phoneagent.apps import AppCatalogConfig, AppDiscoveryConfig, AppLauncherConfig
from phoneagent.cli import check_model_api, check_system_requirements
from phoneagent.config.env import load_env
from phoneagent.model import ModelConfig
from phoneagent.runtime import AgentEvent, RecoveryConfig, VerificationConfig


DEVICE_CHECKS = (
    ("adb", "ADB 可执行文件"),
    ("device", "Android 设备"),
    ("keyboard", "ADB Keyboard"),
    ("screenshot", "视觉观察"),
)
MODEL_CHECK = ("model", "视觉模型 API")
BUSY_TASK_STATES = {"running", "waiting_user"}


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, (str, int, float, bool)):
        return enum_value
    return repr(value)


def _check_record(check_id: str, label: str, status: str = "pending") -> dict[str, Any]:
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "summary": "等待检查",
        "details": "",
    }


def _build_configs(project_root: Path) -> tuple[ModelConfig, AgentConfig, Path]:
    load_env(project_root / ".env")
    model_config = ModelConfig()

    trajectory_setting = Path(os.getenv("PHONE_AGENT_TRAJECTORY_DIR", "runs"))
    trajectory_dir = (
        trajectory_setting
        if trajectory_setting.is_absolute()
        else project_root / trajectory_setting
    ).resolve()

    alias_setting = os.getenv("PHONE_AGENT_APP_ALIASES_FILE")
    alias_file: str | None = None
    if alias_setting:
        alias_path = Path(alias_setting)
        alias_file = str(
            alias_path if alias_path.is_absolute() else (project_root / alias_path).resolve()
        )

    agent_config = AgentConfig(
        max_steps=_env_int("PHONE_AGENT_MAX_STEPS", 100),
        max_runtime_seconds=_env_float("PHONE_AGENT_MAX_RUNTIME_SECONDS", 900),
        device_id=os.getenv("PHONE_AGENT_DEVICE_ID") or None,
        verbose=False,
        context_turns=_env_int("PHONE_AGENT_CONTEXT_TURNS", 12),
        max_consecutive_failures=_env_int("PHONE_AGENT_MAX_FAILURES", 3),
        max_repeated_actions=_env_int("PHONE_AGENT_MAX_REPEATED_ACTIONS", 3),
        observation_retries=_env_int("PHONE_AGENT_OBSERVATION_RETRIES", 2),
        trajectory_dir=str(trajectory_dir),
        max_app_context_chars=_env_int("PHONE_AGENT_MAX_APP_CONTEXT_CHARS", 6000),
        app_catalog=AppCatalogConfig(
            ttl_seconds=_env_float("PHONE_AGENT_APP_CATALOG_TTL", 300),
            max_prompt_matches=_env_int("PHONE_AGENT_APP_PROMPT_LIMIT", 5),
        ),
        app_discovery=AppDiscoveryConfig(alias_file=alias_file),
        app_launcher=AppLauncherConfig(),
        verification=VerificationConfig(
            observation_retries=_env_int("PHONE_AGENT_VERIFICATION_RETRIES", 1),
            visual_change_threshold=_env_float(
                "PHONE_AGENT_VERIFICATION_THRESHOLD", 0.002
            ),
        ),
        recovery=RecoveryConfig(
            max_total_recoveries=_env_int("PHONE_AGENT_MAX_RECOVERIES", 8),
            max_attempts_per_failure=_env_int("PHONE_AGENT_RECOVERY_ATTEMPTS", 2),
        ),
    )
    return model_config, agent_config, trajectory_dir


class TrajectoryStore:
    """Read bounded trajectory summaries without permitting path traversal."""

    def __init__(self, directory: Path):
        self.directory = directory.resolve()

    def set_directory(self, directory: Path) -> None:
        self.directory = directory.resolve()

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.directory.exists():
            return []
        files = sorted(
            self.directory.glob("trajectory_*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )[: max(1, min(limit, 200))]
        summaries: list[dict[str, Any]] = []
        for path in files:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                summaries.append(
                    {
                        "filename": path.name,
                        "run_id": payload.get("run_id", ""),
                        "task": payload.get("task", ""),
                        "success": payload.get("success"),
                        "started_at": payload.get("started_at"),
                        "finished_at": payload.get("finished_at"),
                        "duration_seconds": payload.get("duration_seconds"),
                        "event_count": payload.get("event_count", 0),
                        "final_message": payload.get("final_message", ""),
                        "size_bytes": path.stat().st_size,
                    }
                )
            except (OSError, ValueError, TypeError):
                summaries.append(
                    {
                        "filename": path.name,
                        "task": "无法读取此轨迹",
                        "success": None,
                        "event_count": 0,
                        "size_bytes": path.stat().st_size if path.exists() else 0,
                    }
                )
        return summaries

    def read(self, filename: str) -> dict[str, Any]:
        path = self._resolve(filename)
        return json.loads(path.read_text(encoding="utf-8"))

    def path_for(self, filename: str) -> Path:
        return self._resolve(filename)

    def _resolve(self, filename: str) -> Path:
        if not filename or Path(filename).name != filename:
            raise ValueError("Invalid trajectory filename")
        if not re.fullmatch(r"trajectory_[A-Za-z0-9_-]+\.json", filename):
            raise ValueError("Invalid trajectory filename")
        path = (self.directory / filename).resolve()
        if path.parent != self.directory or not path.is_file():
            raise FileNotFoundError(filename)
        return path


class ConsoleRuntime:
    """Own one checked PhoneAgent instance for the lifetime of the web server."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        agent_factory: Callable[..., PhoneAgent] = PhoneAgent,
        device_checker: Callable[[str | None], tuple[bool, str | None]] = (
            check_system_requirements
        ),
        model_checker: Callable[[ModelConfig], bool] = check_model_api,
    ) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()
        initial_trajectory = self.project_root / os.getenv(
            "PHONE_AGENT_TRAJECTORY_DIR", "runs"
        )
        self.trajectories = TrajectoryStore(initial_trajectory)
        self._agent_factory = agent_factory
        self._device_checker = device_checker
        self._model_checker = model_checker
        self._agent: PhoneAgent | None = None
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._events: list[dict[str, Any]] = []
        self._next_sequence = 1
        self._task_thread: threading.Thread | None = None
        self._check_thread: threading.Thread | None = None
        self._checking = False
        self._closing = False
        self._prompt_response: bool | None = None
        self._prompt_answered = False
        self.session_started_at = time.time()

        checks = [_check_record(*item) for item in (*DEVICE_CHECKS, MODEL_CHECK)]
        self.startup: dict[str, Any] = {
            "status": "idle",
            "message": "等待启动检查",
            "checks": checks,
            "device_id": None,
            "model_name": None,
            "base_url": None,
            "completed_at": None,
            "reused": False,
        }
        self.task: dict[str, Any] = self._empty_task()
        self.pending_prompt: dict[str, Any] | None = None

    @staticmethod
    def _empty_task() -> dict[str, Any]:
        return {
            "id": None,
            "status": "idle",
            "goal": "",
            "phase": "idle",
            "current_step": 0,
            "current_app": "",
            "recoveries": 0,
            "started_at": None,
            "finished_at": None,
            "result": "",
            "error": "",
            "trajectory": None,
            "last_thinking": "",
            "last_action": None,
            "last_verification": None,
            "last_recovery": None,
        }

    def start_checks(self) -> bool:
        with self._condition:
            if self._checking or self.task["status"] in BUSY_TASK_STATES:
                return False
            self._checking = True
            self._agent = None
            self.startup.update(
                {
                    "status": "checking",
                    "message": "正在检查设备与模型服务",
                    "completed_at": None,
                    "reused": False,
                }
            )
            self.startup["checks"] = [
                _check_record(check_id, label, "running")
                for check_id, label in (*DEVICE_CHECKS, MODEL_CHECK)
            ]
            self._append_event_locked(
                "startup",
                "开始一次性启动检查",
                {"scope": "web_server_session"},
            )
            self._check_thread = threading.Thread(
                target=self._run_checks,
                name="phoneagent-web-checks",
                daemon=True,
            )
            self._check_thread.start()
            return True

    def _run_checks(self) -> None:
        try:
            model_config, agent_config, trajectory_dir = _build_configs(self.project_root)
            self.trajectories.set_directory(trajectory_dir)
            with self._condition:
                self.startup["model_name"] = model_config.model_name
                self.startup["base_url"] = model_config.base_url

            device_output = io.StringIO()
            try:
                with redirect_stdout(device_output):
                    device_ok, device_id = self._device_checker(agent_config.device_id)
            except Exception as exc:  # Preflight errors must remain visible in the UI.
                device_ok, device_id = False, None
                print(f"[FAILED] {exc}", file=device_output)
            self._apply_device_check_output(device_output.getvalue(), device_ok)

            model_output = io.StringIO()
            try:
                with redirect_stdout(model_output):
                    model_ok = self._model_checker(model_config)
            except Exception as exc:
                model_ok = False
                print(f"[FAILED] {exc}", file=model_output)
            self._apply_model_check_output(model_output.getvalue(), model_ok)

            with self._condition:
                self.startup["device_id"] = device_id
                if device_ok and model_ok and device_id:
                    agent_config.device_id = device_id
                    self._agent = self._agent_factory(
                        model_config=model_config,
                        agent_config=agent_config,
                        confirmation_callback=self._confirmation_callback,
                        takeover_callback=self._takeover_callback,
                        event_callback=self._on_agent_event,
                        note_callback=self._on_note,
                    )
                    self.startup["status"] = "ready"
                    self.startup["message"] = "启动检查完成，运行时可以接收任务"
                    event_message = "PhoneAgent Web Console 已就绪"
                else:
                    self.startup["status"] = "failed"
                    self.startup["message"] = "启动检查未通过，请修复后手动重新检查"
                    event_message = "启动检查未通过"
                self.startup["completed_at"] = time.time()
                self._append_event_locked(
                    "startup_ready" if self._agent is not None else "startup_failed",
                    event_message,
                    {
                        "device_id": device_id,
                        "model": model_config.model_name,
                        "base_url": model_config.base_url,
                    },
                )
        except Exception as exc:
            with self._condition:
                self.startup["status"] = "failed"
                self.startup["message"] = f"无法创建运行配置：{exc}"
                self.startup["completed_at"] = time.time()
                for check in self.startup["checks"]:
                    if check["status"] == "running":
                        check.update(status="failed", summary="配置无效", details=str(exc))
                self._append_event_locked(
                    "startup_failed",
                    "Web Console 配置初始化失败",
                    {"error": str(exc)},
                )
        finally:
            with self._condition:
                self._checking = False
                self._condition.notify_all()

    def _apply_device_check_output(self, output: str, overall_ok: bool) -> None:
        sections = self._split_device_sections(output)
        with self._condition:
            for index, (check_id, _label) in enumerate(DEVICE_CHECKS, start=1):
                details = sections.get(index, "").strip()
                if "[FAILED]" in details:
                    status = "failed"
                elif "[WARN]" in details:
                    status = "warning"
                elif "[OK]" in details or overall_ok:
                    status = "passed"
                else:
                    status = "skipped"
                summary = self._last_meaningful_line(details)
                self._update_check_locked(
                    check_id,
                    status,
                    summary or ("检查通过" if overall_ok else "未执行"),
                    details,
                )
            self._condition.notify_all()

    def _apply_model_check_output(self, output: str, ok: bool) -> None:
        details = output.strip()
        with self._condition:
            self._update_check_locked(
                "model",
                "passed" if ok else "failed",
                self._last_meaningful_line(details) or ("API 已响应" if ok else "API 检查失败"),
                details,
            )
            self._condition.notify_all()

    @staticmethod
    def _split_device_sections(output: str) -> dict[int, str]:
        sections: dict[int, list[str]] = {}
        current: int | None = None
        for line in output.splitlines():
            match = re.match(r"\[(\d)/4\]\s+", line.strip())
            if match:
                current = int(match.group(1))
                sections[current] = [line]
            elif current is not None:
                sections[current].append(line)
        return {index: "\n".join(lines) for index, lines in sections.items()}

    @staticmethod
    def _last_meaningful_line(text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        preferred = [
            line
            for line in lines
            if any(marker in line for marker in ("[OK]", "[WARN]", "[FAILED]", "Selected:"))
        ]
        return (preferred or lines or [""])[-1]

    def _update_check_locked(
        self,
        check_id: str,
        status: str,
        summary: str,
        details: str,
    ) -> None:
        for check in self.startup["checks"]:
            if check["id"] == check_id:
                check.update(status=status, summary=summary, details=details)
                return

    def start_task(self, goal: str) -> dict[str, Any]:
        normalized = str(goal or "").strip()
        if not normalized:
            raise ValueError("任务不能为空")
        if len(normalized) > 8_000:
            raise ValueError("任务文本不能超过 8000 个字符")
        with self._condition:
            if self.startup["status"] != "ready" or self._agent is None:
                raise RuntimeError("启动检查尚未通过")
            if self.task["status"] in BUSY_TASK_STATES:
                raise RuntimeError("已有任务正在执行")
            task_id = uuid4().hex
            self.task = self._empty_task()
            self.task.update(
                {
                    "id": task_id,
                    "status": "running",
                    "goal": normalized,
                    "phase": "initializing",
                    "started_at": time.time(),
                }
            )
            self.startup["reused"] = True
            self._append_event_locked(
                "web_task_started",
                "任务已提交到 PhoneAgent",
                {"goal": normalized},
                task_id=task_id,
            )
            self._task_thread = threading.Thread(
                target=self._run_task,
                args=(task_id, normalized),
                name=f"phoneagent-web-task-{task_id[:8]}",
                daemon=True,
            )
            self._task_thread.start()
            return deepcopy(self.task)

    def _run_task(self, task_id: str, goal: str) -> None:
        agent = self._agent
        if agent is None:
            return
        try:
            result = agent.run(goal)
            state = agent.state.to_dict()
            success = state.get("success") is True
            trajectory = (
                Path(agent.last_trajectory_path).name
                if agent.last_trajectory_path
                else None
            )
            with self._condition:
                if self.task["id"] != task_id:
                    return
                self.task.update(
                    {
                        "status": "success" if success else "failed",
                        "phase": state.get("phase", "completed" if success else "failed"),
                        "current_step": state.get("current_step", 0),
                        "current_app": state.get("current_app", ""),
                        "recoveries": state.get("recovery_count", 0),
                        "finished_at": state.get("finished_at") or time.time(),
                        "result": result,
                        "trajectory": trajectory,
                        "last_thinking": state.get("last_thinking", ""),
                        "last_action": state.get("last_action"),
                        "last_verification": state.get("last_verification"),
                        "last_recovery": state.get("last_recovery"),
                    }
                )
                self._append_event_locked(
                    "web_task_finished",
                    result,
                    {"success": success, "trajectory": trajectory},
                    task_id=task_id,
                )
        except Exception as exc:
            with self._condition:
                if self.task["id"] != task_id:
                    return
                self.task.update(
                    {
                        "status": "failed",
                        "phase": "failed",
                        "finished_at": time.time(),
                        "result": "任务执行发生未处理异常",
                        "error": str(exc),
                    }
                )
                self._append_event_locked(
                    "web_task_error",
                    "任务执行发生未处理异常",
                    {
                        "error": str(exc),
                        "exception_type": type(exc).__name__,
                        "traceback": traceback.format_exc(limit=8),
                    },
                    task_id=task_id,
                )
        finally:
            with self._condition:
                if self.pending_prompt and self.pending_prompt.get("task_id") == task_id:
                    self.pending_prompt = None
                    self._prompt_answered = True
                    self._prompt_response = False
                self._condition.notify_all()

    def _on_agent_event(self, event: AgentEvent) -> None:
        payload = _json_safe(event.payload)
        with self._condition:
            if self.task["status"] not in BUSY_TASK_STATES:
                return
            step = payload.get("step") if isinstance(payload, dict) else None
            if isinstance(step, int):
                self.task["current_step"] = step
            if event.type.value == "phase_change" and isinstance(payload, dict):
                self.task["phase"] = str(payload.get("current", self.task["phase"]))
            elif event.type.value == "observation" and isinstance(payload, dict):
                self.task["current_app"] = str(payload.get("current_app", ""))
            elif event.type.value == "model_response" and isinstance(payload, dict):
                self.task["last_thinking"] = str(payload.get("thinking", ""))
            elif event.type.value == "action" and isinstance(payload, dict):
                self.task["last_action"] = payload.get("action")
            elif event.type.value == "verification" and isinstance(payload, dict):
                self.task["last_verification"] = payload
            elif event.type.value == "recovery" and isinstance(payload, dict):
                self.task["last_recovery"] = payload
                if payload.get("stage") == "outcome":
                    self.task["recoveries"] += 1
            self._append_event_locked(
                event.type.value,
                event.message,
                payload,
                timestamp=event.timestamp,
                task_id=self.task["id"],
            )

    def _on_note(self, note: str) -> None:
        with self._condition:
            self._append_event_locked(
                "note",
                note,
                {},
                task_id=self.task["id"],
            )

    def _confirmation_callback(self, message: str) -> bool:
        return self._wait_for_prompt("confirmation", message)

    def _takeover_callback(self, message: str) -> None:
        self._wait_for_prompt("takeover", message)

    def _wait_for_prompt(self, prompt_type: str, message: str) -> bool:
        with self._condition:
            prompt_id = uuid4().hex
            self.pending_prompt = {
                "id": prompt_id,
                "type": prompt_type,
                "message": str(message),
                "task_id": self.task["id"],
                "created_at": time.time(),
            }
            self._prompt_answered = False
            self._prompt_response = None
            self.task["status"] = "waiting_user"
            self._append_event_locked(
                "user_prompt",
                "等待用户确认" if prompt_type == "confirmation" else "等待人工接管",
                {"prompt_type": prompt_type, "message": str(message)},
                task_id=self.task["id"],
            )
            while not self._prompt_answered and not self._closing:
                self._condition.wait()
            answer = bool(self._prompt_response)
            self.pending_prompt = None
            if self.task["status"] == "waiting_user":
                self.task["status"] = "running"
            self._append_event_locked(
                "user_response",
                "用户已确认继续" if answer else "用户拒绝了敏感操作",
                {"prompt_type": prompt_type, "accepted": answer},
                task_id=self.task["id"],
            )
            return answer

    def respond_prompt(self, prompt_id: str, accepted: bool) -> None:
        with self._condition:
            if self.pending_prompt is None or self.pending_prompt["id"] != prompt_id:
                raise ValueError("确认请求已经失效")
            if self.pending_prompt["type"] == "takeover" and not accepted:
                raise ValueError("人工接管只能在完成手机操作后继续")
            self._prompt_response = bool(accepted)
            self._prompt_answered = True
            self._condition.notify_all()

    def snapshot(self) -> dict[str, Any]:
        with self._condition:
            return _json_safe(
                {
                    "session": {
                        "started_at": self.session_started_at,
                        "server_time": time.time(),
                        "event_cursor": self._next_sequence - 1,
                    },
                    "startup": deepcopy(self.startup),
                    "task": deepcopy(self.task),
                    "pending_prompt": deepcopy(self.pending_prompt),
                    "trajectory_dir": str(self.trajectories.directory),
                }
            )

    def events_after(self, sequence: int, limit: int = 250) -> dict[str, Any]:
        with self._condition:
            events = [item for item in self._events if item["sequence"] > sequence]
            events = events[: max(1, min(limit, 500))]
            return {
                "events": deepcopy(events),
                "cursor": events[-1]["sequence"] if events else self._next_sequence - 1,
            }

    def _append_event_locked(
        self,
        event_type: str,
        message: str,
        payload: Any,
        *,
        task_id: str | None = None,
        timestamp: float | None = None,
    ) -> None:
        event = {
            "sequence": self._next_sequence,
            "timestamp": timestamp or time.time(),
            "type": event_type,
            "message": str(message or ""),
            "payload": _json_safe(payload),
            "task_id": task_id,
        }
        self._next_sequence += 1
        self._events.append(event)
        if len(self._events) > 2_000:
            del self._events[:-1_500]
        self._condition.notify_all()

    def close(self) -> None:
        with self._condition:
            self._closing = True
            if self.pending_prompt is not None:
                self._prompt_response = False
                self._prompt_answered = True
            self._condition.notify_all()
