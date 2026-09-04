"""Source fetchers for the Brain Engine crawler.

Each fetcher returns (text, discovered_links). All network access goes
through the shared RobotsChecker and RateLimiter — no fetcher bypasses
either.
"""
import asyncio
import re
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup


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


def _extract_sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in parts if 5 <= len(s.split()) <= 40]


async def fetch_wikipedia(url: str, client) -> tuple[str, list[str]]:
    """Fetch a Wikipedia article: main text + in-article links."""
    resp = await client.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")

    body = soup.select_one("#mw-content-text") or soup
    paras = body.select("p")
    text = " ".join(p.get_text() for p in paras)
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()

    links: list[str] = []
    seen: set[str] = set()
    for a in body.select("a[href]"):
        href = a.get("href", "")
        if href.startswith("https://en.wikipedia.org/wiki/"):
            full = href
        elif href.startswith("/wiki/"):
            full = "https://en.wikipedia.org" + href
        else:
            continue
        path = full.replace("https://en.wikipedia.org/wiki/", "")
        if ":" in path or "#" in path:
            continue
        if full not in seen:
            seen.add(full)
            links.append(full)

    return text, links[:50]


async def fetch_arxiv(url: str, client) -> tuple[str, list[str]]:
    """Fetch an arXiv abstract page: abstract text + linked paper IDs."""
    resp = await client.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")

    abstract_block = soup.select_one("blockquote.abstract")
    text = abstract_block.get_text(" ", strip=True) if abstract_block else ""
    text = re.sub(r'^Abstract:\s*', '', text)

    links: list[str] = []
    seen: set[str] = set()
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if "/abs/" in href:
            full = href if href.startswith("http") else f"https://arxiv.org{href}"
            if full not in seen:
                seen.add(full)
                links.append(full)

    return text, links[:30]


async def fetch_generic_article(url: str, client) -> tuple[str, list[str]]:
    """Fetch a plain article page (used for RSS-discovered news articles):
    paragraph text + outbound links found in the article body."""
    resp = await client.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    paras = soup.select("p")
    text = " ".join(p.get_text() for p in paras)
    text = re.sub(r'\s+', ' ', text).strip()

    links: list[str] = []
    seen: set[str] = set()
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if href.startswith("http") and href not in seen:
            seen.add(href)
            links.append(href)

    return text, links[:20]


async def fetch_rss_news(feed_url: str, client) -> list[tuple[str, str]]:
    """Parse an RSS feed, return (article_url, title) for each entry."""
    import feedparser
    resp = await client.get(feed_url)
    parsed = feedparser.parse(resp.text)
    return [(entry.link, entry.get("title", "")) for entry in parsed.entries if entry.get("link")]
