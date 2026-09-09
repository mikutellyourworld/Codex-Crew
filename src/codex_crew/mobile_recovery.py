"""Opt-in ADB tunnel recovery for one explicitly selected, already paired phone.

Run under a service manager for boot recovery. This never installs, launches,
pairs, changes security settings, scans ports or switches to another phone.
"""

import argparse
import time

from codex_crew.mobile import Bridge, MobileError, endpoint, port


def recover(bridge: Bridge, address: str, host_port: int, phone_port: int) -> None:
    address = endpoint(address)
    wanted = [f"tcp:{port(phone_port)}", f"tcp:{port(host_port)}"]
    if bridge.devices().get(address) != "device":
        bridge.connect(address)
    bridge.verify(address)

    def present() -> bool:
        return any(
            line.split()[-2:] == wanted
            for line in bridge.run("-s", address, "reverse", "--list").splitlines()
        )

    if not present():
        bridge.run("-s", address, "reverse", *wanted)
        if not present():
            raise MobileError("ADB did not confirm the dashboard tunnel.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connect", required=True, type=endpoint)
    parser.add_argument("--host-port", type=port, default=5486)
    parser.add_argument("--phone-port", type=port, default=5486)
    parser.add_argument("--adb")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    bridge = Bridge(args.adb)
    previous = None
    try:
        while True:
            try:
                recover(bridge, args.connect, args.host_port, args.phone_port)
                message = "Dashboard tunnel ready."
                result = 0
            except MobileError:
                message = (
                    "Phone unavailable; retrying. If its debugging port changed, "
                    "update the selected connection endpoint."
                )
                result = 1
            if message != previous:
                print(message, flush=True)
                previous = message
            if args.once:
                return result
            time.sleep(15)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
