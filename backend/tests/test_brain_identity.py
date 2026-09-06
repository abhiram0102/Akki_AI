"""Identity resolution: does it find the same thing under different names,
without any list of names being written down?"""
import pytest

from backend.services import brain_identity


class _Doc:
    def __init__(self, vector):
        import numpy as np
        self.vector = np.array(vector, dtype="float32")
        self.vector_norm = float((self.vector @ self.vector) ** 0.5)
        self.has_vector = True


class _FakeVectors:
    """Stands in for the language model, so these tests check the ALGORITHM
    rather than what a particular model happens to believe."""
    def __init__(self, table):
        self.table = table

    def __call__(self, word):
        return _Doc(self.table.get(word, [0.0, 0.0, 1.0]))


@pytest.fixture(autouse=True)
def _no_real_model(monkeypatch):
    monkeypatch.setattr(brain_identity, "_vectors", lambda: _FakeVectors({
        # same direction = the same thing under two names
        "nucleus": [1.0, 0.0, 0.0],
        "nucleus accumben": [0.99, 0.14, 0.0],
        # a different direction entirely
        "photosynthesis": [0.0, 1.0, 0.0],
        "oxygen": [0.0, 0.5, 0.87],
    }))


def test_it_finds_the_same_thing_under_two_names():
    pairs = brain_identity.duplicate_pairs(
        ["nucleus", "nucleus accumben", "photosynthesis"])
    found = {(a, b) for _, a, b in pairs}
    assert ("nucleus", "nucleus accumben") in found or \
           ("nucleus accumben", "nucleus") in found


def test_it_does_not_merge_things_that_are_merely_related():
    """Photosynthesis and oxygen belong together in the graph and are NOT the
    same node. Relatedness is what edges are for; identity is a stronger claim."""
    pairs = brain_identity.duplicate_pairs(["photosynthesis", "oxygen"])
    assert not pairs, f"merged two related but distinct concepts: {pairs}"


def test_equivalence_is_transitive():
    """a == b and b == c has to put all three under one name, or the graph
    keeps a chain of two-way links that never actually meet."""
    canonical = brain_identity.resolve([(0.99, "a", "b"), (0.98, "b", "c")])
    assert len({canonical["a"], canonical["b"], canonical["c"]}) == 1


def test_the_shorter_name_wins():
    """The longer form is the more specific one, so knowledge folds into the
    general name rather than a specialisation of it."""
    canonical = brain_identity.resolve([(0.99, "nucleus", "nucleus accumben")])
    assert canonical["nucleus accumben"] == "nucleus"


def test_no_synonym_list_exists_in_the_module():
    """The defining constraint of the project. Identity is decided by a model
    that never saw this graph, not by names written down here."""
    import pathlib
    source = pathlib.Path(brain_identity.__file__).read_text(encoding="utf-8")
    body = source.split('"""', 2)[-1]  # skip the module docstring
    for pair in ("nucleus", "oxygen", "dioxygen", "cloud"):
        assert f'"{pair}"' not in body and f"'{pair}'" not in body, (
            f"{pair!r} is named in the module body -- that is a synonym list"
        )


def test_antonyms_are_the_known_failure_of_vector_identity():
    """Pinned because it is a property of the method, not a threshold to tune.

    Distributional vectors place opposites together, because opposites occur in
    identical contexts. On the live graph, mutual-nearest matching at 0.85
    proposed `north`==`south`, `east`==`west`, `november`==`september` and
    `democrats`==`republicans`. Any future identity rule must be checked
    against cases of this shape before it is believed, whatever its aggregate
    score says."""
    import numpy as np
    # Two concepts that occupy nearly the same contexts and mean the opposite.
    opposite = {"north": [1.0, 0.0, 0.0], "south": [0.99, 0.1, 0.0]}

    class _Doc:
        def __init__(self, v):
            self.vector = np.array(v, dtype="float32")
            self.vector_norm = float((self.vector @ self.vector) ** 0.5)
            self.has_vector = True

    import backend.services.brain_identity as bi
    original = bi._vectors
    bi._vectors = lambda: (lambda w: _Doc(opposite.get(w, [0.0, 0.0, 1.0])))
    try:
        pairs = bi.duplicate_pairs(["north", "south"])
    finally:
        bi._vectors = original
    assert pairs, (
        "cosine similarity no longer pairs antonyms -- if a later change made "
        "identity behaviour-based rather than vector-based, delete this test "
        "rather than restoring the weakness it documents"
    )
