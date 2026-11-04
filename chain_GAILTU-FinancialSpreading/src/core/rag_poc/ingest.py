"""Index the PDF with the existing Credit RAG factory."""

from custom_lcel_components.chains import get_sentence_window_rag_chain_from_config
from config import get_settings

def build_index(pdf_path: str):
    settings = get_settings()
    config = {
        "llm_model": settings.azure_openai_deployment,
        "llm_model_agent": settings.azure_openai_deployment,
        "temperature": settings.llm_temperature,
        "top_p": settings.llm_top_p,
        "embedding_model_name": "text-embedding-3-large",
        "pdf_loader_type": "PyMuPDFLoader",
        "include_source": False,
        "hybrid_search_args": None,
        "remove_duplicate_chunks": True,
        "sentence_chunker_window_size": 5,
        "similarity_top_k": 20,
        "source_key": "pdf_source",
        "rerank_args": {"top_n": 10, "model": "cross-encoder/ms-marco-MiniLM-L-2-v2"},
    }

    _, index_chain, _ = get_sentence_window_rag_chain_from_config(config)
    collection_name = index_chain.invoke({"pdf_source": pdf_path})
    return collection_name, config