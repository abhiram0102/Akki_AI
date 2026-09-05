"""Fetching for the Brain Engine crawler.

One fetcher, for every source. All network access goes through the shared
RobotsChecker and RateLimiter — nothing bypasses either.

This file used to hold a fetcher per site: Wikipedia keyed to `#mw-content-text`
and a `/wiki/` link prefix, arXiv keyed to `blockquote.abstract` and `/abs/`,
and a generic one keyed to HTML's `<p>` element with a fixed list of elements
to strip. It also split sentences on `.!?`. Every one of those encoded
knowledge of a format, which the project's defining constraint forbids, and
every one of them meant a new site needed new code.

They are replaced by `fetch`, which hands the raw response to
`brain_discovery` and lets the structure be worked out from the bytes. The
result is that an unfamiliar site needs no code at all, and the HTML parser
is gone from the path entirely.
"""
import asyncio
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from backend.services import brain_discovery


class RobotsChecker:
    """Fetches and caches robots.txt per domain, checks URLs against it."""

    def __init__(self):
        self._cache: dict[str, RobotFileParser] = {}

    async def allowed(self, url: str, client) -> bool:
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"

        if domain not in self._cache:
            parser = RobotFileParser()
            try:
                resp = await client.get(f"{domain}/robots.txt")
                parser.parse(resp.text.splitlines())
            except Exception:
                parser.parse([])  # no robots.txt reachable -> treat as allow-all
            self._cache[domain] = parser

        return self._cache[domain].can_fetch("*", url)


class RateLimiter:
    """Enforces a minimum interval between requests to the same domain."""

    def __init__(self, min_interval_seconds: float = 1.0):
        self.min_interval = min_interval_seconds
        self._last_request: dict[str, float] = {}

    async def wait(self, url: str) -> None:
        domain = urlparse(url).netloc
        now = time.monotonic()
        last = self._last_request.get(domain)
        if last is not None:
            elapsed = now - last
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
        self._last_request[domain] = time.monotonic()


async def fetch(url: str, client) -> tuple[str, list[str]]:
    """Fetch any document and return its prose and the references it offers.

    Nothing here knows what kind of document it is about to receive. The
    response body goes to `brain_discovery`, which works out this document's
    markup delimiters, sentence boundaries and references from the bytes
    themselves, so the same call handles an encyclopedia article, a paper
    abstract, or a format nobody has seen before.
    """
    resp = await client.get(url)
    structure = brain_discovery.discover_structure(resp.text, url)
    return structure["text"], structure["links"]


async def fetch_structure(url: str, client, narrow_to_shape: bool = True) -> dict:
    """As `fetch`, but returning everything discovered — including the
    sentences already split at boundaries learned from this document, and the
    delimiters and terminators that were discovered along the way, so a caller
    never has to re-split prose with a rule of its own.
    """
    resp = await client.get(url)
    return brain_discovery.discover_structure(
        resp.text, url, narrow_to_shape=narrow_to_shape
    )
