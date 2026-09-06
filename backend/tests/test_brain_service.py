"""Tests for the brain query service — mocked Neo4j session/driver, no live
graph required."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.services import brain_service


def _make_result(records: list[dict]):
    """An async-iterable fake Neo4j result yielding the given record dicts,
    each accessed by dict-style key lookup (e.g. record["word"])."""
    async def _iter():
        for r in records:
            yield r
    result = MagicMock()
    result.__aiter__ = lambda self=result: _iter()
    return result


def _fake_driver_with_sequential_results(results_in_call_order: list[list[dict]]):
    """Each successive call to session.run() returns the next list of fake
    records in sequence — used because this service issues multiple
    structurally-identical-looking queries (e.g. the same Cypher shape
    called once per concept in convergence mode) that a query-text-based
    fake couldn't distinguish, but which must return different fake data
    per call."""
    driver = MagicMock()
    call_queue = [_make_result(r) for r in results_in_call_order]

    async def run(query, **params):
        return call_queue.pop(0)

    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = session_cm
    session_cm.__aexit__.return_value = False
    session_cm.run = run
    driver.session.return_value = session_cm
    return driver


class TestDiscoverSingleConcept:
    async def test_returns_ranked_associations(self, monkeypatch):
        driver = _fake_driver_with_sequential_results([
            [{"word": "heat", "g2": 42.5, "count": 10}],
        ])
        monkeypatch.setattr(brain_service, "get_driver", lambda: driver)
        result = await brain_service.discover("fire", None)
        assert result["concept"] == "fire"
        assert result["associations"][0]["word"] == "heat"
        assert result["associations"][0]["g2"] == 42.5


class TestDiscoverConvergence:
    async def test_returns_convergence_points(self, monkeypatch):
        # First call = _reachable_with_depth("fire"), second = _reachable_with_depth("music")
        driver = _fake_driver_with_sequential_results([
            [{"word": "transformation", "depth": 2}],
            [{"word": "transformation", "depth": 3}],
        ])
        monkeypatch.setattr(brain_service, "get_driver", lambda: driver)
        result = await brain_service.discover("fire", "music")
        assert any(c["concept"] == "transformation" for c in result["convergencePoints"])


def _fake_driver_by_c1(reach_by_seed: dict):
    """Fake driver that returns each seed's reachable set based on the `c1`
    query param — needed for convergence, which iterates seeds in
    nondeterministic set order."""
    driver = MagicMock()

    async def run(query, **params):
        seed = params.get("c1")
        recs = [{"word": w, "depth": d} for w, d in reach_by_seed.get(seed, {}).items()]
        return _make_result(recs)

    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = session_cm
    session_cm.__aexit__.return_value = False
    session_cm.run = run
    driver.session.return_value = session_cm
    return driver


class TestMultiOriginConvergence:
    async def test_ranks_by_number_of_independent_origins(self, monkeypatch):
        # 'transformation' is reached from all three unrelated seeds → strongest.
        reach = {
            "fire": {"transformation": 2, "energy": 1},
            "music": {"transformation": 3, "rhythm": 1},
            "biology": {"transformation": 2, "cell": 1},
        }
        monkeypatch.setattr(brain_service, "get_driver", lambda: _fake_driver_by_c1(reach))
        result = await brain_service.discover_convergence(["fire", "music", "biology"], min_origins=2)
        pts = result["convergencePoints"]
        assert pts[0]["concept"] == "transformation"
        assert pts[0]["originCount"] == 3
        assert pts[0]["origins"] == ["biology", "fire", "music"]
        # single-origin concepts (energy/rhythm/cell) are below the floor.
        assert all(p["originCount"] >= 2 for p in pts)

    async def test_seeds_themselves_are_not_convergence_points(self, monkeypatch):
        reach = {"fire": {"music": 1, "x": 2}, "music": {"fire": 1, "x": 2}}
        monkeypatch.setattr(brain_service, "get_driver", lambda: _fake_driver_by_c1(reach))
        result = await brain_service.discover_convergence(["fire", "music"], min_origins=2)
        concepts = {p["concept"] for p in result["convergencePoints"]}
        assert "fire" not in concepts and "music" not in concepts
        assert "x" in concepts  # reached from both, and not itself a seed

    async def test_too_few_seeds_returns_error(self, monkeypatch):
        monkeypatch.setattr(brain_service, "get_driver", lambda: _fake_driver_by_c1({}))
        result = await brain_service.discover_convergence(["fire"], min_origins=2)
        assert "error" in result


def _capturing_driver(records: list[dict] | None = None, captured: dict | None = None):
    """A fake driver whose session.run() records the Cypher params it was
    called with (into `captured`) and returns `records` as the result."""
    if captured is None:
        captured = {}
    if records is None:
        records = []
    driver = MagicMock()

    async def run(query, **params):
        captured.update(params)
        return _make_result(records)

    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = session_cm
    session_cm.__aexit__.return_value = False
    session_cm.run = run
    driver.session.return_value = session_cm
    return driver


class TestMinCountFloorIsParameterized:
    """`/api/brain/ask` needs to answer freshly-learned concepts (which only
    have count=1 edges) at a relaxed floor, while discover/converge keep the
    strict default floor of 2 — so min_count must be a real parameter bound
    into the Cypher, not the hardcoded MIN_EDGE_COUNT constant."""

    async def test_top_associations_defaults_to_module_floor(self, monkeypatch):
        captured: dict = {}
        monkeypatch.setattr(brain_service, "get_driver", lambda: _capturing_driver(captured=captured))
        await brain_service._top_associations("fire")
        assert captured["min_count"] == brain_service.MIN_EDGE_COUNT

    async def test_top_associations_forwards_explicit_min_count(self, monkeypatch):
        captured: dict = {}
        monkeypatch.setattr(brain_service, "get_driver", lambda: _capturing_driver(captured=captured))
        await brain_service._top_associations("fire", min_count=1)
        assert captured["min_count"] == 1

    async def test_reachable_with_depth_defaults_to_module_floor(self, monkeypatch):
        captured: dict = {}
        monkeypatch.setattr(brain_service, "get_driver", lambda: _capturing_driver(captured=captured))
        await brain_service._reachable_with_depth("fire")
        assert captured["min_count"] == brain_service.MIN_EDGE_COUNT

    async def test_reachable_with_depth_forwards_explicit_min_count(self, monkeypatch):
        captured: dict = {}
        monkeypatch.setattr(brain_service, "get_driver", lambda: _capturing_driver(captured=captured))
        await brain_service._reachable_with_depth("fire", min_count=1)
        assert captured["min_count"] == 1


class TestGetStatus:
    async def test_reads_pg_stats_and_neo4j_counts(self, monkeypatch):
        # First call = concept count query, second call = edge count query
        driver = _fake_driver_with_sequential_results([
            [{"count": 500}],
            [{"count": 1200}],
        ])
        monkeypatch.setattr(brain_service, "get_driver", lambda: driver)

        pg_session = AsyncMock()
        stats_row = MagicMock(total_pages=42, total_sentences=1000, updated_at=None)
        frontier_count = MagicMock(scalar=MagicMock(return_value=17))
        pg_session.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=stats_row)),
            frontier_count,
        ])

        result = await brain_service.get_status(pg_session)
        assert result["totalPages"] == 42
        assert result["frontierSize"] == 17


def _fake_driver_with_background(reach_by_seed: dict, pool: list[str]):
    """A driver that answers both queries convergence now makes: the random
    seed draw used to measure the graph's noise floor, and the per-seed
    traversal."""
    driver = MagicMock()

    async def run(query, **params):
        if "rand()" in query:
            return _make_result([{"word": w} for w in pool])
        seed = params.get("c1")
        return _make_result(
            [{"word": w, "depth": d} for w, d in reach_by_seed.get(seed, {}).items()]
        )

    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = session_cm
    session_cm.__aexit__.return_value = False
    session_cm.run = run
    driver.session.return_value = session_cm
    return driver


class TestConvergenceAgainstChance:
    @pytest.fixture(autouse=True)
    def _clear_measured_floor(self):
        """The noise floor is cached per graph, so it has to be cleared between
        tests or one test's graph is measured against another's."""
        brain_service._BACKGROUND.clear()
        yield
        brain_service._BACKGROUND.clear()

    async def test_a_concept_everything_reaches_is_ranked_below_a_rare_one(self, monkeypatch):
        """The measured failure this fixes. On the live graph, seeding three
        unrelated topics returned "dna" from all three origins and "time" from
        two -- and ranked by origin count alone they sit in one list, with no
        way to tell that "time" turns up for 38% of RANDOM seed triples while
        "dna" turns up for none of them.

        Here "common" is reachable from every seed in the graph and "rare" from
        almost none, so "common" is reached from more origins. It must still
        rank below."""
        pool = [f"seed{i}" for i in range(10)]
        reach = {s: {"common": 1} for s in pool}
        reach.update({
            "alpha": {"common": 1, "rare": 2},
            "beta": {"common": 1, "rare": 2},
            "gamma": {"common": 1},
        })
        monkeypatch.setattr(brain_service, "get_driver",
                            lambda: _fake_driver_with_background(reach, pool))
        result = await brain_service.discover_convergence(
            ["alpha", "beta", "gamma"], min_origins=2)
        points = {p["concept"]: p for p in result["convergencePoints"]}
        assert points["common"]["originCount"] == 3
        assert points["rare"]["originCount"] == 2
        assert result["convergencePoints"][0]["concept"] == "rare", (
            "a concept reached from every random seed outranked a rare one "
            "purely on origin count"
        )
        assert points["rare"]["surprise"] > points["common"]["surprise"]

    async def test_the_noise_floor_is_measured_from_the_graph_not_a_word_list(self, monkeypatch):
        """The same word must be treated as noise or as signal depending on how
        the graph behaves, not on what the word is. A stopword list would be
        the hardcoded knowledge this project exists to avoid -- and would be
        wrong for any graph built from something other than English prose."""
        pool = [f"seed{i}" for i in range(10)]
        seeds = ["alpha", "beta"]
        reach = {"alpha": {"time": 1}, "beta": {"time": 1}}

        everywhere = {s: {"time": 1} for s in pool}
        everywhere.update(reach)
        monkeypatch.setattr(brain_service, "get_driver",
                            lambda: _fake_driver_with_background(everywhere, pool))
        noisy = await brain_service.discover_convergence(seeds, min_origins=2)

        brain_service._BACKGROUND.clear()
        nowhere = {s: {"unrelated": 1} for s in pool}
        nowhere.update(reach)
        monkeypatch.setattr(brain_service, "get_driver",
                            lambda: _fake_driver_with_background(nowhere, pool))
        telling = await brain_service.discover_convergence(seeds, min_origins=2)

        noisy_score = next(p["surprise"] for p in noisy["convergencePoints"]
                           if p["concept"] == "time")
        telling_score = next(p["surprise"] for p in telling["convergencePoints"]
                             if p["concept"] == "time")
        assert telling_score > noisy_score, (
            "the same concept scored the same in both graphs, so the floor is "
            "not being read from the graph"
        )

    async def test_ranking_falls_back_to_origin_count_without_a_measured_floor(self, monkeypatch):
        """A graph too small or too new to sample must still answer, rather
        than scoring everything as equally surprising and ordering at random."""
        reach = {
            "fire": {"transformation": 2, "energy": 1},
            "music": {"transformation": 3, "rhythm": 1},
            "biology": {"transformation": 2, "cell": 1},
        }
        monkeypatch.setattr(brain_service, "get_driver",
                            lambda: _fake_driver_with_background(reach, []))
        result = await brain_service.discover_convergence(
            ["fire", "music", "biology"], min_origins=2)
        assert result["convergencePoints"][0]["concept"] == "transformation"

    async def test_surprise_grows_as_a_concept_gets_rarer(self):
        """The score has to be monotone in rarity, or ranking by it means
        nothing."""
        common = brain_service._surprise(2, 3, 0.5)
        uncommon = brain_service._surprise(2, 3, 0.05)
        rare = brain_service._surprise(2, 3, 0.005)
        assert rare > uncommon > common
