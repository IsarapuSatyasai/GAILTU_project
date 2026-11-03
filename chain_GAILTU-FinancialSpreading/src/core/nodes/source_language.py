"""Node: Detect Source Language.

Detects the language of the parsed PDF document using the
`detect_language` utility from custom_lcel_components.
"""

import logging

from graph.graph_state import FinancialGraphState
from custom_lcel_components.utils import detect_language, init_lang_detect

# logger = logging.getLogger(__name__)


def source_language(state: FinancialGraphState) -> dict:
    """Detect the main language of the Annual report.
    This function concatenates extracted PDF page content and uses `detect_language`
    to identify the source language. Falls back to the configured
    `generated_report_language` if the detected language is unsupported.

    Returns:
        dict: Updated state with `source_language` set to the detected
            language name (e.g. "English", "French", "Dutch").
    """
    pdf_pages = state.get("pdf_pages", [])
    generated_report_language = state.get("generated_report_language", "English")

    if not pdf_pages:
        # logger.warning("No PDF pages available for language detection, defaulting to %s.", generated_report_language)
        return {
            "source_language": generated_report_language,
            "errors": state.get("errors", []) + ["No PDF content for language detection"],
        }

    try:
        # Initialise langdetect for deterministic results
        init_lang_detect({})

        # Combine page content into a representative sample
        sample_text = " ".join(
            page.page_content for page in pdf_pages if hasattr(page, "page_content")
        )

        if not sample_text.strip():
            # logger.warning("PDF pages contain no text, defaulting to %s.", generated_report_language)
            return {
                "source_language": generated_report_language,
                "errors": state.get("errors", []),
            }

        detected = detect_language({
            "answer": sample_text,
            "generated_report_language": generated_report_language,
        })

        # logger.info("Source language detected: %s", detected)
        return {"source_language": detected, "errors": state.get("errors", [])}

    except Exception as e:
        # logger.error("Language detection failed: %s", str(e))
        return {
            "source_language": generated_report_language,
            "errors": state.get("errors", []) + [f"Language detection error: {str(e)}"],
        }
