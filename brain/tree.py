"""
AKKI Brain Tree Builder

Loads the KB the brain built from the internet.
Extracts dependencies for any concept.
Builds a branching tree — origin → branches → sub-branches.
Shows it as ASCII tree, saves as JSON and interactive HTML.
"""

import pickle
import math
import json
import os
import sys
from collections import defaultdict, Counter

# Import KB class so pickle can deserialize the saved brain
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
_spec = importlib.util.spec_from_file_location("run", os.path.join(os.path.dirname(__file__), "run.py"))
_mod  = importlib.util.module_from_spec(_spec)
# We just need the KB class — don't run main
import builtins
_real_name = __name__
sys.modules["run"] = _mod   # register so pickle finds run.KB
_spec.loader.exec_module(_mod)
KB = _mod.KB

KB_PATH = "brain/knowledge.pkl"


# ── Load KB ───────────────────────────────────────────────────────────────────

def load_kb():
    if not os.path.exists(KB_PATH):
        print("ERROR: No brain found. Run 'python brain/run.py' first.")
        sys.exit(1)
    with open(KB_PATH, "rb") as f:
        kb = pickle.load(f)
    print(f"Brain loaded: {kb.total_sent:,} sentences | {kb.total_pages} pages | {len(kb.word_freq):,} words")
    return kb


# ── Extract dependencies from KB ──────────────────────────────────────────────

def get_related(kb, concept: str, top_n: int = 8) -> list:
    """
    Find what is most strongly related to this concept.
    Uses PMI (Pointwise Mutual Information) — learned from co-occurrence.
    No rules. Pure statistics from what the brain read.
    """
    if concept not in kb.cooccurrence:
        return []

    total = sum(kb.word_freq.values())
    concept_freq = max(kb.word_freq.get(concept, 1), 1)

    scored = []
    for other, count in kb.cooccurrence[concept].items():
        if len(other) < 4:
            continue
        if kb.word_freq.get(other, 0) < 3:
            continue

        other_freq = max(kb.word_freq[other], 1)
        p_xy = count / total
        p_x  = concept_freq / total
        p_y  = other_freq / total

        if p_x > 0 and p_y > 0 and p_xy > 0:
            try:
                pmi = math.log(p_xy / (p_x * p_y))
                if pmi > 0:
                    scored.append((other, round(pmi, 3)))
            except:
                pass

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_n]


def get_direction(kb, concept: str, other: str) -> str:
    """
    Which comes first in sentences — concept or other?
    Earlier = more likely to be the cause.
    Later = more likely to be the effect.
    """
    concept_positions = kb.positions.get(concept, [])
    other_positions   = kb.positions.get(other, [])

    if not concept_positions or not other_positions:
        return "related"

    avg_concept = sum(concept_positions) / len(concept_positions)
    avg_other   = sum(other_positions)   / len(other_positions)

    if avg_concept < avg_other - 0.06:
        return "leads_to"       # concept comes first → it causes/leads to other
    elif avg_other < avg_concept - 0.06:
        return "depends_on"     # other comes first → concept depends on other
    else:
        return "related"


# ── Tree builder ──────────────────────────────────────────────────────────────

class TreeNode:
    def __init__(self, concept: str, pmi: float = 0.0, direction: str = "root", depth: int = 0):
        self.concept   = concept
        self.pmi       = pmi
        self.direction = direction   # root / leads_to / depends_on / related
        self.depth     = depth
        self.children  = []

    def to_dict(self) -> dict:
        return {
            "concept":   self.concept,
            "pmi":       self.pmi,
            "direction": self.direction,
            "depth":     self.depth,
            "children":  [c.to_dict() for c in self.children],
        }


def build_tree(kb, root_concept: str, max_depth: int = 3, max_children: int = 6) -> TreeNode:
    """
    Build a dependency tree from the root concept.
    At each node: find related concepts, determine direction, recurse.
    """
    visited = set()

    def _build(concept: str, depth: int, pmi: float, direction: str) -> TreeNode:
        node = TreeNode(concept, pmi, direction, depth)

        if depth >= max_depth or concept in visited:
            return node

        visited.add(concept)

        related = get_related(kb, concept, top_n=max_children)

        for other, other_pmi in related:
            if other in visited or other == concept:
                continue
            dir_ = get_direction(kb, concept, other)
            child = _build(other, depth + 1, other_pmi, dir_)
            node.children.append(child)

        return node

    return _build(root_concept, 0, 0.0, "root")


# ── ASCII tree printer ────────────────────────────────────────────────────────

DIRECTION_SYMBOL = {
    "root":       "◉",
    "leads_to":   "→",
    "depends_on": "←",
    "related":    "↔",
}

DIRECTION_COLOR = {
    "root":       "\033[96m",   # cyan
    "leads_to":   "\033[92m",   # green
    "depends_on": "\033[91m",   # red
    "related":    "\033[93m",   # yellow
}

RESET = "\033[0m"


def print_tree(node: TreeNode, prefix: str = "", is_last: bool = True):
    """Print tree as ASCII art with colors."""
    connector = "└── " if is_last else "├── "
    sym = DIRECTION_SYMBOL.get(node.direction, "·")
    col = DIRECTION_COLOR.get(node.direction, "")

    if node.depth == 0:
        print(f"\n{col}◉ {node.concept.upper()}{RESET}")
    else:
        strength = f"[{node.pmi:.2f}]" if node.pmi > 0 else ""
        print(f"{prefix}{connector}{col}{sym} {node.concept}{RESET} {strength}")

    child_prefix = prefix + ("    " if is_last else "│   ")
    for i, child in enumerate(node.children):
        is_child_last = (i == len(node.children) - 1)
        print_tree(child, child_prefix, is_child_last)


def print_legend():
    print(f"\n  Legend:")
    print(f"  {DIRECTION_COLOR['leads_to']}→ leads to / causes{RESET}")
    print(f"  {DIRECTION_COLOR['depends_on']}← depends on / needs{RESET}")
    print(f"  {DIRECTION_COLOR['related']}↔ related / bidirectional{RESET}")
    print(f"  [N.NN] = connection strength (PMI score)\n")


# ── HTML visualization ────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>AKKI Brain Tree: {concept}</title>
<style>
  body {{ background: #04080f; color: #fff; font-family: monospace; margin: 0; overflow: hidden; }}
  #title {{ position: fixed; top: 20px; left: 50%; transform: translateX(-50%);
            font-size: 18px; font-weight: 900; color: #00d8ff; letter-spacing: 0.2em;
            text-transform: uppercase; z-index: 100; }}
  #legend {{ position: fixed; bottom: 20px; left: 20px; font-size: 11px;
             background: rgba(8,13,26,0.9); border: 1px solid rgba(0,216,255,0.2);
             padding: 10px 14px; border-radius: 10px; z-index: 100; }}
  #legend div {{ margin: 3px 0; }}
  #info {{ position: fixed; top: 20px; right: 20px; font-size: 11px;
           background: rgba(8,13,26,0.9); border: 1px solid rgba(0,216,255,0.2);
           padding: 10px 14px; border-radius: 10px; z-index: 100; }}
  canvas {{ display: block; }}
  .tooltip {{ position: fixed; background: rgba(8,13,26,0.95);
              border: 1px solid rgba(0,216,255,0.4); border-radius: 8px;
              padding: 8px 12px; font-size: 12px; pointer-events: none;
              display: none; z-index: 200; }}
</style>
</head>
<body>
<div id="title">AKKI Brain Tree — {concept}</div>
<div id="info">
  <div style="color:#00d8ff;font-weight:bold;margin-bottom:6px">Brain Stats</div>
  <div>Sentences: {sentences:,}</div>
  <div>Pages: {pages:,}</div>
  <div>Words: {words:,}</div>
  <div style="margin-top:6px;color:rgba(255,255,255,0.4)">Drag to rotate</div>
</div>
<div id="legend">
  <div style="color:#00ff88">→ leads to / causes</div>
  <div style="color:#ff3868">← depends on / needs</div>
  <div style="color:#ffb700">↔ related</div>
  <div style="color:#00d8ff">◉ origin</div>
</div>
<div class="tooltip" id="tooltip"></div>
<canvas id="canvas"></canvas>
<script>
const DATA = {data};

const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const tooltip = document.getElementById('tooltip');

let W, H;
function resize() {{
  W = canvas.width  = window.innerWidth;
  H = canvas.height = window.innerHeight;
}}
resize();
window.addEventListener('resize', () => {{ resize(); draw(); }});

// Color scheme
const COLORS = {{
  root:       '#00d8ff',
  leads_to:   '#00ff88',
  depends_on: '#ff3868',
  related:    '#ffb700',
}};

// Layout: radial tree
const nodes = [];
const edges = [];

function flatten(node, parent, angle, angleSpan, radius) {{
  const x = W/2 + Math.cos(angle) * radius;
  const y = H/2 + Math.sin(angle) * radius;
  const id = nodes.length;
  nodes.push({{ id, concept: node.concept, x, y, direction: node.direction, pmi: node.pmi, depth: node.depth }});

  if (parent !== null) {{
    edges.push({{ from: parent, to: id, direction: node.direction }});
  }}

  const n = node.children.length;
  if (n === 0) return;

  const step = angleSpan / Math.max(n, 1);
  const start = angle - angleSpan/2 + step/2;
  const childRadius = radius + 120 + (3 - node.depth) * 30;

  node.children.forEach((child, i) => {{
    flatten(child, id, start + i * step, step * 0.8, childRadius);
  }});
}}

flatten(DATA, null, 0, Math.PI * 2, 0);

// Pan/drag
let offsetX = 0, offsetY = 0, dragging = false, startX, startY;
canvas.addEventListener('mousedown', e => {{ dragging = true; startX = e.clientX - offsetX; startY = e.clientY - offsetY; }});
canvas.addEventListener('mousemove', e => {{
  if (dragging) {{ offsetX = e.clientX - startX; offsetY = e.clientY - startY; draw(); return; }}
  // Tooltip
  const mx = e.clientX - offsetX;
  const my = e.clientY - offsetY;
  let found = null;
  for (const n of nodes) {{
    const dx = n.x - mx, dy = n.y - my;
    if (Math.sqrt(dx*dx+dy*dy) < 20) {{ found = n; break; }}
  }}
  if (found) {{
    tooltip.style.display = 'block';
    tooltip.style.left = (e.clientX + 12) + 'px';
    tooltip.style.top  = (e.clientY - 10) + 'px';
    tooltip.innerHTML = `<b style="color:${{COLORS[found.direction] || '#fff'}}">${{found.concept}}</b><br>
      Direction: ${{found.direction}}<br>
      Strength: ${{found.pmi.toFixed(3)}}<br>
      Depth: ${{found.depth}}`;
  }} else {{
    tooltip.style.display = 'none';
  }}
}});
canvas.addEventListener('mouseup', () => dragging = false);

function draw() {{
  ctx.clearRect(0, 0, W, H);

  // Draw edges
  edges.forEach(e => {{
    const from = nodes[e.from];
    const to   = nodes[e.to];
    const col  = COLORS[e.direction] || '#888';
    ctx.beginPath();
    ctx.strokeStyle = col + '55';
    ctx.lineWidth = 1.5;
    ctx.moveTo(from.x + offsetX, from.y + offsetY);
    ctx.lineTo(to.x   + offsetX, to.y   + offsetY);
    ctx.stroke();
  }});

  // Draw nodes
  nodes.forEach(n => {{
    const x = n.x + offsetX;
    const y = n.y + offsetY;
    const col = COLORS[n.direction] || '#888';
    const r = n.depth === 0 ? 18 : Math.max(6, 14 - n.depth * 3);

    // Glow
    const grad = ctx.createRadialGradient(x, y, 0, x, y, r * 2);
    grad.addColorStop(0, col + '44');
    grad.addColorStop(1, 'transparent');
    ctx.beginPath();
    ctx.fillStyle = grad;
    ctx.arc(x, y, r * 2, 0, Math.PI * 2);
    ctx.fill();

    // Node circle
    ctx.beginPath();
    ctx.fillStyle = '#04080f';
    ctx.strokeStyle = col;
    ctx.lineWidth = n.depth === 0 ? 3 : 1.5;
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    // Label
    const fontSize = n.depth === 0 ? 13 : Math.max(9, 12 - n.depth * 2);
    ctx.fillStyle = n.depth === 0 ? col : 'rgba(255,255,255,0.85)';
    ctx.font = `${{n.depth === 0 ? 'bold ' : ''}}${{fontSize}}px monospace`;
    ctx.textAlign = 'center';
    ctx.fillText(n.concept, x, y + r + fontSize + 2);
  }});
}}

draw();
</script>
</body>
</html>"""


def build_html(node: TreeNode, kb, output_path: str):
    data_json = json.dumps(node.to_dict(), indent=2)
    html = HTML_TEMPLATE.format(
        concept   = node.concept,
        sentences = kb.total_sent,
        pages     = kb.total_pages,
        words     = len(kb.word_freq),
        data      = data_json,
    )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[HTML] Saved → {output_path}")


# ── Convergence finder ────────────────────────────────────────────────────────

def find_convergence(tree: TreeNode) -> list:
    """
    Find concepts that appear in multiple branches of the tree.
    These are the convergence points — hidden truths the brain found.
    """
    seen_by = defaultdict(set)

    def _walk(node: TreeNode, path: list):
        if node.depth > 0:
            seen_by[node.concept].add(path[0] if path else "root")
        for child in node.children:
            _walk(child, path + [node.concept])

    for child in tree.children:
        _walk(child, [tree.concept])

    convergences = [
        {"concept": c, "reached_from": list(s), "strength": len(s)}
        for c, s in seen_by.items()
        if len(s) >= 2
    ]
    convergences.sort(key=lambda x: x["strength"], reverse=True)
    return convergences[:10]


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    concept = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "love"

    kb = load_kb()

    # Check concept exists in KB
    if concept not in kb.word_freq:
        # Try to find something close
        close = [w for w in kb.word_freq if concept.lower() in w.lower()]
        if close:
            concept = close[0]
            print(f"Using: '{concept}'")
        else:
            print(f"'{concept}' not found in brain yet. Try: {list(kb.word_freq.most_common(10))}")
            sys.exit(1)

    print(f"\nBuilding tree for: '{concept}'")
    print(f"Max depth: 3 | Max children per node: 6\n")

    # Build tree
    tree = build_tree(kb, concept, max_depth=3, max_children=6)

    # Print ASCII tree
    print_tree(tree)
    print_legend()

    # Find convergence
    convergences = find_convergence(tree)
    if convergences:
        print(f"\nCONVERGENCE POINTS found in tree:")
        for c in convergences:
            print(f"  '{c['concept']}' — reached from: {c['reached_from']} (strength: {c['strength']})")
    else:
        print(f"\nNo convergence yet. Brain needs more exploration.")

    # Save JSON
    json_path = f"brain/tree_{concept.replace(' ','_')}.json"
    with open(json_path, "w") as f:
        json.dump(tree.to_dict(), f, indent=2)
    print(f"\n[JSON] Saved → {json_path}")

    # Build HTML visualization
    html_path = f"brain/tree_{concept.replace(' ','_')}.html"
    build_html(tree, kb, html_path)

    print(f"\nOpen {html_path} in your browser to see the interactive tree.")
