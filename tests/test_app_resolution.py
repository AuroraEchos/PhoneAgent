from __future__ import annotations

from phoneagent.config.apps import (
    get_canonical_app_name,
    get_package_name,
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
