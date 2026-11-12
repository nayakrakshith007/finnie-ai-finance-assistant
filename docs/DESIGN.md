# Finnie — Design Document

Architecture, data flow, and design decisions for the multi-agent finance assistant.

---

## 1. System Architecture

```mermaid
graph TB
    subgraph UI ["Streamlit UI (app.py)"]
        CT[💬 Chat tab]
        PT[📊 Portfolio tab]
        MT[📈 Market tab]
        GT[🎯 Goals tab]
        NT[📰 News tab]
        TT[🧾 Tax tab]
    end

    subgraph Session ["web_app/session.py"]
        RT[run_turn]
        SS[session state]
    end

    subgraph Graph ["LangGraph StateGraph"]
        SV[Supervisor\nrouter]
        A1[Agent 1]
        A2[Agent 2]
        CN[Compliance\nnode]
    end

    subgraph Agents ["src/agents/"]
        QA[finance_qa]
        MA[market_analysis]
        SD[stock_deep_dive]
        PA[portfolio_analysis]
        GP[goal_planning]
        NW[news_synthesizer]
        TX[tax_education]
    end

    subgraph Data ["Data sources"]
        KB[(Chroma\nknowledge base\n2000 chunks)]
        YF[yfinance\nNSE/BSE data]
        AV[Alpha Vantage\nfallback]
        DB[(SQLite\nuser accounts\n+ checkpoints)]
    end

    CT & PT & MT & GT & NT & TT --> RT
    RT --> SS
    SS --> Graph
    SV -->|route: [agent1]| A1
    SV -->|route: [agent1, agent2]| A1 --> A2
    A1 & A2 --> CN
    CN --> SS

    QA & TX -->|MMR retrieval| KB
    MA & SD & NW -->|quotes / news| YF
    YF -->|rate limit| AV
    PA -->|holdings + prices| YF
    GP -->|pure arithmetic| GP

    SS <-->|checkpointer| DB
    UI <-->|auth| DB
```

---

## 2. LangGraph Execution Flow

```mermaid
sequenceDiagram
    participant U as User
    participant S as Streamlit session
    participant SV as Supervisor (router)
    participant A1 as Agent 1
    participant A2 as Agent 2 (optional)
    participant C as Compliance node

    U->>S: "Analyse my portfolio and check if it fits my 10-year goal"
    S->>SV: AgentState{messages, user_profile, portfolio}
    SV->>SV: rewrite question (resolved_question)
    SV->>SV: pick route via structured output
    Note over SV: route = [portfolio_analysis, goal_planning]
    SV-->>A1: state with route

    A1->>A1: portfolio_analysis.handle()
    Note over A1: computes value, P&L, allocation
    A1-->>A2: state + trace entry

    A2->>A2: goal_planning.handle()
    Note over A2: SIP calc on inflation-adjusted target
    A2-->>C: state + trace entry

    C->>C: merge answers, append disclaimer
    C-->>S: final AgentState

    S-->>U: answer + trace + sources
```

---

## 3. Agent Router (Supervisor)

```mermaid
flowchart LR
    Q[User question] --> RW[Rewrite to\nstand alone]
    RW --> LLM[gpt-4o-mini\nstructured output]
    LLM --> VAL{Validate route}
    VAL -->|unknown agent| FB[Fallback:\nfinance_qa]
    VAL -->|> 2 agents| CAP[Cap at 2]
    VAL -->|duplicates| DD[Deduplicate]
    VAL -->|valid| R[route list]
    FB & CAP & DD & R --> EXEC[Execute agents\nin order]
```

The supervisor also **rewrites** the user's question before routing — "What about the second one?" becomes the full resolved question using conversation history. Agents receive the rewritten question via `BaseAgent._latest_question()`, which prefers `resolved_question` over the raw message.

**Router gate:** 91.1% strict accuracy on 45 labelled queries (FR-002 requires ≥ 90%).

---

## 4. RAG Pipeline

```mermaid
flowchart TB
    subgraph Indexing ["Index build (scripts/build_index.py)"]
        KA[281 knowledge-base\narticles] --> CH[Chunker\nchunk_size=800\noverlap=100]
        CH --> EM[OpenAI embeddings\ntext-embedding-3-small\n512-dim Matryoshka]
        EM --> CR[(Chroma collection\nfinnie_kb\n~2000 chunks)]
    end

    subgraph Retrieval ["Per-turn retrieval (rag/retriever.py)"]
        Q2[Resolved question] --> QE[Query embedding]
        QE --> MMR[MMR retrieval\ntop_k=4\nlambda=0.5]
        CR --> MMR
        MMR --> DC[Deduplicated\nchunks + metadata]
        DC --> PR[Prompt builder\n+ chain]
        PR --> ANS[Answer]
    end
```

**Why 512-dim Matryoshka?** OpenAI's `text-embedding-3-small` supports dimension truncation. At 512 dims (vs 1536 full): 67% smaller index, <5% quality loss on MTEB benchmarks, ~$0.01 per full re-index.

**Why MMR?** Maximal Marginal Relevance selects for relevance *and* diversity — it avoids returning 4 chunks from the same article for a broad question. `lambda=0.5` balances the two.

**Eval results:** Realistic-query set (15 queries written from a beginner's phrasing):
- Hit@1 = 1.00
- MRR = 1.00
- P@4 = 0.85

---

## 5. Portfolio Analysis Layer

```mermaid
flowchart LR
    subgraph Input ["User input"]
        CSV[CSV / manual\nholdings table]
    end

    subgraph Validation ["portfolio/holdings.py"]
        CSV --> IV[Input validation\ncollects errors\nnever raises]
        IV --> HOLD[Validated holdings\nlist of dicts]
    end

    subgraph Pricing ["data/market.py — 4-tier degradation"]
        HOLD --> L1[Live yfinance\nquote]
        L1 -->|fail| L2[Fresh cache\n< 15 min]
        L2 -->|fail| L3[Stale cache\nlabelled]
        L3 -->|no symbol| REJ[Rejected:\nno mock for\nunknown symbol]
        L3 -->|known| L4[Mock price\nlabelled]
    end

    subgraph Metrics ["portfolio/metrics.py — pure arithmetic"]
        L1 & L2 & L3 & L4 --> PM[Total value\nUnrealised P&L\nAsset allocation]
        PM --> HHI[HHI concentration]
        PM --> DS[Diversification score\ncomposite heuristic]
        PM --> RB[Risk band\nfrom asset-class weights]
    end
```

**Three design decisions to defend:**
- **HHI for concentration** — standard, citable metric. A simple holding count is blind to a 97% position.
- **Diversification score** — Finnie's own composite (evenness × breadth × class spread), documented as a heuristic. Pure evenness would score three equally-weighted IT stocks 100/100.
- **Risk band is structural** — derived from asset-class weights (equity %, debt %, gold %), not from volatility. Works on turn one with no price history and is explainable in a sentence.

---

## 6. State Reducers (LangGraph)

```mermaid
classDiagram
    class AgentState {
        messages: list[BaseMessage]
        user_profile: dict
        portfolio: dict
        agent_trace: list[TraceEntry]
        retrieved_docs: list
        market_data: dict
        route: list[str]
        resolved_question: str
        error: str | None
    }

    class Reducers {
        messages → add_messages (append, deduplicate)
        agent_trace → operator.add (append only)
        all others → last-write-wins
    }

    AgentState --> Reducers : governed by
```

`add_messages` is LangGraph's built-in reducer — it appends new messages and allows removal via `RemoveMessage`. The compliance node uses this to merge two AI messages from a compound turn into one, then removes the superseded intermediate.

---

## 7. Streamlit Session Architecture

```mermaid
flowchart TB
    subgraph SS ["st.session_state"]
        GS[graph_state\nwhat agents read]
        UI[ui_messages\nwhat Chat tab renders]
        TC[turn_count]
        TL[total_latency]
    end

    subgraph Tabs ["Tabs (all call run_turn)"]
        CT2[Chat tab]
        PT2[Portfolio tab]
        MT2[Market tab]
        GT2[Goals tab]
    end

    subgraph Auth ["SQLite checkpointer"]
        CP[Conversation history\nper user_id thread]
    end

    CT2 & PT2 & MT2 & GT2 -->|run_turn| SS
    SS <-->|authenticated path| CP
    SS -->|anonymous path| SS
```

**Why one `run_turn()`?** Four tabs assembling their own state updates = four chances to forget to clear last turn's market data, drop the user profile, or invoke the graph without conversation history. The bug appears in one tab only, which is the hardest kind to notice.

**`record_in_chat=False`** — pressing "Analyse my portfolio" in the Portfolio tab should not silently inject a message the user never typed into the Chat transcript.

---

## 8. Compliance Architecture

```mermaid
flowchart LR
    AN[Any agent\nhandle] -->|AIMessage| GR[Graph\nstate]
    GR --> CN2[Compliance\nnode\nterminal]
    CN2 --> CHK{Check content}
    CHK -->|banned phrase| BL[Block + replacement\nmessage]
    CHK -->|advice framing| BL
    CHK -->|ok| WRAP[Append disclaimer\nexactly once]
    WRAP --> END([END])
    BL --> END

    style CN2 fill:#ff9999
    style END fill:#99ff99
```

The compliance node is called **exactly once**, as the terminal node in the graph. `app.py` does not import `core.compliance`, and two tests in `tests/test_graph.py` assert it never does. A second call would double-inject the disclaimer — this was the actual bug found live on 2026-11-08.

---

## Design decisions summary

| Decision | Choice | Alternative considered | Why this wins |
|---|---|---|---|
| Orchestration | LangGraph StateGraph | Custom loop | Explicit graph = inspectable execution, testable nodes, free checkpointing |
| Router output | Structured output (Pydantic) | Free-text parsing | A route decides what code runs; can't trust free text there |
| Embeddings | text-embedding-3-small 512-dim | local all-MiniLM-L6-v2 | Quality: 1.00 MRR vs ~0.75 on realistic queries |
| Vector store | Chroma | FAISS | Metadata stored natively; no sidecar dict to keep in sync |
| Concentration metric | HHI | Holding count | Holding count is blind to a 97% position; HHI is citable |
| Disclaimer | Terminal graph node | Each agent | Agents would each add it = doubled/tripled disclaimer; terminal = exactly once |
| Retrieval | MMR | Similarity-only | Avoids 4 chunks from the same article for a broad question |
| Tax assessment year | Computed from date | Hardcoded | A hardcoded AY is right for 5 months and wrong thereafter |
