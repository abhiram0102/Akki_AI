"""Guard: active (attacking) exploit tools are not YET wired into the live AI
agent's callable tool set.

Current state (LangGraph Phase 1): the agent can call the safe recon/knowledge
tools only; the 6 active exploit tools are reachable exclusively through the
Live Tools panel + /api/tools/execute behind the authorization attestation
(see test_tool_execute_auth_gate.py). They are deliberately NOT bound to the
agent graph, because the approval-gate interrupt that must precede any
agent-initiated attack does not exist yet.

Phase 2 (persistent checkpointer + interrupt_before on the tool node for
ACTIVE_TOOLS) will intentionally make these tools agent-callable *behind that
gate*. When Phase 2 lands, this guard should be REPLACED with one asserting
"no active tool executes without passing through the approval interrupt" —
not simply deleted. Until then, this catches an active tool being wired to the
agent prematurely (i.e. callable with no gate at all), which would be unsafe.

The live agent registry is langgraph_agent_service.py (agent_service.py is
dead code, imported nowhere).
"""
from backend.services.tool_service import ACTIVE_TOOLS
from backend.services import langgraph_agent_service as lg


def test_no_active_tool_is_in_any_agent_tool_mapping():
    all_agent_callable = set()
    for tool_names in lg.AGENT_TOOL_MAPPING.values():
        all_agent_callable.update(tool_names)
    leaked = ACTIVE_TOOLS & all_agent_callable
    assert not leaked, (
        f"Active exploit tools are agent-callable with no approval gate yet: {leaked}. "
        "Until Phase 2's interrupt gate exists, active tools must not be in "
        "AGENT_TOOL_MAPPING."
    )


def test_no_active_tool_is_a_registered_langchain_tool():
    registered_names = {t.name for t in lg.AVAILABLE_TOOLS}
    leaked = ACTIVE_TOOLS & registered_names
    assert not leaked, (
        f"Active exploit tools are registered as bindable agent tools with no "
        f"approval gate yet: {leaked}. Until Phase 2, keep them out of AVAILABLE_TOOLS."
    )
