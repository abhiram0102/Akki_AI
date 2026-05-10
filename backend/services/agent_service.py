"""
AKKI Multi-Agent Orchestration System

7 specialized agents, each with deep cybersecurity expertise:
  NEXUS    - Planner/Orchestrator
  GHOST    - OSINT & Reconnaissance  
  PHANTOM  - Exploitation & Offensive Ops
  SENTINEL - Defense & Detection Engineering
  DISSECT  - Malware Analysis & Reverse Engineering
  MENTOR   - Cybersecurity Education & Tutoring
  ARCHIVE  - Memory & Knowledge Retrieval

The Planner agent routes incoming requests to the most appropriate specialist.
Agents can be chained for complex multi-step operations.
"""
import json
import re
from datetime import datetime, timezone
from backend.services.ai_service import ai_service, AGENT_PERSONAS, AIQuotaError
from backend.services.tool_service import run_tool


# Tool definitions that agents can invoke
AVAILABLE_TOOLS = {
    "dns_lookup": {
        "description": "Perform comprehensive DNS record lookup (A, AAAA, MX, NS, TXT, SOA)",
        "params": {"domain": "Target domain to look up"},
        "agents": ["recon", "planner"],
    },
    "whois": {
        "description": "WHOIS lookup for domain or IP registration info",
        "params": {"target": "Domain or IP address"},
        "agents": ["recon", "planner"],
    },
    "http_probe": {
        "description": "Probe HTTP/HTTPS endpoint for security headers, server info, and technology stack",
        "params": {"url": "Target URL"},
        "agents": ["recon", "exploit", "planner"],
    },
    "port_scan": {
        "description": "Scan common TCP ports to identify open services",
        "params": {"host": "Target hostname or IP"},
        "agents": ["recon", "exploit", "planner"],
    },
    "subdomain_enum": {
        "description": "Enumerate subdomains using DNS brute force",
        "params": {"domain": "Root domain to enumerate"},
        "agents": ["recon", "planner"],
    },
    "ssl_analyze": {
        "description": "Analyze SSL/TLS certificate information",
        "params": {"host": "Target hostname"},
        "agents": ["recon", "defense", "planner"],
    },
}


QUOTA_RESPONSES = {
    "planner": """**NEXUS OPERATING IN CACHED MODE**

> *Gemini API quota temporarily exhausted. Core intelligence available.*

**I can still assist you with:**
- Explaining cybersecurity concepts and techniques
- Reviewing MITRE ATT&CK tactics and procedures  
- Discussing penetration testing methodologies
- Analyzing security architectures
- Providing tool syntax and usage guidance
- Walking through attack chains and kill chains

**Quota reset typically within:** 15-60 minutes

**What would you like to explore from my cached knowledge base?**""",

    "recon": """**GHOST — OSINT INTELLIGENCE (CACHED MODE)**

My active scanning capabilities are temporarily limited, but my passive intelligence is available.

**Available resources:**
- OSINT methodology and tradecraft
- Google dorking operators and techniques  
- Shodan/Censys query syntax
- Recon-ng and theHarvester usage
- GitHub OSINT techniques
- DNS and certificate transparency analysis approaches
- Attack surface mapping frameworks

What target are you researching? I can guide your manual reconnaissance.""",

    "exploit": """**PHANTOM — EXPLOIT INTELLIGENCE (CACHED MODE)**

Active AI analysis temporarily paused. Static exploit knowledge available.

**I can cover:**
- CVE analysis and exploit concepts
- OWASP Top 10 vulnerability explanations
- MITRE ATT&CK technique breakdowns
- Common exploit patterns and payloads
- Metasploit module usage
- Manual exploitation techniques

What vulnerability or technique do you need help with?""",

    "defense": """**SENTINEL — DEFENSE INTELLIGENCE (CACHED MODE)**

Detection and hardening knowledge base active.

**Available guidance:**
- Sigma rule templates
- YARA rule construction
- CIS Benchmark controls
- SIEM query examples (Splunk/ELK)
- Incident response playbooks
- Network segmentation best practices

What security control are you implementing?""",

    "malware": """**DISSECT — MALWARE INTELLIGENCE (CACHED MODE)**

Static analysis knowledge base active.

**Available:**
- PE/ELF structure analysis guidance
- Common malware family TTPs
- IOC extraction techniques
- Reverse engineering workflow
- Sandbox analysis interpretation
- YARA rule templates

What malware sample or technique are you analyzing?""",

    "tutor": """**MENTOR — EDUCATION ENGINE (CACHED MODE)**

Teaching knowledge base fully operational.

**I can help with:**
- CEH, OSCP, Security+, PNPT study guides
- Networking fundamentals
- Linux privilege escalation techniques
- Web application security (OWASP)
- CTF challenge strategies
- Interview preparation
- Lab environment setup

What topic would you like to learn about?""",

    "memory": """**ARCHIVE — KNOWLEDGE RETRIEVAL (CACHED MODE)**

Historical context processing available from session memory.

What information would you like me to recall or synthesize?""",
}


class AgentService:
    def __init__(self):
        self.conversation_histories = {}  # session_id -> list of messages

    def _get_history(self, session_id: str) -> list:
        return self.conversation_histories.get(session_id, [])

    def _add_to_history(self, session_id: str, role: str, content: str):
        if session_id not in self.conversation_histories:
            self.conversation_histories[session_id] = []
        self.conversation_histories[session_id].append({
            "role": role,
            "content": content,
        })
        # Keep last 20 messages
        if len(self.conversation_histories[session_id]) > 20:
            self.conversation_histories[session_id] = self.conversation_histories[session_id][-20:]

    async def _should_use_tools(self, message: str, agent: str) -> list:
        """Detect if the message warrants real tool execution."""
        tool_triggers = []
        msg_lower = message.lower()

        # DNS/WHOIS triggers
        if any(kw in msg_lower for kw in ["dns", "lookup", "records", "whois", "registrar", "nameserver"]):
            # Extract domain
            domain = self._extract_domain(message)
            if domain:
                tool_triggers.append({"tool": "dns_lookup", "params": {"domain": domain}})

        # Port scan triggers
        if any(kw in msg_lower for kw in ["port scan", "open ports", "nmap", "scan ports", "port check"]):
            host = self._extract_domain(message) or self._extract_ip(message)
            if host:
                tool_triggers.append({"tool": "port_scan", "params": {"host": host}})

        # HTTP probe triggers
        if any(kw in msg_lower for kw in ["http headers", "security headers", "probe", "website check", "web scan"]):
            url = self._extract_url(message)
            if url:
                tool_triggers.append({"tool": "http_probe", "params": {"url": url}})

        # Subdomain triggers
        if any(kw in msg_lower for kw in ["subdomain", "enumerate subdomains", "subdomains of"]):
            domain = self._extract_domain(message)
            if domain:
                tool_triggers.append({"tool": "subdomain_enum", "params": {"domain": domain}})

        # WHOIS explicit
        if "whois" in msg_lower:
            target = self._extract_domain(message) or self._extract_ip(message)
            if target:
                tool_triggers.append({"tool": "whois", "params": {"target": target}})

        return tool_triggers[:3]  # Max 3 tools per request

    def _extract_domain(self, text: str) -> str | None:
        """Extract a domain from text."""
        # Common domain patterns
        patterns = [
            r'\b(?:https?://)?([a-zA-Z0-9][a-zA-Z0-9\-]*\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)\b',
        ]
        for pat in patterns:
            matches = re.findall(pat, text)
            for m in matches:
                # Filter out common non-domain words
                if m not in ["example.com", "localhost"] and "." in m:
                    return m.lower()
        return None

    def _extract_ip(self, text: str) -> str | None:
        """Extract an IP address from text."""
        pattern = r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b'
        matches = re.findall(pattern, text)
        return matches[0] if matches else None

    def _extract_url(self, text: str) -> str | None:
        """Extract a URL from text."""
        pattern = r'(https?://[^\s]+|[a-zA-Z0-9][a-zA-Z0-9\-]*\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)'
        matches = re.findall(pattern, text)
        return matches[0] if matches else None

    async def process_message(
        self,
        message: str,
        session_id: str,
        user_id: str,
        voice_input: bool = False,
        context: dict = None,
    ) -> dict:
        """
        Main message processing pipeline:
        1. Route to appropriate agent
        2. Optionally execute real tools
        3. Generate AI response with tool context
        4. Update conversation history
        """
        history = self._get_history(session_id)
        tool_results = []
        tool_calls_display = []

        try:
            # Step 1: Route to specialist agent
            routing = await ai_service.route_to_agent(message, context)
            agent_key = routing.get("agent", "planner")
            agent_info = AGENT_PERSONAS.get(agent_key, AGENT_PERSONAS["planner"])

            # Step 2: Check for tool opportunities
            tool_triggers = await self._should_use_tools(message, agent_key)

            for trigger in tool_triggers:
                tool_name = trigger["tool"]
                params = trigger["params"]
                tool_result = await run_tool(tool_name, params)
                tool_results.append(tool_result)
                tool_calls_display.append({
                    "id": f"tool-{tool_name}-{len(tool_calls_display)}",
                    "name": tool_name,
                    "displayName": AVAILABLE_TOOLS.get(tool_name, {}).get("description", tool_name),
                    "params": params,
                    "result": tool_result,
                    "status": "success" if tool_result.get("success") else "error",
                })

            # Step 3: Build enriched prompt
            enriched_message = message
            if tool_results:
                tool_context = "\n\n".join([
                    f"**{tr['tool']} Results:**\n```json\n{json.dumps(tr.get('result', {}), indent=2)[:1500]}\n```"
                    for tr in tool_results if tr.get("success")
                ])
                enriched_message = f"""{message}

**[TOOL EXECUTION RESULTS - Use these in your analysis]**
{tool_context}

Analyze these results, explain what they reveal about the target, identify security implications, and provide actionable recommendations."""

            # Step 4: Generate AI response
            messages = history + [{"role": "user", "content": enriched_message}]
            response_text = await ai_service.chat_completion(
                messages,
                agent=agent_key,
                temperature=0.7,
            )

        except AIQuotaError:
            agent_key = "planner"
            agent_info = AGENT_PERSONAS["planner"]
            # Try to route even in quota mode
            try:
                routing_simple = await ai_service.route_to_agent(message, context)
                agent_key = routing_simple.get("agent", "planner")
                agent_info = AGENT_PERSONAS.get(agent_key, AGENT_PERSONAS["planner"])
            except Exception:
                pass

            response_text = QUOTA_RESPONSES.get(agent_key, QUOTA_RESPONSES["planner"])
            routing = {"agent": agent_key, "confidence": 0.5, "reason": "Quota fallback"}

        except Exception as e:
            agent_key = "planner"
            agent_info = AGENT_PERSONAS["planner"]
            response_text = f"""**NEXUS — SYSTEM ERROR**

An error occurred while processing your request: `{str(e)[:300]}`

Please try rephrasing your question or try again in a moment."""
            routing = {"agent": "planner", "confidence": 0.0, "reason": "Error fallback"}

        # Step 5: Update conversation history
        self._add_to_history(session_id, "user", message)
        self._add_to_history(session_id, "assistant", response_text)

        return {
            "content": response_text,
            "toolCalls": tool_calls_display,
            "ragUsed": False,
            "sources": [],
            "emotionalTone": "professional",
            "plan": None,
            "agent": agent_key,
            "agentName": agent_info["name"],
            "agentRole": agent_info["role"],
            "agentColor": agent_info["color"],
            "routing": routing,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def get_agent_status(self) -> list:
        """Return status of all registered agents."""
        return [
            {
                "id": agent_id,
                "name": info["name"],
                "role": info["role"],
                "color": info["color"],
                "status": "active",
                "capabilities": list(AVAILABLE_TOOLS.keys()),
            }
            for agent_id, info in AGENT_PERSONAS.items()
        ]


agent_service = AgentService()
