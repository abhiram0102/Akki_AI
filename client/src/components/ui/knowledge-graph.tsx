import { useState } from "react";
import { motion } from "framer-motion";

interface KGNode {
  id: string;
  label: string;
  type: "semantic" | "episodic" | "procedural" | "emotional" | "document";
  strength: number;
}

interface KnowledgeGraphProps {
  memories: Array<{
    id: string;
    type: string;
    content: { summary?: string };
    strength?: number;
  }>;
  documents: Array<{ id: string; title: string }>;
}

const TYPE_CONFIG = {
  semantic:   { color: "#00ff88", rgb: "0,255,136",   icon: "🧠", label: "Knowledge" },
  episodic:   { color: "#ffb700", rgb: "255,183,0",   icon: "⏱",  label: "Session"   },
  procedural: { color: "#00d8ff", rgb: "0,216,255",   icon: "⚙",  label: "Learning"  },
  emotional:  { color: "#ec4899", rgb: "236,72,153",  icon: "❤",  label: "Bond"      },
  document:   { color: "#9b59fc", rgb: "155,89,252",  icon: "📄", label: "Doc"       },
} as const;

const CLUSTER_RANGES: Record<string, [number, number]> = {
  semantic:   [100, 160],
  episodic:   [20,  80],
  document:   [160, 220],
  procedural: [280, 340],
  emotional:  [220, 280],
};

function computePositions(nodes: KGNode[]) {
  const byType: Record<string, KGNode[]> = {};
  nodes.forEach(n => {
    if (!byType[n.type]) byType[n.type] = [];
    byType[n.type].push(n);
  });

  const positions: Record<string, { x: number; y: number; r: number }> = {};

  Object.entries(byType).forEach(([type, typeNodes]) => {
    const [minA, maxA] = CLUSTER_RANGES[type] ?? [0, 60];
    typeNodes.forEach((node, i) => {
      const count = typeNodes.length;
      const angle =
        minA +
        (count === 1
          ? (maxA - minA) / 2
          : (i / (count - 1)) * (maxA - minA));
      const rad = ((angle - 90) * Math.PI) / 180;
      const dist = 110 + (i % 2 === 0 ? 20 : -10);
      positions[node.id] = {
        x: 280 + dist * Math.cos(rad),
        y: 180 + dist * Math.sin(rad),
        r: 8 + node.strength * 9,
      };
    });
  });

  return positions;
}

export default function KnowledgeGraph({ memories, documents }: KnowledgeGraphProps) {
  const [hovered, setHovered] = useState<string | null>(null);

  const nodes: KGNode[] = [
    ...memories.map(m => ({
      id: m.id,
      label: (m.content?.summary ?? "").slice(0, 40) || m.type,
      type: m.type as KGNode["type"],
      strength: m.strength ?? 0.5,
    })),
    ...documents.map(d => ({
      id: d.id,
      label: d.title.slice(0, 40),
      type: "document" as const,
      strength: 0.7,
    })),
  ];

  const positions = computePositions(nodes);
  const hoveredNode = nodes.find(n => n.id === hovered);

  if (nodes.length === 0) {
    return (
      <div
        style={{
          textAlign: "center",
          padding: "30px 16px",
          fontFamily: "monospace",
          fontSize: 10,
          color: "rgba(255,255,255,0.25)",
        }}
      >
        <div style={{ fontSize: 32, marginBottom: 8 }}>🌐</div>
        Graph will populate as memories and documents are added
      </div>
    );
  }

  return (
    <div style={{ position: "relative" }}>
      <svg viewBox="0 0 560 360" style={{ width: "100%", height: "auto" }}>
        <defs>
          <radialGradient id="hubgrd" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="rgba(0,216,255,0.35)" />
            <stop offset="100%" stopColor="rgba(0,216,255,0.05)" />
          </radialGradient>
          {Object.entries(TYPE_CONFIG).map(([type, cfg]) => (
            <filter
              key={type}
              id={`kglow-${type}`}
              x="-50%"
              y="-50%"
              width="200%"
              height="200%"
            >
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feFlood
                floodColor={cfg.color}
                floodOpacity="0.6"
                result="color"
              />
              <feComposite
                in="color"
                in2="blur"
                operator="in"
                result="glow"
              />
              <feMerge>
                <feMergeNode in="glow" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          ))}
        </defs>

        {/* Edges from hub to each node */}
        {nodes.map(node => {
          const p = positions[node.id];
          if (!p) return null;
          const cfg = TYPE_CONFIG[node.type] ?? TYPE_CONFIG.semantic;
          const isHov = hovered === node.id;
          const mx = (280 + p.x) / 2 + (p.y - 180) * 0.2;
          const my = (180 + p.y) / 2 - (p.x - 280) * 0.2;
          return (
            <motion.path
              key={node.id}
              d={`M280,180 Q${mx},${my} ${p.x},${p.y}`}
              fill="none"
              stroke={isHov ? cfg.color : `rgba(${cfg.rgb},0.18)`}
              strokeWidth={isHov ? 1.5 : 0.8}
              initial={{ pathLength: 0, opacity: 0 }}
              animate={{ pathLength: 1, opacity: 1 }}
              transition={{ duration: 0.8, delay: 0.1 }}
              style={{ transition: "stroke 0.3s, stroke-width 0.3s" }}
            />
          );
        })}

        {/* Hub node */}
        <motion.circle
          cx={280}
          cy={180}
          r={20}
          fill="url(#hubgrd)"
          stroke="rgba(0,216,255,0.6)"
          strokeWidth={2}
          animate={{ r: [20, 23, 20] } as Record<string, number[]>}
          transition={{ duration: 3, repeat: Infinity }}
        />
        <text
          x={280}
          y={183}
          textAnchor="middle"
          fill="#00d8ff"
          fontSize={9}
          fontFamily="monospace"
          fontWeight={900}
        >
          AKKI
        </text>
        <text
          x={280}
          y={198}
          textAnchor="middle"
          fill="rgba(0,216,255,0.5)"
          fontSize={7}
          fontFamily="monospace"
        >
          MIND
        </text>

        {/* Data nodes */}
        {nodes.map(node => {
          const p = positions[node.id];
          if (!p) return null;
          const cfg = TYPE_CONFIG[node.type] ?? TYPE_CONFIG.semantic;
          const isHov = hovered === node.id;
          return (
            <g
              key={node.id}
              style={{ cursor: "pointer" }}
              onMouseEnter={() => setHovered(node.id)}
              onMouseLeave={() => setHovered(null)}
            >
              {isHov && (
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={p.r + 6}
                  fill="none"
                  stroke={cfg.color}
                  strokeWidth={1}
                  opacity={0.5}
                />
              )}
              <motion.circle
                cx={p.x}
                cy={p.y}
                r={p.r}
                fill={`rgba(${cfg.rgb},${isHov ? 0.35 : 0.18})`}
                stroke={cfg.color}
                strokeWidth={isHov ? 2 : 1}
                filter={isHov ? `url(#kglow-${node.type})` : undefined}
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ type: "spring", delay: 0.05 }}
                style={{ transition: "fill 0.2s, stroke-width 0.2s" }}
              />
              {isHov && (
                <g>
                  <rect
                    x={p.x - 60}
                    y={p.y - p.r - 28}
                    width={120}
                    height={22}
                    rx={5}
                    fill="rgba(8,13,26,0.97)"
                    stroke={`rgba(${cfg.rgb},0.5)`}
                    strokeWidth={1}
                  />
                  <text
                    x={p.x}
                    y={p.y - p.r - 12}
                    textAnchor="middle"
                    fill={cfg.color}
                    fontSize={8}
                    fontFamily="monospace"
                  >
                    {node.label.slice(0, 22)}
                    {node.label.length > 22 ? "…" : ""}
                  </text>
                </g>
              )}
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 8,
          padding: "8px 12px",
          borderTop: "1px solid rgba(255,255,255,0.05)",
        }}
      >
        {(Object.entries(TYPE_CONFIG) as [keyof typeof TYPE_CONFIG, (typeof TYPE_CONFIG)[keyof typeof TYPE_CONFIG]][]).map(([type, cfg]) => {
          const count = nodes.filter(n => n.type === type).length;
          if (count === 0) return null;
          return (
            <div
              key={type}
              style={{ display: "flex", alignItems: "center", gap: 4 }}
            >
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: cfg.color,
                  boxShadow: `0 0 4px ${cfg.color}`,
                }}
              />
              <span
                style={{
                  fontFamily: "monospace",
                  fontSize: 8,
                  color: "rgba(255,255,255,0.40)",
                }}
              >
                {cfg.label} ({count})
              </span>
            </div>
          );
        })}
      </div>

      {/* Hovered node detail */}
      {hoveredNode && (
        <div
          style={{
            padding: "8px 12px",
            background: "rgba(8,13,26,0.95)",
            borderTop: "1px solid rgba(255,255,255,0.05)",
          }}
        >
          <div
            style={{
              fontFamily: "monospace",
              fontSize: 9,
              color:
                TYPE_CONFIG[hoveredNode.type]?.color ?? "#fff",
              fontWeight: 700,
              marginBottom: 3,
            }}
          >
            {TYPE_CONFIG[hoveredNode.type]?.label ?? hoveredNode.type}
          </div>
          <div
            style={{
              fontFamily: "monospace",
              fontSize: 10,
              color: "rgba(255,255,255,0.60)",
              lineHeight: 1.5,
            }}
          >
            {hoveredNode.label}
          </div>
        </div>
      )}
    </div>
  );
}
