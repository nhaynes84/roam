"""Async client for the ROAM Touch hub.

Thin on purpose: `hub/API.md` is the contract and this file implements it
rather than reinterpreting it. Two rules from that document are load-bearing
here and are easy to get wrong:

* **Sending is REST only, never a WebSocket frame.** One write path means one
  place where failures surface.
* **`/send` rejects C0 control bytes with 400.** Anything control-shaped goes
  to `/interrupt`. The Android client learned this the hard way -- its STOP
  button was silently 400ing for weeks.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


class HubError(RuntimeError):
    """The hub refused, or could not be reached."""


class HubClient:
    def __init__(self, session: aiohttp.ClientSession, base_url: str, token: str):
        self._session = session
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}

    @property
    def base_url(self) -> str:
        return self._base

    @property
    def ws_url(self) -> str:
        # ⚠️ ws:// against the HTTP base -- not wss://. Plain HTTP is correct
        # here *because* WireGuard is the encryption layer; that reasoning
        # dies the moment the hub binds anything other than the tailnet.
        return self._base.replace("http://", "ws://").replace("https://", "wss://") + "/ws"

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._base}{path}"
        try:
            async with self._session.request(
                method, url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=10), **kwargs
            ) as resp:
                body = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise HubError(f"{method} {path} -> {resp.status}: {body}")
                return body
        except aiohttp.ClientError as exc:
            raise HubError(f"{method} {path} failed: {exc}") from exc

    async def health(self) -> dict:
        return await self._request("GET", "/health")

    async def channels(self) -> list[dict]:
        data = await self._request("GET", "/channels")
        return data.get("channels", data if isinstance(data, list) else [])

    async def history(self, pane_id: str, limit: int = 12) -> list[dict]:
        pane = pane_id.replace("%", "%25")
        data = await self._request("GET", f"/channels/{pane}/history?limit={limit}")
        return data.get("events", data if isinstance(data, list) else [])

    async def send(self, pane_id: str, text: str) -> dict:
        pane = pane_id.replace("%", "%25")
        return await self._request(
            "POST", f"/channels/{pane}/send", json={"text": text, "origin": "voice"}
        )

    async def spawn(self, label: str, command: str = "claude", cwd: str | None = None) -> dict:
        payload: dict[str, Any] = {"command": command, "label": label, "origin": "voice"}
        if cwd:
            payload["cwd"] = cwd
        data = await self._request("POST", "/channels", json=payload)
        return data.get("channel", data)
