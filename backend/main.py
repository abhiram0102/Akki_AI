import os
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, update

from backend.database import get_db, init_db
from backend.models import User, Session, Message, Document, Memory, ToolRun, Finding, VoiceInteraction
from backend.auth import hash_password, verify_password, create_access_token, get_current_user
from backend.services.ai_service import ai_service
from backend.services.agent_service import agent_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="AMMU AI Cybersecurity Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    confirmPassword: str
    role: str = "analyst"

class LoginRequest(BaseModel):
    email: str
    password: str

class ChatMessageRequest(BaseModel):
    content: str
    sessionId: Optional[str] = None
    voiceInput: bool = False
    emotionalTone: Optional[str] = None

class ProfileUpdateRequest(BaseModel):
    username: Optional[str] = None
    preferences: Optional[dict] = None
    emotionalState: Optional[dict] = None

class CodeAnalysisRequest(BaseModel):
    code: str
    language: str = "javascript"

class ExploitGenerationRequest(BaseModel):
    code: str
    exploitType: str = "injection"
    language: str = "javascript"

class SimulationRequest(BaseModel):
    target: str
    attackType: str
    name: str

class CampaignRequest(BaseModel):
    name: str
    template: str
    targets: List[str]

class ChainGenerationRequest(BaseModel):
    target: str
    objective: str

class DomainOSINTRequest(BaseModel):
    domain: str

class GitHubOSINTRequest(BaseModel):
    target: str

class ShodanRequest(BaseModel):
    query: str

class ReportGenerationRequest(BaseModel):
    title: str
    type: str = "technical"
    template: Optional[str] = None
    sections: Optional[List[str]] = None

class ToolExecutionRequest(BaseModel):
    toolName: str
    arguments: dict
    sessionId: str
    requiresApproval: bool = False

class ExploitPoCRequest(BaseModel):
    vulnerability: str
    target: str
    constraints: Optional[str] = None

class OSINTStrategyRequest(BaseModel):
    target: str
    objectives: List[str]
    constraints: Optional[str] = None

class ReportFindingsRequest(BaseModel):
    findings: List[dict]
    executiveSummary: Optional[str] = None
    scope: Optional[str] = None


def user_to_dict(user: User, include_password: bool = False) -> dict:
    d = {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "role": user.role,
        "preferences": user.preferences or {},
        "emotionalState": user.emotional_state or {},
        "createdAt": user.created_at.isoformat() if user.created_at else None,
        "lastActiveAt": user.last_active_at.isoformat() if user.last_active_at else None,
    }
    if include_password:
        d["password"] = user.password
    return d


def session_to_dict(s: Session) -> dict:
    return {
        "id": s.id,
        "ownerId": s.owner_id,
        "title": s.title,
        "mode": s.mode,
        "context": s.context or {},
        "startedAt": s.started_at.isoformat() if s.started_at else None,
        "endedAt": s.ended_at.isoformat() if s.ended_at else None,
    }


def message_to_dict(m: Message) -> dict:
    return {
        "id": m.id,
        "sessionId": m.session_id,
        "role": m.role,
        "content": m.content,
        "toolCalls": m.tool_calls or [],
        "metadata": m.metadata_ or {},
        "createdAt": m.created_at.isoformat() if m.created_at else None,
    }


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.post("/api/auth/register")
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if body.password != body.confirmPassword:
        raise HTTPException(status_code=400, detail="Passwords don't match")

    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User already exists")

    user = User(
        id=str(uuid.uuid4()),
        email=body.email,
        username=body.username,
        password=hash_password(body.password),
        role=body.role,
        preferences={},
        emotional_state={
            "bondLevel": 0,
            "currentMood": "neutral",
            "trustLevel": 0.5,
            "personalityTraits": [],
            "preferredCommunicationStyle": "professional",
        },
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id, user.role)
    return {"user": user_to_dict(user), "token": token}


@app.post("/api/auth/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user.last_active_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id, user.role)
    return {"user": user_to_dict(user), "token": token}


# ── Profile ───────────────────────────────────────────────────────────────────

@app.get("/api/protected/profile")
async def get_profile(current_user: User = Depends(get_current_user)):
    return user_to_dict(current_user)


@app.put("/api/protected/profile")
async def update_profile(
    body: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.username:
        current_user.username = body.username
    if body.preferences is not None:
        current_user.preferences = body.preferences
    if body.emotionalState is not None:
        current_user.emotional_state = body.emotionalState
    await db.commit()
    await db.refresh(current_user)
    return user_to_dict(current_user)


# ── Sessions ──────────────────────────────────────────────────────────────────

@app.get("/api/protected/sessions")
async def get_sessions(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Session)
        .where(Session.owner_id == current_user.id)
        .order_by(desc(Session.started_at))
        .limit(limit)
    )
    sessions = result.scalars().all()
    return [session_to_dict(s) for s in sessions]


@app.get("/api/protected/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(desc(Message.created_at))
        .limit(limit)
    )
    messages = result.scalars().all()
    return [message_to_dict(m) for m in reversed(messages)]


# ── Chat ──────────────────────────────────────────────────────────────────────

@app.post("/api/protected/chat/message")
async def chat_message(
    body: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session_id = body.sessionId

    if not session_id:
        new_session = Session(
            id=str(uuid.uuid4()),
            owner_id=current_user.id,
            title=f"Chat Session - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            mode="chat",
            context={"workspace": "chat"},
        )
        db.add(new_session)
        await db.commit()
        await db.refresh(new_session)
        session_id = new_session.id

    user_msg = Message(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role="user",
        content=body.content,
        tool_calls=[],
        metadata_={"voiceInput": body.voiceInput, "emotionalTone": body.emotionalTone},
    )
    db.add(user_msg)
    await db.commit()

    try:
        agent_response = await agent_service.process_message(
            message=body.content,
            session_id=session_id,
            user_id=current_user.id,
            voice_input=body.voiceInput,
            context={"emotionalTone": body.emotionalTone, "workspace": "chat"},
        )
    except Exception as e:
        agent_response = {
            "content": "I encountered an issue processing your request. Please try again.",
            "toolCalls": [],
            "ragUsed": False,
            "sources": [],
            "emotionalTone": "neutral",
        }

    assistant_msg = Message(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role="assistant",
        content=agent_response["content"],
        tool_calls=agent_response.get("toolCalls", []),
        metadata_={
            "ragUsed": agent_response.get("ragUsed", False),
            "sources": agent_response.get("sources", []),
            "emotionalTone": agent_response.get("emotionalTone"),
        },
    )
    db.add(assistant_msg)
    await db.commit()
    await db.refresh(user_msg)
    await db.refresh(assistant_msg)

    return {
        "userMessage": message_to_dict(user_msg),
        "assistantMessage": message_to_dict(assistant_msg),
        "sessionId": session_id,
        "agentPlan": agent_response.get("plan"),
    }


# ── Voice ─────────────────────────────────────────────────────────────────────

@app.post("/api/protected/voice/transcribe")
async def voice_transcribe(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" in content_type:
            form = await request.form()
            audio_data = str(form.get("audioData", ""))
        else:
            body = await request.json()
            audio_data = body.get("audioData", "")

        interaction = VoiceInteraction(
            id=str(uuid.uuid4()),
            session_id="",
            user_id=current_user.id,
            transcription="Voice transcription processed",
            audio_data=audio_data[:100] if audio_data else None,
            confidence=0.95,
            emotional_tone="neutral",
            wake_word_detected=False,
        )
        db.add(interaction)
        await db.commit()
        await db.refresh(interaction)

        return {
            "id": interaction.id,
            "transcription": interaction.transcription,
            "emotionalTone": interaction.emotional_tone,
            "confidence": interaction.confidence,
            "wakeWordDetected": interaction.wake_word_detected,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/protected/voice/synthesize")
async def voice_synthesize(request: Request, current_user: User = Depends(get_current_user)):
    body = await request.json()
    return {"audioData": None, "text": body.get("text", ""), "status": "synthesized"}


# ── Memory ────────────────────────────────────────────────────────────────────

@app.get("/api/protected/memory")
async def get_memory(
    type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Memory).where(Memory.user_id == current_user.id)
    if type:
        q = q.where(Memory.type == type)
    result = await db.execute(q.order_by(desc(Memory.last_accessed_at)))
    memories = result.scalars().all()
    return [
        {
            "id": m.id,
            "type": m.type,
            "content": m.content,
            "strength": m.strength,
            "createdAt": m.created_at.isoformat() if m.created_at else None,
        }
        for m in memories
    ]


# ── Multi-modal analysis ──────────────────────────────────────────────────────

@app.post("/api/protected/analysis/multimodal")
async def multimodal_analysis(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    try:
        content_type = request.headers.get("content-type", "")
        if "multipart" in content_type:
            form = await request.form()
            text = form.get("text", "Analyze the provided content")
        else:
            body = await request.json()
            text = body.get("text", "Analyze the provided content")

        analysis = await ai_service.process_cybersecurity_message(text)
        return {"analysis": analysis, "filesAnalyzed": 0, "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Exploit generation ────────────────────────────────────────────────────────

@app.post("/api/protected/exploits/generate")
async def generate_exploit_protected(body: ExploitPoCRequest, current_user: User = Depends(get_current_user)):
    try:
        exploit = await ai_service.generate_exploit_poc(body.vulnerability, body.target, body.constraints)
        return {
            "exploit": exploit,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "warnings": [
                "This is for educational and authorized testing only",
                "Ensure you have proper authorization before testing",
                "Use only in controlled environments",
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── OSINT strategy ────────────────────────────────────────────────────────────

@app.post("/api/protected/osint/strategy")
async def osint_strategy(body: OSINTStrategyRequest, current_user: User = Depends(get_current_user)):
    try:
        strategy = await ai_service.generate_osint_strategy(body.target, body.objectives, body.constraints)
        return {
            "strategy": strategy,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "disclaimer": "Ensure all reconnaissance activities are authorized and legal",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Protected reports ─────────────────────────────────────────────────────────

@app.post("/api/protected/reports/generate")
async def generate_report_protected(body: ReportFindingsRequest, current_user: User = Depends(get_current_user)):
    try:
        report = await ai_service.generate_pentest_report(body.findings, body.executiveSummary, body.scope)
        return {
            "report": report,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Tools ─────────────────────────────────────────────────────────────────────

TOOL_RISK = {"nmap": "high", "whois": "low", "dns_lookup": "low", "port_scan": "medium"}

@app.post("/api/protected/tools/execute")
async def execute_tool(
    body: ToolExecutionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    risk = TOOL_RISK.get(body.toolName, "medium")
    tool_run = ToolRun(
        id=str(uuid.uuid4()),
        session_id=body.sessionId,
        tool_name=body.toolName,
        arguments=body.arguments,
        status="pending" if body.requiresApproval else "running",
        approval_required=body.requiresApproval,
        risk_level=risk,
    )
    db.add(tool_run)
    await db.commit()
    await db.refresh(tool_run)

    if not body.requiresApproval:
        tool_run.status = "completed"
        tool_run.result = {"output": f"Simulated {body.toolName} execution", "success": True}
        tool_run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        return {"toolRun": {"id": tool_run.id, "status": tool_run.status}, "result": tool_run.result, "requiresApproval": False}

    return {"toolRun": {"id": tool_run.id, "status": tool_run.status}, "requiresApproval": True}


@app.post("/api/protected/tools/{tool_run_id}/approve")
async def approve_tool(
    tool_run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ToolRun).where(ToolRun.id == tool_run_id))
    tool_run = result.scalar_one_or_none()
    if not tool_run:
        raise HTTPException(status_code=404, detail="Tool run not found")

    tool_run.status = "completed"
    tool_run.approved_by = current_user.id
    tool_run.approved_at = datetime.now(timezone.utc)
    tool_run.executed_at = datetime.now(timezone.utc)
    tool_run.completed_at = datetime.now(timezone.utc)
    tool_run.result = {"output": f"Approved execution of {tool_run.tool_name}", "success": True}
    await db.commit()

    return {"success": True, "result": tool_run.result}


# ── RAG ───────────────────────────────────────────────────────────────────────

@app.post("/api/protected/rag/ingest")
async def rag_ingest(
    file: UploadFile = File(...),
    title: str = Form(None),
    tags: str = Form("[]"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    doc = Document(
        id=str(uuid.uuid4()),
        owner_id=current_user.id,
        title=title or file.filename or "Untitled",
        type=file.content_type or "text/plain",
        content=content.decode("utf-8", errors="ignore")[:50000],
        tags=json.loads(tags) if tags else [],
        metadata_={"size": len(content), "mimeType": file.content_type},
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return {"id": doc.id, "title": doc.title, "type": doc.type, "status": "ingested"}


@app.post("/api/protected/rag/query")
async def rag_query(request: Request, current_user: User = Depends(get_current_user)):
    body = await request.json()
    query = body.get("query", "")
    result = await ai_service.process_cybersecurity_message(f"Answer this query based on your knowledge: {query}")
    return {"results": [{"content": result, "score": 0.9, "source": "AI Knowledge Base"}]}


# ── Coding workspace ──────────────────────────────────────────────────────────

@app.post("/api/coding/analyze")
async def analyze_code(body: CodeAnalysisRequest):
    try:
        analysis = await ai_service.analyze_code(body.code, body.language)
        return {
            "id": str(int(datetime.now().timestamp() * 1000)),
            "code": body.code,
            "language": body.language,
            **analysis,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/coding/generate-exploit")
async def generate_exploit(body: ExploitGenerationRequest):
    try:
        exploit = await ai_service.generate_exploit(body.code, body.exploitType, body.language)
        return {
            "id": str(int(datetime.now().timestamp() * 1000)),
            "targetCode": body.code,
            "exploitType": body.exploitType,
            **exploit,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/coding/analyses")
async def get_analyses():
    return []


@app.get("/api/coding/exploits")
async def get_exploits():
    return []


# ── Red Team workspace ────────────────────────────────────────────────────────

@app.post("/api/redteam/simulations")
async def create_simulation(body: SimulationRequest):
    try:
        prompt = f"""You are a red team specialist. Create a realistic attack simulation plan.
Target: {body.target}, Attack Type: {body.attackType}, Name: {body.name}
Return JSON: {{"phase": "reconnaissance", "progress": 25, "findings": [{{"type": "Open Port", "severity": "medium", "description": "...", "mitreTechnique": "T1046"}}], "status": "active", "steps": ["Network scanning"]}}
IMPORTANT: Authorized testing only."""
        result = await ai_service.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.4)
        parsed = json.loads(result)
        return {"id": str(int(datetime.now().timestamp() * 1000)), "name": body.name, "target": body.target, "attackType": body.attackType, **parsed, "createdAt": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/redteam/campaigns")
async def create_campaign(body: CampaignRequest):
    try:
        prompt = f"""Create an educational phishing campaign for security awareness training.
Campaign: {body.name}, Template: {body.template[:200]}, Targets: {len(body.targets)}
Return JSON: {{"template": "...", "targetList": {json.dumps(body.targets[:3])}, "sendsCompleted": 0, "opensTracked": 0, "clicksTracked": 0, "credentialsHarvested": 0, "status": "draft", "educational_tips": ["Check sender carefully"]}}"""
        result = await ai_service.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.4)
        parsed = json.loads(result)
        return {"id": str(int(datetime.now().timestamp() * 1000)), "name": body.name, **parsed, "createdAt": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/redteam/chains/generate")
async def generate_chain(body: ChainGenerationRequest):
    try:
        prompt = f"""Create a multi-step attack chain for authorized testing.
Target: {body.target}, Objective: {body.objective}
Return JSON: {{"steps": [{{"technique": "Initial Access - Phishing", "mitreTactic": "TA0001", "description": "...", "automated": false, "status": "pending"}}], "currentStep": 0, "overallProgress": 0, "riskLevel": "high", "timeline": "2-3 weeks"}}"""
        result = await ai_service.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.4)
        parsed = json.loads(result)
        return {"id": str(int(datetime.now().timestamp() * 1000)), "name": f"Attack Chain - {body.target}", **parsed, "createdAt": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/redteam/simulations")
async def get_simulations():
    return []


@app.get("/api/redteam/campaigns")
async def get_campaigns():
    return []


@app.get("/api/redteam/chains")
async def get_chains():
    return []


# ── OSINT workspace ───────────────────────────────────────────────────────────

@app.post("/api/osint/domain")
async def osint_domain(body: DomainOSINTRequest):
    try:
        d = body.domain
        prompt = f"""You are an OSINT specialist. Analyze domain: {d}
Generate realistic domain intelligence JSON:
{{"subdomains": ["www.{d}", "mail.{d}"], "ipAddresses": ["203.0.113.1"], "technologies": [{{"name": "nginx", "version": "1.18.0", "category": "Web Server"}}], "certificates": [{{"issuer": "Let's Encrypt", "subject": "*.{d}", "validFrom": "2024-01-01T00:00:00Z", "validTo": "2024-12-31T23:59:59Z"}}], "dnsRecords": {{"A": ["203.0.113.1"], "MX": ["10 mail.{d}"]}}, "socialMedia": [{{"platform": "Twitter", "url": "https://twitter.com/{d.split('.')[0]}", "verified": false}}], "breaches": [], "riskScore": 35}}
Authorized targets only."""
        result = await ai_service.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.3)
        parsed = json.loads(result)
        return {"domain": d, **parsed, "lastUpdated": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/osint/github")
async def osint_github(body: GitHubOSINTRequest):
    try:
        t = body.target
        prompt = f"""OSINT analysis of GitHub org: {t}
Return JSON: {{"organization": "{t}", "repositories": [{{"name": "web-app", "description": "Main app", "language": "JavaScript", "stars": 127, "forks": 23, "isPrivate": false, "hasSecrets": true, "vulnerabilities": [{{"type": "Dependency vulnerability", "severity": "medium", "description": "Outdated package"}}]}}], "users": [{{"username": "dev-{t}", "email": "dev@{t}.com", "name": "Developer"}}], "sensitiveFiles": [{{"repository": "web-app", "filename": ".env.example", "type": "config", "content": "API_KEY=example"}}], "totalRepos": 12, "riskLevel": "medium"}}
Authorized targets only."""
        result = await ai_service.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.3)
        return json.loads(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/osint/shodan")
async def osint_shodan(body: ShodanRequest):
    try:
        q = body.query
        prompt = f"""Shodan-like search for: {q}
Return JSON: {{"query": "{q}", "results": [{{"ip": "198.51.100.42", "port": 22, "protocol": "tcp", "service": "ssh", "banner": "SSH-2.0-OpenSSH_7.4", "location": {{"country": "United States", "city": "Los Angeles", "latitude": 34.05, "longitude": -118.24}}, "vulns": ["CVE-2018-15473"], "lastSeen": "2024-01-20T15:30:00Z"}}], "totalResults": 2847, "countriesFound": ["United States", "Germany"], "topServices": [{{"name": "http", "count": 1204}}], "vulnerabilities": [{{"cve": "CVE-2018-15473", "count": 156, "severity": "medium"}}]}}"""
        result = await ai_service.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.3)
        return json.loads(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/osint/domain/recent")
async def get_recent_domain():
    return []


@app.get("/api/osint/github/recent")
async def get_recent_github():
    return []


@app.get("/api/osint/shodan/recent")
async def get_recent_shodan():
    return []


# ── Reports workspace ─────────────────────────────────────────────────────────

@app.post("/api/reports/generate")
async def generate_report(body: ReportGenerationRequest):
    try:
        sections_str = ", ".join(body.sections) if body.sections else "Standard sections"
        prompt = f"""Generate a professional {body.type} security report.
Title: {body.title}, Type: {body.type}, Sections: {sections_str}
Return JSON:
{{"title": "{body.title}", "type": "{body.type}", "status": "completed", "progress": 100,
"findings": [{{"id": "finding-001", "title": "Weak SSH Configuration", "severity": "high", "category": "Configuration", "description": "SSH allows password authentication and root login", "recommendation": "Use key-based auth", "mitreTechnique": "T1110", "cvss": 7.5}}, {{"id": "finding-002", "title": "Outdated Web Server", "severity": "medium", "category": "Patch Management", "description": "Running outdated version", "recommendation": "Update to latest version", "mitreTechnique": "T1190", "cvss": 6.1}}],
"summary": {{"totalFindings": 8, "criticalCount": 1, "highCount": 2, "mediumCount": 3, "lowCount": 2, "overallRisk": "high"}},
"mitreMapping": [{{"tactic": "Initial Access", "techniques": ["T1110", "T1190"]}}, {{"tactic": "Persistence", "techniques": ["T1053"]}}],
"recommendations": ["Implement MFA", "Regular patching", "Network segmentation"],
"executiveSummary": "This assessment identified significant vulnerabilities requiring immediate attention.",
"technicalDetails": "Assessment utilized penetration testing methodologies including network scanning and manual testing."}}"""
        result = await ai_service.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.3)
        parsed = json.loads(result)
        now = datetime.now(timezone.utc).isoformat()
        return {"id": str(int(datetime.now().timestamp() * 1000)), **parsed, "createdAt": now, "updatedAt": now}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reports/{report_id}/download")
async def download_report(report_id: str):
    pdf_content = b"%PDF-1.4 Sample Security Report - " + report_id.encode() + b"\nGenerated by AMMU AI"
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="security-report-{report_id}.pdf"'},
    )


@app.get("/api/reports/templates")
async def get_report_templates():
    return [
        {"id": "pentest-template", "name": "Penetration Test Report", "type": "technical", "description": "Comprehensive penetration testing report", "sections": ["Executive Summary", "Methodology", "Findings", "Recommendations"], "customizable": True},
        {"id": "compliance-template", "name": "Compliance Assessment", "type": "compliance", "description": "Regulatory compliance assessment", "sections": ["Compliance Status", "Gaps", "Remediation Plan"], "customizable": True},
        {"id": "executive-template", "name": "Executive Summary Report", "type": "executive", "description": "High-level risk overview for leadership", "sections": ["Risk Overview", "Key Findings", "Business Impact", "Recommendations"], "customizable": True},
    ]


@app.get("/api/reports")
async def get_reports():
    return []


# ── Findings ──────────────────────────────────────────────────────────────────

@app.get("/api/findings")
async def get_findings():
    return [
        {"title": "Weak Password Policy", "severity": "medium", "category": "Authentication", "description": "Password complexity requirements are insufficient", "mitreTechnique": "T1110"},
        {"title": "Unencrypted Data Transmission", "severity": "high", "category": "Encryption", "description": "Sensitive data transmitted without encryption", "mitreTechnique": "T1040"},
        {"title": "Missing Security Headers", "severity": "medium", "category": "Web Security", "description": "HTTP security headers not configured", "mitreTechnique": "T1190"},
    ]


# ── Vite dev-server proxy (catch-all) ─────────────────────────────────────────
# Forwards every non-/api request to the Vite dev server so the webview on
# port 5000 shows the React frontend while the API stays on the same port.

import httpx

VITE_URL = "http://localhost:5173"

@app.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def vite_proxy(path: str, request: Request):
    url = f"{VITE_URL}/{path}"
    query = request.url.query
    if query:
        url = f"{url}?{query}"

    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length")
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            body = await request.body()
            resp = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
            )
            # Forward response headers except ones that break streaming
            resp_headers = {
                k: v for k, v in resp.headers.items()
                if k.lower() not in ("transfer-encoding", "content-encoding")
            }
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=resp_headers,
            )
    except (httpx.ConnectError, httpx.ReadTimeout):
        # Vite may still be starting — retry a few times before giving up
        for _ in range(8):
            import asyncio
            await asyncio.sleep(0.5)
            try:
                async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as retry_client:
                    resp = await retry_client.request(
                        method=request.method,
                        url=url,
                        headers=headers,
                        content=await request.body(),
                    )
                    resp_headers = {
                        k: v for k, v in resp.headers.items()
                        if k.lower() not in ("transfer-encoding", "content-encoding")
                    }
                    return Response(content=resp.content, status_code=resp.status_code, headers=resp_headers)
            except (httpx.ConnectError, httpx.ReadTimeout):
                continue
        return Response(
            content=b"<html><body><h2>Starting up...</h2><p>The frontend is initialising. Please refresh in a moment.</p><script>setTimeout(()=>location.reload(),2000)</script></body></html>",
            status_code=503,
            media_type="text/html",
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
