"""Finnie RAG Lab — a debug harness for the retrieval pipeline.

This is NOT the product UI. `app.py` is the chat interface a user sees; this is the
instrument panel *behind* it, for answering questions like:

  - Why did that question return those chunks?
  - Which chunks did the relevance threshold throw away, and how close were they?
  - Does MMR actually change the result for this query, or only in theory?
  - Is the answer grounded in what was retrieved, or is the model filling gaps?
  - What did that question cost?

Design choices worth knowing
----------------------------
1. **It calls the low-level search functions, not `FinnieRetriever`.** The retriever
   applies the relevance threshold internally and returns survivors only. A debug
   tool needs to see what was *rejected* and by how much, so this page runs
   `similarity_search` / `mmr_search` directly and applies the threshold itself,
   visibly.

2. **Generation is opt-in.** Retrieval costs a fraction of a cent (one query
   embedding); generation costs real money on `gpt-4o`. The toggle defaults to off
   so you can iterate on retrieval all afternoon for pennies.

3. **Settings are per-run overrides, not config edits.** Nothing here writes to
   `config.yaml`. Find a better threshold, then change it in config deliberately.

Run from the ai_finance_assistant/ directory:
    streamlit run rag_lab.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import streamlit as st  # noqa: E402

st.set_page_config(
    page_title="Finnie RAG Lab",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

KB_DIR = PROJECT_ROOT / "data" / "knowledge_base"
EVAL_QUERIES = PROJECT_ROOT / "data" / "eval_queries.json"


# ── cached resources ──────────────────────────────────────────────────────────
# Chroma client and the OpenAI client are expensive to build and safe to share
# across reruns. Streamlit re-executes this whole file on every interaction, so
# without caching every slider nudge would reopen the index.


@st.cache_resource(show_spinner="Opening the index…")
def _resources():
    from core.config import load_config
    from rag.embedder import get_client as get_openai_client
    from rag.vector_store import get_client, get_or_create_collection

    cfg = load_config()
    chroma = get_client(cfg.resolve(cfg.rag.index_dir))
    collection = get_or_create_collection(chroma)
    return cfg, collection, get_openai_client()


@st.cache_resource(show_spinner="Building the LLM client…")
def _llm():
    from core.llm import build_llm

    return build_llm()


@st.cache_data
def _categories() -> list[str]:
    if not KB_DIR.exists():
        return []
    return sorted(p.name for p in KB_DIR.iterdir() if p.is_dir())


@st.cache_data
def _preset_queries() -> dict[str, list[dict]]:
    """Eval queries grouped by bucket, so you can test against the real set."""
    if not EVAL_QUERIES.exists():
        return {}
    data = json.loads(EVAL_QUERIES.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict]] = {}
    for q in data.get("queries", []):
        if q.get("type") != "positive":
            continue
        grouped.setdefault(q.get("difficulty", "other"), []).append(q)
    return grouped


@st.cache_data
def _collection_size() -> int:
    from rag.vector_store import collection_count

    _cfg, collection, _oai = _resources()
    return collection_count(collection)


# ── session state ─────────────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []  # list of run dicts, newest last
if "spend" not in st.session_state:
    st.session_state.spend = 0.0
if "query_text" not in st.session_state:
    st.session_state.query_text = ""


# ── sidebar: retrieval knobs ──────────────────────────────────────────────────
cfg, collection, openai_client = _resources()

st.sidebar.title("🔬 RAG Lab")
st.sidebar.caption("Debug harness for the retrieval pipeline. Not the product UI.")

st.sidebar.subheader("Retrieval settings")
st.sidebar.caption(f"Defaults come from `config.yaml`. Index: {_collection_size():,} chunks.")

top_k = st.sidebar.slider(
    "top_k", 1, 15, cfg.rag.top_k, help="How many chunks to pull before threshold filtering."
)
use_mmr = st.sidebar.toggle(
    "Use MMR",
    value=cfg.rag.use_mmr,
    help=(
        "Maximal Marginal Relevance trades a little precision for diversity, "
        "removing near-duplicate chunks. On the eval set it lifts hit rate from "
        "0.95 to 1.00."
    ),
)
mmr_lambda = st.sidebar.slider(
    "MMR λ",
    0.0,
    1.0,
    cfg.rag.mmr_lambda,
    0.05,
    disabled=not use_mmr,
    help="0 = maximum diversity, 1 = maximum relevance (equivalent to plain vector search).",
)
threshold = st.sidebar.slider(
    "Relevance threshold",
    0.0,
    1.5,
    float(cfg.rag.relevance_threshold),
    0.05,
    help=(
        "Maximum cosine DISTANCE to keep — lower is stricter. Chunks above this are "
        "dropped. Good matches typically land at 0.40–0.70."
    ),
)

cats = _categories()
category = st.sidebar.selectbox(
    "Category filter",
    ["(none — search whole KB)", *cats],
    help=(
        "The eval deliberately runs with no filter: supplying the expected category "
        "and then scoring on it pins precision at 1.0."
    ),
)
category_arg = None if category.startswith("(none") else category

st.sidebar.divider()
st.sidebar.metric("Session spend (est.)", f"${st.session_state.spend:.4f}")
if st.sidebar.button("Reset session", width="stretch"):
    st.session_state.history = []
    st.session_state.spend = 0.0
    st.rerun()


# ── query input ───────────────────────────────────────────────────────────────
st.title("RAG Lab")

presets = _preset_queries()
if presets:
    with st.expander("Load a query from the eval set", expanded=False):
        bucket = st.selectbox("Bucket", sorted(presets), index=0)
        options = presets.get(bucket, [])
        labels = [f"{q['id']} — {q['question']}" for q in options]
        if labels:
            chosen = st.selectbox("Query", labels, label_visibility="collapsed")
            picked = options[labels.index(chosen)]
            cols = st.columns([1, 3])
            with cols[0]:
                if st.button("Use this query", type="primary"):
                    st.session_state.query_text = picked["question"]
                    st.rerun()
            with cols[1]:
                st.caption(
                    f"Expected category: `{picked.get('expected_category', '—')}` · "
                    f"keywords: {', '.join(picked.get('expected_keywords', []))}"
                )
            if picked.get("reference_answer"):
                st.caption(f"**Reference answer:** {picked['reference_answer']}")

question = st.text_area(
    "Question",
    value=st.session_state.query_text,
    height=80,
    placeholder="e.g. Is PPF better than ELSS?",
)

# The generation toggle lives here, beside the run button, NOT in the sidebar:
# Streamlit auto-collapses the sidebar on a narrow window, which hid the single
# most important control and made the lab look retrieval-only.
ctl = st.columns([1, 2])
with ctl[1]:
    do_generate = st.toggle(
        "Generate the final answer",
        value=False,
        key="do_generate",
        help=(
            "Off = retrieval only (one embedding, a fraction of a cent). "
            "On = runs the system + user prompt through gpt-4o, roughly $0.01 per question."
        ),
    )
with ctl[0]:
    run = st.button(
        "Run retrieval + answer" if do_generate else "Run retrieval only",
        type="primary",
        width="stretch",
    )

if not do_generate:
    st.caption(
        "⚠️ Generation is **off** — you will see retrieved chunks and the assembled prompt, "
        "but no final answer. Switch on *Generate the final answer* above to run the full "
        "pipeline."
    )


# ── the run ───────────────────────────────────────────────────────────────────
def _search(query: str) -> tuple[list[dict], float, float]:
    """Return (raw results, embed seconds, search seconds) with no filtering applied."""
    from rag.embedder import embed_single
    from rag.vector_store import mmr_search, similarity_search

    t0 = time.perf_counter()
    vector = embed_single(query, client=openai_client)
    t1 = time.perf_counter()

    where = {"category": category_arg} if category_arg else None
    if use_mmr:
        raw = mmr_search(
            collection=collection,
            query_embedding=vector,
            top_k=top_k,
            lambda_mult=mmr_lambda,
            where=where,
        )
    else:
        raw = similarity_search(
            collection=collection,
            query_embedding=vector,
            top_k=top_k,
            where=where,
        )
    t2 = time.perf_counter()
    return raw, t1 - t0, t2 - t1


def _build_prompt(query: str, kept: list[dict]) -> tuple[str, str, str]:
    """Assemble exactly what would be sent to the model: (system, user, context).

    Built whether or not generation is enabled, so you can inspect the prompt
    without paying for a completion. This is the step between retrieval and the
    answer, and the place most RAG bugs actually live: chunks retrieved fine, but
    the context was truncated, mis-ordered, or missing its source labels.
    """
    from langchain_core.documents import Document

    from rag.prompt import RAG_SYSTEM_PROMPT, RAG_USER_TEMPLATE, format_context

    docs = [
        Document(page_content=r["text"], metadata={**r["metadata"], "distance": r["distance"]})
        for r in kept
    ]
    context = format_context(docs)
    return (
        RAG_SYSTEM_PROMPT.format(context=context),
        RAG_USER_TEMPLATE.format(question=query),
        context,
    )


def _generate(query: str, kept: list[dict]) -> dict:
    """Run the prompt + LLM step over the chunks that survived the threshold."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from core.llm import _COST_PER_1K  # single source of pricing truth

    # Same assembly the preview shows, so what you inspect is what gets sent.
    system_text, user_text, context = _build_prompt(query, kept)
    messages = [SystemMessage(content=system_text), HumanMessage(content=user_text)]

    t0 = time.perf_counter()
    response = _llm().invoke(messages)
    elapsed = time.perf_counter() - t0

    usage = (response.response_metadata or {}).get("token_usage", {}) or {}
    model = (response.response_metadata or {}).get("model_name", "gpt-4o")
    pricing = next(
        (v for k, v in _COST_PER_1K.items() if model.startswith(k)),
        _COST_PER_1K["gpt-4o"],
    )
    cost = (
        usage.get("prompt_tokens", 0) / 1000 * pricing["input"]
        + usage.get("completion_tokens", 0) / 1000 * pricing["output"]
    )

    # Compliance runs exactly as it does in production: it may refuse.
    from core.compliance import check_and_wrap

    try:
        final = check_and_wrap(response.content)
        blocked = None
    except ValueError as exc:
        final = response.content
        blocked = str(exc)

    return {
        "raw_answer": response.content,
        "final_answer": final,
        "blocked": blocked,
        "latency": elapsed,
        "usage": usage,
        "model": model,
        "cost": cost,
        "context_chars": len(context),
    }


if run and question.strip():
    st.session_state.query_text = question
    raw, embed_s, search_s = _search(question.strip())

    kept = [r for r in raw if r["distance"] <= threshold]
    dropped = [r for r in raw if r["distance"] > threshold]

    gen = None
    if do_generate:
        if kept:
            with st.spinner("Generating…"):
                gen = _generate(question.strip(), kept)
            st.session_state.spend += gen["cost"]
        else:
            st.warning(
                "Nothing passed the threshold, so there is no context to generate from. "
                "In production the agent refuses here rather than answering unaided — "
                "which is the behaviour you want."
            )

    st.session_state.history.append(
        {
            "question": question.strip(),
            "n_kept": len(kept),
            "n_dropped": len(dropped),
            "best": kept[0]["distance"] if kept else None,
            "mmr": use_mmr,
            "top_k": top_k,
            "threshold": threshold,
            "cost": gen["cost"] if gen else 0.0,
        }
    )

    # ── timings ───────────────────────────────────────────────────────────────
    m = st.columns(4)
    m[0].metric("Embed", f"{embed_s * 1000:.0f} ms")
    m[1].metric("Search", f"{search_s * 1000:.0f} ms")
    m[2].metric("Kept / retrieved", f"{len(kept)} / {len(raw)}")
    m[3].metric("Best distance", f"{kept[0]['distance']:.4f}" if kept else "—")

    # ── answer ────────────────────────────────────────────────────────────────
    if gen:
        st.subheader("Answer")
        if gen["blocked"]:
            st.error(
                f"**Compliance guard blocked this response.** {gen['blocked']}\n\n"
                "This is the guard working, not a bug — the raw text is shown below for "
                "inspection but would never reach a user."
            )
            st.code(gen["raw_answer"], language=None)
        else:
            st.markdown(gen["final_answer"])

        g = st.columns(4)
        g[0].metric("Latency", f"{gen['latency']:.2f} s")
        g[1].metric("Prompt tokens", f"{gen['usage'].get('prompt_tokens', 0):,}")
        g[2].metric("Completion tokens", f"{gen['usage'].get('completion_tokens', 0):,}")
        g[3].metric("Cost", f"${gen['cost']:.5f}")
        st.caption(
            f"Model `{gen['model']}` · context {gen['context_chars']:,} chars from "
            f"{len(kept)} chunks · disclaimer "
            f"{'appended' if not gen['blocked'] else 'not reached'}"
        )

    # ── the prompt actually sent ──────────────────────────────────────────────
    system_text, user_text, context_text = _build_prompt(question.strip(), kept)
    approx_tokens = len(system_text + user_text) // 4  # ~4 chars/token, good enough here

    with st.expander(
        f"Prompt sent to the model — system + user, ~{approx_tokens:,} tokens", expanded=False
    ):
        st.caption(
            "This is the complete input to `gpt-4o`: the system message carries the rules and "
            "the retrieved context, the user message carries the raw question. Shown even when "
            "generation is off, so you can check the context before paying for a completion."
        )
        st.markdown(
            f"**System message** · {len(system_text):,} chars "
            f"(context is {len(context_text):,} of them)"
        )
        st.code(system_text, language="text")
        st.markdown(f"**User message** · {len(user_text):,} chars")
        st.code(user_text, language="text")
        st.caption(
            "Rule 2 is what produces a refusal instead of a guess, and rule 4 is how "
            "contradictory tax rates get resolved toward the later Budget rather than averaged."
        )

    # ── retrieved chunks ──────────────────────────────────────────────────────
    st.subheader(f"Retrieved chunks ({len(kept)} kept)")
    if not kept:
        st.info("No chunk passed the threshold. Raise the threshold slider to see near misses.")

    for i, r in enumerate(kept, start=1):
        md = r["metadata"]
        head = (
            f"**{i}.** `{md.get('category', '?')}` · {md.get('title', 'untitled')} "
            f"— *{md.get('section', '')}*  ·  distance **{r['distance']:.4f}**"
        )
        with st.expander(head, expanded=(i == 1)):
            c = st.columns([1, 1, 1])
            c[0].caption(f"**Source:** {md.get('source', '—')}")
            c[1].caption(f"**Retrieved:** {md.get('date_retrieved') or '—'}")
            url = md.get("url")
            c[2].caption(f"**Link:** [{url}]({url})" if url else "**Link:** —")
            st.text(r["text"])

    if dropped:
        with st.expander(f"Dropped by threshold ({len(dropped)}) — how close were they?"):
            st.caption(
                f"These scored worse than the {threshold:.2f} cutoff. If a chunk you expected "
                "is sitting just above it, the threshold is too strict for this query — but "
                "check that it would not also let noise in on other queries before changing it."
            )
            st.dataframe(
                [
                    {
                        "distance": round(r["distance"], 4),
                        "over by": round(r["distance"] - threshold, 4),
                        "category": r["metadata"].get("category", ""),
                        "title": r["metadata"].get("title", ""),
                        "section": r["metadata"].get("section", ""),
                    }
                    for r in dropped
                ],
                width="stretch",
                hide_index=True,
            )

elif run:
    st.warning("Type a question first.")


# ── run history ───────────────────────────────────────────────────────────────
if st.session_state.history:
    st.divider()
    st.subheader("This session")
    st.caption(
        "Settings are recorded per run, so you can compare the same question across "
        "different MMR and threshold values."
    )
    st.dataframe(
        [
            {
                "question": h["question"][:60] + ("…" if len(h["question"]) > 60 else ""),
                "kept": h["n_kept"],
                "dropped": h["n_dropped"],
                "best dist": round(h["best"], 4) if h["best"] is not None else None,
                "mmr": h["mmr"],
                "top_k": h["top_k"],
                "thresh": h["threshold"],
                "cost": f"${h['cost']:.5f}",
            }
            for h in reversed(st.session_state.history)
        ],
        width="stretch",
        hide_index=True,
    )
