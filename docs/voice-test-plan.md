# Manual voice test plan (LiveKit Agent Console)

Unit tests and `make evals` check rules and behaviour. Only a real call shows speech
recognition, turn-taking, audio smoothness and latency. Run this before recording the demo.

## Setup

1. `uv run clinic reset-demo`, then start the worker:
   `uv run --env-file .env python -m agent.main dev` (or `lk agent dev`).
2. Use headphones (no echo). Open the Agent Console and connect.
3. Keep the worker terminal visible. After each call, save the log: the timing lines are
   `event=turn_latency`, `event=voice_metrics`, `event=llm_timing` and `event=clinic_tool_latency`.

## Calls

Score each call separately on four things: **audio** (no stutter, cut-offs or overlaps),
**responsiveness** (time from you stopping to the agent starting), **dates/digits heard
correctly**, and **naturalness** (no repeated questions, no scripted feel).

| # | What you say | What should happen |
|---|---|---|
| 1 | Just listen to the greeting. | Recording notice once, then "How can I help you today?" Nothing repeated later. |
| 2 | "I need a refill." Then, one per turn: "Sarah Johnson", "March", "fourteenth", "nineteen eighty-five", "three three four four". | Asks only for what's missing, accepts the date in pieces, never reads the DOB or digits back, verifies, then asks which medication. |
| 3 | "Hi, I'm Sarah Johnson, born March 14th 1985, last four 3344. When's my next appointment?" | No further identity questions; answers Thursday, December 3rd at 10:30 AM with Dr. Patel. |
| 4 | Give Michael Brown with DOB "November 9th 1972", then "sorry, my date of birth is November 8th 1972", then last four "1020". | Uses the corrected date and verifies. Then try a wrong last four in a new call: the generic failure line, no hint which detail was wrong. |
| 5 | Verified as Sarah: "Can I refill my metformin?" then "yes". | Reads back Metformin 500mg at CVS Main St, waits for yes, then says it goes to the doctor for approval (no refills left). Never says "approved". |
| 6 | Verified as Sarah: "Is there anything on Wednesday December 2nd with Dr. Lee?" | Offers only real Dr. Lee times (10 AM, 1:30 PM). Ask for "the 3rd": it must say there's nothing then, not invent one. |
| 7 | New patient: "It's my first visit, I'd like to book." Give name, DOB, phone, email, "self-pay", "annual check-up", "Dr. Patel, Friday morning". | First-visit question, no SSN question, Friday 9 AM offered, full read-back with spelled email, books only after yes, arrival instructions, "anything else?". |
| 8 | Mid-call, an unexpected question: "Where are you located?" / "Which doctor does internal medicine?" | Answers (120 Main Street; Dr. Lee) and returns to the task. |
| 9 | After hours (see README, time simulation) "I want my balance." | Office closed, no balance, takes name/number/short reason, reads back, scripted closing. |
| 10 | At any point: "I'm having chest pain." | Immediate 911 line, call ends, nothing else said. |

## Latency evidence to collect

For calls 2, 3 and 7, record from the log:

- `end_of_turn_delay` and `transcription_delay` (caller stops → turn committed)
- `llm_node_ttft` / `ttft_ms` (time to first LLM token)
- `tts_node_ttfb` and TTS `real_time_factor` (above 1.0 means speech is generated slower than it plays, which is heard as stutter)
- `interrupted=True` on agent messages you did not interrupt (false barge-in or echo)
- any `flush audio emitter due to slow audio generation` or `event loop blocked` warnings

A healthy turn is roughly: end of turn under 1 s, LLM first token under 1.5 s, TTS first
byte under 0.5 s, real-time factor well under 1. If the RTF is high or the slow-audio warning
remains, compare a run with the worker in a US region; the last log showed it registered in
India South, while Deepgram and the LLM are US-hosted.
