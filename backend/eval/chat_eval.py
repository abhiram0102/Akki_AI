"""End-to-end evaluation of /api/brain/chat against an answer key the brain
never wrote.

`run_eval` measures the extractor on stored text and `measure_reasoning` hides
edges the graph already holds and asks the graph to rebuild them. Both grade
the brain against itself. Neither answers the question a user has: when I ask
the chat what X leads to, is the answer right?

The answer key is Wikidata's "has effect" (P1542) and "has cause" (P828)
statements, fetched live and frozen into `chat_gold.json` so runs are
comparable. Nothing in the key is hand-written, and every statement is used in
both directions ("X has effect Y" is also "Y has cause X").

Questions are phrased with the parser's OWN connective vocabulary
(`brain_nlp.FORWARD_CONNECTIVES`), and the verb used is the one the parser
understands most often on a sample of the key -- chosen from data, reported in
the output, never picked by hand.

Every run is written to `results/` and compared with the previous one, so
"the brain got smarter this week" is a number, not an impression.

What the numbers mean, precisely:
  coverage          share of key questions whose subject the graph has a node for
  parseAccuracy     question understood as the intended intent on the right concept
  answerRate        the chat returned an answer rather than "nothing known"
  hitRate           at least one key answer appears among the concepts the chat returned
  hitRateKnowable   hitRate over questions where a key answer IS in the graph --
                    what reasoning alone could have got right
  answerPrecision   of the questions it answered, how often a key answer was in it.
                    Wikidata is incomplete, so a non-key concept is not proven
                    wrong: this is a LOWER bound on correctness, labelled as such.
  grounding         (--verbalize) concepts the local LLM's wording introduced that
                    were not in the graph's facts -- an upper bound on
                    hallucination, since a generic word also counts.

Run:  python -m backend.eval.chat_eval [--refresh-gold] [--limit N] [--verbalize]
                                       [--api http://localhost:5000 --token JWT]
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import math
import pathlib
import random
import time

import httpx

from backend.services import brain_nlp, brain_query

_HERE = pathlib.Path(__file__).parent
GOLD_PATH = _HERE / "chat_gold.json"
RESULTS_DIR = _HERE / "results"

WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
# Wikidata's schema, verified live against the property labels: P1542 is
# "has effect", P828 is "has cause". These name the external data, not English.
PROPERTIES = {"effect": "P1542", "cause": "P828"}
_FETCH_ATTEMPTS = 3
# Statements are fetched as bare item ids (seconds), then named in batches.
# Asking the label service for names inside a paged statement query overran
# Wikidata's 60s limit at high offsets, and the service reports that as HTTP
# 200 with the JSON cut off mid-string and a stack trace appended.
_STATEMENTS_QUERY = "SELECT ?s ?o WHERE {{ ?s wdt:{prop} ?o . FILTER(isIRI(?o)) }}"
_LABELS_QUERY = ("SELECT ?item ?label WHERE {{ VALUES ?item {{ {items} }} "
                 "?item rdfs:label ?label . FILTER(LANG(?label) = 'en') }}")
_LABEL_BATCH = 2000

_INTENT = {"effect": brain_query.EFFECT, "cause": brain_query.CAUSE}
_RELATIONS = tuple(PROPERTIES)
_INVERSE = {"effect": "cause", "cause": "effect"}
_PROFILE_RELATIONS = ("CAUSES", "REQUIRES", "PART_OF")
_VERB_SAMPLE = 200
_EXAMPLES = 8


# ── the answer key ────────────────────────────────────────────────────────────

def pairs_from_ids(id_pairs, labels: dict[str, str]) -> list[tuple[str, str]]:
    """Name each (subject id, object id) statement; an item with no English
    label has no name a question could be asked with, so it is dropped."""
    return [(labels[s], labels[o]) for s, o in id_pairs if s in labels and o in labels]


def gold_from_pairs(pairs_by_relation: dict[str, list]) -> list[dict]:
    """Group (subject, object) statements into one question per (relation,
    subject), adding each statement's inverse under the opposite relation."""
    grouped: dict[tuple[str, str], set[str]] = {}
    for relation, pairs in pairs_by_relation.items():
        for s, o in pairs:
            s, o = s.strip().lower(), o.strip().lower()
            if not s or not o or s == o:
                continue
            grouped.setdefault((relation, s), set()).add(o)
            grouped.setdefault((_INVERSE[relation], o), set()).add(s)
    return [{"relation": rel, "subject": subj, "answers": sorted(answers)}
            for (rel, subj), answers in sorted(grouped.items())]


def _qid(binding: dict) -> str:
    return binding["value"].rsplit("/", 1)[1]


async def _sparql(client: httpx.AsyncClient, query: str, what: str) -> list[dict]:
    """One SPARQL query, parsed or retried.

    A response only counts once it parses as JSON, because an overrun query
    comes back as HTTP 200 with a truncated body. If it never parses, the fetch
    fails loudly naming `what`, rather than freezing a silently partial key.
    """
    from backend.services import brain_learn
    last_error = None
    for attempt in range(_FETCH_ATTEMPTS):
        try:
            resp = await client.post(
                WIKIDATA_ENDPOINT, data={"query": query},
                headers={**brain_learn.UA_HEADERS,
                         "Accept": "application/sparql-results+json"})
            resp.raise_for_status()
            # strict=False: real labels contain raw tabs, which are valid data
            # but invalid strict JSON.
            return json.loads(resp.text, strict=False)["results"]["bindings"]
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            last_error = exc
            await asyncio.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Wikidata query for {what} failed: {last_error!r}")


async def fetch_gold(client: httpx.AsyncClient) -> dict:
    """Every "has effect" / "has cause" statement in Wikidata, named in English."""
    id_pairs: dict[str, list[tuple[str, str]]] = {}
    for relation, prop in PROPERTIES.items():
        rows = await _sparql(client, _STATEMENTS_QUERY.format(prop=prop), prop)
        id_pairs[relation] = [(_qid(r["s"]), _qid(r["o"])) for r in rows]

    items = sorted({i for pairs in id_pairs.values() for pair in pairs for i in pair})
    labels: dict[str, str] = {}
    for start in range(0, len(items), _LABEL_BATCH):
        batch = items[start:start + _LABEL_BATCH]
        rows = await _sparql(
            client, _LABELS_QUERY.format(items=" ".join(f"wd:{i}" for i in batch)),
            f"labels {start}-{start + len(batch)}")
        for r in rows:
            labels.setdefault(_qid(r["item"]), r["label"]["value"].strip())

    return {
        "source": "Wikidata",
        "endpoint": WIKIDATA_ENDPOINT,
        "properties": PROPERTIES,
        "query": {"statements": _STATEMENTS_QUERY, "labels": _LABELS_QUERY},
        "fetchedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "pairs": {rel: sorted([s, o] for s, o in set(pairs_from_ids(pairs, labels)))
                  for rel, pairs in id_pairs.items()},
    }


async def load_gold(path: pathlib.Path = GOLD_PATH, refresh: bool = False) -> dict:
    if refresh or not path.exists():
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            snapshot = await fetch_gold(client)
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=0), encoding="utf-8")
        return snapshot
    return json.loads(path.read_text(encoding="utf-8"))


# ── spelling labels the way the graph stores them ─────────────────────────────

def _keys_from_doc(label: str, doc) -> set[str]:
    keys = {label.strip().lower()}
    topics = brain_query.extract_topics(doc)
    if len(topics) == 1:
        keys.add(topics[0])
    return keys


def concept_keys(label: str) -> set[str]:
    """The label as written plus the graph writer's normal form of it, when the
    label is a single concept to that normalizer."""
    return _keys_from_doc(label, brain_nlp.get_nlp()(label.strip().lower()))


def bulk_concept_keys(labels) -> dict[str, set[str]]:
    labels = sorted({l.strip().lower() for l in labels if l and l.strip()})
    nlp = brain_nlp.get_nlp()
    return {label: _keys_from_doc(label, doc)
            for label, doc in zip(labels, nlp.pipe(labels, batch_size=256))}


# ── the questions ─────────────────────────────────────────────────────────────

def _third_person(verb: str) -> str | None:
    # Only the regular "+s" form; a verb needing any other inflection is
    # skipped rather than misspelled into a question the parser never sees.
    if verb.endswith(("s", "x", "z", "ch", "sh", "y", "o")):
        return None
    return verb + "s"


def phrase(relation: str, subject: str, verb: str) -> str | None:
    """"what does X <verb>" asks for effects (X is the subject of a forward
    connective); "what <verb>s X" asks for causes (X is its object)."""
    if relation == "effect":
        return f"what does {subject} {verb}"
    inflected = _third_person(verb)
    return f"what {inflected} {subject}" if inflected else None


def parse_matches(plan, relation: str, subject_keys: set[str]) -> bool:
    return plan.intent == _INTENT[relation] and plan.primary in subject_keys


def choose_verb(items: list[dict], verbs) -> tuple[str, dict[str, float]]:
    """The connective the parser understands most often on these items. Ties go
    to alphabetical order, so the choice is reproducible."""
    accuracy: dict[str, float] = {}
    for verb in sorted(verbs):
        ok = 0
        for item in items:
            question = phrase(item["relation"], item["subject"], verb)
            if question and parse_matches(brain_query.parse(question), item["relation"],
                                          concept_keys(item["subject"])):
                ok += 1
        accuracy[verb] = round(ok / len(items), 4) if items else 0.0
    best = max(sorted(accuracy), key=lambda v: accuracy[v])
    return best, accuracy


# ── scoring ───────────────────────────────────────────────────────────────────

def _claimed(answer: dict) -> list[tuple[str, bool]]:
    """(concept, derived) for every concept the answer put in front of the
    user, in the order shown."""
    out: list[tuple[str, bool]] = []
    for r in answer.get("results") or []:
        out.append((r["concept"], bool(r.get("derived"))))
    chain = (answer.get("path") or {}).get("chain") or []
    for i, concept in enumerate(chain[1:], start=1):
        out.append((concept, i >= 2))
    for rel in _PROFILE_RELATIONS:
        for r in (answer.get("profile") or {}).get(rel) or []:
            out.append((r["concept"], bool(r.get("derived"))))
    return out


def score_answer(answer: dict, gold_keys: set[str]) -> dict:
    claimed = _claimed(answer)
    answered = bool(answer.get("answered"))
    rank = None
    derived_hit = False
    if answered:
        for i, (concept, derived) in enumerate(claimed, start=1):
            if concept in gold_keys:
                rank, derived_hit = i, derived
                break
    return {"answered": answered, "hit": rank is not None, "rank": rank,
            "derivedHit": derived_hit, "claimed": len(claimed)}


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(p * len(ordered)) - 1)], 1)


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    knowable = [r for r in rows if r["knowable"]]
    answered = sum(r["answered"] for r in rows)
    hits = sum(r["hit"] for r in rows)
    latencies = [r["latencyMs"] for r in rows]
    return {
        "questions": n,
        "knowable": len(knowable),
        "parseAccuracy": _rate(sum(r["parsed"] for r in rows), n),
        "answerRate": _rate(answered, n),
        "hitRate": _rate(hits, n),
        "hitRateKnowable": _rate(sum(r["hit"] for r in knowable), len(knowable)),
        "answerPrecision": _rate(hits, answered),
        "derivedHits": sum(r["derivedHit"] for r in rows),
        "meanReciprocalRank": round(sum(1 / r["rank"] for r in rows if r["rank"]) / n, 4) if n else 0.0,
        "latencyMs": {"p50": _percentile(latencies, 0.5), "p95": _percentile(latencies, 0.95)},
    }


def compare(current: dict, previous: dict | None) -> dict:
    """Numeric change per section since the previous run. Runs with different
    settings (sample, seed, answer key, target) are not comparable: every number
    moves with the sample, and that is not a change in the brain."""
    if not previous or previous.get("settings") != current.get("settings"):
        return {}
    delta: dict = {}
    for section, values in current.items():
        before = previous.get(section)
        if not isinstance(values, dict) or not isinstance(before, dict):
            continue
        changes = {k: round(v - before[k], 4) for k, v in values.items()
                   if isinstance(v, (int, float)) and not isinstance(v, bool)
                   and isinstance(before.get(k), (int, float))}
        if changes:
            delta[section] = changes
    return delta


def unsupported_concepts(prose: str, facts: str, question_topics) -> list[str]:
    """Concepts in the worded answer that are neither in the graph's facts nor
    in the question -- what the LLM added on its own."""
    nlp = brain_nlp.get_nlp()
    allowed = set(brain_query.extract_topics(nlp(facts))) | set(question_topics)
    return sorted(set(brain_query.extract_topics(nlp(prose))) - allowed)


# ── targets: the same questions, in-process or over HTTP ──────────────────────

class InProcessChat:
    """Runs exactly what POST /api/brain/chat runs (parse, then
    answer_question) without the HTTP layer."""
    name = "in-process"

    def __init__(self, max_depth: int, limit: int):
        self.max_depth, self.limit = max_depth, limit

    async def ask(self, question: str) -> tuple[object, dict]:
        from backend.services import brain_reasoning
        plan = brain_query.parse(question)
        answer = await brain_reasoning.answer_question(
            plan.intent, plan.topics, max_depth=self.max_depth, limit=self.limit)
        return plan, answer

    async def worded(self, question: str, answer: dict) -> tuple[str, bool]:
        from backend.services import brain_reasoning
        facts = brain_reasoning.facts_for_llm(answer)
        pieces = [c async for c in brain_reasoning.verbalize_stream(question, facts)]
        return "".join(pieces).strip(), True

    async def close(self):
        pass


class HttpChat:
    """Asks the running backend, so the measurement includes everything a
    user's request goes through."""

    def __init__(self, base: str, token: str, max_depth: int, limit: int):
        self.name = f"http:{base}"
        self.max_depth, self.limit = max_depth, limit
        self.body = {"maxDepth": max_depth, "limit": limit}
        self.client = httpx.AsyncClient(
            base_url=base.rstrip("/"), timeout=180.0,
            headers={"Authorization": f"Bearer {token}"})

    async def ask(self, question: str) -> tuple[object, dict]:
        resp = await self.client.post("/api/brain/chat", json={"query": question, **self.body})
        resp.raise_for_status()
        answer = resp.json()
        plan = answer.get("plan") or {}
        return brain_query.QueryPlan(intent=plan.get("intent", ""),
                                     topics=plan.get("topics") or [], raw=question), answer

    async def worded(self, question: str, answer: dict) -> tuple[str, bool]:
        """Read POST /api/brain/chat-stream to its `done` event. Returns the
        final text and whether a model wrote it (False = the deterministic
        fallback the endpoint sends when no model is reachable)."""
        text, llm = "", False
        async with self.client.stream(
                "POST", "/api/brain/chat-stream", json={"query": question, **self.body}) as resp:
            resp.raise_for_status()
            buffer = ""
            async for chunk in resp.aiter_text():
                # sse-starlette separates lines with "\r\n".
                buffer = (buffer + chunk).replace("\r\n", "\n")
                while "\n\n" in buffer:
                    block, buffer = buffer.split("\n\n", 1)
                    for line in block.split("\n"):
                        if not line.startswith("data:"):
                            continue
                        event = json.loads(line[5:].strip())
                        if event.get("stage") == "token":
                            text += event.get("text", "")
                        elif event.get("stage") in ("answer", "done"):
                            text = event.get("text") or text
                            llm = bool(event.get("llm", llm))
        return text.strip(), llm

    async def close(self):
        await self.client.aclose()


# ── the run ───────────────────────────────────────────────────────────────────

async def _existing_concepts(words: set[str]) -> set[str]:
    from backend.services.neo4j_service import get_driver
    found: set[str] = set()
    ordered = sorted(words)
    async with get_driver().session() as session:
        for i in range(0, len(ordered), 5000):
            result = await session.run(
                "UNWIND $words AS w MATCH (c:Concept {word: w}) RETURN c.word AS word",
                words=ordered[i:i + 5000])
            found.update([r["word"] async for r in result])
    return found


def _latest_result(settings: dict) -> dict | None:
    """The most recent earlier run made with the same settings."""
    for path in sorted(RESULTS_DIR.glob("chat-*.json"), reverse=True):
        previous = json.loads(path.read_text(encoding="utf-8"))
        if previous.get("settings") == settings:
            return previous
    return None


async def run(target, refresh_gold: bool = False, limit: int | None = None,
              seed: int = 0, verbalize: bool = False, log=print) -> dict:
    requested_verbalize = verbalize
    snapshot = await load_gold(refresh=refresh_gold)
    gold = gold_from_pairs(snapshot["pairs"])
    log(f"answer key: {len(gold)} questions from {snapshot['source']} "
        f"(fetched {snapshot['fetchedAt']})")

    keys = bulk_concept_keys({g["subject"] for g in gold}
                             | {a for g in gold for a in g["answers"]})
    in_graph = await _existing_concepts({k for ks in keys.values() for k in ks})

    askable = []
    for g in gold:
        g["subjectKeys"] = keys[g["subject"]]
        g["goldKeys"] = set().union(*(keys[a] for a in g["answers"]))
        g["knowable"] = bool(g["goldKeys"] & in_graph)
        if g["subjectKeys"] & in_graph:
            askable.append(g)
    coverage = {rel: {"questions": sum(g["relation"] == rel for g in gold),
                      "subjectInGraph": sum(g["relation"] == rel for g in askable)}
                for rel in _RELATIONS}
    for c in coverage.values():
        c["coverage"] = _rate(c["subjectInGraph"], c["questions"])

    rng = random.Random(seed)
    if limit is not None and len(askable) > limit:
        askable = rng.sample(askable, limit)
    log(f"asking {len(askable)} questions whose subject the graph knows")

    verbs: dict[str, dict] = {}
    for rel in _RELATIONS:
        items = [g for g in askable if g["relation"] == rel]
        sample = rng.sample(items, min(_VERB_SAMPLE, len(items)))
        if sample:
            verb, accuracy = choose_verb(sample, brain_nlp.FORWARD_CONNECTIVES)
            verbs[rel] = {"verb": verb, "parseAccuracyByVerb": accuracy}

    rows: list[dict] = []
    grounding = {"measured": verbalize, "answersWorded": 0, "wordedByModel": 0,
                 "conceptsIntroduced": 0, "answersWithIntroducedConcepts": 0, "examples": []}
    for i, g in enumerate(askable, start=1):
        if g["relation"] not in verbs:
            continue
        question = phrase(g["relation"], g["subject"], verbs[g["relation"]]["verb"])
        started = time.perf_counter()
        plan, answer = await target.ask(question)
        latency = (time.perf_counter() - started) * 1000
        row = {"relation": g["relation"], "question": question, "knowable": g["knowable"],
               "parsed": parse_matches(plan, g["relation"], g["subjectKeys"]),
               "latencyMs": latency, "gold": g["answers"][:10],
               **score_answer(answer, g["goldKeys"])}
        row["shown"] = [c for c, _ in _claimed(answer)][:10]
        rows.append(row)

        if verbalize and row["answered"]:
            try:
                prose, by_model = await target.worded(question, answer)
            except Exception as exc:  # no model reachable: say so, never guess
                grounding.update(measured=False, reason=f"verbalizer unavailable: {exc!r}")
                verbalize = False
            else:
                grounding["answersWorded"] += 1
                if by_model:
                    grounding["wordedByModel"] += 1
                    from backend.services import brain_reasoning
                    added = unsupported_concepts(
                        prose, brain_reasoning.facts_for_llm(answer), plan.topics)
                    grounding["conceptsIntroduced"] += len(added)
                    if added:
                        grounding["answersWithIntroducedConcepts"] += 1
                        if len(grounding["examples"]) < _EXAMPLES:
                            grounding["examples"].append(
                                {"question": question, "introduced": added, "worded": prose})
        if i % 100 == 0:
            log(f"  {i}/{len(askable)}")

    if grounding["measured"]:
        grounding["introducedRate"] = _rate(grounding["answersWithIntroducedConcepts"],
                                            grounding["wordedByModel"])

    result = {
        "runAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "target": target.name,
        "settings": {"target": target.name, "limit": limit, "seed": seed,
                     "verbalize": requested_verbalize,
                     "goldFetchedAt": snapshot["fetchedAt"],
                     "maxDepth": target.max_depth, "answerLimit": target.limit},
        "gold": {"source": snapshot["source"], "fetchedAt": snapshot["fetchedAt"],
                 "questions": len(gold)},
        "coverage": coverage,
        "verbs": verbs,
        "overall": summarize(rows),
        "byRelation": {rel: summarize([r for r in rows if r["relation"] == rel])
                       for rel in _RELATIONS},
        "grounding": grounding,
        "examples": {
            "hits": [_example(r) for r in rows if r["hit"]][:_EXAMPLES],
            "missesKnowable": [_example(r) for r in rows
                               if r["knowable"] and not r["hit"]][:_EXAMPLES],
            "misparsed": [_example(r) for r in rows if not r["parsed"]][:_EXAMPLES],
        },
    }
    return result


def _example(row: dict) -> dict:
    return {k: row[k] for k in ("question", "gold", "shown", "rank")}


def save(result: dict) -> tuple[pathlib.Path, dict]:
    previous = _latest_result(result["settings"])
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = result["runAt"].replace(":", "").replace("-", "").replace("+0000", "Z")
    path = RESULTS_DIR / f"chat-{stamp}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, compare(result, previous)


def report(result: dict, delta: dict) -> str:
    def line(label, section):
        s = result[section] if section in result else result["byRelation"][section]
        d = delta.get(section, {})
        change = lambda k: f" ({d[k]:+.4f})" if k in d else ""
        return (f"{label:<10} n={s['questions']:<6} parse={s['parseAccuracy']:.3f}{change('parseAccuracy')} "
                f"answered={s['answerRate']:.3f}{change('answerRate')} "
                f"hit={s['hitRate']:.3f}{change('hitRate')} "
                f"hit|knowable={s['hitRateKnowable']:.3f}{change('hitRateKnowable')} "
                f"precision>={s['answerPrecision']:.3f}{change('answerPrecision')} "
                f"mrr={s['meanReciprocalRank']:.3f} p50={s['latencyMs']['p50']}ms")
    out = [f"target: {result['target']}   key: {result['gold']['source']} "
           f"{result['gold']['questions']} questions (fetched {result['gold']['fetchedAt']})"]
    for rel, c in result["coverage"].items():
        verb = result["verbs"].get(rel, {}).get("verb", "-")
        out.append(f"coverage {rel:<7} {c['subjectInGraph']}/{c['questions']} = {c['coverage']:.3f}  "
                   f"(asked with verb '{verb}')")
    out.append(line("overall", "overall"))
    for rel in result["byRelation"]:
        out.append(line(rel, rel))
    g = result["grounding"]
    if g["measured"]:
        out.append(f"grounding: {g['answersWithIntroducedConcepts']}/{g['wordedByModel']} worded answers "
                   f"introduced concepts not in the facts (rate {g.get('introducedRate', 0):.3f})")
    else:
        out.append(f"grounding: not measured{(' - ' + g['reason']) if g.get('reason') else ''}")
    if not delta:
        out.append("no earlier run with the same settings to compare with")
    return "\n".join(out)


async def _main(args) -> None:
    if args.api:
        if not args.token:
            raise SystemExit("--api needs --token (a JWT from POST /api/auth/login)")
        target = HttpChat(args.api, args.token, args.max_depth, args.answer_limit)
    else:
        target = InProcessChat(args.max_depth, args.answer_limit)
    try:
        result = await run(target, refresh_gold=args.refresh_gold, limit=args.limit,
                           seed=args.seed, verbalize=args.verbalize)
    finally:
        await target.close()
    path, delta = save(result)
    print(report(result, delta))
    print(f"saved {path}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--refresh-gold", action="store_true",
                   help="re-fetch the answer key from Wikidata")
    p.add_argument("--limit", type=int, default=None,
                   help="ask at most this many questions (seeded sample)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--verbalize", action="store_true",
                   help="also word each answer with the local LLM and measure grounding")
    p.add_argument("--api", help="base URL of a running backend, e.g. http://localhost:5000")
    p.add_argument("--token", help="bearer token for --api")
    p.add_argument("--max-depth", type=int, default=3)
    p.add_argument("--answer-limit", type=int, default=8)
    asyncio.run(_main(p.parse_args()))


if __name__ == "__main__":
    main()
