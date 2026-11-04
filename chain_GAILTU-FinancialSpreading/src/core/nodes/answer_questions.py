"""Node: Answer Questions using LLM.

Supports:
- Full-context fallback (original behaviour)
- RAG retrieval using the existing Credit chain components
- Multi-year extraction
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
from rag_poc.extract import build_context, _norm
from rag_poc.retrieve import build_page_index
from nodes.select_pages import _to_page_record

# Retrieval config used when build_rag_index did not provide one
DEFAULT_RAG_CONFIG = {
    "embedding_model_name": "text-embedding-3-large",
    "similarity_top_k": 20,
    "sentence_chunker_window_size": 5,
    "rerank_args": {"top_n": 10, "model": "cross-encoder/ms-marco-MiniLM-L-2-v2"},
    "source_key": "pdf_source",
}

def build_hyperlink(page_number: Optional[int], source_link: str) -> str:
    if page_number is not None and page_number != -1 and source_link:
        return f'=HYPERLINK("{source_link}#page={page_number}", "Page {page_number}")'
    return "N/A"

def align_answers_to_template(
    excel_data: List[Dict[str, Any]],
    extracted_answers: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    # Match on normalised names: the LLM often drops trailing/non-breaking spaces from template
    # names (e.g. "Depreciation\xa0"), which made exact matching silently turn real answers into N/A.
    answer_map = {
        (_norm(a["worksheet"]), _norm(a["variable"])): a
        for a in extracted_answers
    }

    final_answers = []
    for metric in excel_data:
        key = (_norm(metric["worksheet"]), _norm(metric["variable"]))
        answer = answer_map.get(key)
        if answer is not None:
            # keep the template's exact names so validate_template_alignment passes
            answer = {**answer, "worksheet": metric["worksheet"], "variable": metric["variable"]}
        else:
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

def validate_template_alignment(excel_data, answers) -> None:
    template_keys = {(m["worksheet"], m["variable"]) for m in excel_data}
    answer_keys = {(a["worksheet"], a["variable"]) for a in answers}
    if template_keys != answer_keys:
        raise ValueError(
            f"Template alignment failed. Missing: {template_keys - answer_keys}. "
            f"New: {answer_keys - template_keys}."
        )
    if len(excel_data) != len(answers):
        raise ValueError(
            f"Metric count mismatch. Template: {len(excel_data)}, Answers: {len(answers)}."
        )

def detect_years(selected_pages: List[Dict[str, Any]]) -> List[int]:
    candidates = Counter()
    year_patterns = [
        r"(?:december|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?)\s+\d{1,2},?\s*(20[1-3]\d)",
        r"(?:^|\s)(?:\d{1,2}[/-]\d{1,2}[/-]|20[1-3]\d[/-]\d{1,2}[/-])(20[1-3]\d)",
        r"(?:years?|period)\s+ended\s+(20[1-3]\d)",
        r"(?:as\s+(?:at|of))\s+(20[1-3]\d)",
        r"\b(20[1-3]\d)\b",
    ]
    financial_context = [
        "balance sheet", "income statement", "cash flow", "statement of",
        "financial", "assets", "liabilities", "revenue", "net income",
        "total assets", "summary", "creditlens", "rabodet", "statement date",
    ]
    ignore_context = [
        "prepared:", "prepared ", "printed:", "print date",
        "generated:", "generated ", "exported:", "exported ",
    ]

    for page in selected_pages:
        text = page.get("text", "") or ""
        lower = text.lower()
        if not any(ctx in lower for ctx in financial_context):
            continue
        for pattern in year_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                year = int(match.group(1))
                if not (2010 <= year <= 2035):
                    continue
                start = max(0, match.start() - 40)
                end = min(len(lower), match.end() + 10)
                nearby = lower[start:end]
                if any(ctx in nearby for ctx in ignore_context):
                    continue
                candidates[year] += 1

    if not candidates:
        return []
    top = [y for y, _ in candidates.most_common(2)]
    return sorted(top, reverse=True)

def answer_questions(state: FinancialGraphState) -> dict:
    excel_data = state.get("excel_data", [])
    errors = list(state.get("errors", []))
    selected_pages = state.get("selected_pages", [])
    use_rag = state.get("use_rag", False)
    rag_collection_name = state.get("rag_collection_name")

    if not selected_pages:
        empty = align_answers_to_template(excel_data, [])
        return {
            "original_answers": empty,
            "answers": empty,
            "answers_by_year": {},
            "years": [],
            "errors": errors + ["Extraction skipped because no template-relevant pages were selected."],
        }

    years = detect_years(selected_pages) or [None]

    llm = state.get("llm")
    structured_llm = llm.with_structured_output(MultiYearExtractionResponse)

    pdf_file_name = state.get("pdf_file_name", "")
    settings = get_settings()
    source_link = settings.sharepoint_link + pdf_file_name.replace(" ", "%20")

    USER_PROMPT = get_user_prompt(excel_data)

    # ---------- Context building (RAG or full) ----------
    alias_hints = ""
    if use_rag and rag_collection_name:
        try:
            rag_config = state.get("rag_config") or {
                **DEFAULT_RAG_CONFIG,
                "llm_model": settings.azure_openai_deployment,
            }
            # Physical PDF pages (1-based) so every retrieved passage gets inline [Page N] markers
            # for the page it really comes from (the page stored in the index is often off).
            pdf_pages = state.get("pdf_pages") or []
            page_texts = {}
            for i, page in enumerate(pdf_pages):
                record = _to_page_record(page, i)
                page_texts[record["page_number"]] = record["text"]
            page_index = build_page_index(page_texts) if page_texts else None

            # Targeted alias queries (Other Labour Costs, General Costs, Depreciation, ...) + generic query
            full_context, alias_hints, _ = build_context(
                rag_collection_name, rag_config, excel_data, years, page_index=page_index
            )
        except Exception as exc:
            errors.append(f"RAG retrieval failed, using selected pages instead: {exc}")
            full_context = ""

        if not full_context:
            full_context = "\n\n".join(
                [
                    f"--- PDF Page {page.get('page_number', i + 1)} ---\n{page.get('text', '')}"
                    for i, page in enumerate(selected_pages)
                ]
            )
    else:
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
        "Return numeric answers with digits and thousand separators exactly as they appear (e.g. 13,950); "
        "apply the sign convention of the system prompt (costs/expenses positive, no parentheses). "
        "Do not remove commas or convert to plain integers. "
        "For source_text, return the COMPLETE table or paragraph from the context that you used (not just a single line). "
        "Prefer the primary consolidated statements over notes or company-only statements when both show the figure."
        if years != [None]
        else (
            "Extract the most recent period available. "
            "Return numeric answers with digits and thousand separators exactly as they appear; "
            "apply the sign convention of the system prompt (costs/expenses positive, no parentheses). "
            "For source_text, return the COMPLETE table or paragraph from the context that you used."
        )
    )

    user_content = (
        f"Please extract the following variables:\n{USER_PROMPT}\n\n"
        f"{year_instruction}\n\n"
        + (f"Line-item aliases (use these to map report labels to template variables):\n{alias_hints}\n\n" if alias_hints else "")
        + "Use only the supplied document context. "
        "For page_number, return the physical PDF page number: the context has [Page N] markers "
        "(text after a marker comes from page N until the next marker) or '--- PDF Page N ---' headers; "
        "use the nearest one before the line the value was taken from.\n\n"
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

            answer.source_link = build_hyperlink(answer.page_number, source_link)
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