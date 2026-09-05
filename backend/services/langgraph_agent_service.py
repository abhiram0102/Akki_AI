"""
LangGraph-based Multi-Agent System for AKKI AI
Production-grade implementation using LangChain and LangGraph frameworks
Replaces custom agent_service.py with enterprise-grade agent orchestration
"""
import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, TypedDict, Annotated, Literal, Optional, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

# Import existing AKKI services
from backend.services.ai_service import ai_service, AGENT_PERSONAS, AIQuotaError
from backend.services.tool_service import run_tool
from backend.services.rag_service import rag_service
from backend.database import get_db
from backend.models import User

logger = logging.getLogger("akki.langgraph_agent")

# ======================= AGENT STATE DEFINITION =======================

class AgentState(TypedDict):
    """State that flows through the LangGraph agent system"""
    messages: Annotated[List[BaseMessage], add_messages]
    agent: str  # Current active agent
    session_id: str
    user_id: str
    tool_results: List[dict]
    rag_context: str
    next: Literal["planner", "defender", "analyst", "researcher", "creator", "tutor", "coding_assistant", "__end__"]
    metadata: Dict[str, Any]  # For tracking execution metrics, tool usage, etc.
    error: Optional[str]  # Error tracking

# ======================= TOOL DEFINITIONS =======================

# Custom LangChain tools that wrap AKKI's real tool execution
class AKKITool(BaseTool):
    """Base class for AKKI tools with proper error handling and logging"""
    name: str
    description: str

    def _run(self, *args, **kwargs) -> str:
        """Synchronous run - not used in async context"""
        raise NotImplementedError("Use _arun instead")

    async def _arun(self, *args, **kwargs) -> str:
        """Async tool execution"""
        try:
            result = await run_tool(self.name, kwargs)
            if result.get("success"):
                # Format result for LLM consumption
                return json.dumps(result.get("result", {}), indent=2)
            else:
                return f"Tool error: {result.get('error', 'Unknown error')}"
        except Exception as e:
            logger.error(f"Tool {self.name} failed: {e}")
            return f"Tool execution failed: {str(e)}"

# Define all available tools
class DNSLookupTool(AKKITool):
    name: str = "dns_lookup"
    description: str = """Perform comprehensive DNS record lookup (A, AAAA, MX, NS, TXT, SOA, CNAME) for a domain.
    Returns DNS records including reverse DNS information. Use for reconnaissance and information gathering."""

class WHOISTool(AKKITool):
    name: str = "whois"
    description: str = """Perform WHOIS lookup on domain or IP address to get registration information.
    Returns registrar, creation/update/expiry dates, organization, country, name servers, etc."""

class HTTPProbeTool(AKKITool):
    name: str = "http_probe"
    description: str = """Probe HTTP/HTTPS endpoint for security headers, server info, status code, and technology stack.
    Analyzes security headers (HSTS, CSP, X-Frame-Options, etc.) and calculates security score."""

class PortScanTool(AKKITool):
    name: str = "port_scan"
    description: str = """Scan common TCP ports on a host to identify open services.
    Scans ports: 21,22,23,25,53,80,110,111,135,139,143,443,445,993,995,1723,3306,3389,5900,8080,8443,8888,27017
    Identifies high-risk services and provides risk assessment."""

class SubdomainEnumTool(AKKITool):
    name: str = "subdomain_enum"
    description: str = """Enumerate subdomains using DNS brute force with common names.
    Checks 70+ common subdomain prefixes (www, mail, ftp, admin, api, dev, staging, etc.)"""

class SSLAnalyzeTool(AKKITool):
    name: str = "ssl_analyze"
    description: str = """Analyze SSL/TLS certificate information for a host.
    Returns certificate subject, issuer, expiration info, and raw certificate data."""


class CRTLookupTool(AKKITool):
    name: str = "crt_lookup"
    description: str = """Certificate transparency lookup via crt.sh.
    Reveals subdomains discovered in SSL/TLS certificate logs without brute-force DNS.
    Use for passive subdomain reconnaissance."""

class IPGeolocationTool(AKKITool):
    name: str = "ip_geolocation"
    description: str = """Geolocate an IP address or hostname.
    Returns country, city, ASN, ISP/org, timezone, and coordinates.
    Accepts IP addresses or domain names (auto-resolves)."""

class WaybackLookupTool(AKKITool):
    name: str = "wayback_lookup"
    description: str = """Wayback Machine / web archive lookup.
    Finds historical snapshots and crawls CDX index for past URLs on a domain.
    Useful for discovering removed pages, old API endpoints, and attack surface history."""

class ReverseIPTool(AKKITool):
    name: str = "reverse_ip"
    description: str = """Reverse IP lookup via HackerTarget.
    Finds other domains hosted on the same IP address.
    Use to identify shared hosting, CDN membership, and co-tenant attack surface."""

class RobotsAnalyzerTool(AKKITool):
    name: str = "robots_analyzer"
    description: str = """Fetch and analyze robots.txt and sitemap.xml for a domain.
    Reveals disallowed paths (often admin panels, internal APIs, backup endpoints).
    Extracts sitemap availability and interesting restricted paths."""

class SigmaMathTool(AKKITool):
    name: str = "sigma_solve"
    description: str = """Invoke SIGMA to solve a mathematical or algorithmic problem.
    Produces: formal problem statement, theorem/algorithm, complexity analysis, Python implementation.
    Use for: algorithm design, complexity analysis, formula derivation, mathematical proofs."""

    async def _arun(self, problem: str = "", **kwargs) -> str:
        try:
            from backend.services.ai_service import ai_service
            result = await ai_service.chat_completion(
                [{"role": "user", "content": problem or kwargs.get("input", "")}],
                agent="sigma",
            )
            return result
        except Exception as e:
            return f"SIGMA tool error: {e}"

    def _run(self, problem: str = "", **kwargs) -> str:
        import asyncio
        try:
            return asyncio.get_event_loop().run_until_complete(self._arun(problem=problem, **kwargs))
        except Exception as e:
            return f"SIGMA tool error: {e}"

class KnowledgeBaseTool(AKKITool):
    name: str = "knowledge_base"
    description: str = """Search uploaded documents in the knowledge base for relevant cybersecurity information.
    Uses RAG (Retrieval-Augmented Generation) to find relevant chunks from user's uploaded documents.
    Essential for grounding responses in specific user-provided context.
    Input: query string describing what information to find."""

    async def _arun(self, query: str = "", **kwargs) -> str:
        """Query the RAG knowledge base directly."""
        try:
            search_query = query or kwargs.get("input", "") or kwargs.get("target", "")
            if not search_query:
                return "No search query provided to knowledge_base tool."

            context = await rag_service.retrieve_context(
                query=search_query,
                top_k=4,
            )
            if not context:
                return "No relevant documents found in the knowledge base for this query."
            return f"**Knowledge Base Results:**\n{context}"
        except Exception as e:
            logger.warning(f"KnowledgeBaseTool failed: {e}")
            return f"Knowledge base search failed: {str(e)}"

    def _run(self, query: str = "", **kwargs) -> str:
        """Sync wrapper — runs async version in event loop."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self._arun(query=query, **kwargs))
        except Exception as e:
            return f"Knowledge base search failed: {str(e)}"

# Tool instances
AVAILABLE_TOOLS = [
    DNSLookupTool(),
    WHOISTool(),
    HTTPProbeTool(),
    PortScanTool(),
    SubdomainEnumTool(),
    SSLAnalyzeTool(),
    CRTLookupTool(),
    IPGeolocationTool(),
    WaybackLookupTool(),
    ReverseIPTool(),
    RobotsAnalyzerTool(),
    KnowledgeBaseTool(),
    SigmaMathTool(),
]

# Map agent types to their available tools (updated for new agent structure)
AGENT_TOOL_MAPPING = {
    "planner": ["dns_lookup", "whois", "http_probe", "port_scan", "subdomain_enum", "ssl_analyze", "crt_lookup", "ip_geolocation", "wayback_lookup", "reverse_ip", "robots_analyzer", "knowledge_base", "sigma_solve"],
    "defender": ["dns_lookup", "whois", "http_probe", "port_scan", "subdomain_enum", "ssl_analyze", "crt_lookup", "ip_geolocation", "robots_analyzer", "knowledge_base"],
    "analyst": ["dns_lookup", "whois", "http_probe", "port_scan", "subdomain_enum", "ssl_analyze", "ip_geolocation", "wayback_lookup", "robots_analyzer", "knowledge_base", "sigma_solve"],
    "researcher": ["dns_lookup", "whois", "http_probe", "port_scan", "subdomain_enum", "ssl_analyze", "crt_lookup", "ip_geolocation", "wayback_lookup", "reverse_ip", "robots_analyzer", "knowledge_base", "sigma_solve"],
    "creator": ["http_probe", "port_scan", "knowledge_base"],  # Limited offensive for safety
    "tutor": ["knowledge_base"],
    "coding_assistant": ["knowledge_base"],
    "sigma": ["sigma_solve", "knowledge_base"],
}

def get_tools_for_agent(agent_name: str) -> List[BaseTool]:
    """Get the list of tools available to a specific agent"""
    tool_names = AGENT_TOOL_MAPPING.get(agent_name, ["knowledge_base"])
    return [tool for tool in AVAILABLE_TOOLS if tool.name in tool_names]

# ======================= AGENT PROMPTS =======================

# Preserve the exact system prompts from the original AGENT_PERSONAS
AGENT_SYSTEM_PROMPTS = {agent_id: info["system"] for agent_id, info in AGENT_PERSONAS.items()}

# ======================= RAG INTEGRATION =======================

async def get_rag_context(query: str, session_id: str, user_id: str, top_k: int = 4) -> str:
    """
    Retrieve RAG context for enhancing agent responses
    Returns formatted context string ready for injection into system prompt
    """
    try:
        # Use the existing retrieve_context method for low-latency retrieval
        context = await rag_service.retrieve_context(
            query=query,
            top_k=top_k,
            owner_id=user_id
        )
        return context
    except Exception as e:
        logger.warning(f"RAG context retrieval failed: {e}")
        return ""

# ======================= AGENT NODES =======================

# ======================= REACT TOOL-CALLING LOOP =======================
#
# The agent graph is a real ReAct loop: a `reason` node decides (call a tool
# or give a final answer), a conditional edge routes to the `tools` node when a
# tool was requested, the `tools` node executes it via the existing AKKITool
# wrappers and feeds the observation back, and control returns to `reason`.
# The loop runs until the model answers in prose or MAX_TOOL_ITERATIONS is hit.
#
# Tool-calling is provider-agnostic: the model is instructed to emit a JSON
# object to call a tool, which works across Free Claude Code / Gemini / Ollama
# without any provider-specific function-calling API.

MAX_TOOL_ITERATIONS = 5

# Explicit argument names per tool, so the model knows exactly what to pass.
_TOOL_PARAM_HINTS = {
    "dns_lookup": {"domain": "target domain"},
    "whois": {"target": "domain or IP"},
    "http_probe": {"url": "target URL"},
    "port_scan": {"host": "hostname or IP"},
    "subdomain_enum": {"domain": "root domain"},
    "ssl_analyze": {"host": "hostname"},
    "crt_lookup": {"domain": "target domain"},
    "ip_geolocation": {"ip": "IP address or hostname"},
    "wayback_lookup": {"url": "target URL or domain"},
    "reverse_ip": {"ip": "IP address"},
    "robots_analyzer": {"domain": "target domain"},
    "knowledge_base": {"query": "what to search for in uploaded documents"},
    "sigma_solve": {"problem": "the math/algorithm problem statement"},
}

# Fast lookup of the instantiated AKKITool objects by name.
_TOOL_BY_NAME = {t.name: t for t in AVAILABLE_TOOLS}


def _allowed_tool_names(agent_name: str) -> list[str]:
    """The tool names this agent is permitted to call."""
    return [n for n in AGENT_TOOL_MAPPING.get(agent_name, ["knowledge_base"]) if n in _TOOL_BY_NAME]


def _tool_catalogue_text(agent_name: str) -> str:
    """Human-readable catalogue of the agent's tools, with arg names, for the
    system prompt."""
    lines = []
    for name in _allowed_tool_names(agent_name):
        tool = _TOOL_BY_NAME[name]
        desc = " ".join((tool.description or "").split())[:200]
        args = _TOOL_PARAM_HINTS.get(name, {})
        arg_str = ", ".join(f'"{k}": <{v}>' for k, v in args.items()) or "(no arguments)"
        lines.append(f'- {name}({arg_str}): {desc}')
    return "\n".join(lines)


def _react_system_prompt(agent_name: str, rag_context: str) -> str:
    """Base persona + tool catalogue + the ReAct calling contract."""
    prompt = AGENT_SYSTEM_PROMPTS[agent_name]
    if rag_context:
        prompt += ("\n\n**KNOWLEDGE BASE CONTEXT:**\n" + rag_context +
                   "\n\nUse this to ground your response in the user's documents.")

    catalogue = _tool_catalogue_text(agent_name)
    if catalogue:
        prompt += f"""

**TOOLS YOU CAN RUN**

You can execute real tools to gather live information before answering. Available tools:
{catalogue}

**HOW TO CALL A TOOL:** reply with ONLY a single JSON object and nothing else, e.g.
{{"tool": "dns_lookup", "args": {{"domain": "example.com"}}}}

After a tool runs you will be shown its result and can call another tool or answer.
**WHEN DONE:** reply with your final answer in normal prose (no JSON). Only call a
tool when live data genuinely helps; otherwise just answer. You may call at most
{MAX_TOOL_ITERATIONS} tools per turn."""
    return prompt


def _parse_tool_call(reply: str) -> dict | None:
    """Extract a {"tool": str, "args": dict} request from a model reply, or
    None if the reply is a normal prose answer. Tolerant of code fences and
    surrounding whitespace; never raises."""
    if not reply:
        return None
    text = reply.strip()
    # Strip a leading ```json / ``` fence if present.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # Find the first balanced-looking JSON object containing a "tool" key.
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict) or "tool" not in obj:
        return None
    tool = obj.get("tool")
    args = obj.get("args", {})
    if not isinstance(tool, str) or not isinstance(args, dict):
        return None
    return {"tool": tool, "args": args}


def _lc_messages_from_state(state: AgentState, system_prompt: str) -> list[dict]:
    """Flatten LangChain message objects into the {role, content} dicts the
    AI service expects, prepending the system prompt."""
    lc = [{"role": "system", "content": system_prompt}]
    for msg in state["messages"]:
        if isinstance(msg, HumanMessage):
            lc.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            lc.append({"role": "assistant", "content": msg.content})
        elif isinstance(msg, SystemMessage):
            continue
        else:
            lc.append({"role": "user", "content": str(msg.content if hasattr(msg, "content") else msg)})
    return lc


async def reason_node(state: AgentState) -> AgentState:
    """Decision node: ask the LLM whether to call a tool or give the final
    answer, given the conversation + any tool observations so far."""
    agent_name = state.get("agent") or "planner"
    iterations = state.get("metadata", {}).get("tool_iterations", 0)
    system_prompt = _react_system_prompt(agent_name, state.get("rag_context", ""))
    lc_messages = _lc_messages_from_state(state, system_prompt)

    try:
        reply = await ai_service.chat_completion(
            messages=lc_messages, agent=agent_name, user_id=state["user_id"]
        )
    except AIQuotaError:
        logger.warning("AI quota exceeded for agent %s", agent_name)
        reply = (f"**{agent_name.upper()} — CACHED MODE**\n\nAI provider temporarily "
                 "unavailable. I can still discuss concepts, techniques, and tool usage "
                 "from my knowledge base — what would you like to explore?")
    except Exception as e:
        logger.error("Agent %s completion failed: %s", agent_name, e)
        reply = f"**{agent_name.upper()} — ERROR**\n\n`{str(e)[:300]}`\n\nPlease rephrase or retry."

    tool_call = _parse_tool_call(reply)
    allowed = _allowed_tool_names(agent_name)

    # A tool call only proceeds if the tool exists, is in scope, and we're
    # under the iteration cap. Otherwise the reply is treated as the answer.
    if tool_call and tool_call["tool"] in allowed and iterations < MAX_TOOL_ITERATIONS:
        metadata = {**state.get("metadata", {})}
        return {**state, "next": "tools", "metadata": {**metadata, "pending_tool": tool_call}, "error": None}

    # Final answer. If the model tried to call an unknown/out-of-scope tool,
    # still surface its text rather than the raw JSON.
    return {
        **state,
        "messages": state["messages"] + [AIMessage(content=reply)],
        "next": "__end__",
        "metadata": {**state.get("metadata", {}), "last_agent": agent_name, "pending_tool": None},
        "error": None,
    }


async def tool_execution_node(state: AgentState) -> AgentState:
    """Act node: run the pending tool and feed its result back as an
    observation for the next reasoning step."""
    metadata = {**state.get("metadata", {})}
    pending = metadata.get("pending_tool")
    iterations = metadata.get("tool_iterations", 0) + 1
    metadata["tool_iterations"] = iterations

    tool_calls = list(metadata.get("tool_calls", []))
    observation: str
    if not pending or pending["tool"] not in _TOOL_BY_NAME:
        observation = f"Tool error: unknown tool {pending.get('tool') if pending else None!r}"
    else:
        name, args = pending["tool"], pending.get("args", {})
        try:
            observation = await _TOOL_BY_NAME[name]._arun(**args)
        except Exception as e:
            logger.error("Tool %s execution failed: %s", name, e)
            observation = f"Tool {name} failed: {str(e)[:300]}"
        tool_calls.append({"tool": name, "args": args})

    metadata["tool_calls"] = tool_calls
    metadata["pending_tool"] = None

    # The observation is appended as a user-role turn so the next reason step
    # sees it as new information to act on.
    obs_msg = HumanMessage(content=f"[TOOL RESULT — {pending['tool'] if pending else 'unknown'}]\n{observation}")
    return {**state, "messages": state["messages"] + [obs_msg], "next": "reason", "metadata": metadata}


def should_continue(state: AgentState) -> str:
    """Conditional edge: route to the tool node when reason_node requested a
    tool, else end the turn."""
    return "tools" if state.get("next") == "tools" else "__end__"

# ======================= ROUTING LOGIC =======================

def cybersecurity_router(state: AgentState) -> Literal["planner", "defender", "analyst", "researcher", "creator", "tutor", "coding_assistant"]:
    """
    Intelligent routing that combines keyword matching with contextual awareness
    Updated for new agent structure: planner, defender, analyst, researcher, creator, tutor, coding_assistant
    """
    if not state["messages"]:
        return "planner"

    # Get the latest user message
    last_message = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            last_message = msg.content.lower()
            break

    if not last_message:
        return "planner"

    logger.debug(f"Routing based on message: {last_message[:100]}...")

    # FAST KEYWORD ROUTING (Updated for new agent structure)
    # Order matters - check more specific patterns first

    # 1. Tutor / Education (highest priority for learning requests)
    tutor_keywords = ["quiz", "tutor", "learn", "study", "exam", "certification", "teach", "explain", "challenge", "mentor", "how to", "what is", "walkthrough", "tutorial"]
    if any(word in last_message for word in tutor_keywords):
        # But avoid false positives for cybersecurity terms that happen to contain these words
        cyber_context = ["exploit", "vulnerability", "malware", "attack", "defense", "security"]
        if not any(cyber in last_message for cyber in cyber_context) or any(edu in last_message for edu in ["learn", "teach", "explain", "tutorial", "how to"]):
            return "tutor"

    # 2. Malware Analysis -> maps to analyst (analysis-focused)
    malware_keywords = ["malware", "reverse engineer", "ghidra", "yara", "binary", "executable", "elf", "pe file", "dissect", "ida pro", "unpacker", "decompiler", "packer", "obfuscation"]
    if any(word in last_message for word in malware_keywords):
        return "analyst"  # Malware analysis is a form of analysis

    # 3. OSINT & Reconnaissance -> maps to researcher (research-focused)
    recon_keywords = ["recon", "reconnaissance", "osint", "shodan", "censys", "whois", "subdomain", "dns", "port scan", "nmap", "theharvester", "footprint", "nslookup", "dig ", "zone transfer", "passive dns"]
    if any(word in last_message for word in recon_keywords):
        return "researcher"  # OSINT & recon aligns with research & information gathering

    # 4. Exploit & Offensive Operations -> maps to analyst (analysis-focused)
    exploit_keywords = ["exploit", "cve-", "vulnerability", "metasploit", "poc", "payload", "sql injection", "sqli", "cross-site scripting", "xss", "buffer overflow", "privilege escalation", "bypass", "rce", "lfi", "rfi", "ssrf", "xxe"]
    if any(word in last_message for word in exploit_keywords):
        return "analyst"  # Exploit/vulnerability analysis fits analysis & problem solving

    # 5. Defense & Detection -> maps to defender (direct match)
    defense_keywords = ["defense", "blue team", "siem", "splunk", "sentinel", "detection rule", "sigma rule", "hardening", "mitigate", "firewall", "waf", "ids", "ips", "endpoint detection", "edr", "xdr", "threat hunting", "incident response"]
    if any(word in last_message for word in defense_keywords):
        return "defender"  # Direct match: defense & security analysis

    # 6. Memory & Context -> maps to planner (context-aware orchestration)
    memory_keywords = ["recall", "remember", "forget", "last time", "context", "history", "previous conversation", "what did we discuss", "earlier you said"]
    if any(word in last_message for word in memory_keywords):
        return "planner"  # Context recall supports planning/orchestration

    # 7. Creation & Design -> maps to creator
    creator_keywords = ["create", "design", "build", "ideate", "brainstorm", "concept", "innovate", "craft", "make", "develop", "draw", "write", "compose", "produce", "form", "shape", "model", "prototype", "design", "creative", "creation"]
    if any(word in last_message for word in creator_keywords):
        return "creator"

    # 8. Programming & Development -> maps to coding_assistant
    coding_keywords = ["code", "program", "debug", "develop", "software", "application", "app", "website", "script", "function", "class", "variable", "fix", "error", "bug", "compile", "run", "execute", "algorithm", "data structure", "frontend", "backend", "fullstack", "api", "rest", "graphql", "programming", "developer", "coding"]
    if any(word in last_message for word in coding_keywords):
        return "coding_assistant"

    # 9. Default to planner for greetings, short inputs, or unclear requests
    # Check if it's a greeting or very short
    words = last_message.split()
    if len(words) <= 3 or last_message.strip() in ["hi", "hello", "hey", "help", "who are you", "what can you do", "thanks", "thank you"]:
        return "planner"

    # Default to planner for everything else
    return "planner"

# ======================= MAIN GRAPH CONSTRUCTION =======================

async def router_node(state: AgentState) -> AgentState:
    """Entry node: pick the persona for this turn (keyword router) and record
    it in state so the reason node knows which persona + tool scope to use."""
    return {**state, "agent": cybersecurity_router(state)}


def build_agent_graph() -> StateGraph:
    """Construct the real ReAct agent graph:

        router → reason ─(tool requested)→ tools → reason → … → END
                    └────────(answer)──────────────────────→ END

    The reason node decides (call a tool or answer); the tools node executes
    the requested tool and feeds the observation back; the loop terminates
    when the model answers in prose or the per-turn tool cap is reached
    (enforced inside reason_node, guaranteeing termination).
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("router", router_node)
    workflow.add_node("reason", reason_node)
    workflow.add_node("tools", tool_execution_node)

    workflow.set_entry_point("router")
    workflow.add_edge("router", "reason")

    # reason decides: run a tool, or finish.
    workflow.add_conditional_edges("reason", should_continue, {"tools": "tools", "__end__": END})

    # after a tool runs, reason again with the new observation.
    workflow.add_edge("tools", "reason")

    # MemorySaver is sufficient for Phase 1 (a whole turn's loop runs inside a
    # single process invocation). Phase 2 swaps this for a Postgres-backed
    # checkpointer so the approval-gate interrupt can resume across workers.
    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)

# Global graph instance (compiled once on import)
_AGENT_GRAPH = None

def get_agent_graph() -> StateGraph:
    """Get or create the compiled agent graph"""
    global _AGENT_GRAPH
    if _AGENT_GRAPH is None:
        _AGENT_GRAPH = build_agent_graph()
    return _AGENT_GRAPH

# ======================= MAIN PROCESSING FUNCTION =======================

async def process_message(
    message: str,
    session_id: str,
    user_id: str,
    voice_input: bool = False,
    context: dict = None,
    config: Optional[RunnableConfig] = None
) -> dict:
    """
    Main entry point for processing user messages through the LangGraph agent system
    Replaces AgentService.process_message with LangGraph-based orchestration

    Args:
        message: User's input message
        session_id: Session identifier for conversation tracking
        user_id: User identifier for personalization and RAG filtering
        voice_input: Whether the input came from voice (unused but kept for compatibility)
        context: Additional context (workspace, etc.)
        config: LangGraph RunnableConfig for callbacks, tags, etc.

    Returns:
        Dict matching the original AgentService.process_message return format
    """
    start_time = time.time()

    try:
        # Extract workspace from context if available
        workspace = (context or {}).get("workspace", "")

        # Prepare initial message with workspace context if present
        user_message = f"[{workspace.upper()} WORKSPACE]\n{message}" if workspace else message

        # Initialize state
        initial_state = AgentState(
            messages=[HumanMessage(content=user_message)],
            agent="",  # Will be set by router
            session_id=session_id,
            user_id=user_id,
            tool_results=[],
            rag_context="",
            next="router",  # Will be overridden by conditional entry point
            metadata={
                "start_time": start_time,
                "session_id": session_id,
                "user_id": user_id,
                "voice_input": voice_input,
                "workspace": workspace
            },
            error=None
        )

        # Get the compiled graph
        graph = get_agent_graph()

        # Configure thread_id for checkpointing (uses session_id)
        thread_config = {
            "configurable": {
                "thread_id": session_id
            }
        }
        if config:
            thread_config.update(config)

        # Execute the graph
        logger.info(f"Starting LangGraph agent processing for session {session_id}")
        final_state = await graph.ainvoke(initial_state, config=thread_config)

        # Calculate total execution time
        total_execution_time = round(time.time() - start_time, 2)

        # Extract the final AI response
        ai_message = final_state["messages"][-1] if final_state["messages"] else AIMessage(content="No response generated")
        agent_used = final_state.get("agent", "planner")

        # Get agent info for response formatting (matching original format)
        agent_info = AGENT_PERSONAS.get(agent_used, AGENT_PERSONAS["planner"])

        # Determine if RAG was used
        rag_used = bool(final_state.get("rag_context", "").strip())

        # Prepare source information (simplified - in production you'd track this better)
        sources = []  # Would be populated from RAG tool execution tracking

        # Real tool calls the ReAct loop actually executed this turn.
        executed_tool_calls = final_state.get("metadata", {}).get("tool_calls", [])

        # Format response to EXACTLY match the original AgentService.process_message return format
        response = {
            "content": ai_message.content,
            "toolCalls": executed_tool_calls,
            "ragUsed": rag_used,
            "sources": sources,
            "emotionalTone": "professional",  # Could be enhanced with emotional AI service integration
            "agent": agent_used,
            "agentName": agent_info["name"],
            "agentRole": agent_info["role"],
            "agentColor": agent_info["color"],
            "routing": {
                "agent": agent_used,
                "confidence": 0.95,  # High confidence from our routing
                "reason": f"LangGraph routing via {agent_used} agent"
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            # Additional metadata for debugging/monitoring (not in original but useful)
            "_metadata": {
                **final_state.get("metadata", {}),
                "total_execution_time": total_execution_time,
                "langgraph_used": True,
                "graph_nodes_visited": len([m for m in final_state["messages"] if isinstance(m, AIMessage)])
            }
        }

        logger.info(f"LangGraph agent processing completed in {total_execution_time}s for session {session_id}, agent: {agent_used}")
        return response

    except Exception as e:
        logger.error(f"LangGraph agent processing failed: {e}", exc_info=True)

        # Fallback to original behavior if LangGraph fails completely
        try:
            logger.info("Falling back to original AI service")
            fallback_result = await ai_service.process_cybersecurity_message(
                message=message,
                context=context,
                user_id=user_id
            )
            fallback_result["_metadata"] = {
                "fallback_used": True,
                "error": str(e),
                "total_execution_time": round(time.time() - start_time, 2)
            }
            return fallback_result
        except Exception as fallback_error:
            logger.error(f"Fallback also failed: {fallback_error}")
            # Last resort error response
            return {
                "content": f"**SYSTEM ERROR**\n\nFailed to process request: {str(e)[:200]}. Please try again later.",
                "toolCalls": [],
                "ragUsed": False,
                "sources": [],
                "emotionalTone": "professional",
                "agent": "planner",
                "agentName": "NEXUS",
                "agentRole": "Orchestration & Planning",
                "agentColor": "cyber-purple",
                "routing": {"agent": "planner", "confidence": 0.0, "reason": "Error fallback"},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

# ======================= HEALTH CHECK & STATUS =======================

async def get_agent_status() -> List[dict]:
    """Get status of all registered agents (matching original interface)"""
    return [
        {
            "id": agent_id,
            "name": info["name"],
            "role": info["role"],
            "color": info["color"],
            "status": "active",
            "capabilities": [tool.name for tool in get_tools_for_agent(agent_id)],
            "framework": "LangGraph"
        }
        for agent_id, info in AGENT_PERSONAS.items()
    ]

# ======================= UTILITY FUNCTIONS =======================

def format_tool_result_for_llm(tool_result: dict) -> str:
    """Format tool execution results for inclusion in LLM context"""
    if not tool_result.get("success"):
        return f"Tool {tool_result.get('tool', 'unknown')} failed: {tool_result.get('error', 'Unknown error')}"

    result_data = tool_result.get("result", {})
    # Truncate large results to prevent context overflow
    result_str = json.dumps(result_data, indent=2)
    if len(result_str) > 2000:
        result_str = result_str[:2000] + "...\n[Result truncated for brevity]"

    return f"**{tool_result.get('tool', 'unknown').upper()} RESULTS:**\n```json\n{result_str}\n```"

# Export the main processing function for easy importing
__all__ = ["process_message", "get_agent_status"]