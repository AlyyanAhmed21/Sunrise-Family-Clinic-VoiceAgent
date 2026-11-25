# Sunrise Family Clinic Voice Agent

A real-time voice receptionist for a fictional family practice, Sunrise Family Clinic
(120 Main Street, Springfield; open Monday–Friday, 9 AM–5 PM Eastern; Dr. Patel, Family
Medicine, and Dr. Lee, Internal Medicine). Callers speak to it through a LiveKit web call.
It verifies existing patients, handles refills, appointment, lab-status and billing
questions, books first visits, takes after-hours messages, and hands off to staff.

> **Assessment prototype.** All patient data is synthetic. The design follows HIPAA
> principles, but this is not a certified, HIPAA-compliant or production system. Do not use
> it with real patient information.

## Contents

- [What it does](#what-it-does)
- [How it works](#how-it-works)
- [Tools used and why](#tools-used-and-why)
- [Setup](#setup)
- [Clinic hours and time simulation](#clinic-hours-and-time-simulation)
- [Running the demo scenarios](#running-the-demo-scenarios)
- [How identity verification works](#how-identity-verification-works)
- [Appointment booking flow](#appointment-booking-flow)
- [How after-hours calls are handled](#how-after-hours-calls-are-handled)
- [Guardrails and HIPAA measures](#guardrails-and-hipaa-measures)
- [Logs, records and tracing](#logs-records-and-tracing)
- [Testing](#testing)
- [Limitations and production considerations](#limitations-and-production-considerations)
- [Project layout](#project-layout)

## What it does

| Caller need | Behaviour |
|---|---|
| Identity verification | Full name, date of birth and last four SSN digits must all match one patient record. Same generic failure whatever was wrong; locked after three failures. |
| Prescription refill | Reads back the medication and pharmacy, saves the request only after the caller confirms; with no refills left, says it goes to the doctor for approval. |
| Next appointment, lab status, balance | Answers for the verified caller only. Lab results are reported as a status, never interpreted. |
| First-visit booking | Collects the minimum details, offers two or three real open slots, reads everything back (spelling the email), books atomically and gives arrival instructions. |
| After hours | Says the office is closed and gives the hours and the 911 line, shares no patient information, and takes a callback message. |
| Emergencies | Chest pain, breathing difficulty, suicidal statements and similar are detected in code before the model runs; the caller is told to call 911 and the call ends. |
| Staff handoff, callbacks, doctor messages | Recorded as requests; the web demo has no live phone transfer. |

## How it works

```
Caller (browser) ── LiveKit room ── Agent worker (this repo)
                                     │
   Deepgram Nova-3 (speech-to-text) ─┤
                                     ▼
                         ClinicAgent screening (code)
                         - emergency check → scripted 911 line, call ends
                         - date of birth / SSN digits captured, removed from text
                                     ▼
                LLM via LiveKit Inference (conversation) ──► tools
                                     │                         │
                         speech check (code)          ClinicService (code)
                                     ▼                 verification, office hours,
   Deepgram Aura-2 (text-to-speech) ◄┘                 authorization, booking, audit
                                                               │
                                                        SQLite (synthetic data)
```

The LLM runs the conversation; application code decides what is allowed.

| The LLM | Application code |
|---|---|
| Understands what the caller wants, asks only for missing details, handles corrections and follow-up questions, explains results in plain speech | Detects emergencies, keeps the DOB and SSN digits out of the model's view, matches identity, enforces office hours, attempt limits and authorization, validates slots, books atomically, and saves nothing the caller has not confirmed |

- **One agent per call mode.** During office hours a `ReceptionistAgent` handles every request
  (prompt: `src/agent/prompts/receptionist.md`). After hours an `AfterHoursAgent` can only take
  a message. Emergency and staff-handoff agents speak one fixed line and end the call.
- **Screening before the model.** Every caller message, spoken or typed, passes through
  `ClinicAgent` (`src/agent/guard.py`) before any model call. A date of birth or SSN digits
  are parsed in code (`src/agent/capture.py`), stored server-side, and replaced with
  `[redacted]` plus a note such as "date of birth received".
- **Tools without identifiers.** No tool accepts a patient ID, date of birth or SSN. The
  service resolves the patient from the verified server-side call session, so the model
  cannot request someone else's record.
- **Confirmation gate.** Refills, bookings, callbacks and messages are two-step tools: the
  first call returns a read-back; the save succeeds only if the caller's next turn was a clear
  "yes" to that read-back.
- **Speech check.** Each sentence the model produces is checked before it is spoken
  (`src/agent/speech_guard.py`); SSN or DOB read-backs, refill promises and dosing advice are
  replaced with a safe line.
- **Fixed lines.** Only the lines the brief or safety require are scripted
  (`src/agent/phrases.py`): recording notice, after-hours notice, emergency direction,
  verification failure, arrival instructions, after-hours closing and staff handoff.

## Tools used and why

| Layer | Choice | Why |
|---|---|---|
| Voice orchestration | LiveKit Agents 1.8 (Python) | Streaming audio, turn detection, interruptions and tool calling in one framework; web calls through the Agent Console |
| Speech-to-text | Deepgram Nova-3 | Fast streaming recognition with key-term boosting for medication names |
| Text-to-speech | Deepgram Aura-2 (`aura-2-thalia-en`) | Low time to first audio; same vendor as STT |
| LLM | `openai/gpt-5.4-mini` via LiveKit Inference, low reasoning effort, automatic fallback model | Reliable tool calling with a short time to first word; no separate orchestration framework |
| Turn detection | LiveKit VAD and TurnDetector | End-of-turn detection tuned for conversation |
| Backend | Python 3.12, Pydantic v2, SQLite | Typed, deterministic domain rules; atomic transactions; SQL portable to PostgreSQL |
| Privacy | Deterministic parsers and maskers | Fast enough to run on every turn and every log line |
| Observability | Masked daily logs, a report command, optional Langfuse tracing | Latency and safety events per call without storing conversation content |
| Quality | pytest, an LLM evaluation suite, Ruff (with security rules), mypy, gitleaks, pip-audit | Deterministic tests, behavioural checks against the real model, and CI security checks |

No LangGraph or retrieval is used: the clinic's facts are small, structured records, and
querying them directly is simpler and safer than retrieval over patient data.

## Setup

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 and all dependencies)
- A LiveKit Cloud project (URL, API key and secret) and a Deepgram API key
- Optional: a Langfuse Cloud project for tracing

Commands below are for Windows PowerShell, run from the repository root. They are the same on
Linux/macOS except where shown. If `uv` is not on your PATH, use `.\.venv\Scripts\uv.exe`
once the virtual environment exists.

### 1. Install

```powershell
uv sync --extra dev
```

### 2. Configure

```powershell
Copy-Item .env.example .env      # Linux/macOS: cp .env.example .env
```

Fill in `.env`:

| Variable | Required | Purpose |
|---|---|---|
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | Yes | LiveKit Cloud project (voice session and LLM inference) |
| `DEEPGRAM_API_KEY` | Yes | Speech-to-text and text-to-speech |
| `HASH_PEPPER` | Yes | Secret used to hash SSN last-four digits; generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `LLM_MODEL`, `LLM_FALLBACK_MODELS`, `LLM_REASONING_EFFORT` | No | Model choice (defaults in `.env.example`) |
| `DEEPGRAM_STT_MODEL`, `DEEPGRAM_TTS_MODEL`, `PROVIDER_TIMEOUT_SECONDS` | No | Speech models and provider timeout |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | No | Enables tracing when both keys are set |
| `ALLOW_TIME_SIMULATION`, `DEMO_NOW` | No | Development-only clinic clock override (see below) |
| `LOG_LEVEL` | No | Default `INFO` |

`.env` is gitignored; never commit it.

### 3. Prepare the database

```powershell
uv run clinic seed
```

This creates `data/clinic.sqlite3` with the synthetic patients and appointment slots. The
worker also does this automatically at the start of each call.

### 4. Start the voice worker

```powershell
uv run --env-file .env python -m agent.main dev
```

Open your LiveKit project's Agent Console (or the Agents Playground), start a session and
speak. The worker log should show `event=voice_session_started … clinic_mode=open` or
`clinic_mode=closed`.

### Everyday commands

The `Makefile` wraps these for Linux/macOS (it needs GNU Make, which Windows does not ship).
Use `uv run`, which runs inside the project's environment; a plain `python -m …` uses the
system Python, where the project is not installed.

| Task | Command |
|---|---|
| Start the worker | `uv run --env-file .env python -m agent.main dev` |
| Show saved requests / audit events | `uv run clinic show-requests` / `uv run clinic show-audit` |
| Reset demo data | `uv run clinic reset-demo` |
| Latency and safety report | `uv run clinic-report` (today), `--all` (7 days), `--last` (last call) |
| Tests | `uv run pytest -q` |
| LLM evaluation suite (uses credit) | `uv run --env-file .env pytest -m llm tests/evals -s` |
| Lint, format, types | `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src/clinic src/agent` |

## Clinic hours and time simulation

Open/closed is decided once at the start of each call from the clinic clock in
`America/New_York`: Monday–Friday from 9:00 AM until 5:00 PM (5:00 PM exactly is closed),
closed on weekends. The mode is stored in the server-side call session, and the service
checks office hours again on every patient-data request.

**Normal mode (default).** The real current time is used:

```
ALLOW_TIME_SIMULATION=false
```

**Simulated mode (development and demos).** Set the flag and one `DEMO_NOW` value in `.env`,
then restart the worker. The simulated clock starts at `DEMO_NOW` and advances in real time;
the timestamp must include a timezone offset.

```
ALLOW_TIME_SIMULATION=true
DEMO_NOW=2026-11-24T10:00:00-05:00
```

| Demo situation | `DEMO_NOW` | Result |
|---|---|---|
| Clinic open (Tuesday 10:00 AM ET) | `2026-11-24T10:00:00-05:00` | Receptionist: full patient workflows |
| Clinic closed (Tuesday 7:00 PM ET) | `2026-11-24T19:00:00-05:00` | After-hours message taking |

The worker log confirms the result, e.g. `clinic_mode=closed simulated_time=True
clinic_time=Tue Nov 24 19:00 EST`. When `ALLOW_TIME_SIMULATION` is `false`, any `DEMO_NOW`
is ignored. A trusted dispatcher can also pass `{"demo_mode": true, "demo_now": "…"}` as
LiveKit job metadata (it takes precedence over `DEMO_NOW` and is also ignored unless the flag
is on). Callers and the model have no way to change the clinic clock: no tool accepts a time,
and the setting is read only when a call starts.

## Running the demo scenarios

The seven scenarios required by the brief, with suggested caller lines and expected
behaviour, are in [docs/demo-script.md](docs/demo-script.md):

1. Successful verification followed by a refill request
2. Failed verification
3. New patient booking a first appointment
4. After-hours call with a recorded message (simulated time)
5. Request for medical advice
6. Emergency
7. Request for another person's information

Before recording, run `uv run clinic reset-demo` to clear earlier requests, audit events,
bookings and confirmation emails (seed patients and their fixture appointments are kept).
Synthetic patients for the scenarios are in `data/seed/patients.json`; for example Sarah
Johnson, born March 14, 1985, SSN last four 3344.

## How identity verification works

Existing patients must give their **full name, date of birth and the last four digits of
their SSN** before anything about them is shared or changed.

1. **Collecting the details.** The caller can give them in any order, in one sentence or
   across several turns, and correct any of them. The agent asks only for what is missing.
2. **Keeping secrets out of the model.** Before the LLM sees a caller's words, code in
   `src/agent/capture.py` recognises a date of birth or SSN digits (spoken or written:
   "March fourteenth nineteen eighty-five", "3/14/1985", "three three four four"), stores
   them in server-side call state, and replaces them in the text with `[redacted]` and a note
   such as "date of birth received". The LLM never sees the values. A date without a year, or
   an ambiguous two-digit year, is not guessed; more than four SSN digits are discarded and
   the agent asks for only the last four.
3. **Matching in the backend.** The LLM calls `verify_identity` with the caller's name only.
   The backend (`clinic.domain.verification`) combines it with the stored DOB and last four
   and requires all three to match **the same** patient record. Names tolerate one character
   per word of speech-recognition error; the DOB must match exactly; the last four is compared
   against a salted, peppered hash with a constant-time comparison.
4. **Failures.** Every failure gets the same reply, "I'm sorry, I couldn't verify those
   details.", and the tool output is identical whichever detail was wrong. After **three**
   failed attempts the call's session is locked in the database, further attempts are
   refused, and the agent offers a transfer to clinic staff.
5. **After verification.** The verified patient is stored in the server-side session. Patient
   tools (appointment, lab status, balance, refill, doctor message) take no patient
   identifier; the backend serves only the session's patient and refuses everything before
   verification.

Patient requests after verification:

- **Refill:** the agent names the medication; the tool returns the medication and pharmacy on
  file to read back; the request is saved only after the caller confirms. With no refills
  left, the caller is told it goes to the doctor for approval; approval is never promised.
- **Next appointment:** read from the record; if there is none, the agent offers to book one
  or arrange a staff callback.
- **Lab results:** status only (e.g. "Pending"), never results or interpretation.
- **Billing:** the balance due.

## Appointment booking flow

1. **Confirm a first visit.** The agent asks "Is this your first visit with Sunrise Family
   Clinic?"
2. **Collect the minimum details,** one or two at a time: full name, date of birth, phone,
   email, insurance provider and member ID (or an explicit self-pay), the reason in a few
   words (no symptoms or history), and optional preferred doctor, days and times. Spoken
   emails ("daniel dot carter at gmail dot com") and member IDs ("4 8 2 9 1", "48 291") are
   normalized in code; an unclear member ID is rejected so the agent asks again.
3. **Offer real slots.** `find_open_slots` returns up to three open slots matching the
   preferences, or the nearest real alternatives if none match. The prompt lists today's date
   and the next 14 days in Eastern Time so "next Tuesday" is resolved correctly. Only slots
   returned in the call can be booked.
4. **Read back and confirm.** The tool produces the read-back: name, date and time, doctor,
   reason, insurance with the member ID digit by digit, and the email spelled out letter by
   letter. Nothing is saved until the caller says yes to that read-back.
5. **Book atomically.** One SQLite transaction creates the new patient record, the
   appointment, the booking request and the audit event, and marks the slot as taken. A
   simulated confirmation email is written to `data/outbox/<appointment_id>.json`.
6. **Instructions and close.** The agent confirms the booking, says "Please arrive 15 minutes
   early and bring a photo ID and your insurance card. You'll receive a confirmation by
   email.", asks if there is anything else, and ends the call politely.

Verified existing patients book through the same flow, skipping the details already on file
(an email is asked for only if none is on file). New patients are not asked for SSN digits, so
their records cannot be used for verification until staff complete identity enrollment.

## How after-hours calls are handled

1. At the start of every call the clinic clock (`America/New_York`) is checked: open Monday to
   Friday from 9:00 AM until 5:00 PM, closed at 5:00 PM exactly and on weekends. A closed call
   is handled by the `AfterHoursAgent`.
2. It opens with the recording notice, says the office is closed, gives the hours, and tells
   the caller to hang up and call 911 if it is an emergency.
3. **No patient information is shared, even if the caller offers to verify.** The after-hours
   agent has no patient tools, and the backend independently refuses patient data outside
   office hours, even for a session that was verified earlier.
4. It takes a message: full name, callback number and the reason in a few words (no health
   details). It reads them back and saves the message only after the caller confirms. The
   request is stored without a patient link (`UNVERIFIED`), with the reason reduced to a
   category.
5. It closes with: "Thank you, [first name]. Your message has been recorded, and our team will
   get back to you on the next business day. If this is an emergency, please hang up and call
   911. Have a good night." and ends the call.

For demos, the clinic clock can be simulated; see
[Clinic hours and time simulation](#clinic-hours-and-time-simulation).

## Guardrails and HIPAA measures

Two principles run through all of these: **the LLM never holds authority** (identity matching,
authorization, office hours, attempt limits and every save are decided in code), and **code
checks what goes into and out of the model** (screening before each model call, a speech
check before each spoken sentence).

### Guardrails

| Guardrail | What happens | How it is enforced | Tested by |
|---|---|---|---|
| Emergencies | The caller is told to hang up and call 911 or go to the nearest emergency room; the normal flow stops and the call ends | Code (`clinic/security/emergency.py`) checks every caller message before the model runs, in both open and closed mode, for chest pain, breathing difficulty, stroke signs, unconsciousness, severe bleeding, overdose, self-harm and similar; a scripted line is spoken and an `emergency_redirected` audit event is written | `tests/security/test_emergency.py`, `tests/agent/test_guard.py`, evals `t6`, `t6b` |
| No medical advice | Never diagnoses, recommends medicines, changes doses or interprets symptoms; offers a message to the doctor (verified callers) or a staff callback | Receptionist prompt; the speech check (`agent/speech_guard.py`) replaces dosing advice before it is spoken; lab tools return a status, never results | `tests/agent/test_speech_guard.py`, evals `t5`, `dose_change_after_verification`, `roleplay_jailbreak` |
| No third-party access | Refuses to share or confirm anything about another person, including whether they are a patient; the patient must call themselves | Verification covers the caller only; tools take no patient identifier, so the backend can only serve the verified caller's own record; prompt rules | Evals `t7`, `spouse_balance`, `other_patient_after_verification` |
| No made-up information | Says it doesn't have the information and offers a staff callback | Tools return only stored data; a slot can be booked only if `find_open_slots` returned it in this call | `tests/agent/test_tools.py` (`unknown_slot`) |
| Stay on topic, resist prompt injection | Declines unrelated questions and instructions to ignore its rules | Prompt; no tool can list patients or read another record, so an injected instruction has nothing to exfiltrate | Evals `prompt_injection`, `roleplay_jailbreak` |
| Human handoff | Offers a transfer when the caller asks for a person, is upset or confused, or verification is locked | `transfer_to_staff` records the request and plays the handoff line; on a web call there is no live transfer | `tests/agent/test_tools.py` |
| Confirm before saving | Refills, bookings, callbacks and messages are read back first | Two-step tools: the save succeeds only if the caller's next turn was a clear "yes" to that exact read-back; the model cannot confirm on the caller's behalf | `tests/agent/test_tools.py` |
| No clinic reset from a call | — | The demo reset is a developer command (`clinic reset-demo`) only; no agent tool or HTTP endpoint can reset or delete data | `tests/agent/test_office_hours.py` |

### HIPAA measures

| Principle | What this project does | Where |
|---|---|---|
| Verify before disclosure | No patient information is shared or changed until name, DOB and SSN last four match one record; every patient-data request is checked against the verified server-side session | `src/clinic/service.py`, `src/clinic/domain/verification.py` |
| Minimum necessary | Tools return only the requested fact (one appointment, a lab status, a balance); medication names are read only if the caller can't remember one; new-patient intake collects only the brief's fields; stored request summaries are categories ("Scheduling callback requested"), not the caller's words | `src/agent/tools/`, `src/clinic/service.py` |
| SSN protection | Only the last four digits are collected; a full SSN is discarded on capture; SSN digits are never sent to the LLM, never spoken back (speech check), never logged, and stored only as a salted, peppered hash | `src/agent/capture.py`, `src/agent/speech_guard.py`, `src/clinic/security/hashing.py` |
| Mask data in logs and transcripts | No audio or transcripts are stored. Every log line passes a deterministic masker for DOB, SSN, last four, phone, email and member ID (replaced with markers such as `[REDACTED_DOB]`); LiveKit's raw-transcript log fields are dropped; optional Langfuse traces have all conversation content stripped before export | `src/clinic/security/masking.py`, `src/clinic/logging.py`, `src/agent/tracing.py` |
| Matching in code, not the LLM | Identity matching is deterministic backend code; the patient database is never placed in a prompt, and the model never sees the DOB or SSN digits | `src/clinic/domain/verification.py`, `src/agent/capture.py` |
| Secure secrets | API keys and `HASH_PEPPER` are read from `.env` (gitignored); `.env.example` holds placeholders; CI runs gitleaks over the git history | `.env.example`, `.gitignore`, `.github/workflows/ci.yml` |
| Audit log | Every verification attempt, record lookup, refill, booking, callback, doctor message, transfer and emergency redirect is recorded with call id, record id, action, outcome and timestamp, without conversation content or which verification field failed | `audit_events` table, `src/clinic/service.py`; view with `uv run clinic show-audit` |
| Business Associate Agreements | Each vendor's BAA position and the production changes are listed below; no BAA is in place for this prototype | [Vendors and BAAs](#vendors-and-baas) |
| Call recording notice | Every call opens with "Thank you for calling Sunrise Family Clinic. This call may be recorded for quality purposes." | `src/agent/phrases.py` |
| Synthetic data only | Only the brief's fictional patients and slots are used, with the full SSN removed from the seed data | `data/seed/` |

Code and test references for each principle are in [docs/hipaa-matrix.md](docs/hipaa-matrix.md),
and every requirement of the brief is traced in
[docs/assignment-checklist.md](docs/assignment-checklist.md).

## Logs, records and tracing

| What | Where | How to view |
|---|---|---|
| Requests (refills, bookings, callbacks, messages, transfers) | `patient_requests` in `data/clinic.sqlite3` | `uv run clinic show-requests` (callback contact details masked) |
| Audit events | `audit_events` | `uv run clinic show-audit` |
| Simulated confirmation emails | `data/outbox/*.json` | Open the files |
| Call timings and safety events | `logs/agent-YYYY-MM-DD.log` (masked, gitignored, kept 7 days) | `uv run clinic-report` |
| Per-turn traces (optional) | Your Langfuse project | Langfuse UI, sessions grouped by call id |

`clinic-report` prints, per call, the median, 95th percentile and maximum of each timing:
end-of-turn delay, LLM time to first token, TTS time to first audio, TTS real-time factor
and tool latency. It also counts failed verifications, refused tool calls, blocked speech,
emergency redirects, interrupted agent turns and LiveKit's audio-underrun warnings.

**Langfuse tracing (optional).** LiveKit Agents emits OpenTelemetry spans for every turn.
`src/agent/tracing.py` exports them to Langfuse with LiveKit's `allow_pii=False`, which removes
transcripts, prompts, tool arguments and tool results in-process before export. Langfuse
receives timings, ids, model names, tool names, token counts and errors. To enable it, set
`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_HOST` (EU
`https://cloud.langfuse.com` or US `https://us.cloud.langfuse.com`; `LANGFUSE_BASE_URL` is
also accepted) and restart the worker. `tests/agent/test_tracing.py` checks that no content
survives export.

## Testing

```powershell
uv run pytest -q                                          # deterministic tests (no credit)
uv run --env-file .env pytest -m llm tests/evals -s       # LLM evaluation suite (uses credit)
uv run ruff check .
uv run ruff format --check .
uv run mypy src/clinic src/agent
```

- **Deterministic tests** cover spoken date, digit, email and member-ID parsing; DOB/SSN
  capture and redaction; emergency detection; the confirmation gate; verification attempts
  and lockout; authorization and office hours; refills; slot search and atomic booking;
  callbacks; the speech check; logging and masking; tracing without content; the report;
  and the demo CLI.
- **The evaluation suite** (`tests/evals/test_scenarios.py`) plays 15 scripted callers
  through the real agents and model in text mode, each against a fresh database: the seven
  demo scenarios and adversarial cases (prompt injection, full-SSN overshare, a spouse asking
  for a balance, dose-change and role-play requests, another patient's balance, after-hours
  requests for patient data). Each case checks what the agent said, which tools it used and
  the records written. It is excluded from `pytest` and CI because it uses LiveKit Inference
  credit.
- **CI** (`.github/workflows/ci.yml`) runs Ruff with bandit security rules, mypy, the
  deterministic tests, gitleaks over the git history and `pip-audit` over the locked
  dependencies.

Text-mode evaluation does not cover speech recognition, audio quality or latency; those were
checked in manual voice calls ([docs/voice-test-plan.md](docs/voice-test-plan.md)).

## Limitations and production considerations

### Known limitations

- Caller names, and a new patient's phone, email and insurance details, reach the LLM
  because the conversation needs them; only the date of birth and SSN digits are withheld.
- Medical-advice, third-party and prompt-injection refusals depend on the model following its
  prompt. Backend authorization and the speech check limit the impact, but a pattern-based
  speech check cannot catch every phrasing.
- There is no live staff transfer or real email delivery.
- New patients cannot verify on later calls until staff complete identity enrollment.
- On the test machine, LiveKit reported occasional audio-underrun warnings while speech
  generation itself was faster than real time; the worker connected through a distant LiveKit
  region, so network jitter is the likely cause. It was not tested from a US-hosted worker.
- SQLite and a JSON email outbox are prototype storage.
- The supplied Maria Garcia record has an appointment on Saturday, November 28, 2026, although
  the clinic is closed on weekends; it is reported as stored.

### Vendors and BAAs

No Business Associate Agreement is in place for this prototype. Before any real PHI is
processed, a BAA must be executed with every vendor that receives it, and the exact products
and configuration confirmed as eligible.

| Vendor | Role | Position | Production action |
|---|---|---|---|
| LiveKit Cloud and LiveKit Inference | Media transport, turn detection, LLM routing | LiveKit offers BAAs for eligible Cloud plans and lists eligible services and models | Execute a LiveKit BAA for the project and confirm the chosen services and model are covered |
| Deepgram | Speech-to-text and text-to-speech (called directly, not through LiveKit Inference) | BAAs available for Enterprise customers | Execute a separate Deepgram BAA; confirm retention settings (`mip_opt_out=True` is a model-improvement opt-out, not zero retention) |
| OpenAI model via LiveKit Inference | LLM | Reached through LiveKit Inference, not OpenAI directly | Keep it on a BAA-covered route; calling OpenAI directly would need OpenAI's own BAA |
| Langfuse Cloud (optional) | Tracing metadata only | Receives no conversation content in this design; BAA terms not verified | Self-host in the covered environment or obtain a BAA before tracing production calls |

A BAA alone does not make a system compliant. Production also needs a security risk
analysis, access controls, encrypted managed storage (e.g. PostgreSQL), retention and deletion
policies, monitoring, incident response, backups, a real staff-transfer path and legal review.

**Microsoft/Azure path.** The same architecture can run on Microsoft services covered by its
BAA: Azure OpenAI in place of LiveKit Inference (only the `llm=` construction in
`src/agent/config.py` changes), Azure AI Content Safety Prompt Shields alongside the existing
screening and speech check, the same content-free OpenTelemetry spans exported to Azure
Monitor, Azure Key Vault for secrets and Azure Database for PostgreSQL. This project has no
Azure dependency and was not tested on Azure.

References (checked 2026-11-24): [LiveKit HIPAA](https://livekit.com/legal/hipaa),
[LiveKit BAA process](https://docs.livekit.io/deploy/admin/hipaa/),
[Deepgram pricing and BAA](https://deepgram.com/pricing),
[Deepgram terms](https://deepgram.com/terms),
[OpenAI BAA process](https://help.openai.com/en/articles/8660679-getting-a-business-associate-agreement-for-the-openai-api).

## Project layout

```
src/agent/          LiveKit voice agents
  agents/           receptionist, after-hours, scripted (emergency, handoff)
  prompts/          system prompts (Markdown)
  tools/            function tools: patient, booking, staff/callback
  capture.py        DOB / SSN capture before the model
  guard.py          screening, speech check and LLM timing around every model call
  speech_guard.py   sentence-level output check
  tracing.py        optional Langfuse export without content
  report.py         clinic-report command
  simulation.py     text-mode harness used by the evaluation suite
src/clinic/         backend: service, office hours, verification, persistence,
                    security (parsing, masking, hashing, emergency), CLI, health API
tests/              unit, security, agent and evaluation tests
data/seed/          synthetic patients and slots
docs/               assignment checklist, HIPAA matrix, decisions, demo script, voice test plan
```

Design decisions and their reasons are recorded in [docs/DECISIONS.md](docs/DECISIONS.md).
