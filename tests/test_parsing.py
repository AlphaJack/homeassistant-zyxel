"""Offline unit tests for the DAL parsing helpers."""

from __future__ import annotations

from custom_components.zyxel.api import (
    _parse_hosts,
    _parse_traffic,
    _parse_wan_traffic,
    _select_active_dsl,
)


def test_select_active_dsl_prefers_up() -> None:
    channels = [
        {"Status": "Down", "DownstreamCurrRate": 0, "UpstreamCurrRate": 0},
        {"Status": "Up", "DownstreamCurrRate": 70042, "UpstreamCurrRate": 14817},
    ]
    active = _select_active_dsl(channels)
    assert active["Status"] == "Up"
    assert active["DownstreamCurrRate"] == 70042


def test_select_active_dsl_empty() -> None:
    assert _select_active_dsl([]) == {}


def test_parse_traffic_named_only() -> None:
    obj = {
        "ipIface": [{"X_ZYXEL_IfName": "br0"}, {"X_ZYXEL_IfName": ""}],
        "ipIfaceSt": [
            {"BytesSent": 10, "BytesReceived": 20},
            {"BytesSent": 1, "BytesReceived": 2},
        ],
    }
    traffic = _parse_traffic(obj)
    assert traffic == {"br0": {"BytesSent": 10, "BytesReceived": 20}}


def test_parse_hosts() -> None:
    obj = {
        "lanhosts": [
            {
                "PhysAddress": "AA:BB:CC:DD:EE:FF",
                "DeviceName": "laptop",
                "IPAddress": "192.168.1.20",
                "Active": True,
                "X_ZYXEL_ConnectionType": "WiFi",
                "X_ZYXEL_RSSI": -60,
                "X_ZYXEL_OperatingStandard": "",
            },
            {"HostName": "no-mac"},  # dropped: no PhysAddress
        ]
    }
    hosts = _parse_hosts(obj)
    assert len(hosts) == 1
    assert hosts[0]["rssi"] == -60
    assert hosts[0]["wifi_standard"] is None
    assert hosts[0]["mac"] == "AA:BB:CC:DD:EE:FF"
    assert hosts[0]["name"] == "laptop"
    assert hosts[0]["active"] is True


def _wan_iface(lower: str, status: str = "Up", gateway: bool = True) -> dict:
    return {
        "X_ZYXEL_SrvName": "WAN",
        "X_ZYXEL_DefaultGatewayIface": gateway,
        "Status": status,
        "LowerLayers": lower,
    }


def test_parse_wan_traffic_pppoe_uses_ppp_counters() -> None:
    obj = {
        "ipIface": [
            _wan_iface("Ethernet.Link.1", gateway=False),
            _wan_iface("PPP.Interface.2"),
        ],
        "ipIfaceSt": [
            {"BytesReceived": 1, "BytesSent": 1},
            {"BytesReceived": 0, "BytesSent": 0},
        ],
        "pppIfaceSt": [
            {"BytesReceived": 5, "BytesSent": 6},
            {"BytesReceived": 70, "BytesSent": 80},
        ],
    }
    assert _parse_wan_traffic(obj) == {
        "name": "WAN",
        "BytesReceived": 70,
        "BytesSent": 80,
    }


def test_parse_wan_traffic_ipoe_uses_ip_counters() -> None:
    obj = {
        "ipIface": [
            _wan_iface("PPP.Interface.1", status="Down"),
            _wan_iface("Ethernet.VLANTermination.6"),
        ],
        "ipIfaceSt": [
            {"BytesReceived": 0, "BytesSent": 0},
            {"BytesReceived": 9, "BytesSent": 3},
        ],
        "pppIfaceSt": [{"BytesReceived": 0, "BytesSent": 0}],
    }
    assert _parse_wan_traffic(obj) == {
        "name": "WAN",
        "BytesReceived": 9,
        "BytesSent": 3,
    }


def test_parse_wan_traffic_none_up() -> None:
    assert (
        _parse_wan_traffic(
            {
                "ipIface": [_wan_iface("PPP.Interface.1", status="Down")],
                "ipIfaceSt": [{}],
            }
        )
        == {}
    )
