# Finnie — AI Finance Assistant
## Claude Code context file

> Read this at the start of every session. It gives full project context in one place.

---

## Who is building this and why

Capstone project for Applied Agentic AI. The goal is to finish it **while learning every concept** so the student can defend every design decision in an interview. Each phase runs in four beats:

1. **Lesson** — Claude teaches the concept, explains the why before the what
2. **Implementation** — Claude writes the code, then walks through every line so the student understands it
3. **Notes** — Key ideas added to `docs/LEARNING_NOTES.html` and `docs/CODE_GUIDE.html`
4. **Grilling** — At the end of each phase, Claude runs an interview-style grill on that phase's concepts

**Never edit a test to make it pass.** The tests are the specification.

---

## How to interact with this student

- **Step by step** — one concept at a time. Teach the why first, then write the code, then explain every line.
- Claude writes the code. Student learns by reading, asking questions, and being grilled.
- Grill at the **end of each phase** — not mid-phase. Cover all concepts from that phase.
- Keep responses short and direct. No walls of text.
- Add code walkthroughs to `docs/CODE_GUIDE.html` as each function is written.

---

## Current status

| Phase | Name | Status |
|-------|------|--------|
| 0 | Environment & project skeleton | 🔨 In progress — 4 TODOs left for student |
| 1–13 | (see ROADMAP) | Pending |

**Phase 0 student TODOs** (in this order):
1. `_apply_env_overrides` in `src/core/config.py`
2. `load_config` in `src/core/config.py`
3. `setup_logging` in `src/core/logging_setup.py`
4. `get_logger` in `src/core/logging_setup.py`

Done when: `pytest -v` passes all 14 tests in `tests/test_config.py` AND `ruff check src` is clean.

**Phase 1 is next:** `core/llm.py` — OpenAI adapter behind an interface, retry with backoff, token-bucket rate limiting, cost meter, `core/compliance.py`, and `FakeLLM`.

---

## Project documents (always open these first if confused)

- **[`docs/ROADMAP.html`](docs/ROADMAP.html)** — 14-phase build plan, checklists, rubric mapping
- **[`docs/LEARNING_NOTES.html`](docs/LEARNING_NOTES.html)** — every concept taught so far, with interview questions
- **Artifact URL for ROADMAP**: https://claude.ai/artifact/4f4dvqr4vYMK7rEavpKHWF

---

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Orchestration | LangGraph `StateGraph` | Highest-weighted rubric item; explicit, inspectable, testable |
| LLM | GPT-4o, `gpt-4o-mini` for routing | Reliable structured outputs; model tiering controls cost |
| Embeddings | `all-MiniLM-L6-v2` local | 384-dim, CPU-friendly, zero API cost |
| Vector store | FAISS `IndexFlatIP` | In-process, exact search, 100 articles is too small for ANN |
| Market data | yfinance primary, Alpha Vantage fallback | yfinance free; Alpha Vantage teaches real rate-limit engineering |
| UI | Streamlit | Named in rubric; `session_state` handles conversation memory |
| Tests | pytest + pytest-cov | FakeLLM + fake price feed = deterministic, offline |

---

## Critical constraints (never violate these)

1. **Secrets in `.env` only** — `.env` is gitignored; `.env.example` is committed and must never contain a real key
2. **Fail fast on missing key** — `load_config` raises `RuntimeError` naming `OPENAI_API_KEY` if absent
3. **Never log a secret or a user's full portfolio**
4. **Compliance is not optional** — every user-facing response carries the educational-use disclaimer; banned phrases: `"you should buy"`, `"you should sell"`, `"i recommend buying"`, `"i recommend selling"`, `"guaranteed return"`, `"risk-free profit"`
5. **Education, not advice** — no agent ever suggests a specific trade

---

## Key file locations

```
ai_finance_assistant/
├── src/core/config.py          ← pydantic schema + 3 TODO functions
├── src/core/logging_setup.py   ← 2 TODO functions
├── tests/test_config.py        ← 14 acceptance tests (do not edit)
├── config.yaml                 ← all behavioural settings (single source of truth)
├── .env.example                ← committed placeholder; copy to .env and add key
├── pyproject.toml              ← pytest config (pythonpath="."), ruff rules
├── requirements.txt            ← dependency ranges; freeze after install
└── docs/
    ├── ROADMAP.html            ← 14-phase plan with checklists
    └── LEARNING_NOTES.html     ← concepts taught + interview questions
```

---

## Setup commands (from `ai_finance_assistant/` directory)

```bash
python -m venv .venv
source .venv/Scripts/activate    # Windows Git Bash; use .venv\Scripts\activate on cmd/PS
pip install -r requirements.txt
pip freeze > requirements.lock.txt
cp .env.example .env             # then paste OPENAI_API_KEY into .env
pytest -v                        # expect failures: NotImplementedError until Phase 0 done
```

---

## Rubric weights (grading priorities)

| Criterion | Points |
|-----------|--------|
| Multi-Agent Architecture | 10 |
| LangGraph Workflow | 10 |
| Web Interface (Streamlit) | 10 |
| RAG Implementation | 8 |
| Conversational Flow | 8 |
| Educational Content | 8 |
| Real-time Data Integration | 7 |
| Data Visualization | 7 |
| Portfolio Analysis | 7 |
| Code Organization | 5 |
| Documentation | 5 |
| Testing | 5 |
| Market Intelligence | 5 |
| MCP Server *(bonus)* | 5 |
| Innovation *(bonus)* | 10 |

---

## Concepts already taught (Phases 0)

- Concepts 01–09: LLMs, prompt/chain/agent/workflow, multi-agent rationale, RAG vs fine-tuning, embeddings, chunking, tool calling, state/memory, education vs advice
- Concepts 10–13: virtual environments, 12-factor config (3 kinds), packages/modules, structured logging
- Interview questions written for all of the above — see `docs/LEARNING_NOTES.html`

---

## Interview prep note

Every phase ends with an interview grilling. The student needs to be able to explain:
- **Why** each design decision was made (not just what)
- **Trade-offs** of the chosen approach vs alternatives
- **What breaks** at scale (10k users, rate limits, latency)
- The **exact terminology** an interviewer would use

---
*Last updated: Phase 0 scaffold complete. Student implementing config + logging.*
