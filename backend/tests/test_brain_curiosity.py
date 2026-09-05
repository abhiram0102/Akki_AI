"""Tests for self-directed curiosity (backend/services/brain_curiosity.py).

This closes the loop AKKI_FULL_ARCHITECTURE.md describes as
Question -> Answer -> Gap -> Read -> Better Answer. What has to be proven is
that the brain queues reading based on real weakness in its own answer, never
on invented concepts, and that a failure to queue can never damage an answer
that was already sent.

`select_gaps` is pure, so most of this needs no database.
"""
import pytest
from unittest.mock import AsyncMock, patch

from backend.services import brain_curiosity


def _answer(**kw):
    base = {
        "topics": ["inflation"], "confidence": "strong",
        "dependsOn": [], "produces": [], "derived": [],
    }
    base.update(kw)
    return base


def test_unknown_concept_is_queued_for_reading():
    """The clearest gap: the brain had nothing solid, so it should go read."""
    picks = brain_curiosity.select_gaps(_answer(confidence="none"))
    assert picks == ["inflation"]


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
    assert "interest rate" in picks


def test_thinly_evidenced_concepts_are_queued():
    """An edge seen once or twice is a guess worth checking."""
    picks = brain_curiosity.select_gaps(_answer(
        dependsOn=[{"word": "barely seen", "count": 1}, {"word": "well known", "count": 20}],
    ))
    assert "barely seen" in picks
    assert "well known" not in picks


def test_only_concepts_the_answer_named_are_queued():
    """The anti-fabrication guarantee: everything queued must trace back to
    something the answer actually said."""
    answer = _answer(
        confidence="none",
        derived=[{"concept": "interest rate"}],
        produces=[{"word": "price rise", "count": 1}],
    )
    named = {"inflation", "interest rate", "price rise"}
    assert set(brain_curiosity.select_gaps(answer, limit=99)) <= named


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
    assert picks.count("inflation") == 1


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
        queued = await brain_curiosity.queue_reading(["x"], client=None, resolver=boom)
    assert queued == 0
