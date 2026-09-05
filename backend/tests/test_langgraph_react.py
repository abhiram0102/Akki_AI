"""Tests for the real ReAct tool-calling loop in langgraph_agent_service.

These exercise the actual compiled LangGraph (router -> reason -> tools ->
reason -> END) with a scripted fake LLM and a fake tool, proving the agent
genuinely decides, calls a tool, executes it, observes the result, and then
answers — the behaviour that was previously faked (tools were wrapped but
never wired into the graph).
"""
import json

import pytest
from langchain_core.messages import HumanMessage, AIMessage

from backend.services import langgraph_agent_service as lg


# ── _parse_tool_call (pure) ──────────────────────────────────────────────────

class TestParseToolCall:
    def test_plain_json_tool_call(self):
        out = lg._parse_tool_call('{"tool": "dns_lookup", "args": {"domain": "example.com"}}')
        assert out == {"tool": "dns_lookup", "args": {"domain": "example.com"}}

    def test_json_wrapped_in_code_fence(self):
        out = lg._parse_tool_call('```json\n{"tool": "port_scan", "args": {"host": "x"}}\n```')
        assert out == {"tool": "port_scan", "args": {"host": "x"}}

    def test_json_with_surrounding_prose_is_still_extracted(self):
        out = lg._parse_tool_call('Sure, let me check: {"tool": "whois", "args": {"target": "x"}}')
        assert out is not None and out["tool"] == "whois"

    def test_prose_answer_returns_none(self):
        assert lg._parse_tool_call("The domain resolves to 1.2.3.4 and looks healthy.") is None

    def test_missing_tool_key_returns_none(self):
        assert lg._parse_tool_call('{"args": {"domain": "x"}}') is None

    def test_malformed_json_returns_none(self):
        assert lg._parse_tool_call('{"tool": "dns_lookup", args: broken}') is None

    def test_args_defaults_to_empty_when_absent(self):
        out = lg._parse_tool_call('{"tool": "knowledge_base"}')
        assert out == {"tool": "knowledge_base", "args": {}}


# ── end-to-end graph runs ────────────────────────────────────────────────────

def _scripted_completion(replies):
    """Return an async chat_completion stand-in that yields `replies` in order,
    then repeats the last one."""
    calls = {"n": 0}

    async def _fake(*args, **kwargs):
        i = min(calls["n"], len(replies) - 1)
        calls["n"] += 1
        return replies[i]

    return _fake, calls


def _initial_state(message: str):
    return lg.AgentState(
        messages=[HumanMessage(content=message)],
        agent="",
        session_id="s1",
        user_id="u1",
        tool_results=[],
        rag_context="",
        next="router",
        metadata={},
        error=None,
    )


class TestReactLoopEndToEnd:
    async def test_agent_calls_tool_then_answers(self, monkeypatch):
        # "dns lookup" routes to the researcher persona, which has dns_lookup
        # in scope. (Avoid "example.com" — the keyword router substring-matches
        # "exam" inside it and mis-routes to the tutor persona.)
        replies = [
            '{"tool": "dns_lookup", "args": {"domain": "acme.io"}}',
            "The domain acme.io resolves to 1.2.3.4 — final answer.",
        ]
        fake_completion, calls = _scripted_completion(replies)
        monkeypatch.setattr(lg.ai_service, "chat_completion", fake_completion)

        async def fake_dns(**kwargs):
            assert kwargs == {"domain": "acme.io"}  # args threaded through correctly
            return json.dumps({"A": ["1.2.3.4"]})
        monkeypatch.setattr(lg._TOOL_BY_NAME["dns_lookup"], "_arun", fake_dns)

        graph = lg.build_agent_graph()
        final = await graph.ainvoke(
            _initial_state("run a dns lookup on acme.io"),
            config={"configurable": {"thread_id": "t-answer"}},
        )

        # The tool was actually executed and recorded.
        tool_calls = final["metadata"]["tool_calls"]
        assert tool_calls == [{"tool": "dns_lookup", "args": {"domain": "acme.io"}}]
        # The final message is the prose answer, not the tool JSON.
        last = final["messages"][-1]
        assert isinstance(last, AIMessage)
        assert "1.2.3.4" in last.content and "final answer" in last.content
        # LLM was called twice: decide-to-call, then answer-after-observation.
        assert calls["n"] == 2

    async def test_answer_without_any_tool_call(self, monkeypatch):
        fake_completion, calls = _scripted_completion(["Here is a direct conceptual answer, no tool needed."])
        monkeypatch.setattr(lg.ai_service, "chat_completion", fake_completion)

        graph = lg.build_agent_graph()
        final = await graph.ainvoke(
            _initial_state("explain what a subnet is"),
            config={"configurable": {"thread_id": "t-direct"}},
        )
        assert final["metadata"].get("tool_calls", []) == []
        assert "direct conceptual answer" in final["messages"][-1].content
        assert calls["n"] == 1

    async def test_iteration_cap_terminates_the_loop(self, monkeypatch):
        # The model always tries to call a tool; the loop must stop at the cap.
        always_tool = '{"tool": "dns_lookup", "args": {"domain": "acme.io"}}'
        fake_completion, _ = _scripted_completion([always_tool])
        monkeypatch.setattr(lg.ai_service, "chat_completion", fake_completion)

        async def fake_dns(**kwargs):
            return json.dumps({"A": ["1.2.3.4"]})
        monkeypatch.setattr(lg._TOOL_BY_NAME["dns_lookup"], "_arun", fake_dns)

        graph = lg.build_agent_graph()
        final = await graph.ainvoke(
            _initial_state("dns lookup acme.io again"),
            config={"configurable": {"thread_id": "t-cap"}},
        )
        # Exactly MAX_TOOL_ITERATIONS tools ran, then it stopped (no infinite loop).
        assert len(final["metadata"]["tool_calls"]) == lg.MAX_TOOL_ITERATIONS

    async def test_out_of_scope_tool_is_not_executed(self, monkeypatch):
        # tutor persona's only tool is knowledge_base; a request to call
        # dns_lookup must NOT execute — it's treated as the final answer.
        replies = ['{"tool": "dns_lookup", "args": {"domain": "example.com"}}']
        fake_completion, _ = _scripted_completion(replies)
        monkeypatch.setattr(lg.ai_service, "chat_completion", fake_completion)

        executed = {"dns": False}
        async def fake_dns(**kwargs):
            executed["dns"] = True
            return "should not run"
        monkeypatch.setattr(lg._TOOL_BY_NAME["dns_lookup"], "_arun", fake_dns)

        graph = lg.build_agent_graph()
        final = await graph.ainvoke(
            _initial_state("teach me how to learn dns"),  # routes to tutor
            config={"configurable": {"thread_id": "t-scope"}},
        )
        assert executed["dns"] is False
        assert final["metadata"].get("tool_calls", []) == []


class TestToolScoping:
    def test_tutor_cannot_reach_dns_lookup(self):
        assert "dns_lookup" not in lg._allowed_tool_names("tutor")

    def test_researcher_can_reach_dns_lookup(self):
        assert "dns_lookup" in lg._allowed_tool_names("researcher")

    def test_catalogue_lists_arg_names(self):
        text = lg._tool_catalogue_text("researcher")
        assert "dns_lookup" in text and "domain" in text
