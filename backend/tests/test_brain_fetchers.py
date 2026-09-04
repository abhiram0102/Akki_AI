"""Tests for the brain crawler's source fetchers, robots.txt checker, and
rate limiter — using a mocked httpx client, no real network calls."""
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.brain_fetchers import RobotsChecker, RateLimiter, fetch_wikipedia


def _mock_response(text: str, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


class TestRobotsChecker:
    async def test_allows_when_no_disallow_matches(self):
        client = AsyncMock()
        client.get.return_value = _mock_response("User-agent: *\nDisallow: /admin/\n")
        checker = RobotsChecker()
        assert await checker.allowed("https://en.wikipedia.org/wiki/Fire", client) is True

    async def test_disallows_matching_path(self):
        client = AsyncMock()
        client.get.return_value = _mock_response("User-agent: *\nDisallow: /wiki/Special:\n")
        checker = RobotsChecker()
        assert await checker.allowed("https://en.wikipedia.org/wiki/Special:Random", client) is False

    async def test_caches_robots_txt_per_domain(self):
        client = AsyncMock()
        client.get.return_value = _mock_response("User-agent: *\nDisallow:\n")
        checker = RobotsChecker()
        await checker.allowed("https://en.wikipedia.org/wiki/A", client)
        await checker.allowed("https://en.wikipedia.org/wiki/B", client)
        assert client.get.call_count == 1  # robots.txt fetched once, reused


class TestRateLimiter:
    async def test_enforces_minimum_gap_per_domain(self):
        limiter = RateLimiter(min_interval_seconds=0.2)
        start = time.monotonic()
        await limiter.wait("https://en.wikipedia.org/wiki/A")
        await limiter.wait("https://en.wikipedia.org/wiki/B")
        elapsed = time.monotonic() - start
        assert elapsed >= 0.2

    async def test_different_domains_not_rate_limited_against_each_other(self):
        limiter = RateLimiter(min_interval_seconds=5.0)
        start = time.monotonic()
        await limiter.wait("https://en.wikipedia.org/wiki/A")
        await limiter.wait("https://arxiv.org/abs/1234")
        elapsed = time.monotonic() - start
        assert elapsed < 1.0


class TestFetchWikipedia:
    async def test_extracts_text_and_links(self):
        html = """
        <html><body><div id="mw-content-text">
        <p>Fire causes heat. Heat leads to energy.</p>
        <a href="/wiki/Heat">Heat</a>
        <a href="/wiki/Special:Random">Random</a>
        <a href="https://external.com/page">External</a>
        </div></body></html>
        """
        client = AsyncMock()
        client.get.return_value = _mock_response(html)
        text, links = await fetch_wikipedia("https://en.wikipedia.org/wiki/Fire", client)
        assert "Fire causes heat" in text
        assert "https://en.wikipedia.org/wiki/Heat" in links
        assert not any("Special:" in l for l in links)
        assert not any("external.com" in l for l in links)
