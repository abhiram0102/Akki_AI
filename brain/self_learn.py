"""
AKKI Self-Teaching Grammar Engine — v3

No hardcoded rules. No LLM. No API keys.
Reads full Wikipedia articles from the internet.
Discovers grammar patterns on its own from statistics.
Figures out what words signal relationships.
Grows branches. Finds convergence. Returns hidden dependencies.
"""

import requests
from bs4 import BeautifulSoup
from collections import defaultdict, Counter
import re
import time
import json
from urllib.parse import quote

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


# ─────────────────────────────────────────────────────────────────────────────
# TEXT COLLECTOR — Gets full Wikipedia articles
# ─────────────────────────────────────────────────────────────────────────────

class TextCollector:

    def collect(self, concept: str, related_depth: int = 2) -> list[str]:
        """Collect sentences from Wikipedia. Gets the full article, not just intro."""
        all_sentences = []

        # Main article
        sentences = self._scrape(concept)
        all_sentences.extend(sentences)
        print(f"  [{concept}] → {len(sentences)} sentences")

        # Related articles from links (more text for better pattern learning)
        if related_depth > 0:
            related = self._get_related_titles(concept)
            for title in related[:related_depth]:
                extra = self._scrape(title)
                all_sentences.extend(extra[:80])  # cap per article
                time.sleep(0.15)

        return all_sentences

    def _scrape(self, concept: str) -> list[str]:
        """Scrape full Wikipedia article for a concept"""
        try:
            url = f"https://en.wikipedia.org/wiki/{quote(concept.replace(' ', '_'))}"
            r = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")

            # Remove footnotes, references sections
            for tag in soup.select(".reflist, .references, .navbox, .infobox"):
                tag.decompose()

            # Get ALL paragraph text
            paras = soup.select("p")
            text = " ".join(p.get_text() for p in paras)

            # Clean citation markers [1], [2] etc
            text = re.sub(r'\[\d+\]', '', text)
            text = re.sub(r'\s+', ' ', text)

            return self._split(text)
        except Exception as e:
            return []

    def _get_related_titles(self, concept: str) -> list[str]:
        """Get titles of articles linked from the main article"""
        try:
            url = f"https://en.wikipedia.org/wiki/{quote(concept.replace(' ', '_'))}"
            r = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            content = soup.select_one("#mw-content-text")
            if not content:
                return []

            titles = []
            for link in content.select("a[href^='/wiki/']")[:30]:
                href = link.get("href", "")
                title = href.replace("/wiki/", "").replace("_", " ")
                if ":" not in title and len(title) > 2 and title != concept:
                    titles.append(title)
            return titles[:8]
        except:
            return []

    def _split(self, text: str) -> list[str]:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [
            re.sub(r'\s+', ' ', s).strip()
            for s in sentences
            if 5 <= len(s.split()) <= 45
        ]


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN DISCOVERER — Finds relationship words from pure statistics
# No rules. Words that consistently bridge pairs get high scores.
# Ultra-common words automatically score low (too common = no signal).
# ─────────────────────────────────────────────────────────────────────────────

class PatternDiscoverer:

    def __init__(self):
        self.bridge_pairs = defaultdict(set)   # word → {(w1,w2) pairs it bridged}
        self.triplets     = defaultdict(int)    # (w1, bridge, w2) → count
        self.bridge_count = defaultdict(int)    # word → times used as bridge
        self.word_count   = defaultdict(int)    # word → total appearances

    def learn(self, sentences: list[str]):
        for sentence in sentences:
            words = re.findall(r'\b[a-z]{2,}\b', sentence.lower())
            if len(words) < 3:
                continue

            for w in words:
                self.word_count[w] += 1

            # Triplets within a 6-word window
            for i in range(len(words)):
                for j in range(i+1, min(i+7, len(words))):
                    for k in range(j+1, min(j+5, len(words))):
                        w1, bridge, w2 = words[i], words[j], words[k]
                        if len(w1) < 3 or len(w2) < 3:
                            continue
                        self.triplets[(w1, bridge, w2)] += 1
                        self.bridge_count[bridge] += 1
                        self.bridge_pairs[bridge].add(f"{w1}|{w2}")

    def discover_relationship_words(self, top_n: int = 60) -> list[str]:
        """
        Score every word by how specifically it bridges pairs.

        Key insight the system discovers on its own:
        - Ultra-common words (the, of, and) appear between EVERYTHING
          → high diversity but also extremely high total frequency
          → low specificity score → filtered out automatically
        - True relationship words (causes, requires, produces) appear
          between SPECIFIC pairs consistently
          → high diversity relative to their total frequency
          → high specificity score → rise to the top

        Nobody told it this. It emerges from the math.
        """
        total_words = sum(self.word_count.values())
        scores = {}

        for word, pairs in self.bridge_pairs.items():
            diversity  = len(pairs)
            total_freq = max(self.word_count.get(word, 1), 1)
            bridge_freq = self.bridge_count.get(word, 1)

            if len(word) < 3 or diversity < 2:
                continue

            # Global frequency ratio — how common is this word overall
            global_ratio = total_freq / max(total_words, 1)

            # Bridge specificity — how much of its appearances are as bridges
            bridge_ratio = bridge_freq / total_freq

            # Score: high diversity × high bridge specificity × low global frequency
            # This automatically punishes ultra-common words
            score = (diversity * bridge_ratio) / (global_ratio * 10000 + 1)

            scores[word] = score

        sorted_words = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [w for w, s in sorted_words[:top_n]]


# ─────────────────────────────────────────────────────────────────────────────
# DIRECTION LEARNER — Forward or backward dependency?
# Learns from sentence position patterns. English places causes early, results late.
# ─────────────────────────────────────────────────────────────────────────────

class DirectionLearner:

    def learn(self, relationship_words: list[str], sentences: list[str]) -> dict:
        directions = {}

        for rel_word in relationship_words:
            late_score  = 0   # rel_word appears late → after it = result = forward
            early_score = 0   # rel_word appears early → after it = cause = backward

            for sentence in sentences:
                words = re.findall(r'\b[a-z]{2,}\b', sentence.lower())
                if rel_word not in words or len(words) < 4:
                    continue

                idx = words.index(rel_word)
                position = idx / len(words)  # 0.0 = start, 1.0 = end

                # If relationship word is in the later half of sentence
                # → what follows is likely a result → forward
                if position > 0.5:
                    late_score += 1
                else:
                    early_score += 1

            directions[rel_word] = "forward" if late_score >= early_score else "backward"

        return directions


# ─────────────────────────────────────────────────────────────────────────────
# DEPENDENCY EXTRACTOR — Uses self-learned grammar to find real dependencies
# ─────────────────────────────────────────────────────────────────────────────

class DependencyExtractor:

    def __init__(self, relationship_words: list[str], directions: dict):
        self.rel_words = set(relationship_words)
        self.directions = directions

    def extract(self, sentences: list[str], concept: str) -> dict:
        depends_on = Counter()
        leads_to   = Counter()
        concept_parts = set(concept.lower().split())

        for sentence in sentences:
            words = re.findall(r'\b[a-z]{2,}\b', sentence.lower())

            for i, word in enumerate(words):
                if word not in self.rel_words:
                    continue

                before = words[max(0,i-5):i]
                after  = words[i+1:min(len(words),i+6)]

                c_before = bool(concept_parts & set(before))
                c_after  = bool(concept_parts & set(after))

                if not c_before and not c_after:
                    continue

                direction = self.directions.get(word, "forward")

                if c_before:
                    other = self._pick(after, concept_parts)
                    if other:
                        if direction == "forward":
                            leads_to[other] += 1
                        else:
                            depends_on[other] += 1

                elif c_after:
                    other = self._pick(before, concept_parts)
                    if other:
                        if direction == "forward":
                            depends_on[other] += 1
                        else:
                            leads_to[other] += 1

        return {
            "depends_on": [w for w,_ in depends_on.most_common(12) if len(w) > 3],
            "leads_to":   [w for w,_ in leads_to.most_common(12)   if len(w) > 3],
        }

    def _pick(self, words: list[str], exclude: set) -> str:
        candidates = [w for w in words if len(w) > 3 and w not in exclude]
        # Pick the longest meaningful word
        candidates.sort(key=len, reverse=True)
        return candidates[0] if candidates else ""


# ─────────────────────────────────────────────────────────────────────────────
# MASTER ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class SelfTeachingBrain:

    def think(self, concept: str) -> dict:
        print(f"\n{'='*60}")
        print(f"AKKI SELF-TEACHING BRAIN")
        print(f"Concept : '{concept}'")
        print(f"No LLM. No rules. Learns from internet itself.")
        print(f"{'='*60}\n")

        collector   = TextCollector()
        discoverer  = PatternDiscoverer()

        # Phase 1 — Collect real text
        print("[1] Collecting text from Wikipedia...")
        main_sentences = collector.collect(concept, related_depth=3)

        # Also collect text from diverse topics to help grammar learning
        print("[1] Collecting diverse text for grammar pattern learning...")
        diverse_sentences = []
        for topic in ["science", "history", "nature", "mathematics"]:
            diverse_sentences.extend(collector.collect(topic, related_depth=1)[:50])

        all_sentences = main_sentences + diverse_sentences
        print(f"[1] Total: {len(all_sentences)} sentences\n")

        if len(all_sentences) < 10:
            return {"concept": concept, "error": "Not enough text collected"}

        # Phase 2 — Learn grammar
        print(f"[2] Learning grammar from {len(all_sentences)} sentences...")
        print("[2] System reading patterns with no instructions...\n")
        discoverer.learn(all_sentences)
        rel_words = discoverer.discover_relationship_words(60)

        print(f"[2] Self-discovered relationship words (top 20):")
        print(f"    {rel_words[:20]}\n")

        # Phase 3 — Learn direction
        print("[3] Learning relationship direction from sentence position...")
        dir_learner = DirectionLearner()
        directions  = dir_learner.learn(rel_words, all_sentences)

        forward_words  = [w for w,d in directions.items() if d == "forward"][:8]
        backward_words = [w for w,d in directions.items() if d == "backward"][:8]
        print(f"[3] Forward words  (X causes Y): {forward_words}")
        print(f"[3] Backward words (Y caused by X): {backward_words}\n")

        # Phase 4 — Extract dependencies
        print("[4] Extracting dependencies using self-learned grammar...")
        extractor = DependencyExtractor(rel_words, directions)
        deps      = extractor.extract(main_sentences, concept)
        print(f"[4] Found: {len(deps['depends_on'])} dependencies, {len(deps['leads_to'])} outputs\n")

        # Phase 5 — Grow branches and detect convergence
        print("[5] Growing branches. Watching for convergence...\n")
        convergence   = defaultdict(set)
        branch_results = {}

        # Mark all direct dependencies as reached by the origin
        for c in deps["depends_on"] + deps["leads_to"]:
            convergence[c].add(concept)

        # Grow from each first-level dependency as a new independent origin
        branch_concepts = (deps["depends_on"][:4] + deps["leads_to"][:4])

        for branch in branch_concepts:
            if not branch or branch == concept:
                continue

            print(f"  Growing branch: '{branch}'")
            branch_sentences = collector.collect(branch, related_depth=1)

            if branch_sentences:
                b_disc = PatternDiscoverer()
                b_disc.learn(branch_sentences + diverse_sentences)
                b_rels = b_disc.discover_relationship_words(40)
                b_dirs = dir_learner.learn(b_rels, branch_sentences)
                b_ext  = DependencyExtractor(b_rels, b_dirs)
                b_deps = b_ext.extract(branch_sentences, branch)

                branch_results[branch] = b_deps

                # Record what this branch reached
                for c in b_deps["depends_on"] + b_deps["leads_to"]:
                    if c:
                        convergence[c].add(branch)

        # Find convergence points — reached by 2+ independent origins
        conv_points = [
            {
                "concept":      c,
                "reached_from": list(origs),
                "strength":     len(origs),
            }
            for c, origs in convergence.items()
            if len(origs) >= 2 and c != concept
        ]
        conv_points.sort(key=lambda x: x["strength"], reverse=True)

        return {
            "concept":                        concept,
            "sentences_read":                 len(all_sentences),
            "relationship_words_discovered":  rel_words[:25],
            "depends_on":                     deps["depends_on"],
            "leads_to":                       deps["leads_to"],
            "branches":                       branch_results,
            "convergence_points":             conv_points[:15],
            "no_llm":                         True,
            "no_hardcoded_rules":             True,
        }

    def print_results(self, r: dict):
        print(f"\n{'='*60}")
        print(f"RESULTS: {r['concept'].upper()}")
        print(f"{'='*60}")

        if "error" in r:
            print(f"Error: {r['error']}")
            return

        print(f"Sentences read:  {r['sentences_read']}")
        print(f"Grammar learned: {r['relationship_words_discovered']}")

        print(f"\nDEPENDS ON — '{r['concept']}' needs these:")
        for d in r["depends_on"] or ["(none found)"]:
            print(f"  ←  {d}")

        print(f"\nLEADS TO — '{r['concept']}' produces these:")
        for l in r["leads_to"] or ["(none found)"]:
            print(f"  →  {l}")

        print(f"\nBRANCH DISCOVERIES:")
        for name, res in r.get("branches", {}).items():
            print(f"  [{name}]  depends: {res['depends_on'][:4]}  leads: {res['leads_to'][:4]}")

        print(f"\nCONVERGENCE POINTS — hidden truths found by multiple independent paths:")
        for cp in r.get("convergence_points", []):
            print(f"  '{cp['concept']}'  strength: {cp['strength']}  from: {cp['reached_from']}")

        if not r.get("convergence_points"):
            print("  (none yet — need more branches)")

        print(f"\nNo LLM: {r['no_llm']}   No hardcoded rules: {r['no_hardcoded_rules']}")
        print(f"{'='*60}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    concept = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "love"

    brain  = SelfTeachingBrain()
    result = brain.think(concept)
    brain.print_results(result)

    fname = f"brain/result_{concept.replace(' ', '_')}.json"
    with open(fname, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nSaved → {fname}")
