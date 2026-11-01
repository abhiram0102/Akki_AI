"""Tests for the end-to-end chat evaluation (backend/eval/chat_eval.py).

The harness scores what a user of /api/brain/chat actually gets against an
answer key the brain never wrote: Wikidata's "has effect" (P1542) and "has
cause" (P828) statements. These tests pin the pieces that decide the numbers --
how the key is built, how questions are phrased, how an answer is scored and
summarised -- so a change to the harness cannot quietly flatter the brain.

Uses the real spaCy pipeline the brain uses (no mocks); no Neo4j, no network.
"""
from backend.eval import chat_eval
from backend.services import brain_query


# ── the answer key ────────────────────────────────────────────────────────────

def test_gold_uses_both_directions_of_each_statement():
    """"X has effect Y" is also "Y has cause X". Dropping the inverse would
    leave half of Wikidata's knowledge out of the key."""
    gold = chat_eval.gold_from_pairs({
        "effect": [("deforestation", "soil erosion")],
        "cause": [("famine", "drought")],
    })
    by_key = {(g["relation"], g["subject"]): g["answers"] for g in gold}
    assert by_key[("effect", "deforestation")] == ["soil erosion"]
    assert by_key[("cause", "soil erosion")] == ["deforestation"]
    assert by_key[("cause", "famine")] == ["drought"]
    assert by_key[("effect", "drought")] == ["famine"]


def test_gold_merges_answers_for_the_same_question_and_drops_self_loops():
    gold = chat_eval.gold_from_pairs({
        "effect": [("smoking", "lung cancer"), ("Smoking", "Heart Disease"), ("fire", "Fire")],
        "cause": [],
    })
    by_key = {(g["relation"], g["subject"]): g["answers"] for g in gold}
    assert by_key[("effect", "smoking")] == ["heart disease", "lung cancer"]
    assert ("effect", "fire") not in by_key


def test_concept_keys_include_the_graph_writers_spelling():
    """A gold label must be compared in the same spelling the graph stores, or
    a concept the brain knows is scored as a miss."""
    assert "global warming" in chat_eval.concept_keys("Global Warming")
    assert "flood" in chat_eval.concept_keys("floods")


# ── the questions ─────────────────────────────────────────────────────────────

def test_effect_question_parses_to_effect_on_the_subject():
    question = chat_eval.phrase("effect", "inflation", "cause")
    plan = brain_query.parse(question)
    assert chat_eval.parse_matches(plan, "effect", chat_eval.concept_keys("inflation"))


def test_cause_question_parses_to_cause_on_the_subject():
    question = chat_eval.phrase("cause", "inflation", "cause")
    plan = brain_query.parse(question)
    assert chat_eval.parse_matches(plan, "cause", chat_eval.concept_keys("inflation"))


def test_parse_on_the_wrong_intent_does_not_match():
    plan = brain_query.parse(chat_eval.phrase("effect", "inflation", "cause"))
    assert not chat_eval.parse_matches(plan, "cause", chat_eval.concept_keys("inflation"))


def test_verb_is_chosen_by_how_often_the_parser_understands_it():
    items = [{"relation": "effect", "subject": s, "answers": []}
             for s in ("inflation", "deforestation")]
    verb, accuracy = chat_eval.choose_verb(items, ["cause", "result"])
    # "what does inflation result" is not a question the parser reads as EFFECT.
    assert verb == "cause"
    assert accuracy["cause"] > accuracy["result"]


# ── scoring one answer ────────────────────────────────────────────────────────

def test_hit_records_the_rank_of_the_first_gold_concept():
    answer = {"answered": True, "results": [
        {"concept": "price", "depth": 1, "derived": False},
        {"concept": "unemployment", "depth": 2, "derived": True},
    ]}
    score = chat_eval.score_answer(answer, {"unemployment"})
    assert score == {"answered": True, "hit": True, "rank": 2, "derivedHit": True,
                     "claimed": 2}


def test_unanswered_is_never_a_hit():
    score = chat_eval.score_answer({"answered": False, "results": []}, {"unemployment"})
    assert score["answered"] is False and score["hit"] is False and score["rank"] is None


def test_profile_answers_are_scored_on_their_concepts():
    """A misparsed question falls back to a profile; if the right concept is in
    it the user still saw it, so it counts."""
    answer = {"answered": True, "profile": {
        "CAUSES": [{"concept": "erosion", "depth": 1, "derived": False}],
        "REQUIRES": [], "PART_OF": []}}
    assert chat_eval.score_answer(answer, {"erosion"})["hit"] is True


# ── summarising a run ─────────────────────────────────────────────────────────

def test_summary_separates_what_the_brain_never_read_from_what_it_got_wrong():
    rows = [
        {"relation": "effect", "knowable": True, "parsed": True, "latencyMs": 10,
         "answered": True, "hit": True, "rank": 1, "derivedHit": False, "claimed": 3},
        {"relation": "effect", "knowable": True, "parsed": True, "latencyMs": 30,
         "answered": True, "hit": False, "rank": None, "derivedHit": False, "claimed": 2},
        {"relation": "effect", "knowable": False, "parsed": False, "latencyMs": 20,
         "answered": False, "hit": False, "rank": None, "derivedHit": False, "claimed": 0},
    ]
    s = chat_eval.summarize(rows)
    assert s["questions"] == 3
    assert s["knowable"] == 2
    assert s["parseAccuracy"] == round(2 / 3, 4)
    assert s["answerRate"] == round(2 / 3, 4)
    assert s["hitRate"] == round(1 / 3, 4)
    assert s["hitRateKnowable"] == 0.5
    assert s["answerPrecision"] == 0.5
    assert s["meanReciprocalRank"] == round(1 / 3, 4)
    assert s["latencyMs"]["p50"] == 20


def test_summary_of_nothing_is_zeros_not_a_crash():
    s = chat_eval.summarize([])
    assert s["questions"] == 0 and s["hitRate"] == 0.0


def test_compare_reports_the_change_since_the_previous_run():
    now = {"overall": {"hitRate": 0.30, "parseAccuracy": 0.9}}
    before = {"overall": {"hitRate": 0.25, "parseAccuracy": 0.9}}
    delta = chat_eval.compare(now, before)
    assert delta["overall"]["hitRate"] == 0.05
    assert delta["overall"]["parseAccuracy"] == 0.0
    assert chat_eval.compare(now, None) == {}


def test_runs_with_different_settings_are_not_compared():
    """A different sample or answer key moves every number; calling that a
    change in the brain would be a false trend."""
    now = {"settings": {"seed": 1, "limit": 120}, "overall": {"hitRate": 0.30}}
    before = {"settings": {"seed": 0, "limit": 300}, "overall": {"hitRate": 0.25}}
    assert chat_eval.compare(now, before) == {}


# ── grounding of the worded answer ────────────────────────────────────────────

def test_worded_answer_concepts_missing_from_the_facts_are_flagged():
    facts = "inflation causes unemployment."
    prose = "Inflation leads to unemployment and also to civil war."
    flagged = chat_eval.unsupported_concepts(prose, facts, ["inflation"])
    assert "civil war" in flagged
    assert "unemployment" not in flagged and "inflation" not in flagged


def test_pairs_without_an_english_label_on_both_ends_are_dropped():
    pairs = chat_eval.pairs_from_ids([("Q1", "Q2"), ("Q3", "Q4")],
                                     {"Q1": "drought", "Q2": "famine", "Q3": "fire"})
    assert pairs == [("drought", "famine")]


# ── talking to Wikidata and the backend (real httpx, in-memory transport) ─────

import urllib.parse  # noqa: E402

import httpx  # noqa: E402


def _query(request) -> str:
    return urllib.parse.parse_qs(request.content.decode())["query"][0]


def _uri(qid):
    return {"type": "uri", "value": f"http://www.wikidata.org/entity/{qid}"}


def _wikidata(statements, labels, broken_first=(), always_broken=False, calls=None):
    """An in-memory Wikidata: `statements` maps property -> [(s, o)] ids,
    `labels` maps id -> English label. Queries named in `broken_first` get a
    truncated body the first time, as the real service does on a timeout."""
    seen: dict[str, int] = {}

    def handler(request):
        q = _query(request)
        if calls is not None:
            calls.append(q)
        seen[q] = seen.get(q, 0) + 1
        if always_broken or (seen[q] == 1 and any(b in q for b in broken_first)):
            return httpx.Response(200, text='{"results": {"bindings": [ {"s')
        if "VALUES" in q:
            rows = [{"item": _uri(i), "label": {"value": labels[i]}}
                    for i in labels if f"wd:{i} " in q + " "]
            body = json.dumps({"results": {"bindings": rows}})
            return httpx.Response(200, text=body.replace("\t", "\t"))
        prop = next(p for p in statements if f"wdt:{p} " in q)
        rows = [{"s": _uri(s), "o": _uri(o)} for s, o in statements[prop]]
        return httpx.Response(200, json={"results": {"bindings": rows}})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


import json  # noqa: E402


async def test_fetch_gold_labels_every_statement_and_drops_unlabelled_items(monkeypatch):
    monkeypatch.setattr(chat_eval.asyncio, "sleep", _no_sleep)
    async with _wikidata({"P1542": [("Q1", "Q2"), ("Q3", "Q4")], "P828": [("Q5", "Q1")]},
                         {"Q1": "drought", "Q2": "famine", "Q3": "fire", "Q5": "wildfire"}) as client:
        snapshot = await chat_eval.fetch_gold(client)
    assert snapshot["pairs"]["effect"] == [["drought", "famine"]]
    assert snapshot["pairs"]["cause"] == [["wildfire", "drought"]]


async def test_fetch_gold_looks_labels_up_in_batches(monkeypatch):
    monkeypatch.setattr(chat_eval.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(chat_eval, "_LABEL_BATCH", 1)
    calls: list[str] = []
    async with _wikidata({"P1542": [("Q1", "Q2")], "P828": []},
                         {"Q1": "drought", "Q2": "famine"}, calls=calls) as client:
        snapshot = await chat_eval.fetch_gold(client)
    assert sum("VALUES" in q for q in calls) == 2
    assert snapshot["pairs"]["effect"] == [["drought", "famine"]]


async def test_fetch_gold_retries_a_truncated_body(monkeypatch):
    """Wikidata answers an overrun query with HTTP 200 and a cut-off body. That
    response must be retried, not frozen into the key as if it were complete."""
    monkeypatch.setattr(chat_eval.asyncio, "sleep", _no_sleep)
    async with _wikidata({"P1542": [("Q1", "Q2")], "P828": []},
                         {"Q1": "drought", "Q2": "famine"},
                         broken_first=("wdt:P1542", "VALUES")) as client:
        snapshot = await chat_eval.fetch_gold(client)
    assert snapshot["pairs"]["effect"] == [["drought", "famine"]]


async def test_fetch_gold_fails_loudly_when_a_response_never_arrives(monkeypatch):
    monkeypatch.setattr(chat_eval.asyncio, "sleep", _no_sleep)
    async with _wikidata({"P1542": [], "P828": []}, {}, always_broken=True) as client:
        try:
            await chat_eval.fetch_gold(client)
        except RuntimeError as exc:
            assert "P1542" in str(exc)
        else:
            raise AssertionError("a partial answer key was accepted")


async def test_fetch_gold_accepts_a_label_containing_a_raw_control_character(monkeypatch):
    """Real Wikidata labels carry raw tabs; strict JSON rejects them."""
    monkeypatch.setattr(chat_eval.asyncio, "sleep", _no_sleep)
    async with _wikidata({"P1542": [("Q1", "Q2")], "P828": []},
                         {"Q1": "x\ty", "Q2": "z"}) as client:
        snapshot = await chat_eval.fetch_gold(client)
    assert snapshot["pairs"]["effect"] == [["x\ty", "z"]]


async def test_http_worded_reads_crlf_sse_to_the_done_event():
    body = ('data: {"stage": "reasoning", "intent": "effect", "topics": [], "answer": {}}\r\n\r\n'
            'data: {"stage": "token", "text": "Inflation "}\r\n\r\n'
            'data: {"stage": "token", "text": "raises prices."}\r\n\r\n'
            'data: {"stage": "done", "text": "Inflation raises prices.", "llm": true}\r\n\r\n')
    chat = chat_eval.HttpChat("http://brain.test", "tok", 3, 8)
    await chat.client.aclose()
    chat.client = httpx.AsyncClient(
        base_url="http://brain.test",
        transport=httpx.MockTransport(lambda r: httpx.Response(
            200, text=body, headers={"content-type": "text/event-stream"})))
    text, by_model = await chat.worded("what does inflation cause", {})
    await chat.close()
    assert text == "Inflation raises prices." and by_model is True


async def _no_sleep(_seconds):
    return None


async def test_http_ask_returns_the_endpoints_plan_and_answer():
    """/api/brain/chat returns the answer with its parse under `plan`; the
    harness must score the parse the SERVER made, not re-parse locally."""
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "intent": "effect", "answered": True, "results": [{"concept": "unemployment"}],
            "plan": {"intent": "effect", "topics": ["inflation"], "wh": "what"}})

    chat = chat_eval.HttpChat("http://brain.test", "tok", 2, 5)
    await chat.client.aclose()
    chat.client = httpx.AsyncClient(base_url="http://brain.test",
                                    headers={"Authorization": "Bearer tok"},
                                    transport=httpx.MockTransport(handler))
    plan, answer = await chat.ask("what does inflation create")
    await chat.close()
    assert seen["auth"] == "Bearer tok"
    assert seen["body"] == {"query": "what does inflation create", "maxDepth": 2, "limit": 5}
    assert plan.intent == "effect" and plan.primary == "inflation"
    assert answer["results"][0]["concept"] == "unemployment"
