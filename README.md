# Finnie — AI Finance Assistant

A multi-agent conversational assistant for financial education. Built for the
Applied Agentic AI capstone.

> **Educational use only.** Finnie explains financial concepts. It does not give
> financial advice and cannot know your circumstances.

## Status

Phase 0 — skeleton. Nothing works yet.

## Stack

| Layer | Choice |
|---|---|
| Orchestration | LangGraph (`StateGraph`) |
| LLM | GPT-4o, `gpt-4o-mini` for routing |
| Embeddings | `all-MiniLM-L6-v2`, local |
| Vector store | FAISS (`IndexFlatIP`) |
| Market data | yfinance, Alpha Vantage fallback |
| UI | Streamlit |

## Setup

```bash
python -m venv .venv
source .venv/Scripts/activate        # Windows bash; use .venv\Scripts\activate on cmd/PowerShell
pip install -r requirements.txt
cp .env.example .env                 # then paste your OPENAI_API_KEY into .env
pytest -v
```

Always run commands from this directory. `pyproject.toml` sets `pythonpath = ["."]`,
which is what makes `from src.core.config import ...` resolve.

## Layout

```
ai_finance_assistant/
├── src/
│   ├── agents/      one module per specialised agent + the shared base class
│   ├── core/        config, LLM client, compliance — no domain logic
│   ├── data/        market data access and caching
│   ├── rag/         chunking, embedding, FAISS index, retrieval
│   ├── web_app/     Streamlit UI
│   ├── utils/       small shared helpers
│   └── workflow/    LangGraph state, router, graph assembly
├── tests/
├── scripts/         one-shot CLI tasks (index building, etc.)
├── data/
│   ├── knowledge_base/  curated articles (source, committed)
│   ├── indexes/         FAISS artifacts (generated, gitignored)
│   └── cache/           market data cache (generated, gitignored)
├── config.yaml      all behavioural settings
└── pyproject.toml   pytest, coverage and ruff configuration
```

## Project documents

- [`docs/ROADMAP.html`](docs/ROADMAP.html) — the 14-phase build plan, with per-phase
  checklists, acceptance criteria and rubric mapping.
- [`docs/LEARNING_NOTES.html`](docs/LEARNING_NOTES.html) — every concept behind the
  build, with the interview questions for each.

Open either one in a browser.
