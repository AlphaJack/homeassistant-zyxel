"""Constants for the Zyxel integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "zyxel"

CONF_USE_HTTPS = "use_https"
CONF_VERIFY_SSL = "verify_ssl"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_TRACK_DEVICES = "track_devices"
CONF_RELEASE_SESSION = "release_session"

DEFAULT_HOST = "192.168.1.1"
DEFAULT_USE_HTTPS = False
DEFAULT_VERIFY_SSL = False
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 15
# Off by default: presence tracking creates one device per LAN client, which is
# only useful for "who is home" automations and otherwise clutters HA.
DEFAULT_TRACK_DEVICES = False
# Off by default: logging in on every refresh costs a few extra requests. On,
# the account is free for the web UI between refreshes.
DEFAULT_RELEASE_SESSION = False

UPDATE_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

MANUFACTURER = "Zyxel"
