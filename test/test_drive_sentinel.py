"""Safety and isolation tests for the bundled Drive Sentinel backend."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import pytest

from codex_crew.apps.builtins.drive_sentinel import backend


def test_non_windows_volume_inventory_does_not_touch_winapi(monkeypatch) -> None:
    class RefuseWinApi:
        def __getattr__(self, _name):
            raise AssertionError("WinAPI must not be read on a non-Windows host")

    monkeypatch.setattr(backend.os, "name", "posix")
    monkeypatch.setattr(backend.ctypes, "windll", RefuseWinApi(), raising=False)

    assert backend.mounted_volumes() == []


def _request(
    path: str,
    payload: dict,
    *,
    signed: bool = True,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    secret = "test-drive-sentinel-proxy-secret"
    raw_body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if signed:
        timestamp = str(int(time.time()))
        body_hash = hashlib.sha256(raw_body).hexdigest()
        message = f"{timestamp}:POST:{path}:{body_hash}"
        signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        headers["X-CodexCrew-Proxy"] = f"{timestamp}:{signature}"
    headers.update(extra_headers or {})

    with patch.dict(os.environ, {"CODEXCREW_PROXY_SECRET": secret}):
        server = ThreadingHTTPServer(("127.0.0.1", 0), backend.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}{path}",
                data=raw_body,
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    return response.status, json.loads(response.read())
            except urllib.error.HTTPError as error:
                return error.code, json.loads(error.read())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


def _get(path: str, *, signed: bool) -> tuple[int, dict]:
    secret = "test-drive-sentinel-proxy-secret"
    headers: dict[str, str] = {}
    if signed:
        timestamp = str(int(time.time()))
        body_hash = hashlib.sha256(b"").hexdigest()
        message = f"{timestamp}:GET:{path}:{body_hash}"
        signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        headers["X-CodexCrew-Proxy"] = f"{timestamp}:{signature}"

    with patch.dict(os.environ, {"CODEXCREW_PROXY_SECRET": secret}):
        server = ThreadingHTTPServer(("127.0.0.1", 0), backend.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}{path}", headers=headers
            )
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    return response.status, json.loads(response.read())
            except urllib.error.HTTPError as error:
                return error.code, json.loads(error.read())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


def test_cleanup_rejects_a_selected_drive_that_does_not_match_the_index(monkeypatch) -> None:
    index = backend.Index()
    index.root = backend.Node("D:\\")
    index.root_path = "D:\\"
    index.targets = {
        "cache-1": {
            "id": "cache-1",
            "path": "D:\\cache",
            "label": "cache",
            "kind": "cache",
            "risk": "safe",
            "action": "delete",
            "note": "regenerable",
        }
    }
    monkeypatch.setattr(backend, "IDX", index)
    monkeypatch.setattr(backend, "purge", lambda _target: {"ok": True})

    status, body = _request("/api/purge", {"id": "cache-1", "root": "C:\\"})

    assert status == 409
    assert body["code"] == "indexed_root_mismatch"


def test_unattended_sweep_refuses_a_non_system_volume(monkeypatch) -> None:
    index = backend.Index()
    index.root = backend.Node("D:\\")
    index.root_path = "D:\\"
    index.targets = {
        "cache-1": {
            "id": "cache-1",
            "path": "D:\\cache",
            "label": "cache",
            "kind": "cache",
            "risk": "safe",
            "action": "delete",
            "note": "regenerable",
            "automatable": True,
            "bytes": 10,
        }
    }
    monkeypatch.setattr(backend, "IDX", index)
    monkeypatch.setenv("SystemDrive", "C:")
    monkeypatch.setattr(
        backend,
        "drive_space",
        lambda _root=backend.DRIVE: {"total": 100, "free": 0, "used": 100},
    )

    result = backend.sweep(min_free_gb=1, dry=False)

    assert result["ok"] is False
    assert result["code"] == "unattended_system_drive_only"


def test_backend_start_does_not_scan_until_the_user_requests_it(monkeypatch) -> None:
    scan_started = False

    class Server:
        def __init__(self, *_args, **_kwargs):
            pass

        def serve_forever(self):
            raise KeyboardInterrupt

    class Thread:
        def __init__(self, *, target, **_kwargs):
            nonlocal scan_started
            if target == backend.IDX.scan:
                scan_started = True

        def start(self):
            pass

    monkeypatch.setattr(backend, "ThreadingHTTPServer", Server)
    monkeypatch.setattr(backend.threading, "Thread", Thread)

    backend.serve()

    assert scan_started is False


def test_new_index_has_no_scan_root_until_an_explicit_scan() -> None:
    index = backend.Index()

    assert index.root is None
    assert index.root_path == ""


def test_unsigned_loopback_post_is_refused_before_dispatch(monkeypatch) -> None:
    called = False

    def unexpected_sweep(*_args, **_kwargs):
        nonlocal called
        called = True
        return {"ok": True}

    monkeypatch.setattr(backend, "sweep", unexpected_sweep)

    status, body = _request("/api/sweep", {}, signed=False)

    assert status == 401
    assert body == {"error": "unauthorized"}
    assert called is False


def test_only_health_is_readable_without_the_proxy_signature() -> None:
    status_code, status_body = _get("/api/status", signed=False)
    health_code, health_body = _get("/health", signed=False)

    assert status_code == 401
    assert status_body == {"error": "unauthorized"}
    assert health_code == 200
    assert health_body == {"status": "ok", "app": "drive-sentinel"}


def test_cross_site_browser_post_is_refused_even_with_a_valid_signature(monkeypatch) -> None:
    called = False

    def unexpected_sweep(*_args, **_kwargs):
        nonlocal called
        called = True
        return {"ok": True}

    monkeypatch.setattr(backend, "sweep", unexpected_sweep)

    status, body = _request(
        "/api/sweep",
        {},
        extra_headers={"Sec-Fetch-Site": "cross-site"},
    )

    assert status == 403
    assert body == {"error": "cross-site request refused"}
    assert called is False


def test_http_sweep_is_a_dry_run_unless_apply_is_explicit(monkeypatch) -> None:
    calls: list[tuple[float, bool]] = []

    def recording_sweep(min_free_gb: float, dry: bool):
        calls.append((min_free_gb, dry))
        return {"ok": True, "dry_run": dry}

    monkeypatch.setattr(backend, "sweep", recording_sweep)

    status, body = _request("/api/sweep", {})

    assert status == 200
    assert body["dry_run"] is True
    assert calls == [(backend.SWEEP_MIN_FREE_GB, True)]


def test_activity_log_follows_the_codex_crew_data_home(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CODEXCREW_HOME", str(tmp_path))

    assert backend.activity_log_path() == str(
        tmp_path / "apps" / "drive-sentinel" / "activity.jsonl"
    )


def test_purge_refuses_before_deleting_when_audit_log_is_unavailable(tmp_path, monkeypatch) -> None:
    victim = tmp_path / "cache"
    victim.mkdir()
    (victim / "data.bin").write_bytes(b"keep me")
    target = {
        "path": str(victim),
        "label": "cache",
        "kind": "cache",
        "risk": "safe",
        "note": "regenerable",
    }

    def unavailable() -> None:
        raise OSError("read-only data home")

    monkeypatch.setattr(backend, "ensure_audit_log_writable", unavailable)

    with pytest.raises(OSError, match="read-only data home"):
        backend.purge(target)

    assert victim.is_dir()
    assert (victim / "data.bin").read_bytes() == b"keep me"
