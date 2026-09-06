from collections import Counter
from unittest.mock import AsyncMock, MagicMock
import pytest
from backend.services import brain_learn

class _Result:
    def __init__(self, rows): self._rows = rows
    def __aiter__(self):
        async def gen():
            for r in self._rows: yield r
        return gen()

@pytest.mark.asyncio
async def test_apply_to_graph_upserts_and_returns_counts():
    session = MagicMock()
    # 1st run: concept upsert -> rows with word/frequency/total
    # 2nd run: edge upsert -> rows with cause/effect/count
    # 3rd run: g2 writeback -> no rows needed
    session.run = AsyncMock(side_effect=[
        _Result([{"word": "fire", "frequency": 3, "total": 10},
                 {"word": "heat", "frequency": 2, "total": 10}]),
        _Result([{"cause": "fire", "effect": "heat", "count": 2}]),
        _Result([]),
    ])
    out = await brain_learn.apply_to_graph(session, Counter({"fire": 1, "heat": 1}),
                                           Counter({("fire", "heat"): 1}))
    assert out["new_edges"] == 1
    assert session.run.await_count == 3


@pytest.mark.asyncio
async def test_resolve_source_reads_a_search_page_rather_than_an_api(monkeypatch):
    """Resolution goes through the same discovery used on every other page.
    Nothing parses a site's search API, and no address is constructed from a
    title, so a search page in any format resolves the same way."""
    async def fake_fetch(url, client, narrow_to_shape=True):
        assert "neurons" in url
        return {"text": "", "sentences": [], "delimiters": ("<", ">"),
                "terminators": ["."],
                "links": ["https://example.org/topic/Neuron",
                          "https://example.org/topic/Axon"]}
    monkeypatch.setattr("backend.services.brain_fetchers.fetch_structure", fake_fetch)
    got = await brain_learn.resolve_source("neurons", MagicMock())
    assert got == "https://example.org/topic/Neuron"


@pytest.mark.asyncio
async def test_resolve_source_returns_nothing_rather_than_guessing_an_address(monkeypatch):
    """The old fallback guessed a URL by title-casing the term and joining it
    with underscores — one site's address convention applied universally, which
    produced a confidently wrong address for every other site. Failing to
    resolve must now report nothing so the caller can say it does not know."""
    async def boom(url, client, narrow_to_shape=True):
        raise Exception("net")
    monkeypatch.setattr("backend.services.brain_fetchers.fetch_structure", boom)
    assert await brain_learn.resolve_source("quantum tunneling", MagicMock()) is None


@pytest.mark.asyncio
async def test_resolve_source_trusts_a_redirect_over_ranking_the_landed_page(monkeypatch):
    """Found live: searching "graphene" 302-redirects straight to the real
    article, but the article's own outbound links ("Discovery of graphene",
    "GrapheneOS", "Graphite", ...) were then ranked as if they were search
    results, and even a fixed ranking picked the wrong one among them. The
    search engine's own redirect is stronger evidence than anything derived
    from the page it lands on, so it must win outright -- references are
    never even consulted when this signal is present."""
    async def fake_fetch(url, client, narrow_to_shape=True):
        return {
            "text": "", "sentences": [], "delimiters": ("<", ">"), "terminators": ["."],
            "redirectedTo": "https://example.org/wiki/Graphene",
            "references": [
                {"url": "https://example.org/wiki/Discovery_of_graphene",
                 "text": "Discovery of graphene"},
                {"url": "https://example.org/wiki/GrapheneOS", "text": "GrapheneOS"},
            ],
        }
    monkeypatch.setattr("backend.services.brain_fetchers.fetch_structure", fake_fetch)
    got = await brain_learn.resolve_source("graphene", MagicMock())
    assert got == "https://example.org/wiki/Graphene"


@pytest.mark.asyncio
async def test_resolve_source_prefers_exact_match_over_a_longer_superstring(monkeypatch):
    """Found live: asking about "graphene" resolved to a page titled
    "grapheneos" instead, because plain word-overlap counting scored a
    substring match ("graphene" inside "grapheneos") the same as a real
    word match. The reference whose anchor text IS the query exactly must
    win regardless of what else happens to contain it as a substring."""
    async def fake_fetch(url, client, narrow_to_shape=True):
        return {
            "text": "", "sentences": [], "delimiters": ("<", ">"), "terminators": ["."],
            "references": [
                {"url": "https://example.org/wiki/GrapheneOS", "text": "GrapheneOS"},
                {"url": "https://example.org/wiki/Graphene", "text": "Graphene"},
            ],
        }
    monkeypatch.setattr("backend.services.brain_fetchers.fetch_structure", fake_fetch)
    got = await brain_learn.resolve_source("graphene", MagicMock())
    assert got == "https://example.org/wiki/Graphene"


@pytest.mark.asyncio
async def test_resolve_source_prefers_token_boundary_over_bare_substring(monkeypatch):
    """A reference where the query appears as a real, bounded word/phrase
    must outrank one where it only appears embedded inside a longer word,
    even with no exact-match reference present at all."""
    async def fake_fetch(url, client, narrow_to_shape=True):
        return {
            "text": "", "sentences": [], "delimiters": ("<", ">"), "terminators": ["."],
            "references": [
                {"url": "https://example.org/wiki/Supergraphene", "text": "Supergraphene alloy"},
                {"url": "https://example.org/wiki/Graphene_sheet", "text": "Graphene sheet structure"},
            ],
        }
    monkeypatch.setattr("backend.services.brain_fetchers.fetch_structure", fake_fetch)
    got = await brain_learn.resolve_source("graphene", MagicMock())
    assert got == "https://example.org/wiki/Graphene_sheet"


@pytest.mark.asyncio
async def test_resolve_source_breaks_ties_within_a_tier_by_word_overlap(monkeypatch):
    """Within the same match tier (here: neither is an exact or bounded
    match to the full two-word query), more overlapping words is still a
    real, if weaker, signal and should win the tie."""
    async def fake_fetch(url, client, narrow_to_shape=True):
        return {
            "text": "", "sentences": [], "delimiters": ("<", ">"), "terminators": ["."],
            "references": [
                {"url": "https://example.org/wiki/Machine", "text": "Machine parts"},
                {"url": "https://example.org/wiki/MachineLearningOverview",
                 "text": "Machine learning overview"},
            ],
        }
    monkeypatch.setattr("backend.services.brain_fetchers.fetch_structure", fake_fetch)
    got = await brain_learn.resolve_source("machine learning", MagicMock())
    assert got == "https://example.org/wiki/MachineLearningOverview"


@pytest.mark.asyncio
async def test_resolve_source_returns_nothing_when_the_page_offers_no_references(monkeypatch):
    async def empty(url, client, narrow_to_shape=True):
        return {"text": "", "sentences": [], "links": [],
                "delimiters": None, "terminators": []}
    monkeypatch.setattr("backend.services.brain_fetchers.fetch_structure", empty)
    assert await brain_learn.resolve_source("nothing here", MagicMock()) is None


@pytest.mark.asyncio
async def test_learn_concept_fetches_extracts_and_applies(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(brain_learn, "resolve_source",
                        AsyncMock(return_value="https://example.org/topic/Neuron"))

    fetch_mock = AsyncMock(return_value={
        "text": "Fire causes heat. Heat spreads energy.",
        "sentences": ["Fire causes heat.", "Heat spreads energy."],
        "links": [], "delimiters": ("<", ">"), "terminators": ["."],
    })
    monkeypatch.setattr(brain_learn, "fetch_structure", fetch_mock)

    def fake_extract(sentence):
        if sentence.startswith("Fire"):
            return [("fire", "heat")]
        if sentence.startswith("Heat"):
            return [("heat", "energy")]
        return []
    monkeypatch.setattr(brain_learn, "extract_dependencies", fake_extract)

    apply_mock = AsyncMock(return_value={"new_concepts": 3, "new_edges": 2})
    monkeypatch.setattr(brain_learn, "apply_to_graph", apply_mock)

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=MagicMock())
    session_cm.__aexit__ = AsyncMock(return_value=False)
    neo4j_driver = MagicMock()
    neo4j_driver.session = MagicMock(return_value=session_cm)

    out = await brain_learn.learn_concept("neurons", client, neo4j_driver, follow_links=0)

    assert out["term"] == "neurons"
    assert out["resolved_title"] == "https://example.org/topic/Neuron"
    assert out["new_concepts"] == 3
    assert out["new_edges"] == 2
    assert out["sources"] == ["https://example.org/topic/Neuron"]
    fetch_mock.assert_awaited_once_with("https://example.org/topic/Neuron", client)
    apply_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_learn_concept_anchors_queried_term(monkeypatch):
    """The generic subject/object extractor learns the article's contents
    (e.g. "ledger", "transaction") but never anchors the queried term itself
    ("blockchain") into the graph. learn_concept must add an explicit anchor
    node + edges so the queried term is answerable after learning."""
    client = MagicMock()
    monkeypatch.setattr(brain_learn, "resolve_source",
                        AsyncMock(return_value="https://example.org/topic/Blockchain"))

    fetch_mock = AsyncMock(return_value={
        "text": "Ledger records transaction. Transaction updates block. Block forms chain.",
        "sentences": [
            "Ledger records transaction.",
            "Transaction updates block.",
            "Block forms chain.",
        ],
        "links": [], "delimiters": ("<", ">"), "terminators": ["."],
    })
    monkeypatch.setattr(brain_learn, "fetch_structure", fetch_mock)

    def fake_extract(sentence):
        if sentence.startswith("Ledger"):
            return [("ledger", "transaction")]
        if sentence.startswith("Transaction"):
            return [("transaction", "block")]
        if sentence.startswith("Block"):
            return [("block", "chain")]
        return []
    monkeypatch.setattr(brain_learn, "extract_dependencies", fake_extract)

    captured = {}

    async def fake_apply_to_graph(session, word_freq, edge_counts):
        captured["word_freq"] = Counter(word_freq)
        captured["edge_counts"] = Counter(edge_counts)
        return {"new_concepts": len(word_freq), "new_edges": len(edge_counts)}
    monkeypatch.setattr(brain_learn, "apply_to_graph", fake_apply_to_graph)

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=MagicMock())
    session_cm.__aexit__ = AsyncMock(return_value=False)
    neo4j_driver = MagicMock()
    neo4j_driver.session = MagicMock(return_value=session_cm)

    await brain_learn.learn_concept("blockchain", client, neo4j_driver, follow_links=0)

    assert "blockchain" in captured["word_freq"]
    assert any(cause == "blockchain" for (cause, _effect) in captured["edge_counts"])
