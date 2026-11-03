"""This module provides functions for chunking text documents.

The two main functions are:

- base_chunker(documents: List[Dict], chunk_size: int = 1024, remove_duplicates: bool = True, chunk_overlap: bool = 200) -> List[TextNode]:
    Chunks a list of documents into smaller pieces and optionally removes duplicate chunks.
- sentence_chunker(documents: List[Dict], remove_duplicates=True) -> List[Dict]:
    Chunks documents into nodes using a sentence window approach and optionally removes duplicate chunks.

"""

import json
import logging
from typing import Dict, List, Tuple

import tiktoken
from llama_index.core.node_parser.text.utils import split_by_sentence_tokenizer
from llama_index.core.text_splitter import SentenceSplitter
from mlflow.tracing.provider import trace_disabled

from custom_lcel_components.variables import _MAX_EMBED_LENGTH

logger = logging.getLogger(__name__)


# @trace_disabled
def base_chunker(
    documents: List[Dict],
    chunk_size: int = 1024,
    remove_duplicates: bool = True,
    chunk_overlap: bool = 200,
) -> List[Dict]:
    """Chunks a list of documents into smaller pieces and optionally removes duplicate chunks.

    This function takes a list of documents and splits each document's text into smaller chunks.
    It can also remove duplicate chunks based on their text content. The chunking process
    can be customized with the chunk size and chunk overlap parameters.

    Args:
        documents (List[Dict]): A list of dictionaries, where each dictionary contains a "text" key and optional "metadata".
        chunk_size (int, optional): The maximum size of each chunk. Defaults to 1024.
        remove_duplicates (bool, optional): Whether to remove duplicate chunks. Defaults to True.
        chunk_overlap (int, optional): The number of overlapping characters between chunks. Defaults to 200.

    Returns:
        List[Dict]: A list of dictionaries with the text split into smaller chunks and duplicates optionally removed.
    """
    if not documents:
        logger.warning("Skip chunking because non empty vector db...")
        return []

    text_splitter = SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    split_docs = []
    for doc in documents:
        splits = text_splitter.split_text_metadata_aware(doc["text"], doc["metadata"])
        for split in splits:
            split_doc = doc.copy()
            split_doc["text"] = split
            split_docs.append(split_doc)

    if remove_duplicates:
        split_docs = _remove_duplicate_chunks(split_docs)

    return split_docs


def sentence_chunker(
    documents: List[dict],
    remove_duplicates=True,
) -> List[Dict]:
    """
    Chunks a list of documents into smaller pieces based on sentences and optionally removes duplicate chunks.
    Additionally, update the metadata to include the correct page number for each chunk.

    This function processes a list of documents by first combining their text into a combined document, and then splitting this combined document's text into smaller chunks based on sentences.
    Additionally, update the metadata to include the correct page number for each chunk.
    It can also remove duplicate chunks based on their text content. The resulting chunks are then capped to a maximum length.

    Args:
        documents (List[Dict]): A list of dictionaries, where each dictionary contains a "text" key.
        remove_duplicates (bool, optional): Whether to remove duplicate chunks. Defaults to True.

    Returns:
        List[Dict]: A list of dictionaries with the text split into smaller chunks, duplicates optionally removed, and chunks capped to the maximum length.
    """

    if not documents:
        logger.warning("skip chunking because non empty vector db")
        return []

    # Take a list of documents and combines their text into a combined_documents. If the documents is a dictionary, it extracts the list of documents from the "documents" key.
    # The combined document retains the metadata of the first document in the list.
    if isinstance(documents, dict):
        documents = documents["documents"]

    # split the documents' text into smaller chunks based on sentences.
    text_splitter = split_by_sentence_tokenizer()

    splitted_docs = []
    for original_doc in documents:
        # Combine per-document to preserve correct source/page mapping
        combined_documents, text_by_page = _combine_documents([original_doc])

        for doc in combined_documents:
            splits = text_splitter(doc["text"])
            for split in splits:
                split_doc = doc.copy()
                # Removes trailing whitespace
                split_cleaned = (split or "").rstrip()
                if not split_cleaned:
                    continue
                split_doc["text"] = split_cleaned

                split_doc = _update_chunk_metadata(
                    split_doc, split_cleaned, text_by_page
                )

                splitted_docs.append(split_doc)

    if remove_duplicates:
        splitted_docs = _remove_duplicate_chunks(splitted_docs)

    capped_docs = _cap_chunks(splitted_docs)

    return capped_docs


def _remove_duplicate_chunks(split_docs: List[Dict]) -> List[Dict]:
    """Remove duplicate documents based on their text content.

    This function takes a list of dictionaries, each representing a document with a "text" key.
    It returns a new list of dictionaries, excluding any duplicates based on the "text" content.

    Args:
        split_docs (List[Dict]): A list of dictionaries, where each dictionary contains a "text" key.

    Returns:
        List[Dict]: A list of dictionaries with duplicates removed based on the "text" content.
    """
    non_duplicates = []
    non_duplicates_text = []
    for doc in split_docs:
        if doc["text"] not in non_duplicates_text:
            non_duplicates.append(doc)
            non_duplicates_text.append(doc["text"])
    return non_duplicates


def _combine_documents(
    documents: List[Dict],
) -> Tuple[List[Dict], List[Tuple[int, str]]]:
    """Combines a list of documents into a single document and retains the text by page.

    This function takes a list of documents, each represented as a dictionary with "text" and "metadata" keys.
    It combines the text of all documents into a single document and retains the text of each page along with its page number.

    Args:
        documents (List[Dict]): A list of dictionaries, where each dictionary contains a "text" key and a "metadata" key.

    Returns:
        Tuple[List[Dict], List[Tuple[int, str]]]: A tuple containing:
            - A list with a single combined document.
            - A list of tuples, where each tuple contains a page number and the corresponding text.
    """
    # A list of tuples, where each tuple contains a page number and the corresponding text.
    text_by_page = []

    if documents:
        combined_document = documents[0].copy()
        combined_text = ""

        for doc in documents:
            text = doc["text"]
            combined_text = combined_text + text + " "
            page_num = json.loads(doc["metadata"])["page_no"]
            text_by_page.append((page_num, text))

        combined_document["text"] = combined_text
        combined_documents = [combined_document]
    else:
        combined_documents = []
        text_by_page = []
    return combined_documents, text_by_page


def _find_string_in_page_reference(
    page_reference: List[Tuple[int, str]], search_string: str
) -> str:
    """Finds the page number(s) of a given string in a page reference data.

    Args:
        page_reference (list of tuples): A list where each tuple contains a page number and the text of that page.
        search_string (str): The string to search for in the page reference data.

    Returns:
        tuple: A tuple containing the start and end page numbers where the string is found.
               If the string is found on a single page, start_page and end_page will be the same.
               If the string spans across two pages, start_page and end_page will be different.
               If the string is not found, both start_page and end_page will be None.
    """
    start_page = None
    end_page = None

    # Iterate through each page to find the string
    for page_num, page_text in page_reference:
        if search_string in page_text:
            start_page = page_num
            end_page = page_num
            break

    # Check if the string spans across two pages
    if start_page is None or end_page is None:
        for i in range(len(page_reference) - 1):
            combined_text = page_reference[i][1] + " " + page_reference[i + 1][1]
            if search_string in combined_text:
                start_page = page_reference[i][0]
                end_page = page_reference[i + 1][0]
                break

    if start_page == end_page:
        page_number = str(start_page)
    else:
        page_number = f"{start_page},{end_page}"

    return page_number


def _cap_chunks(split_documents: List[Dict]) -> List[Dict]:
    """Caps the length of document chunks to a maximum length.

    This function takes a list of documents and ensures that the text in each document
    does not exceed a specified maximum length. If a document's text exceeds the maximum length,
    it is split into smaller chunks, each within the maximum length limit.

    Args:
        split_documents (List[Dict]): A list of dictionaries, where each dictionary contains a "text" key.

    Returns:
        List[Dict]: A list of dictionaries with text chunks capped to the maximum length.
    """
    capped_documents = []
    tokenizer = tiktoken.get_encoding("cl100k_base")
    for doc in split_documents:
        number_of_tokens = len(tokenizer.encode(doc["text"]))
        if number_of_tokens <= _MAX_EMBED_LENGTH:
            capped_documents.append(doc)
        else:
            logger.warning(
                "Capping chunk: there is a chunk that exceeds the max length of: "
                + str(_MAX_EMBED_LENGTH)
            )
            number_of_chunks = int((number_of_tokens / _MAX_EMBED_LENGTH) + 1)
            capped_texts = split_into_n(doc["text"], number_of_chunks)
            for capped_text in capped_texts:
                capped_doc = doc.copy()
                capped_doc["text"] = capped_text
                capped_documents.append(capped_doc)
    return capped_documents


def split_into_n(s: str, n: int):
    """
    Split string `s` into n nearly-equal parts.
    If len(s) < n, some parts will be empty strings.

    Examples:
        split_into_n("abcdefghij", 3) -> ['abcd', 'efg', 'hij']
        split_into_n("abcdef", 4)     -> ['ab', 'c', 'd', 'ef']
    """
    if n <= 0:
        raise ValueError("n must be a positive integer")

    length = len(s)
    base, extra = divmod(length, n)  # extra parts get +1 character
    parts = []
    start = 0

    for i in range(n):
        size = base + (1 if i < extra else 0)
        parts.append(s[start : start + size])
        start += size

    return parts


def _update_chunk_metadata(
    split_doc: dict, split_cleaned: str, text_by_page: dict
) -> dict:
    """
    Updates the metadata of a split document to include the correct page number.

    Args:
        split_doc (dict): The chunked document dictionary.
        split_cleaned (str): The cleaned text of the chunk.
        text_by_page (dict): Mapping of page content to page numbers.

    Returns:
        dict: The updated split document with metadata including page number.
    """
    meta_like = split_doc.get("metadata")
    if isinstance(meta_like, str):
        try:
            old_metadata = json.loads(meta_like)
            meta_was_str = True
        except json.JSONDecodeError:
            old_metadata = {"_raw_metadata": meta_like}
            meta_was_str = True
    elif isinstance(meta_like, dict):
        old_metadata = dict(meta_like)
        meta_was_str = False
    else:
        old_metadata = {}
        meta_was_str = False

    page_number = _find_string_in_page_reference(text_by_page, split_cleaned)
    old_metadata["page_no"] = page_number

    split_doc["metadata"] = (
        json.dumps(old_metadata, ensure_ascii=False) if meta_was_str else old_metadata
    )
    return split_doc
