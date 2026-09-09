"""Connection invariants: no false success, stale ports, ambiguous devices or code leaks."""

import subprocess
from unittest.mock import Mock

import pytest

from codex_crew.mobile import (
    Bridge,
    MobileError,
    endpoint,
    main,
    parse_devices,
    parse_services,
    port,
    wizard,
)


@pytest.mark.parametrize("value", ["0", "65536", "abc", "-1"])
def test_bad_ports(value):
    with pytest.raises(MobileError):
        port(value)


@pytest.mark.parametrize(
    "value",
    [
        "--help",
        "host:5555",
        "127.0.0.1:0",
        "0.0.0.0:99",
        "224.0.0.1:9",
        "127.0.0.1:33;id",
    ],
)
def test_bad_endpoints(value):
    with pytest.raises(MobileError):
        endpoint(value)


def test_ipv6_and_port_range():
    assert endpoint("[2001:db8::1]:65535") == "[2001:db8::1]:65535"
    assert endpoint("192.0.2.1:1") == "192.0.2.1:1"


def test_discovery_separates_pairing_connect_and_legacy():
    services = parse_services(
        "List of discovered mdns services\n"
        "phone _adb-tls-pairing._tcp. 192.0.2.1:30001\n"
        "phone _adb-tls-connect._tcp 192.0.2.1:30002\n"
        "old _adb._tcp 192.0.2.1:5555\n"
        "bad _adb-tls-connect._tcp --help\n"
    )
    assert [s.address for s in services] == ["192.0.2.1:30001", "192.0.2.1:30002"]
    assert "pairing" in services[0].kind


def test_devices_include_authorization_states():
    assert parse_devices(
        "List of devices attached\nusb device product:test\nother unauthorized\nlast offline\n"
    ) == {
        "usb": "device",
        "other": "unauthorized",
        "last": "offline",
    }


def test_pairing_code_is_stdin_not_command_or_error(monkeypatch):
    run = Mock(
        return_value=subprocess.CompletedProcess(
            [], 0, "Successfully paired to phone", ""
        )
    )
    monkeypatch.setattr(subprocess, "run", run)
    Bridge("adb").pair("192.0.2.1:30001", "000000")
    assert run.call_args.args[0] == ["adb", "pair", "192.0.2.1:30001"]
    assert run.call_args.kwargs["input"] == "000000\n"
    run.return_value = subprocess.CompletedProcess(
        [], 0, "Unable to start pairing client 000000", ""
    )
    with pytest.raises(MobileError, match="Pairing failed") as error:
        Bridge("adb").pair("192.0.2.1:30001", "000000")
    assert "000000" not in str(error.value)


def test_zero_exit_connect_failure_is_not_success(monkeypatch):
    bridge = Bridge("adb")
    monkeypatch.setattr(
        bridge,
        "run",
        Mock(side_effect=["failed to connect", "List of devices attached\n"]),
    )
    with pytest.raises(MobileError, match="not connected"):
        bridge.connect("192.0.2.1:30002")


def test_verify_rejects_offline_and_options(monkeypatch):
    bridge = Bridge("adb")
    monkeypatch.setattr(bridge, "devices", lambda: {"phone": "offline"})
    for serial in ("phone", "-d", "two phones"):
        with pytest.raises(MobileError):
            bridge.verify(serial)


def test_subprocess_failure_and_timeout_never_echo_output(monkeypatch):
    run = Mock(return_value=subprocess.CompletedProcess([], 1, "private output", ""))
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(MobileError) as error:
        Bridge("adb").run("devices")
    assert "private" not in str(error.value)
    run.side_effect = subprocess.TimeoutExpired("adb", 20, output="private output")
    with pytest.raises(MobileError, match="timed out"):
        Bridge("adb").run("devices")


def test_tunnel_and_launch_use_exact_serial_and_separate_ports(monkeypatch):
    bridge = Bridge("adb")
    monkeypatch.setattr(bridge, "verify", Mock())
    run = Mock(
        side_effect=["package:/app/base.apk", "", "usb tcp:6000 tcp:7000", "Status: ok"]
    )
    monkeypatch.setattr(bridge, "run", run)
    bridge.open_app("usb", 7000, 6000)
    assert run.call_args_list[1].args == (
        "-s",
        "usb",
        "reverse",
        "tcp:6000",
        "tcp:7000",
    )
    assert run.call_args.args[-1] == "http://127.0.0.1:6000/"


def test_missing_tunnel_prevents_launch(monkeypatch):
    bridge = Bridge("adb")
    monkeypatch.setattr(bridge, "verify", Mock())
    run = Mock(side_effect=["package:/app/base.apk", "", "usb tcp:6000 tcp:9999"])
    monkeypatch.setattr(bridge, "run", run)
    with pytest.raises(MobileError, match="tunnel"):
        bridge.open_app("usb", 7000, 6000)
    assert run.call_count == 3


def test_pairing_refreshes_before_connection(monkeypatch):
    bridge = Bridge("adb")
    monkeypatch.setattr(bridge, "devices", dict)
    discovery = Mock(
        side_effect=[
            parse_services("phone _adb-tls-pairing._tcp 192.0.2.1:30001"),
            parse_services("phone _adb-tls-connect._tcp 192.0.2.1:30009"),
        ]
    )
    monkeypatch.setattr(bridge, "discover", discovery)
    pair = Mock()
    connect = Mock(return_value="phone")
    monkeypatch.setattr(bridge, "pair", pair)
    monkeypatch.setattr(bridge, "connect", connect)
    answers = iter(["n", "1", "1"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr("getpass.getpass", lambda _: "000000")
    assert wizard(bridge) == "phone"
    pair.assert_called_once_with("192.0.2.1:30001", "000000")
    connect.assert_called_once_with("192.0.2.1:30009")
    assert discovery.call_count == 2


def test_multiple_devices_require_choice(monkeypatch):
    bridge = Bridge("adb")
    monkeypatch.setattr(
        bridge, "devices", lambda: {"usb-a": "device", "usb-b": "device"}
    )
    monkeypatch.setattr("builtins.input", lambda _: "2")
    assert wizard(bridge) == "usb-b"


def test_invalid_cli_port_fails_before_adb():
    assert main(["--host-port", "0"]) == 1
