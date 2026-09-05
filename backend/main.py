# reload 1788245457
import os
import json
import uuid
import logging
import secrets
import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Any, Dict
from contextlib import asynccontextmanager

# Load environment variables — root first, then backend/ for service-specific keys
from dotenv import load_dotenv
load_dotenv()
load_dotenv("backend/.env", override=False)

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, Request, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, EmailStr
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, update, func, delete

from backend.database import get_db, init_db
from backend.models import User, Session, Message, Document, Memory, ToolRun, Finding, VoiceInteraction, WorkspaceRecord, Workflow, WorkflowStep
from backend.auth import hash_password, verify_password, create_access_token, get_current_user, security, revoke_token, decode_token
from fastapi.security import HTTPAuthorizationCredentials
from backend.services.ai_service import ai_service, AIQuotaError, PromptInjectionError, AGENT_PERSONAS, _parse_json
from backend.services.langgraph_agent_service import process_message, resume_message
from backend.services.tool_service import run_tool, ACTIVE_TOOLS
from backend.services.tutor_service import tutor_service
from backend.services.report_service import generate_pdf_report, generate_docx_report
from backend.services.emotional_ai_service import emotional_ai
from backend.services.workflow_service import workflow_service
from backend.services.marketplace_service import marketplace_service

logger = logging.getLogger("akki.main")

# ── Rate Limiter ──────────────────────────────────────────────────────────────

def _user_rate_key(request: Request) -> str:
    """Use user_id:role as the rate-limit key for authenticated requests;
    fall back to IP for anonymous traffic."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            from backend.auth import decode_token as _dt
            payload = _dt(auth[7:])
            uid = payload.get("userId", "")
            role = payload.get("role", "analyst")
            if uid:
                return f"user:{role}:{uid}"
        except Exception:
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=_user_rate_key, default_limits=["200/minute"])



@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Probe Ollama for local model availability (non-blocking)
    try:
        from backend.services.ollama_service import ollama_service
        await ollama_service.check_availability()
    except Exception:
        pass

    # Initialize sample marketplace items if none exist
    try:
        from backend.database import AsyncSessionLocal
        from backend.models import MarketplaceItem
        from sqlalchemy import select, func

        async with AsyncSessionLocal() as session:
            # Check if we already have marketplace items
            result = await session.execute(select(func.count(MarketplaceItem.id)))
            count = result.scalar()

            if count == 0:
                # Create some sample marketplace items
                sample_items = [
                    {
                        "name": "Nmap Network Scanner",
                        "description": "Powerful network discovery and security auditing tool",
                        "category": "tool",
                        "subcategory": "network_scanning",
                        "version": "7.90",
                        "author": "Nmap Team",
                        "repository_url": "https://github.com/nmap/nmap",
                        "documentation_url": "https://nmap.org/docs.html",
                        "install_command": "apt-get install nmap",
                        "config_schema": {
                            "type": "object",
                            "properties": {
                                "target": {"type": "string", "description": "Target IP or hostname"},
                                "ports": {"type": "string", "description": "Ports to scan (e.g., 80,443 or 1-1000)", "default": "1-1000"},
                                "scan_type": {"type": "string", "enum": ["quick", "intense", "vuln", "comprehensive"], "default": "quick"}
                            },
                            "required": ["target"]
                        },
                        "is_public": True,
                        "is_verified": True
                    },
                    {
                        "name": "Shodan API Integration",
                        "description": "Integrate with Shodan.io for device and network intelligence",
                        "category": "data_source",
                        "subcategory": "threat_intelligence",
                        "version": "2.1.0",
                        "author": "Shodan",
                        "repository_url": "https://github.com/shodan/shodan-python",
                        "documentation_url": "https://developer.shodan.io/",
                        "install_command": "pip install shodan",
                        "config_schema": {
                            "type": "object",
                            "properties": {
                                "api_key": {"type": "string", "description": "Shodan API key"},
                                "rate_limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 1}
                            },
                            "required": ["api_key"]
                        },
                        "is_public": True,
                        "is_verified": True
                    }
                ]

                for item_data in sample_items:
                    marketplace_item = MarketplaceItem(
                        id=str(__import__('uuid').uuid4()),
                        user_id=None,  # System-provided items
                        **item_data
                    )
                    session.add(marketplace_item)

                await session.commit()
    except Exception as e:
        # Don't fail the application if sample data creation fails
        import logging
        logging.getLogger("akki.main").warning(f"Failed to create sample marketplace items: {e}")

    yield


app = FastAPI(title="AKKI AI Cybersecurity Platform", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# Compress all responses ≥ 1 KB — reduces payload by ~70% for JSON
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:5174"],
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
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://fonts.googleapis.com https://kit.fontawesome.com https://ka-f.fontawesome.com https://replit.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://ka-f.fontawesome.com; "
        "font-src 'self' https://fonts.gstatic.com https://ka-f.fontawesome.com data:; "
        "img-src 'self' data: blob: https:; "
        "connect-src 'self' https://api.elevenlabs.io https://api.tavily.com wss: ws:; "
        "media-src 'self' blob:;"
    )
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


# ── Pydantic schemas (imported from backend.schemas) ─────────────────────────
from backend.schemas import *
def workflow_to_dict(w: Workflow) -> dict:
    return {
        "id": w.id,
        "userId": w.user_id,
        "name": w.name,
        "description": w.description,
        "isActive": w.is_active,
        "createdAt": w.created_at.isoformat() if w.created_at else None,
        "updatedAt": w.updated_at.isoformat() if w.updated_at else None,
    }


def workflow_step_to_dict(s: WorkflowStep) -> dict:
    return {
        "id": s.id,
        "workflowId": s.workflow_id,
        "stepOrder": s.step_order,
        "agentType": s.agent_type,
        "promptTemplate": s.prompt_template,
        "config": s.config,
        "createdAt": s.created_at.isoformat() if s.created_at else None,
    }


def user_to_dict(user: User) -> dict:
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



# ── Parallel pre-fetch helpers ─────────────────────────────────────────────────

async def _prefetch_rag(content: str, session_id: str | None, owner_id: str) -> str:
    """Retrieve RAG context — called concurrently with routing and memory fetch."""
    try:
        from backend.services.rag_service import rag_service
        from backend.database import AsyncSessionLocal
        active_doc_groups: list[str] | None = None
        if session_id:
            async with AsyncSessionLocal() as _s:
                _r = await _s.execute(select(Session).where(Session.id == session_id))
                _sess = _r.scalar_one_or_none()
                if _sess:
                    active_doc_groups = (_sess.context or {}).get("activeDocGroups")
        return await rag_service.retrieve_context(
            query=content, top_k=4, owner_id=owner_id, group_filter=active_doc_groups
        )
    except Exception as _e:
        logger.debug("[RAG prefetch] %s", _e)
        return ""


async def _prefetch_memory(user_id: str) -> str:
    """Fetch user long-term memories — called concurrently with routing and RAG."""
    try:
        from backend.database import AsyncSessionLocal
        async with AsyncSessionLocal() as _s:
            _r = await _s.execute(
                select(Memory)
                .where(Memory.user_id == user_id, Memory.type.in_(["semantic", "episodic", "procedural"]))
                .order_by(desc(Memory.strength), desc(Memory.last_accessed_at))
                .limit(6)
            )
            mems = _r.scalars().all()
            lines = [f"- [{m.type}] {(m.content or {}).get('summary', '')}" for m in mems if (m.content or {}).get("summary")]
            if lines:
                # Fire-and-forget update of last_accessed_at
                ids = [m.id for m in mems]
                await _s.execute(
                    update(Memory).where(Memory.id.in_(ids))
                    .values(last_accessed_at=datetime.now(timezone.utc))
                )
                await _s.commit()
            return "\n".join(lines)
    except Exception as _e:
        logger.debug("[Memory prefetch] %s", _e)
        return ""


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


async def _extract_and_store_memories(user_id: str, user_message: str, ai_response: str) -> None:
    """Background task: extract semantic/episodic/procedural memories from a conversation turn."""
    import json as _json
    if len(ai_response) < 80 or len(user_message) < 10:
        return
    try:
        from backend.services.ai_service import ai_service as _ai
        prompt = f"""Extract important facts about this user from this conversation turn that should be remembered long-term.

User said: {user_message[:400]}
AI responded: {ai_response[:600]}

Return JSON with this shape:
{{"memories": [
  {{"type": "semantic", "summary": "User is a Python developer with 3 years experience", "importance": 0.8}},
  {{"type": "episodic", "summary": "User asked how Kerberoasting works", "importance": 0.6}},
  {{"type": "procedural", "summary": "User is learning SQL injection exploitation techniques", "importance": 0.7}}
]}}

Memory types:
- semantic: persistent facts about user (skills, preferences, background, tools they use)
- episodic: notable topics from THIS conversation worth remembering
- procedural: things user is actively learning or practising

Rules:
- Only include memories with importance > 0.55
- Max 2 memories per turn
- Return {{"memories": []}} if nothing important to remember
- Summaries must be concise (under 120 chars)"""

        raw = await _ai.chat_completion(
            [{"role": "user", "content": prompt}],
            json_mode=True,
            temperature=0.1,
        )
        parsed = _json.loads(raw)
        new_memories = [m for m in parsed.get("memories", []) if float(m.get("importance", 0)) > 0.55]
        if not new_memories:
            return

        from backend.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            for mem_data in new_memories[:2]:
                importance = float(mem_data.get("importance", 0.6))
                mem = Memory(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    type=mem_data.get("type", "episodic"),
                    content={
                        "summary": mem_data.get("summary", ""),
                        "details": {"source": "chat_extraction"},
                        "importance": importance,
                    },
                    strength=importance,
                    expires_at=None,
                )
                session.add(mem)
            await session.commit()
    except Exception as e:
        logger.debug("[Memory] Extraction failed: %s", e)

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


@app.get("/api/protected/stats")
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Real-time platform statistics for the dashboard."""
    uid = current_user.id
    from sqlalchemy import func, and_
    from backend.models import Session, Message, WorkspaceRecord, Document

    # Total messages sent by this user (across all sessions)
    msg_count_result = await db.execute(
        select(func.count(Message.id))
        .join(Session, Session.id == Message.session_id)
        .where(Session.owner_id == uid)
    )
    total_messages = msg_count_result.scalar() or 0

    # Total workspace records by type
    rec_result = await db.execute(
        select(WorkspaceRecord.record_type, func.count(WorkspaceRecord.id))
        .where(WorkspaceRecord.user_id == uid)
        .group_by(WorkspaceRecord.record_type)
    )
    by_type: dict[str, int] = {row[0]: row[1] for row in rec_result.all()}
    total_reports = by_type.get("report", 0)
    total_scans = by_type.get("analysis", 0) + by_type.get("exploit", 0)
    total_sessions = await db.scalar(
        select(func.count(Session.id)).where(Session.owner_id == uid)
    ) or 0

    # RAG: check if any embedded documents exist for this user
    rag_doc_count = await db.scalar(
        select(func.count(Document.id))
        .where(Document.owner_id == uid, Document.embedded_at.isnot(None))
    ) or 0

    # Agents are always all 7 (they're code, not processes)
    agents_online = 7

    return {
        "totalConversations": total_sessions,
        "totalMessages": total_messages,
        "activeAgents": agents_online,
        "reportsGenerated": total_reports,
        "scansRun": total_scans,
        "ragDocuments": rag_doc_count,
        "ragActive": rag_doc_count > 0,
    }


@app.get("/api/voice/test")
async def test_voice():
    """Test ElevenLabs TTS with a short phrase. Returns audio/mpeg on success."""
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    voice_id = os.environ.get("ELEVENLABS_DEFAULT_VOICE", "pNInz6obpgDQGcFmaJgB")
    if not api_key:
        return {"status": "no_key", "message": "ELEVENLABS_API_KEY not set in root .env file"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": "Hello! ElevenLabs is connected and working.",
                    "model_id": "eleven_turbo_v2_5",
                    "voice_settings": {
                        "stability": 0.45,
                        "similarity_boost": 0.80,
                        "style": 0.35,
                        "use_speaker_boost": True,
                    },
                },
            )
        if resp.status_code == 200:
            from fastapi.responses import Response as FastAPIResponse
            return FastAPIResponse(
                content=resp.content,
                media_type="audio/mpeg",
                headers={"X-Test": "ok"},
            )
        # Return full error so frontend can display it
        try:
            err_json = resp.json()
            err_msg = err_json.get("detail", {})
            if isinstance(err_msg, dict):
                err_msg = err_msg.get("message", resp.text[:300])
        except Exception:
            err_msg = resp.text[:300]
        return {"status": "error", "code": resp.status_code, "message": str(err_msg)}
    except Exception as exc:
        return {"status": "error", "message": f"Network error: {exc}"}


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


@app.post("/api/auth/logout")
async def logout(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_user),
):
    """Revoke the current token immediately."""
    token = credentials.credentials
    # Calculate remaining TTL (7 days - elapsed)
    try:
        payload = decode_token(token)
        import time as _time
        remaining = max(0, int(payload.get("exp", 0) - _time.time()))
    except Exception:
        remaining = 604800
    await revoke_token(token, expires_in_seconds=remaining or 604800)
    return {"success": True, "message": "Logged out"}


@app.post("/api/auth/refresh")
async def refresh_token_endpoint(
    current_user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Issue a new token and revoke the old one."""
    old_token = credentials.credentials
    # Revoke old token
    try:
        payload = decode_token(old_token)
        import time as _time
        remaining = max(0, int(payload.get("exp", 0) - _time.time()))
        await revoke_token(old_token, expires_in_seconds=remaining or 604800)
    except Exception:
        pass
    # Issue new token
    new_token = create_access_token(str(current_user.id), current_user.role)
    return {"token": new_token, "user": user_to_dict(current_user)}

@app.post("/api/auth/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(request: Request, body: dict, db: AsyncSession = Depends(get_db)):
    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email required")
    # Always return success to prevent email enumeration
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        # In production: send reset email here via SMTP
        reset_token = secrets.token_urlsafe(32)
        logger.info(f"[ForgotPassword] Reset requested for {email}, token: {reset_token}")
    return {"success": True, "message": "If an account with that email exists, a reset link has been sent."}

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


# ── Profile: emotional-state sub-route ────────────────────────────────────────

@app.get("/api/protected/profile/emotional-state")
async def get_emotional_state(current_user: User = Depends(get_current_user)):
    return {"emotionalState": current_user.emotional_state or {
        "bondLevel": 0,
        "currentMood": "neutral",
        "trustLevel": 0.5,
        "personalityTraits": [],
        "preferredCommunicationStyle": "professional"
    }}


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
    before: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    LIMIT = 30
    if before:
        ref_result = await db.execute(
            select(Message.created_at).where(Message.id == before)
        )
        ref_ts = ref_result.scalar_one_or_none()
        if ref_ts is None:
            raise HTTPException(status_code=404, detail="Reference message not found")
        result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .where(Message.created_at < ref_ts)
            .order_by(desc(Message.created_at))
            .limit(LIMIT + 1)
        )
    else:
        result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(desc(Message.created_at))
            .limit(LIMIT + 1)
        )
    messages = result.scalars().all()
    has_more = len(messages) > LIMIT
    messages = list(reversed(messages[:LIMIT]))
    return {"messages": [message_to_dict(m) for m in messages], "hasMore": has_more}


@app.patch("/api/protected/sessions/{session_id}")
async def rename_session(
    session_id: str,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Session).where(Session.id == session_id, Session.owner_id == current_user.id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if "title" in body:
        session.title = body["title"][:120]
    await db.commit()
    return session_to_dict(session)


@app.delete("/api/protected/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Session).where(Session.id == session_id, Session.owner_id == current_user.id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    # Delete associated messages first
    await db.execute(delete(Message).where(Message.session_id == session_id))
    await db.delete(session)
    await db.commit()
    return {"success": True}


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
        agent_response = await process_message(
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
        # When the agent paused to run an active/attacking tool, the chat
        # message response carries this so the client can prompt for approval
        # and then call /api/protected/chat/resume.
        "status": agent_response.get("status"),
        "pendingApproval": agent_response.get("pendingApproval"),
    }


@app.post("/api/protected/chat/resume")
@limiter.limit("60/minute")
async def chat_resume(
    request: Request,
    body: ChatResumeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resume a paused agent turn after the user approves/denies an active
    (attacking) tool the agent requested. Continues the LangGraph run from its
    checkpointed interrupt for this session."""
    result = await resume_message(session_id=body.sessionId, approved=body.approved)

    # Persist the agent's post-resume message so the conversation stays whole.
    assistant_msg = Message(
        id=str(uuid.uuid4()),
        session_id=body.sessionId,
        role="assistant",
        content=result.get("content", ""),
        tool_calls=result.get("toolCalls", []),
        metadata_={"resumedApproved": body.approved, "status": result.get("status")},
    )
    db.add(assistant_msg)
    await db.commit()
    await db.refresh(assistant_msg)

    return {
        "assistantMessage": {
            **message_to_dict(assistant_msg),
            "agent": result.get("agent", "analyst"),
            "toolCalls": result.get("toolCalls", []),
        },
        "sessionId": body.sessionId,
        "status": result.get("status"),
        "pendingApproval": result.get("pendingApproval"),
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
    """
    Text-to-Speech via ElevenLabs.
    Returns raw MP3 audio bytes as a streaming response.
    Falls back to a JSON stub if ELEVENLABS_API_KEY is not set.
    """
    body = await request.json()
    text: str = body.get("text", "").strip()
    voice_id: str = body.get("voiceId", os.environ.get("ELEVENLABS_DEFAULT_VOICE", "pNInz6obpgDQGcFmaJgB"))
    model_id: str = body.get("modelId", "eleven_turbo_v2_5")
    stability: float = float(body.get("stability", 0.45))
    similarity: float = float(body.get("similarity", 0.80))
    style: float = float(body.get("style", 0.35))
    speed: float = float(body.get("speed", 1.0))

    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        logger.warning("[Voice] ELEVENLABS_API_KEY not set — returning stub")
        return {"audioData": None, "text": text, "status": "no_key"}

    if not text:
        return {"audioData": None, "text": "", "status": "empty"}

    # Truncate to ElevenLabs safe limit
    text = text[:2500]

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": text,
                    "model_id": model_id,
                    "voice_settings": {
                        "stability": stability,
                        "similarity_boost": similarity,
                        "style": style,
                        "use_speaker_boost": True,
                    },
                    "output_format": "mp3_44100_128",
                },
            )

        if resp.status_code == 200:
            from fastapi.responses import Response as FastAPIResponse
            return FastAPIResponse(
                content=resp.content,
                media_type="audio/mpeg",
                headers={
                    "X-Voice-Id": voice_id,
                    "X-Text-Length": str(len(text)),
                    "Cache-Control": "no-cache",
                },
            )
        else:
            detail = resp.text[:200]
            logger.error("[Voice] ElevenLabs error %d: %s", resp.status_code, detail)
            raise HTTPException(status_code=502, detail=f"ElevenLabs error: {detail}")

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[Voice] ElevenLabs request failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


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



@app.post("/api/protected/memory")
async def create_memory_manual(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually pin a memory (user-created semantic knowledge)."""
    summary = (body.get("summary") or "").strip()
    if not summary or len(summary) > 500:
        raise HTTPException(status_code=400, detail="summary must be 1–500 characters")
    mem_type = body.get("type", "semantic")
    if mem_type not in ("semantic", "episodic", "procedural"):
        mem_type = "semantic"
    mem = Memory(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        type=mem_type,
        content={"summary": summary, "details": {"source": "manual", "userCreated": True}, "importance": 0.8},
        strength=0.8,
        expires_at=None,
    )
    db.add(mem)
    await db.commit()
    await db.refresh(mem)
    return {
        "id": mem.id,
        "type": mem.type,
        "content": mem.content,
        "strength": mem.strength,
        "createdAt": mem.created_at.isoformat() if mem.created_at else None,
    }
@app.delete("/api/protected/memory/{memory_id}")
async def delete_memory(
    memory_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Memory).where(Memory.id == memory_id, Memory.user_id == current_user.id)
    )
    mem = result.scalar_one_or_none()
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found")
    await db.delete(mem)
    await db.commit()
    return {"success": True, "id": memory_id}

# ── SIGMA Mathematical Reasoning Engine ──────────────────────────────────────

@app.post("/api/protected/sigma/solve")
@limiter.limit("20/minute")
async def sigma_solve(
    request: Request,
    body: SigmaRequest,
    current_user: User = Depends(get_current_user),
):
    """SIGMA Mathematical Reasoning Engine — formulate, prove, implement."""
    from backend.services.ai_service import ai_service

    statement = body.statement.strip()
    if not statement:
        raise HTTPException(status_code=400, detail="statement required")

    # Build the prompt — include answers to clarifying questions if provided
    if body.answers:
        answers_text = "\n".join(f"Q: {q}\nA: {a}" for q, a in body.answers.items())
        prompt = f"""Problem statement: {statement}

User's answers to clarifying questions:
{answers_text}

Now produce the full mathematical solution."""
    else:
        prompt = f"""Problem statement: {statement}

First, determine if this problem statement is sufficiently specified for a rigorous mathematical solution.
If clarification is needed, respond ONLY with JSON: {{"needs_clarification": true, "questions": ["...", "..."]}}
Otherwise, produce the full solution with all Σ sections."""

    try:
        result = await ai_service.chat_completion(
            [{"role": "user", "content": prompt}],
            agent="sigma",
            user_id=str(current_user.id),
        )

        # Try to detect JSON clarification response
        import json as _json
        stripped = result.strip()
        if stripped.startswith("{") and "needs_clarification" in stripped:
            try:
                parsed = _json.loads(stripped)
                if parsed.get("needs_clarification"):
                    return {"needs_clarification": True, "questions": parsed.get("questions", []), "solution": None}
            except Exception:
                pass

        return {"needs_clarification": False, "questions": [], "solution": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

        analysis = await ai_service.process_cybersecurity_message(text, user_id=str(current_user.id))
        return {"analysis": analysis, "filesAnalyzed": 0, "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Exploit generation ────────────────────────────────────────────────────────

@app.post("/api/protected/exploits/generate")
async def generate_exploit_protected(body: ExploitPoCRequest, current_user: User = Depends(get_current_user)):
    try:
        exploit = await ai_service.generate_exploit_poc(body.vulnerability, body.target, body.constraints, user_id=str(current_user.id))
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
        strategy = await ai_service.generate_osint_strategy(body.target, body.objectives, body.constraints, user_id=str(current_user.id))
        return {
            "strategy": strategy,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "disclaimer": "Ensure all reconnaissance activities are authorized and legal",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Protected reports ─────────────────────────────────────────────────────────

@app.post("/api/protected/reports/generate")
async def generate_report_protected(body: ReportGenerationRequest, current_user: User = Depends(get_current_user)):
    try:
        # If using a template, load it first
        sections = body.sections
        if body.templateId:
            # Load template sections (implementation would fetch from database)
            # For now, we'll proceed with the provided sections
            pass

        # If no custom sections provided, use default behavior for backward compatibility
        if not sections:
            report = await ai_service.generate_pentest_report(
                body.findings,
                body.executiveSummary,
                body.scope,
                user_id=str(current_user.id)
            )
            return {
                "report": report,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        # Generate custom report based on sections
        report = await ai_service.generate_custom_report(
            findings=body.findings,
            executive_summary=body.executiveSummary,
            scope=body.scope,
            sections=sections,
            title=body.title,
            report_type=body.reportType,
            user_id=str(current_user.id)
        )
        return {
            "report": report,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Report Configuration Management ───────────────────────────────────────────

@app.post("/api/protected/report-sections")
@limiter.limit("20/minute")
async def create_report_section_template(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    section_type: str = Form(...),
    content_template: str = Form(...),
    is_public: bool = Form(False),
    current_user: User = Depends(get_current_user),
):
    try:
        from backend.database import AsyncSessionLocal
        from backend.models import ReportSectionTemplate

        async with AsyncSessionLocal() as session:
            template = ReportSectionTemplate(
                id=str(__import__('uuid').uuid4()),
                user_id=current_user.id,
                name=name,
                description=description,
                section_type=section_type,
                content_template=content_template,
                is_public=is_public
            )
            session.add(template)
            await session.commit()
            await session.refresh(template)

            return {
                "id": template.id,
                "name": template.name,
                "description": template.description,
                "section_type": template.section_type,
                "is_public": template.is_public,
                "createdAt": template.created_at.isoformat() if template.created_at else None,
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/protected/report-sections")
async def get_report_section_templates(
    include_public: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        from backend.models import ReportSectionTemplate
        from sqlalchemy import select, or_

        query = select(ReportSectionTemplate).where(
            ReportSectionTemplate.user_id == current_user.id
        )
        if include_public:
            query = query.where(
                or_(
                    ReportSectionTemplate.user_id == current_user.id,
                    ReportSectionTemplate.is_public == True
                )
            )

        result = await db.execute(query.order_by(ReportSectionTemplate.created_at.desc()))
        templates = result.scalars().all()

        return [{
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "section_type": t.section_type,
            "is_public": t.is_public,
            "createdAt": t.created_at.isoformat() if t.created_at else None,
            "updatedAt": t.updated_at.isoformat() if t.updated_at else None,
        } for t in templates]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/protected/report-configurations")
@limiter.limit("20/minute")
async def save_report_configuration(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    sections: str = Form(...),  # JSON string
    is_default: bool = Form(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        from backend.models import ReportConfiguration
        import json

        sections_list = json.loads(sections)

        # If setting as default, unset other defaults
        if is_default:
            from sqlalchemy import update
            await db.execute(
                update(ReportConfiguration)
                .where(ReportConfiguration.user_id == current_user.id)
                .values(is_default=False)
            )

        config = ReportConfiguration(
            id=str(__import__('uuid').uuid4()),
            user_id=current_user.id,
            name=name,
            description=description,
            sections=sections_list,
            is_default=is_default
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)

        return {
            "id": config.id,
            "name": config.name,
            "description": config.description,
            "sections": config.sections,
            "is_default": config.is_default,
            "createdAt": config.created_at.isoformat() if config.created_at else None,
            "updatedAt": config.updated_at.isoformat() if config.updated_at else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/protected/report-configurations")
async def get_report_configurations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        from backend.models import ReportConfiguration
        from sqlalchemy import select

        result = await db.execute(
            select(ReportConfiguration)
            .where(ReportConfiguration.user_id == current_user.id)
            .order_by(desc(ReportConfiguration.is_default), desc(ReportConfiguration.created_at))
        )
        configs = result.scalars().all()

        return [{
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "sections": c.sections,
            "is_default": c.is_default,
            "createdAt": c.created_at.isoformat() if c.created_at else None,
            "updatedAt": c.updated_at.isoformat() if c.updated_at else None,
        } for c in configs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/protected/report-configurations/{config_id}")
async def delete_report_configuration(
    config_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        from backend.models import ReportConfiguration
        from sqlalchemy import delete

        result = await db.execute(
            delete(ReportConfiguration)
            .where(
                ReportConfiguration.id == config_id,
                ReportConfiguration.user_id == current_user.id
            )
        )
        await db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Configuration not found")

        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Tools ─────────────────────────────────────────────────────────────────────

TOOL_RISK = {"nmap": "high", "whois": "low", "dns_lookup": "low", "port_scan": "medium"}

@app.get("/api/protected/tools/pending")
async def get_pending_tools(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ToolRun).where(
            ToolRun.status == "pending",
            ToolRun.approval_required == True,
        ).order_by(desc(ToolRun.created_at)).limit(20)
    )
    runs = result.scalars().all()
    return [
        {
            "id": r.id,
            "toolName": r.tool_name,
            "arguments": r.arguments,
            "riskLevel": r.risk_level,
        }
        for r in runs
    ]


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
        # Run the real tool instead of returning a simulation stub
        try:
            from backend.services.tool_service import run_tool
            tool_result = await run_tool(body.toolName, body.arguments)
        except Exception as tool_err:
            logger.error("[ToolExec] %s failed: %s", body.toolName, tool_err)
            tool_result = {"success": False, "error": str(tool_err), "tool": body.toolName}

        tool_run.status = "completed"
        tool_run.result = tool_result
        tool_run.executed_at = datetime.now(timezone.utc)
        tool_run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        return {"toolRun": {"id": tool_run.id, "status": tool_run.status}, "result": tool_result, "requiresApproval": False}


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
    tool_run.approved_by = current_user.id
    tool_run.approved_at = datetime.now(timezone.utc)
    tool_run.executed_at = datetime.now(timezone.utc)

    # Now actually run the approved tool
    try:
        from backend.services.tool_service import run_tool
        tool_result = await run_tool(tool_run.tool_name, tool_run.arguments or {})
    except Exception as tool_err:
        logger.error("[ToolApprove] %s failed: %s", tool_run.tool_name, tool_err)
        tool_result = {"success": False, "error": str(tool_err), "tool": tool_run.tool_name}

    tool_run.status = "completed"
    tool_run.result = tool_result
    tool_run.completed_at = datetime.now(timezone.utc)
    await db.commit()

    return {"success": True, "result": tool_result}


# ── RAG ───────────────────────────────────────────────────────────────────────

@app.post("/api/protected/rag/ingest")
async def rag_ingest(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(None),
    tags: str = Form("[]"),
    current_user: User = Depends(get_current_user),
):
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 50 MB.")
    try:
        from backend.services.rag_service import rag_service
        parsed_tags = json.loads(tags) if tags else []
        background_tasks.add_task(
            rag_service.ingest_document,
            file_content=content,
            title=title or file.filename or "Untitled",
            owner_id=current_user.id,
            tags=parsed_tags,
            content_type=file.content_type or "text/plain",
            filename=file.filename or "unknown"
        )
        return {"status": "processing", "message": "Document is being processed in the background"}
    except ImportError:
        # Fallback: basic ingest without CRAG pipeline
        from backend.database import AsyncSessionLocal
        doc = Document(
            id=str(uuid.uuid4()),
            owner_id=current_user.id,
            title=title or file.filename or "Untitled",
            type=file.content_type or "text/plain",
            content=content.decode("utf-8", errors="ignore")[:50000],
            tags=json.loads(tags) if tags else [],
            metadata_={"size": len(content), "mimeType": file.content_type},
        )
        async with AsyncSessionLocal() as session:
            session.add(doc)
            await session.commit()
            await session.refresh(doc)
        return {"id": doc.id, "title": doc.title, "type": doc.type, "status": "ingested"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/protected/rag/query")
async def rag_query(request: Request, current_user: User = Depends(get_current_user)):
    body = await request.json()
    query = body.get("query", "")
    top_k = body.get("topK", 5)
    filters = body.get("filters", None)
    try:
        from backend.services.rag_service import rag_service
        result = await rag_service.query(query=query, top_k=top_k, filters=filters, user_id=str(current_user.id))
        return result
    except ImportError:
        # Fallback: simple AI response without CRAG
        result = await ai_service.process_cybersecurity_message(
            f"Answer this query based on your knowledge: {query}",
            user_id=str(current_user.id)
        )
        return {"results": [{"content": result, "score": 0.9, "source": "AI Knowledge Base"}]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/protected/rag/documents")
async def get_rag_documents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all documents uploaded by the current user."""
    result = await db.execute(
        select(Document)
        .where(Document.owner_id == current_user.id)
        .order_by(desc(Document.created_at))
        .limit(50)
    )
    docs = result.scalars().all()
    return [
        {
            "id": d.id,
            "title": d.title,
            "type": d.type,
            "tags": d.tags or [],
            "createdAt": d.created_at.isoformat() if d.created_at else None,
            "embeddedAt": d.embedded_at.isoformat() if d.embedded_at else None,
        }
        for d in docs
    ]


@app.delete("/api/protected/rag/documents/{document_id}")
async def delete_rag_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a document and its chunks."""
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.delete(doc)  # CASCADE deletes chunks
    await db.commit()
    return {"success": True, "id": document_id}


@app.get("/api/protected/rag/groups")
async def get_rag_groups(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all document groups (unique tags) with their documents."""
    result = await db.execute(
        select(Document)
        .where(Document.owner_id == current_user.id)
        .order_by(desc(Document.created_at))
    )
    docs = result.scalars().all()
    groups: dict[str, list[dict]] = {}
    ungrouped: list[dict] = []
    for doc in docs:
        info = {
            "id": doc.id,
            "title": doc.title,
            "type": doc.type,
            "tags": doc.tags or [],
            "embeddedAt": doc.embedded_at.isoformat() if doc.embedded_at else None,
            "createdAt": doc.created_at.isoformat() if doc.created_at else None,
        }
        if not doc.tags:
            ungrouped.append(info)
        else:
            for tag in doc.tags:
                groups.setdefault(tag, []).append(info)
    return {
        "groups": [{"name": k, "docs": v} for k, v in sorted(groups.items())],
        "ungrouped": ungrouped,
    }


@app.patch("/api/protected/rag/documents/{document_id}/tags")
async def update_doc_tags(
    document_id: str,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update group membership (tags) for a document."""
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    tags = [str(t).strip() for t in (body.get("tags") or []) if str(t).strip()]
    doc.tags = tags
    await db.commit()
    return {"id": doc.id, "title": doc.title, "tags": doc.tags}


@app.delete("/api/protected/rag/groups/{group_name}")
async def delete_rag_group(
    group_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a group tag from ALL user documents (does not delete the documents)."""
    result = await db.execute(
        select(Document).where(Document.owner_id == current_user.id)
    )
    docs = result.scalars().all()
    updated = 0
    for doc in docs:
        if doc.tags and group_name in doc.tags:
            doc.tags = [t for t in doc.tags if t != group_name]
            updated += 1
    await db.commit()
    return {"success": True, "updated": updated}


@app.patch("/api/protected/sessions/{session_id}/doc-groups")
async def set_session_doc_groups(
    session_id: str,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set which document groups are active for a chat session.

    body.groups: list[str] | null
    - null or empty → use ALL embedded documents (default)
    - ["GroupA","GroupB"] → only retrieve from docs tagged with those groups
    """
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.owner_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    ctx = dict(session.context or {})
    groups = body.get("groups")  # None means deactivate / use all
    ctx["activeDocGroups"] = groups if groups else None
    session.context = ctx
    await db.commit()
    return {"sessionId": session_id, "activeDocGroups": ctx["activeDocGroups"]}


# ── Workflow Management ───────────────────────────────────────────────────────────

@app.post("/api/protected/workflows")
@limiter.limit("20/minute")
async def create_workflow(
    request: Request,
    body: WorkflowCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        workflow = await workflow_service.create_workflow(
            user_id=current_user.id,
            name=body.name,
            description=body.description,
            steps=[step.dict() for step in body.steps]
        )
        return workflow_to_dict(workflow)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/protected/workflows")
async def get_workflows(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        workflows = await workflow_service.get_workflows(user_id=current_user.id)
        return [workflow_to_dict(w) for w in workflows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/protected/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    current_user: User = Depends(  get_current_user  ),
       db:  AsyncSession  =  Depends(  get_db  ),
   ):
    try:
        workflow = await workflow_service.get_workflow(
            workflow_id=workflow_id,
            user_id=current_user.id
        )
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return workflow_to_dict(workflow)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/protected/workflows/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    body: WorkflowUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        workflow = await workflow_service.update_workflow(
            workflow_id=workflow_id,
            user_id=current_user.id,
            name=body.name,
            description=body.description,
            is_active=body.is_active
        )
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return workflow_to_dict(workflow)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/protected/workflows/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        success = await workflow_service.delete_workflow(
            workflow_id=workflow_id,
            user_id=current_user.id
        )
        if not success:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/protected/workflows/{workflow_id}/steps")
@limiter.limit("20/minute")
async def add_workflow_step(request: Request, workflow_id: str, body: WorkflowStepRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        step = await workflow_service.add_step(
            workflow_id=workflow_id,
            user_id=current_user.id,
            agent_type=body.agent_type,
            prompt_template=body.prompt_template,
            config=body.config
        )
        if not step:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return workflow_step_to_dict(step)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/protected/workflows/steps/{step_id}")
async def update_workflow_step(
    step_id: str,
    body: WorkflowStepUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        step = await workflow_service.update_step(
            step_id=step_id,
            user_id=current_user.id,
            agent_type=body.agent_type,
            prompt_template=body.prompt_template,
            config=body.config,
            step_order=body.step_order
        )
        if not step:
            raise HTTPException(status_code=404, detail="Step not found")
        return workflow_step_to_dict(step)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/protected/workflows/steps/{step_id}")
async def delete_workflow_step(
    step_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        success = await workflow_service.delete_step(
            step_id=step_id,
            user_id=current_user.id
        )
        if not success:
            raise HTTPException(status_code=404, detail="Step not found")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/protected/workflows/{workflow_id}/reorder")
async def reorder_workflow_steps(
    workflow_id: str,
    body: WorkflowReorderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        success = await workflow_service.reorder_steps(
            workflow_id=workflow_id,
            user_id=current_user.id,
            step_orders=body.step_orders
        )
        if not success:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/protected/workflows/{workflow_id}/execute")
@limiter.limit("10/minute")
async def execute_workflow(request: Request, workflow_id: str, body: WorkflowExecutionRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Create session if needed before entering the generator (db dep is only valid here)
    session_id = body.session_id
    if not session_id:
        new_session = Session(
            id=str(uuid.uuid4()),
            owner_id=current_user.id,
            title=f"Workflow Execution - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            mode="workflow",
            context={"workflow_id": workflow_id},
        )
        db.add(new_session)
        await db.commit()
        await db.refresh(new_session)
        session_id = new_session.id

    # Load workflow + steps while db dep is still valid; raises HTTPException on failure
    try:
        workflow = await workflow_service.get_workflow(workflow_id, current_user.id)
        if not workflow:
            raise HTTPException(status_code=400, detail="Workflow not found or access denied")
        steps = await workflow_service.get_workflow_steps(workflow_id, current_user.id)
        if not steps:
            raise HTTPException(status_code=400, detail="Workflow has no steps to execute")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Capture primitive values for the generator closure (model objects may detach)
    user_id = current_user.id
    initial_input = body.initial_input
    workflow_name = workflow.name

    async def sse_generator():
        context: Dict[str, Any] = {
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "user_id": user_id,
            "session_id": session_id,
            "initial_input": initial_input,
            "previous_output": initial_input,
            "step_results": []
        }
        for i, step in enumerate(steps):
            yield f"data: {json.dumps({'type': 'step_start', 'stepId': step.id, 'name': step.agent_type, 'index': i})}\n\n"
            prompt = step.prompt_template.replace("{input}", context["previous_output"])
            for key, value in step.config.items():
                if isinstance(value, str) and "{" in value and "}" in value:
                    prompt = prompt.replace("{" + key + "}", str(context.get(key, "")))
            try:
                agent_response = await process_message(
                    message=prompt,
                    session_id=session_id,
                    user_id=user_id,
                    context={
                        "workflow_step": True,
                        "step_id": step.id,
                        "agent_type": step.agent_type,
                        "workflow_context": context
                    }
                )
                step_result = {
                    "step_id": step.id,
                    "agent_type": step.agent_type,
                    "prompt": prompt,
                    "response": agent_response.get("content", ""),
                    "agent": agent_response.get("agent", "planner"),
                    "toolCalls": agent_response.get("toolCalls", []),
                    "ragUsed": agent_response.get("ragUsed", False),
                    "sources": agent_response.get("sources", []),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                context["step_results"].append(step_result)
                context["previous_output"] = agent_response.get("content", "")
                yield f"data: {json.dumps({'type': 'step_done', 'stepId': step.id, 'result': str(agent_response.get('content', ''))[:500]})}\n\n"
            except Exception as e:
                step_result = {
                    "step_id": step.id,
                    "agent_type": step.agent_type,
                    "prompt": prompt,
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                context["step_results"].append(step_result)
                yield f"data: {json.dumps({'type': 'step_error', 'stepId': step.id, 'error': str(e)[:200]})}\n\n"
                if not step.config.get("continue_on_error", False):
                    break
        yield f"data: {json.dumps({'type': 'done', 'stepsExecuted': len(context['step_results']), 'totalSteps': len(steps)})}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

# ── Marketplace ──────────────────────────────────────────────────────────────

@app.post("/api/protected/marketplace/items")
@limiter.limit("20/minute")
async def create_marketplace_item(
    request: Request,
    body: MarketplaceItemCreateRequest,
    current_user: User = Depends(get_current_user)
):
    try:
        marketplace_item = await marketplace_service.create_marketplace_item(
            name=body.name,
            description=body.description,
            category=body.category,
            subcategory=body.subcategory,
            version=body.version,
            author=body.author,
            repository_url=body.repository_url,
            documentation_url=body.documentation_url,
            install_command=body.install_command,
            config_schema=body.config_schema,
            is_public=body.is_public,
            is_verified=body.is_verified,
            user_id=current_user.id
        )
        return {
            "id": marketplace_item.id,
            "name": marketplace_item.name,
            "description": marketplace_item.description,
            "category": marketplace_item.category,
            "subcategory": marketplace_item.subcategory,
            "version": marketplace_item.version,
            "author": marketplace_item.author,
            "repository_url": marketplace_item.repository_url,
            "documentation_url": marketplace_item.documentation_url,
            "install_command": marketplace_item.install_command,
            "is_public": marketplace_item.is_public,
            "is_verified": marketplace_item.is_verified,
            "download_count": marketplace_item.download_count,
            "rating": marketplace_item.rating,
            "createdAt": marketplace_item.created_at.isoformat() if marketplace_item.created_at else None,
            "updatedAt": marketplace_item.updated_at.isoformat() if marketplace_item.updated_at else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/protected/marketplace/items")
async def get_marketplace_items(
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    is_public: Optional[bool] = None,
    is_verified: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user)
):
    try:
        items = await marketplace_service.get_marketplace_items(
            user_id=current_user.id,
            category=category,
            subcategory=subcategory,
            is_public=is_public,
            is_verified=is_verified,
            limit=limit,
            offset=offset
        )
        return [{
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "category": item.category,
            "subcategory": item.subcategory,
            "version": item.version,
            "author": item.author,
            "repository_url": item.repository_url,
            "documentation_url": item.documentation_url,
            "install_command": item.install_command,
            "is_public": item.is_public,
            "is_verified": item.is_verified,
            "download_count": item.download_count,
            "rating": item.rating,
            "createdAt": item.created_at.isoformat() if item.created_at else None,
            "updatedAt": item.updated_at.isoformat() if item.updated_at else None
        } for item in items]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/protected/marketplace/items/{item_id}")
async def get_marketplace_item(
    item_id: str,
    current_user: User = Depends(get_current_user)
):
    try:
        item = await marketplace_service.get_marketplace_item(item_id, current_user.id)
        if not item:
            raise HTTPException(status_code=404, detail="Marketplace item not found")
        return {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "category": item.category,
            "subcategory": item.subcategory,
            "version": item.version,
            "author": item.author,
            "repository_url": item.repository_url,
            "documentation_url": item.documentation_url,
            "install_command": item.install_command,
            "is_public": item.is_public,
            "is_verified": item.is_verified,
            "download_count": item.download_count,
            "rating": item.rating,
            "createdAt": item.created_at.isoformat() if item.created_at else None,
            "updatedAt": item.updated_at.isoformat() if item.updated_at else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/protected/marketplace/items/{item_id}")
async def update_marketplace_item(
    item_id: str,
    body: MarketplaceItemUpdateRequest,
    current_user: User = Depends(get_current_user)
):
    try:
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        item = await marketplace_service.update_marketplace_item(
            item_id=item_id,
            updates=updates,
            user_id=str(current_user.id),
        )
        if not item:
            raise HTTPException(status_code=404, detail="Item not found or access denied")
        return {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "category": item.category,
            "subcategory": item.subcategory,
            "version": item.version,
            "author": item.author,
            "repositoryUrl": item.repository_url,
            "documentationUrl": item.documentation_url,
            "installCommand": item.install_command,
            "configSchema": item.config_schema,
            "isPublic": item.is_public,
            "isVerified": item.is_verified,
            "downloadCount": item.download_count,
            "rating": item.rating,
            "createdAt": item.created_at.isoformat() if item.created_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/protected/marketplace/items/{item_id}")
async def delete_marketplace_item(
    item_id: str,
    current_user: User = Depends(get_current_user)
):
    try:
        success = await marketplace_service.delete_marketplace_item(
            item_id=item_id,
            user_id=str(current_user.id),
        )
        if not success:
            raise HTTPException(status_code=404, detail="Item not found or access denied")
        return {"success": True, "id": item_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/protected/marketplace/items/{item_id}/install")
async def install_marketplace_item(
    item_id: str,
    body: MarketplaceItemInstallRequest,
    current_user: User = Depends(get_current_user)
):
    try:
        user_item = await marketplace_service.install_marketplace_item(
            user_id=current_user.id,
            marketplace_item_id=item_id,
            config=body.config
        )
        return {
            "id": user_item.id,
            "marketplaceItemId": user_item.marketplace_item_id,
            "installedAt": user_item.installed_at.isoformat() if user_item.installed_at else None,
            "config": user_item.config,
            "isEnabled": user_item.is_enabled
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/protected/marketplace/items/{item_id}/install")
async def uninstall_marketplace_item(
    item_id: str,
    current_user: User = Depends(get_current_user)
):
    try:
        success = await marketplace_service.uninstall_marketplace_item(
            user_id=current_user.id,
            marketplace_item_id=item_id
        )
        if not success:
            raise HTTPException(status_code=404, detail="Installation not found")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/protected/marketplace/installed")
async def get_installed_marketplace_items(
    enabled_only: bool = False,
    current_user: User = Depends(get_current_user)
):
    try:
        items = await marketplace_service.get_user_installed_items(
            user_id=current_user.id,
            enabled_only=enabled_only
        )
        return [{
            "id": item.id,
            "marketplaceItemId": item.marketplace_item_id,
            "installedAt": item.installed_at.isoformat() if item.installed_at else None,
            "config": item.config,
            "isEnabled": item.is_enabled
        } for item in items]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/protected/marketplace/items/{item_id}/config")
async def update_marketplace_item_config(
    item_id: str,
    body: MarketplaceItemConfigUpdateRequest,
    current_user: User = Depends(get_current_user)
):
    try:
        user_item = await marketplace_service.update_marketplace_item_config(
            user_id=current_user.id,
            marketplace_item_id=item_id,
            config=body.config
        )
        if not user_item:
            raise HTTPException(status_code=404, detail="Installation not found")
        return {
            "id": user_item.id,
            "marketplaceItemId": user_item.marketplace_item_id,
            "config": user_item.config,
            "isEnabled": user_item.is_enabled
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/protected/marketplace/items/{item_id}/toggle")
async def toggle_marketplace_item_enabled(
    item_id: str,
    is_enabled: bool,
    current_user: User = Depends(get_current_user)
):
    try:
        user_item = await marketplace_service.toggle_marketplace_item_enabled(
            user_id=current_user.id,
            marketplace_item_id=item_id,
            is_enabled=is_enabled
        )
        if not user_item:
            raise HTTPException(status_code=404, detail="Installation not found")
        return {
            "id": user_item.id,
            "marketplaceItemId": user_item.marketplace_item_id,
            "isEnabled": user_item.is_enabled
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/protected/marketplace/items/{item_id}/rate")
async def rate_marketplace_item(
    item_id: str,
    body: MarketplaceItemRatingRequest,
    current_user: User = Depends(get_current_user)
):
    try:
        # Validate rating
        if body.rating < 0.0 or body.rating > 5.0:
            raise HTTPException(status_code=400, detail="Rating must be between 0.0 and 5.0")

        item = await marketplace_service.rate_marketplace_item(
            item_id=item_id,
            rating=body.rating,
            user_id=current_user.id
        )
        if not item:
            raise HTTPException(status_code=404, detail="Marketplace item not found")
        return {
            "id": item.id,
            "rating": item.rating
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/protected/marketplace/search")
async def search_marketplace_items(
    q: str,
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    try:
        items = await marketplace_service.search_marketplace_items(
            query=q,
            user_id=current_user.id,
            limit=limit
        )
        return [{
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "category": item.category,
            "subcategory": item.subcategory,
            "version": item.version,
            "author": item.author,
            "repository_url": item.repository_url,
            "documentation_url": item.documentation_url,
            "install_command": item.install_command,
            "is_public": item.is_public,
            "is_verified": item.is_verified,
            "download_count": item.download_count,
            "rating": item.rating,
            "createdAt": item.created_at.isoformat() if item.created_at else None,
            "updatedAt": item.updated_at.isoformat() if item.updated_at else None
        } for item in items]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Coding workspace ──────────────────────────────────────────────────────────

@app.post("/api/coding/analyze")
@limiter.limit("30/minute")
async def analyze_code(
    request: Request,
    body: CodeAnalysisRequest,
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    import tempfile, subprocess, os as _os

    bandit_context = ""

    # Run bandit for Python code (real static analysis)
    if body.language.lower() in ("python", "py"):
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(body.code[:50000])  # cap at 50KB
                tmp_path = f.name

            loop = asyncio.get_event_loop()
            proc_result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["python", "-m", "bandit", "-r", "-f", "json", "-l", tmp_path],
                    capture_output=True, text=True, timeout=15,
                ),
            )
            _os.unlink(tmp_path)

            if proc_result.stdout:
                bandit_data = json.loads(proc_result.stdout)
                results = bandit_data.get("results", [])
                if results:
                    bandit_context = f"\n\nBANDIT STATIC ANALYSIS RESULTS (real findings):\n"
                    for r in results[:10]:  # top 10 findings
                        bandit_context += (
                            f"- Line {r.get('line_number','?')}: {r.get('issue_text','')} "
                            f"[severity:{r.get('issue_severity','UNKNOWN')} "
                            f"confidence:{r.get('issue_confidence','UNKNOWN')} "
                            f"CWE:{r.get('issue_cwe',{}).get('id','?')}]\n"
                        )
        except Exception as bandit_err:
            logger.warning("[CodeAnalysis] Bandit failed: %s", bandit_err)
            bandit_context = ""

    try:
        analysis = await ai_service.analyze_code(body.code, body.language, extra_context=bandit_context)
    except Exception:
        analysis = {
            "vulnerabilities": [],
            "securityScore": 70,
            "mitreTags": [],
            "exploitPotential": "Analysis unavailable — AI service offline",
            "recommendations": ["Manually review code for security issues"],
        }

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
    try:
        prompt = f"""You are a red team specialist. Create a detailed, realistic attack simulation plan for authorized penetration testing.
Target: {body.target}
Attack Type: {body.attackType}
Simulation Name: {body.name}

Return valid JSON (no markdown, no code fences):
{{"phase": "reconnaissance", "progress": 15, "status": "active",
"findings": [
  {{"type": "Attack Vector", "severity": "high", "description": "Detailed finding description", "mitreTechnique": "T1595"}},
  {{"type": "Exposed Service", "severity": "medium", "description": "Another finding", "mitreTechnique": "T1046"}}
],
"steps": ["Phase 1: Reconnaissance", "Phase 2: Scanning", "Phase 3: Exploitation", "Phase 4: Post-Exploitation"],
"riskLevel": "high", "estimatedDuration": "3-5 days",
"prerequisites": ["Written authorization", "Isolated test environment"]}}

IMPORTANT: This simulation is for authorized security testing only."""
        result = await asyncio.wait_for(
            ai_service.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.4),
            timeout=25.0,
        )
        parsed = _parse_json(result)
    except Exception:
        parsed = {
            "phase": "reconnaissance", "progress": 0, "status": "planned",
            "findings": [
                {"type": "Target Surface", "severity": "medium", "description": f"Initial assessment of {body.target} attack surface — AI enrichment pending", "mitreTechnique": "T1595"},
                {"type": "Exposed Services", "severity": "high", "description": "Active service enumeration required — run port scan via Agents tab", "mitreTechnique": "T1046"},
                {"type": "Credential Attack Surface", "severity": "medium", "description": "Password spray and credential stuffing vectors to be evaluated", "mitreTechnique": "T1110"},
            ],
            "steps": [
                "Phase 1: Passive reconnaissance — WHOIS, DNS, OSINT",
                "Phase 2: Active scanning — port/service/version detection",
                "Phase 3: Vulnerability assessment — CVE mapping, manual testing",
                "Phase 4: Exploitation — targeted attacks on confirmed vulnerabilities",
                "Phase 5: Post-exploitation — lateral movement, persistence, privilege escalation",
                "Phase 6: Reporting — findings documentation and remediation recommendations",
            ],
            "riskLevel": "high", "estimatedDuration": "3-5 days",
            "prerequisites": ["Written authorization from system owner", "Isolated test environment preferred", "Rules of engagement defined", "Emergency contact established"],
        }

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
Campaign: {body.name} | Targets: {len(body.targets)}
Template hint: {body.template[:200]}

Return valid JSON (no markdown):
{{"template": "Full phishing email here...", "subject": "Urgent: Account Verification Required",
"targetList": {json.dumps(body.targets[:5])},
"sendsCompleted": 0, "opensTracked": 0, "clicksTracked": 0, "credentialsHarvested": 0, "status": "draft",
"educational_tips": ["Verify sender domain", "Check URL hover destination", "Never enter credentials from email links"],
"indicators_of_phishing": ["Urgency language", "Mismatched sender domain", "Generic greeting", "Suspicious link"]}}"""
        result = await asyncio.wait_for(
            ai_service.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.4),
            timeout=25.0,
        )
        parsed = _parse_json(result)
    except Exception:
        parsed = {
            "template": body.template or f"Dear {'{'}Recipient{'}'}, your account requires immediate verification. Please click the link below to confirm your credentials within 24 hours or your account will be suspended.\n\nVerify Now: https://secure.{body.name.lower().replace(' ', '-')}.example.com/verify\n\nSecurity Team",
            "subject": "Urgent: Immediate Account Verification Required",
            "targetList": body.targets[:5],
            "sendsCompleted": 0, "opensTracked": 0, "clicksTracked": 0, "credentialsHarvested": 0, "status": "draft",
            "educational_tips": [
                "Always verify the sender domain before clicking — hover over the sender address",
                "Check URLs before clicking — hover to see the real destination",
                "Never enter credentials after clicking an email link — navigate directly to the site",
                "Report suspicious emails to your IT security team immediately",
                "Enable MFA on all accounts to limit credential theft impact",
            ],
            "indicators_of_phishing": [
                "Urgency or threatening language ('your account will be suspended')",
                "Mismatched sender domain (looks legit but domain is different)",
                "Generic greeting ('Dear Customer' instead of your name)",
                "Suspicious link destination (hover reveals different URL than displayed)",
                "Unexpected email asking for credentials or personal info",
            ],
        }

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
Target: {body.target} | Objective: {body.objective}

Return valid JSON (no markdown):
{{"steps": [
  {{"technique": "Initial Access", "mitreTactic": "TA0001", "mitreTechnique": "T1566", "description": "Gain foothold via phishing or exposed service", "automated": false, "status": "pending", "expectedDuration": "1-2 days"}},
  {{"technique": "Execution", "mitreTactic": "TA0002", "mitreTechnique": "T1059", "description": "Execute payload to establish persistence", "automated": true, "status": "pending", "expectedDuration": "30 minutes"}},
  {{"technique": "Privilege Escalation", "mitreTactic": "TA0004", "mitreTechnique": "T1068", "description": "Escalate to SYSTEM/root via local vuln", "automated": false, "status": "pending", "expectedDuration": "2-4 hours"}},
  {{"technique": "Lateral Movement", "mitreTactic": "TA0008", "mitreTechnique": "T1550", "description": "Move toward objective using credentials", "automated": true, "status": "pending", "expectedDuration": "1 day"}}
],
"currentStep": 0, "overallProgress": 0, "riskLevel": "critical", "timeline": "1-2 weeks",
"mitigations": ["Network segmentation", "PAWs", "MFA enforcement", "EDR solutions"]}}"""
        result = await asyncio.wait_for(
            ai_service.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.4),
            timeout=25.0,
        )
        parsed = _parse_json(result)
    except Exception:
        parsed = {
            "steps": [
                {"technique": "Initial Access — Spearphishing / Exposed Service", "mitreTactic": "TA0001", "mitreTechnique": "T1566", "description": f"Craft targeted attack against {body.target} — phishing or exploiting exposed service to gain initial foothold", "automated": False, "status": "pending", "expectedDuration": "1-2 days"},
                {"technique": "Execution — Script Interpreter", "mitreTactic": "TA0002", "mitreTechnique": "T1059", "description": "Execute malicious script/binary to establish persistence and C2 channel", "automated": True, "status": "pending", "expectedDuration": "30-60 minutes"},
                {"technique": "Discovery — Network & Service Enumeration", "mitreTactic": "TA0007", "mitreTechnique": "T1046", "description": "Enumerate internal network, hosts, services, and shares to map attack path", "automated": True, "status": "pending", "expectedDuration": "1-2 hours"},
                {"technique": "Privilege Escalation", "mitreTactic": "TA0004", "mitreTechnique": "T1068", "description": "Exploit local vulnerability or misconfiguration to gain elevated privileges", "automated": False, "status": "pending", "expectedDuration": "2-4 hours"},
                {"technique": "Credential Access — Dumping", "mitreTactic": "TA0006", "mitreTechnique": "T1003", "description": "Extract credentials from memory/SAM/NTDS for lateral movement", "automated": True, "status": "pending", "expectedDuration": "30 minutes"},
                {"technique": "Lateral Movement — Pass-the-Hash/Ticket", "mitreTactic": "TA0008", "mitreTechnique": "T1550", "description": f"Use harvested credentials to move laterally toward: {body.objective}", "automated": True, "status": "pending", "expectedDuration": "1-2 days"},
                {"technique": "Objective Completion & Evidence Collection", "mitreTactic": "TA0010", "mitreTechnique": "T1041", "description": "Complete stated objective with documented proof-of-exploitation for the report", "automated": False, "status": "pending", "expectedDuration": "2-4 hours"},
            ],
            "currentStep": 0, "overallProgress": 0, "riskLevel": "critical", "timeline": "1-2 weeks",
            "mitigations": [
                "Network segmentation — restrict lateral movement between segments",
                "Privileged Access Workstations (PAWs) for admin tasks",
                "MFA enforcement across all accounts and VPN access",
                "EDR/XDR deployment with behavioral detection rules",
                "Threat hunting on MITRE ATT&CK technique coverage",
                "Credential tiering — separate admin and user accounts",
            ],
        }

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
    from backend.services.tool_service import run_tool

    # ── Run real DNS and WHOIS lookups using tool_service ──────────────────────
    dns_result = {}
    whois_result = {}
    http_result = {}
    subdomain_result = {}

    try:
        dns_raw = await run_tool("dns_lookup", {"domain": d})
        if dns_raw.get("success"):
            dns_result = dns_raw.get("dns_records", {})
            ip_list = dns_raw.get("ip_addresses", [])
        else:
            ip_list = []
    except Exception:
        ip_list = []

    try:
        whois_raw = await run_tool("whois", {"target": d})
        if whois_raw.get("success"):
            whois_result = whois_raw.get("registration", {})
    except Exception:
        pass

    try:
        http_raw = await run_tool("http_probe", {"url": f"https://{d}"})
        if http_raw.get("success"):
            http_result = http_raw
    except Exception:
        pass

    try:
        sub_raw = await run_tool("subdomain_enum", {"domain": d})
        if sub_raw.get("success"):
            subs = sub_raw.get("subdomains", [])
        else:
            subs = []
    except Exception:
        subs = []

    # ── Feed real tool output to AI for risk assessment and enrichment ─────────
    real_data_context = f"""
Real DNS records for {d}: {json.dumps(dns_result)}
Real IP addresses: {json.dumps(ip_list)}
Real WHOIS data: {json.dumps(whois_result)}
Real subdomains found: {json.dumps(subs[:20])}
Real HTTP headers/technologies: {json.dumps({k: v for k, v in http_result.items() if k in ("server", "technologies", "security_headers", "security_score", "status_code")})}
"""
    try:
        prompt = f"""You are an OSINT analyst. Analyze this real reconnaissance data for domain {d} and return a structured risk assessment.

{real_data_context}

Return ONLY valid JSON with this exact structure:
{{"subdomains": [...real subdomains found...],
"ipAddresses": [...real IPs...],
"technologies": [{{"name": "...", "version": null, "category": "..."}}],
"certificates": [],
"dnsRecords": {{...real records...}},
"socialMedia": [],
"whois": {{...real whois...}},
"breaches": [],
"openPorts": [],
"riskScore": <0-100 based on findings>,
"riskFactors": ["...specific risks identified from the real data..."]}}"""
        result = await ai_service.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.2, agent="recon")
        parsed = _parse_json(result)
    except Exception:
        # Fall back to structured real data without AI enrichment
        parsed = {
            "subdomains": subs,
            "ipAddresses": ip_list,
            "technologies": http_result.get("technologies", []),
            "certificates": [],
            "dnsRecords": dns_result,
            "socialMedia": [],
            "whois": whois_result,
            "breaches": [],
            "openPorts": [],
            "riskScore": http_result.get("security_score", 50),
            "riskFactors": ["AI enrichment unavailable — raw tool data shown"],
        }

    now = datetime.now(timezone.utc).isoformat()
    data = {"domain": d, **parsed, "lastUpdated": now, "dataSource": "real_tools"}
    rec = await _save_workspace(db, "osint", "domain", title=d, data=data, user_id=current_user.id if current_user else None)
    return {"id": rec.id, **data}


@app.post("/api/osint/github")
@limiter.limit("20/minute")
async def osint_github(
    request: Request,
    body: GitHubOSINTRequest,
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Real GitHub OSINT via GitHub REST API v3.
    Works unauthenticated (60 req/hr); set GITHUB_TOKEN for 5000 req/hr."""
    import httpx as _httpx

    t = body.target.strip().lstrip("@").split("/")[-1]
    token = os.environ.get("GITHUB_TOKEN", "")
    gh_headers: dict = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        gh_headers["Authorization"] = f"Bearer {token}"

    SENSITIVE_NAMES = {
        ".env", ".env.example", ".env.local", ".env.production", ".env.staging",
        "credentials.json", "secrets.json", "config.yml", "secrets.yml",
        "terraform.tfvars", "terraform.tfvars.json",
        "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa",
        ".npmrc", ".pypirc", "docker-compose.yml",
    }

    try:
        async with _httpx.AsyncClient(headers=gh_headers, timeout=15.0) as client:
            # Try org endpoint first; fall back to user
            org_resp = await client.get(f"https://api.github.com/orgs/{t}")
            is_org = org_resp.status_code == 200
            if is_org:
                entity = org_resp.json()
                repos_resp = await client.get(
                    f"https://api.github.com/orgs/{t}/repos",
                    params={"per_page": 30, "sort": "updated", "type": "public"},
                )
                members_resp = await client.get(
                    f"https://api.github.com/orgs/{t}/members",
                    params={"per_page": 30},
                )
            else:
                user_resp = await client.get(f"https://api.github.com/users/{t}")
                if user_resp.status_code == 404:
                    raise HTTPException(status_code=404, detail=f"GitHub org/user '{t}' not found")
                if user_resp.status_code == 403:
                    raise HTTPException(
                        status_code=503,
                        detail="GitHub API rate limit hit — add GITHUB_TOKEN to .env for 5000 req/hr",
                    )
                entity = user_resp.json()
                repos_resp = await client.get(
                    f"https://api.github.com/users/{t}/repos",
                    params={"per_page": 30, "sort": "updated"},
                )
                members_resp = None

            repos_raw = repos_resp.json() if repos_resp.status_code == 200 else []
            members_raw = members_resp.json() if (members_resp and members_resp.status_code == 200) else []

            # Scan first 8 public repos for sensitive filenames (respect rate limits)
            sensitive_files: list[dict] = []
            for repo in repos_raw[:8]:
                if repo.get("size", 0) == 0 or repo.get("private", False):
                    continue
                tree_resp = await client.get(
                    f"https://api.github.com/repos/{t}/{repo['name']}/git/trees/HEAD",
                    params={"recursive": "1"},
                )
                if tree_resp.status_code != 200:
                    continue
                for item in tree_resp.json().get("tree", []):
                    fname = item["path"].split("/")[-1].lower()
                    if fname in SENSITIVE_NAMES or fname.startswith(".env"):
                        sensitive_files.append({
                            "repository": repo["name"],
                            "filename": item["path"],
                            "type": "potential secret/config file",
                            "content": None,
                        })

        repositories = [
            {
                "name": r["name"],
                "description": r.get("description") or "",
                "language": r.get("language") or "Unknown",
                "stars": r.get("stargazers_count", 0),
                "forks": r.get("forks_count", 0),
                "isPrivate": r.get("private", False),
                "hasSecrets": any(sf["repository"] == r["name"] for sf in sensitive_files),
                "lastCommit": r.get("updated_at", ""),
                "vulnerabilities": [],
            }
            for r in repos_raw
        ]

        users: list[dict] = [
            {
                "username": m["login"],
                "email": "",
                "name": m.get("name") or m["login"],
                "publicRepos": 0,
                "followers": 0,
                "company": entity.get("name") or t,
            }
            for m in members_raw[:20]
        ] or [
            {
                "username": entity.get("login", t),
                "email": entity.get("email") or "",
                "name": entity.get("name") or entity.get("login", t),
                "publicRepos": entity.get("public_repos", 0),
                "followers": entity.get("followers", 0),
                "company": entity.get("company") or "",
            }
        ]

        risk_factors: list[str] = []
        if sensitive_files:
            risk_factors.append(f"{len(sensitive_files)} potential secret/config files found in public repos")
        high_issue_repos = [r["name"] for r in repos_raw if r.get("open_issues_count", 0) > 50 and not r.get("fork")]
        if high_issue_repos:
            risk_factors.append(f"High open-issue counts in: {', '.join(high_issue_repos[:3])}")
        if not risk_factors:
            risk_factors.append("No obvious risks detected in public repositories")

        parsed = {
            "organization": entity.get("name") or entity.get("login") or t,
            "repositories": repositories,
            "users": users,
            "sensitiveFiles": sensitive_files,
            "totalRepos": entity.get("public_repos", len(repositories)),
            "totalMembers": entity.get("members_count") or (1 if not is_org else len(members_raw)),
            "riskLevel": "high" if len(sensitive_files) > 3 else "medium" if sensitive_files else "low",
            "riskFactors": risk_factors,
            "dataSource": "github_api",
        }

    except HTTPException:
        raise
    except _httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="GitHub API timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GitHub OSINT error: {e}")

    now = datetime.now(timezone.utc).isoformat()
    data = {**parsed, "target": t, "lastUpdated": now}
    rec = await _save_workspace(db, "osint", "github", title=t, data=data,
                                user_id=current_user.id if current_user else None)
    return {"id": rec.id, **data}


@app.post("/api/osint/shodan")
@limiter.limit("10/minute")
async def osint_shodan(
    request: Request,
    body: ShodanRequest,
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Real Shodan OSINT via Shodan REST API. Requires SHODAN_API_KEY in .env."""
    import httpx as _httpx

    api_key = os.environ.get("SHODAN_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="SHODAN_API_KEY not configured — add it to .env to enable real Shodan queries",
        )

    q = body.query.strip()
    try:
        async with _httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                "https://api.shodan.io/shodan/host/search",
                params={"key": api_key, "query": q, "minify": "false"},
            )
        if resp.status_code == 401:
            raise HTTPException(status_code=503, detail="Shodan API key invalid")
        if resp.status_code == 402:
            raise HTTPException(status_code=503, detail="Shodan API plan does not support this query type")
        resp.raise_for_status()
        raw = resp.json()

        countries: dict[str, int] = {}
        service_counts: dict[str, int] = {}
        vuln_map: dict[str, dict] = {}
        hits: list[dict] = []

        for m in raw.get("matches", []):
            loc = m.get("location") or {}
            country = loc.get("country_name", "Unknown")
            countries[country] = countries.get(country, 0) + 1

            svc = (m.get("_shodan") or {}).get("module") or m.get("transport", "tcp")
            service_counts[svc] = service_counts.get(svc, 0) + 1

            vulns_raw = m.get("vulns") or {}
            for cve, info in (vulns_raw.items() if isinstance(vulns_raw, dict) else {}.items()):
                if cve not in vuln_map:
                    cvss = float(info.get("cvss") or 0) if isinstance(info, dict) else 0
                    vuln_map[cve] = {
                        "cve": cve,
                        "count": 0,
                        "severity": "critical" if cvss >= 9 else "high" if cvss >= 7 else "medium" if cvss >= 4 else "low",
                        "description": info.get("summary", "") if isinstance(info, dict) else "",
                    }
                vuln_map[cve]["count"] += 1

            hits.append({
                "ip": m.get("ip_str", ""),
                "hostname": ((m.get("hostnames") or [""])[0]),
                "port": m.get("port", 0),
                "protocol": m.get("transport", "tcp"),
                "service": svc,
                "banner": (m.get("data") or "")[:300],
                "location": {
                    "country": loc.get("country_name", ""),
                    "city": loc.get("city", ""),
                    "latitude": loc.get("latitude", 0),
                    "longitude": loc.get("longitude", 0),
                },
                "vulns": list(vulns_raw.keys()) if isinstance(vulns_raw, dict) else [],
                "lastSeen": m.get("timestamp", ""),
                "org": m.get("org", ""),
            })

        top_services = sorted(
            [{"name": k, "count": v} for k, v in service_counts.items()],
            key=lambda x: x["count"], reverse=True,
        )[:10]

        parsed = {
            "query": q,
            "results": hits,
            "totalResults": raw.get("total", len(hits)),
            "countriesFound": sorted(countries, key=lambda c: countries[c], reverse=True),
            "topServices": top_services,
            "vulnerabilities": list(vuln_map.values()),
            "exposureScore": min(100, len(hits) * 2 + len(vuln_map) * 5),
            "dataSource": "shodan_api",
        }

    except HTTPException:
        raise
    except _httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Shodan API timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Shodan OSINT error: {e}")

    now = datetime.now(timezone.utc).isoformat()
    data = {**parsed, "lastUpdated": now}
    rec = await _save_workspace(db, "osint", "shodan", title=q, data=data,
                                user_id=current_user.id if current_user else None)
    return {"id": rec.id, **data}



@app.post("/api/osint/virustotal")
@limiter.limit("10/minute")
async def osint_virustotal(
    request: Request,
    body: VirusTotalRequest,
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query VirusTotal API v3 for domain/IP/URL/hash reputation."""
    import httpx as _httpx
    api_key = os.environ.get("VIRUSTOTAL_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="VIRUSTOTAL_API_KEY not configured")

    q = body.query.strip()
    qt = body.query_type.lower()
    headers = {"x-apikey": api_key}

    try:
        async with _httpx.AsyncClient(timeout=20.0) as client:
            if qt == "url":
                import base64
                url_id = base64.urlsafe_b64encode(q.encode()).rstrip(b"=").decode()
                resp = await client.get(
                    f"https://www.virustotal.com/api/v3/urls/{url_id}",
                    headers=headers,
                )
            elif qt == "ip":
                resp = await client.get(
                    f"https://www.virustotal.com/api/v3/ip_addresses/{q}",
                    headers=headers,
                )
            elif qt == "hash":
                resp = await client.get(
                    f"https://www.virustotal.com/api/v3/files/{q}",
                    headers=headers,
                )
            else:  # domain (default)
                resp = await client.get(
                    f"https://www.virustotal.com/api/v3/domains/{q}",
                    headers=headers,
                )

        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"{q} not found in VirusTotal")
        if resp.status_code == 401:
            raise HTTPException(status_code=503, detail="VirusTotal API key invalid")
        resp.raise_for_status()
        data = resp.json().get("data", {})
        attrs = data.get("attributes", {})

        stats = attrs.get("last_analysis_stats", {})
        result = {
            "query": q,
            "query_type": qt,
            "malicious": stats.get("malicious", 0),
            "suspicious": stats.get("suspicious", 0),
            "harmless": stats.get("harmless", 0),
            "undetected": stats.get("undetected", 0),
            "reputation": attrs.get("reputation", 0),
            "tags": attrs.get("tags", []),
            "categories": attrs.get("categories", {}),
            "country": attrs.get("country", ""),
            "last_analysis_date": attrs.get("last_analysis_date", None),
            "raw": attrs,
        }
    except _httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="VirusTotal API timeout")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"VirusTotal error: {e}")

    await _save_workspace(db, "osint", "virustotal", title=q, data=result,
                          user_id=current_user.id if current_user else None)
    return result


@app.post("/api/osint/censys")
@limiter.limit("10/minute")
async def osint_censys(
    request: Request,
    body: CensysRequest,
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query Censys Search API v2 for host/certificate intelligence."""
    import httpx as _httpx
    api_id = os.environ.get("CENSYS_API_ID", "")
    api_secret = os.environ.get("CENSYS_API_SECRET", "")
    if not api_id or not api_secret:
        raise HTTPException(status_code=503, detail="CENSYS_API_ID / CENSYS_API_SECRET not configured")

    q = body.query.strip()
    try:
        async with _httpx.AsyncClient(timeout=20.0, auth=(api_id, api_secret)) as client:
            if body.query_type == "cert":
                resp = await client.get(
                    "https://search.censys.io/api/v2/certificates",
                    params={"q": q, "per_page": 25},
                )
            else:  # host
                resp = await client.get(
                    "https://search.censys.io/api/v2/hosts/search",
                    params={"q": q, "per_page": 25},
                )

        if resp.status_code == 401:
            raise HTTPException(status_code=503, detail="Censys credentials invalid")
        resp.raise_for_status()
        payload = resp.json()
        hits = payload.get("result", {}).get("hits", [])

        result = {
            "query": q,
            "query_type": body.query_type,
            "total": payload.get("result", {}).get("total", len(hits)),
            "hits": hits[:25],
        }
    except _httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Censys API timeout")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Censys error: {e}")

    await _save_workspace(db, "osint", "censys", title=q, data=result,
                          user_id=current_user.id if current_user else None)
    return result

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
    body: SimpleReportRequest,
    current_user: Optional[User] = Depends(optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    sections_str = ", ".join(body.sections) if body.sections else "Executive Summary, Scope, Methodology, Findings, Recommendations"

    # ── Gather real session data to ground the report ─────────────────────────
    real_context = ""
    if current_user:
        try:
            user_records = await _get_workspace_records(db, None, None, user_id=current_user.id)
            if user_records:
                analyses = [r for r in user_records if r.record_type in ("analysis", "exploit", "domain", "simulation")][:8]
                context_items = []
                for rec in analyses:
                    title = rec.data.get("title", rec.record_type)
                    findings_count = len(rec.data.get("findings", rec.data.get("vulnerabilities", [])))
                    risk = rec.data.get("riskScore", rec.data.get("risk_level", "unknown"))
                    context_items.append(f"- {rec.record_type}: '{title}' ({findings_count} findings, risk={risk})")
                if context_items:
                    real_context = "\n\nReal session data to base this report on:\n" + "\n".join(context_items)
        except Exception:
            real_context = ""

    try:
        prompt = f"""You are a senior security analyst writing a professional {body.type} security report.
Title: {body.title}
Report Type: {body.type}
Sections Required: {sections_str}
{real_context}

Write a realistic, actionable security report based on the session data above (if provided).
Do NOT invent placeholder CVE IDs. Only reference real, published CVEs or omit the CVE field.
Do NOT use 'CVE-XXXX-XXXX' or any placeholder patterns.

Return ONLY valid JSON:
{{"title": "{body.title}", "type": "{body.type}", "status": "completed", "progress": 100,
"findings": [
  {{"id": "f-1", "title": "...", "severity": "critical|high|medium|low", "category": "...",
   "description": "...", "recommendation": "...", "mitreTechnique": "T1XXX", "cvss": 7.5, "cve": null}}
],
"summary": {{"totalFindings": 0, "criticalCount": 0, "highCount": 0, "mediumCount": 0, "lowCount": 0, "overallRisk": "medium", "riskScore": 50}},
"mitreMapping": [{{"tactic": "...", "tacticId": "TAXXXX", "techniques": ["TXXXX"]}}],
"recommendations": ["..."],
"executiveSummary": "...",
"technicalDetails": "...",
"scope": "{sections_str}",
"methodology": "{body.type} assessment"
}}"""
        result = await ai_service.chat_completion([{"role": "user", "content": prompt}], json_mode=True, temperature=0.3, agent="planner")
        parsed = _parse_json(result)
        # Safety: strip any CVE placeholder that slipped through
        import re as _re
        result_clean = _re.sub(r'"CVE-\d{4}-XXXX"', 'null', json.dumps(parsed))
        parsed = json.loads(result_clean)
    except AIQuotaError:
        parsed = {
            "title": body.title, "type": body.type, "status": "completed", "progress": 100,
            "findings": [],
            "summary": {"totalFindings": 0, "criticalCount": 0, "highCount": 0, "mediumCount": 0, "lowCount": 0, "overallRisk": "unknown", "riskScore": 0},
            "mitreMapping": [],
            "recommendations": ["Full report generation unavailable — Gemini quota exceeded. Try again when quota resets."],
            "executiveSummary": f"Report generation for '{body.title}' requires AI processing which is currently quota-limited.",
            "technicalDetails": "",
            "scope": sections_str,
            "methodology": f"{body.type} assessment",
            "aiNote": "Quota exceeded — empty report placeholder.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    now = datetime.now(timezone.utc).isoformat()
    data = {**parsed, "createdAt": now, "updatedAt": now}
    rec = await _save_workspace(db, "reports", "report", title=body.title, data=data, user_id=current_user.id if current_user else None)
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


@app.post("/api/protected/reports/{report_id}/share")
async def share_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import secrets as _secrets
    result = await db.execute(select(WorkspaceRecord).where(
        WorkspaceRecord.id == report_id,
        WorkspaceRecord.user_id == current_user.id,
    ))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Report not found")
    token = _secrets.token_urlsafe(24)
    record.data = {**(record.data or {}), "shareToken": token}
    await db.commit()
    return {"shareToken": token, "shareUrl": f"/shared/report/{token}"}


@app.get("/api/shared/report/{token}")
async def get_shared_report(token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(WorkspaceRecord).where(
            WorkspaceRecord.record_type == "report"
        )
    )
    for record in result.scalars().all():
        if (record.data or {}).get("shareToken") == token:
            return workspace_record_to_dict(record)
    raise HTTPException(status_code=404, detail="Report not found or link expired")


@app.delete("/api/protected/reports/{report_id}/share")
async def revoke_report_share(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(WorkspaceRecord).where(
        WorkspaceRecord.id == report_id,
        WorkspaceRecord.user_id == current_user.id,
    ))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Report not found")
    data = dict(record.data or {})
    data.pop("shareToken", None)
    record.data = data
    await db.commit()
    return {"success": True}


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

    # Deduplicate real findings by title+severity (no more fake baseline entries)
    seen: set[str] = set()
    deduped: list[dict] = []
    for f in db_findings:
        key = f"{f.get('title','')}|{f.get('severity','')}"
        if key not in seen:
            seen.add(key)
            deduped.append(f)

    return sorted(deduped, key=lambda x: {"critical":0,"high":1,"medium":2,"low":3,"info":4}.get(x.get("severity","info"),4))


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
@limiter.limit("60/minute")
async def stream_chat(
    request: Request,
    body: StreamChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Server-Sent Events streaming chat endpoint with true Gemini token streaming."""
    import json as _json

    # ── Talk mode fast path: skip DB + RAG, use inline history ──────────────
    if body.talk_mode:
        # Build messages from inline history + current message
        talk_messages = [
            {"role": m.get("role", "user"), "content": str(m.get("content", ""))}
            for m in (body.history or [])[-6:]
        ] + [{"role": "user", "content": body.content}]

        async def talk_event_generator():
            import json as _json
            try:
                TALK_SYSTEM = """You are AKKI — a warm, witty, highly intelligent AI companion.
You talk exactly like a brilliant best friend: casual, natural, fun, direct.

STRICT RULES:
- Keep replies SHORT (1-3 sentences max for simple questions, 4-5 for complex ones)
- NEVER use bullet points, headers, or markdown formatting
- NEVER write lists or numbered steps unless explicitly asked
- Sound human — use contractions (you're, I'd, that's, let's)
- Be warm and engaging, occasionally use light humour
- If asked something technical, give the key insight concisely — not a lecture
- Match the user's energy: if they're casual, be casual; if serious, be precise
- End with a natural follow-up question or comment to keep conversation alive

Examples:
User: hey what is machine learning
AKKI: It's basically teaching computers to learn from examples instead of hard-coding rules — like how you recognized cats by seeing thousands of them. Want me to go deeper?

User: i'm bored
AKKI: Oof, the worst! Want to explore something cool? I can geek out about AI, cybersecurity, coding — just say the word."""

                async for chunk in ai_service.stream_completion(
                    talk_messages,
                    agent="planner",
                    system_prompt=TALK_SYSTEM,
                    temperature=0.85,
                    user_id=str(current_user.id),
                ):
                    yield f"data: {_json.dumps({'type': 'token', 'text': chunk})}\n\n"

                yield f"data: {_json.dumps({'type': 'done'})}\n\n"
            except Exception as e:
                logger.error("[Talk] stream error: %s", e)
                yield f"data: {_json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        return StreamingResponse(
            talk_event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    session_id = body.sessionId

    # If no sessionId is provided, create a new Session first
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

    # Persist the user message to the DB first
    user_msg = Message(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role="user",
        content=body.content,
        tool_calls=[],
        metadata_={"streaming": True},
    )
    db.add(user_msg)
    await db.commit()

    # Load recent session history for context
    # Filter: skip empty content (cancelled streams), skip system messages
    history: list[dict] = []
    if session_id:
        hist_result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .where(Message.id != user_msg.id)
            .where(Message.content.isnot(None))
            .where(Message.content != "")
            .where(Message.role.in_(["user", "assistant"]))
            .order_by(desc(Message.created_at))
            .limit(20)   # 20 turns = 10 back-and-forths — enough context
        )
        for m in reversed(hist_result.scalars().all()):
            content = (m.content or "").strip()
            if content:  # double-check after strip
                history.append({"role": m.role, "content": content})

    messages = history + [{"role": "user", "content": body.content}]

    async def event_generator():
        try:
            # Prompt injection check — send error event and stop
            from backend.services.ai_service import _check_prompt_injection
            if _check_prompt_injection(body.content):
                logger.warning("Prompt injection blocked in stream: %s", body.content[:80])
                yield f"data: {_json.dumps({'type': 'error', 'message': 'Input flagged by security filter. Please rephrase your query.'})}\n\n"
                return

            # ── Launch routing + RAG + memory IN PARALLEL ───────────────────────
            # Before: ~2-4s sequential. After: ~1-3s (routing is the bottleneck).
            rag_future = asyncio.ensure_future(
                _prefetch_rag(body.content, session_id, current_user.id)
            )
            memory_future = asyncio.ensure_future(
                _prefetch_memory(str(current_user.id))
            )

            if body.agent:
                agent_key = body.agent
                # RAG + memory already running; cancel routing overhead
            else:
                routing = await ai_service.route_to_agent(body.content)
                agent_key = routing.get("agent", "planner")

            agent_info = AGENT_PERSONAS.get(agent_key, AGENT_PERSONAS["planner"])
            yield f"data: {_json.dumps({'type': 'agent', 'agent': agent_key, 'agentName': agent_info['name'], 'agentRole': agent_info['role']})}\n\n"

            # Collect parallel results (likely done by now since routing took ~1-3s)
            rag_context, memory_context = await asyncio.gather(rag_future, memory_future)
            if rag_context:
                yield f"data: {_json.dumps({'type': 'rag', 'hasContext': True})}\n\n"

            # ── Talk Mode: override with friendly conversational persona ────────
            TALK_SYSTEM = """You are AKKI — a warm, witty, highly intelligent AI companion.
You talk exactly like a brilliant best friend: casual, natural, fun, direct.

STRICT RULES:
- Keep replies SHORT (1-3 sentences max for simple questions, 4-5 for complex ones)
- NEVER use bullet points, headers, or markdown formatting
- NEVER write lists or numbered steps unless explicitly asked
- Sound human — use contractions (you're, I'd, that's, let's)
- Be warm and engaging, occasionally use light humour
- If asked something technical, give the key insight concisely — not a lecture
- Match the user's energy: if they're casual, be casual; if serious, be precise
- End with a natural follow-up question or comment to keep the conversation alive

Examples of your tone:
User: hey what is machine learning
AKKI: It's basically teaching computers to learn from examples instead of hard-coding rules — like how you learned to recognize cats by seeing thousands of them, not by reading a definition. Want me to go deeper on any part?

User: i'm feeling bored
AKKI: Oof, the worst! Want to explore something cool? I can geek out about AI, cybersecurity, coding, or honestly anything — just say the word."""

            # Build augmented system prompt with RAG context
            if body.talk_mode:
                base_system = TALK_SYSTEM
            else:
                base_system = AGENT_PERSONAS.get(agent_key, AGENT_PERSONAS["planner"])["system"]
            memory_prefix = f"\n\n**WHAT YOU KNOW ABOUT THIS USER (from past interactions):**\n{memory_context}\n" if memory_context else ""
            augmented_system = base_system + memory_prefix + ("\n\n**RELEVANT KNOWLEDGE BASE:**\n" + rag_context if rag_context else "")

            full_response = []
            async for chunk in ai_service.stream_completion(
                messages,
                agent=agent_key,
                system_prompt=augmented_system,
                temperature=0.85 if body.talk_mode else None,
                user_id=str(current_user.id),
            ):
                full_response.append(chunk)
                yield f"data: {_json.dumps({'type': 'token', 'text': chunk})}\n\n"

            # Persist assistant message to DB
            if session_id and full_response:
                complete_text = "".join(full_response)
                
                # Try to get emotional tone from emotional_ai
                # Analyze emotional tone AND update bond level (was analyzed but bond never updated)
                try:
                    from backend.services.emotional_ai_service import emotional_ai
                    emotional_tone = await emotional_ai.analyze_emotional_tone(complete_text)
                    # Actually update bond — was never called before, fixing permanently
                    user_message_text = body.content if hasattr(body, "content") else ""
                    await emotional_ai.update_emotional_bond(
                        user_id=str(current_user.id),
                        emotional_tone=emotional_tone,
                        context=user_message_text,
                        interaction_type="chat",
                    )
                except Exception as bond_err:
                    logger.debug("[EmotionalAI] Bond update skipped: %s", bond_err)
                    emotional_tone = "neutral"

                assistant_msg = Message(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    role="assistant",
                    content=complete_text,
                    tool_calls=[],
                    metadata_={
                        "agent": agent_key,
                        "agentName": agent_info["name"],
                        "streaming": True,
                        "emotionalTone": emotional_tone,
                    },
                )
                db.add(assistant_msg)
                await db.commit()
                # Fire-and-forget memory extraction (non-blocking)
                if not body.talk_mode and complete_text and len(complete_text) > 80:
                    asyncio.create_task(
                        _extract_and_store_memories(str(current_user.id), body.content, complete_text)
                    )

            yield f"data: {_json.dumps({'type': 'done', 'sessionId': session_id})}\n\n"

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
async def run_tool_direct(
    body: ToolExecuteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute a real cybersecurity tool and return structured results."""
    if body.toolName in ACTIVE_TOOLS and not body.authorized:
        return {
            "success": False,
            "error": "This tool actively tests/attacks the target. Confirm you own it or have written authorization before running it.",
            "requiresAuthorization": True,
        }

    result = await run_tool(body.toolName, body.params)

    if body.toolName in ACTIVE_TOOLS and body.authorized:
        from backend.models import ToolAuditLog
        db.add(ToolAuditLog(
            user_id=current_user.id,
            tool_name=body.toolName,
            arguments=body.params,
        ))
        await db.commit()

    return result


@app.post("/api/tools/execute/stream")
async def run_tool_stream(
    body: ToolExecuteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE streaming wrapper around run_tool — emits progress events."""
    import json as _json

    async def sse():
        if body.toolName in ACTIVE_TOOLS and not body.authorized:
            yield f"data: {_json.dumps({'type': 'error', 'error': 'This tool actively tests/attacks the target. Confirm you own it or have written authorization before running it.', 'requiresAuthorization': True})}\n\n"
            return

        yield f"data: {_json.dumps({'type': 'start', 'tool': body.toolName})}\n\n"
        try:
            result = await run_tool(body.toolName, body.params)
            if body.toolName in ACTIVE_TOOLS and body.authorized:
                from backend.models import ToolAuditLog
                db.add(ToolAuditLog(
                    user_id=current_user.id,
                    tool_name=body.toolName,
                    arguments=body.params,
                ))
                await db.commit()
            yield f"data: {_json.dumps({'type': 'done', 'result': result})}\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'type': 'error', 'error': str(e)[:200]})}\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Brain Engine ────────────────────────────────────────────────────────────

@app.get("/api/brain/health")
async def brain_health():
    from backend.services import brain_service
    result = await brain_service.health()
    if not result["healthy"]:
        raise HTTPException(status_code=503, detail="Neo4j unreachable")
    return result


@app.get("/api/brain/status")
async def brain_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from backend.services import brain_service
    return await brain_service.get_status(db)


@app.post("/api/brain/discover")
async def brain_discover(
    body: BrainDiscoverRequest,
    current_user: User = Depends(get_current_user),
):
    from backend.services import brain_service
    return await brain_service.discover(body.concept, body.concept2)


@app.post("/api/brain/converge")
async def brain_converge(
    body: BrainConvergeRequest,
    current_user: User = Depends(get_current_user),
):
    """Multi-origin convergence discovery — surface concepts that many
    unrelated seed concepts independently arrive at (candidate hidden truths)."""
    from backend.services import brain_service
    return await brain_service.discover_convergence(
        body.seeds, max_depth=body.maxDepth, min_origins=body.minOrigins
    )


@app.post("/api/brain/ask")
async def brain_ask(
    body: BrainAskRequest,
    current_user: User = Depends(get_current_user),
):
    """Ask the brain about a concept: check the graph, learn it live from
    the web if it doesn't know enough yet, then answer with associations +
    derived (inferred) links — streamed as Server-Sent Events."""
    from sse_starlette.sse import EventSourceResponse
    from backend.services import brain_service, brain_learn
    from backend.services.neo4j_service import get_driver
    import httpx

    concept = body.concept.strip().lower()
    LEARN_THRESHOLD = int(os.getenv("LEARN_THRESHOLD", "3"))

    async def gen():
        yield {"data": json.dumps({"stage": "thinking", "concept": concept})}
        assoc = await brain_service._top_associations(concept)
        if len(assoc) < LEARN_THRESHOLD:
            yield {"data": json.dumps({"stage": "gap", "concept": concept})}
            yield {"data": json.dumps({"stage": "learning", "source": "Wikipedia"})}
            try:
                async with httpx.AsyncClient(timeout=30, headers=brain_learn.UA_HEADERS) as client:
                    learned = await brain_learn.learn_concept(concept, client, get_driver())
                yield {"data": json.dumps({
                    "stage": "grew",
                    "new_concepts": learned["new_concepts"],
                    "new_edges": learned["new_edges"],
                })}
                assoc = await brain_service._top_associations(concept)
            except Exception:
                yield {"data": json.dumps({
                    "stage": "answer",
                    "concept": concept,
                    "associations": [],
                    "inferred": [],
                    "note": "couldn't learn that one — try a broader term",
                })}
                yield {"data": json.dumps({"stage": "done"})}
                return
        inferred = await brain_service.infer_links(concept)
        yield {"data": json.dumps({
            "stage": "answer",
            "concept": concept,
            "associations": assoc,
            "inferred": inferred,
        })}
        yield {"data": json.dumps({"stage": "done"})}

    return EventSourceResponse(gen(), headers={"X-Accel-Buffering": "no"})


# ── Tutoring Engine ────────────────────────────────────────────────────────────

@app.get("/api/tutor/paths")
async def get_learning_paths():
    return await tutor_service.get_learning_paths()


@app.post("/api/tutor/quiz")
async def get_quiz(body: TutorQuizRequest, current_user: User = Depends(get_current_user)):
    return await tutor_service.get_quiz(body.topic, body.difficulty, user_id=str(current_user.id))


@app.post("/api/tutor/explain")
async def explain_topic(body: TutorExplainRequest, current_user: User = Depends(get_current_user)):
    explanation = await tutor_service.explain_topic(body.topic, body.level, user_id=str(current_user.id))
    return {"topic": body.topic, "level": body.level, "explanation": explanation}


@app.post("/api/tutor/challenge")
async def generate_challenge(body: TutorChallengeRequest, current_user: User = Depends(get_current_user)):
    return await tutor_service.generate_challenge(body.topic, body.difficulty, user_id=str(current_user.id))


@app.post("/api/tutor/path")
async def generate_learning_path(body: TutorPathRequest, current_user: User = Depends(get_current_user)):
    return await tutor_service.generate_learning_path(body.goals, body.currentLevel, user_id=str(current_user.id))


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


# ── Global Search ─────────────────────────────────────────────────────────────
@app.get("/api/protected/search")
async def global_search(
    q: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not q or len(q.strip()) < 2:
        return {"sessions": [], "messages": []}
    term = f"%{q.strip().lower()}%"
    # Search sessions by title
    sess_res = await db.execute(
        select(Session)
        .where(Session.owner_id == current_user.id)
        .where(func.lower(Session.title).like(term))
        .limit(5)
    )
    sessions = [session_to_dict(s) for s in sess_res.scalars().all()]
    # Search messages by content
    msg_res = await db.execute(
        select(Message)
        .join(Session, Session.id == Message.session_id)
        .where(Session.owner_id == current_user.id)
        .where(func.lower(Message.content).like(term))
        .order_by(desc(Message.created_at))
        .limit(8)
    )
    messages = [message_to_dict(m) for m in msg_res.scalars().all()]
    return {"sessions": sessions, "messages": messages}


# ── Dev-only: proxy non-API requests to Vite dev server ──────────────────────
# In production (Docker) Nginx serves the frontend — set VITE_URL="" to disable.

import httpx as _httpx_proxy

VITE_URL = os.environ.get("VITE_URL", "http://localhost:5173")

@app.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def vite_proxy(path: str, request: Request):
    # API routes are always handled by FastAPI — never forward to Vite.
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail=f"API route not found: /{path}")

    # Production / Docker: Nginx serves the SPA, so disable the Vite proxy.
    # To re-enable for development, set VITE_URL=http://localhost:5173 in the env.
    if not VITE_URL:
        raise HTTPException(status_code=404, detail="Not found")

    url = f"{VITE_URL}/{path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    body = await request.body()
    _timeout_errors = (
        _httpx_proxy.ConnectError, _httpx_proxy.ReadTimeout,
        _httpx_proxy.ConnectTimeout, _httpx_proxy.TimeoutException,
    )

    try:
        async with _httpx_proxy.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.request(method=request.method, url=url, headers=headers, content=body)
            resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in ("transfer-encoding", "content-encoding")}
            return Response(content=resp.content, status_code=resp.status_code, headers=resp_headers)
    except _timeout_errors:
        for _ in range(5):
            await asyncio.sleep(0.5)
            try:
                async with _httpx_proxy.AsyncClient(timeout=10.0, follow_redirects=True) as retry_client:
                    resp = await retry_client.request(method=request.method, url=url, headers=headers, content=body)
                    resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in ("transfer-encoding", "content-encoding")}
                    return Response(content=resp.content, status_code=resp.status_code, headers=resp_headers)
            except _timeout_errors:
                continue
        return Response(
            content=b"<html><body><h2>Starting...</h2><script>setTimeout(()=>location.reload(),2000)</script></body></html>",
            status_code=503, media_type="text/html",
        )

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
