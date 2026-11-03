"""Node: Answer Questions using LLM.

Supports:
- Full-context fallback (original behaviour)
- Per-metric RAG retrieval
- Richer source_text from retrieved chunks
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
from custom_lcel_components.chains import get_sentence_window_rag_chain_from_config

# Keep the same config as the RAG node
RAG_CONFIG = {
    "llm_model": "gpt-5.2",
    "llm_model_agent": "gpt-5.4",
    "temperature": 0,
    "top_p": 1,
    "embedding_model_name": "text-embedding-3-large",
    "pdf_loader_type": "PyMuPDFLoader",
    "include_source": False,
    "hybrid_search_args": None,
    "remove_duplicate_chunks": True,
    "sentence_chunker_window_size": 5,
    "similarity_top_k": 20,
    "source_key": "selected_pages_source",
    "rerank_args": {"top_n": 10, "model": "cross-encoder/ms-marco-MiniLM-L-2-v2"},
}

def build_hyperlink(page_number: Optional[int], source_link: str) -> str:
    if page_number is not None and page_number != -1 and source_link:
        return f'=HYPERLINK("{source_link}#page={page_number}", "Page {page_number}")'
    return "N/A"

def align_answers_to_template(
    excel_data: List[Dict[str, Any]],
    extracted_answers: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    answer_map = {
        (a["worksheet"], a["variable"]): a
        for a in extracted_answers
        if (a["worksheet"], a["variable"]) in {
            (m["worksheet"], m["variable"]) for m in excel_data
        }
    }

    final_answers = []
    for metric in excel_data:
        key = (metric["worksheet"], metric["variable"])
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

def retrieve_context_for_metric(
    rag_qa_chain,
    collection_name: str,
    metric: Dict[str, Any],
    years: List,
) -> str:
    """Per-metric retrieval."""
    query = (
        f"Find the complete table or paragraph that contains the value for "
        f"'{metric['variable']}' (description: {metric.get('description', '')}). "
        f"Years of interest: {years}. "
        f"Return the full surrounding context (complete table or paragraph), not just a single line."
    )
    try:
        result = rag_qa_chain.invoke({
            "question": query,
            "collection_name": collection_name,
        })
        # Adjust key names to match what your RAG chain actually returns
        return result.get("context") or result.get("source_documents") or result.get("answer") or ""
    except Exception:
        return ""

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
    if use_rag and rag_collection_name:
        _, _, rag_qa_chain = get_sentence_window_rag_chain_from_config(RAG_CONFIG)

        # Per-metric retrieval (optional improvement)
        metric_contexts = {}
        for metric in excel_data:
            ctx = retrieve_context_for_metric(rag_qa_chain, rag_collection_name, metric, years)
            metric_contexts[(metric["worksheet"], metric["variable"])] = ctx

        # Combine retrieved contexts (deduplicated)
        unique_contexts = []
        seen = set()
        for ctx in metric_contexts.values():
            if ctx and ctx not in seen:
                seen.add(ctx)
                unique_contexts.append(ctx)

        full_context = "\n\n--- Retrieved Context ---\n".join(unique_contexts) if unique_contexts else ""
        if not full_context:
            # fallback inside RAG path
            full_context = "\n\n".join(
                [f"--- PDF Page {p.get('page_number', i+1)} ---\n{p.get('text', '')}"
                 for i, p in enumerate(selected_pages)]
            )
    else:
        # Original full-context path
        full_context = "\n\n".join(
            [f"--- PDF Page {p.get('page_number', i+1)} ---\n{p.get('text', '')}"
             for i, p in enumerate(selected_pages)]
        )

    year_instruction = (
        f"Extract every variable only for these years: {years}. "
        "Do not include any other years. "
        "Return one answer object per variable per year. "
        "Include the year field on every answer. "
        "Return numeric answers exactly as they appear in the source document, including thousand separators (e.g. 13,950). "
        "Do not remove commas or convert to plain integers. "
        "For source_text, return the COMPLETE table or paragraph from the context that you used (not just a single line)."
        if years != [None]
        else (
            "Extract the most recent period available. "
            "Return numeric answers exactly as they appear in the source document, including thousand separators. "
            "For source_text, return the COMPLETE table or paragraph from the context that you used."
        )
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