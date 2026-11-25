# HIPAA-aware design matrix

This is an engineering traceability aid for the synthetic assessment prototype, not a HIPAA certification or legal compliance determination.

| Principle | Implementation | Evidence |
|---|---|---|
| Verify before disclosure/action | `ClinicService` resolves patient identity from server-side `call_id`; all three values must match the same patient. | `tests/unit/test_verification.py`, `tests/unit/test_authorization.py` |
| Minimum necessary | Service methods return only the requested appointment, lab status, balance, or refill information; booking reason is reduced to a category in the request log. | `tests/agent/test_tools.py`, `tests/unit/test_service.py` |
| Never request/store/repeat full SSN | Verification accepts exactly the last four digits; per-record salt plus `HASH_PEPPER` protects the stored digest. | `tests/security/test_hashing.py`, `tests/unit/test_parsing.py` |
| Mask identifiers before model/history/log retention | DOB and SSN digits are captured by code and removed from caller text before every model call and from stored history (`src/agent/capture.py`, `src/agent/guard.py`). Every log line passes a deterministic masker for DOB, SSN, last-four, phone, email and member ID; LiveKit raw-transcript log extras are dropped. | `tests/agent/test_capture.py`, `tests/agent/test_guard.py`, `tests/security/test_masking.py`, `tests/security/test_logging.py`, `tests/security/test_canary.py` |
| Perform identity matching in backend code | Deterministic parsing and keyed digest comparison; the LLM never performs identity matching. | `tests/unit/test_verification.py`, `tests/unit/test_authorization.py` |
| Protect credentials and secrets | Credentials and `HASH_PEPPER` are read from environment/`.env`; `.env` is ignored and `.env.example` contains placeholders. | `src/clinic/config.py`, `.gitignore`, `.env.example` |
| Maintain audit trail without unnecessary PHI | Verification, refill, booking, callback, doctor message, and transfer events use typed audit records without raw transcript or failed-field detail. | `tests/security/test_audit.py`, `tests/unit/test_service.py` |
| Execute vendor BAAs before production PHI | The README distinguishes LiveKit Cloud/Inference coverage from the direct Deepgram plugin BAA requirement and direct OpenAI API requirements. No BAAs are assumed signed. | `README.md` vendor/BAA matrix; verify current contract and eligible configuration with each vendor |
| Recording notice and recording controls | Calls announce the recording-quality notice; app recording is disabled (`record=False`) and Deepgram `mip_opt_out=True` is set. | `src/agent/phrases.py`, `src/agent/main.py`, `src/agent/config.py`, `tests/agent/test_prompts.py` |
| Use synthetic data only | Three fictional patient fixtures and synthetic appointment slots are seeded; no real records are included. | `data/seed/`, `tests/unit/test_seed.py` |

## Additional safeguards

| Safeguard | Implementation | Evidence |
|---|---|---|
| Nothing unsafe is spoken | Each sentence the model produces is checked before speech; SSN/DOB read-backs, refill promises and dosing advice are replaced and logged (`event=speech_blocked`, rule name only). | `src/agent/speech_guard.py`, `tests/agent/test_speech_guard.py` |
| Emergencies win | Emergency language is detected in code before any model call; the caller hears a scripted 911 direction, the call ends, and an `emergency_redirected` audit event is written. | `src/clinic/security/emergency.py`, `tests/security/test_emergency.py`, `tests/agent/test_guard.py` |
| Tracing without content | LiveKit spans are exported to Langfuse with `allow_pii=False`; transcripts, prompts, tool arguments and tool results are removed in-process before export. | `src/agent/tracing.py`, `tests/agent/test_tracing.py` |
| Behaviour under adversarial callers | 15 scripted callers run against the real model, including prompt injection, full-SSN overshare, third-party and after-hours PHI requests. | `tests/evals/test_scenarios.py` (`make evals`) |
| Secrets and dependencies | gitleaks scans git history; pip-audit checks locked dependencies; Ruff bandit rules lint for unsafe code. | `.github/workflows/ci.yml` |

## Important limitations

- Audio/text still transit the room, STT, LLM, and TTS providers during a call.
- `mip_opt_out=True` is not a blanket no-retention guarantee.
- Local SQLite and the JSON email outbox are prototype storage, not production-grade PHI storage.
- New-patient records use `verification_ready=0` until staff completes identity enrollment because the assessment intake does not collect SSN last four.
- No live staff transfer or email delivery provider is configured.
- No vendor BAA is executed in the assessment environment.
- Caller names, and a new patient's phone, email and insurance details, reach the LLM because the conversation needs them; only DOB and SSN digits are kept from it.
- Third-party, medical-advice and prompt-injection refusals rely on the prompt; the backend authorization and the speech check limit the damage if the model errs, but cannot judge every phrasing.
- Langfuse Cloud receives call metadata (timings, ids, models, tool names); its BAA terms were not verified.
