<img src="custom_components/zyxel/brand/icon.png" alt="Zyxel" width="88" align="right"/>

# Zyxel for Home Assistant

[![Marketplace Custom](https://img.shields.io/badge/Marketplace-Custom-41BDF5.svg)](https://www.home-assistant.io/integrations/marketplace/)

Local, poll-based monitoring for **Zyxel gateways** that expose the *Web-Based
Configurator* DAL API (`/cgi-bin/DAL`) — DSL/xDSL, fiber and cellular/5G. It talks
to the device on your LAN over HTTP(S), with no cloud, no account and no extra
Python dependencies.

This is meant to be the **one integration to reach for**. It folds in the cellular
signal metrics from the older, cellular-only
[`ha-zyxel`](https://github.com/zulufoxtrot/ha-zyxel) and adds first-class DSL,
system, traffic and presence data, so DSL and cellular owners can use the same
component.

## Supported devices

| Family | Support | Tested on hardware |
| --- | --- | --- |
| DSL/xDSL gateways (DX, EX, VMG…) | Full | Yes — DX3301-T0 |
| Fiber gateways (same DAL API) | Full | No |
| Cellular / LTE / 5G routers (NR, FWA, LTE…) | Signal + system | No (ported mapping) |
| Other DAL-API devices | Generic | No |

Entities are created **only where the device reports them**, so the list depends on
the model. A DSL gateway gets the DSL sensors; a cellular router gets the signal
sensors; both get system, traffic, presence and reboot. Any field a cellular router
reports that isn't curated is offered as a disabled diagnostic sensor, so nothing is
lost on an unfamiliar model.

Cellular support is a port of the field mapping from
[`nr7101`](https://github.com/pkorpine/nr7101) / `ha-zyxel` and has **not** been
re-tested on cellular hardware — please report results.

## Installation

Requires Home Assistant 2026.8.2 or newer.

[![Open in the Marketplace.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=AlphaJack&repository=homeassistant-zyxel&category=integration)

The button opens this repository in the Marketplace on Home Assistant 2026.11 or
newer, and in HACS on older versions. Select *Install*, then restart if asked.

Without the button:

- **Home Assistant 2026.11 or newer:** go to *Settings → Marketplace*, select
  *Add from link* and enter `AlphaJack/homeassistant-zyxel`. The first time, the Marketplace
  asks you to connect your GitHub account.
- **Older versions with HACS:** open the three-dot menu, choose *Custom
  repositories*, and add this repository as an *Integration*.

Then go to *Settings → Devices & services → Add integration → Zyxel*.

To install by hand, copy `custom_components/zyxel` into
`config/custom_components/` and restart.

## Configuration

| Field | Notes |
| --- | --- |
| Host | e.g. `192.168.1.1` (an `http://…` / `https://…` scheme is handled via the HTTPS toggle) |
| Username / Password | A router account. **A dedicated account is recommended.** |
| Use HTTPS | Optional; the device uses a self-signed certificate. |
| Verify SSL | Leave off for the self-signed certificate. |
| Track network devices | Off by default. Enable to add a presence tracker per LAN/Wi-Fi client (for "who is home" automations); leave off to avoid cluttering HA. |

Configure sets the poll interval (default 60 s, minimum 15 s) and can toggle
device tracking later.

### Recommended: a dedicated Administrator account
Use an **Administrator**-group account. The router restricts a normal *User*
account to a few pages (status, traffic, reboot), so WAN IP, Wi-Fi control, WPS,
VoIP, connected-clients and device tracking — all Administrator-only pages — would
not work.

The router also allows **only one active session per username**. A second login
does not evict the first: the router refuses it with HTTP 401 and
`{"result":"Duplicated login"}` until the first session logs out or idles out
(5 minutes by default). If Home Assistant uses the account you also log into the
web UI with, whichever logs in second is locked out. Create a separate
Administrator account (e.g. `homeassistant`) under *Maintenance → User Account*
and use it here. (The integration treats a "Duplicated login" as a transient error
and retries, so a momentary overlap is not fatal.)

To share one account with the web UI instead, turn on *Release the router session
between refreshes* in the integration options. Home Assistant then logs out after
every refresh, so the account is free in between. Refreshes fail while you are
logged in to the web UI.

## Entities

| Entity | Domain | Needs |
| --- | --- | --- |
| DSL downstream / upstream rate | `sensor` | DSL line |
| DSL status | `sensor` | DSL line |
| DSL link | `binary_sensor` | DSL line |
| Cellular RSSI / RSRP / RSRQ / SINR | `sensor` | cellular |
| Cellular band / access technology | `sensor` | cellular |
| Cellular 5G NSA RSRP / SINR, cell IDs, module temp | `sensor` | cellular |
| Cellular link | `binary_sensor` | cellular |
| WAN IP address, connected clients | `sensor` | any |
| CPU usage, memory used | `sensor` | any |
| Uptime, firmware version | `sensor` | any |
| Host name, domain name | `sensor` | any (disabled by default) |
| WAN bytes sent / received | `sensor` | an active WAN |
| LAN bytes sent / received | `sensor` | any (disabled by default) |
| LAN port link (speed, duplex) | `binary_sensor` | each LAN port (disabled by default) |
| VoIP line registration | `binary_sensor` | each enabled FXS line |
| Wi-Fi radio on/off | `switch` | each Wi-Fi band |
| Extra SSID (e.g. guest) on/off | `switch` | each extra SSID and band |
| Port-forward rule on/off | `switch` | each NAT rule |
| LEDs on/off | `switch` | firmware with `LEDStatus` |
| Reboot | `button` | any |
| WPS pairing | `button` | each Wi-Fi band |
| Per-client presence, Wi-Fi signal and rates | `device_tracker` | opt-in ("Track network devices") |

Device tracking is **off by default** — it creates one device per LAN/Wi-Fi client,
which is only useful for presence automations. Enable it via the "Track network
devices" option (at setup or later) if you want it.

### Scope
The integration covers **monitoring plus the common controls** (Wi-Fi radios and
SSIDs, WPS, LEDs, turning existing port-forward rules on or off, reboot). It
intentionally does **not** manage full device configuration — creating or editing
port forwards, firewall/ACL, QoS, DHCP reservations, DDNS, parental control, VLANs,
etc. — which is better handled in the router's web UI. Firmware upgrades are
ISP/TR-069-driven on carrier units, so there is no update entity.

## Notes & limitations
- Talks to an undocumented, reverse-engineered API; parsing is defensive so entities
  degrade to unavailable rather than crash if a firmware update renames a field.
- DSL rates come from the currently-synchronised channel, in kbit/s.
- LAN traffic counters come from the `br0` bridge. WAN counters come from the
  interface that is the default gateway and up (its PPP link for PPPoE). Use a
  Derivative helper to turn them into throughput.

## Credits
- [`nr7101`](https://github.com/pkorpine/nr7101) by pkorpine and
  [`ha-zyxel`](https://github.com/zulufoxtrot/ha-zyxel) by zulufoxtrot for the
  original cellular protocol and field mapping that the cellular sensors port.

## Development

```bash
uv sync

# lint and formatting
uv run ruff check custom_components tests
uv run ruff format --check custom_components tests

# offline tests (parsing, config flow, capability detection)
uv run pytest tests -q --ignore=tests/test_live.py

# live end-to-end test against a real router
ZYXEL_HOST=192.168.1.1 ZYXEL_USER=homeassistant ZYXEL_PASS=… \
  uv run pytest tests/test_live.py -q -s
```

## License
MIT
