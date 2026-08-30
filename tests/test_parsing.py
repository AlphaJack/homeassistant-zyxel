"""Offline unit tests for the DAL parsing helpers."""

from __future__ import annotations

from custom_components.zyxel.api import (
    _parse_hosts,
    _parse_traffic,
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
            },
            {"HostName": "no-mac"},  # dropped: no PhysAddress
        ]
    }
    hosts = _parse_hosts(obj)
    assert len(hosts) == 1
    assert hosts[0]["mac"] == "AA:BB:CC:DD:EE:FF"
    assert hosts[0]["name"] == "laptop"
    assert hosts[0]["active"] is True
