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
| 0 | Environment & project skeleton | ✅ Complete — ruff clean |
| 1 | Config, LLM client & compliance layer | ✅ Complete — ruff clean |
| 2 | Knowledge base curation | ✅ Complete — 281 docs, 14 categories, none below 6, real titles |
| 3 | RAG pipeline | ✅ Complete — chunker, embedder, Chroma store, retriever (MMR), prompt, chain + 3 eval harnesses |
| 4 | BaseAgent abstraction | ✅ Complete — `src/agents/base.py` + `src/workflow/state.py`, 16 tests |
| 5 | Finance Q&A Agent | ✅ Complete — `src/agents/qa.py`, 15 tests |
| 6 | Market data layer + Market Analysis Agent | ✅ Complete — `src/data/market.py` (4-tier degradation, trends), `src/agents/market.py`, 70 tests |
| 7–13 | (see ROADMAP) | Pending |

**Test/lint status:** 136/136 pass (14 config + 21 llm/compliance + 16 base agent + 15 qa agent + 41 market data + 29 market agent), ruff clean.
**Pushed:** `f48e533` on `origin/master`.

**Index:** 2,000 chunks in `data/indexes` (Chroma collection `finnie_kb`), built 2026-11-08.

**Retrieval quality (MMR, top_k=4):** easy 1.00 hit / medium 1.00 / hard 1.00 / **realistic 1.00 hit, MRR 1.00, P@k 0.85**. The `realistic` bucket is the one that matters — 15 queries written from the beginner persona's phrasing rather than reverse-engineered from the corpus (FR-026). Caveat for honesty: the same author wrote both those articles and those queries, so it is better evidence than the easy/medium/hard sets but not independent.

**Day 0 (Nov 8) housekeeping — DONE:**
- Baseline commit `3d02c5e` (299 files); `docs/Varsity PDFs/` gitignored (61 MB, copyrighted, not redistributable)
- `config.yaml` market block is now India-only: `default_tickers` RELIANCE/TCS/HDFCBANK/INFY/ICICIBANK (`.NS`), `default_indices` `^NSEI`/`^BSESN`, plus `currency: INR` and `exchange_suffix`
- **One import convention everywhere:** `src/` is the import root, so all code uses `from core.x import ...` / `from rag.x import ...`. `pyproject.toml` sets `pythonpath = ["src", "."]`; tests were migrated off the `src.`-prefixed style
- 15 ruff errors cleared — the 4 `print` calls in `src/rag/` are now `logger` calls, `zip()` in `_cosine_similarity` is `strict=True`

**Phase 2 KB rebuild — DONE** (PRD FR-020 → FR-026):
- `scripts/fix_kb_titles.py` derived real titles from the line after each `## Chapter N` heading: 253 of 263 files renamed, 2 fallbacks, idempotent. Also strips private-use Unicode glyphs left by PDF extraction
- 18 beginner articles authored, every thin category now ≥ 6: insurance 2→6, fixed-income 2→6, investing 2→6, personal-finance 3→6, tax 8→11. Each carries a real title, source organisation, authority URL, `date_retrieved`, and an educational-use note
- `chunker.py` now carries `url` and `date_retrieved` into chunk metadata — previously parsed then dropped, so citations could never link out
- `eval_queries.json`: 15 `realistic` queries added; `q001` corrected from the pre-July-2024 LTCG rule (10% above ₹1 lakh) to the current 12.5% above ₹1.25 lakh — the eval set had been penalising the right answer
- `src/utils/console.py` — `ensure_utf8_stdout()`, wired into all four scripts. Windows cp1252 consoles crashed the eval scripts *after* the run completed, which would hit any grader on Windows

**Phase 4 BaseAgent — DONE.** `src/workflow/state.py` defines `AgentState` with reducers (`add_messages` for conversation, `operator.add` for `agent_trace`). `src/agents/base.py` is a template method: `run()` owns timing, logging, tracing and the error boundary; subclasses implement only `handle()`. `run()` never raises — a failing agent returns a friendly message plus `error`, because a raising node aborts the whole LangGraph invocation.

**Phase 6 notes.** `src/data/market.py` owns *what the number is*; `src/agents/market.py` owns *what to say about it*. Four-tier degradation (live → fresh cache → stale cache → mock) with the provenance label travelling on the `Quote`. Two rules learned the hard way on 2026-11-08: a feed **raising** means an outage (retry, then degrade), a feed **answering cleanly with nothing** means no such symbol (reject, never mock) — conflating them made AAPL return an invented ₹593. And `get_trends` has **no mock tier at all**: a labelled fake price is honest, a fake trend line is an invented narrative. Symbol extraction is a tested pure function, not an LLM call.

**Phase 7 is next:** Portfolio Analysis Agent (Day 2).

---

## Project documents (always open these first if confused)

- **[`docs/PRD.md`](docs/PRD.md)** — v1.2 product requirements: 46 FRs with acceptance criteria, rubric→artifact matrix, 7-day plan, risks, Streamlit layout spec (§6.5a), and the root-cause analysis of the RAG quality gap (§7.4). **Read this before the ROADMAP.**
- **[`docs/ROADMAP.html`](docs/ROADMAP.html)** — 14-phase build plan, checklists, rubric mapping
- **[`docs/LEARNING_NOTES.html`](docs/LEARNING_NOTES.html)** — every concept taught so far, with interview questions
- **Artifact URL for ROADMAP**: https://claude.ai/artifact/4f4dvqr4vYMK7rEavpKHWF

---

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Orchestration | LangGraph `StateGraph` | Highest-weighted rubric item; explicit, inspectable, testable |
| LLM | GPT-4o, `gpt-4o-mini` for routing | Reliable structured outputs; model tiering controls cost |
| Embeddings | OpenAI `text-embedding-3-small` @ **512-dim** | Matryoshka truncation: 67% smaller index for <5% quality loss. Costs ~$0.01 per full re-index. *(Was planned as local 384-dim MiniLM; changed deliberately on 2026-11-08 for retrieval quality — `tests/test_config.py` asserts 512)* |
| Vector store | ChromaDB | Stores vectors + metadata together natively; simpler than FAISS + separate metadata dict |
| Market data | yfinance primary, Alpha Vantage fallback | yfinance free; Alpha Vantage teaches real rate-limit engineering. **Always call it "yfinance data", never "NSE data"** — yfinance reads Yahoo, a redistributor with a ~15-min delay, so "exchange data" overstates both freshness and provenance |
| UI | Streamlit | Named in rubric; `session_state` handles conversation memory |
| Tests | pytest + pytest-cov | FakeLLM + fake price feed = deterministic, offline |

---

## Critical constraints (never violate these)

1. **Secrets in `.env` only** — `.env` is gitignored; `.env.example` is committed and must never contain a real key
2. **Fail fast on missing key** — `load_config` raises `RuntimeError` naming `OPENAI_API_KEY` if absent
3. **Never log a secret or a user's full portfolio**
4. **Compliance belongs to the graph, not the call site.** Today `check_and_wrap` is called from `app.py` / `rag_lab.py` because there is no graph yet. **On Day 4 it moves into the terminal compliance node and the UI stops importing it** (PRD §7.5 / D1) — otherwise the MCP server in Phase 13 would bypass it. No agent ever calls it: `BaseAgent` deliberately does not apply it, and doing so in an agent double-injects the disclaimer.
5. **Compliance is not optional** — every user-facing response passes `check_and_wrap`, which appends the disclaimer exactly once (it strips any the model wrote itself). The prompt must NOT instruct the model to add one.
6. **Education, not advice** — no agent ever suggests a specific trade
7. **The banned list blocks advice, not topics** (narrowed 2026-11-08). Blocked: promises (`guaranteed returns of`, `guaranteed profit`, `risk-free profit`, `cannot lose money`) and instructions (`you should buy/sell`, `i recommend/suggest buying/selling`). Allowed: factual statements about sovereign-backed rates, e.g. "PPF pays a government-set 7.1%". The old blanket ban on `guaranteed return` made Finnie unable to describe PPF or FDs. Read the list from `config.yaml` — never hardcode a copy, which is exactly how `eval_adversarial.py` ended up grading a policy that was no longer shipped.
8. **Comparison questions get answered, not refused** (prompt rule 6). "Is PPF better than ELSS?" returns the trade-offs plus "it depends on your goals, horizon and risk tolerance" — never a winner, never a refusal.

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
pytest -v                        # 25 tests pass (14 config + 11 llm/compliance)
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
## Scope (locked 2026-11-08)

**India only.** INR, NSE/BSE, Indian instruments and Indian tax. No US/global exchanges, no USD, no 401k/IRA/Roth. A foreign ticker gets a clear out-of-scope reply. Submission target: **2026-11-15**.

**Commits carry no `Co-Authored-By` / AI attribution line** — author's preference, the repo is an interview showcase.

---
*Last updated: 2026-11-08, Day 0. Baseline committed (`3d02c5e`), India-only config, one import convention, ruff clean, 25/25 tests pass. KB rebuild in progress.*
