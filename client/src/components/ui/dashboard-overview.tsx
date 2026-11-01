import * as React from "react";
import { useEffect, useRef, useState } from "react";
import { motion, type Variants } from "framer-motion";
import { DashboardSkeleton } from "./dashboard-skeleton";
import { useLocation } from "wouter";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import AgentNetworkGraph from "./agent-network-graph";

interface DashboardOverviewProps { loading?: boolean; }

/* ── variants ───────────────────────────────────────────────── */
const fade: Variants = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 230, damping: 24 } },
};
const stagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07 } },
};

const METRIC_CONFIG = [
  { label: "Conversations",  key: "totalSessions",    icon: "fas fa-comments",      hex: "#00d8ff", rgb: "0,216,255",   route: "/",        fallback: 0 },
  { label: "Active Agents",  key: "activeAgents",     icon: "fas fa-robot",         hex: "#00ff88", rgb: "0,255,136",   route: "/agents",   fallback: 7 },
  { label: "Reports",        key: "reportsGenerated", icon: "fas fa-chart-bar",     hex: "#9b59fc", rgb: "155,89,252",  route: "/reports",  fallback: 0 },
  { label: "Scans",          key: "scansRun",         icon: "fas fa-shield-halved", hex: "#ff3868", rgb: "255,56,104",  route: "/redteam",  fallback: 0 },
];

interface Stats {
  totalConversations: number;
  totalSessions: number;
  activeAgents: number;
  reportsGenerated: number;
  scansRun: number;
  ragDocuments: number;
  ragActive: boolean;
}

const AGENTS = [
  { name: "NEXUS",    role: "Orchestrator",icon: "fas fa-atom",          g: "#00d8ff,#0050ff", status: true  },
  { name: "SENTINEL", role: "Security",    icon: "fas fa-shield-halved", g: "#60a5fa,#6366f1", status: true  },
  { name: "DISSECT",  role: "Analyst",     icon: "fas fa-microscope",    g: "#9b59fc,#7c3aed", status: true  },
  { name: "GHOST",    role: "OSINT",       icon: "fas fa-ghost",         g: "#ec4899,#f43f5e", status: true  },
  { name: "PHANTOM",  role: "Red Team",    icon: "fas fa-skull",         g: "#ff3868,#f97316", status: false },
  { name: "MENTOR",   role: "Tutor",       icon: "fas fa-graduation-cap",g: "#00ff88,#14b8a6", status: true  },
  { name: "ARCHIVE",  role: "Memory",      icon: "fas fa-database",      g: "#ffb700,#f59e0b", status: true  },
  { name: "SIGMA",    role: "Math",        icon: "fas fa-infinity",      g: "#9b59fc,#7c3aed", status: true  },
];

/* ── Particle Canvas ─────────────────────────────────────────── */
function ParticleCanvas() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf: number;
    const particles: { x: number; y: number; r: number; vx: number; vy: number; a: number; da: number; color: string }[] = [];
    const colors = ["rgba(0,216,255,", "rgba(0,255,136,", "rgba(155,89,252,", "rgba(255,56,104,"];
    const resize = () => { canvas.width = canvas.offsetWidth; canvas.height = canvas.offsetHeight; };
    resize();
    window.addEventListener("resize", resize);

    for (let i = 0; i < 60; i++) {
      const c = colors[Math.floor(Math.random() * colors.length)];
      particles.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        r: Math.random() * 1.5 + 0.3,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        a: Math.random(),
        da: (Math.random() - 0.5) * 0.005,
        color: c,
      });
    }

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      particles.forEach(p => {
        p.x += p.vx; p.y += p.vy; p.a += p.da;
        if (p.x < 0) p.x = canvas.width;
        if (p.x > canvas.width) p.x = 0;
        if (p.y < 0) p.y = canvas.height;
        if (p.y > canvas.height) p.y = 0;
        if (p.a < 0.1) p.da = Math.abs(p.da);
        if (p.a > 0.9) p.da = -Math.abs(p.da);
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = p.color + p.a.toFixed(2) + ")";
        ctx.fill();
      });
      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", resize); };
  }, []);
  return <canvas ref={ref} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }} />;
}

/* ── Counter ─────────────────────────────────────────────────── */
function Counter({ to, fmt }: { to: number; fmt: string }) {
  const [v, setV] = useState(0);
  useEffect(() => {
    let start = 0;
    const step = to / 40;
    const t = setInterval(() => {
      start += step;
      if (start >= to) { setV(to); clearInterval(t); }
      else setV(Math.floor(start));
    }, 30);
    return () => clearInterval(t);
  }, [to]);
  return <>{to === v ? fmt : v.toLocaleString()}</>;
}

/* ── helpers ─────────────────────────────────────────────────── */
function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "morning" : h < 18 ? "afternoon" : "evening";
}
function gc(g: string) {
  const [a, b] = g.split(",");
  return `linear-gradient(135deg, ${a}, ${b})`;
}
function grgba(g: string, a = 0.35): string {
  const c = g.split(",")[0];
  return c.replace("rgba", "rgba").replace("rgb", "rgba");
}

/* ── component ───────────────────────────────────────────────── */
export const DashboardOverview = ({ loading = false }: DashboardOverviewProps) => {
  const [, navigate] = useLocation();

  // Fetch live stats from backend — refreshes every 30s
  const { data: stats } = useQuery<Stats>({
    queryKey: ["/api/protected/stats"],
    queryFn: () => api.get("/api/protected/stats"),
    refetchInterval: 30000,
    staleTime: 15000,
    enabled: !!localStorage.getItem("auth_token"),
  });

  if (loading) return <DashboardSkeleton />;

  return (
    <motion.div
      variants={stagger} initial="hidden" animate="show"
      style={{ padding: "20px 20px 28px", display: "flex", flexDirection: "column", gap: 20, position: "relative" }}
    >

      {/* ── HERO ───────────────────────────────────────────────── */}
      <motion.div variants={fade} style={{
        position: "relative", overflow: "hidden", borderRadius: 18,
        border: "1px solid rgba(0,216,255,0.22)",
        background: "linear-gradient(135deg, rgba(0,216,255,0.07) 0%, rgba(4,8,15,0.95) 55%, rgba(0,255,136,0.04) 100%)",
        boxShadow: "0 0 40px rgba(0,216,255,0.10), inset 0 1px 0 rgba(0,216,255,0.18)",
        padding: "28px 32px",
      }}>
        {/* Canvas particles */}
        <div style={{ position: "absolute", inset: 0, opacity: 0.7 }}><ParticleCanvas /></div>

        {/* Top glow bar */}
        <div style={{ position:"absolute",top:0,left:0,right:0,height:2,
          background:"linear-gradient(90deg,transparent,rgba(0,216,255,0.8),rgba(0,255,136,0.5),transparent)" }} />

        <div style={{ position: "relative", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 20, flexWrap: "wrap" }}>
          {/* Greeting */}
          <div>
            <div style={{ fontFamily:"monospace",fontSize:10,letterSpacing:"0.25em",color:"rgba(0,216,255,0.7)",textTransform:"uppercase",marginBottom:6 }}>
              ▸ &nbsp;WELCOME BACK
            </div>
            <div style={{ fontFamily:"monospace",fontWeight:900,fontSize:30,color:"#fff",lineHeight:1.15 }}>
              Good{" "}
              <motion.span
                animate={{ textShadow: ["0 0 12px rgba(0,216,255,0.6)","0 0 24px rgba(0,216,255,1)","0 0 12px rgba(0,216,255,0.6)"] }}
                transition={{ duration: 2.5, repeat: Infinity, ease: "easeInOut" }}
                style={{ background:"linear-gradient(135deg,#00d8ff,#00ff88)", WebkitBackgroundClip:"text", WebkitTextFillColor:"transparent", backgroundClip:"text" }}
              >
                {greeting()}
              </motion.span>
              ,&nbsp;Operator
            </div>
            <div style={{ fontFamily:"monospace",fontSize:11,color:"rgba(255,255,255,0.38)",marginTop:8,letterSpacing:"0.04em" }}>
              AKKI AI Platform&nbsp;&nbsp;·&nbsp;&nbsp;
              <span style={{ color:"#00ff88",textShadow:"0 0 8px rgba(0,255,136,0.5)" }}>All Systems Operational</span>
            </div>
          </div>

          {/* Status pills */}
          {/* Status pills — live from API */}
          <div style={{ display:"flex",flexDirection:"column",gap:6,alignItems:"flex-end" }}>
            {[
              { t:`${stats?.activeAgents ?? 7} Agents Online`, hex:"#00ff88", rgb:"0,255,136", show: true },
              { t:"RAG Active",    hex:"#00d8ff", rgb:"0,216,255", show: stats?.ragActive ?? false },
              { t:"Knowledge Base", hex:"#9b59fc", rgb:"155,89,252", show: (stats?.ragDocuments ?? 0) > 0,
                label: `${stats?.ragDocuments ?? 0} Doc${(stats?.ragDocuments ?? 0) !== 1 ? "s" : ""}` },
            ].filter(p => p.show).map(p => (
              <motion.div key={p.t}
                animate={{ boxShadow:[`0 0 8px rgba(${p.rgb},0.4)`,`0 0 18px rgba(${p.rgb},0.7)`,`0 0 8px rgba(${p.rgb},0.4)`] }}
                transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                style={{
                  display:"inline-flex",alignItems:"center",gap:7,padding:"5px 13px",borderRadius:999,
                  background:`rgba(${p.rgb},0.12)`,border:`1px solid rgba(${p.rgb},0.5)`,
                  fontFamily:"monospace",fontSize:10,fontWeight:700,
                  letterSpacing:"0.1em",color:p.hex,textTransform:"uppercase",whiteSpace:"nowrap",
                }}
              >
                <motion.span animate={{ opacity:[1,0.2,1] }} transition={{ duration:1.2,repeat:Infinity }}
                  style={{ width:6,height:6,borderRadius:"50%",background:p.hex,boxShadow:`0 0 6px ${p.hex}`,flexShrink:0 }} />
                {"label" in p ? p.label : p.t}
              </motion.div>
            ))}
          </div>
        </div>
      </motion.div>

      {/* ── METRIC CARDS ───────────────────────────────────────── */}
      <motion.div variants={stagger} style={{ display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:14 }}>
        {METRIC_CONFIG.map((m) => {
          const liveValue = stats ? (stats as unknown as Record<string, number>)[m.key] ?? m.fallback : null;
          const displayNum = liveValue ?? m.fallback;
          return (
            <motion.div key={m.label} variants={fade}
              whileHover={{ scale:1.04, y:-4, boxShadow:`0 0 40px rgba(${m.rgb},0.30), 0 8px 32px rgba(0,0,0,0.7)` }}
              transition={{ type:"spring" as const, stiffness:280, damping:22 }}
              onClick={() => navigate(m.route)}
              style={{
                background:`linear-gradient(145deg, rgba(${m.rgb},0.10) 0%, rgba(8,13,26,0.97) 100%)`,
                border:`1px solid rgba(${m.rgb},0.40)`,
                boxShadow:`0 0 24px rgba(${m.rgb},0.14), 0 4px 20px rgba(0,0,0,0.6)`,
                borderRadius:16, padding:"22px 18px", cursor:"pointer", position:"relative", overflow:"hidden",
              }}
            >
              <div style={{ position:"absolute",top:0,left:0,right:0,height:2,background:`linear-gradient(90deg,transparent,rgba(${m.rgb},0.8),transparent)` }} />
              <div style={{ position:"absolute",top:16,right:16,width:40,height:40,borderRadius:12,
                background:`rgba(${m.rgb},0.18)`,border:`1px solid rgba(${m.rgb},0.45)`,
                display:"flex",alignItems:"center",justifyContent:"center",boxShadow:`0 0 14px rgba(${m.rgb},0.25)` }}>
                <i className={m.icon} style={{ color:m.hex,fontSize:16 }} />
              </div>
              <div style={{ fontFamily:"monospace",fontWeight:900,fontSize:38,color:"#fff",lineHeight:1,marginBottom:4,textShadow:`0 0 20px rgba(${m.rgb},0.40)` }}>
                {stats ? <Counter to={displayNum} fmt={displayNum.toLocaleString()} /> : <span>—</span>}
              </div>
              <div style={{ fontFamily:"monospace",fontSize:9,color:"rgba(255,255,255,0.35)",textTransform:"uppercase",letterSpacing:"0.12em",marginBottom:12 }}>
                {m.label}
              </div>
              <div style={{ display:"inline-flex",alignItems:"center",gap:5,padding:"3px 10px",borderRadius:999,
                background:`rgba(${m.rgb},0.12)`,fontFamily:"monospace",fontSize:10,fontWeight:700,color:m.hex }}>
                {stats ? (displayNum === 0 ? "No data yet" : `${displayNum} total`) : "Loading..."}
              </div>
            </motion.div>
          );
        })}
      </motion.div>

      {/* ── AGENT NETWORK (live graph) ──────────────────────── */}
      <motion.div variants={fade}>
        <div style={{ display:"flex",alignItems:"center",gap:12,marginBottom:12 }}>
          <div style={{ flex:1,height:1,background:"linear-gradient(to right,transparent,rgba(0,216,255,0.25),transparent)" }} />
          <span style={{ fontFamily:"monospace",fontSize:9,color:"rgba(0,216,255,0.55)",textTransform:"uppercase",letterSpacing:"0.2em",whiteSpace:"nowrap" }}>
            Live Agent Network
          </span>
          <div style={{ flex:1,height:1,background:"linear-gradient(to right,transparent,rgba(0,216,255,0.25),transparent)" }} />
        </div>
        <div style={{ background:"rgba(8,13,26,0.80)",border:"1px solid rgba(0,216,255,0.14)",borderRadius:16,padding:"8px 4px",overflow:"hidden" }}>
          <AgentNetworkGraph />
        </div>
      </motion.div>

      {/* ── QUICK ACTIONS ──────────────────────────────────────── */}
      <motion.div variants={fade}>
        <div style={{ display:"flex",alignItems:"center",gap:12,marginBottom:12 }}>
          <div style={{ flex:1,height:1,background:"linear-gradient(to right,transparent,rgba(0,216,255,0.20),transparent)" }} />
          <span style={{ fontFamily:"monospace",fontSize:9,color:"rgba(0,216,255,0.50)",textTransform:"uppercase",letterSpacing:"0.2em",whiteSpace:"nowrap" }}>
            Quick Actions
          </span>
          <div style={{ flex:1,height:1,background:"linear-gradient(to right,transparent,rgba(0,216,255,0.20),transparent)" }} />
        </div>

        <motion.div variants={stagger} style={{ display:"flex",gap:12,flexWrap:"wrap" }}>
          {[
            { t:"Start Chat",   i:"fas fa-comment-dots",   hex:"#00d8ff",rgb:"0,216,255", fn:()=>navigate('/') },
            { t:"Upload Doc",   i:"fas fa-file-arrow-up",  hex:"#00ff88",rgb:"0,255,136", fn:()=>{ const inp=document.createElement('input');inp.type='file';inp.accept='.pdf,.md,.txt,.log,.png,.jpg,.jpeg';inp.click(); } },
            { t:"Run Scan",     i:"fas fa-satellite-dish", hex:"#ff3868",rgb:"255,56,104",fn:()=>navigate('/redteam') },
            { t:"View Reports", i:"fas fa-chart-line",     hex:"#9b59fc",rgb:"155,89,252",fn:()=>navigate('/reports') },
          ].map(a => (
            <motion.button key={a.t} variants={fade}
              onClick={a.fn}
              whileHover={{ scale:1.06, y:-3, boxShadow:`0 0 24px rgba(${a.rgb},0.45)` }}
              whileTap={{ scale:0.95 }}
              transition={{ type:"spring" as const, stiffness:340, damping:22 }}
              style={{
                background:`rgba(${a.rgb},0.10)`,border:`1px solid rgba(${a.rgb},0.40)`,
                color:a.hex,fontFamily:"monospace",fontSize:12,fontWeight:700,
                padding:"11px 20px",borderRadius:12,cursor:"pointer",
                display:"flex",alignItems:"center",gap:8,
                boxShadow:`0 0 12px rgba(${a.rgb},0.12)`,
                letterSpacing:"0.04em",
              }}
            >
              <i className={a.i} style={{ fontSize:11 }} />
              {a.t}
            </motion.button>
          ))}
        </motion.div>
      </motion.div>
    </motion.div>
  );
};
