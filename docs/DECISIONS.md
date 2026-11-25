# Architecture and Implementation Decisions

Short records of decisions that affect the design, in the order they were made. Later records supersede earlier ones where they say so (notably ADR-030, which replaced the original scripted, model-free conversation design).

## ADR-001 — LiveKit-native voice orchestration
**Decision:** Use LiveKit Agents for the real-time voice loop, agent routing, turn-taking and handoffs. Do not put LangGraph in the live call path.

**Reason:** LiveKit already owns voice-session concerns such as streaming, interruption and agent handoffs. A second orchestration layer adds complexity and latency without a checkpoint/resume need in these short calls. Verification, authorization, booking and emergency decisions remain deterministic in the service/domain layer.

## ADR-002 — In-process ClinicService; no HTTP surface in the assessment
**Decision:** Agent tools call the in-process `ClinicService` directly. Every tool receives `call_id` and no `patient_id`. `ClinicService` derives the patient from server-side session state, enforces authorization and business rules, and raises typed domain errors. Local operators use `clinic.cli` / Make targets for request inspection, audit inspection and demo reset. There is no agent-to-service HTTP hop, internal service key, or public admin API.

**Reason:** The official deliverable is a real-time voice agent, not a general clinic API. A local CLI provides the required demo operations without adding a network surface or an unnecessary dependency. A future production deployment may add authenticated health/readiness endpoints or split the service behind an API without changing domain contracts.

**Review amendment (2026-11-24):** The earlier FastAPI wrapper proposal was intentionally deferred. The current assessment does not need `/health`, `/ready`, or admin routes; local CLI commands cover operator workflows. Requirements R-14/R-47 are marked partial/deferred rather than claimed complete.

## ADR-003 — Server-side session is the identity authority
**Decision:** Persist call/session state keyed by `call_id`, including open/closed mode, verification state, failed-attempt count and verified patient reference. LLM/tool arguments cannot select a patient. Authorization fails closed.

**Reason:** Prevents prompt injection or caller-supplied identifiers from becoming authority. Business state is controlled by the backend, not inferred from conversation text.

## ADR-004 — Verification parsing and model-egress privacy guards
**Decision:** Parse name, DOB and spoken last-four digits deterministically in code. Disable session-level `preemptive_generation` by default. `VerificationAgent` extends `NoModelAgent`, opts out at agent level and has an `llm_node` that never invokes a model. All other agents extend `GuardedAgent`; its `llm_node` redacts a COPY of chat context immediately before every model invocation, covering preemptive generation, normal turns and tool-follow-up turns. Separately redact sensitive inbound content before it is retained in `session.history` or passed in handoff contexts. The final egress guard must not mutate original history. Verification progress lives only in server-side session state. Per-agent `turn_handling` settings may tune endpointing/interruption but are not the privacy boundary. Verification turns emit no LLM invocation or LLM latency metric. Never echo DOB or SSN digits.

**Reason:** In the reviewed LiveKit Agents 1.8.13 behavior, preemptive generation can invoke the model with raw transcript text before `on_user_turn_completed`; callback-only redaction is too late. Also, `on_user_turn_completed` followed by `StopResponse` drops the turn rather than retaining it in `session.history`; in Agents 1.8.13, raising it from `llm_node` was also logged as an inference failure. The implementation now returns an empty async stream instead. A final model-egress guard plus a no-model verification agent closes the model leak; pre-retention redaction separately protects history and handoffs. `session.run(user_input=...)` bypasses `on_user_turn_completed`, so callback-path tests must drive `on_end_of_turn` or a live session.

## ADR-005 — Store a salted/keyed last-four digest, not the digits
**Decision:** Strip full SSNs from supplied seed data. Generate a per-record random salt and convert the synthetic last-four value to a keyed digest during seeding; persist the salt and digest, never the raw last four. Compare candidate digests with `hmac.compare_digest`. Require `HASH_PEPPER` in `.env`; `make seed` must fail with a clear configuration error if it is missing. CI/tests use a dedicated test pepper. Keep the pepper out of the repository. DOB remains plaintext in the synthetic database because it is required for matching, but must be masked in logs and redacted from retained conversation context.

**Reason:** A four-digit value has very low entropy; the per-record salt and secret pepper are essential protection against precomputed guessing. The supplied fixture contains synthetic full SSNs and last-four values, but neither full SSN nor plaintext last-four is needed in the application database.

## ADR-006 — No stored audio or raw transcripts; disable optional uploads where configurable
**Decision:** Do not persist audio or raw transcripts, and do not write raw conversation text to application logs, audit events, request summaries or generated files. Call `session.start(record=False)`; turn LiveKit Cloud project-level Agent observability OFF; set Deepgram STT and TTS `mip_opt_out=True` for model-improvement opt-out. Confirm the exact plugin option and current vendor wording during Step 0. Disable optional recording/observability uploads wherever the platform exposes a setting; document what was found, configured and unavailable in README.

**Reason:** These settings reduce optional recording, observability and model-improvement use where controls are exposed. They do not stop normal audio/text transit and processing by the room, STT, LLM and TTS vendors; do not claim otherwise.

## ADR-007 — Vendor data transit and production BAA boundary
**Decision:** Explicitly document that audio and text necessarily transit the selected room, STT, LLM and TTS vendors during a live call. Verify current vendor terms/configuration during implementation and document BAA availability and limitations. Production use with PHI requires appropriate BAAs and eligible configurations for every vendor handling PHI.

**Reason:** Disabling optional recording or observability uploads does not eliminate normal service processing/transit. This synthetic-data prototype is HIPAA-aware by design but is not a certified or production HIPAA-compliant deployment.

## ADR-008 — Custom structured logging and latency measurement
**Decision:** Use structured JSON application logs, append-only audit events, `call_id` correlation and custom latency measurements alongside LiveKit's available per-turn metrics. Measure EOU delay, LLM TTFT, TTS TTFB, tool duration and end-to-end turn latency. Do not add a Prometheus/Grafana/OpenTelemetry stack unless a demonstrated need emerges.

**Reason:** The assignment needs evidence of safe behavior and responsiveness, not another infrastructure stack. Avoid transcript content in metrics and logs.

## ADR-009 — Deterministic domain/service logic; no RAG or LangGraph hot path
**Decision:** Keep clinic facts in validated configuration/seed data and business flows in explicit domain/service logic. Do not add RAG, LangGraph or Langfuse to the live path.

**Reason:** The clinic dataset is small and structured. Retrieval or a second agent framework would not improve correctness and could widen the PHI exposure surface.

## ADR-010 — SQLite for the assessment; portable repository boundary
**Decision:** Use SQLite for the local synthetic-data prototype, accessed asynchronously or via `asyncio.to_thread`. Keep persistence behind repository interfaces and use transactions, constraints and parameterized SQL so a later PostgreSQL migration is practical.

**Reason:** SQLite keeps setup light within the assessment window. Booking integrity must still be enforced at the database layer, not by an application-only availability check.

## ADR-011 — Human transfer is simulated in the web demo
**Decision:** A staff-transfer request is recorded as a request/audit event and the web call ends with a clear spoken handoff message. Document SIP/warm-transfer as the production extension.

**Reason:** The assessment accepts a web call and does not provide a clinic phone/transfer endpoint. Do not pretend a real staff transfer occurred.

## ADR-012 — Email confirmation is simulated
**Decision:** Write a confirmation artifact to the local email outbox after a successful booking; do not integrate a live email provider.

**Reason:** The brief explicitly allows email simulation by saving a file or log. This avoids adding another vendor and credential surface.

## ADR-013 — Supplied synthetic appointment data is preserved
**Decision:** Keep Maria Garcia's supplied next appointment on Saturday, 2026-11-28, exactly as provided. Report it as stored if asked; do not silently move or reinterpret it. Document this source-data quirk.

**Reason:** The brief's fixture is the source of truth for the mock patient record, even though the timestamp conflicts with the clinic's weekend closure.

## ADR-014 — Name matching tolerance is constrained and tested
**Decision:** Normalize case, punctuation and common titles; allow at most one edit per name token only to accommodate likely speech-recognition variation. DOB and last-four digest must still match exactly for the same record. Any ambiguity fails closed and returns the generic verification failure.

**Reason:** Speech transcription can slightly distort names, but fuzzy matching must not weaken the independent DOB and last-four checks or reveal whether a record exists.

## ADR-015 — Phase 0 is a time-boxed feasibility gate
**Decision:** Before implementing domain features, prove the LiveKit audio loop, verification-turn redaction/`StopResponse` behavior, model/tool-call viability and latency instrumentation. Check LiveKit Inference availability and tool-calling behavior for `openai/gpt-5.4-mini`, `google/gemma-4-31b-it` and `google/gemini-3.5-flash-lite`; do not select deprecated GPT-4o, `gpt-5` or `gpt-5-mini` IDs. Measure free-credit headroom in the dashboard because pricing/credit consumption is not assumed. Inspect optional recording/observability settings. Keep a documented fallback if a spike fails within the timebox.

**Reason:** These are the highest-risk integration assumptions. Proving them early protects the remaining implementation time.

## ADR-016 — Keep assessment scope lean; no Docker deliverable
**Decision:** Keep voice/LLM/provider construction in `agent/config.py`, request/message persistence in `clinic/domain/requests.py`, and use Make targets for request/audit inspection. Do not add separate `agent/voice.py`, `agent/llm.py`, `clinic/domain/messages.py` or `api/routes_admin.py`. Fold architecture, privacy-data-flow, vendor/BAA and evaluation narrative into README sections. Do not add a Dockerfile or Docker CI job; container image plus PostgreSQL is a future production path only.

**Reason:** This removes duplicate abstractions and unrequired infrastructure without reducing requirement coverage.

## ADR-017 — Parser and volunteered-identifier regression coverage
**Decision:** Parser tests cover filler phrases (“one moment”), “last four”, spoken digit variants (“oh”, “double four”), numeric transcription forms, ordinal DOBs, spoken-year DOBs and rejection of more than four SSN digits. Identifier detection outside verification includes spoken-year DOB forms and routes the caller to verification before model disclosure.

**Reason:** Offline review found tokenization ambiguity around words such as “four” and a missed spoken-year DOB pattern. These are safety-relevant regression cases.


## ADR-018 — Keep assessment scope lean; no Docker deliverable
**Decision:** Keep voice/LLM/provider construction in `agent/config.py`, request/message persistence in `clinic/domain/requests.py`, and use Make targets for request/audit inspection. Do not add separate `agent/voice.py`, `agent/llm.py`, `clinic/domain/messages.py` or `api/routes_admin.py`. Fold architecture, privacy/data-flow, vendor/BAA and evaluation narrative into README sections. Do not add a Dockerfile or Docker CI job; container image plus PostgreSQL is a future production path only.

**Reason:** The assessment rewards correctness, safety and a clear demo, not file count or deployment polish. This removes duplicate abstractions and unrequired infrastructure without reducing requirement coverage.

## ADR-019 — Parser and volunteered-identifier regression coverage
**Decision:** Parser tests cover filler phrases (“one moment”), “last four”, spoken digit variants (“oh”, “double four”), numeric transcription forms, ordinal DOBs, spoken-year DOBs and rejection of more than four SSN digits. Identifier detection outside verification includes spoken-year DOBs and routes callers to verification before model disclosure.

**Reason:** Offline parser review found tokenization ambiguity around “four” and a missed spoken-year DOB pattern. These are safety-relevant regression cases.


## ADR-020 — Preemptive generation and time simulation defaults
**Decision:** Disable session preemptive generation by default and never enable it for verification. `VerificationAgent` is a model-free `NoModelAgent`; its `llm_node` never calls a model. All other agents are `GuardedAgent` instances whose `llm_node` redacts a copied context immediately before model egress. Redact inbound content before history/handoff retention as defense in depth. Verification state is server-side because a turn stopped with `StopResponse` is not appended to `session.history`. `ALLOW_TIME_SIMULATION=false` by default and may be changed only through trusted job metadata.

**Reason:** Preemptive generation can call the model before `on_user_turn_completed`; a later hook is too late to protect identifiers. Session history is not a reliable store for verification state.

## ADR-021 — Provider data controls and model candidates
**Decision:** Use `session.start(record=False)`, LiveKit Cloud project-level Agent observability OFF, and Deepgram STT/TTS `mip_opt_out=True` for model-improvement opt-out, after confirming exact current option semantics in Step 0. Test `openai/gpt-5.4-mini`, `google/gemma-4-31b-it` and `google/gemini-3.5-flash-lite`; do not assume credit headroom, region availability or tool-call reliability. Verify each in the dashboard and live call.

**Reason:** Code settings alone do not override project-level observability. Provider model availability, credit and performance need direct verification.

## ADR-022 — Require HASH_PEPPER and keep deployment scope lean
**Decision:** Fresh setup and `make seed` fail clearly if `HASH_PEPPER` is missing; CI uses a test-only pepper. Store per-record random salt plus keyed last-four digest, never raw last-four/full SSN. DOB remains in the synthetic database and is masked in logs. Do not add a Dockerfile or Docker CI build. Production direction is container image plus PostgreSQL.

**Reason:** Four-digit identifiers have tiny entropy; salt and a secret pepper are essential. Docker is outside the assessment's required scope.

## ADR-023 — Confirmed Step 0 provider and voice settings
**Decision:** Use LiveKit Agents 1.8.13, Deepgram STT/TTS, LiveKit Inference `openai/gpt-5.4-mini`, session preemptive generation disabled, `session.start(record=False)`, and LiveKit Cloud Agent observability OFF.

**Reason:** The live Step 0 Agent Console call confirmed the voice loop and demo-tool path with this stack. These settings establish the implementation baseline; vendor data transit and production BAA eligibility remain explicitly subject to production review.

## ADR-024 — Step 1 SQLite and verification representation
**Decision:** Store verification only as a per-record random salt and HMAC-SHA256 digest; keep DOB plaintext in the synthetic database but redact it at logging boundaries. Use synchronous SQLite transactions behind repository protocols, with WAL and foreign-key enforcement, and keep verification/domain logic independent of providers.

**Reason:** This matches the assessment's low-complexity persistence requirements while preserving a PostgreSQL-portable repository boundary. Verification compares name, DOB and keyed last-four digest against one patient record and locks after three failures.

## ADR-025 — Refill confirmation is a short-lived server-side operation
**Decision:** A refill preview stores a random confirmation-token digest and exact medication/pharmacy details in the call session for five minutes. The caller must explicitly confirm the read-back before the service atomically records the request and audit event and consumes the pending token. The database prevents duplicate open requests.

**Reason:** Tool arguments alone cannot authorize a refill write; confirmation and request state remain bound to the trusted call session, and retries cannot create duplicate requests.


## ADR-026 — Deterministic intake and non-throwing model-free turns (2026-11-24)

- The first-turn router, verification, booking, emergency, and after-hours flows are model-free state machines. This prevents the LLM from prematurely telling an unverified caller that a refill cannot be handled, and prevents verification/booking identifiers from reaching model context.
- `NoModelAgent.llm_node` returns an empty async stream rather than raising `StopResponse`; Agents 1.8.13 logged the intentional exception as an inference failure.
- DOB speech is buffered across partial STT turns. Parse failures do not consume one of the three actual verification attempts or discard already-captured fields.

## ADR-027 — Voice turn stability and event-loop hygiene (2026-11-24)

- Synchronous SQLite/service calls from async agent callbacks/tools run via `asyncio.to_thread`; each repository transaction owns its connection in the worker thread.
- LiveKit endpointing `min_delay` is set to 0.8 seconds to reduce STT transcripts arriving after the turn was committed. This adds some endpoint latency and must be evaluated against real call recordings.
- Deepgram Aura-2 Thalia is the default TTS voice based on the isolated voice check. Pipeline and clinic-tool latency logs contain numeric timing metadata only.

## ADR-028 — New-patient identity enrollment and callback privacy (2026-11-24)

- The assignment's new-patient intake does not include SSN last four. New patient rows are therefore created with `verification_ready=0` and cannot be verified until staff completes identity enrollment; no fabricated last-four value is stored.
- After-hours callbacks store caller name/number in explicit callback fields and a normalized non-clinical reason category. They are not linked to a patient record and cannot access patient data.
- Booking patient/appointment/request/audit creation and slot consumption occur in one SQLite transaction. Confirmation email is a local JSON outbox artifact, not a real email send.

## ADR-029 — Presidio and split-DOB verification safeguards (2026-11-24)

- Use Microsoft Presidio `en_core_web_sm` once per process as a defense-in-depth redaction layer; deterministic parsers and masks remain authoritative.
- Preserve verification fields as month, day and year components across turns. Ignore wait/filler/correction text, and never convert it into a name or consume a failed verification attempt.
- A deterministic mask remains the fail-closed fallback if Presidio initialization or analysis fails.

## ADR-030 — LLM-led conversation, code-held identity secrets (2026-11-25; supersedes the model-free flows of ADR-029 and earlier)

- **Problem.** Six of seven agents were model-free regex state machines speaking fixed lines, so calls sounded like an IVR. A live call failed verification because the DOB parser read a split year ("19 85") as the day, and then read the year "1985" as the SSN last four.
- **Decision.** One LLM receptionist (open hours) and one LLM message-taker (after hours) run the conversation from a single prompt in `src/agent/prompts/`. Code keeps every security decision: emergency detection before the model, DOB/SSN capture and removal from the text (`agent/capture.py`), identity matching, attempt limits, office hours, slot validation, atomic booking, and a confirmation gate that only the caller's own "yes" can open.
- **Brief alignment.** The brief requires matching in code and no SSN data to the LLM; it does not require scripted verification, and it asks for short, natural answers.
- **Screening point.** `ClinicAgent.llm_node` screens every caller message once (cached by id) because LiveKit's typed-input path skips `on_user_turn_completed`.
- **Patient tools are always listed**; access is enforced by the backend session check. Tools added mid-response are invisible to the model, which then picked the wrong tool (it read an open slot as the caller's appointment).
- **Presidio removed.** It masked names and appointment dates the conversation needs, and on the log path its own warnings re-entered the masker (one line → 1,469 records in 15 s), starving the audio loop. Deterministic masking covers the brief's identifiers.
- **Trade-off.** Names and new-patient contact details reach the LLM; production needs a BAA-covered LLM route. The DOB/SSN capture depends on explicit cues ("date of birth", "last four"), which the prompt requires the agent to use when asking.

## ADR-031 — Evaluation, output check, CI security, content-free tracing (2026-11-25)

- **Evaluation over dashboards.** `tests/evals` runs 15 scripted callers through the real LLM and asserts on spoken output, tool use and database records. Marked `llm` and deselected by default because it spends credit. It replaces the earlier print-only replay script.
- **Output check in code.** `speech_guard` checks each sentence before speech (SSN/DOB read-back, refill promises, dosing advice). Chosen over NeMo Guardrails, Guardrails AI and Llama Guard, which add a model call per turn (latency on a voice line) and duplicate checks the backend already enforces.
- **Tracing.** LiveKit's own OpenTelemetry spans are exported to Langfuse over OTLP with `allow_pii=False`; no Langfuse SDK. LiveKit's default is `allow_pii=True`, so the flag is explicit and covered by a test. Langfuse Cloud rather than self-hosting (four extra services). LangSmith not used: it overlaps, and its value depends on seeing content.
- **CI security.** Ruff bandit rules (this removed two production `assert` guards that `python -O` would strip), gitleaks over full history, pip-audit over the lockfile.
- **Logs.** One file per day, kept 7 days, rather than rename-based rotation, which fails on Windows when another call process holds the file open.
- **Azure.** Documented as the production path (Azure OpenAI, Prompt Shields, Azure Monitor, Key Vault); not built, because there is no Azure account for the demo.

## ADR-032 — Fixes from the second round of real voice tests (2026-11-25)

- **Insurance member ID.** Speech-to-text delivered "48291" as "48" then "$2.91" (Deepgram smart formatting) and as spaced digits; the single free-text `insurance` field was validated with a regex needing a contiguous 3+ character token, so every attempt was rejected. Now `insurance_provider`, `member_id` and `self_pay` are separate tool fields; `normalize_member_id` rebuilds IDs from spoken or spaced digits and formatting artifacts; unclear IDs are rejected so the agent asks again; the read-back spells the ID for confirmation. Smart formatting stays on because it helps emails and dates.
- **Emergency detection.** Exact phrases missed "pain in my chest" and "difficulty to breathe" (the LLM still said 911, but the scripted path and call end did not fire). Replaced with patterns allowing word order and a few words between, keeping negation handling.
- **Test isolation.** The service wrote confirmation emails to a hard-coded relative `data/outbox`, so tests polluted the demo outbox; the outbox directory is now injected.
- **Simulated clock** advances from `DEMO_NOW` in real time; a frozen clock gave every audit event in a call the same timestamp.
- **Repository.** Internal working notes and the early feasibility spike are kept out of the repository; SQLite `-wal`/`-shm` files are gitignored because they hold recent database contents.
- **Operator commands.** `clinic seed`, `show-requests`, `show-audit` and `reset-demo` are developer CLI commands only; no agent tool or HTTP endpoint can reset or delete clinic data, and tests assert this.
