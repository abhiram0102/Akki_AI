import os
import json
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

FLASH_MODEL = "gemini-2.0-flash"
PRO_MODEL = "gemini-2.0-flash"


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
    ) -> str:
        if not client:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        model_name = model or FLASH_MODEL
        last_message = messages[-1]["content"] if messages else ""

        if system_prompt:
            prompt = f"System Instructions: {system_prompt}\n\nUser: {last_message}"
        else:
            prompt = last_message

        config = types.GenerateContentConfig(
            temperature=temperature,
            response_mime_type="application/json" if json_mode else "text/plain",
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

    async def analyze_code(self, code: str, language: str) -> dict:
        prompt = f"""You are a cybersecurity expert. Analyze this {language} code for security vulnerabilities.

```{language}
{code}
```

Return ONLY valid JSON in this exact format:
{{
  "vulnerabilities": [
    {{"type": "SQL Injection", "severity": "high", "description": "User input not sanitized", "line": 5, "suggestion": "Use parameterized queries"}}
  ],
  "securityScore": 65,
  "mitreTags": ["T1059"],
  "exploitPotential": "Could allow data exfiltration",
  "recommendations": ["Input validation", "Least privilege"]
}}"""
        result = await self.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.2)
        return json.loads(result)

    async def generate_exploit(self, code: str, exploit_type: str, language: str) -> dict:
        prompt = f"""You are an ethical security researcher. Generate an educational {exploit_type} PoC for this {language} code.

```{language}
{code}
```

Return ONLY valid JSON:
{{
  "payload": "example payload here",
  "description": "How this exploit works",
  "mitreTechnique": "T1190",
  "riskLevel": "high",
  "preventions": ["Input validation", "WAF"],
  "educational_note": "For authorized testing only"
}}"""
        result = await self.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.3)
        return json.loads(result)

    async def generate_pentest_report(self, findings: list, executive_summary: str = None, scope: str = None) -> dict:
        prompt = f"""Generate a professional penetration testing report.

Findings: {json.dumps(findings[:10])}
Scope: {scope or 'All systems'}

Return ONLY valid JSON with keys: executiveSummary, technicalDetails, recommendations (list), riskRating, methodology"""
        result = await self.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.3)
        return json.loads(result)

    async def generate_osint_strategy(self, target: str, objectives: list, constraints: str = None) -> dict:
        prompt = f"""Generate an OSINT strategy for authorized security testing.

Target: {target}
Objectives: {', '.join(objectives)}

Return ONLY valid JSON with keys: phases (list), tools (list), timeline, legalConsiderations, deliverables (list)"""
        result = await self.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.3)
        return json.loads(result)

    async def generate_exploit_poc(self, vulnerability: str, target: str, constraints: str = None) -> dict:
        prompt = f"""Generate an educational exploit PoC for authorized penetration testing.

Vulnerability: {vulnerability}
Target: {target}

Return ONLY valid JSON with keys: payload, description, prerequisites (list), mitigations (list), educationalNotes"""
        result = await self.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.3)
        return json.loads(result)

    async def process_cybersecurity_message(self, message: str, context: dict = None) -> str:
        system = """You are AMMU AI, an advanced cybersecurity AI assistant and red team specialist.
You help security professionals with:
- Penetration testing and red team operations
- Vulnerability analysis and security code review
- OSINT and reconnaissance techniques
- Security assessment and reporting
- Blue team defense and incident response
- MITRE ATT&CK framework mapping

Always provide professional, educational guidance. Remind users that all testing must be on authorized systems only."""

        workspace = context.get("workspace", "") if context else ""
        user_prompt = f"[{workspace.upper()} WORKSPACE]\n{message}" if workspace else message

        return await self.chat_completion(
            [{"role": "user", "content": user_prompt}],
            system_prompt=system,
            temperature=0.7,
        )


ai_service = AIService()
