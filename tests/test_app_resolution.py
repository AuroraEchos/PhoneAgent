from __future__ import annotations

from phoneagent.config.apps import (
    get_canonical_app_name,
    get_package_name,
    infer_task_entry_app,
    list_canonical_app_mapping,
)


def test_chinese_settings_alias_is_supported() -> None:
    assert get_package_name("设置") == "com.android.settings"
    assert get_package_name("系统设置") == "com.android.settings"


def test_alias_lookup_is_case_and_whitespace_tolerant() -> None:
    assert get_package_name("  WE CHAT ") == "com.tencent.mm"
    assert get_package_name("瑞幸 咖啡") == "com.lucky.luckyclient"


def test_raw_android_package_is_accepted() -> None:
    assert get_package_name("com.example.custom_app") == "com.example.custom_app"


def test_unknown_human_name_is_not_guessed() -> None:
    assert get_package_name("微信助手") is None


def test_first_alias_is_the_canonical_display_name() -> None:
    assert get_canonical_app_name("com.tencent.mm") == "微信"
    assert get_canonical_app_name("com.example.unknown") is None


def test_canonical_mapping_returns_an_independent_copy() -> None:
    mapping = list_canonical_app_mapping()
    mapping["com.tencent.mm"] = "changed"

    assert get_canonical_app_name("com.tencent.mm") == "微信"


def test_explicit_launch_task_resolves_entry_app() -> None:
    target = infer_task_entry_app("打开微信给张三发消息")

    assert target is not None
    assert target.app_name == "微信"
    assert target.package_name == "com.tencent.mm"
    assert target.evidence == "launch_verb"


def test_nested_mini_program_task_uses_container_app() -> None:
    target = infer_task_entry_app("打开微信中的美团小程序，看看最近的订单")

    assert target is not None
    assert target.app_name == "微信"
    assert target.package_name == "com.tencent.mm"


def test_compact_mini_program_name_prefers_known_container() -> None:
    target = infer_task_entry_app("打开美团微信小程序")

    assert target is not None
    assert target.app_name == "微信"


def test_operation_container_beats_nested_mini_program_name() -> None:
    target = infer_task_entry_app("请在微信里打开美团小程序")

    assert target is not None
    assert target.app_name == "微信"


def test_operation_container_resolves_entry_app() -> None:
    target = infer_task_entry_app("请在支付宝里查看账单")

    assert target is not None
    assert target.app_name == "支付宝"


def test_app_alias_mention_without_launch_intent_is_not_forced() -> None:
    assert infer_task_entry_app("设置晚上八点的闹钟") is None
    assert infer_task_entry_app("比较微信和 QQ 的隐私政策") is None


def test_negated_app_is_not_selected_over_requested_app() -> None:
    target = infer_task_entry_app("不要打开微信，打开 QQ")

    assert target is not None
    assert target.app_name == "QQ"
