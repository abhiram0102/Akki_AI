"""
AKKI Brain — Stage 1: Explorer

Moves through the internet like a signal through space.
No direction. No rules. No predefined targets.
Touches everything. Collects raw co-occurrence data.
Builds knowledge from pure exposure.

After enough exploration, patterns form on their own.
That is Stage 2.
"""

import requests
from bs4 import BeautifulSoup
from collections import defaultdict, Counter
import re
import time
import json
import random
import math
import pickle
import os
from urllib.parse import quote, urljoin, urlparse

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

SAVE_PATH = "brain/knowledge.pkl"


class KnowledgeBase:
    """
    Everything the system has learned from exploration.
    Saved to disk — persists between runs.
    Gets smarter every time it runs.
    """

    def __init__(self):
        # co-occurrence: how often two words appear near each other
        self.cooccurrence = defaultdict(Counter)

        # positional: average sentence position of each word (0=start, 1=end)
        self.positions = defaultdict(list)

        # transition: word A → word B, how often and in what direction
        self.transitions = defaultdict(Counter)

        # sentence count per word
        self.word_sentences = defaultdict(int)

        # total word frequency
        self.word_freq = Counter()

        # pages visited
        self.visited_urls = set()

        # concepts encountered
        self.concepts_seen = set()

        # total sentences processed
        self.total_sentences = 0

        # knowledge version — increases as it learns more
        self.version = 0

    def save(self):
        os.makedirs("brain", exist_ok=True)
        with open(SAVE_PATH, "wb") as f:
            pickle.dump(self, f)
        print(f"[KB] Saved. Version {self.version}. Sentences: {self.total_sentences}")

    @staticmethod
    def load():
        if os.path.exists(SAVE_PATH):
            with open(SAVE_PATH, "rb") as f:
                kb = pickle.load(f)
            print(f"[KB] Loaded. Version {kb.version}. Sentences: {kb.total_sentences}")
            return kb
        return KnowledgeBase()


class Mover:
    """
    Moves through the internet space.
    Like a particle — starts somewhere, follows links, goes wherever connections lead.
    No predefined path. No target. Pure exploration.
    """

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb
        self.queue = []         # URLs to visit next
        self.visited = kb.visited_urls

    def seed(self, concept: str):
        """Start from a concept. Find its Wikipedia page. Begin moving."""
        url = f"https://en.wikipedia.org/wiki/{quote(concept.replace(' ', '_'))}"
        if url not in self.visited:
            self.queue.append(url)

    def move(self, steps: int = 20):
        """
        Move through space for N steps.
        Each step: visit a page, learn from it, follow a link to the next page.
        """
        steps_done = 0

        while self.queue and steps_done < steps:
            url = self.queue.pop(0)

            if url in self.visited:
                continue

            self.visited.add(url)
            self.kb.visited_urls.add(url)

            print(f"  [move {steps_done+1}/{steps}] {url[:70]}")

            # Fetch the page
            text, links = self._fetch(url)

            if text:
                # Learn from this page
                sentences = self._extract_sentences(text)
                for sentence in sentences:
                    self._learn_from_sentence(sentence)

                print(f"    → learned from {len(sentences)} sentences")

            # Add new links to explore
            # Mix: some random, some first — to explore widely
            random.shuffle(links)
            for link in links[:8]:
                if link not in self.visited:
                    self.queue.append(link)

            steps_done += 1
            self.kb.version += 1
            time.sleep(0.2)

        print(f"  [mover] Done. Total sentences in KB: {self.kb.total_sentences}")

    def _fetch(self, url: str):
        """Fetch a page. Return (text, internal_links)."""
        try:
            r = requests.get(url, headers=HEADERS, timeout=8)
            if r.status_code != 200:
                return "", []

            soup = BeautifulSoup(r.text, "html.parser")

            # Remove noise
            for tag in soup(["script", "style", "nav", "footer",
                             "header", ".reflist", ".navbox"]):
                tag.decompose()

            # Get text
            paras = soup.select("p")
            text = " ".join(p.get_text() for p in paras)
            text = re.sub(r'\[\d+\]', '', text)  # remove citations
            text = re.sub(r'\s+', ' ', text)

            # Get internal Wikipedia links — these are the connections in the space
            links = []
            base = "https://en.wikipedia.org"
            for a in soup.select("a[href^='/wiki/']"):
                href = a.get("href", "")
                if ":" not in href and "#" not in href:
                    full = base + href
                    if full not in self.visited:
                        links.append(full)

            return text, links[:20]

        except Exception as e:
            return "", []

    def _extract_sentences(self, text: str) -> list[str]:
        """Split text into clean sentences."""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        clean = []
        for s in sentences:
            s = s.strip()
            words = s.split()
            if 4 <= len(words) <= 40:
                clean.append(s)
        return clean

    def _learn_from_sentence(self, sentence: str):
        """
        Learn from one sentence.
        Record: co-occurrence, positions, transitions.
        No rules. Pure observation.
        """
        words = re.findall(r'\b[a-z]{3,}\b', sentence.lower())
        if len(words) < 3:
            return

        self.kb.total_sentences += 1
        n = len(words)

        for i, word in enumerate(words):
            self.kb.word_freq[word] += 1
            self.kb.word_sentences[word] += 1

            # Record normalized position (0=start, 1=end)
            pos = i / n
            self.kb.positions[word].append(pos)

            # Co-occurrence within a 5-word window
            window_start = max(0, i - 5)
            window_end = min(n, i + 6)
            for j in range(window_start, window_end):
                if j != i:
                    other = words[j]
                    if other != word:
                        self.kb.cooccurrence[word][other] += 1

            # Transitions: what comes directly after each word
            if i + 1 < n:
                next_word = words[i + 1]
                self.kb.transitions[word][next_word] += 1


class PatternExtractor:
    """
    After exploration, extracts what the system learned.

    Discovers:
    1. Which words are relationship words (appear at verb position, bridge many pairs)
    2. Which concepts co-occur strongly with the target concept
    3. What direction those relationships go (cause → effect)

    All from pure statistics. Nothing hardcoded.
    """

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def find_relationship_words(self, top_n: int = 50) -> list[str]:
        """
        Relationship words (verbs) appear consistently at normalized positions
        between 0.25 and 0.65 — after the subject, before the object.
        They also bridge many different word pairs.
        Discovered purely from position statistics.
        """
        scores = {}

        total_words = sum(self.kb.word_freq.values())

        for word, positions in self.kb.positions.items():
            if len(positions) < 5:
                continue

            freq = self.kb.word_freq[word]
            avg_pos = sum(positions) / len(positions)
            pos_variance = sum((p - avg_pos)**2 for p in positions) / len(positions)

            # Verb position: consistently in the middle of sentences
            # Low variance in position = consistently in same place = grammatical role
            pos_score = 1.0 - abs(avg_pos - 0.45) * 2  # peak at 0.45
            consistency = 1.0 / (pos_variance + 0.01)   # low variance = consistent

            # Co-occurrence diversity: bridges many different concepts
            diversity = len(self.kb.cooccurrence.get(word, {}))

            # Not too rare, not too common
            freq_ratio = freq / max(total_words, 1)
            freq_score = math.exp(-abs(math.log(freq_ratio + 1e-10) + 8))

            # Final score
            if pos_score > 0 and diversity > 3:
                score = pos_score * consistency * diversity * freq_score
                scores[word] = score

        sorted_words = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [w for w, s in sorted_words[:top_n]]

    def find_related_concepts(self, concept: str, top_n: int = 20) -> list[tuple]:
        """
        Find concepts strongly related to the target.
        Uses co-occurrence strength normalized by individual frequencies.
        Returns (concept, strength) pairs.
        """
        if concept not in self.kb.cooccurrence:
            return []

        concept_freq = max(self.kb.word_freq[concept], 1)
        total = sum(self.kb.word_freq.values())

        scored = []
        for other, count in self.kb.cooccurrence[concept].items():
            other_freq = max(self.kb.word_freq[other], 1)

            # Pointwise Mutual Information (PMI)
            # Measures how much more often they co-occur than by chance
            p_xy = count / total
            p_x  = concept_freq / total
            p_y  = other_freq / total

            if p_x > 0 and p_y > 0 and p_xy > 0:
                pmi = math.log(p_xy / (p_x * p_y))
                if pmi > 0 and len(other) > 3:
                    scored.append((other, round(pmi, 3)))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_n]

    def find_direction(self, concept: str, related: str) -> str:
        """
        Does concept → related (concept causes/leads to related)?
        Or related → concept (related causes/leads to concept)?

        Learn from average positions:
        - If concept tends to appear BEFORE related → concept is cause
        - If concept tends to appear AFTER related → concept is effect
        """
        concept_pos = self.kb.positions.get(concept, [])
        related_pos = self.kb.positions.get(related, [])

        if not concept_pos or not related_pos:
            return "unknown"

        avg_concept = sum(concept_pos) / len(concept_pos)
        avg_related = sum(related_pos) / len(related_pos)

        # If concept appears earlier in sentences on average → it is the cause
        if avg_concept < avg_related - 0.05:
            return "leads_to"      # concept → related
        elif avg_related < avg_concept - 0.05:
            return "depends_on"    # concept ← related (related comes first)
        else:
            return "related"       # bidirectional or unclear

    def extract_dependencies(self, concept: str) -> dict:
        """
        Full dependency extraction for a concept.
        Returns what it depends on and what it leads to.
        All learned from pure exploration — no rules.
        """
        related = self.find_related_concepts(concept, top_n=30)

        depends_on = []
        leads_to   = []
        related_to = []

        for other_concept, strength in related:
            direction = self.find_direction(concept, other_concept)

            if direction == "depends_on":
                depends_on.append((other_concept, strength))
            elif direction == "leads_to":
                leads_to.append((other_concept, strength))
            else:
                related_to.append((other_concept, strength))

        return {
            "concept":    concept,
            "depends_on": depends_on[:10],
            "leads_to":   leads_to[:10],
            "related_to": related_to[:10],
        }


class ConvergenceDetector:
    """
    Grows branches from multiple origins independently.
    Finds where they converge.
    Convergence = hidden truth.
    The more unrelated the origins that converge → the more real the truth.
    """

    def __init__(self, kb: KnowledgeBase, extractor: PatternExtractor):
        self.kb = kb
        self.extractor = extractor

    def detect(self, concept: str, branch_depth: int = 2) -> list[dict]:
        """
        Start from the concept.
        Find all first-level dependencies.
        Treat each as an independent origin.
        Grow from each one.
        Find where they all meet.
        """
        # Track which concepts were reached from which origins
        reached_by = defaultdict(set)

        # Mark origin
        reached_by[concept].add("__origin__")

        # Get first level
        deps = self.extractor.extract_dependencies(concept)
        first_level = (
            [c for c, _ in deps["depends_on"]] +
            [c for c, _ in deps["leads_to"]] +
            [c for c, _ in deps["related_to"]]
        )[:12]

        # Mark first level as reached from origin
        for c in first_level:
            reached_by[c].add(concept)

        # Grow from each first-level concept as independent origin
        for origin in first_level[:8]:
            branch_deps = self.extractor.extract_dependencies(origin)
            branch_concepts = (
                [c for c, _ in branch_deps["depends_on"]] +
                [c for c, _ in branch_deps["leads_to"]] +
                [c for c, _ in branch_deps["related_to"]]
            )[:8]

            for c in branch_concepts:
                reached_by[c].add(origin)

            # Level 2 if requested
            if branch_depth >= 2:
                for branch2 in branch_concepts[:4]:
                    b2_deps = self.extractor.extract_dependencies(branch2)
                    b2_concepts = (
                        [c for c, _ in b2_deps["depends_on"]] +
                        [c for c, _ in b2_deps["leads_to"]]
                    )[:6]
                    for c in b2_concepts:
                        reached_by[c].add(branch2)

        # Find convergence points — reached by 2+ different origins
        convergences = []
        for c, origins in reached_by.items():
            if len(origins) >= 2 and c != concept and c not in first_level:
                convergences.append({
                    "concept":      c,
                    "reached_from": list(origins),
                    "strength":     len(origins),
                })

        convergences.sort(key=lambda x: x["strength"], reverse=True)
        return convergences[:15]


class Brain:
    """
    The full system.
    Stage 1: Explore the internet space. Learn with no direction.
    Stage 2: Use what was learned. Find dependencies. Find convergence.
    Gets smarter every run because knowledge persists.
    """

    def __init__(self):
        self.kb = KnowledgeBase.load()

    def explore(self, concept: str, steps: int = 30):
        """
        Stage 1: Move through the internet from this concept.
        Learn from everything encountered.
        No direction. No target. Pure exploration.
        """
        print(f"\n[Stage 1: Explore] Starting from '{concept}'. Steps: {steps}")
        print(f"[Stage 1: Explore] Current KB: {self.kb.total_sentences} sentences")
        print()

        mover = Mover(self.kb)
        mover.seed(concept)
        mover.move(steps=steps)

        self.kb.save()
        print(f"\n[Stage 1: Done] KB now has {self.kb.total_sentences} sentences")

    def think(self, concept: str) -> dict:
        """
        Stage 2: Use accumulated knowledge to find hidden dependencies.
        Works best after exploration. Gets better with more exploration.
        """
        print(f"\n[Stage 2: Think] Concept: '{concept}'")
        print(f"[Stage 2: Think] Using {self.kb.total_sentences} sentences of learned knowledge")
        print()

        extractor  = PatternExtractor(self.kb)
        detector   = ConvergenceDetector(self.kb, extractor)
        rel_words  = extractor.find_relationship_words(top_n=30)
        deps       = extractor.extract_dependencies(concept)
        convergences = detector.detect(concept, branch_depth=2)

        result = {
            "concept":              concept,
            "sentences_in_memory":  self.kb.total_sentences,
            "pages_explored":       len(self.kb.visited_urls),
            "relationship_words":   rel_words[:20],
            "depends_on":           deps["depends_on"],
            "leads_to":             deps["leads_to"],
            "related_to":           deps["related_to"],
            "convergence_points":   convergences,
        }

        return result

    def print_results(self, r: dict):
        print(f"\n{'='*65}")
        print(f"CONCEPT : {r['concept'].upper()}")
        print(f"Memory  : {r['sentences_in_memory']} sentences from {r['pages_explored']} pages")
        print(f"{'='*65}")

        print(f"\nRelationship words discovered (verb position, self-learned):")
        print(f"  {r['relationship_words'][:15]}")

        print(f"\nDEPENDS ON — '{r['concept']}' needs:")
        for c, strength in r["depends_on"] or [("none found", 0)]:
            print(f"  ←  {c}  (PMI: {strength})")

        print(f"\nLEADS TO — '{r['concept']}' produces:")
        for c, strength in r["leads_to"] or [("none found", 0)]:
            print(f"  →  {c}  (PMI: {strength})")

        print(f"\nRELATED — bidirectional or unclear direction:")
        for c, strength in r["related_to"][:8] or [("none found", 0)]:
            print(f"  ↔  {c}  (PMI: {strength})")

        print(f"\nCONVERGENCE POINTS — hidden truths found by multiple independent paths:")
        if r["convergence_points"]:
            for cp in r["convergence_points"]:
                print(f"  '{cp['concept']}'")
                print(f"    strength: {cp['strength']}")
                print(f"    reached independently from: {cp['reached_from']}")
        else:
            print("  None yet — explore more pages to find convergence")

        print(f"{'='*65}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python brain/explorer.py explore love      # explore internet from 'love'")
        print("  python brain/explorer.py think love        # find dependencies of 'love'")
        print("  python brain/explorer.py run love          # explore then think")
        sys.exit(0)

    mode    = sys.argv[1]
    concept = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "love"
    brain   = Brain()

    if mode == "explore":
        brain.explore(concept, steps=30)

    elif mode == "think":
        result = brain.think(concept)
        brain.print_results(result)
        fname = f"brain/result_{concept.replace(' ','_')}.json"
        with open(fname, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\nSaved → {fname}")

    elif mode == "run":
        # Explore first, then think
        brain.explore(concept, steps=25)
        # Also explore related concepts for richer knowledge
        for related in ["emotion", "attachment", "desire", "connection", "trust"]:
            brain.explore(related, steps=10)
        # Now think
        result = brain.think(concept)
        brain.print_results(result)
        fname = f"brain/result_{concept.replace(' ','_')}.json"
        with open(fname, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\nSaved → {fname}")

    else:
        print(f"Unknown mode: {mode}. Use: explore / think / run")
