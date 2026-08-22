from __future__ import annotations

import threading

import pytest

from phoneagent.actions import ActionHandler, ActionParseError, do, finish, parse_action
from phoneagent.actions.policy import (
    action_needs_task_risk_review,
    confirmation_message,
    parse_duration_seconds,
    task_has_negative_boundary,
    task_risk_reasons,
    task_scope_violation_message,
)
from phoneagent.adb.device import _extract_system_panel_state
from phoneagent.devices import SystemPanelCommandResult


def test_parse_tap_action() -> None:
    action = parse_action('do(action="Tap", element=[500, 250])')
    assert action == {"_metadata": "do", "action": "Tap", "element": [500, 250]}


@pytest.mark.parametrize(
    ("text", "canonical"),
    [
        ('do(action="OpenNotifications")', "OpenNotifications"),
        ('do(action="open_quick_settings")', "OpenQuickSettings"),
        ('do(action="close-system-panel")', "CloseSystemPanel"),
    ],
)
def test_parse_system_panel_actions(text: str, canonical: str) -> None:
    assert parse_action(text)["action"] == canonical


def test_parser_rejects_json_action() -> None:
    with pytest.raises(ActionParseError):
        parse_action('{"type":"finish","message":"done","success":true}')


def test_parser_rejects_executable_python() -> None:
    with pytest.raises(ActionParseError):
        parse_action('do(action="Tap", element=__import__("os").system("id"))')


def test_coordinate_scaling_is_bounded() -> None:
    assert ActionHandler._relative_to_absolute([0, 0], 1080, 2400) == (0, 0)
    assert ActionHandler._relative_to_absolute([999, 999], 1080, 2400) == (1079, 2399)
    assert ActionHandler._relative_to_absolute([500, 500], 1080, 2400) == (540, 1201)


def test_wait_action_is_cancelled_without_waiting_for_full_duration() -> None:
    cancel_event = threading.Event()
    handler = ActionHandler(object(), cancel_event=cancel_event)  # type: ignore[arg-type]
    results = []
    thread = threading.Thread(
        target=lambda: results.append(
            handler.execute(do(action="Wait", duration="10 seconds"), 1, 1)
        )
    )
    thread.start()
    cancel_event.set()
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert results[0].error_code == "user_cancelled"


def test_type_keeps_test_keyboard_for_task_then_restores_original_input_method() -> None:
    class Device:
        def __init__(self) -> None:
            self.prepared = 0
            self.typed: list[str] = []
            self.restored: list[str] = []

        def detect_and_set_adb_keyboard(self) -> str:
            self.prepared += 1
            return "original/.Ime"

        def type_text(self, value: str) -> None:
            self.typed.append(value)

        def restore_keyboard(self, ime: str) -> None:
            self.restored.append(ime)

    device = Device()
    handler = ActionHandler(device)  # type: ignore[arg-type]

    first = handler.execute(do(action="Type", text="first"), 1080, 2400)
    second = handler.execute(do(action="Type", text="second"), 1080, 2400)

    assert first.success is True
    assert second.success is True
    assert device.prepared == 1
    assert device.typed == ["first", "second"]
    assert device.restored == []
    assert handler.restore_input_method() is None
    assert device.restored == ["original/.Ime"]
    assert handler.restore_input_method() is None
    assert device.restored == ["original/.Ime"]


@pytest.mark.parametrize(
    ("action", "expected_fragment"),
    [
        ({"sensitive": True, "message": "确认发送"}, "确认发送"),
        ({"requires_confirmation": True}, "marked as sensitive"),
        ({"risk_level": "high", "description": "修改账号"}, "修改账号"),
        ({"description": "place order now"}, "Sensitive operation detected"),
        ({"label": "删除联系人"}, "Sensitive operation detected"),
        ({"description": "点击保存按钮"}, "Sensitive operation detected"),
    ],
)
def test_confirmation_policy_is_independent_from_device_execution(
    action: dict,
    expected_fragment: str,
) -> None:
    assert expected_fragment in str(confirmation_message(action))


def test_confirmation_policy_allows_unmarked_navigation() -> None:
    assert confirmation_message({"action": "Tap", "description": "打开设置"}) is None


def test_task_aware_policy_does_not_depend_on_model_sensitive_flag() -> None:
    action = {"_metadata": "do", "action": "Tap", "element": [500, 500]}
    task = "从银行卡转账100元给张三"

    assert task_risk_reasons(task) == ("financial_or_commercial",)
    assert action_needs_task_risk_review(action, task) is True
    assert "Task-aware confirmation" in str(confirmation_message(action, task=task))
    assert confirmation_message(action, task=task, task_risk_checked=True) is None


def test_explicit_negative_boundary_independently_triggers_coordinate_review() -> None:
    action = {"_metadata": "do", "action": "Tap", "element": [500, 500]}
    task = "输入消息，停留在发送前，不要发送"

    assert task_risk_reasons(task) == ()
    assert task_has_negative_boundary(task) is True
    assert action_needs_task_risk_review(action, task) is True
    assert "explicit negative task boundary" in str(
        confirmation_message(action, task=task)
    )
    assert confirmation_message(action, task=task, task_risk_checked=True) is None


@pytest.mark.parametrize(
    "task",
    [
        "把手机的自动锁屏时间修改为10分钟",
        "修改屏幕亮度",
        "把音量调到50%",
        "给张三发送消息",
        "删除一张测试照片",
        "预约明天的会议",
    ],
)
def test_ordinary_tasks_do_not_trigger_task_risk_review(task: str) -> None:
    action = {"_metadata": "do", "action": "Tap", "element": [500, 500]}

    assert task_risk_reasons(task) == ()
    assert action_needs_task_risk_review(action, task) is False


@pytest.mark.parametrize(
    ("task", "expected"),
    [
        ("支付100元", ("financial_or_commercial",)),
        ("从银行卡转账100元", ("financial_or_commercial",)),
        ("购买一张机票", ("financial_or_commercial",)),
        ("修改银行卡登录密码", ("credential_or_account_security",)),
        ("输入短信验证码", ("credential_or_account_security",)),
        ("删除银行账户", ("credential_or_account_security",)),
    ],
)
def test_only_high_consequence_tasks_trigger_task_risk_review(
    task: str,
    expected: tuple[str, ...],
) -> None:
    assert task_risk_reasons(task) == expected


def test_application_name_alone_is_not_treated_as_payment_authorization() -> None:
    assert task_risk_reasons("打开支付宝") == ()
    assert task_risk_reasons("打开招商银行") == ()
    assert confirmation_message({"action": "Tap", "description": "打开支付宝"}) is None


def test_explicit_negative_task_boundary_blocks_described_final_action() -> None:
    action = {
        "_metadata": "do",
        "action": "Tap",
        "element": [800, 900],
        "description": "点击发送按钮",
    }
    task = "输入消息，停留在发送前，不要发送"

    assert task_has_negative_boundary(task) is True
    assert "explicit user boundary" in str(task_scope_violation_message(action, task))


def test_explicit_negative_task_boundary_blocks_described_api_side_effect() -> None:
    action = do(action="Call_API", instruction="发送消息")
    task = "准备好消息内容，但不要发送"

    assert "explicit user boundary" in str(task_scope_violation_message(action, task))


@pytest.mark.parametrize(
    "action",
    [
        finish(message="已输入但未发送", success=True),
        do(action="Note", message="记录：不要发送"),
        do(action="Take_over", message="请检查但不要发送"),
    ],
)
def test_task_boundary_scope_check_ignores_terminal_and_message_only_actions(
    action: dict,
) -> None:
    task = "输入消息，停留在发送前，不要发送"

    assert task_scope_violation_message(action, task) is None


@pytest.mark.parametrize(
    ("duration", "seconds"),
    [
        (True, 1.0),
        (-2, 0.0),
        (1.5, 1.5),
        ("250 ms", 0.25),
        ("2 minutes", 120.0),
        ("稍等片刻", 1.0),
    ],
)
def test_wait_duration_policy_normalizes_supported_units(duration, seconds: float) -> None:
    assert parse_duration_seconds(duration) == pytest.approx(seconds)


def test_system_panel_action_uses_semantic_device_command() -> None:
    class Device:
        def open_notifications(self) -> SystemPanelCommandResult:
            return SystemPanelCommandResult(
                target="notifications",
                command="expand-notifications",
                success=True,
                returncode=0,
                message="requested",
            )

    result = ActionHandler(Device()).execute(  # type: ignore[arg-type]
        do(action="OpenNotifications"), 1080, 2400
    )

    assert result.success is True
    assert result.metadata["system_panel"]["transport"] == "cmd_statusbar"
    assert result.metadata["system_panel"]["command"] == "expand-notifications"


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (
            "mCurrentFocus=Window{abc u0 NotificationShade type=2040 }",
            (True, "notificationshade"),
        ),
        (
            "mCurrentFocus=Window{abc u0 com.example/.MainActivity type=1 }\n"
            "Window #6 Window{def u0 NotificationShade type=2040 }:\n"
            "  mHasSurface=false\n  isVisible=false",
            (False, "notificationshade"),
        ),
        (
            "mCurrentFocus=Window{abc u0 com.example/.MainActivity type=1 }",
            (None, None),
        ),
    ],
)
def test_system_panel_visibility_uses_window_state(output, expected) -> None:
    assert _extract_system_panel_state(output) == expected
