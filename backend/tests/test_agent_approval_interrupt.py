"""LangGraph Phase 2 — the agent can call active (attacking) tools, but the
graph PAUSES for explicit user approval (a LangGraph interrupt) before running
any of them, and only executes on approval.

Uses the in-memory checkpointer (build_agent_graph() default) so the whole
interrupt/resume cycle runs in one test process; production uses the Postgres
checkpointer for cross-worker durability.
"""
import json

import pytest
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from backend.services import langgraph_agent_service as lg
from backend.services.tool_service import ACTIVE_TOOLS


def _scripted(replies):
    calls = {"n": 0}

    async def _fake(*a, **k):
        i = min(calls["n"], len(replies) - 1)
        calls["n"] += 1
        return replies[i]

    return _fake, calls


def _state(message, thread):
    return lg.AgentState(
        messages=[HumanMessage(content=message)],
        agent="", session_id=thread, user_id="u",
        tool_results=[], rag_context="", next="router", metadata={}, error=None,
    )


class TestActiveToolsAreAgentCallable:
    def test_active_tools_registered_for_the_analyst_persona(self):
        # Phase 2: the offensive persona CAN call the attack tools (gated).
        analyst_tools = set(lg._allowed_tool_names("analyst"))
        assert ACTIVE_TOOLS.issubset(analyst_tools)

    def test_active_tools_have_akkitool_wrappers(self):
        registered = {t.name for t in lg.AVAILABLE_TOOLS}
        assert ACTIVE_TOOLS.issubset(registered)


class TestApprovalInterrupt:
    async def test_active_tool_pauses_for_approval_then_runs_on_approve(self, monkeypatch):
        replies = [
            '{"tool": "vuln_scan", "args": {"host": "acme.io"}}',
            "Scan complete — final answer.",
        ]
        fake, _ = _scripted(replies)
        monkeypatch.setattr(lg.ai_service, "chat_completion", fake)

        ran = {"vuln": False}
        async def fake_vuln(**kwargs):
            ran["vuln"] = True
            assert kwargs == {"host": "acme.io"}
            return json.dumps({"result": "open ports found"})
        monkeypatch.setattr(lg._TOOL_BY_NAME["vuln_scan"], "_arun", fake_vuln)

        graph = lg.build_agent_graph()
        cfg = {"configurable": {"thread_id": "t-approve"}}

        # First pass PAUSES on the approval interrupt — tool has NOT run yet.
        r1 = await graph.ainvoke(_state("run a vuln scan exploit on acme.io", "t-approve"), config=cfg)
        pending = lg._extract_pending_approval(r1)
        assert pending is not None
        assert pending["tool"] == "vuln_scan"
        assert ran["vuln"] is False  # nothing executed before approval

        # Resume with approval — now the tool actually runs, loop finishes.
        r2 = await graph.ainvoke(Command(resume={"approved": True}), config=cfg)
        assert ran["vuln"] is True
        tcalls = r2["metadata"]["tool_calls"]
        assert tcalls == [{"tool": "vuln_scan", "args": {"host": "acme.io"}, "approved": True}]
        assert "final answer" in r2["messages"][-1].content

    async def test_active_tool_denied_does_not_run(self, monkeypatch):
        replies = [
            '{"tool": "vuln_scan", "args": {"host": "acme.io"}}',
            "Understood, I will not scan without authorization.",
        ]
        fake, _ = _scripted(replies)
        monkeypatch.setattr(lg.ai_service, "chat_completion", fake)

        ran = {"vuln": False}
        async def fake_vuln(**kwargs):
            ran["vuln"] = True
            return "should not run"
        monkeypatch.setattr(lg._TOOL_BY_NAME["vuln_scan"], "_arun", fake_vuln)

        graph = lg.build_agent_graph()
        cfg = {"configurable": {"thread_id": "t-deny"}}

        r1 = await graph.ainvoke(_state("run a vuln scan exploit on acme.io", "t-deny"), config=cfg)
        assert lg._extract_pending_approval(r1) is not None

        # Deny — the tool must NOT execute.
        r2 = await graph.ainvoke(Command(resume={"approved": False}), config=cfg)
        assert ran["vuln"] is False
        tcalls = r2["metadata"]["tool_calls"]
        assert tcalls and tcalls[-1]["approved"] is False

    async def test_passive_tool_does_not_pause(self, monkeypatch):
        # A safe recon tool runs without any approval interrupt.
        replies = [
            '{"tool": "dns_lookup", "args": {"domain": "acme.io"}}',
            "DNS resolved — final answer.",
        ]
        fake, _ = _scripted(replies)
        monkeypatch.setattr(lg.ai_service, "chat_completion", fake)
        async def fake_dns(**kwargs):
            return json.dumps({"A": ["1.2.3.4"]})
        monkeypatch.setattr(lg._TOOL_BY_NAME["dns_lookup"], "_arun", fake_dns)

        graph = lg.build_agent_graph()
        cfg = {"configurable": {"thread_id": "t-passive"}}
        r1 = await graph.ainvoke(_state("run a dns lookup on acme.io", "t-passive"), config=cfg)
        # No interrupt — it completed in one pass.
        assert lg._extract_pending_approval(r1) is None
        assert "final answer" in r1["messages"][-1].content
