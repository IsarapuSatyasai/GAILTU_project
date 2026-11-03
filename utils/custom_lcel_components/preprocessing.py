"""This module provides various functions for processing and cleaning text documents.

The main functions are:
- combine_documents(documents: List[dict]) -> List[dict]:
    Combines a list of document dictionaries into a single document dictionary.

- remove_duplicate_sentences(sentences: List[str]) -> List[str]:
    Removes duplicate sentences from a list of sentences.

- sentence_window_cleaning_step(text: str) -> str:
    Cleans the input text by appending a dot if it contains only one sentence. Useful for handling cases where consecutive pages contain a single sentence.

- clean_documents(documents: List[dict], custom_cleaning_step: Optional[Callable[[str], str]] = None) -> List[dict]:
    Cleans the documents and optionally applies a custom cleaning step. Removes duplicate sentences, extra whitespaces, and other unwanted characters."""

import logging
import re
from typing import List

logger = logging.getLogger(__name__)


def combine_documents(documents: List[dict]) -> List[dict]:
    """
    Combines a list of documents into a single document.

    This function takes a list of documents and combines their text into a single document.
    If the input is a dictionary, it extracts the list of documents from the "documents" key.
    The combined document retains the metadata of the first document in the list.

    Args:
        documents (List[Dict]): A list of dictionaries, where each dictionary contains a "text" key.

    Returns:
        List[Dict]: A list containing a single combined document, or an empty list if no documents are provided.
    """
    if isinstance(documents, dict):
        documents = documents["documents"]

    if documents:
        combined_document = documents[0].copy()
        combined_document["text"] = " ".join([doc["text"] for doc in documents])
        combined_documents = [combined_document]
    else:
        combined_documents = []

    return combined_documents


def sentence_window_cleaning_step(text):
    """
    Cleans the input text by appending a dot if it contains only one sentence.

    This function is useful for handling cases where consecutive pages contain a single sentence,
    which could be a large table per page. By appending a dot, it ensures proper separation of pages.
    A dot will be added only if there is a single sentence on the page and it does not already end with a dot.

    Args:
        text (str): The input text to be cleaned.

    Returns:
        str: The cleaned text with a dot appended if it contains only one sentence.
    """
    # If consecutive pages contain a single sentence, which could be a large table per page, then separate the pages with a dot.
    sentence_count = _count_sentences(text)

    if (sentence_count == 1) & (not text.endswith(".")):
        cleaned_text = text + "."
    else:
        cleaned_text = text

    return cleaned_text


def clean_documents(documents, custom_cleaning_step=None):
    """
    Clean the documents and optionally applying a custom cleaning step.

    Args:
        documents (list): A list containing documents to be cleaned.
        custom_cleaning_step (callable, optional): A function to apply additional cleaning steps.
    Returns:
        list: A list of cleaned documents.
    """
    # documents = _dict["documents"]
    if not documents:
        logger.warning("skip cleaning because non empty persisted database...")
        return []
    cleaned_documents = []
    for document in documents:
        # Check whether document["text"] is a string
        if not isinstance(document["text"], str):
            document["text"] = ""
            cleaned_documents.append(document)
            continue

        sentences = re.split(
            r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s", document["text"]
        )

        # Remove duplicates
        non_duplicate_sentences = _remove_duplicate_sentences(sentences)

        # Join the unique sentences back into a string
        non_duplicate_string = " ".join(non_duplicate_sentences)

        # Remove \n and extra whitespaces. See one example below
        # input: "This is a sample text.\n\nIt contains multiple\n\n\nnewlines and    extra    spaces."
        # output: "This is a sample text. It contains multiple newlines and extra spaces."
        cleaned_text = re.sub(r"\s+", " ", non_duplicate_string).strip()

        # Remove space between any words followed by full stop, question mark or exclamation point. See one example below
        # input: "This is a sample text . Is it correct ? Yes, it is !"
        # output: "This is a sample text. Is it correct? Yes, it is!"
        cleaned_text = re.sub(r"\s+(?=[.?!])", "", cleaned_text)

        # Replace sequences of more than two dots with nothing. See one example below
        # input: "This is a sample text... It contains sequences of more than two dots...."
        # output: "This is a sample text It contains sequences of more than two dots."
        cleaned_text = re.sub(r"\.{2,}", "", cleaned_text)

        # Remove underscores. See one example below
        # input: "This_is_a_sample_text_with_underscores."
        # output: "This is a sample text with underscores."
        cleaned_text = re.sub(r"_+", "", cleaned_text)

        # Apply custom cleaning step if provided
        if custom_cleaning_step:
            document["text"] = custom_cleaning_step(cleaned_text)
        else:
            document["text"] = cleaned_text

        cleaned_documents.append(document)
    return cleaned_documents


def _remove_duplicate_sentences(sentences: List[str]) -> List[str]:
    """
    Removes duplicate sentences from a list of sentences.

    This function takes a list of sentences and returns a new list with duplicates removed,
    preserving the order of the original sentences.

    Args:
        sentences (List[str]): A list of sentences.

    Returns:
        List[str]: A list of sentences with duplicates removed.
    """

    non_duplicate_sentences = []
    for sentence in sentences:
        if sentence not in non_duplicate_sentences:
            non_duplicate_sentences.append(sentence)
    return non_duplicate_sentences


def _count_sentences(text):
    """
    Counts the number of sentences in a given text.

    This function uses a regular expression to identify sentence endings (., !, ?)
    and counts the number of sentences in the provided text.

    Args:
        text (str): The text to count sentences in.

    Returns:
        int: The number of sentences in the text.
    """
    # Regex to identify sentence endings (., !, ?)
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    # Remove empty entries after splitting
    sentences = [sentence for sentence in sentences if sentence.strip()]
    return len(sentences)
