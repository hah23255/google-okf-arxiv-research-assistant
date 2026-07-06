"""Streamlit frontend for pure-OKF ArXiv assistant."""

from __future__ import annotations

import json
import os

import streamlit as st

from google_okf_arxiv_assistant.frontend_client import (
    FrontendClientError,
    check_backend_health,
    fetch_document,
    fetch_stats,
    query_backend,
    query_model_backend,
    search_backend,
)

DOC_TYPE_OPTIONS = ["", "concept", "reference", "decision", "process", "log", "index"]
SORT_OPTIONS = ["score_desc", "title_asc", "updated_at_desc"]
CHAT_MODELS = ["granite4.1:3b", "qwen3.5:2b", "nemotron-3-nano:4b"]


def _default_api_base_url() -> str:
    try:
        if "api_base_url" in st.secrets:
            return str(st.secrets["api_base_url"]).strip()
    except Exception:
        pass
    return os.environ.get("OKF_API_BASE_URL", "http://127.0.0.1:8000")


def _init_state() -> None:
    defaults: dict[str, object] = {
        "messages": [],
        "api_base_url": _default_api_base_url().rstrip("/"),
        "top_k": 5,
        "use_model_chat": True,
        "chat_model": "granite4.1:3b",
        "search_query": "",
        "search_top_k": 10,
        "search_doc_type": "",
        "search_tags_text": "",
        "search_paper_id": "",
        "search_sort_by": "score_desc",
        "search_results": [],
        "search_error": "",
        "search_history": [],
        "presets": [],
        "doc_preview": None,
        "status_health": None,
        "status_error": "",
        "status_stats": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _render_sidebar() -> None:
    with st.sidebar:
        st.header("Settings")
        with st.form("settings_form"):
            api_base_url = st.text_input("API Base URL", value=str(st.session_state.api_base_url))
            top_k = st.slider("Default Top K", min_value=1, max_value=20, value=int(st.session_state.top_k))
            use_model_chat = st.checkbox(
                "Use model-backed chat (/query-model)",
                value=bool(st.session_state.use_model_chat),
            )
            current_model = str(st.session_state.chat_model)
            selected_model = st.selectbox(
                "Chat model",
                CHAT_MODELS,
                index=CHAT_MODELS.index(current_model) if current_model in CHAT_MODELS else 0,
            )
            submitted = st.form_submit_button("Apply")

        if submitted:
            st.session_state.api_base_url = api_base_url.strip().rstrip("/")
            st.session_state.top_k = int(top_k)
            st.session_state.use_model_chat = bool(use_model_chat)
            st.session_state.chat_model = selected_model
            st.success("Settings updated")

        if st.session_state.use_model_chat:
            st.caption(
                "Model mode enabled: lexical OKF retrieval + local Ollama synthesis "
                f"using `{st.session_state.chat_model}`."
            )
        else:
            st.caption("Deterministic mode enabled: no model synthesis.")

        if st.button("Check backend health"):
            try:
                st.session_state.status_health = check_backend_health(st.session_state.api_base_url)
                st.session_state.status_error = ""
            except FrontendClientError as exc:
                st.session_state.status_health = None
                st.session_state.status_error = str(exc)

        if st.session_state.status_health is True:
            st.success("Backend health is OK")
        elif st.session_state.status_health is False:
            st.warning("Backend responded but status != ok")

        if st.session_state.status_error:
            st.error(st.session_state.status_error)


def _append_chat(
    role: str,
    content: str,
    citations: list[str] | None = None,
    *,
    mode: str = "",
    model_used: str = "",
    warning: str | None = None,
) -> None:
    st.session_state.messages.append(
        {
            "role": role,
            "content": content,
            "citations": citations or [],
            "mode": mode,
            "model_used": model_used,
            "warning": warning,
        }
    )


def _run_chat_query(prompt: str) -> None:
    _append_chat("user", prompt)
    try:
        if st.session_state.use_model_chat:
            result = query_model_backend(
                api_base_url=st.session_state.api_base_url,
                query=prompt,
                top_k=int(st.session_state.top_k),
                model=str(st.session_state.chat_model),
            )
        else:
            result = query_backend(
                api_base_url=st.session_state.api_base_url,
                query=prompt,
                top_k=int(st.session_state.top_k),
            )
        _append_chat(
            "assistant",
            result.answer,
            result.citations,
            mode=result.mode,
            model_used=result.model_used,
            warning=result.warning,
        )
    except FrontendClientError as exc:
        _append_chat("assistant", f"Backend error: {exc}", [])


def _run_search(
    query: str,
    top_k: int,
    doc_type: str,
    tags_text: str,
    paper_id_contains: str,
    sort_by: str,
) -> None:
    tags_any = [piece.strip() for piece in tags_text.split(",") if piece.strip()]

    st.session_state.search_query = query
    st.session_state.search_top_k = int(top_k)
    st.session_state.search_doc_type = doc_type
    st.session_state.search_tags_text = tags_text
    st.session_state.search_paper_id = paper_id_contains
    st.session_state.search_sort_by = sort_by

    try:
        results = search_backend(
            api_base_url=st.session_state.api_base_url,
            query=query,
            top_k=int(top_k),
            doc_type=doc_type or None,
            tags_any=tags_any,
            paper_id_contains=paper_id_contains or None,
            sort_by=sort_by,
        )
        st.session_state.search_results = results
        st.session_state.search_error = ""
        st.session_state.search_history.append(
            {
                "query": query,
                "top_k": int(top_k),
                "doc_type": doc_type,
                "tags_text": tags_text,
                "paper_id_contains": paper_id_contains,
                "sort_by": sort_by,
                "result_count": len(results),
            }
        )
    except FrontendClientError as exc:
        st.session_state.search_results = []
        st.session_state.search_error = str(exc)


def _render_chat_tab() -> None:
    st.subheader("Chat")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            citations = msg.get("citations") or []
            if citations:
                st.caption("Citations: " + ", ".join(citations))
            mode = str(msg.get("mode", "")).strip()
            model_used = str(msg.get("model_used", "")).strip()
            warning = msg.get("warning")
            if mode:
                if model_used:
                    st.caption(f"Mode: {mode} | Model: {model_used}")
                else:
                    st.caption(f"Mode: {mode}")
            if isinstance(warning, str) and warning.strip():
                st.warning(warning.strip())

    prompt = st.chat_input("Ask a question (min 3 characters)")
    if prompt:
        _run_chat_query(prompt)
        st.rerun()


def _render_search_tab() -> None:
    st.subheader("Search Explorer")

    with st.form("search_form"):
        query = st.text_input("Query", value=str(st.session_state.search_query))
        top_k = st.slider("Top K", min_value=1, max_value=50, value=int(st.session_state.search_top_k))
        doc_type = st.selectbox("Document type", DOC_TYPE_OPTIONS, index=DOC_TYPE_OPTIONS.index(st.session_state.search_doc_type) if st.session_state.search_doc_type in DOC_TYPE_OPTIONS else 0)
        tags_text = st.text_input("Tags (comma-separated)", value=str(st.session_state.search_tags_text))
        paper_id_contains = st.text_input("Paper ID contains", value=str(st.session_state.search_paper_id))
        sort_by = st.selectbox("Sort by", SORT_OPTIONS, index=SORT_OPTIONS.index(st.session_state.search_sort_by) if st.session_state.search_sort_by in SORT_OPTIONS else 0)
        submitted = st.form_submit_button("Run search")

    if submitted:
        _run_search(
            query=query,
            top_k=int(top_k),
            doc_type=doc_type,
            tags_text=tags_text,
            paper_id_contains=paper_id_contains,
            sort_by=sort_by,
        )

    st.markdown("### Presets")
    preset_name = st.text_input("Preset name", value="")
    col_save, col_apply = st.columns(2)
    with col_save:
        if st.button("Save current preset"):
            name = preset_name.strip()
            if not name:
                st.warning("Enter a preset name")
            else:
                st.session_state.presets = [p for p in st.session_state.presets if p["name"] != name]
                st.session_state.presets.append(
                    {
                        "name": name,
                        "query": st.session_state.search_query,
                        "top_k": st.session_state.search_top_k,
                        "doc_type": st.session_state.search_doc_type,
                        "tags_text": st.session_state.search_tags_text,
                        "paper_id_contains": st.session_state.search_paper_id,
                        "sort_by": st.session_state.search_sort_by,
                    }
                )
                st.success(f"Saved preset: {name}")

    with col_apply:
        if st.session_state.presets:
            selected_preset_name = st.selectbox(
                "Load preset",
                options=[p["name"] for p in st.session_state.presets],
                key="preset_selector",
            )
            if st.button("Apply preset"):
                selected = next(p for p in st.session_state.presets if p["name"] == selected_preset_name)
                _run_search(
                    query=str(selected["query"]),
                    top_k=int(selected["top_k"]),
                    doc_type=str(selected["doc_type"]),
                    tags_text=str(selected["tags_text"]),
                    paper_id_contains=str(selected["paper_id_contains"]),
                    sort_by=str(selected["sort_by"]),
                )
                st.success(f"Applied preset: {selected_preset_name}")

    if st.session_state.search_error:
        st.error(st.session_state.search_error)

    st.markdown("### Results")
    results = st.session_state.search_results
    if not results:
        st.info("No search results yet.")
    else:
        for idx, item in enumerate(results, start=1):
            with st.expander(f"[{idx}] {item.title} ({item.doc_name})"):
                st.write(f"Score: {item.score:.4f}")
                st.write(f"Type: {item.doc_type or 'n/a'}")
                st.write(f"Paper ID: {item.paper_id or 'n/a'}")
                st.write("Tags: " + (", ".join(item.tags) if item.tags else "n/a"))
                if item.highlights:
                    st.write("Highlights: " + ", ".join(item.highlights))
                st.write(item.snippet)
                if st.button("Preview document", key=f"preview_{idx}_{item.doc_name}"):
                    try:
                        st.session_state.doc_preview = fetch_document(
                            api_base_url=st.session_state.api_base_url,
                            doc_name=item.doc_name,
                        )
                    except FrontendClientError as exc:
                        st.session_state.doc_preview = None
                        st.error(str(exc))

    st.markdown("### Citation Explorer")
    citation_pool = []
    citation_pool.extend([item.doc_name for item in results])
    for msg in st.session_state.messages:
        citation_pool.extend(msg.get("citations") or [])
    citation_options = sorted(set(citation_pool))

    if citation_options:
        selected_doc = st.selectbox("Select document", options=citation_options, key="citation_explorer_select")
        if st.button("Load selected document"):
            try:
                st.session_state.doc_preview = fetch_document(
                    api_base_url=st.session_state.api_base_url,
                    doc_name=selected_doc,
                )
            except FrontendClientError as exc:
                st.session_state.doc_preview = None
                st.error(str(exc))
    else:
        st.caption("No citations available yet.")

    if st.session_state.doc_preview is not None:
        st.markdown("### Document Preview")
        st.write(f"Document: {st.session_state.doc_preview.doc_name}")
        st.json(st.session_state.doc_preview.frontmatter)
        st.text(st.session_state.doc_preview.body)


def _conversation_markdown() -> str:
    lines = ["# Conversation Export", ""]
    for msg in st.session_state.messages:
        role = str(msg.get("role", "assistant")).capitalize()
        lines.append(f"## {role}")
        lines.append(str(msg.get("content", "")))
        citations = msg.get("citations") or []
        if citations:
            lines.append("Citations: " + ", ".join(citations))
        mode = str(msg.get("mode", "")).strip()
        model_used = str(msg.get("model_used", "")).strip()
        warning = msg.get("warning")
        if mode:
            lines.append("Mode: " + mode)
        if model_used:
            lines.append("Model: " + model_used)
        if isinstance(warning, str) and warning.strip():
            lines.append("Warning: " + warning.strip())
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _render_history_export_tab() -> None:
    st.subheader("History & Export")
    st.write(f"Messages: {len(st.session_state.messages)}")
    st.write(f"Search runs: {len(st.session_state.search_history)}")

    user_questions = [m["content"] for m in st.session_state.messages if m.get("role") == "user"]
    if user_questions:
        rerun_query = st.selectbox("Rerun past chat query", options=user_questions, key="rerun_chat_select")
        if st.button("Rerun selected chat query"):
            _run_chat_query(rerun_query)
            st.success("Reran selected query")
    else:
        st.caption("No chat history yet.")

    if st.session_state.search_history:
        options = [
            f"{idx+1}. {row['query']} (k={row['top_k']}, results={row['result_count']})"
            for idx, row in enumerate(st.session_state.search_history)
        ]
        idx_label = st.selectbox("Rerun past search", options=options, key="rerun_search_select")
        selected_idx = options.index(idx_label)
        row = st.session_state.search_history[selected_idx]
        if st.button("Rerun selected search"):
            _run_search(
                query=str(row["query"]),
                top_k=int(row["top_k"]),
                doc_type=str(row["doc_type"]),
                tags_text=str(row["tags_text"]),
                paper_id_contains=str(row["paper_id_contains"]),
                sort_by=str(row["sort_by"]),
            )
            st.success("Reran selected search")
    else:
        st.caption("No search history yet.")

    export_payload = {
        "messages": st.session_state.messages,
        "search_history": st.session_state.search_history,
        "presets": st.session_state.presets,
    }

    st.download_button(
        label="Download history JSON",
        data=json.dumps(export_payload, indent=2),
        file_name="okf_assistant_history.json",
        mime="application/json",
    )
    st.download_button(
        label="Download conversation Markdown",
        data=_conversation_markdown(),
        file_name="okf_assistant_conversation.md",
        mime="text/markdown",
    )


def _render_status_tab() -> None:
    st.subheader("Status Panel")
    col_health, col_stats = st.columns(2)

    with col_health:
        if st.button("Refresh backend health"):
            try:
                st.session_state.status_health = check_backend_health(st.session_state.api_base_url)
                st.session_state.status_error = ""
            except FrontendClientError as exc:
                st.session_state.status_health = None
                st.session_state.status_error = str(exc)

        if st.session_state.status_health is True:
            st.success("Backend health: OK")
        elif st.session_state.status_health is False:
            st.warning("Backend health: not OK")
        else:
            st.caption("Health not checked yet")

    with col_stats:
        if st.button("Refresh bundle stats"):
            try:
                st.session_state.status_stats = fetch_stats(st.session_state.api_base_url)
                st.session_state.status_error = ""
            except FrontendClientError as exc:
                st.session_state.status_stats = None
                st.session_state.status_error = str(exc)

    if st.session_state.status_error:
        st.error(st.session_state.status_error)

    stats = st.session_state.status_stats
    if stats is not None:
        st.metric("Total docs", stats.total_docs)
        st.metric("Has index", "yes" if stats.has_index else "no")
        st.markdown("#### Type counts")
        st.json(stats.types_count)
        st.markdown("#### Top tags")
        st.table([{"tag": row.tag, "count": row.count} for row in stats.tags_count_top])
    else:
        st.caption("Bundle stats not fetched yet")


def main() -> None:
    st.set_page_config(page_title="OKF ArXiv Assistant", page_icon="📚", layout="wide")
    st.title("📚 Google OKF ArXiv Assistant")
    st.write("Pure-OKF assistant with chat, search explorer, citation preview, and history export.")

    _init_state()
    _render_sidebar()

    tab_chat, tab_search, tab_history, tab_status = st.tabs(
        ["Chat", "Search Explorer", "History & Export", "Status"]
    )
    with tab_chat:
        _render_chat_tab()
    with tab_search:
        _render_search_tab()
    with tab_history:
        _render_history_export_tab()
    with tab_status:
        _render_status_tab()


if __name__ == "__main__":
    main()
