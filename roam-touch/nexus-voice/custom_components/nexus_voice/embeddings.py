"""Embeddings for channel matching, via the local Ollama on talos.

⚠️ Every call here is best-effort. If Ollama is unreachable the matcher must
degrade to string matching, never fail the utterance -- a voice assistant that
answers "I couldn't reach the embedding service" is worse than one that
occasionally opens a new channel.

⚠️ Ollama unloads an idle model after ~5 minutes, which turns a 120 ms call
into a ~600 ms one. `keep_alive` pins it; the cost is a few hundred MB of RAM
on a 48 GB box.
"""

from __future__ import annotations

import logging

import aiohttp

from .const import EMBED_MODEL

_LOGGER = logging.getLogger(__name__)

#: Measured on talos 2026-08-21: 596 ms cold, 120 ms warm.
_TIMEOUT = aiohttp.ClientTimeout(total=6)


class Embedder:
    def __init__(self, session: aiohttp.ClientSession, base_url: str):
        self._session = session
        self._base = base_url.rstrip("/")
        #: label-or-document text -> vector. Keyed by the TEXT, so a Claude
        #: session summary that drifts invalidates its own cache entry with no
        #: bookkeeping.
        self._cache: dict[str, tuple[float, ...]] = {}

    async def embed(self, text: str, cache: bool = False) -> tuple[float, ...] | None:
        if not text.strip():
            return None
        if cache and text in self._cache:
            return self._cache[text]
        try:
            async with self._session.post(
                f"{self._base}/api/embeddings",
                json={"model": EMBED_MODEL, "prompt": text[:6000], "keep_alive": -1},
                timeout=_TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("ollama returned %s; falling back to lexical", resp.status)
                    return None
                vector = tuple((await resp.json()).get("embedding") or ())
        except (aiohttp.ClientError, TimeoutError) as exc:
            _LOGGER.warning("ollama unreachable (%s); falling back to lexical", exc)
            return None
        if not vector:
            return None
        if cache:
            self._cache[text] = vector
        return vector

    def forget(self, keep: set[str]) -> None:
        """Drop cached vectors for text no channel carries any more."""
        for text in [t for t in self._cache if t not in keep]:
            del self._cache[text]
