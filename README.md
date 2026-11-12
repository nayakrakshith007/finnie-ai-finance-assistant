# Finnie — AI Finance Assistant

A production-grade multi-agent conversational assistant for Indian personal finance education. Built as an Applied Agentic AI capstone — every design decision is documented and defensible in an interview.

> **Educational use only.** Finnie explains financial concepts for Indian investors. It never recommends a specific trade and cannot know your full circumstances.

---

## What it does

| Capability | Agent | Description |
|---|---|---|
| Finance Q&A | `finance_qa` | Explains SIPs, PPF, ELSS, NPS, expense ratios, and other Indian instruments using a RAG pipeline over a curated 2,000-chunk knowledge base |
| Market data | `market_analysis` | Live quotes and 30-day trends for NSE/BSE stocks and indices (NIFTY, SENSEX) via yfinance |
| Stock deep dive | `stock_deep_dive` | P/E ratio, RSI, analyst consensus and 6-month price chart for a named stock |
| Portfolio analysis | `portfolio_analysis` | Total value, P&L, asset allocation, HHI concentration score, and fee exposure across your holdings |
| Goal planning | `goal_planning` | SIP calculator — how much to invest monthly to reach any amount in any horizon, with inflation adjustment |
| Tax education | `tax_education` | LTCG/STCG rates (post-July 2024), 80C deductions, old vs new regime, debt fund rules — updated for the current assessment year |
| News synthesis | `news_synthesizer` | Latest headlines for a company or theme, summarised with key takeaways |

---

## Architecture

```
User question
      │
      ▼
┌─────────────┐    structured output    ┌─────────────────────┐
│  Supervisor │ ──────────────────────► │  Agent registry     │
│  (router)   │  route: [agent1, ...]   │  7 agents, max 2/turn│
└─────────────┘                         └─────────────────────┘
      │
      ▼  (up to 2 agents, in order)
┌──────────────────────────────────────────┐
│  Agent 1  →  Agent 2  →  Compliance node │
│  (parallel-capable, LangGraph StateGraph)│
└──────────────────────────────────────────┘
      │
      ▼
  Answer + trace + sources → Streamlit UI
```

**Key design decisions (interview-ready):**

- **LangGraph `StateGraph`** — explicit, inspectable, testable. The graph's execution order is derived from `agent_trace`, not a counter, so composition (FR-003) falls out of the same wiring as a single-agent turn with no special case.
- **Supervisor does two jobs in one LLM call** — it picks the route *and* rewrites the user's question to stand alone ("What about the second one?" → "What is the TCS price?"), so agents receive a self-contained question at zero extra cost.
- **Structured output constrains shape, not values** — the router validates every agent name against the registry, collapses duplicates, caps the route at 2, and falls back to `finance_qa`. A route decides what code runs next; it is the last place to trust a model's output blindly.
- **RAG with MMR retrieval** — Maximal Marginal Relevance over 2,000 chunks (OpenAI `text-embedding-3-small` at 512-dim Matryoshka truncation). Realistic-query eval: 1.00 hit rate, 1.00 MRR, 0.85 P@4.
- **Compliance as a terminal graph node** — the disclaimer is appended exactly once by the graph, never by agents or the UI.

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| Orchestration | LangGraph `StateGraph` | Highest-weighted rubric item; explicit, inspectable, testable |
| LLM | GPT-4o (agents), `gpt-4o-mini` (router) | Reliable structured outputs; model tiering controls cost |
| Embeddings | OpenAI `text-embedding-3-small` @ 512-dim | Matryoshka truncation: 67% smaller index for <5% quality loss |
| Vector store | ChromaDB | Vectors + metadata in one store; simpler than FAISS + sidecar dict |
| Market data | yfinance (primary), Alpha Vantage (fallback) | yfinance free; Alpha Vantage teaches real rate-limit engineering |
| UI | Streamlit | Named in rubric; `session_state` handles conversation memory |
| Tests | pytest + pytest-cov | FakeLLM + fake price feed = deterministic, offline |

---

## Test coverage

| Metric | Value |
|---|---|
| Tests | **612 passing** |
| Test scope | agents, RAG, router (structural), portfolio, goals, tax, UI session |
| Router gate | **91.1% strict accuracy** on 45 labelled queries (gate: ≥ 90%) |
| Retrieval quality | Realistic-query eval: hit@1 = 1.00, MRR = 1.00, P@4 = 0.85 |

---

## Setup

```bash
# 1. Clone and enter the project directory
cd ai_finance_assistant

# 2. Create virtual environment
python -m venv .venv

# 3. Activate
source .venv/Scripts/activate        # Windows Git Bash
# .venv\Scripts\activate             # Windows cmd/PowerShell

# 4. Install dependencies
pip install -r requirements.txt

# 5. Configure secrets
cp .env.example .env
# Open .env and paste your OPENAI_API_KEY

# 6. Build the knowledge-base index (one-time, ~$0.01)
python scripts/build_index.py

# 7. Run tests
pytest -v

# 8. Launch the app
streamlit run app.py
```

The app opens at **http://localhost:8501**. Create an account on the signup tab; your conversation history is saved across sessions.

---

## Project layout

```
ai_finance_assistant/
├── app.py                      Streamlit entry point
├── config.yaml                 All behavioural settings (single source of truth)
├── src/
│   ├── agents/
│   │   ├── base.py             Template-method base: timing, tracing, error boundary
│   │   ├── qa.py               Finance Q&A — RAG over knowledge base
│   │   ├── market.py           Market analysis — quotes and trends
│   │   ├── stock.py            Stock deep dive — P/E, RSI, analyst outlook
│   │   ├── portfolio.py        Portfolio analysis — value, P&L, allocation
│   │   ├── goal.py             Goal planning — SIP calculator
│   │   ├── news.py             News synthesis — yfinance headlines
│   │   └── tax.py              Tax education — subclasses FinanceQAAgent
│   ├── core/
│   │   ├── config.py           Pydantic config schema
│   │   ├── llm.py              LLM client + cost-meter callback
│   │   └── compliance.py       Disclaimer injection (terminal graph node only)
│   ├── data/
│   │   ├── market.py           4-tier degradation: live → fresh cache → stale → mock
│   │   └── news.py             yfinance news parser (handles both payload shapes)
│   ├── portfolio/
│   │   ├── metrics.py          Pure-arithmetic P&L, HHI, diversification score
│   │   ├── holdings.py         Input validation — collects errors, never raises
│   │   └── analysis.py         Assembles the analysis dict from holdings + prices
│   ├── goals/
│   │   └── projections.py      Annuity-due SIP formula with inflation adjustment
│   ├── rag/
│   │   ├── chunker.py          Document → chunks with metadata
│   │   ├── embedder.py         OpenAI embeddings with retry
│   │   └── retriever.py        Chroma MMR retrieval
│   ├── web_app/
│   │   ├── session.py          State + the one run_turn() every tab calls
│   │   ├── charts.py           Pure Plotly builders (tested without Streamlit)
│   │   ├── auth.py             SQLite-backed user accounts + bcrypt passwords
│   │   └── tabs/               chat.py, portfolio.py, market.py, goals.py, news.py, tax.py
│   └── workflow/
│       ├── state.py            AgentState TypedDict with LangGraph reducers
│       ├── registry.py         AGENT_CLASSES tuple — single source of agent truth
│       ├── router.py           Supervisor: structured output → validated route
│       └── graph.py            build_production_graph() — the compiled StateGraph
├── tests/                      612 tests, all offline
├── scripts/
│   ├── build_index.py          Index the knowledge base into Chroma
│   └── eval_router.py          Measure routing accuracy (45 labelled queries)
└── data/
    ├── knowledge_base/         281 curated articles, 14 categories
    ├── router_queries.json     45 labelled routing queries (the FR-002 gate)
    └── router_eval_results.json  Latest eval run (91.1% strict, 93.3% lenient)
```

---

## Docs

- [`docs/PRD.md`](docs/PRD.md) — Product requirements: 46 FRs with acceptance criteria, rubric mapping, risks
- [`docs/DESIGN.md`](docs/DESIGN.md) — Architecture diagrams: system overview, agent flow, RAG pipeline, LangGraph graph
- [`docs/ROADMAP.html`](docs/ROADMAP.html) — 14-phase build plan with checklists
- [`docs/LEARNING_NOTES.html`](docs/LEARNING_NOTES.html) — Every concept taught, with interview questions

---

## Key constraints

- **India only** — INR, NSE/BSE, Indian instruments and Indian tax. A foreign ticker gets a clear out-of-scope reply.
- **Education, not advice** — no agent suggests a specific trade. Compliance node appends the disclaimer exactly once.
- **yfinance data** — prices come from Yahoo Finance (redistributed, ~15-min delayed). Fit for learning, not trading.
- **Secrets in `.env` only** — `.env` is gitignored; `.env.example` is committed and never contains a real key.
