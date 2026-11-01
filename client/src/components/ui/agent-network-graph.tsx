import { useState } from "react";
import { motion } from "framer-motion";
import { useChat } from "@/store/chat";
import { useLocation } from "wouter";

/* ── agent data ──────────────────────────────────────────────── */
const AGENTS = [
  { id: "planner",    name: "NEXUS",    role: "Orchestrator", icon: "fas fa-atom",           color: "#00d8ff", rgb: "0,216,255",   angle: null },
  { id: "defender",  name: "SENTINEL", role: "Security",     icon: "fas fa-shield-halved",  color: "#60a5fa", rgb: "96,165,250",  angle: 0    },
  { id: "analyst",   name: "DISSECT",  role: "Analyst",      icon: "fas fa-microscope",     color: "#9b59fc", rgb: "155,89,252",  angle: 60   },
  { id: "researcher",name: "GHOST",    role: "OSINT",        icon: "fas fa-ghost",          color: "#ec4899", rgb: "236,72,153",  angle: 120  },
  { id: "creator",   name: "PHANTOM",  role: "Red Team",     icon: "fas fa-skull",          color: "#ff3868", rgb: "255,56,104",  angle: 180  },
  { id: "tutor",     name: "MENTOR",   role: "Tutor",        icon: "fas fa-graduation-cap", color: "#00ff88", rgb: "0,255,136",   angle: 240  },
  { id: "memory",    name: "ARCHIVE",  role: "Memory",       icon: "fas fa-database",       color: "#ffb700", rgb: "255,183,0",   angle: 300  },
  { id: "sigma",    name: "SIGMA",    role: "Math",         icon: "fas fa-infinity",       color: "#9b59fc", rgb: "155,89,252", angle: 330  },
] as const;

const NEXUS = AGENTS[0];
const SPOKES = AGENTS.slice(1) as Array<typeof AGENTS[1]>;

/* SVG viewport — wider to give node labels breathing room */
const CX = 220, CY = 195, R = 142;

function pos(angleDeg: number) {
  const rad = (angleDeg - 90) * Math.PI / 180;
  return { x: CX + R * Math.cos(rad), y: CY + R * Math.sin(rad) };
}

/* ── component ───────────────────────────────────────────────── */
export default function AgentNetworkGraph({ className }: { className?: string }) {
  const { activeAgent } = useChat();
  const [hovered, setHovered] = useState<string | null>(null);
  const [, navigate] = useLocation();

  const activeId = activeAgent?.agent ?? null;

  return (
    <div style={{ position: "relative", width: "100%" }} className={className}>
      <svg viewBox="0 0 440 400" style={{ width: "100%", height: "auto", maxHeight: 340, display: "block" }}>
        <defs>
          {/* Hex-grid background pattern */}
          <pattern id="ang-hexgrid" width="40" height="34.64" patternUnits="userSpaceOnUse">
            <polygon
              points="20,2 38,11 38,29 20,38 2,29 2,11"
              fill="none"
              stroke="rgba(0,216,255,0.06)"
              strokeWidth="0.8"
            />
          </pattern>

          {/* Per-agent glow filters */}
          {SPOKES.map(a => (
            <filter key={a.id} id={`ang-glow-${a.id}`} x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feFlood floodColor={a.color} floodOpacity="0.8" result="color" />
              <feComposite in="color" in2="blur" operator="in" result="glow" />
              <feMerge>
                <feMergeNode in="glow" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          ))}

          {/* NEXUS glow filter */}
          <filter id="ang-glow-nexus" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feFlood floodColor="#00d8ff" floodOpacity="0.9" result="color" />
            <feComposite in="color" in2="blur" operator="in" result="glow" />
            <feMerge>
              <feMergeNode in="glow" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Hex grid background */}
        <rect width="440" height="400" fill="url(#ang-hexgrid)" opacity="0.5" />

        {/* Subtle radial gradient overlay at center */}
        <radialGradient id="ang-radial" cx="50%" cy="50%" r="40%">
          <stop offset="0%" stopColor="rgba(0,216,255,0.06)" />
          <stop offset="100%" stopColor="rgba(0,0,0,0)" />
        </radialGradient>
        <rect width="440" height="400" fill="url(#ang-radial)" />

        {/* ── Edges + particles ─────────────────────────────── */}
        {SPOKES.map(a => {
          const p = pos(a.angle);
          const isActive = activeId === a.id;
          return (
            <g key={a.id}>
              <line
                x1={CX} y1={CY} x2={p.x} y2={p.y}
                stroke={isActive ? a.color : "rgba(255,255,255,0.07)"}
                strokeWidth={isActive ? 1.5 : 1}
                filter={isActive ? `url(#ang-glow-${a.id})` : undefined}
                style={{ transition: "stroke 0.4s, stroke-width 0.4s" }}
              />
              {/* Travelling data particles when active */}
              {isActive && ([0, 1, 2] as const).map(i => (
                <motion.circle
                  key={i}
                  r={3}
                  fill={a.color}
                  animate={{
                    cx: [CX, p.x],
                    cy: [CY, p.y],
                    opacity: [0, 1, 1, 0],
                  }}
                  transition={{
                    duration: 1.2,
                    delay: i * 0.35,
                    repeat: Infinity,
                    ease: "easeInOut",
                  }}
                  style={{ filter: `drop-shadow(0 0 4px ${a.color})` }}
                />
              ))}
            </g>
          );
        })}

        {/* ── Spoke nodes ───────────────────────────────────── */}
        {SPOKES.map(a => {
          const p = pos(a.angle);
          const isActive = activeId === a.id;
          const isHovered = hovered === a.id;
          return (
            <g
              key={a.id}
              style={{ cursor: "pointer" }}
              onClick={() => navigate("/agents")}
              onMouseEnter={() => setHovered(a.id)}
              onMouseLeave={() => setHovered(null)}
            >
              {/* Active pulse ring */}
              {isActive && (
                <motion.circle
                  cx={p.x}
                  cy={p.y}
                  fill="none"
                  stroke={a.color}
                  strokeWidth={2}
                  animate={{ r: [28, 42, 28], opacity: [0.8, 0, 0.8] }}
                  transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
                />
              )}
              {/* Hover ring */}
              {isHovered && !isActive && (
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={32}
                  fill="none"
                  stroke={a.color}
                  strokeWidth={1}
                  opacity={0.4}
                />
              )}
              {/* Main circle */}
              <circle
                cx={p.x}
                cy={p.y}
                r={28}
                fill={`rgba(${a.rgb},${isActive ? 0.30 : isHovered ? 0.20 : 0.12})`}
                stroke={a.color}
                strokeWidth={isActive ? 2 : 1}
                opacity={isActive ? 1 : 0.75}
                filter={isActive ? `url(#ang-glow-${a.id})` : undefined}
                style={{ transition: "all 0.3s" }}
              />
              {/* Icon */}
              <foreignObject
                x={p.x - 14}
                y={p.y - 14}
                width={28}
                height={28}
                style={{ pointerEvents: "none" }}
              >
                {/* @ts-ignore — xmlns required for SVG foreignObject in some renderers */}
                <div xmlns="http://www.w3.org/1999/xhtml" style={{ width: 28, height: 28, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <i
                    className={a.icon}
                    style={{
                      color: isActive ? a.color : "rgba(255,255,255,0.65)",
                      fontSize: 13,
                      textShadow: isActive ? `0 0 8px ${a.color}` : "none",
                    }}
                  />
                </div>
              </foreignObject>
              {/* Name label */}
              <text
                x={p.x}
                y={p.y + 44}
                textAnchor="middle"
                fill={isActive ? a.color : "rgba(255,255,255,0.50)"}
                fontSize={9}
                fontFamily="monospace"
                fontWeight={isActive ? 700 : 400}
                style={{ transition: "fill 0.3s" }}
              >
                {a.name}
              </text>
              <text
                x={p.x}
                y={p.y + 55}
                textAnchor="middle"
                fill="rgba(255,255,255,0.22)"
                fontSize={7}
                fontFamily="monospace"
              >
                {a.role.toUpperCase()}
              </text>
              {/* Tooltip on hover */}
              {isHovered && (
                <g>
                  <rect
                    x={p.x - 36}
                    y={p.y - 52}
                    width={72}
                    height={20}
                    rx={5}
                    fill="rgba(8,13,26,0.95)"
                    stroke={`rgba(${a.rgb},0.45)`}
                    strokeWidth={1}
                  />
                  <text
                    x={p.x}
                    y={p.y - 38}
                    textAnchor="middle"
                    fill={a.color}
                    fontSize={8}
                    fontFamily="monospace"
                    fontWeight={700}
                  >
                    {a.role}
                  </text>
                </g>
              )}
            </g>
          );
        })}

        {/* ── NEXUS center node ─────────────────────────────── */}
        <g style={{ cursor: "pointer" }} onClick={() => navigate("/agents")}>
          {/* Outer rotating dashed ring */}
          <motion.g
            animate={{ rotate: 360 }}
            transition={{ duration: 12, repeat: Infinity, ease: "linear" }}
            style={{ transformOrigin: `${CX}px ${CY}px` }}
          >
            <circle
              cx={CX}
              cy={CY}
              r={46}
              fill="none"
              stroke="rgba(0,216,255,0.35)"
              strokeWidth={1.5}
              strokeDasharray="8 4"
            />
          </motion.g>
          {/* Slow counter-rotating ring */}
          <motion.g
            animate={{ rotate: -360 }}
            transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
            style={{ transformOrigin: `${CX}px ${CY}px` }}
          >
            <circle
              cx={CX}
              cy={CY}
              r={52}
              fill="none"
              stroke="rgba(0,255,136,0.18)"
              strokeWidth={1}
              strokeDasharray="4 12"
            />
          </motion.g>
          {/* Pulsing glow ring */}
          <motion.circle
            cx={CX}
            cy={CY}
            fill="none"
            stroke="#00d8ff"
            strokeWidth={1}
            animate={{ opacity: [0.4, 0.8, 0.4], r: [40, 44, 40] }}
            transition={{ duration: 2.5, repeat: Infinity, ease: "easeInOut" }}
          />
          {/* Main circle */}
          <circle
            cx={CX}
            cy={CY}
            r={36}
            fill="rgba(0,216,255,0.18)"
            stroke="#00d8ff"
            strokeWidth={2}
            filter="url(#ang-glow-nexus)"
          />
          {/* Icon */}
          <foreignObject
            x={CX - 16}
            y={CY - 16}
            width={32}
            height={32}
            style={{ pointerEvents: "none" }}
          >
            {/* @ts-ignore */}
            <div xmlns="http://www.w3.org/1999/xhtml" style={{ width: 32, height: 32, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <i className="fas fa-atom" style={{ color: "#00d8ff", fontSize: 18, textShadow: "0 0 12px #00d8ff" }} />
            </div>
          </foreignObject>
          {/* Labels */}
          <text
            x={CX}
            y={CY + 54}
            textAnchor="middle"
            fill="#00d8ff"
            fontSize={11}
            fontFamily="monospace"
            fontWeight={900}
            letterSpacing={2}
          >
            NEXUS
          </text>
          <text
            x={CX}
            y={CY + 66}
            textAnchor="middle"
            fill="rgba(0,216,255,0.45)"
            fontSize={7}
            fontFamily="monospace"
          >
            ORCHESTRATOR
          </text>
        </g>

        {/* ── Active agent info badge (bottom-right) ────────── */}
        {activeId && (() => {
          const agent = SPOKES.find(a => a.id === activeId);
          if (!agent) return null;
          return (
            <g>
              <rect
                x={320}
                y={352}
                width={110}
                height={34}
                rx={8}
                fill="rgba(8,13,26,0.95)"
                stroke={`rgba(${agent.rgb},0.45)`}
                strokeWidth={1}
              />
              <motion.circle
                cx={332}
                cy={369}
                r={4}
                fill={agent.color}
                animate={{ opacity: [1, 0.3, 1] }}
                transition={{ duration: 1, repeat: Infinity, ease: "easeInOut" }}
              />
              <text x={342} y={366} fill={agent.color} fontSize={9} fontFamily="monospace" fontWeight={700}>
                {agent.name}
              </text>
              <text x={342} y={377} fill="rgba(255,255,255,0.35)" fontSize={7} fontFamily="monospace">
                ACTIVE
              </text>
            </g>
          );
        })()}
      </svg>
    </div>
  );
}
