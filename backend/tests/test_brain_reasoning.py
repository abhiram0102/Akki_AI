"""Tests for the typed-relation projection that makes reasoning possible.

The pure logic here — mapping a verb to a typed relation, and orienting the
typed edge relative to how `brain_relations` stored the observation — is where a
wrong edge would silently compose into a wrong inference. Direction is the thing
most worth pinning: a REQUIRES or PART_OF edge points OPPOSITE to the stored
(subject, object) order, and getting that backwards would invert every chain
built on it. No I/O; the graph traversal itself needs a live Neo4j and is
covered by the live measurement, not here.

`brain_relations` stores what `brain_nlp.extract_relations` emits, so a row's
(subject, relation, object) order is the extractor's, documented per case below.
"""
from backend.services import brain_reasoning as R
from backend.services.brain_nlp import FORWARD_CONNECTIVES, BACKWARD_CONNECTIVES


# ── relation_for: verb -> (type, flip) ────────────────────────────────────────

def test_forward_connectives_are_causes_unflipped():
    for verb in FORWARD_CONNECTIVES:
        assert R.relation_for(verb) == ("CAUSES", False), verb


def test_backward_connectives_are_requires_flipped():
    for verb in BACKWARD_CONNECTIVES:
        assert R.relation_for(verb) == ("REQUIRES", True), verb


def test_containment_verbs_are_part_of_flipped():
    assert R.relation_for("contain") == ("PART_OF", True)
    assert R.relation_for("comprise") == ("PART_OF", True)


def test_prevention_verbs_are_prevents_unflipped():
    assert R.relation_for("prevent") == ("PREVENTS", False)
    assert R.relation_for("inhibit") == ("PREVENTS", False)


def test_unknown_verb_is_not_typed():
    assert R.relation_for("walk") is None
    assert R.relation_for("be") is None
    assert R.relation_for("") is None


def test_typing_is_case_insensitive():
    assert R.relation_for("Cause") == ("CAUSES", False)
    assert R.relation_for("  REQUIRE ") == ("REQUIRES", True)


# ── typed_edges_from_triples: the direction that matters ──────────────────────
# A row is (subject, verb, object, count) exactly as brain_relations stores it.

def _edge(buckets, rel):
    """The single edge in `rel`'s bucket, or fail if there isn't exactly one."""
    edges = buckets[rel]
    assert len(edges) == 1, f"{rel}: expected 1 edge, got {edges}"
    return edges[0]


def test_causes_keeps_stored_order():
    # "deforestation causes flooding" -> stored (deforestation, cause, flooding)
    out = R.typed_edges_from_triples([("deforestation", "cause", "flooding", 5)])
    e = _edge(out, "CAUSES")
    assert (e["src"], e["dst"]) == ("deforestation", "flooding")


def test_requires_points_from_dependent_to_prerequisite():
    # "combustion requires oxygen" is stored by the extractor prerequisite-first
    # as (oxygen, require, combustion). The typed edge must read the natural way:
    # combustion REQUIRES oxygen — i.e. dependent -> prerequisite.
    out = R.typed_edges_from_triples([("oxygen", "require", "combustion", 3)])
    e = _edge(out, "REQUIRES")
    assert (e["src"], e["dst"]) == ("combustion", "oxygen")


def test_part_of_points_from_part_to_whole():
    # "cell contains nucleus" -> stored (cell, contain, nucleus). The part is the
    # object; the typed edge must be nucleus PART_OF cell.
    out = R.typed_edges_from_triples([("cell", "contain", "nucleus", 6)])
    e = _edge(out, "PART_OF")
    assert (e["src"], e["dst"]) == ("nucleus", "cell")


def test_prevents_keeps_stored_order():
    out = R.typed_edges_from_triples([("vaccine", "prevent", "disease", 2)])
    e = _edge(out, "PREVENTS")
    assert (e["src"], e["dst"]) == ("vaccine", "disease")


def test_untyped_verbs_produce_no_edges():
    out = R.typed_edges_from_triples([("x", "walk", "y", 9), ("p", "be", "q", 4)])
    assert all(len(edges) == 0 for edges in out.values())


def test_repeats_fold_into_summed_count_and_collect_verbs():
    # Two causal verbs between the same pair fold into one edge, counts summed,
    # both verbs kept as evidence of what named the relation.
    out = R.typed_edges_from_triples([
        ("smoking", "cause", "cancer", 4),
        ("smoking", "lead", "cancer", 3),
    ])
    e = _edge(out, "CAUSES")
    assert e["count"] == 7
    assert e["verbs"] == ["cause", "lead"]


def test_self_loops_and_blank_endpoints_are_dropped():
    out = R.typed_edges_from_triples([
        ("a", "cause", "a", 5),        # self-loop
        ("", "cause", "b", 5),         # blank subject
        ("a", "cause", "", 5),         # blank object
    ])
    assert all(len(edges) == 0 for edges in out.values())


def test_count_defaults_to_one_when_absent():
    # The crawler projects per-page triples with no explicit count.
    out = R.typed_edges_from_triples([("rain", "cause", "flood")])
    assert _edge(out, "CAUSES")["count"] == 1


# ── module invariants that guard the traversal ────────────────────────────────

def test_prevents_is_not_chainable():
    # PREVENTS is not transitive (A prevents B, B prevents C does not make A
    # prevent C); reason() must refuse to chain it. If someone adds it to the
    # transitive set, this fails before it can produce a wrong inference.
    assert "PREVENTS" not in R._TRANSITIVE
    assert set(R._TRANSITIVE) == {"CAUSES", "REQUIRES", "PART_OF"}


def test_every_relation_type_has_a_projection_bucket():
    out = R.typed_edges_from_triples([])
    assert set(out.keys()) == set(R.RELATION_TYPES)
