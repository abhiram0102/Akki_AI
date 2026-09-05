"""Answer formation for POST /api/brain/ask.

Implements "Function 7 — Answer Formation" (AKKI_FULL_ARCHITECTURE.md, step 6),
which specifies the answer as four things: what the concept depends on, what it
produces, hidden convergences from unrelated origins, and connections nobody
usually makes. Each maps onto graph capability that already existed and was
simply never reached from `/ask`:

    dependsOn    -> brain_service._top_dependencies   (in-edges)
    produces     -> brain_service._top_associations   (out-edges)
    convergences -> brain_service.discover / discover_convergence
    derived      -> brain_service.infer_links         (2-hop, nothing stated it)

Design decision — the voice is composed, not generated.
Every sentence here is assembled from facts already in the graph. No language
model writes any of it, which keeps two documented constraints intact (the
design spec's "Any LLM in the answer path" non-goal, and the architecture
doc's "never asks LLM after Phase 1") and keeps every claim traceable back to
an edge with real evidence attached. The brain speaks in first person because
the content is its own: it read the sources, it derived the links. A narrator
model could later rephrase `summary` without being allowed to add a fact, and
nothing in this module would need to change.
"""
from starlette.concurrency import run_in_threadpool

from backend.services import brain_meaning, brain_query, brain_service

# Evidence thresholds for describing how sure the brain is. Deterministic, so
# the same graph state always produces the same wording.
_STRONG_EVIDENCE = 5
_THIN_EVIDENCE = 2

# Single-topic convergence (Function 7 step 5). The topic's own strongest
# branches act as independent origins; a concept several of them reach is a hub
# nothing stated directly. Depth is kept short because these origins start out
# related to each other, so a long walk would find trivial common ground.
_CONVERGENCE_SEEDS = 4
_CONVERGENCE_DEPTH = 2
_MIN_ORIGINS = 3


def _names(items: list[dict], key: str = "word", limit: int = 3) -> list[str]:
    return [i[key] for i in items[:limit]]


def _join(names: list[str]) -> str:
    """"a", "a and b", "a, b and c" — Oxford-free, matches spoken phrasing."""
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _confidence(evidence: list[dict]) -> str:
    """How much the brain has actually seen, said qualitatively rather than as
    a number the user would have to interpret."""
    if not evidence:
        return "none"
    strong = sum(1 for e in evidence if (e.get("count") or 0) >= _STRONG_EVIDENCE)
    if strong >= _THIN_EVIDENCE:
        return "strong"
    if len(evidence) >= _THIN_EVIDENCE:
        return "moderate"
    return "thin"


def _derived_sentence(derived: list[dict]) -> str | None:
    """The line that makes this not retrieval: a link the brain reasoned its
    way to, which no single source stated."""
    if not derived:
        return None
    top = derived[0]
    via = top.get("via")
    if via:
        return (f"And one I worked out myself: {top['concept']}, reached through {via}. "
                f"Nothing I read said that directly.")
    return f"And one I worked out myself: {top['concept']}. Nothing I read said that directly."


def _compose(plan, sections: dict) -> str:
    """Build the spoken answer from the sections that actually have content."""
    topic = plan.primary or plan.raw
    depends = _join(_names(sections["dependsOn"]))
    produces = _join(_names(sections["produces"]))
    parts: list[str] = []

    if plan.intent == brain_query.RELATE:
        meeting = _join(_names(sections["convergences"], key="concept"))
        other = plan.secondary
        if meeting:
            parts.append(f"{topic} and {other} meet at {meeting}.")
        else:
            parts.append(f"I can't yet find where {topic} and {other} meet.")

    elif plan.intent == brain_query.EXPLORE:
        meeting = _join(_names(sections["convergences"], key="concept"))
        if meeting:
            parts.append(
                f"Starting from {_join(plan.topics)} separately, I keep arriving at "
                f"{meeting}."
            )
        else:
            parts.append(f"I can't yet find common ground between {_join(plan.topics)}.")

    elif plan.intent == brain_query.CAUSE:
        if depends:
            parts.append(f"{topic} rests on {depends}.")
        if produces:
            parts.append(f"In turn it drives {produces}.")

    elif plan.intent == brain_query.EFFECT:
        if produces:
            parts.append(f"{topic} drives {produces}.")
        if depends:
            parts.append(f"It rests on {depends} to do it.")

    else:  # DEFINE
        if depends:
            parts.append(f"{topic} rests on {depends}.")
            if produces:
                parts.append(f"It drives {produces}.")
        elif produces:
            # Without the leading sentence there is no antecedent, so "It
            # drives galaxy" reads as a fragment. Name the topic instead.
            parts.append(f"{topic} drives {produces}.")

    if not parts:
        parts.append(f"I don't know {topic} well enough yet to say anything useful about it.")

    derived_line = _derived_sentence(sections["derived"])
    if derived_line:
        parts.append(derived_line)

    spoken = " ".join(parts)
    # Concept names are stored lowercase, so a sentence that opens with one
    # would otherwise start mid-word-looking. Capitalize only the first letter;
    # the concept's own spelling elsewhere in the sentence is left alone.
    return spoken[:1].upper() + spoken[1:] if spoken else spoken


def _gap(sections: dict, plan, confidence: str) -> str | None:
    """What the brain knows it does not know. Function 7 step 8 feeds this back
    into the reading queue; surfacing it is also the single most Jarvis-like
    thing the answer does, because admitting a gap is what a system that is
    actually reasoning about its own state can do."""
    total = len(sections["dependsOn"]) + len(sections["produces"])
    if total == 0:
        return f"I have nothing solid on {plan.primary or plan.raw} yet."
    if not sections["dependsOn"]:
        return f"I can see what {plan.primary} leads to, but not yet what it rests on."
    if not sections["produces"]:
        return f"I can see what {plan.primary} rests on, but not yet what it leads to."
    # Only admit thinness when the evidence really is thin. Deriving this from
    # the same signal as `confidence` stops the answer from reporting strong
    # confidence and "still thin" in the same breath.
    if confidence == "thin":
        return f"My picture of {plan.primary} is still thin. I'd want to read more."
    return None


async def build(plan, min_count: int = brain_service.MIN_EDGE_COUNT,
                sources: list[str] | None = None,
                produces: list[dict] | None = None,
                derived: list[dict] | None = None) -> dict:
    """Run the graph operations this intent calls for and compose the answer.

    `produces` and `derived` let a caller that has already fetched out-edges and
    derived links hand them in rather than have them queried a second time. The
    `/ask` endpoint does exactly that: it needs out-edges anyway to decide
    whether to learn first, so re-reading them here would be a wasted round trip
    AND could return something different from what the caller is about to
    report, leaving the spoken answer disagreeing with its own evidence list.

    Returns the four Function 7 sections plus the spoken `summary`, an
    `observation` the user did not ask for, an honest `gap`, and `provenance`
    naming what was actually read.
    """
    primary = plan.primary
    sections: dict = {"dependsOn": [], "produces": [], "convergences": [], "derived": []}

    if plan.intent == brain_query.RELATE and plan.secondary:
        result = await brain_service.discover(primary, plan.secondary)
        sections["convergences"] = result.get("convergencePoints", [])[:5]
    elif plan.intent == brain_query.EXPLORE:
        result = await brain_service.discover_convergence(plan.topics)
        sections["convergences"] = result.get("convergencePoints", [])[:5]

    if primary:
        # Both directions are read for every intent. Intent decides which one
        # leads the sentence, not which one is fetched — an answer that knows
        # both halves can always say the more interesting one.
        sections["dependsOn"] = await brain_service._top_dependencies(primary, min_count=min_count)
        sections["produces"] = (
            produces if produces is not None
            else await brain_service._top_associations(primary, min_count=min_count)
        )
        sections["derived"] = (
            derived if derived is not None
            else await brain_service.infer_links(primary, min_count=min_count)
        )

    # Function 7 step 5 says to find convergence points related to the
    # question — for ANY question, not only ones naming several concepts.
    # Previously a single-topic question never ran convergence at all, so the
    # capability the architecture doc calls "the moment of intelligence" was
    # unreachable from the most common kind of query.
    #
    # For one topic, its own strongest branches become the independent origins.
    # A concept that several of those branches all lead back to is a hub the
    # topic depends on without any single source saying so. Seeds come from
    # edges already fetched, so this costs no extra neighbour lookup.
    if not sections["convergences"] and len(sections["produces"]) >= _MIN_ORIGINS:
        seeds = [i["word"] for i in sections["produces"][:_CONVERGENCE_SEEDS]]
        try:
            result = await brain_service.discover_convergence(
                seeds, max_depth=_CONVERGENCE_DEPTH, min_origins=_MIN_ORIGINS,
            )
            # A seed or the topic itself turning up is not a discovery.
            excluded = set(seeds) | {primary}
            sections["convergences"] = [
                p for p in result.get("convergencePoints", [])
                if p.get("concept") not in excluded
            ][:3]
        except Exception:
            # Convergence is an enrichment; an answer without it is still a
            # correct answer, so a traversal failure must not lose the rest.
            sections["convergences"] = []

    # Function 7 step 3: which meaning of the concept is being asked about.
    # Embedding and clustering are CPU-bound, so they run off the event loop.
    # A concept with a single known sense returns None and the answer simply
    # does not mention senses, rather than asserting a distinction that is not
    # there.
    sense = None
    if primary:
        try:
            sense = await run_in_threadpool(
                brain_meaning.disambiguate, primary, plan.raw
            )
        except Exception:
            sense = None

    # Detecting the sense is only half the job. The graph is single-sense —
    # every use of a word collapses onto one node — so a concept's stored
    # neighbours mix its meanings together, and an answer about emotional fire
    # would still come back talking about oxygen and fuel. Intersecting those
    # neighbours with the vocabulary of the sense actually being asked about
    # separates them again.
    #
    # DESIGN NOTE — why this happens here and not in the graph.
    # The alternative was to tag every edge with the sense it came from and
    # partition the graph itself. That was rejected: cluster identity is not
    # stable as contexts accumulate, so an edge written today as sense 1 could
    # denote a different sense once more reading shifts the clusters, and there
    # is no migration for edges already written. Filtering at answer time reads
    # the current clustering every time, so it is always consistent with what
    # the brain currently believes, and needs no schema change or migration.
    sense_filtered = False
    if sense is not None:
        try:
            vocabulary = await run_in_threadpool(
                brain_meaning.sense_vocabulary, primary, sense["sense"]
            )
        except Exception:
            vocabulary = set()
        if vocabulary:
            def in_sense(items, key):
                return [i for i in items if (i.get(key) or "").split()[-1] in vocabulary]

            narrowed = {
                "dependsOn": in_sense(sections["dependsOn"], "word"),
                "produces": in_sense(sections["produces"], "word"),
                "derived": in_sense(sections["derived"], "concept"),
            }
            # Never let narrowing empty the answer. A sense whose vocabulary
            # happens not to overlap the graph's neighbours is a reason to say
            # less confidently which meaning applies, not a reason to report
            # knowing nothing about a concept the brain has genuinely read.
            if narrowed["dependsOn"] or narrowed["produces"]:
                sections.update(narrowed)
                sense_filtered = True

    evidence = sections["dependsOn"] + sections["produces"]
    confidence = _confidence(evidence)

    # The unprompted observation: something relevant the user did not ask for.
    observation = None
    if sense:
        # Saying which sense it settled on is more useful than any other
        # remark, because it tells the reader what the rest of the answer is
        # about — and a concept with two meanings is exactly where a confident
        # answer about the wrong one would mislead.
        observation = (
            f"You seem to mean {primary} in the sense of "
            f"{_join(sense.get('label') or [])}. I know it used other ways too."
        )
    elif sections["convergences"] and plan.intent in (
            brain_query.DEFINE, brain_query.CAUSE, brain_query.EFFECT):
        # A concept reached from several independent branches is stronger
        # evidence of a hidden dependency than any single 2-hop link, so it
        # outranks the derived link for the volunteered remark.
        top = sections["convergences"][0]
        origins = top.get("origins") or []
        observation = (
            f"Something I noticed on my own: {_join(origins[:3])} all lead back to "
            f"{top.get('concept')}. Nothing I read connected them on purpose."
        )
    elif plan.intent in (brain_query.DEFINE, brain_query.CAUSE, brain_query.EFFECT):
        if len(sections["derived"]) > 1:
            second = sections["derived"][1]
            observation = (f"I also noticed {primary} connects to {second['concept']}"
                           + (f" through {second['via']}" if second.get("via") else "")
                           + ", which isn't an obvious pairing.")
    elif sections["convergences"]:
        top = sections["convergences"][0]
        observation = (f"{top.get('concept')} is where those paths meet most closely, "
                       f"and nothing I read connected them on purpose.")

    return {
        **plan.as_dict(),
        "dependsOn": sections["dependsOn"],
        "produces": sections["produces"],
        "convergences": sections["convergences"],
        "derived": sections["derived"],
        "summary": _compose(plan, sections),
        "observation": observation,
        "gap": _gap(sections, plan, confidence),
        "confidence": confidence,
        "sense": sense,
        # Whether the evidence above was narrowed to the chosen sense, so a
        # reader can tell a sense-specific answer from one that merely knows
        # which sense was meant.
        "senseFiltered": sense_filtered,
        "provenance": sources or [],
    }
