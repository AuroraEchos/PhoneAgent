from __future__ import annotations

from phoneagent.adb import device as adb_device
from phoneagent.adb.command import ADBCommandError
from phoneagent.devices import AndroidDevice


def test_device_initialization_does_not_query_installed_apps(monkeypatch) -> None:
    def unexpected_query(_device_id=None):
        raise AssertionError("device catalog must not be queried during initialization")

    monkeypatch.setattr(adb_device, "list_installed_packages", unexpected_query)

    AndroidDevice(device_id="test-device")


def test_lazy_launch_resolves_checks_and_starts_package(monkeypatch) -> None:
    calls: list[tuple[str, str | None, float]] = []
    monkeypatch.setattr(adb_device, "is_package_installed", lambda package, device: True)
    monkeypatch.setattr(
        adb_device,
        "launch_package",
        lambda package, device, timeout: calls.append((package, device, timeout)),
    )
    device = AndroidDevice(device_id="test-device", app_launch_timeout_seconds=7.5)

    result = device.launch_app_resolved("微信")

    assert result.success is True
    assert result.package_name == "com.tencent.mm"
    assert result.display_name == "微信"
    assert result.metadata["resolved_lazily"] is True
    assert calls == [("com.tencent.mm", "test-device", 7.5)]


def test_lazy_launch_rejects_unknown_alias_without_adb(monkeypatch) -> None:
    def unexpected_check(*_args, **_kwargs):
        raise AssertionError("ADB must not be queried for an unknown alias")

    monkeypatch.setattr(adb_device, "is_package_installed", unexpected_check)

    result = AndroidDevice().launch_app_resolved("不存在的应用")

    assert result.success is False
    assert result.error_code == "app_not_found"


def test_lazy_launch_reports_uninstalled_configured_app(monkeypatch) -> None:
    monkeypatch.setattr(adb_device, "is_package_installed", lambda package, device: False)

    result = AndroidDevice().launch_app_resolved("微信")

    assert result.success is False
    assert result.error_code == "app_not_installed"
    assert result.package_name == "com.tencent.mm"


def test_lazy_launch_converts_adb_failure_to_structured_result(monkeypatch) -> None:
    monkeypatch.setattr(adb_device, "is_package_installed", lambda package, device: True)

    def fail_launch(package, device, timeout):
        raise ADBCommandError(["adb", "shell", "monkey"], reason="test failure")

    monkeypatch.setattr(adb_device, "launch_package", fail_launch)

    result = AndroidDevice().launch_app_resolved("微信")

    assert result.success is False
    assert result.error_code == "app_launch_failed"
    assert result.metadata["exception_type"] == "ADBCommandError"


def test_list_launchable_apps_is_configured_installed_intersection(monkeypatch) -> None:
    monkeypatch.setattr(
        adb_device,
        "list_installed_packages",
        lambda device: {"com.tencent.mm", "com.example.unconfigured"},
    )

    apps = AndroidDevice(device_id="test-device").list_launchable_apps()

    assert [(app.display_name, app.package_name) for app in apps] == [("微信", "com.tencent.mm")]
