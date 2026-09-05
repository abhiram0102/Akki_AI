"""Guards the evaluation baseline.

The unit tests prove specific behaviours still work. This one answers a
different question: did a change quietly make the brain read less of a page, or
extract worse relations, across the whole stored corpus? That is the failure
mode nobody notices, because nothing breaks — the brain just gets duller.

Comparison is against `backend/eval/baseline.json`, recorded from a real run.
Tolerances are deliberately loose: this is a tripwire for a real regression, not
a lock on exact numbers, which would fire on any harmless change and get
switched off. When a change legitimately moves the numbers, re-record with
`python -m backend.eval.run_eval --write-baseline` and say so in the commit.
"""
import json
import pathlib

import pytest

from backend.eval import run_eval

BASELINE = json.loads(
    (pathlib.Path(run_eval.__file__).parent / "baseline.json").read_text(encoding="utf-8")
)

# Quality may not drop at all beyond floating-point noise. Yield may drift a
# little, since a change to discovery legitimately shifts what a page produces,
# but a large fall means the brain stopped reading something it used to.
_QUALITY_TOLERANCE = 0.01
_YIELD_TOLERANCE = 0.20


@pytest.fixture(scope="module")
def results():
    return run_eval.run()


def test_relation_quality_has_not_regressed(results):
    """Precision and recall against the hand-labelled sentences. Yield can
    always be raised by accepting noise, so precision is the one that stops a
    change from trading correctness for volume."""
    now = results["relationQuality"]
    before = BASELINE["relationQuality"]
    assert now["precision"] >= before["precision"] - _QUALITY_TOLERANCE, (
        f"precision fell from {before['precision']} to {now['precision']}"
    )
    assert now["recall"] >= before["recall"] - _QUALITY_TOLERANCE, (
        f"recall fell from {before['recall']} to {now['recall']}"
    )


def test_real_text_quality_has_not_regressed(results):
    """Same guard, over `real_text_gold.REAL_TEXT_GOLD` (sampled from the
    real corpus, not written for the purpose -- see that module's
    docstring). This is the number that should be trusted over the
    hand-labelled one above when the two disagree, precisely because it
    was not hand-picked to flatter the extractor."""
    now = results["realTextQuality"]
    before = BASELINE["realTextQuality"]
    assert now["precision"] >= before["precision"] - _QUALITY_TOLERANCE, (
        f"real-text precision fell from {before['precision']} to {now['precision']}"
    )
    assert now["recall"] >= before["recall"] - _QUALITY_TOLERANCE, (
        f"real-text recall fell from {before['recall']} to {now['recall']}"
    )


def test_every_page_still_yields_structure(results):
    """A page that stops producing text or sentences means discovery broke on
    a real document, which no unit test on synthetic input would catch."""
    for name, page in results["discovery"].items():
        assert page["sentences"] > 0, f"{name} yielded no sentences at all"
        assert page["textChars"] > 0, f"{name} yielded no readable text"


def test_reading_yield_has_not_collapsed(results):
    """The quiet failure: discovery still works, but the brain reads far less
    of each page than it used to."""
    for name, before in BASELINE["discovery"].items():
        now = results["discovery"][name]
        for field in ("sentences", "textChars", "links"):
            floor = before[field] * (1 - _YIELD_TOLERANCE)
            assert now[field] >= floor, (
                f"{name}.{field} fell from {before[field]} to {now[field]}"
            )


def test_extraction_yield_has_not_collapsed(results):
    """Structure can survive while the concepts and relations drawn from it
    dry up, which would starve the graph without breaking anything."""
    for name, before in BASELINE["extraction"].items():
        now = results["extraction"][name]
        for field in ("concepts", "relations"):
            floor = before[field] * (1 - _YIELD_TOLERANCE)
            assert now[field] >= floor, (
                f"{name}.{field} fell from {before[field]} to {now[field]}"
            )


def test_the_corpus_is_read_from_disk_not_the_network():
    """An evaluation that hits the network measures the network: pages change,
    sites rate-limit, and two runs stop being comparable. The corpus must stay
    fixed and local."""
    corpus = pathlib.Path(run_eval.__file__).parent / "corpus"
    stored = list(corpus.glob("*.html.gz"))
    assert stored, "no stored corpus pages found"
    assert (corpus / "manifest.json").exists()
