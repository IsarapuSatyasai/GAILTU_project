"""The following functions are useful transformations to enhance the relevance and quality of the results.
They can be applied after the retrieval step or in arbitrary chains.

Note that these functions currently only takes a list of LLamaindex nodes as input.
Example:
    .. code-block:: python
    from custom_lcel_components.rerank import wrap_rerank_nodes
    post_proces_func = wrap_rerank_nodes(top_n=3)
"""

import json
import logging
import os
import warnings
from typing import List, Tuple

import torch
from sentence_transformers import CrossEncoder

from custom_lcel_components.variables import (
    DEFAULT_SENTENCE_TRANSFORMER_MAX_LENGTH,
    TF_CPP_MIN_LOG_LEVEL,
)

os.environ["TF_CPP_MIN_LOG_LEVEL"] = TF_CPP_MIN_LOG_LEVEL

logger = logging.getLogger(__name__)

torch.set_default_dtype(torch.float64)


def rerank_chunks(
    _dir: dict,
    top_n: int = 10,
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-2-v2",
    chunk_key="retrieved_chunks",
) -> List[dict]:
    """
    Reranks retrieved chunks based on their relevance to a question using a specified model.

    This function takes a dictionary containing retrieved chunks and a question, and reranks the chunks
    based on their relevance to the question using a specified cross-encoder model. The top N chunks are returned.

    Args:
        _dir (dict): A dictionary containing the chunk key (list of chunks) and "question" (the question to rerank against).
        top_n (int, optional): The number of top chunks to return. Defaults to 10.
        model_name (str, optional): The name of the cross-encoder model to use for reranking. Defaults to "cross-encoder/ms-marco-MiniLM-L-2-v2".

    Returns:
        List[dict]: A list of the top N reranked chunks, each with an added "rerank_score".
    """
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    chunks = _dir[chunk_key]
    question = _dir["question"]
    with warnings.catch_warnings(action="ignore"):
        model = CrossEncoder(
            model_name, max_length=DEFAULT_SENTENCE_TRANSFORMER_MAX_LENGTH
        )

    pairs = _infer_pairs(chunks, question)
    scores = model.predict(pairs)

    scored_chunks = []
    for chunk, score in zip(chunks, scores):
        chunk["rerank_score"] = score
        scored_chunks.append(chunk)
    sorted_chunks = sorted(
        scored_chunks, key=lambda d: d["rerank_score"], reverse=True
    )[0:top_n]

    # logger.warning("These are the number of reranked nodes: " + str(len(sorted_chunks)))
    return sorted_chunks


def add_sentence_window(_dir: dict, chunk_key="retrieved_chunks") -> list[dict]:
    """
    Adds a sentence window to each retrieved chunk's text from the metadata and removes the window from the metadata.

    Parameters:
    _dir (dict): A dictionary containing the retrieved chunks.
                 Expected key is the chunk_key.

    Returns:
    list: A list of modified retrieved chunks with the sentence window added to the text and removed from the metadata.
    """
    chunks = _dir[chunk_key]
    modified_chunks = []
    for chunk in chunks:
        metadata = json.loads(chunk["metadata"])
        chunk["text"] = metadata["window"]
        del metadata["window"]
        chunk["metadata"] = json.dumps(metadata)
        modified_chunks.append(chunk)
    return modified_chunks


def create_context_from_chunks(_dir: dict, chunk_key="retrieved_chunks") -> str:
    """
    Creates a single context string from a list of retrieved text chunks.

    This function takes a dictionary containing retrieved chunks and concatenates the text
    from each chunk into a single context string.

    Args:
        _dir (dict): A dictionary containing chunk_key (list of chunks).

    Returns:
        str: A single string containing the concatenated text from all retrieved chunks.
    """
    chunks = _dir[chunk_key]
    texts = [chunk["text"] for chunk in chunks]
    return "".join(texts)



def get_page_no_from_chunks(_dir, chunk_key="retrieved_chunks", include_source=True):
    """
    Extract unique page numbers from chunks, optionally grouped by source.

    Args:
        _dir (dict): Dictionary containing a list of chunks under `chunk_key`.
                     Each chunk has a 'metadata' field (JSON string or dict)
                     with keys:
                        - 'page_no': string of comma-separated pages (e.g., "1,2")
                        - 'source' (optional): document/source name
        chunk_key (str): Key in `_dir` where chunks are stored. Default: "retrieved_chunks".
        include_source (bool):
            - If True: returns a formatted string with each source and its unique pages.
            - If False: returns a flat list of unique pages across all sources.

    Returns:
        str | list:
            - If include_source=True: formatted string like:
                'docA': ['1', '2']
                'docB': ['2', '3']
                'unknown': ['10']
            - If include_source=False: list of unique pages, e.g.:
                ['1', '2', '3', '10']

    Notes:
        - Preserves the order of appearance for both sources and pages.
        - If 'source' is missing, uses 'unknown' as the key.
    """
    chunks = _dir.get(chunk_key, [])
    source_pages = {}
    all_pages = []

    for chunk in chunks:
        meta = chunk.get("metadata", "{}")
        if isinstance(meta, str):
            meta = json.loads(meta)

        source = meta.get("source") or "unknown"
        pages = str(meta.get("page_no", "")).split(",")

        if source not in source_pages:
            source_pages[source] = []

        for p in map(str.strip, pages):
            if p:
                if p not in source_pages[source]:
                    source_pages[source].append(p)
                if p not in all_pages:
                    all_pages.append(p)

    if include_source:
        return "\n".join(f"'{src}': {pages}" for src, pages in source_pages.items())
    else:
        return all_pages


def get_issue_pages_no_from_chunks(_dir, chunk_key="retrieved_chunks"):
    """
    Extract the issue page numbers from the metadata of the first retrieved chunk.

    Args:
        _dir (dict): Dictionary containing a list of chunks under `chunk_key`.
                    Each chunk has a 'metadata' field (JSON string or dict)
                    with keys:
                        - 'issue_pages': string representation of a list of
                        issue page numbers (e.g., "[2, 4, 6, 8]").
        chunk_key (str): Key in `_dir` where chunks are stored. Default: "retrieved_chunks".

    Returns:
        str: A string containing a list of issue page numbers, e.g.
            "[2, 4, 6, 8, 10, ..., 50, 51]".
    """
    chunks = _dir.get(chunk_key, [])
    chunk = chunks[0]
    meta = chunk.get("metadata", "{}")
    if isinstance(meta, str):
        meta = json.loads(meta)

    return meta["issue_pages"]


def _infer_pairs(chunks: List[dict], question: str) -> List[Tuple]:
    """
    Creates pairs of a question and relevant text chunks.

    This function takes a list of relevant text chunks and a question, and creates pairs
    where each pair consists of the question and a text chunk.

    Args:
        chunks (List[dict]): A list of dictionaries, where each dictionary contains a "text" key.
        question (str): The question to pair with each text chunk.

    Returns:
        List[Tuple[str, str]]: A list of tuples, each containing the question and a text chunk.
    """
    pairs = []
    for chunk in chunks:
        pair = (question, chunk["text"])
        pairs.append(pair)
    return pairs
