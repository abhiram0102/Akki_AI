from typing import Optional, List, Dict, Any
from pydantic import BaseModel


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


class ChatResumeRequest(BaseModel):
    """Resume a paused agent turn after approving/denying an active tool."""
    sessionId: str
    approved: bool


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



class VirusTotalRequest(BaseModel):
    query: str  # domain, IP, URL, or file hash
    query_type: str = "domain"  # domain | ip | url | hash


class CensysRequest(BaseModel):
    query: str
    query_type: str = "host"  # host | cert

# Simple workspace report generation (title + type only)
class SimpleReportRequest(BaseModel):
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


class ReportSectionConfig(BaseModel):
    """Configuration for a report section"""
    type: str  # Section type (executive_summary, findings, methodology, custom, etc.)
    title: str
    content: Optional[str] = None  # For custom content
    template_id: Optional[str] = None  # Reference to a saved template
    data_sources: List[str] = []  # What data to include (findings, scope, etc.)
    config: Dict[str, Any] = {}  # Additional configuration


class ReportGenerationRequest(BaseModel):
    """Request for generating a custom report"""
    findings: List[dict]
    executiveSummary: Optional[str] = None
    scope: Optional[str] = None
    sections: List[ReportSectionConfig] = []
    templateId: Optional[str] = None  # Use a saved report configuration
    title: str = "Security Assessment Report"
    reportType: str = "technical"


class ToolExecuteRequest(BaseModel):
    toolName: str
    params: dict
    authorized: bool = False


class BrainDiscoverRequest(BaseModel):
    concept: str
    concept2: str | None = None


class BrainConvergeRequest(BaseModel):
    """Multi-origin convergence: seed concepts to grow branches from."""
    seeds: list[str]
    maxDepth: int = 3
    minOrigins: int = 2


class BrainAskRequest(BaseModel):
    """Ask the brain about a concept — streams thinking/learning/answer
    stages over SSE from POST /api/brain/ask.

    `query` carries a natural question ("why does inflation happen") and is
    parsed by `brain_query` into an intent plus the concepts it names. `concept`
    is the original single-term field and still works unchanged: posting a bare
    concept parses to a DEFINE on that one topic, which is exactly the previous
    behaviour. Both are optional so either style of client is valid; `query`
    wins when both are sent.
    """
    concept: str | None = None
    query: str | None = None


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


# ── Marketplace Schemas ───────────────────────────────────────────────────────

class MarketplaceItemCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    category: str  # tool, agent, data_source
    subcategory: Optional[str] = None
    version: str = "1.0.0"
    author: Optional[str] = None
    repository_url: Optional[str] = None
    documentation_url: Optional[str] = None
    install_command: Optional[str] = None
    config_schema: Optional[Dict[str, Any]] = None
    is_public: bool = False
    is_verified: bool = False


class MarketplaceItemUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    version: Optional[str] = None
    author: Optional[str] = None
    repository_url: Optional[str] = None
    documentation_url: Optional[str] = None
    install_command: Optional[str] = None
    config_schema: Optional[Dict[str, Any]] = None
    is_public: Optional[bool] = None
    is_verified: Optional[bool] = None


class MarketplaceItemInstallRequest(BaseModel):
    config: Optional[Dict[str, Any]] = None


class MarketplaceItemConfigUpdateRequest(BaseModel):
    config: Dict[str, Any]


class MarketplaceItemRatingRequest(BaseModel):
    rating: float  # 0.0 to 5.0


class MarketplaceItemResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    category: str
    subcategory: Optional[str]
    version: str
    author: Optional[str]
    repository_url: Optional[str]
    documentation_url: Optional[str]
    install_command: Optional[str]
    is_public: bool
    is_verified: bool
    download_count: int
    rating: float
    createdAt: str
    updatedAt: str


class UserMarketplaceItemResponse(BaseModel):
    id: str
    marketplaceItemId: str
    installedAt: str
    config: Optional[Dict[str, Any]]
    isEnabled: bool


class StreamChatRequest(BaseModel):
    content: str
    sessionId: Optional[str] = None
    agent: Optional[str] = None
    talk_mode: bool = False   # True → use short friendly Siri-style persona
    history: list[dict] = []  # inline conversation history for talk mode (no DB)


# ── Workflow Schemas ──────────────────────────────────────────────────────────

class WorkflowStepRequest(BaseModel):
    agent_type: str
    prompt_template: str
    config: Optional[dict] = None


class WorkflowCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    steps: List[WorkflowStepRequest] = []


class WorkflowUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class WorkflowStepUpdateRequest(BaseModel):
    agent_type: Optional[str] = None
    prompt_template: Optional[str] = None
    config: Optional[dict] = None
    step_order: Optional[int] = None


class WorkflowReorderRequest(BaseModel):
    step_orders: List[dict]  # Each dict should have "id" and "step_order"


class WorkflowExecutionRequest(BaseModel):
    initial_input: str
    session_id: Optional[str] = None


class SigmaRequest(BaseModel):
    statement: str
    answers: dict = {}   # user's answers to clarifying questions (empty on first call)
