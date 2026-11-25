# Assignment checklist

Each requirement from the assessment brief, where it is implemented, and the evidence. "Live
call" means it was exercised in a manual voice call through the LiveKit Agent Console;
"eval" means a case in `tests/evals/test_scenarios.py` (real LLM, text mode).

Status: **Complete**, **Complete (prompt-led)** where the behaviour depends on the model
following its instructions, with code limiting the impact if it does not, or **Manual**
where the deliverable is outside the code.

## 1. Real-time voice

| Requirement | Implementation | Evidence | Status |
|---|---|---|---|
| Speech-to-text → LLM → text-to-speech, by web call | LiveKit Agents session with Deepgram Nova-3, LiveKit Inference LLM, Deepgram Aura-2 (`src/agent/config.py`, `src/agent/main.py`) | Live calls | Complete |
| Not a text chatbot | Product path is the voice worker; text mode is used only by the eval suite | Live calls | Complete |

## 2. Opening the call

| Requirement | Implementation | Evidence | Status |
|---|---|---|---|
| Greet and say the call may be recorded | Fixed opening line spoken on entry (`src/agent/phrases.py`, `on_enter` in both agents) | `tests/agent/test_guard.py`, `tests/agent/test_prompts.py`, live calls | Complete |
| Check current time against office hours (Mon–Fri 9–5 ET) | `clinic.domain.hours.is_open` on `America/New_York` time at call start; mode stored in the call session; re-checked by the service on every patient-data request | `tests/unit/test_hours.py`, `tests/agent/test_office_hours.py`, `tests/unit/test_service.py` | Complete |
| Closed → after-hours flow | `agent_for` selects `AfterHoursAgent` for a closed call | `tests/agent/test_office_hours.py`, eval `t4_after_hours`, live call | Complete |

## 3. Identity verification

| Requirement | Implementation | Evidence | Status |
|---|---|---|---|
| Ask for full name, DOB, last 4 of SSN | Receptionist prompt; DOB and digits captured in code (`src/agent/capture.py`) | `tests/agent/test_capture.py`, evals `t1`, `t2`, live calls | Complete |
| Never ask for, repeat or say the full SSN | Full SSNs discarded on capture; speech check blocks SSN/DOB read-back (`src/agent/speech_guard.py`) | `tests/agent/test_capture.py`, `tests/agent/test_speech_guard.py`, eval `full_ssn_overshare` | Complete |
| All three must match the same record | `clinic.domain.verification.verify_candidate` | `tests/unit/test_verification.py` | Complete |
| No patient information until verified | Service resolves the patient only from a verified server-side session | `tests/unit/test_authorization.py`, `tests/unit/test_service.py`, `tests/agent/test_tools.py` | Complete |
| Never reveal which detail was wrong | One generic failure; identical tool output for any wrong field | `tests/agent/test_tools.py` (identical outputs), eval `t2` | Complete |
| Max 3 failed attempts, then end verification and offer transfer (or callback when closed) | Session locks at 3 failures in the backend; prompt offers transfer; verification is unavailable after hours, where a callback is taken | `tests/agent/test_tools.py`, eval `t2`, live call | Complete |

## 4. Requests after verification

| Requirement | Implementation | Evidence | Status |
|---|---|---|---|
| Refill: confirm medication and pharmacy, create request | Two-step `request_refill` with confirmation gate | `tests/agent/test_tools.py`, eval `t1`, live call | Complete |
| No refills left → sent to doctor for approval; never promise approval | `needs_doctor_approval` outcome; speech check blocks "approved" claims | `tests/agent/test_tools.py`, `tests/agent/test_speech_guard.py` | Complete |
| Next appointment; if none, offer booking or staff callback | `get_next_appointment` returns `none` with a hint; `request_callback` and booking tools available | `tests/unit/test_service.py`; offer wording is prompt-led | Complete (prompt-led) |
| Lab results: status only | `get_lab_status` returns the status string only | `tests/unit/test_service.py`, `tests/agent/test_tools.py` | Complete |
| Billing: balance due | `get_balance` | `tests/agent/test_tools.py` (refused before verification, `$45.00` after) | Complete |

## 5. New-patient booking

| Requirement | Implementation | Evidence | Status |
|---|---|---|---|
| Confirm first visit ("Is this your first visit…?") | Receptionist prompt | `tests/agent/test_prompts.py`, live call | Complete (prompt-led) |
| Collect only: name, DOB, phone, email, insurance + member ID or self-pay, short reason, optional doctor and preferred times | `book_appointment` validates each field; DOB captured in code; spoken email and member ID normalized | `tests/agent/test_tools.py`, `tests/unit/test_parsing.py`, eval `t3` | Complete |
| No detailed symptoms or history | Reason limited to a few words; only a category is stored | `tests/agent/test_tools.py` (`reason_too_long`) | Complete |
| Offer 2–3 matching slots | `find_open_slots` returns up to three real slots; nearest real alternatives when nothing matches | `tests/agent/test_tools.py` | Complete |
| Read back name, date/time, doctor, reason; spell the email | Read-back produced by the tool, including spelled email and member ID | `tests/agent/test_tools.py`, live call | Complete |
| Save new patient + appointment; remove the slot | One SQLite transaction | `tests/unit/test_service.py`, `tests/agent/test_tools.py`, eval `t3` | Complete |
| Arrival instructions; simulated confirmation email | Fixed instruction line; JSON file in `data/outbox/` | `tests/agent/test_tools.py`, eval `t3` | Complete |
| Ask if anything else, then end politely | Prompt plus `end_call` tool | Evals, live calls | Complete (prompt-led) |
| Verified existing patients book through the same flow, skipping details on file | `book_appointment` uses the verified record's name and email | `tests/agent/test_tools.py` | Complete |

## 6. Saving requests

| Requirement | Implementation | Evidence | Status |
|---|---|---|---|
| Save each refill, booking, callback and message with patient/new-patient ID, type, timestamp, short summary | `patient_requests` table; summaries are categories, not the caller's words; transfers recorded too | `tests/unit/test_service.py`, `uv run clinic show-requests` | Complete |

## 7. After-hours flow

| Requirement | Implementation | Evidence | Status |
|---|---|---|---|
| Say the office is closed and give the hours; 911 for emergencies | Fixed closed greeting | `tests/agent/test_guard.py`, live call | Complete |
| No patient information after hours, even if verified | After-hours agent has no patient tools; service refuses outside hours | `tests/agent/test_office_hours.py`, `tests/agent/test_tools.py`, eval `after_hours_no_phi_even_with_details` | Complete |
| Record name, callback number, short reason; read back; save; scripted close | `record_callback_message` with confirmation gate and fixed closing | `tests/agent/test_tools.py`, eval `t4`, live call | Complete |

## 8. Conversation quality

| Requirement | Implementation | Evidence | Status |
|---|---|---|---|
| Short, natural spoken answers | LLM-led conversation with a single receptionist prompt | Live calls, evals | Complete (prompt-led) |
| Confirm details before saving any request | Confirmation gate: saves only after the caller's own "yes" to that read-back | `tests/agent/test_tools.py` | Complete |

## 9. Guardrails

| Requirement | Implementation | Evidence | Status |
|---|---|---|---|
| No medical advice; offer a message to the doctor | Prompt; speech check blocks dosing advice; `leave_message_for_doctor` (verified) or staff callback | `tests/agent/test_speech_guard.py`, evals `t5`, `dose_change_after_verification`, `roleplay_jailbreak` | Complete (prompt-led) |
| Emergencies: tell them to call 911, stop the normal flow | Code-level detection before the LLM on every turn; scripted line; call ends; audited | `tests/security/test_emergency.py`, `tests/agent/test_guard.py`, evals `t6`, `t6b`, live call | Complete |
| No third-party access | Verification covers the caller only; prompt forbids confirming another person is a patient | Evals `t7`, `spouse_balance`, `other_patient_after_verification`, live call | Complete (prompt-led) |
| No made-up information | Tools return only stored data; slots must come from `find_open_slots` | `tests/agent/test_tools.py` (`unknown_slot`) | Complete |
| Stay on topic; resist prompt injection | Prompt; no tool can list patients or take a patient ID | Eval `prompt_injection`, `tests/agent/test_tools.py` | Complete (prompt-led) |
| Offer transfer when upset, confused or asking for a person | `transfer_to_staff` records the request and plays the handoff line | `tests/agent/test_tools.py`, live call | Complete (simulated: no live transfer endpoint on a web call) |

## 10. HIPAA principles

See [hipaa-matrix.md](hipaa-matrix.md) for the full mapping. Summary:

| Principle | Status |
|---|---|
| Verify before disclosure | Complete |
| Minimum necessary | Complete |
| SSN protection (last 4 only, never spoken back, never sent to the LLM) | Complete |
| Mask data in logs and transcripts | Complete. Identifiers are replaced with `[REDACTED_DOB]`, `[REDACTED_SSN]` and similar markers rather than partial masks such as `****-**-14`; no transcripts are stored |
| Matching in code, not the LLM | Complete |
| Secrets in `.env`, `.env.example` provided | Complete |
| Audit log | Complete |
| BAA statement per vendor and production changes | Complete (README) |
| Call recording notice | Complete |
| Synthetic data only | Complete |

## 11. Submission

| Requirement | Status |
|---|---|
| README: setup, tools and why, verification, booking flow, after-hours, guardrails and HIPAA measures | Complete |
| 5–7 minute demo video of the seven scenarios | Manual: to be recorded with [demo-script.md](demo-script.md) |
| GitHub repository link | Manual |
