"""Node: Build the Financial Spreading RAG index."""

from graph.graph_state import FinancialGraphState
from rag_poc.ingest import build_index


def build_rag_index(state: FinancialGraphState) -> dict:
    selected_pages = state.get("selected_pages", [])
    errors = list(state.get("errors", []))

    if not selected_pages:
        return {
            "rag_collection_name": None,
            "use_rag": False,
            "errors": errors + ["No selected pages available for RAG indexing."],
        }

    try:
        collection_name, rag_config = build_index(state["pdf_source"])

        return {
            "rag_collection_name": collection_name,
            "rag_config": rag_config,
            "use_rag": True,
            "errors": errors,
        }

    except Exception as exc:
        return {
            "rag_collection_name": None,
            "rag_config": None,
            "use_rag": False,
            "errors": errors + [f"Financial RAG indexing failed: {exc}"],
        }