"""
AKKI Brain — Continuous Runner

Runs forever until you press Ctrl+C.
Explores the internet space continuously.
Shows exactly what it is learning and how fast.
Saves progress every 5 minutes.
Shows brain development stats every 50 pages.
"""

import time
import os
import sys
import signal
import math
import pickle
import random
import requests
from bs4 import BeautifulSoup
from collections import defaultdict, Counter
from urllib.parse import quote
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────
KB_PATH   = "brain/knowledge.pkl"
LOG_PATH  = "brain/brain_log.txt"
os.makedirs("brain", exist_ok=True)

# ── HTTP headers ──────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

# ── Starting seeds — where the brain begins exploring ─────────────────────────
SEEDS = [
    "love", "fire", "water", "time", "light", "energy", "life", "death",
    "mind", "consciousness", "evolution", "gravity", "language", "music",
    "mathematics", "biology", "physics", "chemistry", "history", "culture",
    "economy", "society", "power", "knowledge", "truth", "beauty", "justice",
    "war", "peace", "technology", "intelligence", "memory", "emotion",
    "perception", "reality", "space", "universe", "atom", "cell", "brain",
    "heart", "blood", "earth", "ocean", "forest", "city", "family", "trade",
]

# ── Global state ──────────────────────────────────────────────────────────────
running        = True
start_time     = time.time()
pages_visited  = 0
sentences_learned = 0
last_save_time = time.time()
last_stat_page = 0


def signal_handler(sig, frame):
    global running
    print(f"\n\n[STOPPING] Signal {sig} received. Saving...\n")
    running = False

signal.signal(signal.SIGINT,  signal_handler)
signal.signal(signal.SIGTERM, signal_handler)   # also catch hub stop


# ── Knowledge Base ────────────────────────────────────────────────────────────

class KB:
    def __init__(self):
        self.cooccurrence  = defaultdict(Counter)
        self.positions     = defaultdict(list)
        self.transitions   = defaultdict(Counter)
        self.word_freq     = Counter()
        self.visited       = set()
        self.frontier      = []          # discovered links not yet visited — saved to disk
        self.total_sent    = 0
        self.total_pages   = 0
        self.concepts_seen = Counter()

    def save(self):
        with open(KB_PATH, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load():
        if os.path.exists(KB_PATH):
            with open(KB_PATH, "rb") as f:
                kb = pickle.load(f)
            # Ensure frontier attribute exists (backward compat)
            if not hasattr(kb, 'frontier'):
                kb.frontier = []
            return kb
        return KB()


# ── Logger ────────────────────────────────────────────────────────────────────

def log(msg: str, also_print: bool = True):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    if also_print:
        print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ── Internet mover ────────────────────────────────────────────────────────────

def fetch_page(url: str):
    """Fetch one Wikipedia page. Return (text, links)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code != 200:
            return "", []

        soup = BeautifulSoup(r.text, "html.parser")

        import re

        # Get text from paragraphs
        paras = soup.select("p")
        text  = " ".join(p.get_text() for p in paras)
        text  = re.sub(r'\[\d+\]', '', text)
        text  = re.sub(r'\s+', ' ', text)

        # Get links from article body only
        # Wikipedia renders full URLs in the body links
        body  = soup.select_one("#mw-content-text") or soup
        links = []
        seen  = set()

        for a in body.select("a[href]"):
            href = a.get("href", "")

            # Handle both full URLs and paths
            if href.startswith("https://en.wikipedia.org/wiki/"):
                full = href
            elif href.startswith("/wiki/"):
                full = "https://en.wikipedia.org" + href
            else:
                continue

            # Filter noise pages
            path = full.replace("https://en.wikipedia.org/wiki/", "")
            if (":" in path or "#" in path or
                path.startswith("File:") or
                path.startswith("Special:") or
                path.startswith("Help:") or
                path.startswith("Wikipedia:")):
                continue

            if full not in seen:
                seen.add(full)
                links.append(full)

        return text, links[:50]

    except Exception:
        return "", []


def extract_sentences(text: str) -> list:
    import re
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [
        s.strip() for s in parts
        if 5 <= len(s.split()) <= 40
    ]


def learn_sentence(kb: KB, sentence: str):
    """Learn from one sentence. Record everything."""
    import re
    words = re.findall(r'\b[a-z]{3,}\b', sentence.lower())
    if len(words) < 3:
        return 0

    n = len(words)
    kb.total_sent += 1

    for i, word in enumerate(words):
        kb.word_freq[word] += 1
        pos = i / n
        kb.positions[word].append(pos)

        # Co-occurrence window ±5
        for j in range(max(0,i-5), min(n,i+6)):
            if j != i:
                kb.cooccurrence[word][words[j]] += 1

        # Direct transition
        if i+1 < n:
            kb.transitions[word][words[i+1]] += 1

    return 1


# ── Stats printer ─────────────────────────────────────────────────────────────

def print_stats(kb: KB):
    elapsed      = time.time() - start_time
    elapsed_min  = elapsed / 60
    pages_pm     = pages_visited / max(elapsed_min, 0.01)
    sent_ps      = kb.total_sent / max(elapsed, 0.01)
    unique_words = len(kb.word_freq)

    # Top words by frequency
    top_words = [w for w,_ in kb.word_freq.most_common(20)
                 if len(w) > 4][:15]

    # Words at verb position (0.3-0.6) with diversity
    verb_candidates = []
    for word, positions in kb.positions.items():
        if len(positions) < 10:
            continue
        avg = sum(positions) / len(positions)
        if 0.28 <= avg <= 0.62 and len(word) > 3:
            diversity = len(kb.cooccurrence.get(word,{}))
            if diversity > 5:
                verb_candidates.append((word, avg, diversity))
    verb_candidates.sort(key=lambda x: x[2], reverse=True)
    top_verbs = [w for w,a,d in verb_candidates[:15]]

    # Top concepts seen
    top_concepts = [c for c,_ in kb.concepts_seen.most_common(10)]

    # Strongest co-occurrences found
    strong_pairs = []
    total = sum(kb.word_freq.values())
    checked = 0
    for w1, others in kb.cooccurrence.items():
        if checked > 500:
            break
        if kb.word_freq[w1] < 5:
            continue
        for w2, count in others.most_common(3):
            if kb.word_freq[w2] < 5 and len(w1) > 4 and len(w2) > 4:
                p_xy = count / total
                p_x  = kb.word_freq[w1] / total
                p_y  = kb.word_freq.get(w2, 1) / total
                if p_x > 0 and p_y > 0 and p_xy > 0:
                    try:
                        pmi = math.log(p_xy / (p_x * p_y))
                        if pmi > 3:
                            strong_pairs.append((w1, w2, round(pmi,2)))
                    except:
                        pass
        checked += 1
    strong_pairs.sort(key=lambda x: x[2], reverse=True)

    bar = "=" * 65

    log(bar, True)
    log(f"  BRAIN DEVELOPMENT REPORT", True)
    log(bar, True)
    log(f"  Runtime         : {elapsed_min:.1f} minutes", True)
    log(f"  Pages explored  : {kb.total_pages:,}", True)
    log(f"  Speed           : {pages_pm:.1f} pages/min  |  {sent_ps:.1f} sentences/sec", True)
    log(f"  Sentences read  : {kb.total_sent:,}", True)
    log(f"  Unique words    : {unique_words:,}", True)
    log(f"  Concepts seen   : {len(kb.concepts_seen):,}", True)
    log(f"  Co-occur pairs  : {sum(len(v) for v in kb.cooccurrence.values()):,}", True)
    log(bar, True)
    log(f"  VOCABULARY GROWING:", True)
    log(f"  {top_words}", True)
    log(f"", True)
    log(f"  SELF-DISCOVERED RELATIONSHIP WORDS (verb position):", True)
    log(f"  {top_verbs}", True)
    log(f"", True)
    log(f"  STRONGEST CONNECTIONS FOUND:", True)
    for w1, w2, pmi in strong_pairs[:10]:
        log(f"    '{w1}' ←→ '{w2}'  (strength: {pmi})", True)
    log(f"", True)
    log(f"  CONCEPTS EXPLORED MOST:", True)
    log(f"  {top_concepts}", True)
    log(bar, True)
    log(f"", True)


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    global running, pages_visited, sentences_learned, last_save_time, last_stat_page
    from collections import deque

    log("=" * 65)
    log("  AKKI BRAIN — STARTING CONTINUOUS EXPLORATION")
    log("  Runs forever. Stop with Ctrl+C or hub stop.")
    log("  Saves every 60 seconds. Stats every 50 pages.")
    log("=" * 65)

    kb = KB.load()
    log(f"  Brain loaded: {kb.total_sent:,} sentences, {kb.total_pages} pages explored")
    log("")

    discovered_links: list[tuple] = list(kb.frontier)
    kb.frontier = []

    queue: deque = deque()

    if discovered_links:
        random.shuffle(discovered_links)
        for item in discovered_links[:200]:
            queue.append(item)
        discovered_links = discovered_links[200:]
        log(f"  Resuming from frontier: {len(queue)} links queued, {len(discovered_links):,} in reserve")
    else:
        seed_list = SEEDS.copy()
        random.shuffle(seed_list)
        for seed in seed_list:
            url = f"https://en.wikipedia.org/wiki/{quote(seed.replace(' ','_'))}"
            queue.append((url, seed))
        log(f"  Fresh start. {len(queue)} seeds queued.")

    log(f"  Starting...\n")

    try:
        while running:

            if not queue:
                if discovered_links:
                    random.shuffle(discovered_links)
                    batch = discovered_links[:20]
                    discovered_links = discovered_links[20:]
                    for item in batch:
                        queue.append(item)
                    log(f"\n  [REFILL] {len(batch)} links → queue. Frontier: {len(discovered_links):,}\n")
                else:
                    log(f"\n  [RESEED] Frontier empty. Clearing visited. Reseeding...\n")
                    kb.visited.clear()
                    seed_list = SEEDS.copy()
                    random.shuffle(seed_list)
                    for seed in seed_list[:10]:
                        url = f"https://en.wikipedia.org/wiki/{quote(seed.replace(' ','_'))}"
                        queue.append((url, seed))

            url, concept = queue.popleft()

            if url in kb.visited:
                continue

            kb.visited.add(url)
            kb.total_pages += 1
            kb.concepts_seen[concept] += 1
            pages_visited += 1

            text, links = fetch_page(url)

            if text:
                sentences = extract_sentences(text)
                learned = 0
                for s in sentences:
                    learned += learn_sentence(kb, s)
                sentences_learned += learned

                elapsed   = time.time() - start_time
                speed_pg  = pages_visited / max(elapsed / 60, 0.01)
                speed_snt = sentences_learned / max(elapsed, 0.01)

                log(
                    f"  PAGE {kb.total_pages:>5} | "
                    f"'{concept[:22]:<22}' | "
                    f"{learned:>4} sent | "
                    f"total: {kb.total_sent:>8,} | "
                    f"{speed_pg:.1f} pg/min | "
                    f"{speed_snt:.0f} s/sec | "
                    f"frontier: {len(discovered_links):,}"
                )

                # All links go to frontier
                for link in links:
                    if link not in kb.visited:
                        link_concept = (
                            link.replace("https://en.wikipedia.org/wiki/","")
                                .replace("_"," ")
                        )
                        discovered_links.append((link, link_concept))

            # Save every 60 seconds (not 5 minutes)
            if time.time() - last_save_time > 60:
                kb.frontier = discovered_links + list(queue)
                kb.save()
                log(
                    f"\n  [SAVE] {kb.total_sent:,} sent | "
                    f"{kb.total_pages} pages | "
                    f"{len(kb.word_freq):,} words | "
                    f"frontier: {len(kb.frontier):,}\n"
                )
                last_save_time = time.time()

            # Stats every 50 pages
            if kb.total_pages - last_stat_page >= 50:
                last_stat_page = kb.total_pages
                print_stats(kb)

            time.sleep(0.15)

    finally:
        # Always save — even on crash or SIGTERM
        kb.frontier = discovered_links + list(queue)
        kb.save()
        elapsed = (time.time() - start_time) / 60
        log(f"\n[SAVED & STOPPED]")
        log(f"  Runtime   : {elapsed:.1f} minutes")
        log(f"  Pages     : {kb.total_pages:,}")
        log(f"  Sentences : {kb.total_sent:,}")
        log(f"  Words     : {len(kb.word_freq):,}")
        log(f"  Frontier  : {len(kb.frontier):,} links saved for next run")
        if kb.total_pages >= 50:
            print_stats(kb)

if __name__ == "__main__":
    main()
