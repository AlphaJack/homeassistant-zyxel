<img src="custom_components/zyxel/brand/icon.png" alt="Zyxel" width="88" align="right"/>

# Zyxel for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)

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

Requires Home Assistant 2024.12 or newer.

In HACS, open the three-dot menu, choose *Custom repositories*, and add this
repository as an *Integration*. Install it and restart. Then go to
*Settings → Devices & services → Add integration → Zyxel*.

To install by hand, copy `custom_components/zyxel` into `config/custom_components/`
and restart.

## Configuration

| Field | Notes |
| --- | --- |
| Host | e.g. `192.168.1.1` (an `http://…` / `https://…` scheme is handled via the HTTPS toggle) |
| Username / Password | A router account. **A dedicated account is recommended.** |
| Use HTTPS | Optional; the device uses a self-signed certificate. |
| Verify SSL | Leave off for the self-signed certificate. |

Configure sets the poll interval (default 60 s, minimum 15 s).

### Recommended: a dedicated router account
The router allows **only one active session per username**. If Home Assistant uses
the account you also log into the web UI with, they evict each other ("Duplicated
login"). Create a separate account (e.g. `homeassistant`) under *Maintenance → User
Account* and use it here. (The integration treats a "Duplicated login" as a
transient error and retries, so a momentary overlap is not fatal.)

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
| LAN bytes sent / received | `sensor` | any (disabled by default) |
| VoIP line registration | `binary_sensor` | each enabled FXS line |
| Wi-Fi radio on/off | `switch` | each Wi-Fi band |
| Reboot | `button` | any |
| WPS pairing | `button` | each Wi-Fi band |
| Per-client presence | `device_tracker` | any (disabled by default) |

Device-tracker entities are created for every client the router has seen and are
**disabled by default** — enable the ones you care about.

### Scope
The integration covers **monitoring plus the common controls** (Wi-Fi on/off, WPS,
reboot). It intentionally does **not** manage full device configuration — port
forwarding, firewall/ACL, QoS, DHCP reservations, DDNS, parental control, VLANs,
etc. — which is better handled in the router's web UI. Firmware upgrades are
ISP/TR-069-driven on carrier units, so there is no update entity.

## Notes & limitations
- Talks to an undocumented, reverse-engineered API; parsing is defensive so entities
  degrade to unavailable rather than crash if a firmware update renames a field.
- DSL rates come from the currently-synchronised channel, in kbit/s.
- LAN traffic counters come from the `br0` bridge; WAN-side naming varies by mode.

## Credits
- [`nr7101`](https://github.com/pkorpine/nr7101) by pkorpine and
  [`ha-zyxel`](https://github.com/zulufoxtrot/ha-zyxel) by zulufoxtrot for the
  original cellular protocol and field mapping that the cellular sensors port.

## Development

```bash
uv venv --python 3.13 .venv
.venv/bin/pip install pytest-homeassistant-custom-component

# offline tests (parsing, config flow, capability detection)
.venv/bin/python -m pytest tests -q --ignore=tests/test_live.py

# live end-to-end test against a real router
ZYXEL_HOST=192.168.1.1 ZYXEL_USER=homeassistant ZYXEL_PASS=… \
  .venv/bin/python -m pytest tests/test_live.py -q -s
```

## Related

Another Home Assistant integration by the same author:

[<img src="https://raw.githubusercontent.com/AlphaJack/homeassistant-sanremo-coffee-machines/main/custom_components/sanremo/brand/logo.png" alt="Sanremo Coffee Machines" height="40"/>](https://github.com/AlphaJack/homeassistant-sanremo-coffee-machines)

## License
MIT
