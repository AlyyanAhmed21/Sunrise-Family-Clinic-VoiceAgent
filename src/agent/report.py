"""Summarize voice-call performance from the masked agent logs (`logs/agent-YYYY-MM-DD.log`).

    uv run clinic-report             # every call in today's (newest) log
    uv run clinic-report --last      # only the most recent call
    uv run clinic-report --all       # every call in the last 7 days
    uv run clinic-report --file logs/agent-2026-11-25.log

For each call: count, median, 95th percentile and max of every timing the agent logs, plus
counts of the warnings that accompany choppy audio. The log holds numbers and ids only.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

_EVENT = re.compile(r"event=(?P<event>\w+) call_id=(?P<call>[\w-]+)(?P<rest>.*)")
_VALUES = re.compile(r"values=(\{.*\})")
_PAIR = re.compile(r"(\w+)=([\w.:-]+)")
_WARNINGS = {
    "slow audio generation (heard as stutter)": "flush audio emitter due to slow audio generation",
    "event loop blocked": "event loop blocked",
}

# What to look at first, with a rough "healthy" level for a phone conversation.
KEY_METRICS = {
    "turn.user.end_of_turn_delay": "caller stops -> turn committed (s); healthy < 1.0",
    "turn.user.transcription_delay": "caller stops -> final transcript (s); healthy < 0.5",
    "turn.assistant.llm_node_ttft": "LLM time to first token (s); healthy < 1.5",
    "turn.assistant.tts_node_ttfb": "TTS time to first audio (s); healthy < 0.5",
    "TTSMetrics.real_time_factor": "TTS synth time / audio length; > 1 means audio starves",
    "llm_timing.ttft_ms": "LLM time to first token incl. screening (ms)",
    "clinic_tool_latency.duration_ms": "database/service time per tool call (ms)",
}


# Safety and outcome events, counted per call (the log holds the category, never content).
_OUTCOME_EVENTS = {"verification", "speech_blocked", "emergency_detected", "tool_refused"}


@dataclass
class CallReport:
    call_id: str
    started: str = ""
    mode: str = ""
    values: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    warnings: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    events: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    interrupted_agent_turns: int = 0


def parse(lines: list[str]) -> dict[str, CallReport]:
    calls: dict[str, CallReport] = {}
    current: CallReport | None = None
    for line in lines:
        match = _EVENT.search(line)
        if match is None:
            if current is not None:
                for label, needle in _WARNINGS.items():
                    if needle in line:
                        current.warnings[label] += 1
                refused = re.search(r"event=tool_refused error_category=(\w+)", line)
                if refused:  # logged without a call id: belongs to the call in progress
                    current.events[f"tool_refused:{refused.group(1)}"] += 1
            continue
        call = calls.setdefault(match["call"], CallReport(match["call"]))
        current = call
        _record(call, match["event"], match["rest"], line)
    return calls


def _record(call: CallReport, event: str, rest: str, line: str) -> None:
    pairs = dict(_PAIR.findall(rest))
    values_match = _VALUES.search(rest)
    values = json.loads(values_match.group(1)) if values_match else {}
    if event in _OUTCOME_EVENTS:
        detail = pairs.get("outcome") or pairs.get("rule") or pairs.get("error_category") or ""
        call.events[f"{event}:{detail}" if detail else event] += 1
    if event == "voice_session_started":
        call.started, call.mode = line[:19], pairs.get("clinic_mode", "")
    elif event == "turn_latency":
        if pairs.get("role") == "assistant" and pairs.get("interrupted") == "True":
            call.interrupted_agent_turns += 1
        for name, value in values.items():
            call.values[f"turn.{pairs.get('role')}.{name}"].append(float(value))
    elif event == "voice_metrics":
        for name, value in values.items():
            if not isinstance(value, bool):
                call.values[f"{pairs.get('type')}.{name}"].append(float(value))
    elif event in ("llm_timing", "clinic_tool_latency", "turn_screened"):
        for name in ("ttft_ms", "total_ms", "duration_ms"):
            if name in pairs and pairs[name] not in ("none", "unavailable"):
                call.values[f"{event}.{name}"].append(float(pairs[name]))


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def render(call: CallReport) -> str:
    lines = [f"\n=== call {call.call_id}  {call.started}  mode={call.mode or '?'}"]
    lines.append(f"{'metric':45} {'n':>4} {'p50':>9} {'p95':>9} {'max':>9}")
    ordered = [m for m in KEY_METRICS if m in call.values]
    ordered += sorted(m for m in call.values if m not in KEY_METRICS)
    for name in ordered:
        data = call.values[name]
        lines.append(
            f"{name:45} {len(data):>4} {_percentile(data, 0.5):>9.3f} "
            f"{_percentile(data, 0.95):>9.3f} {max(data):>9.3f}"
        )
    outcomes = ", ".join(f"{name} x{count}" for name, count in sorted(call.events.items()))
    lines.append(f"safety/outcome events: {outcomes or 'none'}")
    lines.append(f"agent turns interrupted: {call.interrupted_agent_turns}")
    for label in _WARNINGS:
        lines.append(f"{label}: {call.warnings.get(label, 0)}")
    return "\n".join(lines)


def log_files(directory: Path, *, all_days: bool) -> list[Path]:
    files = sorted(directory.glob("agent-*.log"))  # ISO dates sort chronologically
    return files if all_days else files[-1:]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, help="a specific log file")
    parser.add_argument("--all", action="store_true", help="every day kept in logs/")
    parser.add_argument("--last", action="store_true", help="only the most recent call")
    args = parser.parse_args()
    files = [args.file] if args.file else log_files(Path("logs"), all_days=args.all)
    if not files or not all(path.exists() for path in files):
        raise SystemExit("No agent log found in logs/. Make a call with the agent first.")
    lines = [line for path in files for line in path.read_text(encoding="utf-8").splitlines()]
    calls = list(parse(lines).values())
    if args.last:
        calls = calls[-1:]
    print("Key metrics:")
    for name, meaning in KEY_METRICS.items():
        print(f"  {name}: {meaning}")
    for call in calls:
        print(render(call))


if __name__ == "__main__":
    main()
