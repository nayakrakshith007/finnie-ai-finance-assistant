# PRD — Finnie: AI Finance Assistant

**Capstone:** Applied Agentic AI for SWEs — *Democratizing Financial Literacy Through Intelligent Conversational AI*
**Owner:** Rakshith Nayak · **Status:** Phases 0–3 complete (KB rebuild pending), Phases 4–13 scheduled · **Version:** 1.2
**Date:** 2026-11-08 · **Target submission:** 2026-11-15 (7 days)
**Sources:** Problem Statement.docx, Project Milestones.docx, Grading Rubric.xlsx, `docs/ROADMAP.html`, live repo state

---

## 1. Executive Summary

**Vision.** Finnie is a multi-agent conversational finance tutor that lets a complete beginner ask "should I start a SIP or buy an index fund?" and get a cited, jargon-free, compliance-safe education — grounded in a curated knowledge base and live market data, never in investment advice.

**Value proposition — three audiences at once:**

| Audience | What Finnie delivers |
|---|---|
| Beginner investor (product user) | Jargon-free, cited financial education + portfolio insight + goal projections, for the Indian market |
| Course evaluator (grader) | Every rubric line item demonstrably implemented, each worth a visible artifact |
| Interviewer (career outcome) | A production-shaped agentic system the author can defend line-by-line, publicly deployed on GitHub |

**Why multi-agent, not one big prompt.** Six specialised agents behind a LangGraph supervisor give (a) deep domain accuracy per vertical, (b) independently testable units, (c) explicit, inspectable state transitions, and (d) a routing layer that can fan out or compose agents for compound questions. This is also the single highest-weighted item on the rubric (Multi-Agent Architecture 10 + LangGraph Workflow 10 = 20% of the grade).

**Scope decisions locked for this build:** **India-only** (INR, NSE/BSE, Indian tax and instruments — no US market coverage); OpenAI `gpt-4o` for reasoning and `gpt-4o-mini` for routing; ChromaDB vector store; Streamlit UI; Docker + Streamlit Cloud public deployment.

---

## 2. Problem Statement

### 2.1 The user's problem

Financial literacy is the gate between people and wealth-building, and it is locked by four specific barriers — each one a design requirement, not just background:

| Pain point | Observable symptom | What Finnie must therefore do |
|---|---|---|
| **Jargon wall** | Beginner cannot parse "expense ratio", "LTCG", "asset allocation" | Plain-language answers with an inline glossary and a reading level fixed at beginner |
| **Trust deficit** | Users distrust AI financial output, and rightly so — hallucination risk is real money | Every factual claim carries a retrieved source citation; retrieval below a relevance threshold triggers an honest "I don't have a grounded answer" |
| **Theory/practice gap** | Static articles explain diversification but not *your* portfolio | Live market data + the user's own holdings analysed with the same vocabulary as the lesson |
| **Advice/education confusion** | A wrong answer here is a regulatory problem, not a bug | A compliance layer that no response can bypass: disclaimer injected, banned advice phrases blocked |

### 2.2 The author's problem

A capstone that merely works scores well and teaches nothing defensible. The constraint that shapes this entire PRD: **every component must be explainable in an interview** — why this design, what the alternatives were, what breaks at 10k users. The build process therefore interleaves lesson → implementation → walkthrough → grilling per phase (see `CLAUDE.md`).

### 2.3 Quantified stakes (grade model)

100 base points + 15 bonus. Current secured ceiling if nothing further ships: roughly 25/100. The gap to close in 7 days is the entire agent, workflow, UI, and quality surface.

---

## 3. Goals & Success Metrics

### 3.1 SMART goals

| # | Goal | Measure | Priority |
|---|---|---|---|
| G1 | All 6 agents implemented with distinct, non-overlapping capability | 6/6 agents pass their own behavioural test file | **P0** |
| G2 | LangGraph `StateGraph` routes, composes, remembers, and recovers | Router accuracy ≥ 90% on a 40-query labelled set; fallback node covers every agent exception | **P0** |
| G3 | RAG answers are grounded and cited | ≥ 90% of answers carry ≥ 1 citation; retrieval hit@3 ≥ 0.85 on `eval_queries.json` | **P0** |
| G4 | Live market data is resilient | Zero unhandled failures across quote-fetch, rate-limit, and API-down simulations; cache hit ratio > 70% in a demo session | **P0** |
| G5 | 4-tab Streamlit app usable by a beginner | Chat, Portfolio, Market, Goals all functional; context preserved across ≥ 5 turns | **P0** |
| G6 | Knowledge base at the "Excellent" bar | ≥ 100 freshly sourced Indian-context articles across ≥ 10 categories, none below 6 articles, all with real titles and source metadata | **P0** |
| G7 | Test coverage ≥ 80% (target 90%) | `pytest --cov` report committed in README | **P1** |
| G8 | Documentation an evaluator can run from cold | README + DESIGN.md + architecture diagram; fresh clone to running app in ≤ 5 commands | **P1** |
| G9 | Public live demo + container | Streamlit Cloud URL in README; `docker run` works | **P1** |
| G10 | MCP server exposing finance tools to Claude Desktop | 3+ tools callable; documented. **Attempted last, time-boxed to 3 hours on Nov 15, after the demo video is already banked**; showcased only if it works | **P2 (bonus, opportunistic)** |
| G11 | Innovation surface | Agent-trace visualiser + RAG eval dashboard + adversarial compliance suite | **P2 (bonus)** |
| G12 | Interview readiness | Author answers the full grill set per phase without notes | **P0 (personal)** |

### 3.2 Rubric → artifact traceability

| Rubric criterion | Pts | Artifact that earns it | Goal |
|---|---|---|---|
| Multi-Agent Architecture | 10 | `src/agents/*.py`, 6 agents + `BaseAgent` | G1 |
| LangGraph Workflow | 10 | `src/workflow/graph.py`, state schema, router, fallback | G2 |
| Web Interface | 10 | `src/web_app/`, 4 tabs | G5 |
| RAG Implementation | 8 | `src/rag/*`, citations, eval result JSONs | G3 |
| Conversational Flow | 8 | Memory in state; multi-turn demo | G2, G5 |
| Educational Content | 8 | `data/knowledge_base/` 100+ articles | G6 |
| Real-time Data Integration | 7 | `src/data/market.py`, cache + backoff + fallback | G4 |
| Data Visualization | 7 | Plotly charts: allocation, trend, projection | G5 |
| Portfolio Analysis | 7 | `src/agents/portfolio.py` + pure metric functions | G1 |
| Code Organization | 5 | Prescribed tree, typed, ruff clean | G8 |
| Documentation | 5 | README, DESIGN.md, diagrams, docstrings | G8 |
| Testing | 5 | ≥ 80% coverage, unit + integration | G7 |
| Market Intelligence | 5 | `src/agents/market.py` interpretation layer | G1 |
| MCP Server *(bonus)* | 5 | `src/mcp_server/` | G10 |
| Innovation *(bonus)* | 10 | Trace visualiser, eval dashboard, adversarial suite | G11 |

---

## 4. Non-Goals (explicit boundaries)

Stated so neither the build nor the grader expects them:

1. **No personalised investment advice.** No "buy X". Education only, enforced in code by `src/core/compliance.py`.
2. **No real money movement.** No brokerage integration, no order placement, no payments.
3. **No user authentication or multi-tenancy.** Streamlit `session_state` only; no accounts, no user database.
4. **No PII persistence.** Portfolios live in session memory; nothing written to disk.
5. **No model fine-tuning.** RAG is the chosen grounding mechanism; the trade-off is documented, not implemented both ways.
6. **No mobile or native app.** Web only.
7. **No intraday/tick data and no trading signals.** Quotes with a 30-minute cache TTL are sufficient and honest.
8. **No crypto, derivatives, or F&O coverage** in the knowledge base for v1.
9. **No voice interface.** Listed as future direction only.
10. **No microservices split.** Monolith with clean module boundaries; distributed architecture is a documented future step.
11. **No non-Indian markets.** NSE/BSE tickers and INR only; no US/global exchanges, no USD, no 401k/IRA/Roth content. Global market support is a documented future direction, and the agent says so plainly when asked about a foreign ticker.

---

## 5. User Personas

> **These are fictional composites, not real people.** A persona is a standard product-design device: a named, concrete stand-in for a user segment, so that requirements can be tested against someone specific ("would Priya understand this answer?") instead of an abstraction ("would a beginner?"). P2 is the sole exception — that one is the actual author. Rename any of them freely; the names carry no weight beyond readability.

### P1 — "Priya", 26, first-time investor (primary product user) — *fictional*

Software QA engineer in Pune. ₹85k/month, ₹2L sitting in a savings account, just opened a demat account and froze. Has heard "index fund" and "SIP" but cannot tell them apart; terrified of losing money.

- **Jobs:** "Explain ETFs like I'm new." · "Is my 3-stock portfolio risky?" · "How much do I need monthly for ₹50L in 10 years?"
- **Needs:** zero jargon, visible sources, no pressure, INR and Indian instruments.
- **Fails if:** the answer reads like Investopedia, or a number appears with no explanation.

### P2 — Rakshith, the author (builder/learner)

Needs the system to be a teaching instrument and a portfolio piece simultaneously.

- **Jobs:** "Build it end-to-end." · "Grill me on LangGraph state." · "Make the repo the thing a recruiter reads first."
- **Needs:** one concept per step; code walkthroughs; an interview question bank per phase.
- **Fails if:** code lands that he cannot defend.

### P3 — Dr. Mehta, course evaluator (grader)

Has 40 submissions and roughly 20 minutes each.

- **Jobs:** clone, run, judge against the rubric, watch the demo video.
- **Needs:** ≤ 5-command setup, visible architecture diagram, obvious mapping to rubric lines, a demo that shows agents cooperating.
- **Fails if:** setup breaks, or the sophistication is real but invisible.

---

## 6. Functional Requirements

Format: `FR-ID · Priority · Requirement · Acceptance criteria`. P0 = submission-blocking, P1 = grade-critical, P2 = bonus.

### 6.1 Workflow orchestration (LangGraph)

| ID | Pri | Requirement | Acceptance criteria |
|---|---|---|---|
| FR-001 | P0 | Typed shared state (`TypedDict`/Pydantic): messages, user_profile, retrieved_docs, market_data, portfolio, goal_params, agent_trace, error | State schema unit-tested; every node reads/writes only declared keys |
| FR-002 | P0 | Supervisor router node classifies each query to one or more agents using `gpt-4o-mini` with structured output | ≥ 90% accuracy on 40 labelled queries. **Claude authors the 40-query labelled set** (balanced across the 6 agents, plus compound and ambiguous cases); the author reviews and accepts the labels before it becomes the gate. Unknown intent falls back to the Q&A agent |
| FR-003 | P0 | Composition: a compound query ("analyse my portfolio and tell me if it fits my 10-year goal") invokes agents in sequence with state hand-off | Integration test proves a 2-agent chain inside one turn |
| FR-004 | P0 | Conversation memory: last N turns plus a persistent user profile (risk appetite, horizon, knowledge level) in state | Follow-up "what about the second one?" resolves correctly; 5-turn test passes |
| FR-005 | P0 | Fallback/error node: any agent exception or LLM timeout routes to a graceful degraded answer, never a stack trace | Fault-injection test per agent; user-visible message is friendly and the error is logged |
| FR-006 | P0 | Compliance node runs last on every path: injects the disclaimer, blocks banned phrases | No response can reach the UI without passing it; banned-phrase test suite green |
| FR-007 | P1 | Agent trace recorded in state and renderable (which nodes ran, in what order, with latency) | Trace visible in a UI expander and in the demo video |

### 6.2 Agents

| ID | Pri | Agent | Requirement & acceptance criteria |
|---|---|---|---|
| FR-010 | P0 | **Finance Q&A** | RAG-grounded answers with ≥ 1 citation; refuses when top-k relevance is below threshold; beginner reading level |
| FR-011 | P0 | **Market Analysis** | Live quote, % change, and 30/90-day trend for NSE/BSE tickers plus NIFTY 50 / SENSEX indices; *interprets* (what a 2% drop does and does not mean), never predicts; a non-Indian ticker returns a clear out-of-scope message |
| FR-012 | P0 | **Portfolio Analysis** | Accepts holdings; returns total value, allocation %, asset-class breakdown, concentration + diversification score, expense-ratio note, risk band; every metric a pure, hand-fixture-tested function |
| FR-013 | P0 | **Goal Planning** | Goal amount + horizon + risk appetite → required monthly SIP, compound projection, inflation-adjusted target, allocation template; math unit-tested against hand calculations |
| FR-014 | P1 | **News Synthesizer** | Fetches recent headlines for a ticker or theme, summarises in ≤ 5 bullets with source links, flags sentiment as uncertain |
| FR-015 | P1 | **Tax Education** | India only: STCG/LTCG on equity and debt, Section 80C, ELSS lock-in, NPS (80CCD), indexation status post-2023, dividend taxation, old vs new regime at a high level. Explains rules with the assessment year stated, never computes a user's tax liability |
| FR-016 | P0 | **BaseAgent** abstraction | Shared contract: name, description, `run(state) -> state`, prompt template, tool list, error wrapping, logging. Every agent subclasses it; no duplicated plumbing |

### 6.3 RAG subsystem *(partially built)*

| ID | Pri | Requirement | Acceptance criteria |
|---|---|---|---|
| FR-020 | P0 | **Knowledge base rebuild.** ≥ 100 freshly sourced Indian-context articles from reputable sources, replacing reliance on Varsity chapter dumps. Required sources: SEBI investor education, AMFI, RBI, NPS Trust, Income Tax Dept, Zerodha Varsity, Cleartax/Groww/ET Money explainers. Each article carries a **real descriptive title** (never "Chapter 1"), plus `source`, `url`, `category`, `date_retrieved` | `scripts/build_index.py` reports ≥ 100 docs; every doc has a human-readable title; no article assumes a US instrument or US tax rule |
| FR-020a | P0 | **Balanced category coverage** — no category below 6 articles. Current KB is lopsided (stocks 36, tax 8, insurance 2, investing 2, personal-finance 3), which is the root cause of weak real-world answers | Per-category count table in README; each of the ≥ 10 categories ≥ 6 articles; the thin categories (tax, insurance, personal-finance, fixed-income, basics) brought to parity first |
| FR-020b | P1 | **Retire the `category_map` workaround.** `config.yaml` currently remaps bonds→basics, etfs→basics, mutual-funds→retirement, diversification→retirement to make evals pass. Once the KB is rebuilt, categories must be real | `category_map` is empty or removed; retrieval filters on true categories; eval queries pass without remapping |
| FR-021 | P0 | Chunking + embedding (`all-MiniLM-L6-v2`, 384-dim) into ChromaDB with metadata | *Built* — `src/rag/chunker.py`, `embedder.py`, `vector_store.py` |
| FR-022 | P0 | Retrieval with category filtering and a relevance threshold | *Built* — `src/rag/retriever.py`; results in `data/eval_retrieval_results_*.json` |
| FR-023 | P0 | Source attribution rendered in every answer | *Built* — `src/rag/prompt.py`, `chain.py`; verified in the generation eval |
| FR-024 | P1 | Eval harness: retrieval, generation, adversarial | *Built* — `scripts/eval_*.py`; expand `eval_queries.json` to ≥ 30 queries |
| FR-025 | P0 | **Re-index and re-evaluate after the KB rebuild.** Full re-embed (one batched pass, ~$0.01), then re-run all three evals and commit the before/after comparison | Post-rebuild retrieval hit@3 ≥ 0.85 **on a query set written independently of the KB** (not reverse-engineered from the articles); before/after table in DESIGN.md |
| FR-026 | P1 | **Beginner-realism query set.** The existing 25 eval queries were written against Varsity content, which inflates scores (current hit_rate 0.92–1.0, groundedness 5/5, yet real answers disappoint). Add ≥ 15 queries phrased the way the beginner persona (§5, P1) would actually ask ("how much should I put in a SIP every month?", "is PPF better than ELSS?") | New queries live in `eval_queries.json` tagged `realistic`; scored separately so the honest number is visible, not averaged away |

### 6.4 Market data layer

| ID | Pri | Requirement | Acceptance criteria |
|---|---|---|---|
| FR-030 | P0 | yfinance primary for quotes and history; `.NS`/`.BO` suffix resolution; index symbols (`^NSEI`, `^BSESN`); symbol normalisation and validation against an Indian-ticker allowlist | Unit tests with a fake price feed; `RELIANCE` resolves to `RELIANCE.NS`; `AAPL` is rejected as out of scope |
| FR-031 | P0 | Cache with 30-minute TTL, keyed by symbol + field | Cache-hit test: the second call issues no network request |
| FR-032 | P0 | Rate limiting, exponential-backoff retry, Alpha Vantage fallback, then stale cache, then mock data | Fault-injection tests for 429, timeout, and total outage |
| FR-033 | P1 | Data freshness indicator surfaced to the user ("as of HH:MM, cached") | Visible in the Market tab and in agent responses |

### 6.5 Web interface

| ID | Pri | Requirement | Acceptance criteria |
|---|---|---|---|
| FR-060 | P0 | Four tabs: Chat, Portfolio, Market, Goals | All four functional in the deployed app |
| FR-061 | P0 | Chat: streaming response, turn history, agent-trace expander, persistent disclaimer banner | 5-turn context test; disclaimer always visible |
| FR-062 | P0 | Portfolio input: CSV upload, manual entry, and a one-click sample portfolio | A malformed CSV produces a specific, friendly error |
| FR-063 | P0 | Visualisations (Plotly): allocation pie, asset-class bar, price trend line, goal projection area | Every chart titled, axis-labelled, INR-formatted |
| FR-064 | P1 | Sidebar user profile: risk appetite, horizon, knowledge level — feeds `user_profile` in state | Changing risk appetite demonstrably changes Goal agent output |

### 6.5a Streamlit layout specification

The author has no UI design background, and the rubric requires Streamlit, so the layout is specified here rather than improvised. Streamlit constrains layout to a vertical flow of `st.columns`, `st.tabs`, `st.sidebar` and `st.expander` — which is a gift: there are few decisions to get wrong. Rule for every tab: **one primary thing, supporting detail below it.**

```
┌─ SIDEBAR (persistent) ────────┐  ┌─ MAIN ─────────────────────────────────┐
│ Finnie logo + tagline         │  │ [ Chat ] [ Portfolio ] [ Market ] [ Goals ]
│ ─────────────────             │  │
│ Your profile                  │  │  ⚠ Educational information only — not
│  Risk appetite  ○○●  moderate │  │    financial advice.          (always on)
│  Horizon        [ 10 ] years  │  │
│  Knowledge      ( beginner ▾) │  │  ── tab body ──
│ ─────────────────             │  │
│ Session                       │  │
│  Tokens used:  12,480         │  │
│  Est. cost:    $0.08          │  │
│  [ Clear conversation ]       │  │
└───────────────────────────────┘  └────────────────────────────────────────┘
```

| Tab | Primary element | Supporting detail |
|---|---|---|
| **Chat** | `st.chat_message` history + `st.chat_input` pinned at the bottom, response streamed | Per-answer: `st.expander("Sources")` listing cited articles with links; `st.expander("How I answered this")` showing the agent trace (nodes, order, latency) |
| **Portfolio** | Allocation pie, full width | Above it: three `st.columns` of `st.metric` (total value, day change, diversification score). Below: holdings `st.dataframe`, then asset-class bar chart, then the narration paragraph. Input via `st.file_uploader` + `st.data_editor` for manual entry + a "Load sample portfolio" button |
| **Market** | Price trend line for the selected ticker | Ticker `st.selectbox` (NIFTY 50, SENSEX + the holdings) above; `st.metric` row for price / change / % change; freshness caption ("as of 14:32 IST · cached"); interpretation paragraph below |
| **Goals** | Goal projection area chart (corpus vs years) | Inputs in three columns: target amount, horizon, current savings. Below: `st.metric` for required monthly SIP, then the inflation-adjusted target, then the allocation template table |

Visual rules: one accent colour and one warning colour only; INR formatted with the Indian digit grouping (`₹12,50,000`, not `₹1,250,000`); every chart titled and axis-labelled; no chart relies on colour alone to carry meaning (NFR-07).

### 6.6 Quality, docs, delivery

| ID | Pri | Requirement | Acceptance criteria |
|---|---|---|---|
| FR-070 | P1 | Test suite ≥ 80% coverage: per-agent unit tests, router accuracy test, graph integration tests, fault injection, compliance suite. Offline-deterministic via `FakeListChatModel` + fake price feed | `pytest --cov` ≥ 80%; runnable with no API key |
| FR-071 | P1 | README (architecture, setup, API, usage, troubleshooting) plus `docs/DESIGN.md` (architecture decisions, agent protocol, RAG details, performance) and Mermaid diagrams | Fresh clone to running app in ≤ 5 commands, verified on a clean machine |
| FR-072 | P0 | Demo video 5–10 min: multi-turn chat across agents, portfolio analysis, live market data, goal planning, agent trace. **Recorded complete on Day 6 without MCP** (the safety take), with an optional MCP segment appended on Day 7 | Linked in README; a submittable video exists from the end of Nov 14 onward |
| FR-073 | P1 | `Dockerfile` + `docker-compose.yml`; deployed to Streamlit Cloud with secrets via the dashboard | Public URL in README; `docker run` serves the app |
| FR-074 | P2 | MCP server exposing ≥ 3 tools (quote lookup, portfolio metrics, KB search) to Claude Desktop. Attempted last, 3-hour time box, only after FR-072's video is recorded | Tools callable from Claude Desktop; config documented; a short demo segment appended to the video. On failure: abandoned with no impact on any other deliverable |
| FR-075 | P2 | Innovation: agent-trace visualiser, RAG eval dashboard tab, adversarial compliance suite, cost meter in the UI | Each visible in the demo video |

### 6.7 Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-01 | Response latency, simple Q&A | p50 < 4 s, p95 < 8 s |
| NFR-02 | Cost per conversation | < $0.02 average (router on `gpt-4o-mini`, cached market data) |
| NFR-02a | **Token budget discipline** — the API key is a provided allowance of unknown size, so it is treated as scarce | Every test runs on `FakeListChatModel` (zero spend); `gpt-4o-mini` for routing and all eval grading; embeddings batched so a re-index is one pass; generation evals run on a 25-query subset, not the full set, and only after a KB change; the live cost meter is checked daily and reported in the README; no agent prompt exceeds 1200 output tokens (`llm.max_tokens`) |
| NFR-03 | Secret hygiene | `.env` only, gitignored; `.env.example` committed with placeholders; no secret ever logged |
| NFR-04 | Observability | Structured logging per node: agent name, latency, token count, cache hit/miss |
| NFR-05 | Graceful degradation | No unhandled exception reaches the UI under any fault-injection test |
| NFR-06 | Reproducibility | `requirements.lock.txt` pinned; tests pass offline with no API key |
| NFR-07 | Accessibility | Beginner reading level; every chart labelled; no colour-only encoding |

---

## 7. Architecture

### 7.1 Target system

```
User ──> Streamlit UI (4 tabs, session_state)
             │
             ▼
     LangGraph StateGraph
             │
      ┌──────┴───────┐
      │  Supervisor  │  gpt-4o-mini, structured intent classification
      └──────┬───────┘
             │ routes / composes
   ┌─────┬─────┬─────┬─────┬─────┐
   ▼     ▼     ▼     ▼     ▼     ▼
  Q&A  Market Portfolio Goal  News  Tax      <- all subclass BaseAgent
   │     │       │      │      │     │
   ▼     ▼       ▼      ▼      ▼     ▼
 RAG   Market   Pure   Projection News  RAG
(Chroma) data   metric   math     feed (tax cat.)
         layer  funcs
             │
             ▼
      Compliance node  (disclaimer + banned-phrase guard, unskippable)
             │
             ▼
        Response + agent trace + citations
```

### 7.2 Locked technology decisions (and the defence for each)

| Layer | Choice | Why this, not the alternative |
|---|---|---|
| Orchestration | LangGraph `StateGraph` | Explicit, inspectable, testable state machine; CrewAI hides routing behind role-play, which is harder to unit-test and harder to defend |
| LLM | `gpt-4o` reasoning / `gpt-4o-mini` routing | Reliable structured outputs; model tiering cuts cost roughly 10x on the highest-frequency call |
| Embeddings | `text-embedding-3-small` at 512-dim (matryoshka reduction) | **Correction to earlier notes:** `CLAUDE.md` claims local `all-MiniLM-L6-v2`, but `config.yaml` actually uses OpenAI `text-embedding-3-small` truncated to 512-dim — 67% smaller index for under 5% quality loss. It is an API call, but a trivially cheap one: re-embedding the whole 100-article KB costs roughly $0.01. Defence for the 512-dim choice: matryoshka embeddings degrade gracefully when truncated, unlike a naive dimensional cut |
| Vector store | ChromaDB | Stores vectors and metadata together, enabling category-filtered retrieval; FAISS needs a parallel metadata dict |
| Market data | yfinance primary, Alpha Vantage fallback | yfinance is free and covers NSE/BSE; Alpha Vantage's hard rate limit is the realistic place to demonstrate backoff engineering |
| UI | Streamlit | Named in the rubric; `session_state` is a sufficient memory substrate for a single-session app |
| Tests | pytest + `FakeListChatModel` + fake price feed | Deterministic and offline — a grader with no API key can still run the suite |

### 7.3 Current state of the repo (verified 2026-11-08)

| Status | Component |
|---|---|
| Done | Phase 0 env/skeleton · Phase 1 config + LLM client (rate limiter, cost meter) + compliance guard · Phase 2 KB (14 categories seeded, Varsity PDFs extracted) · Phase 3 RAG pipeline (chunker, embedder, Chroma store, retriever, prompt, chain) with 3 eval harnesses and results |
| Empty | `src/agents/` · `src/workflow/` · `src/web_app/` · `src/data/` |
| Gaps | Tests cover only config + compliance (25 tests) · no Dockerfile · no DESIGN.md · single git commit with substantial uncommitted work in the tree |
| Defects found | **KB coverage is lopsided** — 263 files, but stocks 36 / bonds 30 / etfs 30 vs tax 8, risk 16, personal-finance 3, insurance 2, fixed-income 2, investing 2 · **titles are useless** (`title: "Chapter 1"`), so citations tell the reader nothing · **`config.yaml` ships US default tickers** (AAPL, MSFT, GOOGL, AMZN, NVDA) — must become NIFTY/SENSEX and Indian equities · **`category_map` masks a real mismatch** by remapping four categories at eval time · **`CLAUDE.md` is wrong twice**: claims Phase 2 is next (RAG already landed) and claims local MiniLM embeddings (config uses `text-embedding-3-small` @ 512-dim) |

### 7.4 Why RAG answers disappoint despite strong eval numbers

The metrics look excellent — retrieval hit_rate 0.92 (vector) / 1.00 (MMR), MRR 0.92, groundedness 5.0/5, relevance 4.88/5 — yet real answers underwhelm. That gap is the finding, not a contradiction, and it has four causes:

1. **The eval set is reverse-engineered from the corpus.** All 25 queries were written against Varsity chapters already in the index, so they measure "can it find the chunk I was thinking of", not "can it answer what a beginner asks". ROUGE-L of 0.168 is the tell: answers barely resemble the reference answers even while scoring 5/5 on groundedness. Fixed by FR-026.
2. **Corpus/intent mismatch.** Varsity's strength is technical and fundamental analysis; the beginner persona (§5, P1) asks about SIPs, PPF vs ELSS, emergency funds, and term insurance. Those categories are exactly the thin ones (2–8 articles). Fixed by FR-020 and FR-020a.
3. **Provenance is unreadable.** Every citation renders as "Chapter 1", which makes a correct, grounded answer *feel* untrustworthy. Trust is a stated product requirement (§2.1), so this is a defect, not cosmetics. Fixed by FR-020.
4. **Chapter-sized documents chunk poorly.** 500-token chunks cut from long chapters lose their surrounding context, which shows up as `completeness` dipping to 3/5 on the weakest queries while groundedness stays at 5. Mitigated by shorter, single-topic source articles; revisit chunk size only if it persists after the rebuild.

**Conclusion:** the retrieval *mechanics* are sound — keep the chunker, embedder, store and MMR as built. The *corpus* is the problem. Rebuild the content, not the pipeline, then re-measure honestly against queries the corpus has never seen.

---

## 8. Implementation Phases (7 days, dependency-ordered)

Each day ends with something runnable and a grill on that day's concepts. Phase numbering follows `docs/ROADMAP.html`.

| Day | Date | Phases | Deliverable | Rubric pts in play |
|---|---|---|---|---|
| **0** | Nov 8 | Housekeeping + **KB rebuild** + Phase 4 | Commit the RAG work; fix `CLAUDE.md` and `config.yaml` (Indian default tickers, embedding model note); source 100+ Indian articles, re-index, re-eval (FR-020 → FR-026); `BaseAgent` abstraction with tests | 8 + 5 |
| **1** | Nov 9 | Phase 5 + Phase 6 | Finance Q&A Agent (RAG-wired); market data layer (cache, backoff, fallback) + Market Analysis Agent | 10 + 7 + 5 |
| **2** | Nov 10 | Phase 7 | Portfolio Analysis Agent: schema, pure metric functions, hand-fixture tests, narration prompt | 7 |
| **3** | Nov 11 | Phase 8 + Phase 9 | Goal Planning Agent (SIP/compound/inflation math, 6% India inflation default); News Synthesizer; Tax Education Agent (Indian tax rules) — **all six agents complete** | 10 (agents) |
| **4** | Nov 12 | Phase 10 | **LangGraph workflow**: state schema, supervisor router (+ the 40-query labelled set for review), composition, memory, fallback, compliance node, trace | 10 + 8 |
| **5** | Nov 13 | Phase 11 | Streamlit 4-tab app per §6.5a, Plotly visualisations, sidebar profile, streaming chat, trace expander; skeleton deploy to Streamlit Cloud | 10 + 7 |
| **6** | Nov 14 | Phase 12 + **safety take** | Tests to ≥ 80%, README + DESIGN.md + Mermaid diagrams, Dockerfile, production deploy. **Record a complete demo video without MCP** — the mandatory deliverable, banked early | 5 + 5 + 5 |
| **7** | Nov 15 | Phase 13 *(time-boxed)* | **MCP attempt, hard stop at 3 hours.** If it works: record a short MCP segment and append it, or re-record the walkthrough. If it does not: abandon it, the Day 6 video stands, submit. Then eval dashboard / trace visualiser with whatever time is left, and submit | 15 bonus |

**Hard ordering constraints.** FR-016 (BaseAgent) precedes every agent. All agents precede FR-001–FR-007 (the graph wires them). The graph precedes the UI (the UI renders state). Everything precedes the demo video. **Day 6 is non-negotiable** — documentation and the video are 10 guaranteed points that bonus work must never displace.

**Committed scope:** all six agents, from 6–10 hours/day. This targets the rubric's top band, which asks for all six with sophisticated inter-agent communication.

**MCP is last and time-boxed, by the author's decision.** It sits at the very end with a 3-hour hard stop on Nov 15, attempted *before* the video is final so a working server can be showcased. The protection against it eating the deadline is the **Day 6 safety take**: a complete demo video is recorded and banked on Nov 14 with no MCP in it. MCP then either earns a short appended segment or gets dropped silently — and either way the mandatory 5-point deliverable is already in hand. Never start MCP before the Day 6 video exists.

**Cut list if a day slips** (sacrifice in this order): MCP server → eval dashboard → trace visualiser → the 90% coverage target (hold the line at 80%) → News Synthesizer → Tax Education. Never cut: the graph, the four tabs, the rebuilt KB, the demo video, the README.

---

## 9. Risks & Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | **7 days is tight for 10 phases.** Scope collapse near the deadline | High | Severe | Strict cut list (§8); Day 6 docs/video fixed and immovable; every day ends runnable, so any day is a submittable state |
| R2 | **Alpha Vantage NSE/BSE coverage is patchy**, so the designated fallback may not cover an Indian symbol | Medium | Moderate | Treat Alpha Vantage as a best-effort third layer, not a guarantee; stale cache and labelled mock data are the real safety net (R5). Document the limitation in DESIGN.md rather than hiding it — it is a defensible engineering answer |
| R3 | **Router misclassification** makes the multi-agent system look broken in the demo | Medium | High | 40-query labelled test set as a gate; structured output with an enum; unknown routes to Q&A; trace exposed so routing is visible rather than magic |
| R4 | **OpenAI cost and rate limits** during development and the demo | Medium | Moderate | `gpt-4o-mini` for routing; `InMemoryRateLimiter` + cost meter already built; tests run on `FakeListChatModel` with zero spend |
| R5 | **Market API failure during grading** | Medium | High | Four-layer degradation: live → cache → stale cache → mock, with a freshness label. Fault-injected in tests so the demo survives an outage |
| R6 | **Streamlit Cloud deploy fails late** (secrets, memory, Chroma on ephemeral disk) | Medium | Moderate | Deploy a skeleton on Day 5 before the app is finished; ship the prebuilt Chroma index in the repo; Docker is the fallback proof |
| R7 | **Test coverage misses 80%** | Medium | Moderate | Write tests with each phase, not at the end; pure metric functions are cheap coverage; check coverage daily |
| R8 | **Compliance leak** — an agent emits advice-shaped text | Low | Severe | Compliance node is terminal on every path and cannot be bypassed; the adversarial prompt suite already exists (`eval_adversarial`) and expands per agent |
| R9 | **Interview readiness sacrificed to shipping speed** | High | Severe *(personal)* | The grill at every phase boundary is a deliverable, not a nice-to-have; `LEARNING_NOTES.html` updated the same day the code lands |
| R10 | **Repo looks thin to recruiters** despite good code — one commit, no history | Medium | Moderate | Commit per phase with meaningful messages; README leads with the architecture diagram and the live demo link |
| R11 | **API allowance is of unknown size** and was provided, not purchased — running dry mid-build would halt everything | Medium | Severe | NFR-02a budget discipline: zero-spend tests, `gpt-4o-mini` for routing and eval grading, batched one-pass embedding, generation evals only after a KB change. Check the cost meter daily and log the running total in the README. If the key dies, `FakeListChatModel` keeps the entire test suite and most of the UI demonstrable |
| R12 | **Scraped KB articles carry licensing and accuracy risk** | Medium | Moderate | Prefer regulator and industry-body sources (SEBI, AMFI, RBI, NPS Trust, Income Tax Dept) whose investor-education material is meant for reuse; store a summary with attribution and `url`, never a verbatim copy; record `date_retrieved` so tax rules can be re-checked against the assessment year |

---

## 10. Open Assumptions

Flagged rather than blocking; correct any that are wrong:

1. **6–10 focused hours/day** available Nov 8–15 (confirmed). This is what makes all six agents and the MCP server committed scope rather than stretch goals.
2. Portfolio input accepts CSV upload *and* manual entry; a sample portfolio ships for evaluators who have neither.
3. News data comes from yfinance's news field or an RSS feed — no paid news API.
4. The Varsity PDFs already in `docs/` are a licit source for KB content when summarised with attribution, not reproduced verbatim.
5. Submission is a GitHub repo link plus the demo video; no live presentation.
6. The existing single-commit history can be built on; no repo rewrite needed.

---

## 11. Interview-Prep Appendix (post-build phase)

The second half of this engagement. For each subsystem the author must be able to answer, unprompted:

- **Multi-agent:** Why a supervisor rather than a swarm? When does routing beat one large prompt? How do you test a non-deterministic router?
- **LangGraph:** What is in your state and why? Where do cycles appear? How does this differ from a chain, from CrewAI, from a plain while-loop?
- **RAG:** Chunk size and overlap — why those numbers? What is hit@k and what did yours measure? When is fine-tuning the right call instead?
- **Embeddings:** Why 384-dim local over `text-embedding-3-small`? What does cosine similarity actually measure?
- **Resilience:** Walk through all four degradation layers of the market feed. What is exponential backoff with jitter, and why jitter?
- **Cost and scale:** Where does this break at 10k users? Which call dominates cost? What do you cache, and what must you never cache?
- **Compliance:** How do you prove no response bypasses the guard? What is your adversarial test strategy?
- **Testing:** How do you make an LLM system deterministic in CI?

---

## Self-Score (100-point PRD framework)

| Dimension | Max | Score | Note |
|---|---|---|---|
| AI-Specific Optimization | 25 | 24 | Sequential dependency-ordered phases, 11 explicit non-goals, structured FR tables, cut list for graceful degradation |
| Traditional PRD Core | 25 | 24 | Quantified pain points per segment, 3 specific personas with failure conditions, SMART goals with metrics |
| Implementation Clarity | 30 | 30 | 46 FRs with IDs, priorities and acceptance criteria; 8 NFRs; architecture diagram; Streamlit layout spec (§6.5a); decision defences; day-level phasing |
| Completeness | 20 | 20 | 12 risks with mitigations, hard ordering constraints, open assumptions, rubric traceability matrix, a root-cause analysis of the RAG quality gap (§7.4), interview appendix |
| **Total** | **100** | **98** | |

Remaining deduction: no formal input/output contract per agent (deferred to `docs/DESIGN.md` on Day 6).

**Adversarial review:** self-adversarial pass applied (single-provider session — no second provider available to dispatch to). Challenges raised and resolved: *"7 days cannot deliver 10 phases"* → explicit cut list plus the every-day-runnable rule (R1); *"supporting two markets is scope creep"* → scope narrowed to India only, enforced by an out-of-scope response for foreign tickers (§4.11, FR-030); *"a broken router makes the whole thesis look fake"* → 90% accuracy gate plus visible trace (R3); *"Streamlit Cloud will fail on the last day"* → deploy a skeleton on Day 5, Docker as fallback (R6); *"bonus work will eat the documentation day"* → Day 6 declared immovable (§8).

---
*PRD v1.2 · 2026-11-08 · India-only scope; all six agents committed; MCP last and time-boxed behind a Day 6 safety-take video; KB rebuild and RAG root-cause analysis*
*Sources: Problem Statement.docx, Project Milestones.docx, Grading Rubric.xlsx, docs/ROADMAP.html, verified repo state and eval results*
