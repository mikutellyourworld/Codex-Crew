from unittest.mock import Mock

import pytest

from codex_crew.mobile import MobileError
from codex_crew.mobile_recovery import recover


def test_reconnects_selected_phone_and_restores_missing_tunnel():
    bridge = Mock()
    bridge.devices.return_value = {}
    bridge.run.side_effect = ["", "", "host tcp:5486 tcp:5486"]
    recover(bridge, "192.0.2.1:30000", 5486, 5486)
    bridge.connect.assert_called_once_with("192.0.2.1:30000")
    bridge.run.assert_any_call("-s", "192.0.2.1:30000", "reverse", "tcp:5486", "tcp:5486")
    bridge.open_app.assert_not_called()


def test_healthy_tunnel_is_not_rewritten():
    bridge = Mock()
    bridge.devices.return_value = {"192.0.2.1:30000": "device"}
    bridge.run.return_value = "host tcp:5486 tcp:5486"
    recover(bridge, "192.0.2.1:30000", 5486, 5486)
    bridge.connect.assert_not_called()
    assert bridge.run.call_count == 1


def test_unconfirmed_tunnel_is_failure():
    bridge = Mock()
    bridge.devices.return_value = {"192.0.2.1:30000": "device"}
    bridge.run.return_value = ""
    with pytest.raises(MobileError):
        recover(bridge, "192.0.2.1:30000", 5486, 5486)


def test_refused_endpoint_never_falls_back_to_other_phone():
    bridge = Mock()
    bridge.devices.return_value = {"192.0.2.2:30000": "device"}
    bridge.connect.side_effect = MobileError("Unavailable")
    with pytest.raises(MobileError):
        recover(bridge, "192.0.2.1:30000", 5486, 5486)
    bridge.run.assert_not_called()
