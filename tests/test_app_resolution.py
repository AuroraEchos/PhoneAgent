from __future__ import annotations

from phoneagent.apps import AppMatchType, AppResolver, InstalledApp, extract_pure_launch_intent
from phoneagent.config.apps import get_package_name


def test_chinese_settings_alias_is_supported() -> None:
    assert get_package_name("设置") == "com.android.settings"
    assert get_package_name("系统设置") == "com.android.settings"


def test_resolver_prefers_exact_alias() -> None:
    apps = [
        InstalledApp(
            label="Settings",
            package_name="com.android.settings",
            aliases=("设置", "系统设置"),
        ),
        InstalledApp(label="WeChat", package_name="com.tencent.mm", aliases=("微信",)),
    ]
    result = AppResolver().resolve("设置", apps)
    assert result.matched
    assert result.matched_app is not None
    assert result.matched_app.package_name == "com.android.settings"
    assert result.match_type is AppMatchType.ALIAS_EXACT


def test_pure_launch_intent_is_conservative() -> None:
    intent = extract_pure_launch_intent("打开微信")
    assert intent is not None
    assert intent.query == "微信"
    assert extract_pure_launch_intent("打开微信，然后搜索张三") is None
