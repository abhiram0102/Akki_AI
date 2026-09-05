"""Tests for answer formation (backend/services/brain_answer.py).

What these have to prove is that every sentence the brain speaks is built from
edges that are actually in the graph — no fabricated content, no wording that
survives when the supporting evidence is removed. Graph access is mocked; no
Neo4j required.
"""
import contextlib

import pytest
from unittest.mock import AsyncMock, patch


@contextlib.contextmanager
def _stack(patches):
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        yield

from backend.services import brain_answer, brain_meaning, brain_query, brain_service


def _graph(depends=None, produces=None, derived=None, convergences=None,
           multi=None, sense=None, vocabulary=None):
    """Patch every graph read brain_answer performs.

    `convergences` feeds the two-concept path; `multi` feeds the single-topic
    path, where the topic's own branches are used as independent origins.
    """
    return (
        # Sense lookup is stubbed by default so these tests never open a real
        # meaning store; the sense-specific tests below supply their own.
        patch.object(brain_meaning, "disambiguate", lambda c, q: sense),
        patch.object(brain_meaning, "sense_vocabulary", lambda c, i: vocabulary or set()),
        patch.object(brain_service, "discover_convergence",
                     AsyncMock(return_value={"convergencePoints": multi or []})),
        patch.object(brain_service, "_top_dependencies", AsyncMock(return_value=depends or [])),
        patch.object(brain_service, "_top_associations", AsyncMock(return_value=produces or [])),
        patch.object(brain_service, "infer_links", AsyncMock(return_value=derived or [])),
        patch.object(brain_service, "discover",
                     AsyncMock(return_value={"convergencePoints": convergences or []})),
    )


async def _build(plan, **kw):
    with _stack(_graph(**kw)):
        return await brain_answer.build(plan)


@pytest.mark.asyncio
async def test_summary_names_only_concepts_present_in_the_graph():
    """The anti-fabrication test: every concept named in the spoken sentence
    must appear in one of the returned evidence sections."""
    plan = brain_query.QueryPlan(intent=brain_query.DEFINE, topics=["inflation"], raw="inflation")
    out = await _build(
        plan,
        depends=[{"word": "money supply", "g2": 9.0, "count": 6}],
        produces=[{"word": "price rise", "g2": 8.0, "count": 5}],
    )
    assert "money supply" in out["summary"]
    assert "price rise" in out["summary"]
    known = {i["word"] for i in out["dependsOn"] + out["produces"]}
    assert known == {"money supply", "price rise"}


@pytest.mark.asyncio
async def test_both_edge_directions_are_reported_separately():
    """Function 7 step 6 splits "depends on" from "produces". They come from
    opposite traversals and must not be merged into one undifferentiated list."""
    plan = brain_query.QueryPlan(intent=brain_query.DEFINE, topics=["x"], raw="x")
    out = await _build(
        plan,
        depends=[{"word": "upstream", "g2": 9.0, "count": 6}],
        produces=[{"word": "downstream", "g2": 9.0, "count": 6}],
    )
    assert [i["word"] for i in out["dependsOn"]] == ["upstream"]
    assert [i["word"] for i in out["produces"]] == ["downstream"]


@pytest.mark.asyncio
async def test_intent_changes_which_direction_leads_the_sentence():
    """Same graph, different question. Asking why something happens must lead
    with what it rests on; asking what it leads to must lead with what it
    drives. Identical evidence, different emphasis."""
    ev = {
        "depends": [{"word": "upstream", "g2": 9.0, "count": 6}],
        "produces": [{"word": "downstream", "g2": 9.0, "count": 6}],
    }
    cause = await _build(brain_query.QueryPlan(brain_query.CAUSE, ["x"], "why x"), **ev)
    effect = await _build(brain_query.QueryPlan(brain_query.EFFECT, ["x"], "what x causes"), **ev)
    assert cause["summary"].index("upstream") < cause["summary"].index("downstream")
    assert effect["summary"].index("downstream") < effect["summary"].index("upstream")


@pytest.mark.asyncio
async def test_derived_link_is_marked_as_the_brains_own_reasoning():
    """The claim that makes this not retrieval has to be stated as such, and
    must name the intermediate concept that produced it so it stays checkable."""
    plan = brain_query.QueryPlan(brain_query.DEFINE, ["x"], "x")
    out = await _build(
        plan,
        produces=[{"word": "p", "g2": 9.0, "count": 6}],
        derived=[{"concept": "surprise", "via": "bridge", "strength": 40.0, "derived": True}],
    )
    assert "surprise" in out["summary"]
    assert "bridge" in out["summary"]


@pytest.mark.asyncio
async def test_no_derived_claim_when_nothing_was_derived():
    """The reasoning sentence must disappear entirely when the graph produced
    no derived link, rather than being asserted with nothing behind it."""
    plan = brain_query.QueryPlan(brain_query.DEFINE, ["x"], "x")
    out = await _build(plan, produces=[{"word": "p", "g2": 9.0, "count": 6}], derived=[])
    assert "worked out myself" not in out["summary"]


@pytest.mark.asyncio
async def test_empty_graph_produces_an_admission_not_an_invention():
    """With nothing in the graph the brain must say so. This is the failure
    mode that matters most: a system that fabricates when it knows nothing."""
    plan = brain_query.QueryPlan(brain_query.DEFINE, ["obscure"], "obscure")
    out = await _build(plan)
    assert "don't know" in out["summary"]
    assert out["gap"] is not None
    assert out["confidence"] == "none"


@pytest.mark.asyncio
async def test_one_sided_knowledge_is_admitted_as_such():
    """Knowing effects but not causes is a real, nameable gap, and Function 7
    step 8 depends on it being detected."""
    plan = brain_query.QueryPlan(brain_query.DEFINE, ["x"], "x")
    out = await _build(plan, produces=[{"word": "p", "g2": 9.0, "count": 6}])
    assert out["gap"] is not None
    assert "rests on" in out["gap"]


@pytest.mark.asyncio
async def test_confidence_tracks_how_often_evidence_was_seen():
    """Confidence must come from edge counts, not be a constant."""
    plan = brain_query.QueryPlan(brain_query.DEFINE, ["x"], "x")
    strong = await _build(plan, depends=[
        {"word": "a", "g2": 9.0, "count": 9}, {"word": "b", "g2": 9.0, "count": 8}])
    weak = await _build(plan, depends=[{"word": "a", "g2": 9.0, "count": 1}])
    assert strong["confidence"] == "strong"
    assert weak["confidence"] != "strong"


@pytest.mark.asyncio
async def test_provenance_is_carried_through():
    """The URLs the brain read were previously computed and discarded."""
    plan = brain_query.QueryPlan(brain_query.DEFINE, ["x"], "x")
    with _stack(_graph(produces=[{"word": "p", "g2": 9.0, "count": 6}])):
        out = await brain_answer.build(plan, sources=["https://example.org/x"])
    assert out["provenance"] == ["https://example.org/x"]


@pytest.mark.asyncio
async def test_unprompted_observation_is_extra_not_a_repeat():
    """The Jarvis-like touch: volunteer something the user did not ask for.
    It must be a different fact from the one already in the summary."""
    plan = brain_query.QueryPlan(brain_query.DEFINE, ["x"], "x")
    out = await _build(
        plan,
        produces=[{"word": "p", "g2": 9.0, "count": 6}],
        derived=[
            {"concept": "first", "via": "v1", "strength": 40.0, "derived": True},
            {"concept": "second", "via": "v2", "strength": 20.0, "derived": True},
        ],
    )
    assert out["observation"] is not None
    assert "second" in out["observation"]
    assert "second" not in out["summary"]


@pytest.mark.asyncio
async def test_gap_never_contradicts_confidence():
    """Regression: the answer reported strong confidence and "still thin" in
    the same breath because the two were computed from different thresholds."""
    plan = brain_query.QueryPlan(brain_query.DEFINE, ["x"], "x")
    out = await _build(
        plan,
        depends=[{"word": "a", "g2": 9.0, "count": 8}, {"word": "b", "g2": 7.0, "count": 6}],
        produces=[{"word": "c", "g2": 8.0, "count": 7}, {"word": "d", "g2": 6.0, "count": 5}],
    )
    assert out["confidence"] == "strong"
    assert out["gap"] is None


@pytest.mark.asyncio
async def test_spoken_answer_starts_capitalised():
    """Concept names are stored lowercase, so a sentence opening with one has
    to be capitalised or the answer reads like a fragment."""
    plan = brain_query.QueryPlan(brain_query.DEFINE, ["inflation"], "inflation")
    out = await _build(plan, depends=[{"word": "money supply", "g2": 9.0, "count": 8}])
    assert out["summary"][0].isupper()


@pytest.mark.asyncio
async def test_caller_supplied_edges_are_not_refetched():
    """The endpoint has already read out-edges to decide whether to learn.
    Re-reading them would waste a round trip and could return something
    different, leaving the spoken answer disagreeing with its own evidence."""
    plan = brain_query.QueryPlan(brain_query.DEFINE, ["x"], "x")
    supplied = [{"word": "given", "g2": 9.0, "count": 6}]
    assoc = AsyncMock(return_value=[{"word": "refetched", "g2": 9.0, "count": 6}])
    with patch.object(brain_service, "_top_dependencies", AsyncMock(return_value=[])), \
         patch.object(brain_service, "_top_associations", assoc), \
         patch.object(brain_service, "infer_links", AsyncMock(return_value=[])):
        out = await brain_answer.build(plan, produces=supplied, derived=[])
    assoc.assert_not_called()
    assert [i["word"] for i in out["produces"]] == ["given"]


@pytest.mark.asyncio
async def test_single_topic_question_still_runs_convergence():
    """Function 7 step 5 applies to every question. A one-concept question
    previously skipped convergence entirely, so the capability the architecture
    doc calls "the moment of intelligence" was unreachable from the commonest
    kind of query. The topic's own branches become the independent origins."""
    plan = brain_query.QueryPlan(brain_query.DEFINE, ["inflation"], "inflation")
    out = await _build(
        plan,
        produces=[{"word": "a", "g2": 9.0, "count": 6}, {"word": "b", "g2": 8.0, "count": 6},
                  {"word": "c", "g2": 7.0, "count": 6}],
        multi=[{"concept": "hub", "originCount": 3, "origins": ["a", "b", "c"], "avgDepth": 1.5}],
    )
    assert [p["concept"] for p in out["convergences"]] == ["hub"]
    assert "hub" in out["observation"]


@pytest.mark.asyncio
async def test_convergence_never_reports_a_seed_as_a_discovery():
    """A branch turning up as a meeting point of its own siblings is circular,
    not a finding."""
    plan = brain_query.QueryPlan(brain_query.DEFINE, ["inflation"], "inflation")
    out = await _build(
        plan,
        produces=[{"word": "a", "g2": 9.0, "count": 6}, {"word": "b", "g2": 8.0, "count": 6},
                  {"word": "c", "g2": 7.0, "count": 6}],
        multi=[{"concept": "a", "originCount": 3, "origins": ["b", "c"], "avgDepth": 1.0},
               {"concept": "inflation", "originCount": 3, "origins": ["a", "b"], "avgDepth": 1.0}],
    )
    assert out["convergences"] == []


@pytest.mark.asyncio
async def test_too_few_branches_skips_convergence_entirely():
    """With fewer origins than the minimum there is nothing to converge, and
    the traversal must not be attempted."""
    plan = brain_query.QueryPlan(brain_query.DEFINE, ["x"], "x")
    conv = AsyncMock(return_value={"convergencePoints": []})
    with patch.object(brain_service, "discover_convergence", conv),          patch.object(brain_service, "_top_dependencies", AsyncMock(return_value=[])),          patch.object(brain_service, "_top_associations", AsyncMock(return_value=[])),          patch.object(brain_service, "infer_links", AsyncMock(return_value=[])):
        await brain_answer.build(plan, produces=[{"word": "only", "count": 6}], derived=[])
    conv.assert_not_called()


@pytest.mark.asyncio
async def test_no_dangling_pronoun_when_the_first_clause_is_missing():
    """Regression: with no incoming edges the summary opened "It drives galaxy",
    a pronoun with nothing to refer to."""
    plan = brain_query.QueryPlan(brain_query.DEFINE, ["dark matter"], "dark matter")
    out = await _build(plan, produces=[{"word": "galaxy", "g2": 3.0, "count": 1}])
    assert out["summary"].startswith("Dark matter drives")


# ── The chosen sense has to change the answer, not just label it ─────────────

_SENSE = {"sense": 1, "label": ["passion", "conviction"], "contextCount": 6,
          "example": "He argued with such fire that the audience applauded."}


@pytest.mark.asyncio
async def test_evidence_is_narrowed_to_the_sense_being_asked_about():
    """The graph is single-sense: every use of a word collapses onto one node,
    so a concept's neighbours mix its meanings. Asking about the emotional
    sense of a word must not come back talking about oxygen and fuel."""
    plan = brain_query.QueryPlan(brain_query.DEFINE, ["fire"], "his fire and passion")
    out = await _build(
        plan,
        depends=[{"word": "oxygen", "g2": 9.0, "count": 8},
                 {"word": "conviction", "g2": 8.0, "count": 6}],
        produces=[{"word": "fuel", "g2": 9.0, "count": 8},
                  {"word": "passion", "g2": 8.0, "count": 6}],
        sense=_SENSE,
        vocabulary={"passion", "conviction", "argued", "audience"},
    )
    assert out["senseFiltered"] is True
    assert [i["word"] for i in out["dependsOn"]] == ["conviction"]
    assert [i["word"] for i in out["produces"]] == ["passion"]
    assert "oxygen" not in out["summary"] and "fuel" not in out["summary"]


@pytest.mark.asyncio
async def test_narrowing_never_empties_an_answer():
    """A sense whose vocabulary happens not to overlap the graph's neighbours
    is a reason to be less sure which meaning applies, not a reason to report
    knowing nothing about a concept the brain has genuinely read."""
    plan = brain_query.QueryPlan(brain_query.DEFINE, ["fire"], "his fire")
    out = await _build(
        plan,
        depends=[{"word": "oxygen", "g2": 9.0, "count": 8}],
        produces=[{"word": "fuel", "g2": 9.0, "count": 8}],
        sense=_SENSE,
        vocabulary={"nothing", "in", "common"},
    )
    assert out["senseFiltered"] is False
    assert [i["word"] for i in out["dependsOn"]] == ["oxygen"]


@pytest.mark.asyncio
async def test_an_unambiguous_concept_is_not_narrowed_at_all():
    plan = brain_query.QueryPlan(brain_query.DEFINE, ["x"], "x")
    out = await _build(plan, depends=[{"word": "a", "g2": 9.0, "count": 8}])
    assert out["sense"] is None
    assert out["senseFiltered"] is False
    assert [i["word"] for i in out["dependsOn"]] == ["a"]


@pytest.mark.asyncio
async def test_the_answer_says_which_meaning_it_settled_on():
    """A confident answer about the wrong sense of a word is the most
    misleading thing here, so the choice has to be stated, not implied."""
    plan = brain_query.QueryPlan(brain_query.DEFINE, ["fire"], "his fire and passion")
    out = await _build(
        plan,
        produces=[{"word": "passion", "g2": 8.0, "count": 6}],
        sense=_SENSE,
        vocabulary={"passion"},
    )
    assert "passion" in out["observation"]
