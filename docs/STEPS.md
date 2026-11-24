# Build Plan

Exactly six build steps. Repository initialization and this planning-document checkpoint are setup work before Step 0; they are not additional build steps. Work in complete file batches, verify each step, update requirement statuses and `STATUS.md`, then make one conventional commit per completed step. Build steps are delivery batches, not source directories: only the temporary Step 0 harness lives under `step0/`; final application code is organized under `src/clinic/` and `src/agent/`.

## Step 0 — Spikes and environment (30–45 minutes)

**Produces / touches:** root environment files (`pyproject.toml`, generated `uv.lock`, `.python-version`, `.env.example`, `.gitignore`, `Makefile`); the complete `step0/` feasibility harness; `docs/latency.md` and `docs/DECISIONS.md`. The harness is deliberately isolated from final runtime packages.

**Work:** Initialize the public-safe repo and Python 3.12/uv environment; require `HASH_PEPPER` in `.env` and use a test-only pepper in CI; configure provider credentials; build the smallest LiveKit voice loop in `step0/smoke_agent.py`; verify Agent Console audio and a harmless deterministic tool call. Disable session-level `preemptive_generation` by default. Implement and test `NoModelAgent` for verification (agent-level opt-out and model-free `llm_node`) plus `GuardedAgent.llm_node` for every other agent (redact a COPY of context immediately before model egress, covering preemptive, normal and tool-follow-up calls). Confirm verification state remains server-side; test the `on_user_turn_completed` + `StopResponse` behavior and ensure no LLM invocation or LLM latency metric occurs on verification turns. Drive callback privacy tests through `on_end_of_turn` or a live session; do not rely on `session.run(user_input=...)`, which bypasses `on_user_turn_completed`. Check LiveKit Inference model availability/tool calling for `openai/gpt-5.4-mini`, `google/gemma-4-31b-it` and `google/gemini-3.5-flash-lite`; measure credit consumption in the dashboard (credit headroom is unverified until measured). Capture latency baseline and inspect region options. Configure and verify `session.start(record=False)`, LiveKit Cloud project-level Agent observability OFF, and Deepgram STT/TTS `mip_opt_out=True` (confirm exact plugin option/vendor wording). Record actual settings/evidence and normal vendor data transit in README.

**Acceptance:** The SDK/provider probes pass; deterministic spike tests pass; a real browser voice call speaks and hears and the smoke tool call returns its sentinel; raw verification text never reaches any LLM path, including preemptive generation; verification agent makes no model call and emits no LLM metric; other agents redact copied context at model egress and redact inbound content before retention in `session.history` or handoff contexts; all three optional-data controls are configured or their unavailability is documented; model tool calling works; baseline metrics contain no transcript content; credit/region/setting findings are recorded. The LiveKit Cloud observability setting, remote model availability/tool calling, credit headroom, region latency and live history behavior have manual evidence recorded. If an integration is blocked for more than 20 minutes, take the simplest viable fallback and record it in `DECISIONS.md`.

## Step 1 — Domain, security and persistence

**Produces:** `src/clinic/config.py`, `clock.py`, `models.py`, `session.py`, `audit.py`, `logging.py`, `service.py` skeleton; `src/clinic/domain/{hours,verification,refills,appointments,requests}.py`; `src/clinic/security/{parsing,hashing,masking,emergency}.py`; `src/clinic/persistence/{db,repositories,seed,reset,email_outbox}.py`; `data/seed/{patients,slots}.json`; `tests/unit/*`, `tests/security/*`.

**Work:** Define typed domain values/errors and injected clock/config/repositories. Sanitize and seed the three supplied fake patients, medications, appointments, labs, balances and available slots; add only synthetic edge-case records. Remove full SSNs and hash last-four values before persistence. Implement session state, deterministic verification parsing/matching, three-attempt lockout, office-hours logic, emergency detection, masking, structured logs and append-only audit records. Set SQLite constraints/WAL/foreign keys and async-safe access.

**Acceptance:** Unit/security tests pass for hours boundaries, verification match/mismatch/lockout, spoken digits and DOB parsing (including “my last four is…”, “one moment”, “oh”, “double four”, `3344`, `33 44`, `3-3-4-4`, ordinal DOBs and spoken years; reject over-four-digit input), volunteered-identifier detection/routing (including spoken-year DOBs), hash comparison, masking, emergency lexicon, seed sanitization, audit privacy and DB constraints. No full SSN or plaintext last-four value is persisted.

## Step 2 — ClinicService, agents and tools

**Produces:** complete `src/clinic/service.py`; `src/agent/{state,tools,guard,phrases}.py`; `src/agent/agents/{greeter,verification,patient,after_hours,new_patient}.py`; `src/agent/prompts/*.md`; `src/clinic/api/{main,deps,routes_health}.py`; `tests/api/*`, `tests/agent/*`.

**Work:** Implement one in-process `ClinicService` as the authority for business state and authorization. Agent tools call it directly with `call_id`; tools never accept `patient_id`. FastAPI wraps the same service for health, readiness and API tests; demo inspection uses Make commands, not admin routes. Add least-privilege agent tools and LiveKit handoffs. Implement verified refill, appointment, lab-status and billing flows; scripted verification prompts/failures; generic errors; call correlation, timeouts and safe fallbacks.

**Acceptance:** Service/API/agent tests prove that unverified sessions cannot read or mutate patient data, caller/tool-supplied patient IDs are impossible, after-hours mode blocks patient data, each patient workflow returns only minimum necessary data, and handoffs preserve redaction. `/health` and `/ready` behave correctly.

## Step 3 — Booking, after-hours and guardrails

**Produces / completes:** `src/clinic/domain/appointments.py`, `requests.py`, `src/clinic/persistence/email_outbox.py`, `src/agent/agents/new_patient.py`, `after_hours.py`, guard/prompt modules; `tests/unit/test_booking*`, `tests/agent/test_guardrails*`, `tests/security/test_phi_canary.py`; `data/out/.gitkeep`.

**Work:** Complete new- and existing-patient booking, minimal intake, 2–3 slot offers, readback/email spelling, confirmation-before-write, atomic patient+appointment+slot transaction, simulated email outbox and arrival instructions. Implement after-hours callback with no PHI even for an already-verified session. Complete doctor-message/callback/transfer persistence, emergency termination, medical-advice refusal, third-party denial, no-fabrication, off-topic and prompt-injection defenses. Add idempotency and reset behavior.

**Acceptance:** Booking/slot-race/rollback tests pass; all request types persist required metadata; after-hours never discloses patient data; emergency interrupts all flows; PHI canary proves raw identifiers do not appear in logs, audit output, generated artifacts or retained history; all six guardrail categories pass deterministic/agent evaluations.

## Step 4 — Voice tuning, reliability and measurement

**Produces / completes:** `src/agent/config.py`, `src/agent/metrics.py`, `docs/latency.md`, and README privacy/data-flow and vendor/BAA sections.

**Work:** Tune endpointing and interruption behavior, especially digit/DOB collection; compare medication transcription settings; keep fixed/safety prompts scripted; prewarm VAD, turn detector, DB and provider clients; measure EOU, LLM TTFT, TTS TTFB, tool and end-to-end latency. Add bounded timeouts and safe fallbacks. Inspect provider controls and document settings; document normal vendor transit and current BAA status with careful qualification.

**Acceptance:** Rehearsal confirms natural turn-taking, digit/date capture and no raw transcript/audio persistence. `docs/latency.md` contains measured baseline/final p50/p95 by scripted, plain-LLM and tool-call turn where sample size permits; any unmet target is reported honestly. Provider settings and data-flow limitations are documented.

## Step 5 — Documentation, CI, demo and submission

**Produces:** `README.md` (architecture, privacy/data-flow, vendor/BAA and evaluation sections), `docs/hipaa-matrix.md`, `docs/demo-script.md`, concise `docs/interview-notes.md`, `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `Makefile` completion, final `docs/STATUS.md` and requirement statuses.

**Work:** Map all 10 HIPAA principles to implementation and tests; document stack, setup, architecture, verification, booking, after-hours, guardrails, vendor transit/BAAs, production changes and limitations. Add CI for Ruff, mypy, deterministic tests and secret scan. Do not add a Dockerfile or Docker build job. Create exact seven-scene demo script, reset procedure and short interview notes. Run final checklist, record and upload the 5–7 minute real-voice demo, publish the public repository and verify links.

**Acceptance:** Fresh-clone setup works; CI is green; Ruff/mypy/tests pass; domain/security coverage target is reported; no secrets or full SSNs exist in repo/history; all seven scenarios are rehearsed by voice at least twice; public GitHub and demo links open while logged out.

## Priority cut line

- **P0:** real voice, verification/privacy, patient workflows, booking, after-hours, guardrails, audit + PHI canary, README and seven-scene demo.
- **P1:** health/readiness, measured latency report, CI and secret scanning.
- **P2 (cut first):** extra observability infrastructure, post-call graph, real email and real telephony transfer. Docker is excluded from this assessment scope; container image plus PostgreSQL is a future production path only.

Do not add LangGraph, Langfuse, RAG, Prometheus, Grafana or OpenTelemetry unless a concrete requirement or Phase 0 evidence justifies reopening the decision.

## Review amendments (2026-11-24)

**Step 0 additions:** prove the preemptive-generation leak with a raw identifier canary; prove the guarded egress path blocks it; prove verification uses no model and emits no LLM metric. Verify all three data controls: `session.start(record=False)`, LiveKit Cloud Agent observability OFF, and Deepgram STT/TTS `mip_opt_out=True`. Record dashboard/provider evidence and any unavailable control. Test the three candidate LiveKit Inference model IDs: `openai/gpt-5.4-mini`, `google/gemma-4-31b-it`, and `google/gemini-3.5-flash-lite`; verify current availability and tool calling, and check credit headroom in the dashboard.
**Step 1 additions:** implement the complete parser regression set, including volunteered spoken-year DOB detection; require `HASH_PEPPER` for seeding and fail clearly if absent. CI uses a test-only pepper.
**Step 2 additions:** disable session preemptive generation by default; `VerificationAgent` is `NoModelAgent` with an `llm_node` that never calls a model; other agents are `GuardedAgent` with last-point copy redaction. Redact before history/handoff retention too. Do not rely on `on_user_turn_completed` + `StopResponse` to retain a turn, or on `session.run(user_input=...)` to exercise that hook.
**Step 5 scope:** no Dockerfile and no Docker build job. Keep architecture/privacy/vendor/evaluation narrative in README sections. If time remains, a tiny Dockerfile is P2 only and must be verified on CI before inclusion.
