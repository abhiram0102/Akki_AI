"""Structure discovery from raw bytes.

The project's defining constraint is that nothing in the pipeline may carry
predefined knowledge of URL, HTML, link, word or sentence formats. Structure
has to be *discovered* from the bytes of a response, not parsed with rules
tuned to a format someone already knew about.

What this replaces
------------------
`brain_fetchers` previously hardcoded, per site: Wikipedia's `#mw-content-text`
container and `/wiki/` link prefix, arXiv's `blockquote.abstract`, a citation
regex `\\[\\d+\\]`, HTML's `<p>` element as the carrier of prose, a fixed list of
elements to strip, and a sentence splitter keyed to `.!?`. Every one of those
is knowledge of a format, and every one is gone from the path this module
serves.

What is discovered, and how
---------------------------
1. **Markup delimiters.** The byte pair that most consistently opens and closes
   spans across the document. In HTML this discovers `<` and `>`; given a
   document in an invented syntax it discovers that syntax's delimiters
   instead, having never been told they exist.
2. **Prose.** Whatever falls outside the discovered spans.
3. **Sentence boundaries.** The bytes that statistically precede a
   whitespace-then-capital transition. In English text this discovers `.`, `?`
   and `!` from evidence rather than being handed them.
4. **References.** Address-shaped runs inside markup spans, kept when they
   resolve against the document's own address, then narrowed to the shape that
   dominates the document, which is what separates article references from
   navigation and asset references without naming either.

The honest boundary
-------------------
Two things here are wire protocol rather than format knowledge, and are used
deliberately: the RFC 3986 character set that defines what a URI may contain,
and RFC-conformant resolution of a relative reference against a base. Those
define the transport itself. Knowing them is not the same as knowing that
Wikipedia keeps its articles under `/wiki/`, and the tests prove the difference
by feeding this module invented formats it has never seen.

Unicode case and whitespace classification come from the standard library, not
from a table written here.
"""
from collections import Counter
from urllib.parse import urljoin, urlparse

# RFC 3986 unreserved characters, the general delimiters that give a reference
# its structure, and the percent sign that introduces an escape. This is the
# transport's own alphabet, not a convention of any site.
#
# The RFC's sub-delimiters (!$&'()*+,;=) are deliberately excluded. They are
# legal inside a path but appear there almost never, while documents use them
# constantly to quote and separate values — `href='/a/b'` would otherwise be
# read as one long address beginning with the attribute's name. Excluding them
# lets a run END at whatever a document uses for quoting, without this module
# being told what that is. The cost is that a query string is truncated at its
# first separator, which for a crawler yields the canonical page address and is
# what we want anyway.
_URI_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "-._~:/?#@%"
)

# RFC 3986 sub-delimiters. They are excluded from a reference's path for the
# reason above, but the RFC's query grammar explicitly ADMITS them, and a
# search result commonly carries its target in a query parameter. So once a run
# has passed the `?` that begins a query, they are allowed back in — otherwise
# `/search?entry=1234` truncates to `/search?entry` and every result on such a
# page resolves to the same useless address. The distinction is the RFC's own,
# not any site's.
_QUERY_CHARS = frozenset("!$&'()*+,;=")

# A delimiter pair has to enclose a real share of the document to be structure
# rather than punctuation coincidence, and cannot enclose nearly all of it or
# there would be no prose left to read.
_MIN_SPANS = 12
_MIN_COVERAGE = 0.02
_MAX_COVERAGE = 0.97

# How many of the most frequent punctuation bytes to consider as delimiters.
_DELIMITER_CANDIDATES = 10

# A byte must precede this many sentence-like transitions before it is
# considered at all, and must then score at least this share of the best
# candidate's score (see `discover_sentence_terminators`).
_TERMINATOR_EVIDENCE = 3
_TERMINATOR_SHARE = 0.5

# A reference a document offers to a reader carries readable text; this is how
# many letters must follow a span before it counts as one.
_MIN_ANCHOR_LETTERS = 2

# Sentences outside this word range are navigation fragments or run-on blocks
# rather than statements, in any language with word separators.
_MIN_SENTENCE_WORDS = 5
_MAX_SENTENCE_WORDS = 40

# A statement is something a person would read. Script and data embedded in a
# page sit OUTSIDE the markup delimiters — the code between a script's opening
# and closing tags is not itself inside a span — so it survives separation and
# reads as prose. It does not look like prose though: it is dense with quotes,
# braces, colons and digits, and thin on plain words. Requiring most of a
# statement's tokens to be ordinary words removes it without naming scripts,
# data formats, or any element.
_MIN_WORD_RATIO = 0.6


def _candidate_delimiters(raw: str) -> list[str]:
    counts = Counter(ch for ch in raw if not ch.isalnum() and not ch.isspace())
    return [ch for ch, _ in counts.most_common(_DELIMITER_CANDIDATES)]


def _spans_for(raw: str, opener: str, closer: str) -> list[tuple[int, int]]:
    """Well-formed, non-overlapping opener..closer spans, scanned left to right.

    A span that would contain another opener is abandoned at that opener, so a
    stray delimiter cannot swallow the rest of the document.
    """
    spans: list[tuple[int, int]] = []
    i = 0
    length = len(raw)
    while i < length:
        start = raw.find(opener, i)
        if start == -1:
            break
        end = raw.find(closer, start + 1)
        if end == -1:
            break
        nested = raw.find(opener, start + 1)
        if nested != -1 and nested < end:
            i = nested
            continue
        spans.append((start, end + 1))
        i = end + 1
    return spans


def discover_delimiters(raw: str) -> tuple[str, str] | None:
    """The byte pair that behaves like markup delimiters in this document.

    Scores every ordered pair drawn from the document's most frequent
    punctuation by how many well-formed spans it produces. Returns None when
    nothing behaves like structure, which is the correct answer for a plain
    text document and means the whole document is prose.
    """
    if not raw:
        return None
    candidates = _candidate_delimiters(raw)
    best: tuple[float, str, str] | None = None
    total = len(raw)

    for opener in candidates:
        for closer in candidates:
            if opener == closer:
                continue
            spans = _spans_for(raw, opener, closer)
            if len(spans) < _MIN_SPANS:
                continue
            covered = sum(end - start for start, end in spans)
            coverage = covered / total
            if not (_MIN_COVERAGE <= coverage <= _MAX_COVERAGE):
                continue
            # A bracketing pair has three structural properties, none of
            # them linguistic and none naming any format.
            #
            # 1. The opener leads. Whatever a document opens with, it opens
            #    before it closes. This rejects reading a pair inside out —
            #    taking the closer as the opener encloses the prose BETWEEN
            #    records rather than the markup, and would otherwise score well
            #    since it yields as many spans and covers more bytes.
            if raw.find(opener) > raw.find(closer):
                continue

            # 2. Markup reads less like language than the text around it.
            #    Prose separates words with spaces at a steady rate; markup is
            #    names, separators and punctuation, and spaces it far more
            #    sparsely. Requiring the material INSIDE the spans to be less
            #    space-dense than the material outside rejects a pair that
            #    brackets a sentence rather than an element — a quote-to-full-
            #    stop pair, say, which otherwise encloses plenty of bytes
            #    perfectly consistently.
            #
            #    Whitespace comes from Unicode via the standard library, so no
            #    alphabet or punctuation set is written down here.
            inside_len = covered
            outside_len = total - covered
            if outside_len <= 0 or inside_len <= 0:
                continue
            inside_spaces = sum(
                1 for start, end in spans for ch in raw[start:end] if ch.isspace()
            )
            total_spaces = sum(1 for ch in raw if ch.isspace())
            if (inside_spaces / inside_len) >= ((total_spaces - inside_spaces) / outside_len):
                continue

            # 3. Balance: a real pair opens about as often as it closes,
            #    whereas a separator that merely recurs near the closer occurs
            #    at an unrelated rate.
            opener_count = raw.count(opener)
            closer_count = raw.count(closer)
            balance = min(opener_count, closer_count) / max(opener_count, closer_count)

            # Ranked by how consistently the pair brackets, then by how much it
            # encloses. Volume only breaks ties, so a pair enclosing a token
            # loses to one enclosing a whole element when both bracket equally
            # often.
            score = (len(spans) * balance, covered)
            if best is None or score > best[0]:
                best = (score, opener, closer)

    if best is None:
        return None
    return best[1], best[2]


def separate(raw: str, delimiters: tuple[str, str] | None = None,
             with_following: bool = False):
    """Split a document into its prose and its markup spans.

    Anything inside a discovered span is structure; everything else is text a
    reader would see. With no delimiters discovered the document is all prose.
    """
    if delimiters is None:
        delimiters = discover_delimiters(raw)
    if delimiters is None:
        return (raw, [], []) if with_following else (raw, [])

    opener, closer = delimiters
    spans = _spans_for(raw, opener, closer)
    if not spans:
        return (raw, [], []) if with_following else (raw, [])

    pieces: list[str] = []
    markup: list[str] = []
    cursor = 0
    for start, end in spans:
        pieces.append(raw[cursor:start])
        markup.append(raw[start:end])
        cursor = end
    pieces.append(raw[cursor:])

    # Joining on a space keeps words from two sides of a span fusing into one.
    text = " ".join(p.strip() for p in pieces if p.strip())
    text = " ".join(text.split())
    if with_following:
        # The text sitting immediately after each span, which is what tells a
        # reference the document shows a reader from one it loads silently.
        following = [raw[start:end] for start, end in zip(
            [e for _, e in spans],
            [st for st, _ in spans[1:]] + [len(raw)],
        )]
        return text, markup, following
    return text, markup


def discover_sentence_terminators(text: str) -> set[str]:
    """Which bytes end sentences in this text, learned from where they sit.

    A terminator is a byte that is usually followed by whitespace and then a
    capital letter. In English prose this yields `.`, `?` and `!` without any
    of them being named here; in a text that marks boundaries some other way it
    yields that instead. Case and whitespace come from Unicode via the standard
    library, so no alphabet is written down either.
    """
    followed_by_boundary: Counter = Counter()
    occurrences: Counter = Counter()

    for index, ch in enumerate(text):
        if ch.isalnum() or ch.isspace():
            continue
        occurrences[ch] += 1
        rest = text[index + 1:index + 3]
        if not rest or not rest[0].isspace():
            continue
        following = rest[1:2]
        if following and following.isupper():
            followed_by_boundary[ch] += 1

    if not followed_by_boundary:
        return set()

    # Scoring by rate alone fails on a real page, and the failure was measured
    # rather than imagined. On a Wikipedia article the full stop precedes 681
    # boundaries but does so only 29% of the time, because the page also
    # carries scripts and navigation where a full stop is followed by anything.
    # Meanwhile a navigation arrow appearing 105 times precedes a boundary 91%
    # of the time. A rate threshold therefore picks the arrow and discards the
    # full stop, which is exactly backwards.
    #
    # Both halves matter: how OFTEN a byte ends a sentence, and how much more
    # often it does so than punctuation in this text generally. The second is
    # measured against the document's own base rate, so a page full of prose
    # and a page full of markup are each judged on their own terms.
    total_boundaries = sum(followed_by_boundary.values())
    total_occurrences = sum(occurrences[ch] for ch in followed_by_boundary)
    base_rate = total_boundaries / total_occurrences if total_occurrences else 0
    if base_rate <= 0:
        return set()

    scores: dict[str, float] = {}
    for ch, hits in followed_by_boundary.items():
        if hits < _TERMINATOR_EVIDENCE:
            continue
        lift = (hits / occurrences[ch]) / base_rate
        scores[ch] = hits * lift

    if not scores:
        return set()
    best = max(scores.values())
    return {ch for ch, score in scores.items() if score >= best * _TERMINATOR_SHARE}


def split_sentences(text: str, terminators: set[str] | None = None) -> list[str]:
    """Break prose into statements at discovered boundaries.

    With nothing discovered the text is returned as a single statement rather
    than being cut at a guess.
    """
    if terminators is None:
        terminators = discover_sentence_terminators(text)
    if not terminators:
        candidate = [text.strip()] if text.strip() else []
    else:
        candidate = []
        current: list[str] = []
        for ch in text:
            current.append(ch)
            if ch in terminators:
                candidate.append("".join(current).strip())
                current = []
        tail = "".join(current).strip()
        if tail:
            candidate.append(tail)

    return [
        s for s in candidate
        if _MIN_SENTENCE_WORDS <= len(s.split()) <= _MAX_SENTENCE_WORDS
        and _is_prose(s)
    ]


def _is_prose(sentence: str) -> bool:
    """Whether a statement reads like language rather than like code or data."""
    tokens = sentence.split()
    if not tokens:
        return False
    words = sum(
        1 for t in tokens
        if t.strip(".,;:()[]{}\"'").isalpha()
    )
    return words / len(tokens) >= _MIN_WORD_RATIO


def _address_runs(fragment: str, delimiters: tuple[str, str] | None = None) -> list[str]:
    """Maximal runs of URI-legal characters inside one markup span.

    The document's own discovered delimiters are excluded from the run even
    when they are legal URI characters. `~` is RFC 3986 unreserved, so a
    document that happens to close its spans with `~` would otherwise have that
    delimiter absorbed onto the end of every address it contains. What
    terminates a run is therefore partly learned from the document rather than
    fixed here.
    """
    excluded = set(delimiters) if delimiters else set()
    runs: list[str] = []
    current: list[str] = []
    in_query = False
    for ch in fragment:
        allowed = ch in _URI_CHARS or (in_query and ch in _QUERY_CHARS)
        if allowed and ch not in excluded:
            current.append(ch)
            if ch == "?":
                in_query = True
        else:
            if len(current) > 1:
                runs.append("".join(current))
            current = []
            in_query = False
    if len(current) > 1:
        runs.append("".join(current))
    return runs


def discover_references(markup: list[str], base_url: str,
                        delimiters: tuple[str, str] | None = None,
                        following: list[str] | None = None,
                        with_text: bool = False,
                        narrow_to_shape: bool = True):
    """Addresses this document points at, found without knowing its format.

    Every URI-legal run inside every markup span is resolved against the
    document's own address; a run that resolves to a usable absolute address is
    a candidate. Candidates are then narrowed to the path shape that dominates
    the document, which is what separates a page's body references from its
    navigation and assets. That shape is measured per document rather than
    described here, so a site whose articles sit at a different depth needs no
    change.
    """
    base_host = urlparse(base_url).netloc
    resolved: list[str] = []
    seen: set[str] = set()
    anchor_text: dict[str, str] = {}

    for index, span in enumerate(markup):
        # A reference the document OFFERS is attached to something readable —
        # the words a reader clicks. A reference the document merely LOADS,
        # such as a stylesheet or a script, is followed by more structure and
        # never by prose. Filtering on that separates content from assets
        # without naming a single file type or element, which is what a rule
        # keyed to ".css" or to a link element would have done.
        if following is not None:
            after = following[index] if index < len(following) else ""
            if sum(1 for ch in after if ch.isalpha()) < _MIN_ANCHOR_LETTERS:
                continue
        body = span
        if delimiters:
            body = body.strip(delimiters[0] + delimiters[1])
        runs = _address_runs(span, delimiters)
        for run in runs:
            # A run with no path structure at all is an attribute value or a
            # bare token, not a reference.
            if "/" not in run:
                continue
            # A run that IS the entire span body is a bare name, not a
            # reference carried by one. A closing element reads as a path —
            # `</div>` yields `/div`, which resolves to a perfectly valid
            # address that no document ever pointed at. A real reference sits
            # alongside the element's own name, so it never occupies the whole
            # span on its own.
            if run == body.strip():
                continue
            try:
                candidate = urljoin(base_url, run)
            except ValueError:
                continue
            parts = urlparse(candidate)
            if parts.scheme not in ("http", "https") or not parts.netloc:
                continue
            # A fragment points inside the document already being read.
            clean = candidate.split("#", 1)[0]
            if clean in seen or clean == base_url:
                continue
            seen.add(clean)
            resolved.append(clean)
            # Keep the words the document attached to this reference. They are
            # what a reader sees and clicks, and they are the only evidence in
            # the document about what the reference is FOR.
            anchor_text[clean] = " ".join(
                (following[index] if following and index < len(following) else "").split()
            )[:200]

    same_host = [u for u in resolved if urlparse(u).netloc == base_host]
    pool = same_host or resolved
    if not pool:
        return []


    depths = Counter(len([p for p in urlparse(u).path.split("/") if p]) for u in pool)
    if not depths:
        return []
    dominant_depth, _ = depths.most_common(1)[0]

    # Narrowing to the dominant shape is right for a page being READ, where
    # body references share a shape and navigation does not. It is wrong for a
    # page being SEARCHED, where the results are the minority and the site's
    # own navigation is the majority — narrowing there returns precisely the
    # links a caller does not want.
    kept = [
        u for u in pool
        if not narrow_to_shape
        or len([p for p in urlparse(u).path.split("/") if p]) == dominant_depth
    ]
    if with_text:
        return [{"url": u, "text": anchor_text.get(u, "")} for u in kept]
    return kept


def discover_structure(raw: str, base_url: str, max_links: int = 50,
                       narrow_to_shape: bool = True) -> dict:
    """Everything this module can learn about one response.

    Returns the prose, the statements it breaks into, the references it points
    at, and the structure that was discovered along the way. The discovered
    delimiters and terminators are returned rather than hidden so a caller (or
    a test) can see what the document taught it.
    """
    delimiters = discover_delimiters(raw)
    text, markup, following = separate(raw, delimiters, with_following=True)
    terminators = discover_sentence_terminators(text)
    sentences = split_sentences(text, terminators)
    references = discover_references(
        markup, base_url, delimiters, following,
        with_text=True, narrow_to_shape=narrow_to_shape,
    )[:max_links]
    links = [r["url"] for r in references]

    return {
        "text": text,
        "sentences": sentences,
        "links": links,
        # Each reference with the words the document attached to it, which is
        # what lets a caller choose the one that matches what it is looking for
        # instead of taking whichever came first.
        "references": references,
        "delimiters": delimiters,
        "terminators": sorted(terminators),
    }
