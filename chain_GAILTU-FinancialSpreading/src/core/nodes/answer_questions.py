"""Node: Answer Questions using LLM.

Iterates over each Excel row and extracts the corresponding financial
data point from the PDF context and added source hyperlink.
"""

from typing import List, Dict, Any, Optional
from collections import Counter, defaultdict
import re

from langchain_core.messages import HumanMessage, SystemMessage

from graph.graph_state import FinancialGraphState
from prompts.system_prompt import SYSTEM_PROMPT
from prompts.user_prompt import get_user_prompt
from models import MultiYearExtractionResponse
from config import get_settings


def build_hyperlink(page_number: Optional[int], source_link: str) -> str:
    """Helper function applying the exact Excel HYPERLINK formula logic."""
    if page_number is not None and page_number != -1 and source_link:
        return f'=HYPERLINK("{source_link}#page={page_number}", "Page {page_number}")'
    return "N/A"


def align_answers_to_template(
    excel_data: List[Dict[str, Any]],
    extracted_answers: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Align extracted answers with the existing Excel template metrics."""

    answer_map = {
        (
            answer["worksheet"],
            answer["variable"],
        ): answer
        for answer in extracted_answers
        if (
            answer["worksheet"],
            answer["variable"],
        ) in {
            (
                metric["worksheet"],
                metric["variable"],
            )
            for metric in excel_data
        }
    }

    final_answers = []

    for metric in excel_data:
        key = (
            metric["worksheet"],
            metric["variable"],
        )

        answer = answer_map.get(key)

        if answer is None:
            answer = {
                "worksheet": metric["worksheet"],
                "variable": metric["variable"],
                "answer": "N/A",
                "confidence": 0.0,
                "page_number": -1,
                "source_fields": [],
                "formula": None,
                "source_link": "N/A",
                "source_heading": None,
                "source_text": None,
            }

        final_answers.append(answer)

    return final_answers


def validate_template_alignment(
    excel_data: List[Dict[str, Any]],
    answers: List[Dict[str, Any]],
) -> None:
    """Validate that final answers exactly match template metrics."""

    template_keys = {
        (
            metric["worksheet"],
            metric["variable"],
        )
        for metric in excel_data
    }

    answer_keys = {
        (
            answer["worksheet"],
            answer["variable"],
        )
        for answer in answers
    }

    if template_keys != answer_keys:
        missing_metrics = template_keys - answer_keys
        new_metrics = answer_keys - template_keys

        raise ValueError(
            f"Template alignment failed. "
            f"Missing metrics: {missing_metrics}. "
            f"New metrics: {new_metrics}."
        )

    if len(excel_data) != len(answers):
        raise ValueError(
            f"Metric count mismatch. "
            f"Template: {len(excel_data)}, "
            f"Answers: {len(answers)}."
        )


def detect_years(selected_pages: List[Dict[str, Any]]) -> List[int]:
    """Detect fiscal years from any PDF format.

    Handles annual reports, CreditLens summaries, and other layouts.
    Ignores preparation and print dates so they are not treated as fiscal years.
    """
    candidates = Counter()

    year_patterns = [
        # "December 31, 2024" / "December 31 2024"
        r"(?:december|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?)\s+\d{1,2},?\s*(20[1-3]\d)",
        # "12/31/2024" / "31/12/2024" / "2024-12-31"
        r"(?:^|\s)(?:\d{1,2}[/-]\d{1,2}[/-]|20[1-3]\d[/-]\d{1,2}[/-])(20[1-3]\d)",
        # "years ended 2024" / "year ended 2024"
        r"(?:years?|period)\s+ended\s+(20[1-3]\d)",
        # "as at 2024" / "as of 2024"
        r"(?:as\s+(?:at|of))\s+(20[1-3]\d)",
        # Standalone 4-digit years near financial context
        r"\b(20[1-3]\d)\b",
    ]

    financial_context = [
        "balance sheet",
        "income statement",
        "cash flow",
        "statement of",
        "financial",
        "assets",
        "liabilities",
        "revenue",
        "net income",
        "total assets",
        "summary",
        "creditlens",
        "rabodet",
        "statement date",
    ]

    # Context that indicates a non-fiscal year (preparation, print, generation)
    ignore_context = [
        "prepared:",
        "prepared ",
        "printed:",
        "print date",
        "generated:",
        "generated ",
        "exported:",
        "exported ",
    ]

    for page in selected_pages:
        text = page.get("text", "") or ""
        lower = text.lower()

        # Skip pages with no financial signal
        if not any(ctx in lower for ctx in financial_context):
            continue

        for pattern in year_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                year = int(match.group(1))
                if not (2010 <= year <= 2035):
                    continue

                # Check surrounding text for ignore context
                start = max(0, match.start() - 40)
                end = min(len(lower), match.end() + 10)
                nearby = lower[start:end]

                if any(ctx in nearby for ctx in ignore_context):
                    continue

                candidates[year] += 1

    if not candidates:
        return []

    # Return the two most common years, newest first
    top = [y for y, _ in candidates.most_common(2)]
    return sorted(top, reverse=True)


def answer_questions(state: FinancialGraphState) -> dict:
    excel_data = state.get("excel_data", [])
    errors = list(state.get("errors", []))
    selected_pages = state.get("selected_pages", [])

    if not selected_pages:
        empty = align_answers_to_template(excel_data, [])
        return {
            "original_answers": empty,
            "answers": empty,
            "answers_by_year": {},
            "years": [],
            "errors": errors + [
                "Extraction skipped because no template-relevant pages were selected."
            ],
        }

    years = detect_years(selected_pages)
    if not years:
        years = [None]

    llm = state.get("llm")
    structured_llm = llm.with_structured_output(MultiYearExtractionResponse)

    pdf_file_name = state.get("pdf_file_name", "")
    settings = get_settings()
    source_link = settings.sharepoint_link + pdf_file_name.replace(" ", "%20")

    USER_PROMPT = get_user_prompt(excel_data)

    full_context = "\n\n".join(
        [
            f"--- PDF Page {page.get('page_number', i + 1)} ---\n{page.get('text', '')}"
            for i, page in enumerate(selected_pages)
        ]
    )

    year_instruction = (
        f"Extract every variable only for these years: {years}. "
        "Do not include any other years. "
        "Return one answer object per variable per year. "
        "Include the year field on every answer. "
        "Return numeric answers exactly as they appear in the source document, including thousand separators (e.g. 13,950). Do not remove commas or convert to plain integers."
        if years != [None]
        else "Extract the most recent period available. "
            "Return numeric answers exactly as they appear in the source document, including thousand separators."
    )

    user_content = (
        f"Please extract the following variables:\n{USER_PROMPT}\n\n"
        f"{year_instruction}\n\n"
        "Use only the supplied document context. "
        "For page_number, return the physical PDF page number shown in the context header.\n\n"
        f"Document context:\n{full_context}\n\n"
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]

    try:
        response: MultiYearExtractionResponse = structured_llm.invoke(messages)

        if errors:
            response.errors.extend(errors)

        answers_by_year = defaultdict(list)

        for answer in response.answers:
            if years != [None] and answer.year not in years:
                continue

            answer.source_link = build_hyperlink(
                answer.page_number,
                source_link,
            )
            year_key = answer.year if answer.year is not None else years[0]
            answers_by_year[year_key].append(answer.model_dump())

        aligned_by_year = {}
        for year, year_answers in answers_by_year.items():
            aligned = align_answers_to_template(excel_data, year_answers)
            validate_template_alignment(excel_data, aligned)
            aligned_by_year[year] = aligned

        latest = years[0] if years and years[0] is not None else next(iter(aligned_by_year), None)
        latest_answers = aligned_by_year.get(
            latest,
            align_answers_to_template(excel_data, []),
        )

        return {
            "years": [y for y in years if y is not None],
            "answers_by_year": aligned_by_year,
            "original_answers": latest_answers,
            "answers": latest_answers,
            "errors": response.errors,
        }

    except Exception as exc:
        error_msg = f"Bulk LLM extraction error: {exc}"
        errors.append(error_msg)
        empty = align_answers_to_template(excel_data, [])
        return {
            "original_answers": empty,
            "answers": empty,
            "answers_by_year": {},
            "years": [],
            "errors": errors,
        }