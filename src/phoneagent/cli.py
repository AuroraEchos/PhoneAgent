#!/usr/bin/env python3
"""PhoneAgent command-line interface."""

from __future__ import annotations

import argparse
import os
import shutil
import sys

from phoneagent import __version__, AgentConfig, PhoneAgent
from phoneagent.adb import (
    ADBConnection,
    ADB_KEYBOARD_IME,
    get_current_input_method,
    is_adb_keyboard_installed,
)
from phoneagent.adb.command import run_adb
from phoneagent.adb.screenshot import ScreenshotCaptureError, get_screenshot
from phoneagent.apps import AppCatalogConfig, AppDiscoveryConfig, AppLauncherConfig
from phoneagent.config.apps import list_supported_apps
from phoneagent.devices import AndroidDevice
from phoneagent.model import ModelConfig
from phoneagent.runtime import RecoveryConfig, VerificationConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PhoneAgent - Android vision-language phone automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  phoneagent "打开设置并查看 Wi-Fi 页面"
  phoneagent --device-id emulator-5554 "打开浏览器搜索 LangGraph"
  phoneagent --connect 192.168.1.100:5555
  phoneagent --enable-tcpip 5555
  phoneagent --list-devices
  phoneagent --list-apps --device-id emulator-5554
        """,
    )
    parser.add_argument("task", nargs="?", help="Task; omit for interactive mode")
    parser.add_argument("--version", action="version", version=f"PhoneAgent {__version__}")
    parser.add_argument(
        "--base-url",
        default=os.getenv("PHONE_AGENT_BASE_URL", "http://localhost:8000/v1"),
        help="OpenAI-compatible API base URL",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("PHONE_AGENT_MODEL", "autoglm-phone-9b"),
        help="Model name",
    )
    parser.add_argument(
        "--apikey",
        default=os.getenv("PHONE_AGENT_API_KEY", "EMPTY"),
        help="Model API key",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=int(os.getenv("PHONE_AGENT_MAX_STEPS", "100")),
    )
    parser.add_argument(
        "--max-runtime-seconds",
        type=float,
        default=float(os.getenv("PHONE_AGENT_MAX_RUNTIME_SECONDS", "900")),
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=int(os.getenv("PHONE_AGENT_MAX_TOKENS", "3000")),
    )
    parser.add_argument(
        "--max-consecutive-failures",
        type=int,
        default=int(os.getenv("PHONE_AGENT_MAX_FAILURES", "3")),
    )
    parser.add_argument(
        "--max-repeated-actions",
        type=int,
        default=int(os.getenv("PHONE_AGENT_MAX_REPEATED_ACTIONS", "3")),
    )
    parser.add_argument(
        "--context-turns",
        type=int,
        default=int(os.getenv("PHONE_AGENT_CONTEXT_TURNS", "12")),
    )
    parser.add_argument(
        "--model-retries",
        type=int,
        default=int(os.getenv("PHONE_AGENT_MODEL_RETRIES", "2")),
    )
    parser.add_argument(
        "--observation-retries",
        type=int,
        default=int(os.getenv("PHONE_AGENT_OBSERVATION_RETRIES", "2")),
    )
    parser.add_argument(
        "--disable-verification",
        action="store_true",
        help="Disable post-action verification (diagnostic only)",
    )
    parser.add_argument(
        "--verification-retries",
        type=int,
        default=int(os.getenv("PHONE_AGENT_VERIFICATION_RETRIES", "1")),
    )
    parser.add_argument(
        "--verification-threshold",
        type=float,
        default=float(os.getenv("PHONE_AGENT_VERIFICATION_THRESHOLD", "0.002")),
        help="Minimum normalized visual difference treated as a screen change",
    )
    parser.add_argument(
        "--disable-recovery",
        action="store_true",
        help="Disable automatic recovery and abort on the first recoverable failure",
    )
    parser.add_argument(
        "--max-recoveries",
        type=int,
        default=int(os.getenv("PHONE_AGENT_MAX_RECOVERIES", "8")),
    )
    parser.add_argument(
        "--recovery-attempts-per-failure",
        type=int,
        default=int(os.getenv("PHONE_AGENT_RECOVERY_ATTEMPTS", "2")),
    )
    parser.add_argument(
        "--enable-backtrack-recovery",
        action="store_true",
        help="Allow one automatic Back action after repeated navigation failures",
    )
    parser.add_argument(
        "--enable-home-reset-recovery",
        action="store_true",
        help="Allow returning to Home after repeated failures (off by default)",
    )
    parser.add_argument(
        "--disable-app-awareness",
        action="store_true",
        help="Disable dynamic installed-app discovery and model app context",
    )
    parser.add_argument(
        "--app-aliases-file",
        default=os.getenv("PHONE_AGENT_APP_ALIASES_FILE"),
        help="Optional JSON file containing user app aliases",
    )
    parser.add_argument(
        "--app-catalog-ttl",
        type=float,
        default=float(os.getenv("PHONE_AGENT_APP_CATALOG_TTL", "300")),
    )
    parser.add_argument(
        "--app-prompt-limit",
        type=int,
        default=int(os.getenv("PHONE_AGENT_APP_PROMPT_LIMIT", "5")),
        help="Maximum task-relevant application candidates injected per query",
    )
    parser.add_argument(
        "--max-app-context-chars",
        type=int,
        default=int(os.getenv("PHONE_AGENT_MAX_APP_CONTEXT_CHARS", "6000")),
        help="Hard character budget for Device App Context",
    )
    parser.add_argument(
        "--disable-deterministic-launch",
        action="store_true",
        help="Route pure app-open tasks through the VLM instead of direct package launch",
    )
    parser.add_argument(
        "--disable-strict-action-recovery",
        action="store_true",
        help="Disable compact strict-action retry after malformed/truncated model output",
    )
    parser.add_argument(
        "--disable-launcher-search-fallback",
        action="store_true",
        help="Do not open Launcher search when no package match is found",
    )
    parser.add_argument(
        "--trajectory-dir",
        default=os.getenv("PHONE_AGENT_TRAJECTORY_DIR", "runs"),
    )
    parser.add_argument(
        "--device-id",
        "-d",
        default=os.getenv("PHONE_AGENT_DEVICE_ID"),
        help="ADB device id for multi-device setups",
    )
    parser.add_argument("--connect", "-c", metavar="ADDRESS")
    parser.add_argument(
        "--disconnect",
        nargs="?",
        const="all",
        metavar="ADDRESS",
    )
    parser.add_argument(
        "--enable-tcpip",
        type=int,
        nargs="?",
        const=5555,
        metavar="PORT",
    )
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument(
        "--list-apps",
        action="store_true",
        help="List launchable apps dynamically discovered on the selected device",
    )
    parser.add_argument(
        "--list-configured-apps",
        action="store_true",
        help="List built-in compatibility aliases without querying a device",
    )
    parser.add_argument("--skip-system-check", action="store_true")
    parser.add_argument("--skip-model-check", action="store_true")
    parser.add_argument(
        "--allow-fallback-screenshot",
        action="store_true",
        help="Diagnostic only: permit unavailable screenshots to be represented by a marked fallback",
    )
    parser.add_argument("--quiet", "-q", action="store_true")
    return parser.parse_args()


def check_system_requirements(device_id: str | None = None) -> tuple[bool, str | None]:
    print("\n" + "=" * 64)
    print("Android / ADB Environment Check")
    print("=" * 64)

    adb_path = shutil.which("adb")
    print("\n[1/4] ADB executable")
    if adb_path is None:
        print("  [FAILED] adb was not found in PATH")
        print("  Ubuntu: sudo apt install android-tools-adb")
        return False, None
    try:
        result = run_adb(["version"], adb_path=adb_path, timeout=10)
        first_line = (result.stdout or "").splitlines()[0]
        print(f"  [OK] {first_line}")
        print(f"  Path: {adb_path}")
    except Exception as exc:
        print(f"  [FAILED] {exc}")
        return False, None

    print("\n[2/4] Connected device")
    conn = ADBConnection(adb_path=adb_path)
    devices = conn.list_devices()
    ready = [device for device in devices if device.status == "device"]
    for device in devices:
        marker = "OK" if device.status == "device" else "WARN"
        model = f" model={device.model}" if device.model else ""
        print(f"  [{marker}] {device.device_id} state={device.status}{model}")

    if device_id:
        selected = next(
            (device.device_id for device in ready if device.device_id == device_id),
            None,
        )
        if selected is None:
            print(f"  [FAILED] Device {device_id!r} is absent or not ready")
            return False, None
    else:
        if not ready:
            print("  [FAILED] No authorized device in `device` state")
            return False, None
        if len(ready) > 1:
            print("  [FAILED] Multiple ready devices; use --device-id")
            return False, None
        selected = ready[0].device_id
    print(f"  Selected: {selected}")

    print("\n[3/4] Text input method")
    try:
        installed = is_adb_keyboard_installed(selected)
        current = get_current_input_method(selected)
        if installed:
            print("  [OK] ADB Keyboard is installed")
        else:
            print("  [WARN] ADB Keyboard is not installed; Type actions will fail")
        if current == ADB_KEYBOARD_IME:
            print("  [OK] ADB Keyboard is active")
        else:
            print(f"  [INFO] Current IME: {current or '<unknown>'}")
            if installed:
                print("  PhoneAgent will switch to ADB Keyboard before typing")
    except Exception as exc:
        print(f"  [WARN] Could not inspect keyboard state: {exc}")

    print("\n[4/4] Visual observation")
    try:
        screenshot = get_screenshot(selected, allow_fallback=False)
        print(
            f"  [OK] screenshot={screenshot.display_width}x{screenshot.display_height} "
            f"encoded={screenshot.width}x{screenshot.height}"
        )
        if screenshot.is_blank:
            print("  [FAILED] Screenshot is uniformly black/protected")
            return False, None
    except ScreenshotCaptureError as exc:
        print(f"  [FAILED] {exc}")
        return False, None

    print("\n[PASSED] Device is ready for PhoneAgent")
    print("=" * 64 + "\n")
    return True, selected


def check_model_api(config: ModelConfig) -> bool:
    print("\n" + "=" * 64)
    print("Model API Check")
    print("=" * 64)
    print(f"  Base URL: {config.base_url}")
    print(f"  Model:    {config.model_name}")
    try:
        from openai import OpenAI, DefaultHttpxClient

        client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=min(config.timeout, 30.0),
            http_client=DefaultHttpxClient(trust_env=False)
        )
        response = client.chat.completions.create(
            model=config.model_name,
            messages=[{"role": "user", "content": "Reply with OK."}],
            max_tokens=8,
            temperature=0.0,
            stream=False,
        )
        if not response.choices:
            print("  [FAILED] API returned no choices")
            return False
        print("  [OK] API responded")
        print("=" * 64 + "\n")
        return True
    except Exception as exc:
        print(f"  [FAILED] {exc}")
        print("=" * 64 + "\n")
        return False


def handle_device_commands(args: argparse.Namespace) -> int | None:
    conn = ADBConnection()
    if args.connect:
        ok, message = conn.connect(args.connect)
        print(f"[{'OK' if ok else 'FAILED'}] {message}")
        return 0 if ok else 1
    if args.disconnect:
        address = None if args.disconnect == "all" else args.disconnect
        ok, message = conn.disconnect(address)
        print(f"[{'OK' if ok else 'FAILED'}] {message}")
        return 0 if ok else 1
    if args.enable_tcpip is not None:
        ok, message = conn.enable_tcpip(args.enable_tcpip, args.device_id)
        print(f"[{'OK' if ok else 'FAILED'}] {message}")
        if ok:
            ip = conn.get_device_ip(args.device_id)
            if ip:
                print(f"Connect later with: phoneagent --connect {ip}:{args.enable_tcpip}")
        return 0 if ok else 1
    if args.list_devices:
        devices = conn.list_devices()
        if not devices:
            print("No ADB devices detected")
            return 1
        for device in devices:
            print(
                f"{device.device_id}\t{device.status}\t"
                f"{device.connection_type.value}\t{device.model or ''}"
            )
        return 0
    return None


def print_configured_apps() -> None:
    for app in sorted(set(list_supported_apps()), key=str.casefold):
        print(app)



def _select_ready_device(device_id: str | None) -> str | None:
    conn = ADBConnection()
    ready = [item for item in conn.list_devices() if item.status == "device"]
    if device_id:
        return device_id if any(item.device_id == device_id for item in ready) else None
    if len(ready) == 1:
        return ready[0].device_id
    return None


def print_device_apps(device_id: str | None) -> int:
    selected = _select_ready_device(device_id)
    if selected is None:
        print(
            "Unable to select one ready Android device. Connect a device or pass --device-id.",
            file=sys.stderr,
        )
        return 1
    try:
        device = AndroidDevice(device_id=selected)
        apps = device.list_launchable_apps(refresh=True)
    except Exception as exc:
        print(f"Failed to discover device applications: {exc}", file=sys.stderr)
        return 1
    if not apps:
        print("No launchable applications were discovered", file=sys.stderr)
        return 1
    print(f"Device: {selected}")
    print(f"Launchable apps: {len(apps)}")
    print("LABEL\tPACKAGE\tACTIVITY\tLABEL_SOURCE")
    for app in apps:
        print(
            f"{app.label}\t{app.package_name}\t"
            f"{app.activity_name or ''}\t{app.label_source}"
        )
    return 0

def run_interactive(agent: PhoneAgent) -> None:
    print("PhoneAgent interactive mode. Type exit/quit/q to stop.\n")
    while True:
        try:
            task = input("Task> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return
        if not task:
            continue
        if task.casefold() in {"exit", "quit", "q"}:
            print("Bye.")
            return
        result = agent.run(task)
        status = "SUCCESS" if agent.state.success else "FAILED"
        print(
            f"\n[{status}] {result} "
            f"(phase={agent.state.phase.value}, recoveries={agent.state.recovery_count})"
        )
        if agent.last_trajectory_path:
            print(f"Trajectory: {agent.last_trajectory_path}")
        print()


def main() -> int:
    args = parse_args()
    if args.list_configured_apps:
        print_configured_apps()
        return 0
    if args.list_apps:
        return print_device_apps(args.device_id)

    command_status = handle_device_commands(args)
    if command_status is not None:
        return command_status

    try:
        model_config = ModelConfig(
            base_url=args.base_url,
            api_key=args.apikey,
            model_name=args.model,
            max_tokens=args.max_tokens,
            max_retries=args.model_retries,
        )
        agent_config = AgentConfig(
            max_steps=args.max_steps,
            max_runtime_seconds=args.max_runtime_seconds,
            max_consecutive_failures=args.max_consecutive_failures,
            max_repeated_actions=args.max_repeated_actions,
            context_turns=args.context_turns,
            observation_retries=args.observation_retries,
            device_id=args.device_id,
            verbose=not args.quiet,
            trajectory_dir=args.trajectory_dir,
            allow_fallback_screenshot=args.allow_fallback_screenshot,
            app_awareness_enabled=not args.disable_app_awareness,
            inject_app_context=not args.disable_app_awareness,
            deterministic_pure_launch_enabled=not args.disable_deterministic_launch,
            strict_action_recovery_enabled=not args.disable_strict_action_recovery,
            max_app_context_chars=args.max_app_context_chars,
            app_catalog=AppCatalogConfig(
                ttl_seconds=args.app_catalog_ttl,
                max_prompt_matches=args.app_prompt_limit,
            ),
            app_discovery=AppDiscoveryConfig(
                alias_file=args.app_aliases_file,
            ),
            app_launcher=AppLauncherConfig(
                enable_launcher_search_fallback=(
                    not args.disable_launcher_search_fallback
                ),
            ),
            verification=VerificationConfig(
                enabled=not args.disable_verification,
                observation_retries=args.verification_retries,
                visual_change_threshold=args.verification_threshold,
            ),
            recovery=RecoveryConfig(
                enabled=not args.disable_recovery,
                max_total_recoveries=args.max_recoveries,
                max_attempts_per_failure=args.recovery_attempts_per_failure,
                allow_backtrack=args.enable_backtrack_recovery,
                allow_home_reset=args.enable_home_reset_recovery,
            ),
        )
    except ValueError as exc:
        print(f"Invalid configuration: {exc}", file=sys.stderr)
        return 2

    resolved_device_id = args.device_id
    if not args.skip_system_check:
        ok, resolved_device_id = check_system_requirements(args.device_id)
        if not ok:
            return 1
        agent_config.device_id = resolved_device_id
    if not args.skip_model_check and not check_model_api(model_config):
        return 1

    agent = PhoneAgent(model_config=model_config, agent_config=agent_config)
    if args.task:
        print(f"\nStarting task: {args.task}\n")
        result = agent.run(args.task)
        status = "SUCCESS" if agent.state.success else "FAILED"
        print(
            f"\n[{status}] {result} "
            f"(phase={agent.state.phase.value}, recoveries={agent.state.recovery_count})"
        )
        if agent.last_trajectory_path:
            print(f"Trajectory: {agent.last_trajectory_path}")
        return 0 if agent.state.success else 3

    run_interactive(agent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
