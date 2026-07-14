"""ADB connection management for local and remote devices."""

from __future__ import annotations

import ipaddress
import logging
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from phoneagent.config.timing import TIMING_CONFIG

logger = logging.getLogger(__name__)


class ConnectionType(Enum):
    """Type of ADB connection."""

    USB = "usb"
    WIFI = "wifi"
    REMOTE = "remote"
    EMULATOR = "emulator"


@dataclass(slots=True)
class DeviceInfo:
    """Information about a connected Android device."""

    device_id: str
    status: str
    connection_type: ConnectionType
    model: str | None = None
    android_version: str | None = None


class ADBConnection:
    """
    Manage ADB connections to Android devices.

    Supports:
        - USB-connected physical devices
        - Android emulators
        - WiFi ADB devices in a private LAN
        - Remote TCP/IP ADB devices

    Example:
        >>> conn = ADBConnection()
        >>> conn.connect("192.168.1.100:5555")
        >>> devices = conn.list_devices()
        >>> conn.disconnect("192.168.1.100:5555")
    """

    DEFAULT_PORT = 5555

    def __init__(self, adb_path: str = "adb"):
        """
        Initialize ADB connection manager.

        Args:
            adb_path: Path to ADB executable.
        """
        self.adb_path = adb_path
        self.last_error: str | None = None

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------

    def _run(
        self,
        args: list[Any],
        *,
        timeout: float = 5,
        device_id: str | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        """
        Run an adb command.

        This helper keeps subprocess handling consistent inside this module.
        It intentionally returns CompletedProcess instead of raising by default,
        because many connection commands need to inspect stdout/stderr.
        """
        cmd = [self.adb_path]

        if device_id:
            cmd.extend(["-s", device_id])

        cmd.extend(str(arg) for arg in args)

        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=check,
        )

    @staticmethod
    def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
        """Return stdout and stderr as one stripped string."""
        return ((result.stdout or "") + (result.stderr or "")).strip()

    @classmethod
    def _normalize_address(cls, address: str) -> str:
        """Normalize ADB TCP/IP address. If port is missing, append 5555."""
        address = address.strip()

        if not address:
            return address

        # IPv6 addresses are uncommon for adb connect and can contain ":".
        # For this project, keep the existing simple host:port convention.
        if ":" not in address:
            return f"{address}:{cls.DEFAULT_PORT}"

        return address

    @staticmethod
    def _parse_model(parts: list[str]) -> str | None:
        for part in parts:
            if part.startswith("model:"):
                return part.split(":", 1)[1]
        return None

    @staticmethod
    def _infer_connection_type(device_id: str) -> ConnectionType:
        """
        Infer connection type from adb device id.

        Examples:
            emulator-5554           -> EMULATOR
            R5CT123456              -> USB
            192.168.1.100:5555      -> WIFI
            8.8.8.8:5555            -> REMOTE
            host.example.com:5555    -> REMOTE
        """
        if device_id.startswith("emulator-"):
            return ConnectionType.EMULATOR

        if ":" not in device_id:
            return ConnectionType.USB

        host = device_id.rsplit(":", 1)[0]

        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return ConnectionType.REMOTE

        if ip.is_private:
            return ConnectionType.WIFI

        return ConnectionType.REMOTE

    def _select_device_id(self, device_id: str | None = None) -> tuple[str | None, str | None]:
        """
        Select a usable device id.

        Returns:
            (device_id, error_message)

        If device_id is provided, validate that it exists and is in `device` state.
        If device_id is None, select the only available authorized device.
        """
        devices = self.list_devices()
        ready_devices = [d for d in devices if d.status == "device"]

        if device_id:
            for device in devices:
                if device.device_id == device_id:
                    if device.status == "device":
                        return device.device_id, None
                    return None, f"Device {device_id} is not ready. Current status: {device.status}"
            return None, f"Device {device_id} was not found."

        if not ready_devices:
            if devices:
                states = ", ".join(f"{d.device_id}={d.status}" for d in devices)
                return None, f"No authorized Android device found. Found devices: {states}"
            return None, "No Android device or emulator detected."

        if len(ready_devices) > 1:
            ids = ", ".join(d.device_id for d in ready_devices)
            return None, f"Multiple authorized devices found: {ids}. Please specify device_id."

        return ready_devices[0].device_id, None

    # ---------------------------------------------------------------------
    # Public APIs
    # ---------------------------------------------------------------------

    def connect(self, address: str, timeout: int = 10) -> tuple[bool, str]:
        """
        Connect to a remote device via TCP/IP.

        Args:
            address: Device address in format "host:port".
                     If port is omitted, 5555 is used.
            timeout: Connection timeout in seconds.

        Returns:
            Tuple of (success, message).

        Note:
            The remote device must have TCP/IP debugging enabled first.
            Usually this requires:
                adb tcpip 5555
        """
        address = self._normalize_address(address)

        if not address:
            return False, "Device address is empty."

        try:
            result = self._run(["connect", address], timeout=timeout)
            output = self._combined_output(result)
            output_lower = output.lower()

            if "already connected" in output_lower:
                return True, f"Already connected to {address}"

            if "connected" in output_lower:
                return True, f"Connected to {address}"

            if result.returncode != 0:
                return False, output or f"Failed to connect to {address}"

            # Some adb versions may return 0 but print unusual text.
            return True, output or f"Connected to {address}"

        except subprocess.TimeoutExpired:
            return False, f"Connection timeout after {timeout}s"
        except FileNotFoundError:
            return False, f"ADB executable not found: {self.adb_path}"
        except Exception as exc:
            return False, f"Connection error: {exc}"

    def disconnect(self, address: str | None = None) -> tuple[bool, str]:
        """
        Disconnect from a TCP/IP device.

        Args:
            address: Device address to disconnect. If None, disconnects all TCP/IP devices.

        Returns:
            Tuple of (success, message).
        """
        try:
            args: list[Any] = ["disconnect"]
            if address:
                args.append(self._normalize_address(address))

            result = self._run(args, timeout=5)
            output = self._combined_output(result)

            if result.returncode == 0:
                return True, output or "Disconnected"

            return False, output or "Disconnect failed"

        except subprocess.TimeoutExpired:
            return False, "Disconnect timeout after 5s"
        except FileNotFoundError:
            return False, f"ADB executable not found: {self.adb_path}"
        except Exception as exc:
            return False, f"Disconnect error: {exc}"

    def list_devices(self) -> list[DeviceInfo]:
        """
        List all connected ADB devices.

        Returns:
            List of DeviceInfo objects.

        Device status may be:
            - device
            - unauthorized
            - offline
            - recovery
            - sideload
            - bootloader
        """
        try:
            result = self._run(["devices", "-l"], timeout=5)

            if result.returncode != 0:
                self.last_error = self._combined_output(result) or "adb devices failed"
                logger.warning("Failed to list ADB devices: %s", self.last_error)
                return []

            devices: list[DeviceInfo] = []
            lines = result.stdout.splitlines()

            for line in lines[1:]:  # Skip "List of devices attached"
                line = line.strip()
                if not line:
                    continue

                parts = line.split()
                if len(parts) < 2:
                    continue

                device_id = parts[0]
                status = parts[1]
                extra_parts = parts[2:]

                devices.append(
                    DeviceInfo(
                        device_id=device_id,
                        status=status,
                        connection_type=self._infer_connection_type(device_id),
                        model=self._parse_model(extra_parts),
                        android_version=None,
                    )
                )

            self.last_error = None
            return devices

        except Exception as exc:
            self.last_error = str(exc)
            logger.warning("Failed to list ADB devices: %s", exc)
            return []

    def get_device_info(self, device_id: str | None = None) -> DeviceInfo | None:
        """
        Get basic information about a device.

        Args:
            device_id: Device ID. If None, returns the only available authorized device
                       when possible.

        Returns:
            DeviceInfo or None if not found.
        """
        selected_device_id, error = self._select_device_id(device_id)
        if error or selected_device_id is None:
            return None

        devices = self.list_devices()
        selected = None

        for device in devices:
            if device.device_id == selected_device_id:
                selected = device
                break

        if selected is None:
            return None

        android_version = self.get_android_version(selected_device_id)

        return DeviceInfo(
            device_id=selected.device_id,
            status=selected.status,
            connection_type=selected.connection_type,
            model=selected.model,
            android_version=android_version,
        )

    def is_connected(self, device_id: str | None = None) -> bool:
        """
        Check whether a device is connected and ready.

        Args:
            device_id: Device ID to check. If None, checks whether at least one
                       device is in `device` state.

        Returns:
            True if a usable device exists, False otherwise.
        """
        devices = self.list_devices()

        if device_id is None:
            return any(device.status == "device" for device in devices)

        return any(
            device.device_id == device_id and device.status == "device"
            for device in devices
        )

    def enable_tcpip(
        self,
        port: int = DEFAULT_PORT,
        device_id: str | None = None,
    ) -> tuple[bool, str]:
        """
        Enable TCP/IP debugging on a USB-connected device.

        Args:
            port: TCP port for ADB. Default is 5555.
            device_id: Device ID. If None, selects the only authorized device.

        Returns:
            Tuple of (success, message).

        Note:
            The device must be connected and authorized first.
            After this, you can disconnect USB and connect via WiFi.
        """
        if not 1 <= port <= 65535:
            return False, f"Invalid TCP port: {port}. Expected range: 1-65535."

        selected_device_id, error = self._select_device_id(device_id)
        if error or selected_device_id is None:
            return False, error or "No usable Android device selected."

        try:
            result = self._run(
                ["tcpip", port],
                device_id=selected_device_id,
                timeout=10,
            )

            output = self._combined_output(result)
            output_lower = output.lower()

            if result.returncode == 0 or "restarting" in output_lower:
                time.sleep(TIMING_CONFIG.connection.adb_restart_delay)
                return True, f"TCP/IP mode enabled on port {port} for {selected_device_id}"

            return False, output or "Failed to enable TCP/IP mode."

        except subprocess.TimeoutExpired:
            return False, "Enable TCP/IP timeout after 10s"
        except FileNotFoundError:
            return False, f"ADB executable not found: {self.adb_path}"
        except Exception as exc:
            return False, f"Error enabling TCP/IP: {exc}"

    def get_device_ip(self, device_id: str | None = None) -> str | None:
        """
        Get the IP address of a connected device.

        Args:
            device_id: Device ID. If None, selects the only authorized device.

        Returns:
            IP address string or None if not found.
        """
        selected_device_id, error = self._select_device_id(device_id)
        if error or selected_device_id is None:
            return None

        # First try: adb shell ip route
        try:
            result = self._run(
                ["shell", "ip", "route"],
                device_id=selected_device_id,
                timeout=5,
            )

            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    parts = line.split()
                    for idx, part in enumerate(parts):
                        if part == "src" and idx + 1 < len(parts):
                            ip = parts[idx + 1]
                            if self._is_valid_ip(ip):
                                return ip

        except Exception as exc:
            logger.debug("Failed to get device IP from route: %s", exc)

        # Second try: wlan0 interface
        try:
            result = self._run(
                ["shell", "ip", "addr", "show", "wlan0"],
                device_id=selected_device_id,
                timeout=5,
            )

            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line.startswith("inet "):
                        parts = line.split()
                        if len(parts) >= 2:
                            ip = parts[1].split("/", 1)[0]
                            if self._is_valid_ip(ip):
                                return ip

        except Exception as exc:
            logger.debug("Failed to get device IP from wlan0: %s", exc)

        return None

    @staticmethod
    def _is_valid_ip(value: str) -> bool:
        try:
            ipaddress.ip_address(value)
        except ValueError:
            return False
        return True

    def get_android_version(self, device_id: str | None = None) -> str | None:
        """
        Get Android version of a connected device.

        Args:
            device_id: Device ID. If None, selects the only authorized device.

        Returns:
            Android version string, such as "14", or None if unavailable.
        """
        selected_device_id, error = self._select_device_id(device_id)
        if error or selected_device_id is None:
            return None

        try:
            result = self._run(
                ["shell", "getprop", "ro.build.version.release"],
                device_id=selected_device_id,
                timeout=5,
            )

            if result.returncode != 0:
                return None

            version = result.stdout.strip()
            return version or None

        except Exception as exc:
            logger.debug("Failed to get Android version: %s", exc)
            return None

    def restart_server(self) -> tuple[bool, str]:
        """
        Restart the ADB server.

        Returns:
            Tuple of (success, message).
        """
        try:
            kill_result = self._run(["kill-server"], timeout=5)
            kill_output = self._combined_output(kill_result)

            time.sleep(TIMING_CONFIG.connection.server_restart_delay)

            start_result = self._run(["start-server"], timeout=5)
            start_output = self._combined_output(start_result)

            if start_result.returncode == 0:
                return True, "ADB server restarted"

            output = start_output or kill_output or "Failed to restart ADB server"
            return False, output

        except subprocess.TimeoutExpired:
            return False, "ADB server restart timeout"
        except FileNotFoundError:
            return False, f"ADB executable not found: {self.adb_path}"
        except Exception as exc:
            return False, f"Error restarting server: {exc}"


def quick_connect(address: str) -> tuple[bool, str]:
    """
    Quick helper to connect to a remote device.

    Args:
        address: Device address, e.g. "192.168.1.100" or "192.168.1.100:5555".

    Returns:
        Tuple of (success, message).
    """
    conn = ADBConnection()
    return conn.connect(address)


def list_devices() -> list[DeviceInfo]:
    """
    Quick helper to list connected devices.

    Returns:
        List of DeviceInfo objects.
    """
    conn = ADBConnection()
    return conn.list_devices()