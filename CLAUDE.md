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
| 7 | Portfolio Analysis Agent | ✅ Complete — `src/portfolio/` (metrics, holdings, analysis) + `src/agents/portfolio.py`, 120 tests |
| 8 | Goal Planning Agent | ✅ Complete — `src/goals/projections.py` + `src/agents/goal.py`, 91 tests |
| 9 | News Synthesizer + Tax Education | ✅ Complete — `src/data/news.py`, `src/agents/news.py`, `src/agents/tax.py`, 66 tests. **All six agents exist.** |
| 10 | LangGraph workflow | ✅ Complete — `src/workflow/{registry,router,graph}.py`, 75 tests. Router gate **95% strict / 100% lenient** on the 40-query set |
| 11–13 | (see ROADMAP) | Pending |

**Test/lint status:** 491/491 pass, ruff clean.
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

**Phase 7 notes.** Three layers, each testable without the one above it: `portfolio/metrics.py` is pure arithmetic checked against hand calculations (every expected value is worked out in the test, never copied from output); `portfolio/holdings.py` validates untrusted input and *collects* errors rather than raising, so a 20-row CSV with one typo still values the other 19; `portfolio/analysis.py` assembles the finished dict from holdings plus a price map passed in, so the whole assembly runs offline.

Three judgement calls to be able to defend: **HHI** for concentration (standard, citable) because a holding count is blind to a 97% position; **diversification_score** is Finnie's own composite of evenness, breadth and class spread, documented as a heuristic — evenness alone would score three equally-weighted IT stocks 100/100; **risk_band** is structural, derived from asset-class weights rather than volatility, so it works on turn one with no price history and is explainable in a sentence.

A holding with no price is **excluded and named**, never valued at zero — a portfolio silently worth less than it is would be the most damaging quiet failure in the system. Non-traded holdings (funds, SGBs, cash) get no `.NS` suffix and carry a user-supplied price; suffixing them would send yfinance after a listing that does not exist. And per constraint 3, this agent logs counts only — `tests/test_portfolio_agent.py` asserts no symbol, quantity or value reaches the log or the trace.

**Phases 8–9 notes.** `goals/projections.py` is the same pure-maths discipline as the portfolio metrics, with every expectation evaluated from the closed form longhand. Two conventions to be able to defend: **annuity due** (contributions at the start of each month, worth ₹1,268 on one year of a ₹10,000 SIP against the end-of-month form) and **i = annual/12** rather than the effective monthly rate, because that is what AMFI, Groww and Zerodha show and an unexplained mismatch reads as a bug in Finnie. The required SIP is sized against the **inflation-adjusted** target: ₹50 lakh in 12 years needs ₹1.006 crore, so ₹33,586/mo rather than ₹16,691.

`TaxEducationAgent` subclasses `FinanceQAAgent` — PRD §7.1 drew it that way, and a parallel implementation would mean two places to fix the next retrieval bug. It adds a fixed `category="tax"` filter (the one agent where that is right, since the router has already established the topic), a prompt pinning the post-July-2024 rates, and an assessment year **computed** from the date and appended in code. A hardcoded AY is right for five months and wrong thereafter.

`data/news.py` parses **both** yfinance news payload shapes (flat pre-0.2.40, nested under `content` from ~0.2.50), because pinning to one means a version bump returns zero headlines, which is indistinguishable from a quiet news day.

**Known gap:** Yahoo's news endpoint was down on 2026-11-08 — `Ticker.news` raised "YAHOO! FINANCE IS CURRENTLY DOWN" while quotes worked fine. So the news parsing is verified against fixtures, not a live response, and **the live path must be re-checked before the Day 6 video**. FR-014 is P1 and already on the cut list if it stays down; the outage path degrades to an honest message with no LLM call.

**Phase 10 notes — the graph.** `START → supervisor → [1–2 agents] → compliance → END`, with a `fallback` node for a route that cannot run. Three things worth being able to defend:

- **The next node is derived from `agent_trace`, not a counter.** `_next_node` subtracts the agents that have already recorded an entry from the route and takes the first one left. No index to keep in sync, and an agent cannot run twice — so a route cannot loop. Composition (FR-003) falls out of the same wiring as a single-agent turn, with no special case.
- **The supervisor does two jobs in one call:** it picks the agents *and* rewrites the question to stand alone. "What about the second one?" becomes "What is the TCS price?" once, in `resolved_question`, instead of handing all six agents the whole transcript. Contextual query rewriting, at zero extra cost, on a call that was already happening every turn. `BaseAgent._latest_question` prefers it.
- **Structured output constrains the shape, not the values.** The router validates every name against the registry, collapses duplicates, caps the route at 2, and falls back to `finance_qa` — a model can still return `crypto_advisor`, six agents, or the same agent twice. A route decides what code runs next; it is the last place to take a model's word for anything.

**Router gate (FR-002): 95% strict, 100% lenient on 40 labelled queries** (`data/router_queries.json`, `scripts/eval_router.py --strict`). Both disagreements were on queries labelled ambiguous, where the router chose the alternative the label itself lists as defensible. **The set still needs the author's review and acceptance before it counts as the gate.**

**Two defects found live on 2026-11-08, invisible to 491 passing tests:**
1. A composed turn left two AI messages in state, so every consumer reading `messages[-1]` as "the answer" silently dropped the first agent's work. The compliance node now merges the turn's answers and removes the superseded ones with `RemoveMessage`. One turn, one answer, one disclaimer.
2. gpt-4o copied the figures out of the goal prompt's own illustrative example, telling a user with a ₹1 crore goal that "₹10 lakh today won't have the same purchasing power". A rule that demonstrates with numbers invites the model to reuse them.

**The general lesson, now three times over:** data belongs in the data block as flags and figures, instructions belong in the rules, and prose written into a data block gets quoted back at the user. The equity-cap flag was rewritten from a sentence into `Horizon equity cap: applied / not applied` for exactly this reason.

**Phase 11 is next:** the Streamlit 4-tab app per PRD §6.5a (Day 5).

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
4. **Compliance is a terminal graph node — DONE on Day 4 (PRD §7.5 / D1).** `check_and_wrap` is called only from `src/workflow/graph.py`. `app.py` no longer imports it, and two tests in `tests/test_graph.py` assert that it never does again. Never call it from an agent or from the UI: `BaseAgent` deliberately does not apply it, and a second call double-injects the disclaimer. `rag_lab.py` keeps its own call on purpose — it is a debug harness for the raw RAG chain, deliberately showing the un-orchestrated pipeline, and is not a user-facing path.
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
