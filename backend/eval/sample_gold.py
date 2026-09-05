"""Reproduces the sample that `real_text_gold.REAL_TEXT_GOLD` was hand-labelled
from. Not part of any test -- a record of how the sample was drawn, so the
sampling strategy is a runnable fact rather than a claim in a docstring.

    .venv/Scripts/python.exe -m backend.eval.sample_gold

Stratified equally by corpus page (15 sentences each), not proportionally by
page length -- see `real_text_gold` module docstring for why. No quality
filtering: sentences are taken as-is, messy fragments included, because
filtering them out would recreate the exact bias (clean, hand-picked
examples) this sample exists to avoid. Fixed seed so the sample is
reproducible.
"""
import gzip
import json

from backend.eval.run_eval import CORPUS
from backend.services import brain_discovery

N_PER_PAGE = 15
SEED = 20260906


def sample() -> list[dict]:
    import random

    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    rng = random.Random(SEED)
    out = []
    for name, meta in sorted(manifest.items()):
        html = gzip.decompress((CORPUS / f"{name}.html.gz").read_bytes()).decode("utf-8")
        structure = brain_discovery.discover_structure(html, meta["url"])
        sentences = structure["sentences"]
        idx = sorted(rng.sample(range(len(sentences)), min(N_PER_PAGE, len(sentences))))
        for i in idx:
            out.append({"page": name, "index": i, "sentence": sentences[i]})
    return out


if __name__ == "__main__":
    print(json.dumps(sample(), indent=2))
