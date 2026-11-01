"""
AKKI Brain — Core Dependency Discovery Engine
No LLM. No APIs. Real internet. Pure convergence detection.

How it works:
1. Take any concept as origin
2. Scrape the real internet for what depends on it and what it leads to
3. Grow branches from every discovery
4. Find where branches from different paths converge
5. Those convergence points are hidden truths
"""

import requests
from bs4 import BeautifulSoup
from collections import defaultdict, deque
import re
import time
import json
from urllib.parse import quote_plus, urljoin, urlparse

# ── Headers to look like a real browser ──────────────────────────────────────
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# ── Dependency signal words — these indicate real dependencies ────────────────
DEPENDENCY_SIGNALS = [
    "requires", "depends on", "needs", "leads to", "causes", "results in",
    "produces", "creates", "enables", "because of", "therefore", "thus",
    "consequently", "is made of", "consists of", "relies on", "stems from",
    "gives rise to", "is rooted in", "without which", "is essential for",
    "is necessary for", "is a result of", "is caused by", "emerges from",
    "is driven by", "is founded on", "is built on", "is based on",
]

# ── Words to ignore — too common, no real dependency signal ──────────────────
STOP_CONCEPTS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "this", "that", "these",
    "those", "it", "its", "they", "them", "their", "we", "our", "you",
    "your", "he", "she", "his", "her", "i", "me", "my", "and", "or",
    "but", "not", "so", "yet", "for", "nor", "at", "by", "from", "with",
    "about", "into", "through", "during", "before", "after", "above",
    "below", "between", "out", "off", "over", "under", "again", "further",
    "then", "once", "also", "very", "just", "more", "most", "other",
    "some", "such", "no", "only", "same", "than", "too", "both", "each",
    "few", "how", "all", "any", "both", "each", "see", "also", "often",
}


class BranchNode:
    """A single node in the dependency tree"""
    def __init__(self, concept: str, origin: str, depth: int, source_url: str = ""):
        self.concept = concept.lower().strip()
        self.origin = origin          # which original seed this came from
        self.depth = depth            # how many branches deep
        self.source_url = source_url  # where we found this
        self.depends_on = []          # things this concept needs
        self.leads_to = []            # things that depend on this concept


class BrainEngine:
    """
    The core engine.
    Takes a concept. Grows branches from the real internet.
    Finds convergence. Returns hidden dependencies.
    """

    def __init__(self, max_depth: int = 3, max_branches: int = 8):
        self.max_depth = max_depth
        self.max_branches = max_branches
        self.visited = set()
        self.all_nodes = defaultdict(list)   # concept -> [BranchNode]
        self.convergence_points = defaultdict(set)  # concept -> set of origins that reached it

    def search_internet(self, concept: str) -> list[dict]:
        """
        Go to the real internet. Search for the concept.
        Return list of pages to read.
        No API. Real scraping.
        """
        results = []

        # Search DuckDuckGo HTML (no API needed)
        try:
            url = f"https://duckduckgo.com/html/?q={quote_plus(concept + ' depends on causes leads to')}"
            response = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")

            # Extract result links and snippets
            for result in soup.select(".result")[:5]:
                link_tag = result.select_one(".result__url")
                snippet_tag = result.select_one(".result__snippet")
                title_tag = result.select_one(".result__title")

                if snippet_tag:
                    results.append({
                        "url": link_tag.get_text().strip() if link_tag else "",
                        "title": title_tag.get_text().strip() if title_tag else "",
                        "snippet": snippet_tag.get_text().strip(),
                    })

            time.sleep(0.5)  # be respectful

        except Exception as e:
            print(f"  [search] failed for '{concept}': {e}")

        return results

    def scrape_page(self, url: str) -> str:
        """
        Actually go to a webpage and read it.
        Return the text content.
        """
        if not url.startswith("http"):
            url = "https://" + url

        try:
            response = requests.get(url, headers=HEADERS, timeout=8)
            soup = BeautifulSoup(response.text, "html.parser")

            # Remove noise
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            # Get main text
            text = soup.get_text(separator=" ", strip=True)

            # Clean up whitespace
            text = re.sub(r'\s+', ' ', text)

            return text[:5000]  # first 5000 chars is enough

        except Exception as e:
            print(f"  [scrape] failed for '{url}': {e}")
            return ""

    def extract_dependencies(self, text: str, concept: str) -> dict:
        """
        Read real text from the internet.
        Extract what depends on what.
        Look for real dependency signals in sentences.
        Returns: {depends_on: [...], leads_to: [...]}
        """
        depends_on = []
        leads_to = []

        # Split into sentences
        sentences = re.split(r'[.!?]', text.lower())

        for sentence in sentences:
            if concept.lower() not in sentence:
                continue

            # Check for dependency signals
            for signal in DEPENDENCY_SIGNALS:
                if signal in sentence:
                    # Extract what comes after the signal
                    parts = sentence.split(signal)
                    if len(parts) > 1:
                        after = parts[1].strip()
                        # Extract meaningful words
                        words = self._extract_concepts(after[:200])

                        # Determine direction
                        # "X requires Y" → X depends on Y
                        # "X leads to Y" → Y depends on X
                        if signal in ["requires", "depends on", "needs", "relies on",
                                      "is based on", "is built on", "stems from",
                                      "is rooted in", "is made of", "consists of"]:
                            depends_on.extend(words)
                        elif signal in ["leads to", "causes", "results in", "produces",
                                        "creates", "enables", "gives rise to", "enables"]:
                            leads_to.extend(words)
                        else:
                            depends_on.extend(words)

        return {
            "depends_on": list(set(depends_on))[:self.max_branches],
            "leads_to": list(set(leads_to))[:self.max_branches],
        }

    def _extract_concepts(self, text: str) -> list[str]:
        """
        Pull meaningful concepts out of text.
        Remove stop words. Keep real concepts.
        """
        # Remove punctuation
        text = re.sub(r'[^\w\s]', ' ', text)
        words = text.lower().split()

        # Filter stop words and short words
        concepts = [
            w for w in words
            if w not in STOP_CONCEPTS
            and len(w) > 3
            and not w.isdigit()
        ]

        # Also extract 2-word phrases
        phrases = []
        for i in range(len(words) - 1):
            if (words[i] not in STOP_CONCEPTS and
                words[i+1] not in STOP_CONCEPTS and
                len(words[i]) > 3 and len(words[i+1]) > 3):
                phrases.append(f"{words[i]} {words[i+1]}")

        return (concepts + phrases)[:10]

    def grow_branch(self, concept: str, origin: str, depth: int = 0) -> BranchNode:
        """
        Take a concept. Go to the internet. Find what it depends on.
        Grow branches recursively up to max_depth.
        """
        node_key = f"{concept}_{origin}"
        if node_key in self.visited or depth >= self.max_depth:
            return None

        self.visited.add(node_key)

        print(f"  {'  ' * depth}[{origin}] Growing: {concept} (depth {depth})")

        node = BranchNode(concept, origin, depth)

        # Record this concept was reached by this origin
        self.convergence_points[concept].add(origin)
        self.all_nodes[concept].append(node)

        # Search the internet for this concept
        search_results = self.search_internet(concept)

        # Process search snippets first (fast)
        all_text = " ".join([r["snippet"] for r in search_results])

        # Try to scrape the first real page (slower but deeper)
        if search_results and search_results[0]["url"]:
            page_text = self.scrape_page(search_results[0]["url"])
            all_text += " " + page_text

        # Extract dependencies from what we found
        deps = self.extract_dependencies(all_text, concept)

        node.depends_on = deps["depends_on"]
        node.leads_to = deps["leads_to"]

        # Grow branches from dependencies
        all_connected = deps["depends_on"] + deps["leads_to"]

        for connected_concept in all_connected[:self.max_branches]:
            if connected_concept and len(connected_concept) > 3:
                child = self.grow_branch(connected_concept, origin, depth + 1)

        return node

    def find_convergence(self) -> list[dict]:
        """
        Find concepts that were reached by MULTIPLE different origins.
        The more origins that converged on a concept — the more real it is.
        Filter out anything reached by only one origin.
        """
        convergences = []

        for concept, origins in self.convergence_points.items():
            if len(origins) >= 2:  # reached by at least 2 different starting points
                convergences.append({
                    "concept": concept,
                    "converged_from": list(origins),
                    "strength": len(origins),  # more origins = stronger dependency
                })

        # Sort by strength — most converged first
        convergences.sort(key=lambda x: x["strength"], reverse=True)

        return convergences

    def think(self, seed_concept: str) -> dict:
        """
        Main entry point.

        Take one concept. Grow branches from it.
        Also grow branches from its first-level dependencies as separate origins.
        Find where they all converge.
        Return the hidden dependency map.
        """
        print(f"\n[AKKI Brain] Starting with: '{seed_concept}'")
        print(f"[AKKI Brain] Going to the internet...\n")

        self.visited = set()
        self.all_nodes = defaultdict(list)
        self.convergence_points = defaultdict(set)

        # Step 1: Grow the main branch
        main_node = self.grow_branch(seed_concept, origin=seed_concept, depth=0)

        if not main_node:
            return {"error": "Could not grow branches from this concept"}

        # Step 2: Use first-level dependencies as new origins
        # This creates multiple independent starting points for convergence detection
        first_level = main_node.depends_on[:4] + main_node.leads_to[:4]

        for secondary_concept in first_level:
            if secondary_concept and secondary_concept != seed_concept:
                self.grow_branch(
                    secondary_concept,
                    origin=secondary_concept,  # new origin
                    depth=0
                )

        # Step 3: Find convergence points
        convergences = self.find_convergence()

        # Step 4: Build the result
        result = {
            "origin": seed_concept,
            "depends_on": main_node.depends_on,
            "leads_to": main_node.leads_to,
            "convergence_points": convergences[:20],  # top 20 convergences
            "total_concepts_discovered": len(self.convergence_points),
            "total_branches_grown": len(self.visited),
        }

        return result

    def print_results(self, result: dict):
        """Print the results in a clear way"""
        print("\n" + "="*60)
        print(f"ORIGIN: {result['origin'].upper()}")
        print("="*60)

        print(f"\nDEPENDS ON ({len(result['depends_on'])} found):")
        for dep in result["depends_on"]:
            print(f"  ← {dep}")

        print(f"\nLEADS TO ({len(result['leads_to'])} found):")
        for lead in result["leads_to"]:
            print(f"  → {lead}")

        print(f"\nCONVERGENCE POINTS (where branches from different origins meet):")
        print(f"These are the hidden dependencies — real because multiple paths found them:\n")
        for i, conv in enumerate(result["convergence_points"][:10], 1):
            origins = ", ".join(conv["converged_from"])
            print(f"  {i}. '{conv['concept']}' (strength: {conv['strength']})")
            print(f"     Found independently from: {origins}")

        print(f"\nTOTAL:")
        print(f"  Concepts discovered: {result['total_concepts_discovered']}")
        print(f"  Branches grown:      {result['total_branches_grown']}")
        print("="*60)


# ── Run it ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Get concept from command line or use default
    if len(sys.argv) > 1:
        concept = " ".join(sys.argv[1:])
    else:
        concept = "love"

    brain = BrainEngine(max_depth=2, max_branches=6)
    result = brain.think(concept)
    brain.print_results(result)

    # Save raw result to file
    output_file = f"brain/results_{concept.replace(' ', '_')}.json"
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n[Saved to {output_file}]")
