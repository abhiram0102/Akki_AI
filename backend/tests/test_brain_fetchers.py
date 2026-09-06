"""Tests for the brain crawler's fetching, robots.txt checker, and rate
limiter — using a mocked httpx client, no real network calls.

There used to be a per-site fetcher here and a test keyed to Wikipedia's own
container id and link prefix. Both are gone: one fetcher now serves every
source, so the test that matters is that it reads a document in a format it
has never been told about.
"""
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.brain_fetchers import RobotsChecker, RateLimiter, fetch, fetch_structure


def _mock_response(text: str, status_code: int = 200, history=None, url=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.history = history or []
    resp.url = url or ""
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
        # asyncio.sleep can return a few ms early under scheduler load, so allow
        # a small tolerance rather than asserting the exact interval (this
        # assertion was observed to flake at ~0.187 against a hard 0.2 bound).
        # The gap must still be substantial — proving the second call waited.
        assert elapsed >= 0.18

    async def test_different_domains_not_rate_limited_against_each_other(self):
        limiter = RateLimiter(min_interval_seconds=5.0)
        start = time.monotonic()
        await limiter.wait("https://en.wikipedia.org/wiki/A")
        await limiter.wait("https://arxiv.org/abs/1234")
        elapsed = time.monotonic() - start
        assert elapsed < 1.0


class TestFetch:
    async def test_reads_html_without_any_html_rule(self):
        """No container id, no link prefix, no element names. The same call
        that handles this handles a site nobody has written code for."""
        html = "<html><body>" + "".join(
            f"<p><a href='/topic/Heat{i}'>Heat {i}</a> "
            f"Fire causes heat in the number {i} case here.</p>"
            for i in range(25)
        ) + "</body></html>"
        client = AsyncMock()
        client.get.return_value = _mock_response(html)

        text, links = await fetch("https://example.org/topic/Fire", client)
        assert "Fire causes heat" in text
        assert "https://example.org/topic/Heat7" in links
        # Markup must not leak into what gets read as prose.
        assert "<" not in text and "href" not in text

    async def test_reads_a_format_that_does_not_exist(self):
        """The decisive one. This document uses `|`/`~` for markup and `§` to
        end sentences. A fetcher carrying a hidden HTML parser returns nothing
        here; discovery returns the prose and the references."""
        doc = "".join(
            f"|ref→/topic/Heat{i}~Fire causes heat in the number {i} case here§ |/ref~"
            for i in range(25)
        )
        client = AsyncMock()
        client.get.return_value = _mock_response(doc)

        structure = await fetch_structure("https://example.org/topic/Fire", client)
        assert structure["delimiters"] == ("|", "~")
        assert "§" in structure["terminators"]
        assert any("Fire causes heat" in s for s in structure["sentences"])
        assert "https://example.org/topic/Heat7" in structure["links"]

    async def test_sentences_come_back_already_split(self):
        """The caller must never have to re-split prose with a rule of its own,
        which is what the old ". " split in the crawler was."""
        doc = "<html><body>" + "".join(
            f"<p>Statement number {i} runs to a reasonable length here.</p>"
            for i in range(25)
        ) + "</body></html>"
        client = AsyncMock()
        client.get.return_value = _mock_response(doc)

        structure = await fetch_structure("https://example.org/start", client)
        assert len(structure["sentences"]) >= 5
        assert all(len(s.split()) >= 5 for s in structure["sentences"])

    async def test_redirected_to_is_none_when_no_redirect_happened(self):
        client = AsyncMock()
        client.get.return_value = _mock_response("<p>Some ordinary page content here.</p>")
        structure = await fetch_structure("https://example.org/page", client)
        assert structure["redirectedTo"] is None

    async def test_redirected_to_reports_the_final_address_after_a_real_redirect(self):
        """A caller resolving an address from a search page (brain_learn.
        resolve_source) needs to know when the HTTP transport itself already
        redirected to a single answer, rather than rendering a results list --
        that is a stronger signal than anything derived from the landed-on
        page's own links."""
        client = AsyncMock()
        client.get.return_value = _mock_response(
            "<p>The article we actually landed on.</p>",
            history=["https://example.org/search?q=term"],
            url="https://example.org/wiki/Term",
        )
        structure = await fetch_structure("https://example.org/search?q=term", client)
        assert structure["redirectedTo"] == "https://example.org/wiki/Term"

    async def test_redirected_to_ignores_a_scheme_only_upgrade(self):
        """An http -> https redirect is not a search engine answering a
        question -- it is still the same page. Found worth checking (not yet
        live-observed as a false positive) after the graphene fix landed."""
        client = AsyncMock()
        client.get.return_value = _mock_response(
            "<p>Still the same page, just upgraded.</p>",
            history=["http://example.org/wiki/Term"],
            url="https://example.org/wiki/Term",
        )
        structure = await fetch_structure("http://example.org/wiki/Term", client)
        assert structure["redirectedTo"] is None

    async def test_redirected_to_ignores_a_bare_trailing_slash_normalisation(self):
        client = AsyncMock()
        client.get.return_value = _mock_response(
            "<p>Still the same page, just normalised.</p>",
            history=["https://example.org/wiki/Term"],
            url="https://example.org/wiki/Term/",
        )
        structure = await fetch_structure("https://example.org/wiki/Term", client)
        assert structure["redirectedTo"] is None
