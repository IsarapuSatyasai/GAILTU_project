"""Node: Build RAG index from selected pages."""

from typing import Any
from graph.graph_state import FinancialGraphState
from custom_lcel_components.chains import get_sentence_window_rag_chain_from_config

RAG_CONFIG = {
    "llm_model": "gpt-5.2",
    "llm_model_agent": "gpt-5.4",
    "temperature": 0,
    "top_p": 1,
    "embedding_model_name": "text-embedding-3-large",
    "pdf_loader_type": "PyMuPDFLoader",
    "include_source": False,
    "hybrid_search_args": None,
    "remove_duplicate_chunks": True,
    "sentence_chunker_window_size": 5,
    "similarity_top_k": 20,
    "source_key": "selected_pages_source",
    "rerank_args": {"top_n": 10, "model": "cross-encoder/ms-marco-MiniLM-L-2-v2"},
}

def build_rag_index(state: FinancialGraphState) -> dict:
    selected_pages = state.get("selected_pages", [])
    errors = list(state.get("errors", []))

    if not selected_pages:
        return {
            "rag_collection_name": None,
            "use_rag": False,
            "errors": errors + ["No pages available for RAG indexing."],
        }

    try:
        rag_chain, index_chain, _ = get_sentence_window_rag_chain_from_config(RAG_CONFIG)

        documents = [
            {
                "text": page.get("text", ""),
                "page_number": page.get("page_number"),
                "metadata": {"page": page.get("page_number")},
            }
            for page in selected_pages
            if page.get("text")
        ]

        collection_name = index_chain.invoke({
            "source": documents,
            "documents": documents,
        })

        return {
            "rag_collection_name": collection_name,
            "use_rag": True,
            "errors": errors,
        }
    except Exception as exc:
        return {
            "rag_collection_name": None,
            "use_rag": False,
            "errors": errors + [f"RAG indexing failed: {exc}"],
        }