"""
AKKI Cybersecurity Tutoring Engine (MENTOR Agent)
Adaptive learning, progress tracking, quiz generation, and curriculum management.
"""
import json
from backend.services.ai_service import ai_service, AIQuotaError

LEARNING_PATHS = {
    "beginner": {
        "title": "Cybersecurity Foundations",
        "description": "Start your journey from zero to security-aware",
        "modules": [
            {"id": "net-basics", "title": "Networking Fundamentals", "topics": ["TCP/IP", "DNS", "HTTP/HTTPS", "Firewalls", "VPNs"], "difficulty": 1},
            {"id": "linux-basics", "title": "Linux for Security", "topics": ["CLI basics", "File permissions", "Processes", "Networking tools"], "difficulty": 1},
            {"id": "sec-concepts", "title": "Security Concepts", "topics": ["CIA Triad", "Authentication", "Encryption basics", "Common threats"], "difficulty": 2},
            {"id": "web-basics", "title": "Web Security Basics", "topics": ["HTTP methods", "Cookies/Sessions", "OWASP Top 10 intro"], "difficulty": 2},
        ]
    },
    "intermediate": {
        "title": "Security Practitioner",
        "description": "Build hands-on penetration testing skills",
        "modules": [
            {"id": "pentest-methodology", "title": "Penetration Testing Methodology", "topics": ["PTES", "Scoping", "Rules of Engagement", "Reporting"], "difficulty": 3},
            {"id": "web-exploitation", "title": "Web Application Exploitation", "topics": ["SQLi", "XSS", "SSRF", "Command Injection", "IDOR"], "difficulty": 3},
            {"id": "network-attacks", "title": "Network Attack Techniques", "topics": ["MITM", "ARP spoofing", "Sniffing", "Port scanning"], "difficulty": 3},
            {"id": "linux-privesc", "title": "Linux Privilege Escalation", "topics": ["SUID/SGID", "Sudo abuse", "Cron jobs", "Kernel exploits"], "difficulty": 4},
            {"id": "active-directory", "title": "Active Directory Attacks", "topics": ["Enumeration", "Kerberoasting", "AS-REP Roasting", "Pass-the-Hash"], "difficulty": 4},
        ]
    },
    "advanced": {
        "title": "Elite Operator",
        "description": "Master offensive and defensive security at expert level",
        "modules": [
            {"id": "exploit-dev", "title": "Exploit Development", "topics": ["Buffer overflow", "ROP chains", "Heap exploitation", "Format string bugs"], "difficulty": 5},
            {"id": "malware-analysis", "title": "Malware Analysis & RE", "topics": ["Static analysis", "Dynamic analysis", "Assembly", "Unpacking"], "difficulty": 5},
            {"id": "red-team-ops", "title": "Red Team Operations", "topics": ["C2 frameworks", "AV evasion", "Persistence", "Lateral movement"], "difficulty": 5},
            {"id": "threat-hunting", "title": "Threat Hunting & DFIR", "topics": ["Hypothesis-driven hunting", "Log analysis", "Memory forensics", "Timeline analysis"], "difficulty": 5},
        ]
    },
    "certifications": {
        "title": "Certification Prep",
        "description": "Targeted preparation for security certifications",
        "modules": [
            {"id": "comptia-sec", "title": "CompTIA Security+", "topics": ["Threats & Attacks", "PKI", "Network Security", "Compliance"], "difficulty": 2},
            {"id": "ejpt", "title": "eJPT (eLearnSecurity)", "topics": ["Host discovery", "Web attacks", "Metasploit", "Pivoting"], "difficulty": 3},
            {"id": "pnpt", "title": "PNPT (TCM Security)", "topics": ["Active Directory", "OSINT", "Post-exploitation", "Report writing"], "difficulty": 4},
            {"id": "oscp", "title": "OSCP (OffSec)", "topics": ["Buffer overflow", "Web exploitation", "AD attacks", "Pivoting", "Report"], "difficulty": 5},
        ]
    }
}

QUIZ_BANK = {
    "networking": [
        {"q": "What port does HTTPS use by default?", "a": "443", "options": ["80", "443", "8080", "8443"], "difficulty": 1},
        {"q": "What does DNS stand for?", "a": "Domain Name System", "options": ["Domain Name System", "Dynamic Network Service", "Data Network Standard", "Domain Network Security"], "difficulty": 1},
        {"q": "What protocol does Ping use?", "a": "ICMP", "options": ["TCP", "UDP", "ICMP", "ARP"], "difficulty": 2},
        {"q": "What is a SYN flood attack?", "a": "A DoS attack exploiting TCP handshake", "options": ["A DoS attack exploiting TCP handshake", "A DNS cache poisoning attack", "A brute force attack", "A SQL injection variant"], "difficulty": 3},
    ],
    "web_security": [
        {"q": "Which OWASP Top 10 category covers SQL Injection?", "a": "Injection", "options": ["Injection", "Broken Access Control", "XSS", "Insecure Design"], "difficulty": 2},
        {"q": "What HTTP header prevents clickjacking?", "a": "X-Frame-Options", "options": ["X-Frame-Options", "Content-Security-Policy", "HSTS", "X-XSS-Protection"], "difficulty": 2},
        {"q": "SSRF allows an attacker to...", "a": "Make the server send requests to internal resources", "options": ["Make the server send requests to internal resources", "Steal session cookies", "Inject SQL code", "Execute JavaScript"], "difficulty": 3},
    ],
    "linux_privesc": [
        {"q": "What does SUID permission allow?", "a": "Execute file as the file owner", "options": ["Execute file as the file owner", "Read-only access to root files", "Network socket binding", "Process killing"], "difficulty": 3},
        {"q": "Which command finds SUID files?", "a": "find / -perm -4000", "options": ["find / -perm -4000", "ls -la /", "ps aux", "netstat -tlpn"], "difficulty": 3},
        {"q": "What is /etc/passwd vs /etc/shadow?", "a": "/etc/shadow stores hashed passwords", "options": ["/etc/shadow stores hashed passwords", "/etc/passwd stores hashed passwords", "Both store passwords", "Neither stores passwords"], "difficulty": 2},
    ],
    "active_directory": [
        {"q": "What is Kerberoasting?", "a": "Requesting TGS tickets to crack service account passwords offline", "options": ["Requesting TGS tickets to crack service account passwords offline", "Exploiting Kerberos pre-authentication", "Forging Kerberos tickets", "Brute forcing domain accounts"], "difficulty": 4},
        {"q": "What is a Golden Ticket attack?", "a": "Forging TGT using KRBTGT account hash", "options": ["Forging TGT using KRBTGT account hash", "Pass-the-Hash with admin credentials", "Kerberoasting all service accounts", "DCSync attack"], "difficulty": 5},
    ],
}


class TutorService:
    async def get_learning_paths(self) -> dict:
        return LEARNING_PATHS

    async def get_quiz(self, topic: str, difficulty: int = None) -> dict:
        """Generate or retrieve quiz questions for a topic."""
        questions = QUIZ_BANK.get(topic.lower().replace(" ", "_"), [])

        if not questions:
            # Generate AI-powered quiz
            try:
                prompt = f"""Generate 5 multiple-choice cybersecurity quiz questions about: {topic}
Difficulty level: {difficulty or 3}/5 (1=beginner, 5=expert)

Return ONLY valid JSON:
{{
  "questions": [
    {{
      "q": "Question text",
      "a": "Correct answer",
      "options": ["Correct answer", "Wrong 1", "Wrong 2", "Wrong 3"],
      "explanation": "Why this is correct",
      "difficulty": 3,
      "topic": "{topic}"
    }}
  ]
}}"""
                result = await ai_service.chat_completion(
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                    temperature=0.4,
                )
                data = json.loads(result)
                return {"topic": topic, "questions": data.get("questions", []), "source": "ai-generated"}
            except AIQuotaError:
                return {
                    "topic": topic,
                    "questions": QUIZ_BANK.get("networking", [])[:3],
                    "source": "cached",
                    "note": "Using cached questions - AI quota exceeded"
                }
            except Exception as e:
                return {"topic": topic, "questions": [], "error": str(e)}

        filtered = questions
        if difficulty:
            filtered = [q for q in questions if abs(q.get("difficulty", 3) - difficulty) <= 1]
        filtered = filtered or questions

        return {"topic": topic, "questions": filtered, "source": "bank"}

    async def generate_learning_path(self, goals: str, current_level: str = "beginner") -> dict:
        """Generate a personalized learning path based on goals."""
        try:
            prompt = f"""Create a personalized cybersecurity learning roadmap.

Student Goals: {goals}
Current Level: {current_level}

Return ONLY valid JSON:
{{
  "title": "Your Personalized Path",
  "estimatedTime": "3-6 months",
  "phases": [
    {{
      "phase": 1,
      "title": "Foundation",
      "weeks": 4,
      "topics": ["Topic 1", "Topic 2"],
      "resources": ["Resource 1"],
      "milestone": "Complete milestone"
    }}
  ],
  "certifications": ["Recommended cert 1"],
  "tools": ["Tool 1", "Tool 2"],
  "practiceResources": ["HackTheBox", "TryHackMe", "PortSwigger Labs"]
}}"""
            result = await ai_service.chat_completion(
                [{"role": "user", "content": prompt}],
                json_mode=True,
                temperature=0.5,
            )
            return json.loads(result)
        except AIQuotaError:
            level_path = LEARNING_PATHS.get(current_level, LEARNING_PATHS["beginner"])
            return {
                "title": f"Standard {current_level.title()} Path",
                "estimatedTime": "3-6 months",
                "phases": [
                    {
                        "phase": i + 1,
                        "title": m["title"],
                        "weeks": 3,
                        "topics": m["topics"],
                        "resources": ["HackTheBox", "TryHackMe"],
                        "milestone": f"Complete {m['title']}"
                    }
                    for i, m in enumerate(level_path["modules"])
                ],
                "certifications": ["CompTIA Security+", "eJPT"],
                "tools": ["Nmap", "Burp Suite", "Metasploit", "Wireshark"],
                "practiceResources": ["HackTheBox", "TryHackMe", "PortSwigger Web Security Academy"],
                "note": "Standard path - AI personalization requires Gemini quota"
            }

    async def explain_topic(self, topic: str, level: str = "intermediate") -> str:
        """Generate a detailed explanation of a cybersecurity topic."""
        try:
            prompt = f"""You are MENTOR, an expert cybersecurity educator.

Explain this topic in depth for a {level} level student: {topic}

Include:
1. What it is and why it matters
2. How it works (technical details appropriate for level)
3. Real-world examples or attack scenarios
4. How to detect or defend against it (if attack technique)
5. Hands-on practice recommendations
6. Key takeaways

Use clear headers, bullet points, and code examples where helpful."""

            return await ai_service.chat_completion(
                [{"role": "user", "content": prompt}],
                agent="tutor",
                temperature=0.6,
            )
        except AIQuotaError:
            return f"""**MENTOR — {topic.upper()} OVERVIEW** *(Cached Mode)*

**What is {topic}?**
{topic} is an important cybersecurity concept that security professionals must understand.

**Key Points:**
- This topic is covered in depth in CEH, OSCP, and Security+ certifications
- Hands-on practice is available at HackTheBox and TryHackMe
- The MITRE ATT&CK framework documents related techniques

**Recommended Resources:**
- PortSwigger Web Security Academy (free)
- TryHackMe - {topic} learning paths
- HackTheBox Academy

*Full AI explanation available when Gemini quota resets.*"""

    async def generate_challenge(self, topic: str, difficulty: int = 3) -> dict:
        """Generate a practical security challenge."""
        try:
            prompt = f"""Create a hands-on cybersecurity challenge.

Topic: {topic}
Difficulty: {difficulty}/5

Return ONLY valid JSON:
{{
  "title": "Challenge title",
  "scenario": "Realistic scenario description",
  "objective": "What the student must accomplish",
  "hints": ["Hint 1", "Hint 2", "Hint 3"],
  "tools": ["Required tool 1", "Required tool 2"],
  "steps": ["Step 1", "Step 2", "Step 3"],
  "solution": "High-level solution approach",
  "learningObjectives": ["Learning objective 1", "Learning objective 2"],
  "estimatedTime": "30-45 minutes",
  "difficulty": {difficulty}
}}"""
            result = await ai_service.chat_completion(
                [{"role": "user", "content": prompt}],
                json_mode=True,
                temperature=0.6,
            )
            return json.loads(result)
        except AIQuotaError:
            return {
                "title": f"{topic} Challenge",
                "scenario": f"You are a penetration tester tasked with demonstrating {topic} vulnerabilities on an authorized test system.",
                "objective": f"Successfully exploit a {topic} vulnerability and document your findings.",
                "hints": ["Start with reconnaissance", "Check documentation for known techniques", "Document all findings"],
                "tools": ["Burp Suite", "Nmap", "Metasploit"],
                "steps": ["Enumerate target", "Identify vulnerability", "Develop exploit", "Document findings", "Write report"],
                "solution": f"Research {topic} techniques on PortSwigger Academy or HackTheBox",
                "learningObjectives": [f"Understand how {topic} works", "Practice responsible disclosure"],
                "estimatedTime": "60-90 minutes",
                "difficulty": difficulty,
                "note": "Full AI challenge generation requires Gemini quota"
            }


tutor_service = TutorService()
