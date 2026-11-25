from agent.report import parse, render

LOG = """\
2026-11-25 10:00:00,000 INFO sunrise.agent event=voice_session_started call_id=c1 clinic_mode=open simulated_time=False clinic_time=x
2026-11-25 10:00:01,000 INFO sunrise.agent.metrics event=turn_latency call_id=c1 role=user chars=12 interrupted=False values={"end_of_turn_delay": 0.8}
2026-11-25 10:00:02,000 INFO sunrise.agent.metrics event=turn_latency call_id=c1 role=assistant chars=40 interrupted=True values={"llm_node_ttft": 1.2, "tts_node_ttfb": 0.3}
2026-11-25 10:00:02,100 INFO sunrise.agent.metrics event=voice_metrics call_id=c1 type=TTSMetrics values={"ttfb": 0.3, "real_time_factor": 0.4, "streamed": true}
2026-11-25 10:00:02,200 INFO sunrise.agent event=llm_timing call_id=c1 ttft_ms=950 total_ms=1800 outcome=success
2026-11-25 10:00:02,300 WARNING livekit.agents flush audio emitter due to slow audio generation
2026-11-25 10:00:03,000 INFO sunrise.agent event=verification call_id=c1 outcome=failed
2026-11-25 10:00:03,100 INFO sunrise.agent.tools event=tool_refused error_category=UnauthorizedPatientAccess
2026-11-25 10:00:03,200 WARNING sunrise.agent.speech_guard event=speech_blocked call_id=c1 rule=dosing_advice
2026-11-25 10:00:03,300 INFO sunrise.agent event=emergency_detected call_id=c1
"""  # noqa: E501


def test_report_aggregates_timings_and_warnings_per_call() -> None:
    calls = parse(LOG.splitlines())

    call = calls["c1"]
    assert call.mode == "open"
    assert call.values["turn.user.end_of_turn_delay"] == [0.8]
    assert call.values["turn.assistant.llm_node_ttft"] == [1.2]
    assert call.values["TTSMetrics.real_time_factor"] == [0.4]
    assert call.values["llm_timing.ttft_ms"] == [950.0]
    assert call.interrupted_agent_turns == 1
    assert call.warnings["slow audio generation (heard as stutter)"] == 1
    assert dict(call.events) == {
        "verification:failed": 1,
        "tool_refused:UnauthorizedPatientAccess": 1,
        "speech_blocked:dosing_advice": 1,
        "emergency_detected": 1,
    }
    rendered = render(call)
    assert "turn.assistant.llm_node_ttft" in rendered
    assert "speech_blocked:dosing_advice x1" in rendered
