from __future__ import annotations

import pytest

livekit_agents = pytest.importorskip("livekit.agents")

from step0.livekit_guard import GuardedAgent, NoModelAgent  # noqa: E402


def test_no_model_agent_stops_before_llm() -> None:
    from livekit.agents import StopResponse

    agent = NoModelAgent(instructions="test")
    with pytest.raises(StopResponse):
        agent.llm_node({"messages": [{"content": "DOB 1985-03-14"}]}, [], None)


def test_guarded_agent_sends_redacted_copy_to_model(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_llm_node(self, chat_ctx, tools, model_settings):
        captured["context"] = chat_ctx
        return "safe"

    monkeypatch.setattr(livekit_agents.Agent, "llm_node", fake_llm_node)
    original = {"messages": [{"content": "DOB 1985-03-14"}]}
    agent = GuardedAgent(instructions="test")
    result = agent.llm_node(original, [], None)
    assert result == "safe"
    assert "1985-03-14" in original["messages"][0]["content"]
    assert "1985-03-14" not in captured["context"]["messages"][0]["content"]
