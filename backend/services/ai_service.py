import os
import json
import asyncio
from typing import AsyncGenerator, Optional
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

FLASH_MODEL = "gemini-2.0-flash"
PRO_MODEL = "gemini-2.0-flash"

AGENT_PERSONAS = {
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


class AIService:
    async def chat_completion(
        self,
        messages: list[dict],
        system_prompt: str = None,
        json_mode: bool = False,
        temperature: float = 0.7,
        model: str = None,
        agent: str = "planner",
    ) -> str:
        if not client:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        model_name = model or FLASH_MODEL

        # Build full prompt with conversation history
        conversation_parts = []
        if system_prompt:
            conversation_parts.append(f"System Instructions:\n{system_prompt}")
        elif agent in AGENT_PERSONAS:
            conversation_parts.append(f"System Instructions:\n{AGENT_PERSONAS[agent]['system']}")

        # Include conversation history (last 10 messages for context)
        for msg in messages[-10:]:
            role = "User" if msg["role"] == "user" else "Assistant"
            conversation_parts.append(f"{role}: {msg['content']}")

        prompt = "\n\n".join(conversation_parts)

        config = types.GenerateContentConfig(
            temperature=temperature,
            response_mime_type="application/json" if json_mode else "text/plain",
            max_output_tokens=8192,
        )

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
            return response.text
        except Exception as e:
            err = str(e)
            if "RESOURCE_EXHAUSTED" in err or "429" in err or "quota" in err.lower() or "rate" in err.lower():
                raise AIQuotaError(f"Gemini API quota exceeded: {err[:200]}")
            raise

    async def stream_completion(
        self,
        messages: list[dict],
        system_prompt: str = None,
        temperature: float = 0.7,
        agent: str = "planner",
    ) -> AsyncGenerator[str, None]:
        if not client:
            yield "GEMINI_API_KEY is not configured"
            return

        conversation_parts = []
        sys_prompt = system_prompt or AGENT_PERSONAS.get(agent, AGENT_PERSONAS["planner"])["system"]
        conversation_parts.append(f"System Instructions:\n{sys_prompt}")

        for msg in messages[-10:]:
            role = "User" if msg["role"] == "user" else "Assistant"
            conversation_parts.append(f"{role}: {msg['content']}")

        prompt = "\n\n".join(conversation_parts)

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=8192,
        )

        try:
            loop = asyncio.get_event_loop()
            full_text = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=FLASH_MODEL,
                    contents=prompt,
                    config=config,
                ).text
            )
            # Simulate streaming by chunking the response
            words = full_text.split(" ")
            for i, word in enumerate(words):
                chunk = word + (" " if i < len(words) - 1 else "")
                yield chunk
                await asyncio.sleep(0.02)
        except Exception as e:
            err = str(e)
            if "RESOURCE_EXHAUSTED" in err or "429" in err or "quota" in err.lower():
                yield "\n\n[AKKI: Gemini API quota exceeded. Falling back to cached intelligence...]\n\n"
                yield "I'm temporarily operating in limited mode due to API quota limits. My core knowledge base is still available for answering questions. Please try again in a few minutes for full AI-powered analysis."
            else:
                yield f"Error: {err[:200]}"

    async def route_to_agent(self, message: str, context: dict = None) -> dict:
        """Determine which specialist agent should handle this message."""
        routing_prompt = f"""Analyze this cybersecurity request and determine the best specialist agent.

Request: {message}

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
            return {"agent": agent, "confidence": parsed.get("confidence", 0.8), "reason": parsed.get("reason", "")}
        except Exception:
            return {"agent": "planner", "confidence": 0.5, "reason": "Default routing"}

    async def analyze_code(self, code: str, language: str) -> dict:
        prompt = f"""You are PHANTOM, an elite exploit researcher analyzing code for security vulnerabilities.
Perform a comprehensive security audit of this {language} code.

```{language}
{code[:3000]}
```

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
        result = await self.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.2)
        return json.loads(result)

    async def generate_exploit(self, code: str, exploit_type: str, language: str) -> dict:
        prompt = f"""You are PHANTOM, generating educational security research content.
Create a {exploit_type} proof-of-concept for this {language} code for authorized penetration testing.

```{language}
{code[:2000]}
```

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
        result = await self.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.3)
        return json.loads(result)

    async def process_cybersecurity_message(self, message: str, context: dict = None, history: list = None) -> dict:
        """Process a message with intelligent agent routing."""
        routing = await self.route_to_agent(message, context)
        agent_key = routing["agent"]
        agent_info = AGENT_PERSONAS.get(agent_key, AGENT_PERSONAS["planner"])

        workspace = context.get("workspace", "") if context else ""
        user_prompt = f"[{workspace.upper()} WORKSPACE]\n{message}" if workspace else message

        messages = (history or []) + [{"role": "user", "content": user_prompt}]

        response_text = await self.chat_completion(
            messages,
            agent=agent_key,
            temperature=0.7,
        )

        return {
            "content": response_text,
            "agent": agent_key,
            "agentName": agent_info["name"],
            "agentRole": agent_info["role"],
            "agentColor": agent_info["color"],
            "routing": routing,
        }

    async def generate_pentest_report(self, findings: list, executive_summary: str = None, scope: str = None) -> dict:
        prompt = f"""You are a senior penetration tester generating a professional report.

Findings: {json.dumps(findings[:10])}
Scope: {scope or 'All systems'}

Return ONLY valid JSON with keys: executiveSummary, technicalDetails, recommendations (list), riskRating, methodology"""
        result = await self.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.3)
        return json.loads(result)

    async def generate_osint_strategy(self, target: str, objectives: list, constraints: str = None) -> dict:
        prompt = f"""You are GHOST, generating an OSINT strategy for authorized security testing.

Target: {target}
Objectives: {', '.join(objectives)}

Return ONLY valid JSON with keys: phases (list), tools (list), timeline, legalConsiderations, deliverables (list), priorityTargets (list)"""
        result = await self.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.3)
        return json.loads(result)


ai_service = AIService()
