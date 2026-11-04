"""Extract all template metrics using RAG context (same schema as the main pipeline)."""

import re
from collections import defaultdict
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from config import get_settings
from prompts.system_prompt import SYSTEM_PROMPT
from prompts.user_prompt import get_user_prompt
from models import MultiYearExtractionResponse
from rag_poc.retrieve import retrieve_context, build_page_index

# Targeted retrieval for metrics whose template names differ from annual-report wording.
# "queries": short, statement-style phrases (work best with embedding search + cross-encoder rerank).
# "aliases": labels the metric may appear under in the report; passed to the LLM as mapping hints.
METRIC_ALIAS_QUERIES = {
    "Other Labour Costs": {
        "queries": [
            "Employee benefits expense 2024 2023",
            "Staff costs wages and salaries social security pension costs",
            "Total labour costs consolidated income statement",
        ],
        "aliases": ["Employee benefits", "Staff costs", "Total labour costs", "Wages and salaries"],
    },
    "General Costs": {
        "queries": [
            "Other operating expenses 2024 2023",
            "General and administrative expenses breakdown",
            "Other expenses consolidated income statement",
        ],
        "aliases": ["Other operating expenses", "General and administrative expenses", "Administrative expenses", "Other expenses"],
    },
    "Depreciation": {
        "queries": [
            "Depreciation and amortization 2024 2023",
            "Depreciation of property plant and equipment",
            "Depreciation of right-of-use assets",
        ],
        "aliases": ["Depreciation", "Depreciation for the year", "Depreciation and amortisation"],
    },
    "Amortisation": {
        "queries": [
            "Depreciation and amortization 2024 2023",
            "Amortization of intangible assets",
            "Amortisation of capitalised development costs software",
        ],
        "aliases": ["Amortization", "Amortisation", "Amortization for the year", "Depreciation and amortisation"],
    },
    "Interest Received - cash": {
        "queries": [
            "Interest received consolidated statement of cash flows",
            "Interest income 2024 2023",
            "Finance income interest received",
        ],
        "aliases": ["Interest received", "Interest income", "Finance income"],
    },
    "Income from Other Finan Assets - cash": {
        "queries": [
            "Income from other financial assets",
            "Income from financial assets cash flow statement",
            "Dividends received financial assets",
        ],
        "aliases": ["Income from other financial assets", "Income from financial assets", "Dividends received"],
    },
}

# Upper bound on merged context size (characters) sent to the LLM.
MAX_CONTEXT_CHARS = 120_000


def _norm(name) -> str:
    """Normalise a variable name: non-breaking spaces to spaces, collapse whitespace, lowercase."""
    return " ".join(str(name).replace("\xa0", " ").split()).lower()


def _split_chunks(ctx) -> list:
    """Split retrieved context into passages so overlapping results can be de-duplicated."""
    if not ctx:
        return []
    if not isinstance(ctx, str):
        ctx = "\n\n".join(map(str, ctx))
    if "[Page " in ctx:  # page-labelled context from retrieve.py: keep each label with its passage
        return [c.strip() for c in re.split(r"\n\n(?=\[Page )", ctx) if c.strip()]
    sep = "\n\n" if "\n\n" in ctx else "\n"
    return [c.strip() for c in ctx.split(sep) if c.strip()]


def build_context(collection_name: str, config: dict, excel_data: list, years: list,
                  max_chars: int = MAX_CONTEXT_CHARS, page_index: dict = None):
    """Merge targeted alias-query context with the generic context, de-duplicated by passage.

    Targeted passages go first so they survive the max_chars cap.
    Returns (context, alias_hints, queries_used).
    """
    # Template names can carry trailing/non-breaking spaces (e.g. "Depreciation\xa0"), so match on
    # normalised names but keep the template's exact name for the LLM hints.
    template_vars = {_norm(m["variable"]): m["variable"] for m in excel_data}
    alias_metrics = {
        template_vars[_norm(v)]: spec
        for v, spec in METRIC_ALIAS_QUERIES.items()
        if _norm(v) in template_vars
    }

    queries = []
    for spec in alias_metrics.values():
        for q in spec["queries"]:
            if q not in queries:
                queries.append(q)

    variables = ", ".join(m["variable"] for m in excel_data[:60])
    generic_query = (
        f"Extract all financial statement values for years {years}. "
        f"Key variables: {variables}. "
        "Return the complete tables or paragraphs that contain these figures."
    )
    queries.append(generic_query)

    seen, chunks = set(), []
    for q in queries:
        for chunk in _split_chunks(retrieve_context(collection_name, q, config, page_index)):
            if chunk not in seen:
                seen.add(chunk)
                chunks.append(chunk)

    context, total = [], 0
    for chunk in chunks:
        if total + len(chunk) > max_chars:
            break
        context.append(chunk)
        total += len(chunk) + 2

    alias_hints = "\n".join(
        f"- {v.strip()}: may appear in the report as {', '.join(spec['aliases'])}"
        for v, spec in alias_metrics.items()
    )
    return "\n\n".join(context), alias_hints, queries


def extract_all(collection_name: str, config: dict, excel_data: list, years: list,
                page_texts: dict = None):
    """page_texts: optional {1-based page: text} of the source PDF (see retrieve.load_page_texts).
    When given, every context passage is labelled with the PDF page(s) it actually appears on."""
    settings = get_settings()
    llm = AzureChatOpenAI(
        azure_deployment=settings.azure_openai_deployment,
        api_version=settings.azure_openai_api_version,
        top_p=settings.llm_top_p,
    )
    structured_llm = llm.with_structured_output(MultiYearExtractionResponse)

    page_index = build_page_index(page_texts) if page_texts else None
    full_context, alias_hints, queries_used = build_context(
        collection_name, config, excel_data, years, page_index=page_index
    )

    USER_PROMPT = get_user_prompt(excel_data)
    year_instruction = (
        f"Extract every variable only for these years: {years}. "
        "Return one answer object per variable per year. "
        "Include the year field on every answer. "
        "Return numeric answers with digits and thousand separators exactly as they appear; "
        "apply the sign convention of the system prompt (costs/expenses positive, no parentheses). "
        "For source_text return the complete table or paragraph used. "
        "The document context contains [Page N] markers: text after a marker comes from PDF page N "
        "until the next marker. Set page_number to the N of the nearest [Page N] marker before the line "
        "the value was taken from. "
        "Prefer the primary consolidated statements over notes or company-only statements when both show the figure."
    )

    user_content = (
        f"Please extract the following variables:\n{USER_PROMPT}\n\n"
        f"{year_instruction}\n\n"
        + (f"Line-item aliases (use these to map report labels to template variables):\n{alias_hints}\n\n" if alias_hints else "")
        + "Use only the supplied document context.\n\n"
        f"Document context:\n{full_context}\n\n"
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]

    response = structured_llm.invoke(messages)

    answers_by_year = defaultdict(list)
    for answer in response.answers:
        if answer.year in years or years == [None]:
            answers_by_year[answer.year].append(answer.model_dump())

    aligned_by_year = {}
    for year, year_answers in answers_by_year.items():
        # Match on normalised names: the LLM often drops trailing/non-breaking spaces from template names
        answer_map = {(_norm(a["worksheet"]), _norm(a["variable"])): a for a in year_answers}
        aligned = []
        for metric in excel_data:
            key = (_norm(metric["worksheet"]), _norm(metric["variable"]))
            answer = answer_map.get(key)
            if answer is not None:
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
            aligned.append(answer)
        aligned_by_year[year] = aligned

    return {
        "years": years,
        "answers_by_year": aligned_by_year,
        "errors": response.errors,
        "context_length": len(full_context),
        "queries_used": queries_used,
    }