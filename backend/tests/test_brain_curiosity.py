"""Tests for self-directed curiosity (backend/services/brain_curiosity.py).

This closes the loop AKKI_FULL_ARCHITECTURE.md describes as
Question -> Answer -> Gap -> Read -> Better Answer. What has to be proven is
that the brain queues reading based on real weakness in its own answer, never
on invented concepts, and that a failure to queue can never damage an answer
that was already sent.

`select_gaps` is pure, so most of this needs no database.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services import brain_curiosity


def _answer(**kw):
    base = {
        "topics": ["inflation"], "confidence": "strong",
        "dependsOn": [], "produces": [], "derived": [],
    }
    base.update(kw)
    return base


def _concepts(picks):
    return [concept for concept, _ in picks]


def test_unknown_concept_is_queued_for_reading():
    """The clearest gap: the brain had nothing solid, so it should go read."""
    picks = brain_curiosity.select_gaps(_answer(confidence="none"))
    assert picks == [("inflation", brain_curiosity.REASON_UNKNOWN)]


def test_confident_answer_with_solid_evidence_queues_nothing():
    """Curiosity must be driven by weakness. A well-supported answer should
    not generate busywork for the crawler."""
    picks = brain_curiosity.select_gaps(_answer(
        dependsOn=[{"word": "money supply", "count": 9}],
        produces=[{"word": "price rise", "count": 8}],
    ))
    assert picks == []


def test_derived_links_are_queued_so_the_loop_self_corrects():
    """Derived links are the brain's own 2-hop guesses that no source stated.
    Queueing them is what makes the loop verify itself rather than simply
    reinforce what it already believes."""
    picks = brain_curiosity.select_gaps(_answer(
        derived=[{"concept": "interest rate", "via": "demand", "strength": 40.0}],
    ))
    assert ("interest rate", brain_curiosity.REASON_DERIVED) in picks


def test_thinly_evidenced_concepts_are_queued():
    """An edge seen once or twice is a guess worth checking."""
    picks = brain_curiosity.select_gaps(_answer(
        dependsOn=[{"word": "barely seen", "count": 1}, {"word": "well known", "count": 20}],
    ))
    assert ("barely seen", brain_curiosity.REASON_THIN) in picks
    assert "well known" not in _concepts(picks)


def test_only_concepts_the_answer_named_are_queued():
    """The anti-fabrication guarantee: everything queued must trace back to
    something the answer actually said."""
    answer = _answer(
        confidence="none",
        derived=[{"concept": "interest rate"}],
        produces=[{"word": "price rise", "count": 1}],
    )
    named = {"inflation", "interest rate", "price rise"}
    assert set(_concepts(brain_curiosity.select_gaps(answer, limit=99))) <= named


def test_queue_is_capped_so_curiosity_cannot_flood_the_frontier():
    """A flood already drowned the knowledge sources once, per the crawler's
    own seeding comment. Curiosity must trickle."""
    picks = brain_curiosity.select_gaps(_answer(
        derived=[{"concept": f"c{i}"} for i in range(20)],
    ))
    assert len(picks) <= brain_curiosity._MAX_PER_ANSWER


def test_no_duplicates_even_when_a_concept_appears_twice():
    picks = brain_curiosity.select_gaps(_answer(
        confidence="none",
        derived=[{"concept": "inflation"}],
        produces=[{"word": "inflation", "count": 1}],
    ))
    assert _concepts(picks).count("inflation") == 1


def test_empty_answer_is_handled():
    assert brain_curiosity.select_gaps({}) == []


@pytest.mark.asyncio
async def test_queue_reading_is_a_noop_without_concepts():
    assert await brain_curiosity.queue_reading([], client=None, resolver=None) == 0


@pytest.mark.asyncio
async def test_resolver_failure_never_propagates():
    """The answer has already been streamed by the time this runs, so a failure
    here must stay silent rather than surface as a broken request."""
    async def boom(concept, client):
        raise RuntimeError("resolver down")

    with patch.object(brain_curiosity, "AsyncSessionLocal", side_effect=RuntimeError("db down")):
        queued = await brain_curiosity.queue_reading(
            [("x", brain_curiosity.REASON_UNKNOWN)], client=None, resolver=boom)
    assert queued == 0


# ── The loop has to close: reading is judged by whether it taught anything ───

def _record(reads, useful):
    """An effectiveness record as measure_effectiveness would return it."""
    return {"reads": reads, "useful": useful,
            "successRate": useful / reads if reads else 0.0, "avgSentences": 4.0}


def test_a_kind_of_gap_that_never_teaches_anything_stops_being_queued():
    """The point of the feedback signal. Without it curiosity would keep making
    the same losing bet forever, however it turned out."""
    answer = _answer(derived=[{"concept": "interest rate"}])
    useless = {brain_curiosity.REASON_DERIVED: _record(40, 1)}
    assert brain_curiosity.select_gaps(answer, effectiveness=useless) == []


def test_a_kind_of_gap_that_pays_off_keeps_being_queued():
    answer = _answer(derived=[{"concept": "interest rate"}])
    useful = {brain_curiosity.REASON_DERIVED: _record(40, 30)}
    picks = brain_curiosity.select_gaps(answer, effectiveness=useful)
    assert ("interest rate", brain_curiosity.REASON_DERIVED) in picks


def test_a_reason_with_little_history_is_given_its_chance():
    """Judging a reason on one bad read would kill it before it could show
    what it does, so a thin record is not evidence against it."""
    answer = _answer(derived=[{"concept": "interest rate"}])
    barely_tried = {brain_curiosity.REASON_DERIVED: _record(2, 0)}
    picks = brain_curiosity.select_gaps(answer, effectiveness=barely_tried)
    assert ("interest rate", brain_curiosity.REASON_DERIVED) in picks


def test_one_failing_reason_does_not_silence_the_others():
    """Reasons are judged separately: knowing nothing about a concept and
    checking an inference are different bets with different odds."""
    answer = _answer(confidence="none", derived=[{"concept": "interest rate"}])
    effectiveness = {
        brain_curiosity.REASON_DERIVED: _record(40, 1),
        brain_curiosity.REASON_UNKNOWN: _record(40, 35),
    }
    picks = brain_curiosity.select_gaps(answer, effectiveness=effectiveness)
    assert ("inflation", brain_curiosity.REASON_UNKNOWN) in picks
    assert "interest rate" not in _concepts(picks)


def test_no_measurements_yet_means_curiosity_behaves_as_before():
    """An unmeasurable loop must fall back to acting on every reason rather
    than stopping."""
    answer = _answer(confidence="none", derived=[{"concept": "interest rate"}])
    assert brain_curiosity.select_gaps(answer, effectiveness={}) == \
        brain_curiosity.select_gaps(answer)


@pytest.mark.asyncio
async def test_the_reason_travels_with_the_queued_entry():
    """The reason has to reach the frontier row, because that row is what
    carries it through to the visited-page record the measurement reads back.
    If it stopped here, every completed read would be unattributable and the
    loop could never close."""
    captured = {}

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, model, url):
            return None

        async def execute(self, statement):
            captured["params"] = statement.compile().params
            return MagicMock(rowcount=1)

        async def commit(self):
            return None

    async def resolver(concept, client):
        return "https://example.org/x"

    with patch.object(brain_curiosity, "AsyncSessionLocal", lambda: _Session()):
        queued = await brain_curiosity.queue_reading(
            [("inflation", brain_curiosity.REASON_DERIVED)], client=None, resolver=resolver
        )

    assert queued == 1
    assert captured["params"]["source_type"] == "curiosity:derived"
    assert captured["params"]["concept"] == "inflation"
