"""This file contains helper functions, classes, and constants that are used across multiple parts of a project.
These functions are designed to be reusable and to simplify common tasks."""

import locale
import logging
from typing import Optional

from langdetect import DetectorFactory, detect

logger = logging.getLogger(__name__)


def get_country_prompts_list_per_country(
    _dir: dict, countries_prompts_dict: Optional[dict] = {}
) -> dict:
    """
    Retrieve the appropriate prompts dictionary based on the country name.

    This function checks the `country_name` from the provided `_dir` dictionary.
    If the country is "ANZ", it returns the prompts specific to that country.
    Otherwise, it defaults to returning the "Default" prompts (e.g., European prompts).

    Args:
        _dir (dict): A dictionary containing at least the key "country_name".
        countries_prompts_dict (dict, optional): A dictionary mapping country names
            to their respective prompts dictionaries. Must include a "Default" key.
            Defaults to an empty dictionary.

    Returns:
        dict: The prompts dictionary for the specified country if found,
              or the "Default" prompts dictionary otherwise.

    Notes:
        - Logs a warning indicating which prompts are being used.
        - Assumes `countries_prompts_dict` contains keys for "ANZ" and "Default".
    """

    country_name = _dir["country_name"]

    if country_name in countries_prompts_dict.keys():
        logger.warning(
            "The following country prompts are used: {country_name}...".format(
                country_name=country_name
            )
        )
        return countries_prompts_dict[country_name]
    else:
        logger.warning("By default, the European prompt is used.")
        return countries_prompts_dict["Default"]


def init_lang_detect(_dict):
    """Warm up ``langdetect`` so later detections are deterministic and fast.

    Running a throwaway detection forces ``langdetect`` to initialise its
    internal model, avoiding a first-call delay elsewhere in a chain.

    Args:
        _dict: Passthrough input (ignored); present for use as a chain step.

    Returns:
        bool: Always ``True`` once initialisation has run.
    """
    # This needs to be done to properly init langdetect
    _ = detect("This is a test.")
    return True


def detect_language(_dir) -> str:
    """
    Detect the language of ``answer`` and map it to a supported display name.

    If ``langdetect`` returns a language code that is not present in the
    supported ``lang_codes`` mapping, the function falls back to the requested
    ``generated_report_language``.

    Args:
        _dir (dict): A dictionary containing:
            {
                'answer': str,
                'generated_report_language': str
            }

    Returns:
        str: The detected language name when supported, otherwise the requested
            ``generated_report_language``.
    """
    lang_codes = {
        "en": "English",
        "fr": "French",
        "de": "German",
        "nl": "Dutch",
        "it": "Italian",
        "es": "Spanish",
        "pt": "Portuguese",
        "pl": "Polish",
    }

    DetectorFactory.seed = 0
    locale.setlocale(locale.LC_ALL, "en_US.UTF-8")
    # Get keys

    generated_report_language = _dir["generated_report_language"]
    lang_code = detect(_dir["answer"])
    language = lang_codes.get(lang_code, generated_report_language)
    logger.warning(f"Detected language: {language}")
    return language


def expand_question_list(_dir: dict, questions_key="questions", keys=[]) -> dict:
    """
    Expands a list of questions by adding selected fields from the parent
    dictionary to each question.

    Args:
        _dir (dict): A dictionary containing one or more question lists and
            the context fields to be added to each question.
        questions_key (str, optional): The key in `_dir` that contains the
            list of questions to expand. Defaults to `"questions"`.
        keys (list, optional): A list of keys from `_dir` whose values should
            be copied into each question. The `"question"` key is ignored.

    Returns:
        listThe expanded list of questions from `_dir[questions_key]`.
    """

    questions = _dir[questions_key]

    for question in questions:
        for key in keys:
            if key != "question":
                question[key] = _dir[key]

    return questions


def select_columns(_dict, keys_to_select=[]):
    """Return a subset of a dictionary containing only the requested keys.

    Keys in ``keys_to_select`` that are absent from ``_dict`` are silently
    skipped.

    Args:
        _dict (dict): The source dictionary to filter.
        keys_to_select (list, optional): Keys to keep in the output. Defaults
            to an empty list, which yields an empty dictionary.

    Returns:
        dict: A new dictionary with only the selected keys that were present.
    """
    return {k: _dict[k] for k in keys_to_select if k in _dict}
