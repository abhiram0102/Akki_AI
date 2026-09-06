"""Measure whether the brain is getting better or worse.

The problem this solves
-----------------------
Everything in the pipeline was tuned by looking at one or two pages. Tests
prove specific behaviours still work, but nothing could answer the question
that actually matters when changing a threshold: *did that help?* Without a
number that moves, every future change is guesswork, and the cost of adding
this only grows.

What it measures
----------------
Two things, over a fixed corpus of real pages stored under `corpus/`:

1. **Discovery and extraction, per page.** What structure was found, how much
   readable text came out of it, how many references, and how many concepts
   and relations the extractor produced. These are yield numbers: they say
   whether a change made the brain read more of a page or less of it.

2. **Relation extraction against hand-labelled sentences.** Precision, recall
   and F1 over `gold_relations.GOLD`. This is the quality number. Yield can
   always be raised by accepting more noise, so it means nothing without a
   precision figure beside it.

Why the corpus is stored rather than fetched
--------------------------------------------
An evaluation that hits the network measures the network. Pages change, sites
rate-limit, and a run today would not be comparable with a run next month.
The corpus is fixed and compressed in the repository, so the same input always
produces the same numbers and the only thing that can move them is a change to
the code.

Usage
-----
    python -m backend.eval.run_eval            # print a report
    python -m backend.eval.run_eval --json     # machine-readable
    python -m backend.eval.run_eval --write-baseline

`backend/tests/test_eval_baseline.py` compares a fresh run against the
committed baseline and fails if quality drops.
"""
import argparse
import gzip
import json
import pathlib

CORPUS = pathlib.Path(__file__).parent / "corpus"
BASELINE = pathlib.Path(__file__).parent / "baseline.json"


def _load_corpus() -> dict[str, tuple[str, str]]:
    """Every stored page as (name -> (url, html)), read from disk only."""
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    pages = {}
    for name, meta in manifest.items():
        path = CORPUS / f"{name}.html.gz"
        if not path.exists():
            continue
        pages[name] = (meta["url"], gzip.decompress(path.read_bytes()).decode("utf-8"))
    return pages


def measure_discovery() -> dict:
    """Yield numbers per page: what was found, and how much came out."""
    from urllib.parse import urlparse

    from backend.services import brain_discovery

    out = {}
    for name, (url, html) in sorted(_load_corpus().items()):
        structure = brain_discovery.discover_structure(html, url)
        sentences = structure["sentences"]
        links = structure["links"]
        host = urlparse(url).netloc
        delimiters = structure["delimiters"]
        out[name] = {
            "delimiters": list(delimiters) if delimiters else None,
            "terminators": structure["terminators"],
            "sentences": len(sentences),
            # How much of the page became readable text. A change that halves
            # this has quietly stopped the brain reading most of the page.
            "textChars": len(structure["text"]),
            "meanSentenceWords": round(
                sum(len(s.split()) for s in sentences) / len(sentences), 2
            ) if sentences else 0.0,
            "links": len(links),
            "sameHostLinks": sum(1 for u in links if urlparse(u).netloc == host),
        }
    return out


def measure_extraction() -> dict:
    """How many concepts and relations the corpus yields, end to end."""
    from backend.services import brain_discovery, brain_nlp

    out = {}
    for name, (url, html) in sorted(_load_corpus().items()):
        structure = brain_discovery.discover_structure(html, url)
        concepts, relations = set(), set()
        # The same per-page cap the crawler applies, so these numbers describe
        # what the brain would actually learn rather than a best case.
        for sentence in structure["sentences"][:200]:
            try:
                pairs = brain_nlp.extract_dependencies(sentence)
            except Exception:
                continue
            for cause, effect in pairs:
                concepts.update((cause, effect))
                relations.add((cause, effect))
        out[name] = {"concepts": len(concepts), "relations": len(relations)}
    return out


def measure_pipeline_quality() -> dict:
    """Page-level assertions against discovery+extraction run FRESH, today --
    the check `measure_relation_quality` and `measure_real_text_quality`
    cannot perform, because both feed a frozen sentence string straight to
    `extract_dependencies` and so can never see a `brain_discovery` fix or
    regression at all. See `pipeline_assertions` module docstring for the
    full account of why this exists and how it was confirmed necessary.

    Deliberately does NOT apply `measure_extraction`'s 200-sentence
    production cap. That cap simulates a realistic per-page crawl budget,
    which is the wrong thing here: a discovery improvement that removes
    junk EARLIER in a page shifts every real sentence after it to a lower
    index, which can push a real, wanted fact past a fixed cutoff that used
    to keep it in scope. Confirmed live: the Warburg/"range" sentences
    below sat comfortably under 200 before session 12's discovery fix and
    at indices 214/231/450 afterward -- a cap here would have reported a
    fix as a regression. This measurement asks "does this page's content
    support extracting this fact at all", not "would a capped production
    crawl reach it", so it reads every sentence discovery finds.
    """
    from backend.eval.pipeline_assertions import (
        EXPECTED_SOMEWHERE_ON_PAGE, FORBIDDEN_ANYWHERE_ON_PAGE,
    )
    from backend.services import brain_discovery, brain_nlp

    page_relations: dict[str, set] = {}
    for name, (url, html) in sorted(_load_corpus().items()):
        structure = brain_discovery.discover_structure(html, url)
        relations = set()
        for sentence in structure["sentences"]:
            try:
                relations.update(brain_nlp.extract_dependencies(sentence))
            except Exception:
                continue
        page_relations[name] = relations

    missing_expected = []
    for page, pair, provenance in EXPECTED_SOMEWHERE_ON_PAGE:
        if pair not in page_relations.get(page, set()):
            missing_expected.append({"page": page, "pair": list(pair), "provenance": provenance})

    present_forbidden = []
    for page, pair, provenance in FORBIDDEN_ANYWHERE_ON_PAGE:
        if pair in page_relations.get(page, set()):
            present_forbidden.append({"page": page, "pair": list(pair), "provenance": provenance})

    return {
        "expectedChecked": len(EXPECTED_SOMEWHERE_ON_PAGE),
        "expectedMissing": missing_expected,
        "forbiddenChecked": len(FORBIDDEN_ANYWHERE_ON_PAGE),
        "forbiddenPresent": present_forbidden,
        "passed": not missing_expected and not present_forbidden,
    }


def measure_relation_quality() -> dict:
    """Precision, recall and F1 against hand-labelled sentences.

    Yield can always be raised by accepting more noise, so it is meaningless
    without precision beside it. Sentences expected to yield nothing count
    here too: a false positive on "X is Y" is a real defect.
    """
    from backend.eval.gold_relations import GOLD
    from backend.services import brain_nlp

    true_positives = false_positives = false_negatives = 0
    misses = []
    for sentence, expected in GOLD:
        try:
            got = set(brain_nlp.extract_dependencies(sentence))
        except Exception:
            got = set()
        true_positives += len(got & expected)
        false_positives += len(got - expected)
        false_negatives += len(expected - got)
        if got != expected:
            misses.append({
                "sentence": sentence,
                "expected": sorted(expected),
                "got": sorted(got),
            })

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) else 0.0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "cases": len(GOLD),
        "truePositives": true_positives,
        "falsePositives": false_positives,
        "falseNegatives": false_negatives,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "disagreements": misses,
    }


def measure_real_text_quality() -> dict:
    """Precision, recall and F1 against `real_text_gold.REAL_TEXT_GOLD` --
    45 sentences sampled from the stored corpus itself (not written for the
    purpose) and hand-labelled, with a second independent annotator's labels
    recorded alongside for inter-annotator agreement. See that module's
    docstring for the sampling strategy, the IAA computation, and an honest
    account of where the two annotators disagreed and why.

    Reported separately from `measure_relation_quality()` deliberately: that
    one is a regression tripwire over hand-written examples designed to
    exercise one pattern each, this one is closer to a real measurement of
    quality on text nobody hand-picked. They should not be averaged together.
    """
    from backend.eval.real_text_gold import REAL_TEXT_GOLD
    from backend.services import brain_nlp

    true_positives = false_positives = false_negatives = 0
    misses = []
    for page, index, sentence, expected in REAL_TEXT_GOLD:
        try:
            got = set(brain_nlp.extract_dependencies(sentence))
        except Exception:
            got = set()
        true_positives += len(got & expected)
        false_positives += len(got - expected)
        false_negatives += len(expected - got)
        if got != expected:
            misses.append({
                "page": page, "index": index, "sentence": sentence,
                "expected": sorted(expected), "got": sorted(got),
            })

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) else 0.0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "cases": len(REAL_TEXT_GOLD),
        "truePositives": true_positives,
        "falsePositives": false_positives,
        "falseNegatives": false_negatives,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "disagreements": misses,
    }


def run() -> dict:
    return {
        "discovery": measure_discovery(),
        "extraction": measure_extraction(),
        "relationQuality": measure_relation_quality(),
        "realTextQuality": measure_real_text_quality(),
        "pipelineQuality": measure_pipeline_quality(),
    }


def _report(results: dict) -> str:
    lines = ["Discovery and extraction, per stored page", ""]
    lines.append(f"{'page':30s} {'sent':>6s} {'text':>8s} {'links':>6s} "
                 f"{'concepts':>9s} {'relations':>10s}  delimiters/terminators")
    for name, d in results["discovery"].items():
        e = results["extraction"].get(name, {})
        delimiters = "".join(d["delimiters"]) if d["delimiters"] else "none"
        lines.append(
            f"{name:30s} {d['sentences']:>6d} {d['textChars']:>8d} {d['links']:>6d} "
            f"{e.get('concepts', 0):>9d} {e.get('relations', 0):>10d}  "
            f"{delimiters}  {''.join(d['terminators'])}"
        )

    q = results["relationQuality"]
    lines += ["", "Relation extraction against hand-labelled sentences (regression tripwire)", ""]
    lines.append(f"  cases      {q['cases']}")
    lines.append(f"  precision  {q['precision']}")
    lines.append(f"  recall     {q['recall']}")
    lines.append(f"  f1         {q['f1']}")
    if q["disagreements"]:
        lines += ["", f"  {len(q['disagreements'])} sentence(s) disagreed with the labels:"]
        for miss in q["disagreements"]:
            lines.append(f"    {miss['sentence']}")
            lines.append(f"      expected {miss['expected']}")
            lines.append(f"      got      {miss['got']}")

    r = results["realTextQuality"]
    lines += ["", "Relation extraction against sentences sampled from the real corpus", ""]
    lines.append(f"  cases      {r['cases']}")
    lines.append(f"  precision  {r['precision']}")
    lines.append(f"  recall     {r['recall']}")
    lines.append(f"  f1         {r['f1']}")
    if r["disagreements"]:
        lines += ["", f"  {len(r['disagreements'])} sentence(s) disagreed with the labels:"]
        for miss in r["disagreements"]:
            lines.append(f"    [{miss['page']}#{miss['index']}] {miss['sentence'][:80]}")
            lines.append(f"      expected {miss['expected']}")
            lines.append(f"      got      {miss['got']}")

    p = results["pipelineQuality"]
    lines += ["", "Page-level assertions against discovery+extraction run FRESH today "
                  "(not frozen strings)", ""]
    lines.append(f"  expected pairs checked   {p['expectedChecked']}   "
                 f"missing: {len(p['expectedMissing'])}")
    lines.append(f"  forbidden pairs checked  {p['forbiddenChecked']}   "
                 f"present: {len(p['forbiddenPresent'])}")
    lines.append(f"  passed                   {p['passed']}")
    for miss in p["expectedMissing"]:
        lines.append(f"    MISSING  [{miss['page']}] {tuple(miss['pair'])}  ({miss['provenance']})")
    for bad in p["forbiddenPresent"]:
        lines.append(f"    PRESENT  [{bad['page']}] {tuple(bad['pair'])}  ({bad['provenance']})")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--write-baseline", action="store_true",
                        help="record this run as the baseline to compare against")
    args = parser.parse_args()

    results = run()
    if args.write_baseline:
        BASELINE.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"baseline written to {BASELINE}")
        return
    print(json.dumps(results, indent=2) if args.json else _report(results))


if __name__ == "__main__":
    main()
