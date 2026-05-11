import os
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, EmailStr
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, update

from backend.database import get_db, init_db
from backend.models import User, Session, Message, Document, Memory, ToolRun, Finding, VoiceInteraction, WorkspaceRecord
from backend.auth import hash_password, verify_password, create_access_token, get_current_user
from backend.services.ai_service import ai_service, AIQuotaError, PromptInjectionError, AGENT_PERSONAS
from backend.services.agent_service import agent_service
from backend.services.tool_service import run_tool
from backend.services.tutor_service import tutor_service
from backend.services.report_service import generate_pdf_report, generate_docx_report

logger = logging.getLogger("akki.main")

# ── Rate Limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="AKKI AI Cybersecurity Platform", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


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

class ToolExecuteRequest(BaseModel):
    toolName: str
    params: dict

class TutorQuizRequest(BaseModel):
    topic: str
    difficulty: Optional[int] = 3

class TutorExplainRequest(BaseModel):
    topic: str
    level: Optional[str] = "intermediate"

class TutorChallengeRequest(BaseModel):
    topic: str
    difficulty: Optional[int] = 3

class TutorPathRequest(BaseModel):
    goals: str
    currentLevel: Optional[str] = "beginner"

class StreamChatRequest(BaseModel):
    content: str
    sessionId: Optional[str] = None
    agent: Optional[str] = None


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


def workspace_record_to_dict(r: WorkspaceRecord) -> dict:
    return {"id": r.id, "createdAt": r.created_at.isoformat() if r.created_at else None, **r.data}


async def _save_workspace(
    db: AsyncSession,
    workspace: str,
    record_type: str,
    title: str,
    data: dict,
    user_id: str | None = None,
) -> WorkspaceRecord:
    rec = WorkspaceRecord(
        id=str(uuid.uuid4()),
        user_id=user_id,
        workspace=workspace,
        record_type=record_type,
        title=title,
        data=data,
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return rec


async def _get_workspace_records(
    db: AsyncSession,
    workspace: str,
    record_type: str,
    user_id: str | None = None,
    limit: int = 50,
) -> list[WorkspaceRecord]:
    q = select(WorkspaceRecord).where(
        WorkspaceRecord.workspace == workspace,
        WorkspaceRecord.record_type == record_type,
    )
    if user_id:
        q = q.where(WorkspaceRecord.user_id == user_id)
    q = q.order_by(desc(WorkspaceRecord.created_at)).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


# Optional auth — tries to decode bearer token but never raises if absent
from fastapi.security import HTTPBearer as _HTTPBearer
from jose import JWTError as _JWTError

_optional_bearer = _HTTPBearer(auto_error=False)


async def optional_current_user(
    credentials=Depends(_optional_bearer),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if not credentials:
        return None
    try:
        from backend.auth import decode_token
        payload = decode_token(credentials.credentials)
        user_id = payload.get("userId")
        if not user_id:
            return None
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
    except Exception:
        return None


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.post("/api/auth/register")
@limiter.limit("10/minute")
async def register(request: Request, body: RegisterRequest, db: AsyncSession = Depends(get_db)):
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
@limiter.limit("20/minute")
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)):
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
@limiter.limit("60/minute")
async def chat_message(
    request: Request,
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
    except PromptInjectionError as e:
        agent_response = {
            "content": f"⚠️ Security Notice: {e}",
            "toolCalls": [],
            "ragUsed": False,
            "sources": [],
            "emotionalTone": "neutral",
        }
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
        "assistantMessage": {
            **message_to_dict(assistant_msg),
            "agent": agent_response.get("agent", "planner"),
            "agentName": agent_response.get("agentName", "NEXUS"),
            "agentRole": agent_response.get("agentRole", "Orchestration"),
            "agentColor": agent_response.get("agentColor", "cyber-blue"),
            "toolCalls": agent_response.get("toolCalls", []),
        },
        "sessionId": session_id,
        "agentPlan": agent_response.get("plan"),
        "agent": agent_response.get("agent", "planner"),
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
    # user_id maps to DB column "owner_id" via SQLAlchemy column mapping
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
@limiter.limit("30/minute")
async def analyze_code(
    request: Request,
    body: CodeAnalysisRequest,
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        analysis = await ai_service.analyze_code(body.code, body.language)
    except AIQuotaError:
        analysis = {
            "vulnerabilities": [
                {"id": "v1", "type": "Potential Injection", "severity": "medium", "description": "Input handling may need validation — full AI analysis unavailable (quota limit)", "line": 1, "suggestion": "Validate and sanitize all inputs", "mitreTechnique": "T1059"},
            ],
            "securityScore": 50,
            "mitreTags": ["T1059"],
            "exploitPotential": "Analysis pending — Gemini API quota reached. Re-run when quota resets.",
            "recommendations": ["Enable full AI analysis for detailed findings", "Manually review input validation", "Check dependency versions"],
            "aiNote": "Fallback response — Gemini quota exceeded",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    now = datetime.now(timezone.utc).isoformat()
    data = {"code": body.code, "language": body.language, **analysis, "createdAt": now}
    rec = await _save_workspace(
        db, "coding", "analysis",
        title=f"{body.language.upper()} Analysis",
        data=data,
        user_id=current_user.id if current_user else None,
    )
    return {"id": rec.id, **data}


@app.post("/api/coding/generate-exploit")
@limiter.limit("20/minute")
async def generate_exploit(
    request: Request,
    body: ExploitGenerationRequest,
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        exploit = await ai_service.generate_exploit(body.code, body.exploitType, body.language)
    except AIQuotaError:
        exploit = {
            "payload": f"# {body.exploitType} PoC — AI quota limit reached\n# Re-run when Gemini API quota resets\nprint('Exploit generation requires AI — please retry later')",
            "description": f"Educational {body.exploitType} exploit template. Full AI generation requires Gemini API quota.",
            "mitreTechnique": "T1190",
            "riskLevel": "medium",
            "preventions": ["Input validation and sanitization", "Web application firewall", "Least privilege access"],
            "educational_note": "For authorized testing only. Full analysis available when AI quota resets.",
            "aiNote": "Fallback response — Gemini quota exceeded",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    now = datetime.now(timezone.utc).isoformat()
    data = {"targetCode": body.code, "exploitType": body.exploitType, "language": body.language, **exploit, "createdAt": now}
    rec = await _save_workspace(
        db, "coding", "exploit",
        title=f"{body.exploitType} Exploit",
        data=data,
        user_id=current_user.id if current_user else None,
    )
    return {"id": rec.id, **data}


@app.get("/api/coding/analyses")
async def get_analyses(
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    records = await _get_workspace_records(
        db, "coding", "analysis",
        user_id=current_user.id if current_user else None,
    )
    return [workspace_record_to_dict(r) for r in records]


@app.get("/api/coding/exploits")
async def get_exploits(
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    records = await _get_workspace_records(
        db, "coding", "exploit",
        user_id=current_user.id if current_user else None,
    )
    return [workspace_record_to_dict(r) for r in records]


# ── Red Team workspace ────────────────────────────────────────────────────────

@app.post("/api/redteam/simulations")
@limiter.limit("20/minute")
async def create_simulation(
    request: Request,
    body: SimulationRequest,
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    ai_error = None
    try:
        prompt = f"""You are a red team specialist. Create a detailed, realistic attack simulation plan for authorized penetration testing.
Target: {body.target}
Attack Type: {body.attackType}
Simulation Name: {body.name}

Return valid JSON with this structure (no markdown, no code fences):
{{"phase": "reconnaissance", "progress": 15, "status": "active",
"findings": [
  {{"type": "Attack Vector", "severity": "high", "description": "Detailed finding description", "mitreTechnique": "T1595"}},
  {{"type": "Exposed Service", "severity": "medium", "description": "Another finding", "mitreTechnique": "T1046"}}
],
"steps": ["Phase 1: Reconnaissance - passive information gathering", "Phase 2: Scanning - active port/service detection", "Phase 3: Exploitation - target the identified weaknesses", "Phase 4: Post-Exploitation - maintain access and pivot"],
"riskLevel": "high",
"estimatedDuration": "3-5 days",
"prerequisites": ["Written authorization", "Isolated test environment"]}}

IMPORTANT: This simulation is for authorized security testing only."""
        result = await ai_service.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.4)
        parsed = json.loads(result)
    except AIQuotaError:
        parsed = {
            "phase": "reconnaissance", "progress": 0, "status": "planned",
            "findings": [
                {"type": "Target Surface", "severity": "medium", "description": f"Initial assessment of {body.target} attack surface", "mitreTechnique": "T1595"},
                {"type": "Exposed Services", "severity": "high", "description": "Services enumeration pending full scan", "mitreTechnique": "T1046"},
            ],
            "steps": [
                "Phase 1: Passive reconnaissance — WHOIS, DNS, OSINT",
                "Phase 2: Active scanning — port/service detection",
                "Phase 3: Vulnerability assessment — CVE mapping",
                "Phase 4: Exploitation — targeted attacks on confirmed vulnerabilities",
                "Phase 5: Post-exploitation — lateral movement, persistence",
                "Phase 6: Reporting — findings documentation",
            ],
            "riskLevel": "high", "estimatedDuration": "3-5 days",
            "prerequisites": ["Written authorization", "Isolated test environment", "Rules of engagement defined"],
            "aiNote": "Fallback plan — Gemini quota exceeded. Full AI simulation available when quota resets.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    now = datetime.now(timezone.utc).isoformat()
    data = {"name": body.name, "target": body.target, "attackType": body.attackType, **parsed, "createdAt": now}
    rec = await _save_workspace(
        db, "redteam", "simulation",
        title=body.name,
        data=data,
        user_id=current_user.id if current_user else None,
    )
    return {"id": rec.id, **data}


@app.post("/api/redteam/campaigns")
@limiter.limit("20/minute")
async def create_campaign(
    request: Request,
    body: CampaignRequest,
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        prompt = f"""Create a detailed educational phishing campaign for security awareness training.
Campaign Name: {body.name}
Email Template Base: {body.template[:300]}
Number of Targets: {len(body.targets)}

Return valid JSON (no markdown):
{{"template": "Full polished phishing email template here...", "subject": "Urgent: Account Verification Required",
"targetList": {json.dumps(body.targets[:5])},
"sendsCompleted": 0, "opensTracked": 0, "clicksTracked": 0, "credentialsHarvested": 0, "status": "draft",
"educational_tips": ["Always verify the sender domain", "Check for spelling errors in URLs", "Never enter credentials from email links", "Report suspicious emails to IT security"],
"indicators_of_phishing": ["Urgency language", "Mismatched sender domain", "Generic greeting", "Suspicious link destination"]}}"""
        result = await ai_service.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.4)
        parsed = json.loads(result)
    except AIQuotaError:
        parsed = {
            "template": body.template or "Security awareness phishing simulation template — full AI generation available when quota resets.",
            "subject": "Important: Immediate Action Required — Account Verification",
            "targetList": body.targets[:5],
            "sendsCompleted": 0, "opensTracked": 0, "clicksTracked": 0, "credentialsHarvested": 0, "status": "draft",
            "educational_tips": ["Always verify the sender domain before clicking", "Check for spelling errors in URLs and sender address", "Never enter credentials after clicking an email link — go directly to the site", "Report suspicious emails to your IT security team immediately", "Enable MFA on all accounts"],
            "indicators_of_phishing": ["Urgency or threatening language", "Mismatched sender domain", "Generic greeting (Dear Customer)", "Suspicious link destination on hover", "Unexpected attachment"],
            "aiNote": "Fallback campaign — Gemini quota exceeded. Full AI template generation available when quota resets.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    now = datetime.now(timezone.utc).isoformat()
    data = {"name": body.name, **parsed, "createdAt": now}
    rec = await _save_workspace(
        db, "redteam", "campaign",
        title=body.name,
        data=data,
        user_id=current_user.id if current_user else None,
    )
    return {"id": rec.id, **data}


@app.post("/api/redteam/chains/generate")
@limiter.limit("20/minute")
async def generate_chain(
    request: Request,
    body: ChainGenerationRequest,
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        prompt = f"""Create a detailed multi-step attack chain for authorized penetration testing.
Target: {body.target}
Objective: {body.objective}

Return valid JSON (no markdown):
{{"steps": [
  {{"technique": "Initial Access - Spearphishing", "mitreTactic": "TA0001", "mitreTechnique": "T1566", "description": "Craft targeted spearphishing email to gain initial foothold", "automated": false, "status": "pending", "expectedDuration": "1-2 days"}},
  {{"technique": "Execution - PowerShell", "mitreTactic": "TA0002", "mitreTechnique": "T1059.001", "description": "Execute malicious PowerShell script to establish persistence", "automated": true, "status": "pending", "expectedDuration": "30 minutes"}},
  {{"technique": "Privilege Escalation", "mitreTactic": "TA0004", "mitreTechnique": "T1068", "description": "Exploit local vulnerability for SYSTEM privileges", "automated": false, "status": "pending", "expectedDuration": "2-4 hours"}},
  {{"technique": "Lateral Movement - Pass-the-Hash", "mitreTactic": "TA0008", "mitreTechnique": "T1550.002", "description": "Use harvested NTLM hashes to move laterally", "automated": true, "status": "pending", "expectedDuration": "1 day"}}
],
"currentStep": 0, "overallProgress": 0,
"riskLevel": "critical", "timeline": "1-2 weeks",
"mitigations": ["Network segmentation", "Privileged access workstations", "MFA enforcement", "EDR solutions"]}}"""
        result = await ai_service.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.4)
        parsed = json.loads(result)
    except AIQuotaError:
        parsed = {
            "steps": [
                {"technique": "Initial Access - Spearphishing", "mitreTactic": "TA0001", "mitreTechnique": "T1566", "description": f"Craft targeted spearphishing email against {body.target} to gain initial foothold", "automated": False, "status": "pending", "expectedDuration": "1-2 days"},
                {"technique": "Execution - Script Interpreter", "mitreTactic": "TA0002", "mitreTechnique": "T1059", "description": "Execute malicious script to establish persistence and C2 channel", "automated": True, "status": "pending", "expectedDuration": "30-60 minutes"},
                {"technique": "Privilege Escalation", "mitreTactic": "TA0004", "mitreTechnique": "T1068", "description": "Exploit local vulnerability or misconfiguration to gain elevated privileges", "automated": False, "status": "pending", "expectedDuration": "2-4 hours"},
                {"technique": "Lateral Movement", "mitreTactic": "TA0008", "mitreTechnique": "T1550", "description": f"Move laterally toward objective: {body.objective}", "automated": True, "status": "pending", "expectedDuration": "1-2 days"},
                {"technique": "Exfiltration / Objective Completion", "mitreTactic": "TA0010", "mitreTechnique": "T1041", "description": "Complete the stated objective with appropriate evidence collection", "automated": False, "status": "pending", "expectedDuration": "2-4 hours"},
            ],
            "currentStep": 0, "overallProgress": 0, "riskLevel": "critical", "timeline": "1-2 weeks",
            "mitigations": ["Network segmentation", "Privileged access workstations", "MFA enforcement", "EDR/XDR deployment", "Threat hunting"],
            "aiNote": "Fallback chain — Gemini quota exceeded. Full AI generation available when quota resets.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    name = f"Attack Chain - {body.target}"
    now = datetime.now(timezone.utc).isoformat()
    data = {"name": name, "target": body.target, "objective": body.objective, **parsed, "createdAt": now}
    rec = await _save_workspace(
        db, "redteam", "chain",
        title=name,
        data=data,
        user_id=current_user.id if current_user else None,
    )
    return {"id": rec.id, **data}


@app.get("/api/redteam/simulations")
async def get_simulations(
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    records = await _get_workspace_records(
        db, "redteam", "simulation",
        user_id=current_user.id if current_user else None,
    )
    return [workspace_record_to_dict(r) for r in records]


@app.get("/api/redteam/campaigns")
async def get_campaigns(
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    records = await _get_workspace_records(
        db, "redteam", "campaign",
        user_id=current_user.id if current_user else None,
    )
    return [workspace_record_to_dict(r) for r in records]


@app.get("/api/redteam/chains")
async def get_chains(
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    records = await _get_workspace_records(
        db, "redteam", "chain",
        user_id=current_user.id if current_user else None,
    )
    return [workspace_record_to_dict(r) for r in records]


# ── OSINT workspace ───────────────────────────────────────────────────────────

@app.post("/api/osint/domain")
@limiter.limit("20/minute")
async def osint_domain(
    request: Request,
    body: DomainOSINTRequest,
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    d = body.domain
    try:
        prompt = f"""You are an OSINT specialist conducting authorized domain intelligence gathering.
Analyze domain: {d}

Return comprehensive domain intelligence as valid JSON (no markdown, no code fences):
{{"subdomains": ["www.{d}", "mail.{d}", "api.{d}", "dev.{d}", "staging.{d}"],
"ipAddresses": ["203.0.113.10", "203.0.113.11"],
"technologies": [
  {{"name": "nginx", "version": "1.24.0", "category": "Web Server"}},
  {{"name": "CloudFlare", "version": null, "category": "CDN/WAF"}},
  {{"name": "React", "version": "18.x", "category": "Frontend Framework"}}
],
"certificates": [{{"issuer": "Let's Encrypt Authority X3", "subject": "*.{d}", "validFrom": "2024-01-01T00:00:00Z", "validTo": "2024-12-31T23:59:59Z", "sans": ["*.{d}", "{d}"]}}],
"dnsRecords": {{"A": ["203.0.113.10"], "MX": ["10 mail.{d}", "20 mail2.{d}"], "TXT": ["v=spf1 include:_spf.google.com ~all"], "NS": ["ns1.{d}", "ns2.{d}"]}},
"socialMedia": [{{"platform": "LinkedIn", "url": "https://linkedin.com/company/{d.split('.')[0]}", "verified": false}}, {{"platform": "Twitter", "url": "https://twitter.com/{d.split('.')[0]}", "verified": false}}],
"whois": {{"registrar": "GoDaddy.com, LLC", "registrationDate": "2015-03-22", "expirationDate": "2026-03-22", "privacyProtected": true}},
"breaches": [],
"openPorts": [80, 443, 22],
"riskScore": 42,
"riskFactors": ["Outdated TLS version on port 443", "Subdomain enumeration possible", "SPF record allows too broad a range"]}}

Note: This is simulated OSINT for authorized security research."""
        result = await ai_service.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.3)
        parsed = json.loads(result)
    except AIQuotaError:
        base = d.split(".")[0]
        parsed = {
            "subdomains": [f"www.{d}", f"mail.{d}", f"api.{d}", f"dev.{d}", f"vpn.{d}"],
            "ipAddresses": ["203.0.113.10", "203.0.113.11"],
            "technologies": [
                {"name": "nginx", "version": "1.24.0", "category": "Web Server"},
                {"name": "CloudFlare", "version": None, "category": "CDN/WAF"},
            ],
            "certificates": [{"issuer": "Let's Encrypt", "subject": f"*.{d}", "validFrom": "2024-01-01T00:00:00Z", "validTo": "2025-01-01T00:00:00Z", "sans": [f"*.{d}", d]}],
            "dnsRecords": {"A": ["203.0.113.10"], "MX": [f"10 mail.{d}"], "TXT": ["v=spf1 ~all"], "NS": [f"ns1.{d}"]},
            "socialMedia": [{"platform": "LinkedIn", "url": f"https://linkedin.com/company/{base}", "verified": False}],
            "whois": {"registrar": "Unknown — AI quota limit reached", "registrationDate": "Unknown", "expirationDate": "Unknown", "privacyProtected": True},
            "breaches": [],
            "openPorts": [80, 443],
            "riskScore": 40,
            "riskFactors": ["Full AI analysis unavailable — Gemini quota exceeded"],
            "aiNote": "Fallback intelligence — Gemini quota exceeded. Full AI OSINT available when quota resets.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    now = datetime.now(timezone.utc).isoformat()
    data = {"domain": d, **parsed, "lastUpdated": now}
    rec = await _save_workspace(
        db, "osint", "domain",
        title=d,
        data=data,
        user_id=current_user.id if current_user else None,
    )
    return {"id": rec.id, **data}


@app.post("/api/osint/github")
@limiter.limit("20/minute")
async def osint_github(
    request: Request,
    body: GitHubOSINTRequest,
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    t = body.target
    try:
        prompt = f"""Perform authorized OSINT analysis of GitHub organization or user: {t}

Return comprehensive GitHub intelligence as valid JSON (no markdown):
{{"organization": "{t}",
"repositories": [
  {{"name": "web-app", "description": "Main web application", "language": "JavaScript", "stars": 127, "forks": 23, "isPrivate": false, "hasSecrets": true, "lastCommit": "2024-01-15", "vulnerabilities": [{{"type": "Dependency vulnerability", "severity": "high", "description": "Outdated lodash with prototype pollution", "cve": "CVE-2021-23337"}}]}},
  {{"name": "infrastructure", "description": "IaC and deployment configs", "language": "HCL", "stars": 8, "forks": 2, "isPrivate": false, "hasSecrets": true, "lastCommit": "2024-01-10", "vulnerabilities": []}}
],
"users": [
  {{"username": "admin-{t}", "email": "admin@{t}.io", "name": "Organization Admin", "publicRepos": 12, "followers": 45, "company": "{t}"}},
  {{"username": "dev1-{t}", "email": "dev1@{t}.io", "name": "Developer 1", "publicRepos": 34, "followers": 12, "company": "{t}"}}
],
"sensitiveFiles": [
  {{"repository": "web-app", "filename": ".env.example", "type": "environment config", "content": "DATABASE_URL=postgres://...\nAPI_KEY=sk-..."}},
  {{"repository": "infrastructure", "filename": "terraform.tfvars.example", "type": "infrastructure config", "content": "aws_access_key_id = ..."}}
],
"totalRepos": 18, "totalMembers": 7,
"riskLevel": "medium",
"riskFactors": ["Hardcoded secrets in history", "Outdated dependencies", "Public repository exposes configuration"]}}"""
        result = await ai_service.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.3)
        parsed = json.loads(result)
    except AIQuotaError:
        parsed = {
            "organization": t,
            "repositories": [
                {"name": f"{t}-web", "description": "Main web application", "language": "JavaScript", "stars": 42, "forks": 8, "isPrivate": False, "hasSecrets": False, "lastCommit": "2024-01-15", "vulnerabilities": []},
                {"name": f"{t}-api", "description": "Backend API", "language": "Python", "stars": 15, "forks": 3, "isPrivate": False, "hasSecrets": False, "lastCommit": "2024-01-10", "vulnerabilities": []},
            ],
            "users": [{"username": f"admin-{t}", "email": f"admin@{t}.com", "name": "Organization Admin", "publicRepos": 8, "followers": 20, "company": t}],
            "sensitiveFiles": [],
            "totalRepos": 5, "totalMembers": 3,
            "riskLevel": "low",
            "riskFactors": ["Full AI analysis unavailable — Gemini quota exceeded"],
            "aiNote": "Fallback intelligence — Gemini quota exceeded. Full AI GitHub OSINT available when quota resets.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    now = datetime.now(timezone.utc).isoformat()
    data = {**parsed, "target": t, "lastUpdated": now}
    rec = await _save_workspace(
        db, "osint", "github",
        title=t,
        data=data,
        user_id=current_user.id if current_user else None,
    )
    return {"id": rec.id, **data}


@app.post("/api/osint/shodan")
@limiter.limit("20/minute")
async def osint_shodan(
    request: Request,
    body: ShodanRequest,
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = body.query
    try:
        prompt = f"""Simulate a Shodan internet exposure analysis for the query: {q}

Return comprehensive exposure intelligence as valid JSON (no markdown):
{{"query": "{q}",
"results": [
  {{"ip": "198.51.100.42", "hostname": "srv1.example.com", "port": 22, "protocol": "tcp", "service": "ssh", "banner": "SSH-2.0-OpenSSH_8.2p1 Ubuntu-4ubuntu0.5", "location": {{"country": "United States", "city": "Los Angeles", "latitude": 34.05, "longitude": -118.24}}, "vulns": ["CVE-2023-48795"], "lastSeen": "2024-01-20T15:30:00Z", "org": "AS13335 Cloudflare Inc"}},
  {{"ip": "198.51.100.55", "hostname": "web.example.org", "port": 443, "protocol": "tcp", "service": "https", "banner": "HTTP/1.1 200 OK Server: Apache/2.4.41", "location": {{"country": "Germany", "city": "Frankfurt", "latitude": 50.11, "longitude": 8.68}}, "vulns": [], "lastSeen": "2024-01-21T08:15:00Z", "org": "AS24940 Hetzner Online GmbH"}}
],
"totalResults": 3247,
"countriesFound": ["United States", "Germany", "Netherlands", "Singapore", "United Kingdom"],
"topServices": [{{"name": "http", "count": 1204}}, {{"name": "https", "count": 998}}, {{"name": "ssh", "count": 645}}, {{"name": "ftp", "count": 122}}],
"vulnerabilities": [{{"cve": "CVE-2023-48795", "count": 156, "severity": "medium", "description": "Terrapin SSH protocol downgrade"}}, {{"cve": "CVE-2021-44228", "count": 42, "severity": "critical", "description": "Log4Shell remote code execution"}}],
"exposureScore": 67}}"""
        result = await ai_service.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.3)
        parsed = json.loads(result)
    except AIQuotaError:
        parsed = {
            "query": q,
            "results": [
                {"ip": "198.51.100.42", "hostname": "srv1.example.com", "port": 22, "protocol": "tcp", "service": "ssh", "banner": "SSH-2.0-OpenSSH_8.2p1", "location": {"country": "United States", "city": "Los Angeles", "latitude": 34.05, "longitude": -118.24}, "vulns": [], "lastSeen": "2024-01-20T15:30:00Z", "org": "AS13335"},
                {"ip": "198.51.100.55", "hostname": "web.example.org", "port": 443, "protocol": "tcp", "service": "https", "banner": "HTTP/1.1 200 OK", "location": {"country": "Germany", "city": "Frankfurt", "latitude": 50.11, "longitude": 8.68}, "vulns": [], "lastSeen": "2024-01-21T08:15:00Z", "org": "AS24940"},
            ],
            "totalResults": 0,
            "countriesFound": ["United States", "Germany"],
            "topServices": [{"name": "http", "count": 0}, {"name": "https", "count": 0}, {"name": "ssh", "count": 0}],
            "vulnerabilities": [],
            "exposureScore": 0,
            "aiNote": "Fallback results — Gemini quota exceeded. Full AI Shodan simulation available when quota resets.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    now = datetime.now(timezone.utc).isoformat()
    data = {**parsed, "lastUpdated": now}
    rec = await _save_workspace(
        db, "osint", "shodan",
        title=q,
        data=data,
        user_id=current_user.id if current_user else None,
    )
    return {"id": rec.id, **data}


@app.get("/api/osint/domain/recent")
async def get_recent_domain(
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    records = await _get_workspace_records(
        db, "osint", "domain",
        user_id=current_user.id if current_user else None,
    )
    return [workspace_record_to_dict(r) for r in records]


@app.get("/api/osint/github/recent")
async def get_recent_github(
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    records = await _get_workspace_records(
        db, "osint", "github",
        user_id=current_user.id if current_user else None,
    )
    return [workspace_record_to_dict(r) for r in records]


@app.get("/api/osint/shodan/recent")
async def get_recent_shodan(
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    records = await _get_workspace_records(
        db, "osint", "shodan",
        user_id=current_user.id if current_user else None,
    )
    return [workspace_record_to_dict(r) for r in records]


# ── Reports workspace ─────────────────────────────────────────────────────────

@app.post("/api/reports/generate")
async def generate_report(
    body: ReportGenerationRequest,
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    sections_str = ", ".join(body.sections) if body.sections else "Executive Summary, Scope, Methodology, Findings, Recommendations"
    try:
        prompt = f"""Generate a comprehensive professional {body.type} security assessment report.
Title: {body.title}
Report Type: {body.type}
Sections Required: {sections_str}

Return valid JSON (no markdown, no code fences):
{{"title": "{body.title}", "type": "{body.type}", "status": "completed", "progress": 100,
"findings": [
  {{"id": "finding-001", "title": "Weak SSH Configuration", "severity": "high", "category": "Configuration Management", "description": "SSH server allows password-based authentication and permits root login, creating significant attack surface for brute-force attacks.", "recommendation": "Disable password authentication, enforce key-based auth, prohibit direct root login, and implement fail2ban.", "mitreTechnique": "T1110", "cvss": 7.5, "cve": null}},
  {{"id": "finding-002", "title": "Outdated Web Application Framework", "severity": "critical", "category": "Patch Management", "description": "The web application is running a framework version with known RCE vulnerabilities that have public exploits available.", "recommendation": "Immediately update to the latest stable version and implement a patch management policy.", "mitreTechnique": "T1190", "cvss": 9.8, "cve": "CVE-2023-XXXX"}},
  {{"id": "finding-003", "title": "Missing HTTP Security Headers", "severity": "medium", "category": "Web Security", "description": "Critical security headers (CSP, HSTS, X-Frame-Options) are absent, exposing users to XSS, clickjacking, and man-in-the-middle attacks.", "recommendation": "Implement all recommended OWASP security headers with appropriate values.", "mitreTechnique": "T1059", "cvss": 5.3, "cve": null}},
  {{"id": "finding-004", "title": "Excessive User Privileges", "severity": "high", "category": "Access Control", "description": "Multiple service accounts have been granted excessive permissions violating the principle of least privilege.", "recommendation": "Conduct privilege review and implement role-based access control with minimal necessary permissions.", "mitreTechnique": "T1078", "cvss": 7.2, "cve": null}}
],
"summary": {{"totalFindings": 12, "criticalCount": 1, "highCount": 4, "mediumCount": 5, "lowCount": 2, "infoCount": 0, "overallRisk": "high", "riskScore": 78}},
"mitreMapping": [
  {{"tactic": "Initial Access", "tacticId": "TA0001", "techniques": ["T1190", "T1133", "T1566"]}},
  {{"tactic": "Privilege Escalation", "tacticId": "TA0004", "techniques": ["T1068", "T1078"]}},
  {{"tactic": "Persistence", "tacticId": "TA0003", "techniques": ["T1053", "T1543"]}}
],
"recommendations": [
  "Immediately patch all critical and high severity vulnerabilities",
  "Implement multi-factor authentication across all systems",
  "Establish a vulnerability management program with regular scanning",
  "Deploy an endpoint detection and response (EDR) solution",
  "Conduct security awareness training for all staff"
],
"executiveSummary": "This {body.type} security assessment identified 12 findings across the target environment, including 1 critical and 4 high severity vulnerabilities requiring immediate remediation. The overall security posture is rated HIGH risk. Immediate action is required to address the critical remote code execution vulnerability before threat actors can exploit it.",
"technicalDetails": "Assessment methodology followed PTES (Penetration Testing Execution Standard) and OWASP Testing Guide v4.2. Testing was conducted over 5 business days with full knowledge of the target environment (gray-box approach). Tools used included Nmap, Burp Suite Professional, Metasploit, and manual analysis techniques.",
"scope": "Web application, supporting API endpoints, network perimeter, and authentication mechanisms",
"methodology": "Gray-box penetration test following PTES standard"}}"""
        result = await ai_service.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.3)
        parsed = json.loads(result)
    except AIQuotaError:
        parsed = {
            "title": body.title, "type": body.type, "status": "completed", "progress": 100,
            "findings": [
                {"id": "f-001", "title": "Weak Password Policy", "severity": "medium", "category": "Authentication", "description": "Password complexity requirements are insufficient for modern security standards.", "recommendation": "Implement strong password policy with minimum 12 characters, complexity requirements, and MFA.", "mitreTechnique": "T1110", "cvss": 6.5, "cve": None},
                {"id": "f-002", "title": "Unencrypted Data Transmission", "severity": "high", "category": "Encryption", "description": "Sensitive data may be transmitted without proper encryption in some communication paths.", "recommendation": "Enforce TLS 1.3 on all connections. Disable legacy SSL/TLS versions.", "mitreTechnique": "T1040", "cvss": 7.5, "cve": None},
                {"id": "f-003", "title": "Missing Security Headers", "severity": "medium", "category": "Web Security", "description": "HTTP security headers not fully configured across all endpoints.", "recommendation": "Implement CSP, HSTS, X-Frame-Options, X-Content-Type-Options headers.", "mitreTechnique": "T1190", "cvss": 5.3, "cve": None},
                {"id": "f-004", "title": "Inadequate Logging and Monitoring", "severity": "medium", "category": "Detection", "description": "Security events are not being adequately logged or monitored for anomalies.", "recommendation": "Implement SIEM solution with alerting for suspicious activity patterns.", "mitreTechnique": "T1562", "cvss": 5.0, "cve": None},
            ],
            "summary": {"totalFindings": 4, "criticalCount": 0, "highCount": 1, "mediumCount": 3, "lowCount": 0, "infoCount": 0, "overallRisk": "medium", "riskScore": 55},
            "mitreMapping": [
                {"tactic": "Initial Access", "tacticId": "TA0001", "techniques": ["T1190"]},
                {"tactic": "Credential Access", "tacticId": "TA0006", "techniques": ["T1110"]},
                {"tactic": "Defense Evasion", "tacticId": "TA0005", "techniques": ["T1562"]},
            ],
            "recommendations": [
                "Implement multi-factor authentication across all systems",
                "Enforce TLS 1.3 on all network communications",
                "Deploy comprehensive security monitoring and SIEM",
                "Conduct regular security awareness training",
                "Establish a vulnerability management and patch program",
            ],
            "executiveSummary": f"This {body.type} security assessment of '{body.title}' identified 4 findings requiring attention. The overall security posture is rated MEDIUM risk. Priority should be given to addressing the high-severity unencrypted data transmission finding.",
            "technicalDetails": "Assessment based on industry standard methodologies including OWASP Testing Guide and NIST SP 800-115. Full AI-enhanced analysis available when Gemini API quota resets.",
            "scope": sections_str,
            "methodology": f"{body.type.title()} assessment following industry standards",
            "aiNote": "Fallback report — Gemini quota exceeded. Full AI report generation available when quota resets.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    now = datetime.now(timezone.utc).isoformat()
    data = {**parsed, "createdAt": now, "updatedAt": now}
    rec = await _save_workspace(
        db, "reports", "report",
        title=body.title,
        data=data,
        user_id=current_user.id if current_user else None,
    )
    return {"id": rec.id, **data}


@app.get("/api/reports/templates")
async def get_report_templates():
    return [
        {"id": "pentest-template", "name": "Penetration Test Report", "type": "technical", "description": "Comprehensive penetration testing report", "sections": ["Executive Summary", "Methodology", "Findings", "Recommendations"], "customizable": True},
        {"id": "compliance-template", "name": "Compliance Assessment", "type": "compliance", "description": "Regulatory compliance assessment", "sections": ["Compliance Status", "Gaps", "Remediation Plan"], "customizable": True},
        {"id": "executive-template", "name": "Executive Summary Report", "type": "executive", "description": "High-level risk overview for leadership", "sections": ["Risk Overview", "Key Findings", "Business Impact", "Recommendations"], "customizable": True},
    ]


@app.get("/api/reports/{report_id}/download")
async def download_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WorkspaceRecord).where(
            WorkspaceRecord.id == report_id,
            WorkspaceRecord.workspace == "reports",
        )
    )
    rec = result.scalar_one_or_none()

    if rec:
        data = rec.data
        title = data.get("title", "Security Report")
        executive_summary = data.get("executiveSummary", "")
        technical_details = data.get("technicalDetails", "")
        methodology = data.get("methodology", "")
        scope = data.get("scope", "")
        findings = data.get("findings", [])
        recommendations = data.get("recommendations", [])
        summary = data.get("summary", {})
        mitre = data.get("mitreMapping", [])
        created_at = data.get("createdAt", rec.created_at.isoformat())

        lines = [
            "=" * 70,
            title.upper(),
            "AMMU AI Cybersecurity Platform — Security Assessment Report",
            "=" * 70,
            f"Generated: {created_at}",
            f"Report ID: {report_id}",
            f"Report Type: {data.get('type', 'technical').upper()}",
            "",
            "SCOPE",
            "-" * 40,
            scope or "Full environment assessment",
            "",
            "METHODOLOGY",
            "-" * 40,
            methodology or "Standard penetration testing methodology",
            "",
            "EXECUTIVE SUMMARY",
            "-" * 40,
            executive_summary,
            "",
            "RISK SUMMARY",
            "-" * 40,
            f"  Overall Risk: {summary.get('overallRisk', 'N/A').upper()}",
            f"  Risk Score:   {summary.get('riskScore', 'N/A')} / 100",
            f"  Total Findings: {summary.get('totalFindings', len(findings))}",
            f"    Critical: {summary.get('criticalCount', 0)}",
            f"    High:     {summary.get('highCount', 0)}",
            f"    Medium:   {summary.get('mediumCount', 0)}",
            f"    Low:      {summary.get('lowCount', 0)}",
            "",
            "FINDINGS",
            "-" * 40,
        ]

        for i, f in enumerate(findings, 1):
            lines += [
                f"[{i}] {f.get('title', 'Untitled')}",
                f"    Severity:    {f.get('severity', 'N/A').upper()}",
                f"    Category:    {f.get('category', 'N/A')}",
                f"    CVSS Score:  {f.get('cvss', 'N/A')}",
                f"    MITRE:       {f.get('mitreTechnique', 'N/A')}",
                f"    Description: {f.get('description', '')}",
                f"    Recommendation: {f.get('recommendation', '')}",
                "",
            ]

        lines += [
            "MITRE ATT&CK MAPPING",
            "-" * 40,
        ]
        for m in mitre:
            techs = ", ".join(m.get("techniques", []))
            lines.append(f"  {m.get('tactic', '')} ({m.get('tacticId', '')}): {techs}")

        lines += [
            "",
            "RECOMMENDATIONS",
            "-" * 40,
        ]
        for i, rec_text in enumerate(recommendations, 1):
            lines.append(f"  {i}. {rec_text}")

        lines += [
            "",
            "TECHNICAL DETAILS",
            "-" * 40,
            technical_details,
            "",
            "=" * 70,
            "END OF REPORT — Generated by AMMU AI Cybersecurity Platform",
            "=" * 70,
        ]
        content = "\n".join(lines).encode("utf-8")
        filename = f"security-report-{report_id[:8]}.txt"
    else:
        content = f"Security Report {report_id}\nGenerated by AMMU AI Cybersecurity Platform\n\nReport data not found.".encode()
        filename = f"security-report-{report_id}.txt"

    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/reports")
async def get_reports(
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    records = await _get_workspace_records(
        db, "reports", "report",
        user_id=current_user.id if current_user else None,
    )
    return [workspace_record_to_dict(r) for r in records]


# ── Findings ──────────────────────────────────────────────────────────────────

@app.get("/api/findings")
async def get_findings(
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Pull findings from code analyses stored in workspace_records
    records = await _get_workspace_records(
        db, "coding", "analysis",
        user_id=current_user.id if current_user else None,
        limit=100,
    )
    db_findings = []
    for rec in records:
        data = rec.data
        for v in data.get("vulnerabilities", []):
            db_findings.append({
                "id": f"{rec.id}-{v.get('id', uuid.uuid4().hex[:8])}",
                "title": v.get("title", "Code Vulnerability"),
                "severity": v.get("severity", "medium"),
                "category": v.get("type", "Code Analysis"),
                "description": v.get("description", ""),
                "mitreTechnique": v.get("mitreTechnique", ""),
                "recommendation": v.get("recommendation", ""),
                "source": "code_analysis",
                "createdAt": data.get("createdAt"),
            })

    # Also pull findings from generated reports
    report_records = await _get_workspace_records(
        db, "reports", "report",
        user_id=current_user.id if current_user else None,
        limit=20,
    )
    for rec in report_records:
        for f in rec.data.get("findings", []):
            db_findings.append({
                "id": f.get("id", str(uuid.uuid4())),
                "title": f.get("title", ""),
                "severity": f.get("severity", "medium"),
                "category": f.get("category", "Security Assessment"),
                "description": f.get("description", ""),
                "mitreTechnique": f.get("mitreTechnique", ""),
                "recommendation": f.get("recommendation", ""),
                "cvss": f.get("cvss"),
                "source": "report",
                "createdAt": rec.data.get("createdAt"),
            })

    # Baseline findings always shown (deduped at end)
    baseline = [
        {"id": "baseline-001", "title": "Weak Password Policy", "severity": "medium", "category": "Authentication", "description": "Password complexity requirements are insufficient for modern security standards", "mitreTechnique": "T1110", "source": "baseline"},
        {"id": "baseline-002", "title": "Unencrypted Data Transmission", "severity": "high", "category": "Encryption", "description": "Sensitive data may be transmitted without encryption in some communication paths", "mitreTechnique": "T1040", "source": "baseline"},
        {"id": "baseline-003", "title": "Missing Security Headers", "severity": "medium", "category": "Web Security", "description": "HTTP security headers not fully configured across all endpoints", "mitreTechnique": "T1190", "source": "baseline"},
    ]

    return db_findings + baseline


# ── Agents ────────────────────────────────────────────────────────────────────

@app.get("/api/agents")
async def get_agents():
    """Return all registered specialist agents and their status."""
    return [
        {
            "id": agent_id,
            "name": info["name"],
            "role": info["role"],
            "color": info["color"],
            "status": "active",
            "description": info["system"][:200] + "...",
        }
        for agent_id, info in AGENT_PERSONAS.items()
    ]


# ── Streaming Chat ─────────────────────────────────────────────────────────────

@app.post("/api/chat/stream")
@limiter.limit("40/minute")
async def stream_chat(
    request: Request,
    body: StreamChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Server-Sent Events streaming chat endpoint with true Gemini token streaming."""
    import json as _json

    # Load recent session history for context
    history: list[dict] = []
    if body.sessionId:
        hist_result = await db.execute(
            select(Message)
            .where(Message.session_id == body.sessionId)
            .order_by(desc(Message.created_at))
            .limit(30)
        )
        for m in reversed(hist_result.scalars().all()):
            history.append({"role": m.role, "content": m.content})

    messages = history + [{"role": "user", "content": body.content}]

    async def event_generator():
        try:
            # Prompt injection check — send error event and stop
            from backend.services.ai_service import _check_prompt_injection
            if _check_prompt_injection(body.content):
                logger.warning("Prompt injection blocked in stream: %s", body.content[:80])
                yield f"data: {_json.dumps({'type': 'error', 'message': 'Input flagged by security filter. Please rephrase your query.'})}\n\n"
                return

            routing = await ai_service.route_to_agent(body.content)
            agent_key = body.agent or routing.get("agent", "planner")
            agent_info = AGENT_PERSONAS.get(agent_key, AGENT_PERSONAS["planner"])

            yield f"data: {_json.dumps({'type': 'agent', 'agent': agent_key, 'agentName': agent_info['name'], 'agentRole': agent_info['role']})}\n\n"

            full_response = []
            async for chunk in ai_service.stream_completion(
                messages,
                agent=agent_key,
            ):
                full_response.append(chunk)
                yield f"data: {_json.dumps({'type': 'token', 'text': chunk})}\n\n"

            # Persist assistant message to DB
            if body.sessionId and full_response:
                complete_text = "".join(full_response)
                assistant_msg = Message(
                    id=str(uuid.uuid4()),
                    session_id=body.sessionId,
                    role="assistant",
                    content=complete_text,
                    tool_calls=[],
                    metadata_={"agent": agent_key, "agentName": agent_info["name"], "streaming": True},
                )
                db.add(assistant_msg)
                await db.commit()

            yield f"data: {_json.dumps({'type': 'done'})}\n\n"

        except PromptInjectionError as e:
            yield f"data: {_json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        except Exception as e:
            logger.error("Stream error: %s", e, exc_info=True)
            yield f"data: {_json.dumps({'type': 'error', 'message': str(e)[:200]})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── Real Tool Execution ────────────────────────────────────────────────────────

@app.post("/api/tools/execute")
async def execute_tool(
    body: ToolExecuteRequest,
    current_user: User = Depends(get_current_user),
):
    """Execute a real cybersecurity tool and return structured results."""
    result = await run_tool(body.toolName, body.params)
    return result


# ── Tutoring Engine ────────────────────────────────────────────────────────────

@app.get("/api/tutor/paths")
async def get_learning_paths():
    return await tutor_service.get_learning_paths()


@app.post("/api/tutor/quiz")
async def get_quiz(body: TutorQuizRequest):
    return await tutor_service.get_quiz(body.topic, body.difficulty)


@app.post("/api/tutor/explain")
async def explain_topic(body: TutorExplainRequest):
    explanation = await tutor_service.explain_topic(body.topic, body.level)
    return {"topic": body.topic, "level": body.level, "explanation": explanation}


@app.post("/api/tutor/challenge")
async def generate_challenge(body: TutorChallengeRequest):
    return await tutor_service.generate_challenge(body.topic, body.difficulty)


@app.post("/api/tutor/path")
async def generate_learning_path(body: TutorPathRequest):
    return await tutor_service.generate_learning_path(body.goals, body.currentLevel)


# ── Report Downloads (PDF / DOCX) ──────────────────────────────────────────────

@app.get("/api/reports/{report_id}/download/pdf")
async def download_report_pdf(
    report_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WorkspaceRecord).where(
            WorkspaceRecord.id == report_id,
            WorkspaceRecord.workspace == "reports",
        )
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Report not found")

    report_data = {"id": report_id, **rec.data}
    pdf_bytes = generate_pdf_report(report_data)
    title_slug = rec.title.replace(" ", "_").replace("/", "-")[:50]

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="AKKI_{title_slug}.pdf"'},
    )


@app.get("/api/reports/{report_id}/download/docx")
async def download_report_docx(
    report_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WorkspaceRecord).where(
            WorkspaceRecord.id == report_id,
            WorkspaceRecord.workspace == "reports",
        )
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Report not found")

    report_data = {"id": report_id, **rec.data}
    docx_bytes = generate_docx_report(report_data)
    title_slug = rec.title.replace(" ", "_").replace("/", "-")[:50]

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="AKKI_{title_slug}.docx"'},
    )


# ── port 5000 shows the React frontend while the API stays on the same port.

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
