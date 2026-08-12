#!/usr/bin/env python3
"""PhoneAgent command-line interface."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple, Union

from phoneagent import __version__, AgentConfig, PhoneAgent
from phoneagent.adb import (
    ADBConnection,
    ADB_KEYBOARD_IME,
    get_current_input_method,
    is_adb_keyboard_installed,
)
from phoneagent.adb.command import ADBCommandError, run_adb
from phoneagent.adb.screenshot import ScreenshotCaptureError, get_screenshot
from phoneagent.config.apps import list_supported_apps
from phoneagent.devices import AndroidDevice
from phoneagent.model import ModelConfig
from phoneagent.runtime import RecoveryConfig, VerificationConfig

# ============================================================================
# Logging Setup
# ============================================================================

logger = logging.getLogger(__name__)

# Configure root logger for CLI
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


# ============================================================================
# Constants
# ============================================================================

DEFAULT_MAX_STEPS = 100
DEFAULT_MAX_RUNTIME_SECONDS = 900
DEFAULT_MAX_TOKENS = 2048
DEFAULT_MAX_CONSECUTIVE_FAILURES = 3
DEFAULT_MAX_REPEATED_ACTIONS = 3
DEFAULT_CONTEXT_TURNS = 12
DEFAULT_MODEL_RETRIES = 2
DEFAULT_OBSERVATION_RETRIES = 2
DEFAULT_APP_LAUNCH_TIMEOUT_SECONDS = 15
DEFAULT_VERIFICATION_RETRIES = 1
DEFAULT_VERIFICATION_THRESHOLD = 0.002
DEFAULT_MAX_RECOVERIES = 8
DEFAULT_RECOVERY_ATTEMPTS_PER_FAILURE = 2
DEFAULT_TRAJECTORY_DIR = "runs"
DEFAULT_TCPIP_PORT = 5555

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_CONFIG_ERROR = 2
EXIT_TASK_FAILURE = 3


# ============================================================================
# Enums and Data Classes
# ============================================================================

class ExitCode(Enum):
    """Standard exit codes for the CLI."""
    SUCCESS = EXIT_SUCCESS
    FAILURE = EXIT_FAILURE
    CONFIG_ERROR = EXIT_CONFIG_ERROR
    TASK_FAILURE = EXIT_TASK_FAILURE


@dataclass
class CLIConfig:
    """Aggregated configuration from CLI arguments."""
    model: ModelConfig
    agent: AgentConfig
    device_id: Optional[str]
    task: Optional[str]
    skip_system_check: bool
    skip_model_check: bool
    quiet: bool


# ============================================================================
# Main CLI Entry Point
# ============================================================================

def main() -> int:
    """Main entry point for PhoneAgent CLI."""
    try:
        args = parse_args()

        # Handle command-only operations
        if args.list_configured_apps:
            _print_configured_apps()
            return ExitCode.SUCCESS.value

        if args.list_apps:
            return _list_device_apps(args.device_id)

        # Handle device management commands
        result = _handle_device_commands(args)
        if result is not None:
            return result

        # Main agent execution
        cli_config = _build_cli_config(args)
        return _run_agent(cli_config)

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        return ExitCode.FAILURE.value
    except Exception as exc:
        logger.exception("Unexpected error")
        print(f"\n[ERROR] Unexpected error: {exc}", file=sys.stderr)
        return ExitCode.FAILURE.value


# ============================================================================
# Argument Parsing
# ============================================================================

def _parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="PhoneAgent - Android vision-language phone automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  phoneagent "打开美团下单一杯咖啡"
  phoneagent --device-id emulator-5554 "打开浏览器搜索 LangGraph"
  phoneagent --connect 192.168.1.100:5555
  phoneagent --enable-tcpip 5555
  phoneagent --list-devices
  phoneagent --list-apps --device-id emulator-5554
        """,
    )

    # Main argument
    parser.add_argument(
        "task",
        nargs="?",
        help="Task to execute; omit for interactive mode"
    )

    # Version
    parser.add_argument(
        "--version",
        action="version",
        version=f"PhoneAgent {__version__}"
    )

    # Model configuration
    model_group = parser.add_argument_group("Model Configuration")
    model_group.add_argument(
        "--base-url",
        default=os.getenv("BASE_URL"),
        help="OpenAI-compatible API base URL (required)"
    )
    model_group.add_argument(
        "--model",
        default=os.getenv("MODEL"),
        help="Model name (required)"
    )
    model_group.add_argument(
        "--apikey",
        default=os.getenv("API_KEY"),
        help="Model API key (required)"
    )
    model_group.add_argument(
        "--max-tokens",
        type=int,
        default=int(os.getenv("MAX_TOKENS", str(DEFAULT_MAX_TOKENS))),
        help=f"Maximum tokens for model responses (default: {DEFAULT_MAX_TOKENS})"
    )
    model_group.add_argument(
        "--model-retries",
        type=int,
        default=int(os.getenv("MODEL_RETRIES", str(DEFAULT_MODEL_RETRIES))),
        help=argparse.SUPPRESS
    )

    # Agent configuration
    agent_group = parser.add_argument_group("Agent Configuration")
    agent_group.add_argument(
        "--max-steps",
        type=int,
        default=int(os.getenv("MAX_STEPS", str(DEFAULT_MAX_STEPS))),
        help=f"Maximum execution steps (default: {DEFAULT_MAX_STEPS})"
    )
    agent_group.add_argument(
        "--max-runtime-seconds",
        type=float,
        default=float(os.getenv("MAX_RUNTIME_SECONDS", str(DEFAULT_MAX_RUNTIME_SECONDS))),
        help=f"Maximum runtime in seconds (default: {DEFAULT_MAX_RUNTIME_SECONDS})"
    )
    agent_group.add_argument(
        "--app-launch-timeout-seconds",
        type=float,
        default=float(os.getenv("APP_LAUNCH_TIMEOUT_SECONDS", str(DEFAULT_APP_LAUNCH_TIMEOUT_SECONDS))),
        help=argparse.SUPPRESS
    )

    # Device configuration
    device_group = parser.add_argument_group("Device Management")
    device_group.add_argument(
        "--device-id",
        default=os.getenv("DEVICE_ID"),
        help="ADB device ID for multi-device setups"
    )
    device_group.add_argument(
        "--connect", "-c",
        metavar="ADDRESS",
        help="Connect to remote device"
    )
    device_group.add_argument(
        "--disconnect",
        nargs="?",
        const="all",
        metavar="ADDRESS",
        help="Disconnect from remote device"
    )
    device_group.add_argument(
        "--enable-tcpip",
        type=int,
        nargs="?",
        const=DEFAULT_TCPIP_PORT,
        metavar="PORT",
        help="Enable TCP/IP debugging"
    )
    device_group.add_argument(
        "--list-devices",
        action="store_true",
        help="List connected ADB devices"
    )
    device_group.add_argument(
        "--list-apps",
        action="store_true",
        help="List configured apps installed on the selected device"
    )
    device_group.add_argument(
        "--list-configured-apps",
        action="store_true",
        help="List built-in compatibility aliases without querying a device"
    )

    # Verification and recovery
    verification_group = parser.add_argument_group("Verification & Recovery")
    verification_group.add_argument(
        "--disable-verification",
        action="store_true",
        help="Disable post-action verification (diagnostic only)"
    )
    verification_group.add_argument(
        "--disable-recovery",
        action="store_true",
        help="Disable automatic recovery and abort on first recoverable failure"
    )

    # Hidden/advanced options
    _add_hidden_options(parser)

    # Output and behavior
    behavior_group = parser.add_argument_group("Behavior")
    behavior_group.add_argument(
        "--trajectory-dir",
        default=os.getenv("TRAJECTORY_DIR", DEFAULT_TRAJECTORY_DIR),
        help=f"Directory for trajectory logs (default: {DEFAULT_TRAJECTORY_DIR})"
    )
    behavior_group.add_argument(
        "--skip-system-check",
        action="store_true",
        help="Skip ADB and device verification"
    )
    behavior_group.add_argument(
        "--skip-model-check",
        action="store_true",
        help="Skip model API verification"
    )
    behavior_group.add_argument(
        "--allow-fallback-screenshot",
        action="store_true",
        help="Diagnostic only: permit unavailable screenshots to be represented by a marked fallback"
    )
    behavior_group.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress verbose output"
    )

    return parser.parse_args()


# Keep the argument parser importable for integrations and tests.  The Web UI
# and earlier releases exposed the CLI helpers as public functions, so the
# refactor to private implementation names must not remove that API surface.
def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for programmatic CLI callers."""
    return _parse_arguments()


def _add_hidden_options(parser: argparse.ArgumentParser) -> None:
    """Add hidden/advanced options not shown in help."""
    hidden = parser.add_argument_group("Advanced (hidden)")

    # These are intentionally hidden from help
    for name, default, env_var, help_text in [
        ("max-consecutive-failures", DEFAULT_MAX_CONSECUTIVE_FAILURES, "MAX_FAILURES", None),
        ("max-repeated-actions", DEFAULT_MAX_REPEATED_ACTIONS, "MAX_REPEATED_ACTIONS", None),
        ("context-turns", DEFAULT_CONTEXT_TURNS, "CONTEXT_TURNS", None),
        ("observation-retries", DEFAULT_OBSERVATION_RETRIES, "OBSERVATION_RETRIES", None),
        ("verification-retries", DEFAULT_VERIFICATION_RETRIES, "VERIFICATION_RETRIES", None),
        ("verification-threshold", DEFAULT_VERIFICATION_THRESHOLD, "VERIFICATION_THRESHOLD", None),
        ("max-recoveries", DEFAULT_MAX_RECOVERIES, "MAX_RECOVERIES", None),
        ("recovery-attempts-per-failure", DEFAULT_RECOVERY_ATTEMPTS_PER_FAILURE, "RECOVERY_ATTEMPTS", None),
    ]:
        type_func = float if "threshold" in name else int
        default_value = type_func(default)
        env_value = os.getenv(env_var)
        final_default = type_func(env_value) if env_value is not None else default_value
        hidden.add_argument(
            f"--{name.replace('_', '-')}",
            type=type_func,
            default=final_default,
            help=argparse.SUPPRESS
        )


# ============================================================================
# Configuration Building
# ============================================================================

def _build_cli_config(args: argparse.Namespace) -> CLIConfig:
    """Build configuration from parsed arguments."""
    # Validate required configuration
    missing = []
    if not args.base_url:
        missing.append("--base-url or BASE_URL env var")
    if not args.model:
        missing.append("--model or MODEL env var")
    if not args.apikey:
        missing.append("--apikey or API_KEY env var")

    if missing:
        print(
            f"Missing required configuration: {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(ExitCode.CONFIG_ERROR.value)

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
            app_launch_timeout_seconds=args.app_launch_timeout_seconds,
            verification=VerificationConfig(
                enabled=not args.disable_verification,
                observation_retries=args.verification_retries,
                visual_change_threshold=args.verification_threshold,
            ),
            recovery=RecoveryConfig(
                enabled=not args.disable_recovery,
                max_total_recoveries=args.max_recoveries,
                max_attempts_per_failure=args.recovery_attempts_per_failure,
            ),
        )
    except ValueError as exc:
        print(f"Invalid configuration: {exc}", file=sys.stderr)
        sys.exit(ExitCode.CONFIG_ERROR.value)

    return CLIConfig(
        model=model_config,
        agent=agent_config,
        device_id=args.device_id,
        task=args.task,
        skip_system_check=args.skip_system_check,
        skip_model_check=args.skip_model_check,
        quiet=args.quiet,
    )


# ============================================================================
# Device Commands
# ============================================================================

def _handle_device_commands(args: argparse.Namespace) -> Optional[int]:
    """Handle standalone device management commands."""
    conn = ADBConnection()

    if args.connect:
        ok, message = conn.connect(args.connect)
        print(f"[{'OK' if ok else 'FAILED'}] {message}")
        return ExitCode.SUCCESS.value if ok else ExitCode.FAILURE.value

    if args.disconnect is not None:
        address = None if args.disconnect == "all" else args.disconnect
        ok, message = conn.disconnect(address)
        print(f"[{'OK' if ok else 'FAILED'}] {message}")
        return ExitCode.SUCCESS.value if ok else ExitCode.FAILURE.value

    if args.enable_tcpip is not None:
        ok, message = conn.enable_tcpip(args.enable_tcpip, args.device_id)
        print(f"[{'OK' if ok else 'FAILED'}] {message}")
        if ok:
            ip = conn.get_device_ip(args.device_id)
            if ip:
                print(f"Connect later with: phoneagent --connect {ip}:{args.enable_tcpip}")
        return ExitCode.SUCCESS.value if ok else ExitCode.FAILURE.value

    if args.list_devices:
        devices = conn.list_devices()
        if not devices:
            print("No ADB devices detected")
            return ExitCode.FAILURE.value
        for device in devices:
            print(
                f"{device.device_id}\t{device.status}\t"
                f"{device.connection_type.value}\t{device.model or ''}"
            )
        return ExitCode.SUCCESS.value

    return None


def _list_device_apps(device_id: Optional[str]) -> int:
    """List configured apps on the selected device."""
    selected = _select_ready_device(device_id)
    if selected is None:
        print(
            "Unable to select one ready Android device. Connect a device or pass --device-id.",
            file=sys.stderr,
        )
        return ExitCode.FAILURE.value

    try:
        device = AndroidDevice(device_id=selected)
        apps = device.list_launchable_apps()
    except Exception as exc:
        print(f"Failed to query installed configured apps: {exc}", file=sys.stderr)
        return ExitCode.FAILURE.value

    if not apps:
        print("No configured applications are installed", file=sys.stderr)
        return ExitCode.FAILURE.value

    print(f"Device: {selected}")
    print(f"Installed configured apps: {len(apps)}")
    print("NAME\tPACKAGE")
    for app in apps:
        print(f"{app.display_name}\t{app.package_name}")
    return ExitCode.SUCCESS.value


def _select_ready_device(device_id: Optional[str]) -> Optional[str]:
    """Select a ready device, preferring the specified ID."""
    conn = ADBConnection()
    ready = [item for item in conn.list_devices() if item.status == "device"]

    if device_id:
        if any(item.device_id == device_id for item in ready):
            return device_id
        return None

    if len(ready) == 1:
        return ready[0].device_id
    return None


def _print_configured_apps() -> None:
    """Print all configured app names."""
    for app in sorted(set(list_supported_apps()), key=str.casefold):
        print(app)


# ============================================================================
# System and Model Checks
# ============================================================================

def _check_system_requirements(device_id: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Check ADB and Android device requirements.

    Returns:
        Tuple of (success, resolved_device_id)
    """
    print("\n" + "=" * 64)
    print("Android / ADB Environment Check")
    print("=" * 64)

    # Check ADB
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

    # Check connected devices
    print("\n[2/4] Connected device")
    conn = ADBConnection(adb_path=adb_path)
    devices = conn.list_devices()
    ready = [device for device in devices if device.status == "device"]

    for device in devices:
        marker = "OK" if device.status == "device" else "WARN"
        model = f" model={device.model}" if device.model else ""
        print(f"  [{marker}] {device.device_id} state={device.status}{model}")

    selected = _select_ready_device(device_id)
    if selected is None:
        if device_id:
            print(f"  [FAILED] Device {device_id!r} is absent or not ready")
        else:
            print("  [FAILED] No authorized device in `device` state or multiple ready devices; use --device-id")
        return False, None

    print(f"  Selected: {selected}")

    # Check input method
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

    # Check screenshot capability
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


def _check_model_api(config: ModelConfig) -> bool:
    """
    Check if the model API is accessible.

    Returns:
        True if API check passes, False otherwise.
    """
    print("\n" + "=" * 64)
    print("Model API Check")
    print("=" * 64)
    print(f"  Base URL: {config.base_url}")
    print(f"  Model:    {config.model_name}")

    try:
        # Late import to avoid dependency if not needed
        from openai import OpenAI, DefaultHttpxClient

        client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=min(config.timeout, 30.0) if config.timeout else 30.0,
            http_client=DefaultHttpxClient(trust_env=False),
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

        choice = response.choices[0]
        content = getattr(choice.message, "content", "")
        reasoning = getattr(choice.message, "reasoning_content", "")
        content_present = bool(content and str(content).strip())
        reasoning_present = bool(reasoning and str(reasoning).strip())
        if not content_present and not reasoning_present:
            print("  [FAILED] API returned empty response")
            return False

        if not content_present:
            print(
                "  [WARN] Short probe returned reasoning without final content "
                f"(finish_reason={choice.finish_reason or 'unknown'})"
            )

        print("  [OK] API responded successfully")
        print("=" * 64 + "\n")
        return True

    except ImportError:
        print("  [FAILED] OpenAI package not installed")
        print("  Run: pip install openai")
        return False
    except Exception as exc:
        print(f"  [FAILED] {exc}")
        print("=" * 64 + "\n")
        return False


def check_system_requirements(
    device_id: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """Public compatibility wrapper for the Android/ADB preflight check."""
    return _check_system_requirements(device_id)


def check_model_api(config: ModelConfig) -> bool:
    """Public compatibility wrapper for the model endpoint preflight check."""
    return _check_model_api(config)


# ============================================================================
# Agent Execution
# ============================================================================

def _run_agent(cli_config: CLIConfig) -> int:
    """
    Run the PhoneAgent with the given configuration.

    Args:
        cli_config: Aggregated CLI configuration.

    Returns:
        Exit code.
    """
    # Perform system checks if enabled
    resolved_device_id = cli_config.device_id

    if not cli_config.skip_system_check:
        ok, resolved_device_id = _check_system_requirements(cli_config.device_id)
        if not ok:
            return ExitCode.FAILURE.value
        cli_config.agent.device_id = resolved_device_id

    # Perform model check if enabled
    if not cli_config.skip_model_check:
        if not _check_model_api(cli_config.model):
            return ExitCode.FAILURE.value

    # Create agent
    agent = PhoneAgent(
        model_config=cli_config.model,
        agent_config=cli_config.agent,
    )

    # Execute task or enter interactive mode
    if cli_config.task:
        return _run_task(agent, cli_config.task)

    return _run_interactive(agent)


def _run_task(agent: PhoneAgent, task: str) -> int:
    """
    Run a single task with the agent.

    Returns:
        Exit code.
    """
    print(f"\nStarting task: {task}\n")

    try:
        result = agent.run(task)
    except Exception as exc:
        print(f"\n[ERROR] Task execution failed: {exc}")
        return ExitCode.FAILURE.value

    status = "SUCCESS" if agent.state.success else "FAILED"
    print(
        f"\n[{status}] {result} "
        f"(phase={agent.state.phase.value}, recoveries={agent.state.recovery_count})"
    )

    if agent.last_trajectory_path:
        print(f"Trajectory: {agent.last_trajectory_path}")

    return ExitCode.SUCCESS.value if agent.state.success else ExitCode.TASK_FAILURE.value


def _run_interactive(agent: PhoneAgent) -> int:
    """
    Run the agent in interactive mode.

    Returns:
        Exit code (always SUCCESS on normal exit).
    """
    print("PhoneAgent interactive mode. Type exit/quit/q to stop.\n")

    while True:
        try:
            task = input("Task> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return ExitCode.SUCCESS.value

        if not task:
            continue

        if task.casefold() in {"exit", "quit", "q"}:
            print("Bye.")
            return ExitCode.SUCCESS.value

        try:
            result = agent.run(task)
        except Exception as exc:
            print(f"\n[ERROR] {exc}")
            continue

        status = "SUCCESS" if agent.state.success else "FAILED"
        print(
            f"\n[{status}] {result} "
            f"(phase={agent.state.phase.value}, recoveries={agent.state.recovery_count})"
        )

        if agent.last_trajectory_path:
            print(f"Trajectory: {agent.last_trajectory_path}")
        print()


# ============================================================================
# Module Entry Point
# ============================================================================

if __name__ == "__main__":
    raise SystemExit(main())
