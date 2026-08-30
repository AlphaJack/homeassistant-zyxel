"""Async client for the Zyxel DAL API (DX3301-T0 and similar VDSL gateways).

The Web-Based Configurator on modern Zyxel gateways exposes a JSON API at
``/cgi-bin/DAL?oid=<name>``. Login uses a hybrid scheme: an RSA public key is
fetched, a random AES-256 key is generated, credentials are AES-CBC encrypted
and the AES key is RSA(PKCS1v1.5) encrypted. Every request/response body is the
envelope ``{"content", "key", "iv"}``.

Firmware quirks handled here (nr7101 gets these wrong on this firmware):
* logout is ``POST /cgi-bin/UserLogout`` with a ``CSRFToken`` header,
* writes carry the session key in the ``CSRFToken`` header,
* the session key rotates on every write (returned in the response body),
* aiohttp must use ``CookieJar(unsafe=True)`` to keep cookies for an IP host.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

import aiohttp
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7
from cryptography.hazmat.primitives.serialization import load_pem_public_key

_LOGGER = logging.getLogger(__name__)

_UA = "HomeAssistant-Zyxel/1.0"
_COMMON_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": _UA,
}


class ZyxelError(Exception):
    """Base error."""


class ZyxelConnectionError(ZyxelError):
    """Raised when the router cannot be reached or returns unusable data."""


class ZyxelAuthError(ZyxelError):
    """Raised when the router rejects the supplied credentials."""


class ZyxelDalClient:
    """Minimal async client for the Zyxel DAL API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        password: str,
        *,
        use_https: bool = False,
        verify_ssl: bool = False,
    ) -> None:
        """Initialise the client. ``session`` should use CookieJar(unsafe=True)."""
        self._session = session
        self._host = host
        self._username = username
        self._password = password
        scheme = "https" if use_https else "http"
        self._base = f"{scheme}://{host}"
        # ``ssl=False`` disables verification for the self-signed device cert.
        self._ssl: Any = None if not use_https else (None if verify_ssl else False)

        self._rsa_pem: str | None = None
        self._aes_key = os.urandom(32)
        self._encryption = False
        self.sessionkey: str | None = None
        self._timeout = aiohttp.ClientTimeout(total=20)

    @property
    def base_url(self) -> str:
        """Return the base URL of the router web UI."""
        return self._base

    # -- crypto ---------------------------------------------------------------

    def _encrypt(self, obj: dict[str, Any]) -> str:
        body = json.dumps(obj, separators=(",", ":")).encode()
        iv = os.urandom(32)
        padder = PKCS7(128).padder()
        padded = padder.update(body) + padder.finalize()
        enc = Cipher(algorithms.AES(self._aes_key), modes.CBC(iv[:16])).encryptor()
        content = enc.update(padded) + enc.finalize()
        assert self._rsa_pem is not None
        pub = load_pem_public_key(self._rsa_pem.encode())
        enc_key = pub.encrypt(  # type: ignore[union-attr]
            base64.b64encode(self._aes_key), asym_padding.PKCS1v15()
        )
        return json.dumps(
            {
                "content": base64.b64encode(content).decode(),
                "key": base64.b64encode(enc_key).decode(),
                "iv": base64.b64encode(iv).decode(),
            }
        )

    def _decrypt(self, payload: dict[str, Any]) -> dict[str, Any]:
        iv = base64.b64decode(payload["iv"])[:16]
        ct = base64.b64decode(payload["content"])
        dec = Cipher(algorithms.AES(self._aes_key), modes.CBC(iv)).decryptor()
        pt = dec.update(ct) + dec.finalize()
        try:
            unpadder = PKCS7(128).unpadder()
            pt = unpadder.update(pt) + unpadder.finalize()
        except ValueError:
            pt = pt.rstrip(b"\x00")
        return json.loads(pt.decode("utf-8"))

    # -- HTTP helpers ---------------------------------------------------------

    async def _get_json(self, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            async with self._session.get(
                url, headers=_COMMON_HEADERS, ssl=self._ssl,
                timeout=self._timeout, **kwargs
            ) as resp:
                if resp.status == 401:
                    raise ZyxelAuthError("Unauthorized")
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise ZyxelConnectionError(str(err)) from err

    # -- login lifecycle ------------------------------------------------------

    async def login(self) -> None:
        """Perform the RSA/AES login handshake."""
        try:
            # 1. establish session cookie
            async with self._session.get(
                f"{self._base}/GetInfoNoLogin", headers=_COMMON_HEADERS,
                ssl=self._ssl, timeout=self._timeout
            ):
                pass
            # 2. RSA public key
            key_resp = await self._get_json(f"{self._base}/getRSAPublickKey")
        except ZyxelAuthError as err:  # pragma: no cover - unusual
            raise ZyxelConnectionError("Login pre-flight failed") from err

        self._rsa_pem = key_resp.get("RSAPublicKey")
        if self._rsa_pem == "None":
            self._rsa_pem = None
        self._encryption = bool(self._rsa_pem)

        login_obj = {
            "Input_Account": self._username,
            "Input_Passwd": base64.b64encode(self._password.encode()).decode(),
            "currLang": "en",
            "RememberPassword": 0,
        }
        body = self._encrypt(login_obj) if self._encryption else json.dumps(login_obj)
        headers = {
            **_COMMON_HEADERS,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": self._base,
            "Referer": f"{self._base}/login",
        }
        try:
            async with self._session.post(
                f"{self._base}/UserLogin",
                data=body.encode(),
                headers=headers,
                ssl=self._ssl,
                timeout=self._timeout,
            ) as resp:
                if resp.status != 200:
                    try:
                        reason = (await resp.json(content_type=None)).get("result")
                    except Exception:  # noqa: BLE001
                        reason = f"HTTP {resp.status}"
                    # "Duplicated login" means another session already holds this
                    # username (the router allows one per user). Credentials are
                    # fine, so treat it as transient rather than an auth failure.
                    if reason and "Duplicated" in str(reason):
                        raise ZyxelConnectionError(f"Login busy: {reason}")
                    raise ZyxelAuthError(f"Login rejected: {reason}")
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise ZyxelConnectionError(str(err)) from err

        if self._encryption:
            data = self._decrypt(data)
        self.sessionkey = data.get("sessionkey")
        if not self.sessionkey:
            raise ZyxelAuthError("No session key returned")

    async def logout(self) -> None:
        """POST logout (GET is ignored by this firmware)."""
        if not self.sessionkey:
            return
        headers = {
            **_COMMON_HEADERS,
            "Origin": self._base,
            "Referer": f"{self._base}/",
            "CSRFToken": str(self.sessionkey),
        }
        try:
            async with self._session.post(
                f"{self._base}/cgi-bin/UserLogout", headers=headers,
                ssl=self._ssl, timeout=self._timeout
            ):
                pass
        except aiohttp.ClientError:  # pragma: no cover - best effort
            pass
        finally:
            self.sessionkey = None

    # -- reads ----------------------------------------------------------------

    async def _dal_get(self, oid: str, *, _retry: bool = True) -> dict[str, Any]:
        """Return the decrypted DAL response, re-authenticating once on 401."""
        if not self.sessionkey:
            await self.login()
        url = f"{self._base}/cgi-bin/DAL?oid={oid}&sessionkey={self.sessionkey}"
        try:
            data = await self._get_json(url)
        except ZyxelAuthError:
            if not _retry:
                raise
            self.sessionkey = None
            await self.login()
            return await self._dal_get(oid, _retry=False)
        return self._decrypt(data) if self._encryption else data

    async def get_object(self, oid: str) -> Any:
        """Return the first ``Object`` for a DAL oid, or None."""
        data = await self._dal_get(oid)
        if data.get("result") != "ZCFG_SUCCESS" or not data.get("Object"):
            _LOGGER.debug("DAL oid %s returned no object", oid)
            return None
        return data["Object"][0]

    async def get_objects(self, oid: str) -> list[dict[str, Any]]:
        """Return the full ``Object`` list for a DAL oid, or an empty list."""
        data = await self._dal_get(oid)
        if data.get("result") != "ZCFG_SUCCESS":
            return []
        return data.get("Object") or []

    async def _get_optional(self, oid: str) -> Any:
        """Read an oid, returning None if the device does not expose it."""
        try:
            return await self.get_object(oid)
        except ZyxelConnectionError:
            # Some models 500/404 on endpoints they do not implement.
            return None

    async def _get_optional_list(self, oid: str) -> list[dict[str, Any]]:
        """Read an oid list, returning [] if the device does not expose it."""
        try:
            return await self.get_objects(oid)
        except ZyxelConnectionError:
            return []

    async def async_get_status(self) -> dict[str, Any]:
        """Fetch and normalise everything the entities need.

        Different device families expose different data: DSL gateways populate
        ``DslChannelInfo`` while cellular/5G routers populate ``cellwan_status``.
        Both are fetched; entities are created per capability by the platforms.
        """
        status = await self.get_object("status") or {}
        traffic_raw = await self._get_optional("Traffic_Status") or {}
        lanhosts_raw = await self._get_optional("lanhosts") or {}
        cellular = await self._get_optional("cellwan_status") or {}
        wan_list = await self._get_optional_list("wan")
        sip_list = await self._get_optional_list("sip_account")
        wlan_list = await self._get_optional_list("wlan")

        dsl_all = status.get("DslChannelInfo") or []
        dsl = _select_active_dsl(dsl_all)

        return {
            "device": status.get("DeviceInfo") or {},
            "system": status.get("SystemInfo") or {},
            "dsl": dsl,
            "dsl_all": dsl_all,
            "cellular": cellular if isinstance(cellular, dict) else {},
            "wan": _select_wan(wan_list),
            "sip": _parse_sip(sip_list),
            "wifi": _parse_wifi(wlan_list),
            "traffic": _parse_traffic(traffic_raw),
            "hosts": _parse_hosts(lanhosts_raw),
        }

    # -- writes ---------------------------------------------------------------

    def _write_headers(self) -> dict[str, str]:
        return {
            **_COMMON_HEADERS,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": self._base,
            "Referer": f"{self._base}/",
            "CSRFToken": str(self.sessionkey),  # session key travels here for writes
        }

    async def async_dal_write(
        self, oid: str, obj: dict[str, Any], method: str = "PUT"
    ) -> dict[str, Any]:
        """Write a DAL object (PUT=set/add, POST=modify, DELETE=remove).

        The session key rotates on every write; the new one is returned in the
        response body and is stored for the next write.
        """
        if not self.sessionkey:
            await self.login()
        url = f"{self._base}/cgi-bin/DAL?oid={oid}"
        body = self._encrypt(obj) if self._encryption else json.dumps(obj)
        try:
            async with self._session.request(
                method, url, data=body.encode(), headers=self._write_headers(),
                ssl=self._ssl, timeout=self._timeout
            ) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise ZyxelConnectionError(str(err)) from err
        if self._encryption:
            data = self._decrypt(data)
        if isinstance(data, dict) and data.get("sessionkey"):
            self.sessionkey = data["sessionkey"]  # consume rotated key
        if data.get("result") != "ZCFG_SUCCESS":
            raise ZyxelConnectionError(
                f"Write to {oid} rejected: {data.get('result')}"
            )
        return data

    async def async_reboot(self) -> None:
        """Reboot the router (POST with CSRFToken header)."""
        if not self.sessionkey:
            await self.login()
        try:
            async with self._session.post(
                f"{self._base}/cgi-bin/Reboot?sessionkey={self.sessionkey}",
                headers=self._write_headers(),
                ssl=self._ssl,
                timeout=self._timeout,
            ) as resp:
                resp.raise_for_status()
        except aiohttp.ClientError as err:
            raise ZyxelConnectionError(str(err)) from err

    async def async_set_wifi_radio(self, band: str, enabled: bool) -> None:
        """Enable/disable a Wi-Fi radio by band ('2.4GHz'/'5GHz').

        Reads the band's main SSID object, flips ``radioenable`` and writes it
        back — the same read-modify-PUT the web UI performs.
        """
        for wlan in await self.get_objects("wlan"):
            if wlan.get("band") == band and wlan.get("MainSSID"):
                wlan["radioenable"] = enabled
                await self.async_dal_write("wlan", wlan, method="PUT")
                return
        raise ZyxelConnectionError(f"No main SSID found for band {band}")

    async def async_wps_pbc(self, band: str) -> None:
        """Start WPS push-button pairing on a band ('2.4GHz'/'5GHz')."""
        for wps in await self.get_objects("wps"):
            if wps.get("Band") == band:
                wps["X_ZYXEL_WPS_EnablePBC"] = True
                await self.async_dal_write("wps", wps, method="PUT")
                return
        raise ZyxelConnectionError(f"No WPS entry for band {band}")


# -- parsing helpers ----------------------------------------------------------


def _select_active_dsl(channels: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick the DSL channel that is Up (falls back to the highest rate)."""
    up = [c for c in channels if str(c.get("Status")) == "Up"]
    if up:
        return max(up, key=lambda c: c.get("DownstreamCurrRate", 0))
    if channels:
        return max(channels, key=lambda c: c.get("DownstreamCurrRate", 0))
    return {}


def _select_wan(wans: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the active WAN (the first with a real IP address)."""
    for wan in wans:
        ip = wan.get("IPAddress")
        if ip and ip not in ("", "0.0.0.0"):
            return {"ip": ip, "type": wan.get("Type"), "name": wan.get("Name")}
    return {}


def _parse_sip(accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalise SIP/VoIP accounts into a compact per-line list."""
    result: list[dict[str, Any]] = []
    for acc in accounts:
        enable = acc.get("Enable")
        result.append(
            {
                "line": acc.get("lineIdx"),
                "number": acc.get("DirectoryNumber"),
                "registered": str(acc.get("Status")) == "Up",
                "enabled": enable is True or str(enable) == "Enabled",
            }
        )
    return result


def _parse_wifi(wlans: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return per-band main-radio state: ``{band: {radio, ssid}}``."""
    result: dict[str, dict[str, Any]] = {}
    for wlan in wlans:
        band = wlan.get("band")
        if band and wlan.get("MainSSID"):
            result[band] = {
                "radio": bool(wlan.get("radioenable")),
                "ssid": wlan.get("SSID"),
            }
    return result


def _parse_traffic(obj: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Flatten Traffic_Status into ``{ifname: stats}`` for named interfaces."""
    result: dict[str, dict[str, Any]] = {}
    for iface_key, st_key in (
        ("ipIface", "ipIfaceSt"),
        ("pppIface", "pppIfaceSt"),
        ("ethIface", "ethIfaceSt"),
    ):
        for iface, st in zip(
            obj.get(iface_key, []), obj.get(st_key, []), strict=False
        ):
            name = iface.get("X_ZYXEL_IfName")
            if name:
                result[name] = st
    return result


def _parse_hosts(obj: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalise lanhosts into a compact per-device list."""
    hosts: list[dict[str, Any]] = []
    for h in obj.get("lanhosts", []):
        mac = h.get("PhysAddress")
        if not mac:
            continue
        name = (
            h.get("DeviceName")
            or h.get("HostName")
            or h.get("curHostName")
            or h.get("Alias")
            or mac
        )
        hosts.append(
            {
                "mac": mac,
                "name": name,
                "ip": h.get("IPAddress"),
                "active": bool(h.get("Active")),
                "connection": h.get("X_ZYXEL_ConnectionType"),
                "access_point": h.get("X_ZYXEL_ConnectedAP"),
                "host_type": h.get("X_ZYXEL_HostType"),
                "interface": h.get("Layer1Interface"),
            }
        )
    return hosts
