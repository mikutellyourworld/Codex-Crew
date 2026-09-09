"""Host-side Android setup. Run ``codexcrew-mobile`` or ``python -m codex_crew.mobile``.

ADB owns pairing keys. Codes are passed on stdin and never persisted or logged.
This local operator command does not expose an HTTP shell or bypass gateway auth.
"""

from __future__ import annotations

import argparse
import getpass
import ipaddress
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from codex_crew import platform_compat

PACKAGE = "dev.codexcrew.mobile"


class MobileError(RuntimeError):
    """Actionable setup failure, without command output containing secrets."""


def port(value: str | int) -> int:
    try:
        number = int(value)
    except (ValueError, TypeError):
        raise MobileError("Port must be a number from 1 to 65535.") from None
    if not 1 <= number <= 65535:
        raise MobileError("Port must be a number from 1 to 65535.")
    return number


def endpoint(value: str) -> str:
    """Only literal IP endpoints: no options, shell syntax or ambiguous DNS."""
    try:
        host, number = value.strip().rsplit(":", 1)
        address = ipaddress.ip_address(host.strip("[]"))
        if address.is_unspecified or address.is_multicast:
            raise ValueError
        host = f"[{address}]" if address.version == 6 else str(address)
        return f"{host}:{port(number)}"
    except (ValueError, MobileError):
        raise MobileError(
            "Enter the phone IP:port (IPv6 uses [address]:port)."
        ) from None


@dataclass(frozen=True)
class Service:
    name: str
    kind: str
    address: str


def parse_services(output: str) -> list[Service]:
    result = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 3:
            continue
        name, kind, address = fields
        kind = kind.rstrip(".")
        if kind not in {"_adb-tls-pairing._tcp", "_adb-tls-connect._tcp"}:
            continue
        try:
            result.append(Service(name, kind, endpoint(address)))
        except MobileError:
            continue
    return result


def parse_devices(output: str) -> dict[str, str]:
    devices = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] in {
            "device",
            "offline",
            "unauthorized",
            "recovery",
        }:
            devices[fields[0]] = fields[1]
    return devices


def find_adb() -> str:
    # Release kits can carry platform-tools alongside the executable.
    suffix = "adb.exe" if platform_compat.IS_WINDOWS else "adb"
    candidates = [Path(sys.executable).parent / "platform-tools" / suffix]
    for key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(key):
            candidates.append(Path(os.environ[key]) / "platform-tools" / suffix)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("adb")
    if found:
        return found
    raise MobileError(
        "ADB is missing. Install Android SDK Platform-Tools, or run the Android SDK "
        "sdkmanager platform-tools installer, then reopen this assistant."
    )


class Bridge:
    def __init__(self, executable: str | None = None):
        self.executable = executable or find_adb()

    def run(self, *args: str, secret: str | None = None, timeout: int = 20) -> str:
        try:
            result = subprocess.run(
                [self.executable, *args],
                input=secret + "\n" if secret is not None else None,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise MobileError(
                "ADB timed out. Check the phone and its current connection port."
            ) from None
        except OSError:
            raise MobileError(
                "Could not start ADB. Check your Platform-Tools installation."
            ) from None
        output = result.stdout + result.stderr
        if result.returncode:
            raise MobileError(
                "ADB failed. Check debugging authorization, network and current ports."
            )
        return output

    def devices(self) -> dict[str, str]:
        return parse_devices(self.run("devices", "-l"))

    def discover(self) -> list[Service]:
        try:
            return parse_services(self.run("mdns", "services"))
        except MobileError:
            return []  # mDNS can be unavailable across a VPN or on older ADB.

    def pair(self, address: str, code: str) -> None:
        address = endpoint(address)
        if not re.fullmatch(r"[0-9]{6}", code):
            raise MobileError("Enter the six-digit code from the pairing popup.")
        output = self.run("pair", address, secret=code, timeout=60)
        if "successfully paired to" not in output.lower():
            # ADB has returned status 0 for pairing failures in the wild.
            raise MobileError(
                "Pairing failed. Reopen the popup and use its new port and code."
            )

    def connect(self, address: str) -> str:
        address = endpoint(address)
        self.run("connect", address)
        self.verify(address)
        return address

    def verify(self, serial: str) -> None:
        if not serial or serial.startswith("-") or any(c.isspace() for c in serial):
            raise MobileError("Invalid device selection.")
        # Exact device selection, never ADB's ambiguous default-device behavior.
        if self.devices().get(serial) != "device":
            raise MobileError(
                "Phone is not connected or authorized. Check its current connection port."
            )
        if self.run("-s", serial, "get-state").strip() != "device":
            raise MobileError("ADB device verification failed.")

    def open_app(
        self, serial: str, host_port: int, phone_port: int, apk: Path | None = None
    ) -> None:
        host_port, phone_port = port(host_port), port(phone_port)
        self.verify(serial)
        if apk is not None:
            apk = apk.expanduser().resolve()
            if not apk.is_file() or apk.suffix.lower() != ".apk":
                raise MobileError("Choose an existing APK file.")
            if "Success" not in self.run(
                "-s", serial, "install", "-r", str(apk), timeout=120
            ):
                raise MobileError("Android did not confirm APK installation.")
        else:
            if "package:" not in self.run("-s", serial, "shell", "pm", "path", PACKAGE):
                raise MobileError(
                    "Install the Codex Crew APK first, or select it in the assistant."
                )
        self.run("-s", serial, "reverse", f"tcp:{phone_port}", f"tcp:{host_port}")
        mappings = self.run("-s", serial, "reverse", "--list")
        if not any(
            line.split()[-2:] == [f"tcp:{phone_port}", f"tcp:{host_port}"]
            for line in mappings.splitlines()
        ):
            raise MobileError("ADB did not confirm the dashboard tunnel.")
        result = self.run(
            "-s",
            serial,
            "shell",
            "am",
            "start",
            "-W",
            "-n",
            f"{PACKAGE}/.MainActivity",
            "--es",
            "dashboard_url",
            f"http://127.0.0.1:{phone_port}/",
        )
        if "Status: ok" not in result or "Error" in result:
            raise MobileError(
                "Android could not open the app. Check the APK installation."
            )


def choose(label: str, values: list[str]) -> str:
    if not values:
        return input(label + " (IP:port): ").strip()
    for number, value in enumerate(values, 1):
        print(f"  {number}. {value}")
    value = input(label + " (number or IP:port): ").strip()
    if value.isdigit() and 1 <= int(value) <= len(values):
        return values[int(value) - 1]
    return value


def wizard(bridge: Bridge) -> str:
    devices = bridge.devices()
    ready = [serial for serial, state in devices.items() if state == "device"]
    if ready:
        return ready[0] if len(ready) == 1 else choose("Choose connected phone", ready)
    if "unauthorized" in devices.values():
        input(
            "Unlock your phone and accept the USB debugging prompt, then press Enter. "
        )
        return wizard(bridge)
    print(
        "Samsung blocking debugging or installation? In phone Settings → Security and "
        "privacy → Auto Blocker, turn it off and confirm, then enable debugging. "
        "This temporarily removes Auto Blocker protections; restore it after debugging. "
        "Direct HTTPS dashboard access does not require this change."
    )
    print("Enable Wireless debugging in Android Developer options.")
    if input("Already paired to this computer? [y/N] ").strip().lower() != "y":
        print("Open Pair device with pairing code. Keep its popup open.")
        services = bridge.discover()
        pairing = choose(
            "Pairing endpoint", [s.address for s in services if "pairing" in s.kind]
        )
        bridge.pair(pairing, getpass.getpass("Pairing code (hidden): "))
        print(
            "Paired. Now use the CONNECTION port on the main Wireless debugging page."
        )
    # Always refresh after pairing; the connect service has its own port.
    services = bridge.discover()
    address = choose(
        "Connection endpoint", [s.address for s in services if "connect" in s.kind]
    )
    return bridge.connect(address)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Codex Crew Android connection assistant"
    )
    parser.add_argument("--adb", help="Path to Android SDK adb")
    parser.add_argument("--apk", type=Path, help="APK to install before opening")
    parser.add_argument(
        "--host-port", type=int, default=5486, help="Actual desktop gateway port"
    )
    parser.add_argument(
        "--phone-port", type=int, default=5486, help="Local port on the phone"
    )
    parser.add_argument("--device", help="Connected USB or wireless ADB serial")
    parser.add_argument("--connect", help="Current phone IP:connection-port")
    parser.add_argument(
        "--gui", action="store_true", help="Open the desktop pairing form"
    )
    parser.add_argument(
        "--discover", action="store_true", help="Show current ADB services and devices"
    )
    args = parser.parse_args(argv)
    try:
        port(args.host_port)
        port(args.phone_port)
        bridge = Bridge(args.adb)
        if args.gui:
            from codex_crew.mobile_gui import launch

            launch(bridge, args)
        elif args.discover:
            for serial, state in bridge.devices().items():
                print(f"{state}: {serial}")
            for service in bridge.discover():
                print(f"{service.kind}: {service.address}")
        else:
            serial = args.device or (
                bridge.connect(args.connect) if args.connect else wizard(bridge)
            )
            bridge.open_app(serial, args.host_port, args.phone_port, args.apk)
            print(
                "Connected. Confirm the dashboard address on the phone, then sign in normally."
            )
        return 0
    except (MobileError, ImportError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("Setup cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
