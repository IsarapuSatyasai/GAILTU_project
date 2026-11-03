"""
This file contains the functions to evaluate the quality of the input text (like annual reports, Credit lens reports)

Utilities for evaluating text quality in extracted PDF texts including :
- count number of long sentences per page, pages containing only one sentence etc.
- detection of empty text pages, and
- basic character‑level statistics such as ASCII ratio, printable ratio, control‑character ratio,
and Shannon entropy.

"""

"""Error prone, error free, one sentence per page"""

import math
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List

import numpy as np
import spacy
from langdetect import detect

# import spacy
# from language_tool_python import LanguageTool

# NOTE this evaluation can only be used for english documents
# NOTE this tool requires Java to be installed
# tool = LanguageTool("en")
nlp_tool = spacy.load("en_core_web_sm")

METRIC_NAMES = [
    "long_sentences",
    "one_long_sentence_per_page",
    "one_sentence_per_page",
    # "error_prone",
    # "error_free",
]


def evaluate_sentence_correctness_by_page(page):
    """
    This function processes a single page of text data from an annual report PDF to identify and classify sentences based on their length and grammatical correctness.

    Parameters:
    page (dict): A dictionary that contains the text of the page and the page number.

    Returns:
    list: A list of dictionaries, each containing a sentence, its type, the page number, and any grammatical matches if applicable.
    """
    sentences_list = []

    sentences = nlp_tool(page["text"])

    for sentence in sentences.sents:
        word_count = len([token for token in sentence if not token.is_punct])

        if word_count > 100 and len(list(sentences.sents)) > 1:
            sentences_list.append({"sentence": sentence.text, "type": "long_sentences"})

        elif word_count > 100 and len(list(sentences.sents)) == 1:
            sentences_list.append(
                {"sentence": sentence.text, "type": "one_long_sentence_per_page"}
            )

        elif word_count <= 100 and len(list(sentences.sents)) == 1:
            sentences_list.append(
                {"sentence": sentences.text, "type": "one_sentence_per_page"}
            )

    return sentences_list


def evaluate_sentence_correctness(document_list: List[Dict], num_threads=4):
    """
    This function processes an annual report PDF in parallel to assess the quality metrics of each page, such as sentence length and grammatical correctness.

    Parameters:
    document_list (list): A list where each element represents a page of the PDF. Each page is expected to be a dictionary containing a key "text" with the page's text content.
    num_threads (int): The number of threads to use for parallel processing.

    Returns:
    dict: A dictionary where each key is the name of the metric, and the value is the percentage of occurrence for that specific metric in the document.
    """
    sentences_list = []
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        results = executor.map(evaluate_sentence_correctness_by_page, document_list)
        for result in results:
            sentences_list.extend(result)

    # Calculate the count and percentage for each type
    metric_counts = {type_: 0 for type_ in METRIC_NAMES}
    for sentence in sentences_list:
        metric_counts[sentence["type"]] += 1

    for metric_name in METRIC_NAMES:
        if len(sentences_list) == 0:
            metric_counts[metric_name] = 0
        else:
            metric_counts[metric_name] = np.round(
                100 * metric_counts[metric_name] / len(sentences_list), 1
            )

    return metric_counts


def get_language(input_text):
    """
    Detect the language of a given text. (This is not used now, it can be used for the future)

    Parameters
    ----------
    input_text : str
        The text whose language should be detected.

    Returns
    -------
    str
        The detected language code (e.g., 'en', 'fr').
        Returns an empty string if detection fails or an exception occurs.
    """

    try:
        # your logic here
        return detect(input_text)
    except Exception:
        return ""


def no_text_percentage(document_list: List[Dict]):
    """
    Calculates the percentage of pages with no textual content from a list of document pages.
    This function analyzes the output of the ingest step and identifies pages that contain no text. It returns both the
    percentage of such pages and a list of their corresponding page numbers.
    Args:
        document_list (List[Dict]): A list of dictionaries, each representing a page with a "text" field.

    Returns:
        Tuple[float, List[int]]:
            - Percentage of pages with no text (rounded to 2 decimal places).
            - List of page numbers that contain no text.
    Example:
    (1.89, [17])

    1.89 --> percentage of pages with no text
    [17] --> list of page numbers with no text

    """
    list_of_page_numbers_with_no_text = [
        i + 1 for i, doc in enumerate(document_list) if not doc["text"].strip()
    ]
    percentage = round(
        (len(list_of_page_numbers_with_no_text) / len(document_list)) * 100, 2
    )
    return percentage, list_of_page_numbers_with_no_text


def ascii_ratio(s):
    """
    Calculates the proportion of ASCII characters in a string.

    ASCII characters are those with Unicode code points less than 128.
    This metric helps identify whether the text contains only standard English characters
    or includes extended Unicode characters (e.g., emojis, accented letters).
    Args:
        s (str): Input string.
    Returns:
        float: Ratio of ASCII characters to total characters in the string.
    Example:
        >>> ascii_ratio("Hello World!")
        1.0
        >>> ascii_ratio("Hello 🌍")
        0.8571428571428571
    """
    ascii_chars = sum(1 for c in s if ord(c) < 128)
    return ascii_chars / len(s) if s else 0


def printable_ratio(s):
    """
    Calculates the proportion of printable characters in a string.
    Printable characters include letters, digits, punctuation, and whitespace.This metric helps detect the presence of invisible or formatting characters.
    Args:
        s (str): Input string.
    Returns:
        float: Ratio of printable characters to total characters in the string.
    Example:
        >>> printable_ratio("Hello World!")
        1.0
        >>> printable_ratio("Hello\x01World")
        0.9090909090909091
    """
    printable_chars = sum(1 for c in s if c.isprintable())
    return printable_chars / len(s) if s else 0


def control_char_ratio(s):
    """
    Calculates the proportion of control characters in a string.

    Control characters are non-printable characters with Unicode code points < 32,
    excluding common whitespace characters like newline (`\\n`), tab (`\\t`), and carriage return (`\\r`).
    This metric helps identify corrupted or machine-generated text.

    Args:
        s (str): Input string.

    Returns:
        float: Ratio of control characters to total characters in the string.

    Example:
        >>> control_char_ratio("Hello World!")
        0.0
        >>> control_char_ratio("Hello\x01World")
        0.09090909090909091
    """
    controls = sum(1 for c in s if ord(c) < 32 and c not in ["\n", "\t", "\r"])
    return controls / len(s) if s else 0


def shannon_entropy(s):
    """
    Calculates the Shannon entropy of a string.

    Entropy measures the randomness or complexity of the text.
    Low entropy indicates repetitive or simple text, while high entropy suggests diverse or noisy content.

    Args:
        s (str): Input string.

    Returns:
        float: Shannon entropy value.

    Example:
        >>> shannon_entropy("aaaaaaa")
        0.0
        >>> shannon_entropy("abcdefg")
        2.807354922057604
        >>> shannon_entropy("Hello World!")
        3.180832987517585
    """
    if not s:
        return 0
    counts = Counter(s)
    probs = [count / len(s) for count in counts.values()]
    return -sum(p * math.log2(p) for p in probs)
