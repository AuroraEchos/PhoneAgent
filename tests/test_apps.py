from __future__ import annotations

import unittest

from phoneagent.apps import (
    AppCatalog,
    AppCatalogConfig,
    AppDiscovery,
    AppResolver,
    InstalledApp,
    extract_pure_launch_intent,
    normalize_app_name,
)


class _Discovery:
    def __init__(self, apps: list[InstalledApp]):
        self.apps = apps
        self.calls = 0

    def list_launchable_apps(self) -> list[InstalledApp]:
        self.calls += 1
        return list(self.apps)


class AppCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.apps = [
            InstalledApp("微信", "com.tencent.mm", ".ui.LauncherUI", aliases=("WeChat",)),
            InstalledApp("企业微信", "com.tencent.wework", ".launch.LaunchSplashActivity"),
        ]

    def test_normalization_preserves_chinese(self) -> None:
        self.assertEqual(normalize_app_name(" 企-业 微_信 "), "企业微信")

    def test_resolution_prefers_exact_alias(self) -> None:
        resolution = AppResolver().resolve("WeChat", self.apps)
        self.assertTrue(resolution.matched)
        self.assertEqual(resolution.matched_app.package_name, "com.tencent.mm")

    def test_catalog_cache_and_prompt_context(self) -> None:
        discovery = _Discovery(self.apps)
        catalog = AppCatalog(
            discovery,  # type: ignore[arg-type]
            config=AppCatalogConfig(ttl_seconds=3600, max_prompt_matches=2),
        )
        self.assertEqual(len(catalog.ensure_loaded()), 2)
        self.assertEqual(discovery.calls, 1)
        context = catalog.build_prompt_context("打开微信")
        self.assertEqual(context["likely_goal_apps"][0]["query"], "微信")
        self.assertEqual(discovery.calls, 1)

    def test_discovery_parsers_remain_available(self) -> None:
        components = AppDiscovery.parse_launcher_components(
            "com.tencent.mm/.ui.LauncherUI\ncom.tencent.mm/.ui.LauncherUI"
        )
        self.assertEqual(components, [("com.tencent.mm", ".ui.LauncherUI")])

    def test_pure_launch_classifier_is_conservative(self) -> None:
        intent = extract_pure_launch_intent("打开微信")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.query, "微信")
        self.assertIsNone(extract_pure_launch_intent("打开微信，然后搜索联系人"))


if __name__ == "__main__":
    unittest.main()
