# ruff: noqa: RUF001

import hashlib

import streamlit as st

from rag_web.api_client import (
    ApiUnavailableError,
    Citation,
    Conversation,
    ConversationDetail,
    Document,
    RagApiClient,
)
from rag_web.config import get_settings


def render() -> None:
    settings = get_settings()
    st.set_page_config(page_title="本地知识库", page_icon=":material/library_books:", layout="wide")
    with RagApiClient(str(settings.api_base_url), settings.http_timeout_seconds) as client:
        try:
            health = client.get_health()
        except ApiUnavailableError as exc:
            st.error(str(exc))
            st.stop()
        documents = _load_documents(client)
        conversations = _load_conversations(client)
        conversation = _ensure_conversation(client, conversations)
        _render_sidebar(client, documents, conversations, conversation)
        _render_main(client, conversation)
    st.caption(f"服务已连接 · 版本 {health.version}")


def _load_documents(client: RagApiClient) -> list[Document]:
    try:
        return client.list_documents()
    except ApiUnavailableError as exc:
        st.sidebar.error(str(exc))
        return []


def _load_conversations(client: RagApiClient) -> list[Conversation]:
    try:
        return client.list_conversations()
    except ApiUnavailableError as exc:
        st.sidebar.error(str(exc))
        return []


def _ensure_conversation(
    client: RagApiClient, conversations: list[Conversation]
) -> ConversationDetail:
    selected = st.session_state.get("conversation_id")
    if selected and any(item.id == selected for item in conversations):
        return client.get_conversation(selected)
    created = client.create_conversation()
    st.session_state.conversation_id = created.id
    return client.get_conversation(created.id)


def _render_sidebar(
    client: RagApiClient,
    documents: list[Document],
    conversations: list[Conversation],
    conversation: ConversationDetail,
) -> None:
    with st.sidebar:
        st.header("对话")
        if st.button("新建对话", icon=":material/add_comment:", use_container_width=True):
            st.session_state.conversation_id = client.create_conversation().id
            st.rerun()
        for item in conversations:
            left, right = st.columns([5, 1])
            if left.button(item.title, key=f"select-{item.id}", use_container_width=True):
                st.session_state.conversation_id = item.id
                st.rerun()
            if right.button("删除", key=f"delete-conversation-{item.id}", icon=":material/delete:"):
                try:
                    client.delete_conversation(item.id)
                    st.session_state.pop("conversation_id", None)
                    st.rerun()
                except ApiUnavailableError as exc:
                    st.error(str(exc))
        new_title = st.text_input(
            "当前对话名称", value=conversation.title, key=f"title-{conversation.id}"
        )
        if st.button("保存名称", icon=":material/save:", use_container_width=True):
            try:
                client.rename_conversation(conversation.id, new_title)
                st.rerun()
            except ApiUnavailableError as exc:
                st.error(str(exc))

        st.divider()
        st.header("文档库")
        uploaded = st.file_uploader("上传 PDF", type=["pdf"], accept_multiple_files=False)
        if uploaded is not None:
            _upload_if_new(
                client, uploaded.name, uploaded.getvalue(), uploaded.type or "application/pdf"
            )
        st.caption(f"文档数量 · {len(documents)}")
        selected_ids = [
            item.id
            for item in documents
            if st.checkbox(item.original_filename, key=f"pick-{item.id}")
        ]
        if selected_ids and st.button("删除选中文档", icon=":material/delete_sweep:"):
            try:
                client.batch_delete_documents(selected_ids)
                st.rerun()
            except ApiUnavailableError as exc:
                st.error(str(exc))
        if selected_ids and st.button("重建选中文档索引", icon=":material/refresh:"):
            try:
                client.batch_rebuild_documents(selected_ids)
                st.rerun()
            except ApiUnavailableError as exc:
                st.error(str(exc))
        for document in documents:
            _render_document_row(client, document)


def _upload_if_new(client: RagApiClient, filename: str, content: bytes, content_type: str) -> None:
    digest = hashlib.sha256(content).hexdigest()
    if st.session_state.get("last_uploaded_sha256") == digest:
        return
    try:
        document = client.upload_document(filename, content, content_type)
        st.session_state.last_uploaded_sha256 = digest
        st.success(f"已完成索引：{document.original_filename}")
        st.rerun()
    except ApiUnavailableError as exc:
        st.error(str(exc))


def _render_document_row(client: RagApiClient, document: Document) -> None:
    with st.container(border=True):
        st.markdown(f"**{document.original_filename}**")
        status = {"indexed": "已完成", "processing": "处理中", "failed": "失败"}.get(
            document.status, document.status
        )
        st.caption(f"{status} · {document.page_count} 页 · {document.chunk_count} 个片段")
        if document.failure_reason:
            st.error(f"失败原因：{document.failure_reason}")
        left, right = st.columns(2)
        if left.button("重建索引", key=f"rebuild-{document.id}", icon=":material/refresh:"):
            try:
                client.rebuild_document(document.id)
                st.rerun()
            except ApiUnavailableError as exc:
                st.error(str(exc))
        if right.button("删除", key=f"delete-{document.id}", icon=":material/delete:"):
            client.delete_document(document.id)
            st.rerun()


def _render_main(client: RagApiClient, conversation: ConversationDetail) -> None:
    st.title("本地知识库")
    st.caption("基于已索引 PDF 提问，答案会附带可定位的原文来源。")
    _render_history(conversation)
    question = st.chat_input("基于已上传文档提问")
    if question:
        st.chat_message("user").markdown(question)
        _stream_answer(client, conversation.id, question)
        st.rerun()


def _render_history(conversation: ConversationDetail) -> None:
    for message in conversation.messages:
        with st.chat_message(message.role):
            st.markdown(message.content)
            if message.role == "assistant":
                _render_citations(message.citations)


def _stream_answer(client: RagApiClient, conversation_id: str, question: str) -> None:
    with st.chat_message("assistant"):
        answer = st.empty()
        text_parts: list[str] = []
        citations: list[Citation] = []
        retrieval: dict | None = None
        try:
            for event in client.stream_message(conversation_id, question):
                if event.event == "token":
                    text_parts.append(str(event.data.get("text", "")))
                    answer.markdown("".join(text_parts) or "▌")
                elif event.event == "citations":
                    citations = [
                        Citation.model_validate(item) for item in event.data.get("items", [])
                    ]
                elif event.event == "retrieval":
                    retrieval = event.data
            _render_citations(citations)
            if retrieval:
                with st.expander("检索详情", expanded=False):
                    st.caption(
                        f"候选片段 {retrieval.get('candidate_count', 0)} · "
                        f"最终来源 {retrieval.get('result_count', 0)} · "
                        f"检索 {retrieval.get('retrieval_ms', 0)} ms · "
                        f"重排 {retrieval.get('rerank_ms', 0)} ms"
                    )
        except ApiUnavailableError as exc:
            answer.error(str(exc))


def _render_citations(citations: list[Citation]) -> None:
    if citations:
        with st.expander(f"来源 · {len(citations)} 条", expanded=False):
            for index, citation in enumerate(citations, start=1):
                st.markdown(f"**[{index}] {citation.filename} · 第 {citation.page} 页**")
                st.caption(citation.excerpt)


render()
