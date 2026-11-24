# Repository structure

Build steps are implementation batches, not source-code directories. We will not create `step1/`, `step2/`, etc. The only top-level step directory is `step0/`, which holds temporary feasibility probes and reference tests. Production code is organized by responsibility under `src/`.

```text
Sunrise-Family-Clinic-VoiceAgent/
├── README.md                         # written in Step 5
├── INSTRUCTIONS.md                   # repository working rules
├── pyproject.toml
├── uv.lock                           # generated with `uv lock`
├── .python-version
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml           # Step 5
├── Makefile
├── .github/
│   └── workflows/ci.yml              # Step 5
├── step0/                            # temporary feasibility harness
│   ├── README_STEP0.md
│   ├── check_sdk.py
│   ├── check_deepgram.py
│   ├── check_inference.py
│   ├── region_probe.py
│   ├── guard.py
│   ├── livekit_guard.py
│   ├── metrics.py
│   ├── smoke_agent.py
│   └── tests/
│       ├── test_privacy.py
│       ├── test_metrics.py
│       └── test_livekit_guard.py
├── data/
│   ├── seed/
│   │   ├── patients.json              # Step 1
│   │   └── slots.json                 # Step 1
│   └── out/                           # runtime outputs, gitignored
├── docs/
│   ├── DECISIONS.md
│   ├── MANIFEST.md
│   ├── REQUIREMENTS.md
│   ├── STATUS.md
│   ├── STEPS.md
│   ├── STRUCTURE.md
│   ├── latency.md
│   ├── hipaa-matrix.md                # Step 5
│   ├── demo-script.md                 # Step 5
│   └── interview-notes.md             # Step 5
├── src/
│   ├── clinic/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── clock.py
│   │   ├── models.py
│   │   ├── session.py
│   │   ├── service.py
│   │   ├── audit.py
│   │   ├── logging.py
│   │   ├── domain/
│   │   ├── security/
│   │   ├── persistence/
│   │   └── api/
│   └── agent/
│       ├── __init__.py
│       ├── main.py
│       ├── config.py
│       ├── state.py
│       ├── tools.py
│       ├── guard.py
│       ├── phrases.py
│       ├── metrics.py
│       ├── agents/
│       └── prompts/
└── tests/
    ├── conftest.py
    ├── unit/
    ├── security/
    ├── api/
    └── agent/
```

`step0/` is retained only while the spike harness is useful. When the final agent is implemented, reusable privacy/metrics helpers and their tests move to the manifest's final `src/agent/` and `tests/` locations; the smoke worker can then be removed. No separate folders are created for Steps 1–5.
