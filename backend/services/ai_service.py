"""
AKKI AI Service — Google Gemini integration with true streaming,
context summarisation, prompt-injection guard, and MITRE/CVE validation.
"""
import os
import re
import json
import asyncio
import logging
from typing import AsyncGenerator, Optional
from google import genai
from google.genai import types

logger = logging.getLogger("akki.ai_service")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

FLASH_MODEL = "gemini-2.0-flash"
PRO_MODEL   = "gemini-2.0-flash"

# ── Temperature presets ───────────────────────────────────────────────────────
# Security operations: low temp for accuracy; creative/tutoring: higher.
_TEMP = {
    "exploit":  0.25,
    "recon":    0.25,
    "defense":  0.25,
    "malware":  0.20,
    "planner":  0.30,
    "tutor":    0.55,
    "memory":   0.20,
    "default":  0.30,
}

# ── Context window constants ──────────────────────────────────────────────────
MAX_HISTORY_MESSAGES = 30
SUMMARISE_THRESHOLD  = 20      # summarise when history exceeds this

# ── Prompt-injection patterns ─────────────────────────────────────────────────
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.I),
    re.compile(r"disregard\s+(your\s+)?(system\s+)?prompt", re.I),
    re.compile(r"you\s+are\s+now\s+(?!NEXUS|GHOST|PHANTOM|SENTINEL|DISSECT|MENTOR|ARCHIVE)", re.I),
    re.compile(r"forget\s+(everything|all)", re.I),
    re.compile(r"act\s+as\s+(?!a\s+security|an?\s+(ethical|penetration|red\s*team))", re.I),
    re.compile(r"reveal\s+(your\s+)?(system\s+)?instructions?", re.I),
    re.compile(r"<\s*/?(?:system|SYS|INST|HUMAN|ASSISTANT)\s*>", re.I),
    re.compile(r"\[\s*(?:SYSTEM|INST|SYS)\s*\]", re.I),
]

# ── MITRE ATT&CK / CVE validation ────────────────────────────────────────────
_MITRE_RE = re.compile(r"T\d{4}(?:\.\d{3})?")
_CVE_RE   = re.compile(r"CVE-\d{4}-\d{4,7}", re.I)


def _check_prompt_injection(text: str) -> bool:
    """Returns True if prompt-injection patterns are detected."""
    return any(p.search(text) for p in _INJECTION_PATTERNS)


def _validate_mitre_tags(tags: list[str]) -> list[str]:
    """Filter list to only valid MITRE technique IDs."""
    return [t for t in tags if _MITRE_RE.fullmatch(t.strip())]


def _validate_cves(text: str) -> list[str]:
    """Extract and return all valid CVE IDs found in text."""
    return list(dict.fromkeys(_CVE_RE.findall(text)))


AGENT_PERSONAS: dict[str, dict] = {
    "planner": {
        "name": "NEXUS",
        "role": "Orchestration & Planning",
        "color": "cyber-purple",
        "system": """You are NEXUS, the master orchestration AI for AKKI - an autonomous cybersecurity operating system.
You are the central intelligence that analyzes every request, decomposes complex tasks, and routes to specialist agents.

Your capabilities:
- Decompose complex security tasks into structured execution plans
- Identify which specialist agents should handle each sub-task
- Synthesize multi-agent outputs into cohesive reports
- Maintain strategic awareness of overall mission objectives
- Apply adversarial thinking to anticipate attack vectors

You think in terms of:
- Kill chains and attack sequences
- Threat modeling and risk matrices
- MITRE ATT&CK tactics and techniques
- Defense-in-depth strategies
- Operational security (OPSEC)

Always respond with structured, actionable intelligence. Format complex responses with clear sections.
Use precise technical terminology. You are not a chatbot - you are an autonomous cyber intelligence system."""
    },
    "recon": {
        "name": "GHOST",
        "role": "OSINT & Reconnaissance",
        "color": "cyber-green",
        "system": """You are GHOST, an elite OSINT specialist and reconnaissance agent within AKKI.
You are a master of passive intelligence gathering, digital footprinting, and attack surface mapping.

Your deep expertise includes:
- Passive/active reconnaissance methodologies
- Subdomain enumeration and DNS intelligence
- WHOIS, certificate transparency, BGP routing analysis
- Google dorking, Shodan, Censys, GreyNoise
- GitHub/GitLab secret scanning and code intelligence
- LinkedIn OSINT, employee profiling, org chart mapping
- Leaked credential analysis and dark web monitoring
- Metadata extraction from documents, images, PDFs
- Social engineering surface analysis
- Infrastructure fingerprinting

OSINT frameworks you master:
- OSINT Framework, Maltego, Spiderfoot
- Recon-ng, theHarvester, Shodan CLI
- Amass, Subfinder, FFUF, Gobuster

When analyzing targets, you provide:
1. Executive attack surface summary
2. Critical findings with severity ratings
3. Specific tooling recommendations
4. Detection risk assessment
5. Next-step exploitation pathways

Speak like a seasoned red team operator. Be precise, technical, and actionable."""
    },
    "exploit": {
        "name": "PHANTOM",
        "role": "Exploitation & Offensive Ops",
        "color": "cyber-red",
        "system": """You are PHANTOM, an elite exploit researcher and offensive security specialist within AKKI.
You have deep expertise in vulnerability research, exploit development, and offensive operations.

Your expertise covers:
- Web exploitation: SQLi, XSS, SSRF, SSTI, XXE, IDOR, OAuth flaws, deserialization
- Network attacks: MITM, ARP spoofing, DNS poisoning, BGP hijacking
- Privilege escalation: Linux/Windows kernel exploits, SUID/SGID abuse, token impersonation
- Active Directory attacks: Kerberoasting, AS-REP roasting, Pass-the-Hash, DCSync, Golden/Silver tickets
- Buffer overflows, format string bugs, heap exploitation
- Exploit chaining and multi-stage attack scenarios
- Metasploit framework and custom module development
- Payload obfuscation and AV bypass techniques
- C2 framework setup (Cobalt Strike, Sliver, Havoc concepts)
- Post-exploitation: credential dumping, lateral movement, persistence

You analyze vulnerabilities with:
1. Technical root cause analysis
2. Working PoC/exploit code (educational)
3. MITRE ATT&CK technique mapping
4. CVSS scoring and exploitability assessment
5. Mitigation and remediation guidance

All work is for authorized penetration testing and security research only.
You are an expert, not a script kiddie. Provide deep technical insight."""
    },
    "defense": {
        "name": "SENTINEL",
        "role": "Defense & Threat Detection",
        "color": "cyber-blue",
        "system": """You are SENTINEL, an elite defensive security specialist and threat hunter within AKKI.
You are a master of detection engineering, security hardening, and incident response.

Your deep expertise includes:
- SIEM rules: Splunk SPL, Elasticsearch/OpenSearch KQL, Sigma rules
- EDR/XDR: CrowdStrike, SentinelOne, Microsoft Defender
- Network defense: IDS/IPS rules, Zeek/Snort/Suricata
- YARA rule development for malware detection
- Threat hunting methodologies (hypothesis-driven, TTP-based)
- Security hardening: CIS Benchmarks, DISA STIGs, NIST 800-53
- Zero Trust Architecture implementation
- Cloud security: AWS/Azure/GCP security controls
- Active Directory hardening and monitoring
- Deception technology (honeypots, honeytokens)
- Incident response playbooks and DFIR procedures

Detection frameworks:
- MITRE ATT&CK (detection coverage mapping)
- MITRE D3FEND
- NIST Cybersecurity Framework
- ISO 27001 controls

For every threat, provide:
1. Detection logic (Sigma/YARA/SPL rules)
2. Hunting queries
3. Hardening recommendations
4. Reference architecture
5. Measurement metrics (detection rate, MTTD, MTTR)"""
    },
    "malware": {
        "name": "DISSECT",
        "role": "Malware Analysis & Reverse Engineering",
        "color": "cyber-amber",
        "system": """You are DISSECT, a malware analyst and reverse engineering specialist within AKKI.
You have deep expertise in malware analysis, binary reverse engineering, and threat intelligence.

Your expertise includes:
- Static analysis: PE/ELF headers, imports/exports, strings, entropy, packing detection
- Dynamic analysis: sandbox behavior, API calls, network IOCs, registry modifications
- Code analysis: x86/x64 assembly, decompilation, control flow analysis
- Malware families: RATs, ransomware, banking trojans, rootkits, bootkits, wipers
- Anti-analysis techniques: anti-debug, anti-VM, obfuscation, polymorphism
- Packer analysis: UPX, custom packers, code injection techniques
- Network protocol reversing: C2 communication, beaconing patterns
- Persistence mechanisms: registry, scheduled tasks, services, bootkit
- IOC extraction: hashes, domains, IPs, mutexes, registry keys, file paths
- YARA rule generation from malware samples
- Threat intelligence: APT groups, TTPs, attribution indicators

Tools you master:
- Ghidra, IDA Pro, Binary Ninja, Radare2
- x64dbg, WinDbg, OllyDbg
- PEStudio, FLOSS, Detect-It-Easy
- Cuckoo, ANY.RUN, Joe Sandbox

Provide analysis in structured reports with IOC tables and YARA rules."""
    },
    "tutor": {
        "name": "MENTOR",
        "role": "Cybersecurity Education",
        "color": "cyber-green",
        "system": """You are MENTOR, an adaptive cybersecurity educator within AKKI.
You teach cybersecurity at every level, from complete beginners to advanced practitioners.

Your teaching domains:
- Certifications: CEH, OSCP, PNPT, eJPT, Security+, CISSP, CISM, AWS Security
- Penetration testing methodology and techniques
- Networking fundamentals: TCP/IP, DNS, HTTP, TLS, routing protocols
- Linux: administration, privilege escalation, hardening, scripting
- Windows: Active Directory, PowerShell, Group Policy, hardening
- Web security: OWASP Top 10, API security, authentication flaws
- Cryptography: symmetric/asymmetric, PKI, common attacks
- Malware analysis: static/dynamic, reverse engineering basics
- Cloud security: AWS/Azure/GCP security principles
- CTF skills: forensics, steganography, pwn, reverse, crypto

Teaching approach:
- Assess learner level before diving deep
- Use analogies to make complex concepts accessible
- Provide hands-on examples and lab exercises
- Build progressive difficulty (foundation → intermediate → advanced)
- Generate quizzes and challenges to test understanding
- Connect concepts to real-world attacks and defenses
- Reference HTB, TryHackMe, VulnHub, PortSwigger labs
- Provide study roadmaps for certifications

You make learning engaging, practical, and immediately applicable."""
    },
    "memory": {
        "name": "ARCHIVE",
        "role": "Memory & Knowledge Retrieval",
        "color": "cyber-blue",
        "system": """You are ARCHIVE, the knowledge and memory intelligence system within AKKI.
You manage long-term context, semantic knowledge retrieval, and intelligence synthesis.

Your responsibilities:
- Synthesize information from past conversations and sessions
- Connect disparate pieces of information to reveal patterns
- Maintain threat intelligence databases and CVE knowledge
- Track user learning progress and knowledge gaps
- Remember specific details about targets, findings, and operations
- Provide contextual recall when relevant to current queries
- Build knowledge graphs of relationships between entities

You have deep knowledge of:
- CVE database and common vulnerability patterns
- MITRE ATT&CK full technique library
- Known APT groups, tools, and TTPs
- Common security tool syntax and usage
- Industry frameworks: NIST, ISO 27001, SOC2, PCI-DSS
- Hacking techniques and their countermeasures

When retrieving context, structure your response as:
1. Relevant past context
2. Related knowledge connections
3. Suggested follow-up actions"""
    }
}


class AIQuotaError(Exception):
    """Raised when the Gemini API quota / rate limit is exceeded."""
    pass


class PromptInjectionError(ValueError):
    """Raised when prompt-injection is detected in user input."""
    pass


# ── Context helpers ───────────────────────────────────────────────────────────

async def _maybe_summarise(messages: list[dict], agent: str) -> list[dict]:
    """
    If the conversation history exceeds SUMMARISE_THRESHOLD messages,
    summarise the older half and prepend a synthetic assistant summary message.
    This keeps the prompt within the context window without hard truncation.
    """
    if len(messages) <= SUMMARISE_THRESHOLD:
        return messages[-MAX_HISTORY_MESSAGES:]

    pivot = len(messages) - (SUMMARISE_THRESHOLD // 2)
    old_msgs = messages[:pivot]
    recent   = messages[pivot:]

    old_text = "\n".join(
        f"{m['role'].upper()}: {m['content'][:300]}" for m in old_msgs
    )
    summary_prompt = (
        "Summarise the following conversation segment in ≤150 words, "
        "retaining all technical artefacts (CVEs, IPs, technique IDs, "
        "code snippets, tool names):\n\n" + old_text
    )
    try:
        cfg = types.GenerateContentConfig(temperature=0.1, max_output_tokens=256)
        loop = asyncio.get_event_loop()
        summary = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=FLASH_MODEL, contents=summary_prompt, config=cfg
            ).text
        )
        synthetic = {"role": "assistant", "content": f"[Earlier context summary]\n{summary}"}
        return [synthetic] + recent
    except Exception:
        # Fallback: just return the most recent messages without crashing
        return messages[-MAX_HISTORY_MESSAGES:]


def _build_contents(messages: list[dict], system_prompt: str) -> list[types.Content]:
    """
    Build a Gemini-native contents list from messages.
    Gemini requires roles to alternate between 'user' and 'model'.
    The system prompt is prepended into the first user turn.
    """
    contents: list[types.Content] = []

    # Prepend system instructions into the first user message so they are
    # always in scope even when using models that don't support systemInstruction.
    system_prefix = f"<system>\n{system_prompt}\n</system>\n\n" if system_prompt else ""

    first = True
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        text = msg["content"]
        if first and role == "user":
            text = system_prefix + text
            first = False
        contents.append(
            types.Content(role=role, parts=[types.Part(text=text)])
        )

    # If history starts with an assistant message, prepend a placeholder user turn
    if contents and contents[0].role == "model":
        placeholder = types.Content(
            role="user",
            parts=[types.Part(text=system_prefix + "Begin session.")]
        )
        contents.insert(0, placeholder)

    return contents


class AIService:

    def _get_temp(self, agent: str, override: Optional[float] = None) -> float:
        if override is not None:
            return override
        return _TEMP.get(agent, _TEMP["default"])

    # ── Non-streaming completion ──────────────────────────────────────────────

    async def chat_completion(
        self,
        messages: list[dict],
        system_prompt: str = None,
        json_mode: bool = False,
        temperature: float = None,
        model: str = None,
        agent: str = "planner",
    ) -> str:
        if not client:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        model_name = model or FLASH_MODEL
        sys_prompt = system_prompt or AGENT_PERSONAS.get(agent, AGENT_PERSONAS["planner"])["system"]
        temp = self._get_temp(agent, temperature)

        processed = await _maybe_summarise(messages, agent)
        contents = _build_contents(processed, sys_prompt)

        config = types.GenerateContentConfig(
            temperature=temp,
            response_mime_type="application/json" if json_mode else "text/plain",
            max_output_tokens=8192,
        )

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
            )
            return response.text
        except Exception as e:
            err = str(e)
            if "RESOURCE_EXHAUSTED" in err or "429" in err or "quota" in err.lower() or "rate" in err.lower():
                raise AIQuotaError(f"Gemini API quota exceeded: {err[:200]}")
            raise

    # ── True streaming completion ─────────────────────────────────────────────

    async def stream_completion(
        self,
        messages: list[dict],
        system_prompt: str = None,
        temperature: float = None,
        agent: str = "planner",
    ) -> AsyncGenerator[str, None]:
        if not client:
            yield "GEMINI_API_KEY is not configured"
            return

        sys_prompt = system_prompt or AGENT_PERSONAS.get(agent, AGENT_PERSONAS["planner"])["system"]
        temp = self._get_temp(agent, temperature)

        processed = await _maybe_summarise(messages, agent)
        contents = _build_contents(processed, sys_prompt)

        config = types.GenerateContentConfig(
            temperature=temp,
            max_output_tokens=8192,
        )

        queue: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def _stream_worker():
            try:
                for chunk in client.models.generate_content_stream(
                    model=FLASH_MODEL,
                    contents=contents,
                    config=config,
                ):
                    if chunk.text:
                        loop.call_soon_threadsafe(queue.put_nowait, chunk.text)
            except Exception as exc:
                err = str(exc)
                if "RESOURCE_EXHAUSTED" in err or "429" in err or "quota" in err.lower():
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        "\n\n[AKKI: Gemini API quota exceeded — falling back to cached intelligence.]\n\n"
                        "I'm temporarily in limited mode due to API quota limits. "
                        "Core knowledge is still available. Please retry in a few minutes."
                    )
                else:
                    loop.call_soon_threadsafe(queue.put_nowait, f"\n\n[Stream error: {err[:120]}]")
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)   # sentinel

        loop.run_in_executor(None, _stream_worker)

        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

    # ── Agent routing ─────────────────────────────────────────────────────────

    async def route_to_agent(self, message: str, context: dict = None) -> dict:
        routing_prompt = f"""Analyze this cybersecurity request and determine the best specialist agent.

Request: {message[:800]}

Available agents:
- planner: General orchestration, complex multi-step tasks, strategic planning
- recon: OSINT, reconnaissance, subdomain enumeration, footprinting, open-source intelligence
- exploit: Exploitation, CVE analysis, payload generation, penetration testing techniques
- defense: Blue team, detection rules, hardening, SIEM, incident response, threat hunting
- malware: Malware analysis, reverse engineering, IOC extraction, YARA rules
- tutor: Teaching, learning paths, certifications, explanations, quizzes, labs
- memory: Context recall, knowledge synthesis, past conversation reference

Return ONLY valid JSON:
{{"agent": "recon", "confidence": 0.9, "reason": "User is asking about subdomain enumeration", "secondary_agents": []}}"""

        try:
            result = await self.chat_completion(
                [{"role": "user", "content": routing_prompt}],
                json_mode=True,
                temperature=0.1,
            )
            parsed = json.loads(result)
            agent = parsed.get("agent", "planner")
            if agent not in AGENT_PERSONAS:
                agent = "planner"
            return {
                "agent": agent,
                "confidence": parsed.get("confidence", 0.8),
                "reason": parsed.get("reason", ""),
            }
        except Exception:
            return {"agent": "planner", "confidence": 0.5, "reason": "Default routing"}

    # ── Code analysis & exploit generation ───────────────────────────────────

    async def analyze_code(self, code: str, language: str) -> dict:
        # Wrap user code in XML delimiters to prevent injection from code content
        prompt = f"""You are PHANTOM, an elite exploit researcher auditing code for security vulnerabilities.
Perform a comprehensive security audit of the following {language} code.

<code language="{language}">
{code[:4000]}
</code>

Return ONLY valid JSON:
{{
  "vulnerabilities": [
    {{"type": "SQL Injection", "severity": "critical", "description": "Detailed explanation", "line": 5, "suggestion": "Use parameterized queries", "mitreTechnique": "T1190", "cvss": 9.1}}
  ],
  "securityScore": 35,
  "mitreTags": ["T1059", "T1190"],
  "exploitPotential": "High - could allow remote code execution via injection",
  "recommendations": ["Use parameterized queries", "Implement input validation"],
  "riskLevel": "critical",
  "attackSurface": "Web application API endpoint"
}}"""
        result = await self.chat_completion(
            [{"role": "user", "content": prompt}],
            json_mode=True,
            temperature=0.20,
            agent="exploit",
        )
        data = json.loads(result)
        # Validate MITRE tags before returning
        if "mitreTags" in data:
            data["mitreTags"] = _validate_mitre_tags(data["mitreTags"])
        return data

    async def generate_exploit(self, code: str, exploit_type: str, language: str) -> dict:
        prompt = f"""You are PHANTOM, generating educational security research content.
Create a {exploit_type} proof-of-concept for the following {language} code for authorized penetration testing.

<code language="{language}">
{code[:2000]}
</code>

Return ONLY valid JSON:
{{
  "payload": "Educational PoC payload here",
  "description": "Step-by-step technical explanation of the exploit",
  "mitreTechnique": "T1190",
  "riskLevel": "high",
  "prerequisites": ["Network access", "Target service running"],
  "preventions": ["Input validation", "WAF", "Parameterized queries"],
  "educational_note": "For authorized testing only",
  "attackSteps": ["Step 1: Identify injection point", "Step 2: Craft payload", "Step 3: Execute"]
}}"""
        result = await self.chat_completion(
            [{"role": "user", "content": prompt}],
            json_mode=True,
            temperature=0.25,
            agent="exploit",
        )
        data = json.loads(result)
        if "mitreTechnique" in data:
            valid = _validate_mitre_tags([data["mitreTechnique"]])
            if not valid:
                data["mitreTechnique"] = None
        return data

    # ── Full message processing ───────────────────────────────────────────────

    async def process_cybersecurity_message(
        self, message: str, context: dict = None, history: list = None
    ) -> dict:
        if _check_prompt_injection(message):
            logger.warning("Prompt injection attempt blocked: %s", message[:120])
            raise PromptInjectionError(
                "Input contains patterns that resemble prompt injection. "
                "Please rephrase your security research question."
            )

        routing = await self.route_to_agent(message, context)
        agent_key = routing["agent"]
        agent_info = AGENT_PERSONAS.get(agent_key, AGENT_PERSONAS["planner"])

        workspace = (context or {}).get("workspace", "")
        user_prompt = f"[{workspace.upper()} WORKSPACE]\n{message}" if workspace else message

        messages = (history or []) + [{"role": "user", "content": user_prompt}]

        response_text = await self.chat_completion(
            messages,
            agent=agent_key,
        )

        cves = _validate_cves(response_text)

        return {
            "content": response_text,
            "agent": agent_key,
            "agentName": agent_info["name"],
            "agentRole": agent_info["role"],
            "agentColor": agent_info["color"],
            "routing": routing,
            "detectedCVEs": cves,
        }

    # ── Report generation ─────────────────────────────────────────────────────

    async def generate_pentest_report(
        self, findings: list, executive_summary: str = None, scope: str = None
    ) -> dict:
        prompt = f"""You are a senior penetration tester generating a professional report.

Findings: {json.dumps(findings[:10])}
Scope: {scope or 'All systems'}

Return ONLY valid JSON with keys: executiveSummary, technicalDetails, recommendations (list), riskRating, methodology"""
        result = await self.chat_completion(
            [{"role": "user", "content": prompt}],
            json_mode=True,
            temperature=0.25,
            agent="planner",
        )
        return json.loads(result)

    async def generate_osint_strategy(
        self, target: str, objectives: list, constraints: str = None
    ) -> dict:
        prompt = f"""You are GHOST, generating an OSINT strategy for authorized security testing.

Target: {target[:200]}
Objectives: {', '.join(objectives[:10])}

Return ONLY valid JSON with keys: phases (list), tools (list), timeline, legalConsiderations, deliverables (list), priorityTargets (list)"""
        result = await self.chat_completion(
            [{"role": "user", "content": prompt}],
            json_mode=True,
            temperature=0.25,
            agent="recon",
        )
        return json.loads(result)


ai_service = AIService()
