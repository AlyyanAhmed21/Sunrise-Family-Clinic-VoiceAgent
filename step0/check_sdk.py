"""Inspect the installed LiveKit Agents SDK without making network calls."""

from __future__ import annotations

import inspect
import sys
from importlib.metadata import PackageNotFoundError, version


def _show_signature(label: str, target: object) -> None:
    try:
        print(f"{label}: {inspect.signature(target)}")
    except (TypeError, ValueError) as exc:
        print(f"{label}: signature unavailable ({type(exc).__name__})")


def _show_source(label: str, target: object, needles: tuple[str, ...]) -> None:
    source_file = getattr(target, "__file__", None) or inspect.getsourcefile(target)
    print(f"\n[{label}] {source_file}")
    if not source_file:
        return
    try:
        source_lines = inspect.getsourcelines(target)[0]
    except (OSError, TypeError):
        return
    for index, line in enumerate(source_lines, 1):
        if any(needle in line for needle in needles):
            start = max(1, index - 3)
            end = min(len(source_lines), index + 5)
            for line_number in range(start, end + 1):
                print(f"{line_number:>4}: {source_lines[line_number - 1].rstrip()}")
            print("...")


def _show_matching_source(
    label: str, target: object, needles: tuple[str, ...], radius: int = 5
) -> None:
    source_file = getattr(target, "__file__", None) or inspect.getsourcefile(target)
    print(f"\n[{label}] {source_file}")
    if not source_file:
        return
    try:
        lines = open(source_file, encoding="utf-8").readlines()
    except OSError:
        return
    shown: set[int] = set()
    for needle in needles:
        hit = next((index for index, line in enumerate(lines) if needle in line), None)
        if hit is None:
            print(f"  not found: {needle}")
            continue
        print(f"  match: {needle}")
        for index in range(max(0, hit - radius), min(len(lines), hit + radius + 1)):
            if index not in shown:
                print(f"{index + 1:>5}: {lines[index].rstrip()}")
                shown.add(index)
        print("...")


def main() -> int:
    try:
        print("livekit-agents:", version("livekit-agents"))
        from livekit.agents import Agent, AgentSession
        from livekit.agents.voice import agent_activity, turn
        from livekit.agents.voice.turn import TurnHandlingOptions
    except (PackageNotFoundError, ImportError) as exc:
        print(f"LiveKit SDK import failed: {exc}", file=sys.stderr)
        return 2

    _show_signature("Agent.__init__", Agent.__init__)
    _show_signature("Agent.llm_node", Agent.llm_node)
    _show_signature("Agent.on_user_turn_completed", Agent.on_user_turn_completed)
    _show_signature("AgentSession.__init__", AgentSession.__init__)
    _show_signature("AgentSession.start", AgentSession.start)
    _show_signature("TurnHandlingOptions", TurnHandlingOptions)
    _show_source("Agent.llm_node", Agent.llm_node, ("Agent.default.llm_node",))
    _show_source("Agent.on_user_turn_completed", Agent.on_user_turn_completed, ("Called when",))
    _show_matching_source(
        "agent_activity StopResponse/history path",
        agent_activity,
        (
            "on_user_turn_completed",
            "except StopResponse",
            "chat_ctx.items.append",
            "preemptive_generation",
        ),
        radius=7,
    )
    _show_matching_source(
        "turn handling defaults and resolution",
        turn,
        ("preemptive_generation", "_resolve_preemptive_generation"),
        radius=5,
    )

    session_params = inspect.signature(AgentSession.start).parameters
    agent_params = inspect.signature(Agent.__init__).parameters
    required = {"record", "room", "agent"}
    missing = required - set(session_params)
    if missing:
        print(f"FAIL: AgentSession.start missing expected parameters: {sorted(missing)}")
        return 1
    if "turn_handling" not in agent_params:
        print("FAIL: Agent.__init__ has no turn_handling parameter")
        return 1
    print("PASS: record=False and per-agent turn_handling are exposed by this SDK.")
    print("NOTE: inspect StopResponse and on_end_of_turn history handling.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
