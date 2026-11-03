"""Select and categorize relevant annual report pages."""

import re
from collections import deque
from collections.abc import Mapping

from config import get_settings
from graph.graph_state import FinancialGraphState
from prompts.selected_keywords import (
    ACCOUNTING_POLICY_TERMS,
    COMPANY_METADATA_TERMS,
    FINANCIAL_SUMMARY_TERMS,
    LOW_VALUE_SECTION_TERMS,
    MANAGEMENT_DISCUSSION_TERMS,
    METRIC_SYNONYM_GROUPS,
    NOTE_SECTION_TERMS,
    SECTION_CATEGORY_TERMS,
    contains_phrase,
    financial_year_count,
    matched_phrases,
    normalize_text,
    numeric_density,
    page_relevance_score,
    page_score,
    table_structure_score,
)


CATEGORY_ORDER = [
    "company_metadata",
    "auditor_report",
    "income_statement",
    "balance_sheet",
    "cash_flow",
    "changes_in_equity",
    "notes_income_statement",
    "notes_balance_sheet",
    "notes_cash_flow",
    "accounting_policies",
    "financial_summary",
    "other_financial_notes",
    "financial_continuation",
]

PRIMARY_CATEGORIES = {
    "income_statement",
    "balance_sheet",
    "cash_flow",
    "changes_in_equity",
}

HIGH_PRIORITY_CATEGORIES = PRIMARY_CATEGORIES | {
    "company_metadata",
    "auditor_report",
}

FINANCIAL_CATEGORIES = PRIMARY_CATEGORIES | {
    "notes_income_statement",
    "notes_balance_sheet",
    "notes_cash_flow",
    "accounting_policies",
    "other_financial_notes",
}

GENERIC_METRIC_LABELS = {
    "other",
    "type",
    "currency",
    "conversion rate",
    "date",
    "name",
    "country",
    "company",
    "period",
    "unit",
    "description",
}

CONTINUATION_MARKERS = [
    "continued",
    "continuation",
    "cont'd",
    "contd",
    "carried forward",
    "brought forward",
    "balance brought forward",
]


def _to_page_record(page, index):
    """Normalize page objects and retain their physical PDF page number."""

    if isinstance(page, Mapping):
        record = dict(page)
        raw_metadata = record.get("metadata")
        text = record.get("text")

        if text is None:
            text = record.get("page_content", "")
    else:
        record = {}
        raw_metadata = getattr(page, "metadata", None)
        text = getattr(page, "page_content", "")

    metadata = (
        dict(raw_metadata)
        if isinstance(raw_metadata, Mapping)
        else {}
    )

    def to_int(value):
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    existing_number = to_int(record.get("page_number"))
    metadata_page = to_int(metadata.get("page"))
    metadata_page_number = to_int(metadata.get("page_number"))

    if existing_number is not None and existing_number >= 1:
        page_number = existing_number
    elif metadata_page is not None and metadata_page >= 0:
        page_number = metadata_page + 1
    elif (
        metadata_page_number is not None
        and metadata_page_number >= 1
    ):
        page_number = metadata_page_number
    else:
        page_number = index + 1

    text = str(text or "")
    metadata["page_number"] = page_number

    record["text"] = text
    record["page_content"] = text
    record["metadata"] = metadata
    record["page_number"] = page_number

    return record


def _metric_terms(variable):
    """Return exact metric names and configured synonyms."""

    base_term = normalize_text(variable)

    if not base_term or base_term in GENERIC_METRIC_LABELS:
        return set()

    terms = {base_term}

    for group in METRIC_SYNONYM_GROUPS:
        normalized_group = {
            normalize_text(term)
            for term in group
        }

        if base_term in normalized_group:
            terms.update(normalized_group)

    return terms


def _metric_family(metric):
    """Infer the financial family used to categorize a matched metric."""

    worksheet = normalize_text(metric.get("worksheet", ""))
    variable = normalize_text(metric.get("variable", ""))
    text = f"{worksheet} {variable}"

    if any(
        contains_phrase(text, term)
        for term in [
            "cash flow",
            "operating activities",
            "investing activities",
            "financing activities",
            "net cash flow",
        ]
    ):
        return "notes_cash_flow"

    if any(
        contains_phrase(text, term)
        for term in [
            "balance sheet",
            "financial position",
            "assets",
            "liabilities",
            "receivables",
            "payables",
            "equity",
            "borrowings",
            "debt",
            "inventory",
            "inventories",
            "provisions",
            "share capital",
            "retained earnings",
        ]
    ):
        return "notes_balance_sheet"

    if any(
        contains_phrase(text, term)
        for term in [
            "income statement",
            "profit and loss",
            "revenue",
            "sales",
            "turnover",
            "expenses",
            "cost of sales",
            "profit",
            "loss",
            "income",
            "tax",
            "earnings",
            "ebit",
            "ebitda",
            "depreciation",
            "amortisation",
            "amortization",
        ]
    ):
        return "notes_income_statement"

    return "other_financial_notes"


def _build_template_metrics(excel_data):
    """Prepare template variables without adding new extraction metrics."""

    template_metrics = []

    for metric in excel_data:
        variable = str(metric.get("variable") or "").strip()
        worksheet = str(metric.get("worksheet") or "").strip()

        if not variable:
            continue

        template_metrics.append(
            {
                "key": (worksheet, variable),
                "label": f"{worksheet}::{variable}",
                "terms": _metric_terms(variable),
                "family": _metric_family(metric),
            }
        )

    return template_metrics


def _find_metric_matches(normalized_text, template_metrics):
    """Find template metrics by exact phrase or configured synonym."""

    matched_keys = set()
    matched_labels = []
    matched_families = set()

    for metric in template_metrics:
        if not any(
            contains_phrase(normalized_text, term)
            for term in metric["terms"]
        ):
            continue

        matched_keys.add(metric["key"])
        matched_labels.append(metric["label"])
        matched_families.add(metric["family"])

    return matched_keys, matched_labels, matched_families


def _page_heading_categories(text, page_number):
    """Identify explicit section headings and report metadata."""

    heading_text = "\n".join(str(text).splitlines()[:25])[:3000]
    categories = set()

    for category, terms in SECTION_CATEGORY_TERMS.items():
        if matched_phrases(heading_text, terms):
            categories.add(category)

    # Report titles usually appear near the beginning of a PDF.
    # Do not classify later pages just because a header repeats the title.
    if 1 <= page_number <= 3:
        report_title_terms = [
            "annual report",
            "integrated report",
            "annual financial report",
        ]

        is_report_title = any(
            contains_phrase(heading_text, term)
            for term in report_title_terms
        )

        is_contents_page = contains_phrase(
            heading_text,
            "table of contents",
        ) or contains_phrase(heading_text, "contents")

        if is_report_title and not is_contents_page:
            categories.add("company_metadata")

    return categories


def _has_note_heading(text):
    """Check whether a page appears to belong to a notes section."""

    heading_text = "\n".join(str(text).splitlines()[:20])[:2500]

    return bool(matched_phrases(heading_text, NOTE_SECTION_TERMS))


def _has_numeric_table_evidence(signals):
    """Identify numeric or tabular content without relying on keywords alone."""

    density = signals["numeric_density"]
    table_score = signals["table_structure_score"]
    has_financial_terms = bool(
        signals["keyword_matches"]
        or signals["strong_matches"]
        or signals["unit_matches"]
    )

    if density >= 0.035 and table_score >= 0.6:
        return True

    if density >= 0.07 and table_score >= 0.4:
        return True

    if density >= 0.12 and has_financial_terms:
        return True

    return False


def _is_low_value_heading(text):
    """Detect sections that may be excluded when they lack useful data."""

    terms = (
        LOW_VALUE_SECTION_TERMS
        + MANAGEMENT_DISCUSSION_TERMS
    )

    return bool(matched_phrases(text, terms))


def _should_keep_page(info):
    """Apply staged inclusion and confident-exclusion rules."""

    text = info["page"]["text"]
    categories = info["categories"]
    signals = info["signals"]
    matched_keys = info["matched_keys"]

    has_table_evidence = _has_numeric_table_evidence(signals)
    has_note_heading = info["has_note_heading"]

    # Template matches and core report sections take priority.
    if matched_keys:
        info["selection_reason"] = "template_metric_match"
        return True

    if categories & HIGH_PRIORITY_CATEGORIES:
        info["selection_reason"] = "identified_report_section"
        return True

    is_low_value = _is_low_value_heading(text)

    # Narrative pages should not be kept solely for generic keywords.
    # Numeric tables or matched metrics override this exclusion.
    if is_low_value and not has_table_evidence:
        info["selection_reason"] = "excluded_low_value_narrative"
        return False

    # Notes and accounting policies are useful when they contain
    # numerical evidence or a clear financial signal.
    if (
        has_note_heading
        and (
            has_table_evidence
            or signals["keyword_matches"]
            or signals["unit_matches"]
        )
    ):
        info["selection_reason"] = "financial_notes"
        return True

    if (
        "accounting_policies" in categories
        and (
            has_table_evidence
            or signals["strong_matches"]
        )
    ):
        info["selection_reason"] = "accounting_policy_content"
        return True

    if (
        "financial_summary" in categories
        and has_table_evidence
    ):
        info["selection_reason"] = "numeric_financial_summary"
        return True

    # Retain other pages when financial terminology is supported
    # by numeric, year, unit, or table-layout evidence.
    has_financial_signal = bool(
        signals["keyword_matches"]
        or signals["unit_matches"]
        or signals["year_count"] >= 2
    )

    if has_table_evidence and has_financial_signal:
        info["selection_reason"] = "financial_table_evidence"
        return True

    # Keep a table with multiple years even when keyword extraction
    # is weak; it may contain a continuation or a differently named metric.
    if (
        signals["year_count"] >= 2
        and signals["numeric_density"] >= 0.04
        and signals["table_structure_score"] >= 0.5
    ):
        info["selection_reason"] = "multi_year_numeric_table"
        return True

    info["selection_reason"] = "insufficient_financial_evidence"
    return False

def _build_page_decision_reason(info, is_selected):
    """Explain the actual selection decision without scores."""

    page = info["page"]
    text = page["text"]
    page_number = page["page_number"]
    signals = info["signals"]
    categories = set(info["categories"])

    matched_metrics = info["matched_metrics"]
    keywords = signals["keyword_matches"]
    strong_matches = signals["strong_matches"]
    unit_matches = signals["unit_matches"]
    low_value_matches = signals["low_value_matches"]

    has_table = _has_numeric_table_evidence(signals)
    has_note_heading = info["has_note_heading"]

    heading_text = "\n".join(text.splitlines()[:25])[:3000]
    detected_headings = []

    for heading_category, terms in SECTION_CATEGORY_TERMS.items():
        matches = matched_phrases(heading_text, terms)
        if matches:
            detected_headings.extend(matches)

    report_title_matches = []
    if 1 <= page_number <= 3:
        report_title_matches = matched_phrases(
            heading_text,
            [
                "annual report",
                "integrated report",
                "annual financial report",
            ],
        )

    if info.get("added_as_continuation"):
        evidence = []

        markers = matched_phrases(text, CONTINUATION_MARKERS)
        if markers:
            evidence.append(
                f"continuation wording detected: {', '.join(markers)}"
            )

        if has_table:
            evidence.append(
                "the page contains numeric or table-like financial evidence"
            )

        if not evidence:
            evidence.append(
                "the adjacent page passed the existing financial "
                "continuation check"
            )

        return (
            "Selected as a continuation of a nearby selected financial page "
            "because " + " and ".join(evidence) + "."
        )

    if is_selected:
        if matched_metrics:
            return (
                "Selected because the page text matches these template "
                "metrics: " + ", ".join(matched_metrics) + "."
            )

        if "company_metadata" in categories and report_title_matches:
            return (
                "Selected because the opening page contains the report "
                f"title '{', '.join(report_title_matches)}'. The current "
                "selection rules classify this opening page as company "
                "metadata and include that category."
            )

        if categories.intersection(HIGH_PRIORITY_CATEGORIES):
            if detected_headings:
                return (
                    "Selected because the page contains a high-priority "
                    "report heading: "
                    + ", ".join(dict.fromkeys(detected_headings))
                    + "."
                )

            return (
                "Selected because the page was classified as a high-priority "
                "report section by the existing heading rules."
            )

        if has_note_heading and (
            has_table or keywords or unit_matches
        ):
            evidence = []
            if has_table:
                evidence.append("numeric or table-like financial evidence")
            if keywords:
                evidence.append(
                    "financial terms: " + ", ".join(keywords)
                )
            if unit_matches:
                evidence.append(
                    "financial units: " + ", ".join(unit_matches)
                )

            return (
                "Selected because a financial notes section was detected "
                "and supported by " + "; ".join(evidence) + "."
            )

        if (
            "accounting_policies" in categories
            and (has_table or strong_matches)
        ):
            evidence = (
                "numeric or table-like financial evidence"
                if has_table
                else "financial terms: " + ", ".join(strong_matches)
            )
            return (
                "Selected because accounting-policy content was detected "
                f"with supporting evidence: {evidence}."
            )

        if "financial_summary" in categories and has_table:
            return (
                "Selected because the page contains a financial-summary "
                "heading and numeric or table-like evidence."
            )

        if has_table and (keywords or unit_matches or signals["year_count"] >= 2):
            evidence = []
            if keywords:
                evidence.append(
                    "financial terms: " + ", ".join(keywords)
                )
            if unit_matches:
                evidence.append(
                    "financial units: " + ", ".join(unit_matches)
                )
            if signals["year_count"] >= 2:
                evidence.append("multiple financial years")

            return (
                "Selected because numeric or table-like financial evidence "
                "is supported by " + "; ".join(evidence) + "."
            )

        if (
            signals["year_count"] >= 2
            and signals["numeric_density"] >= 0.04
            and signals["table_structure_score"] >= 0.5
        ):
            return (
                "Selected because the page contains multiple financial "
                "years and meets the existing numeric-table requirements."
            )

        return (
            "Selected by the existing inclusion rules. Review the page's "
            "selection conditions because no specific matching rule was "
            "identified for this explanation."
        )

    if low_value_matches and not has_table:
        return (
            "Not selected because the page contains low-value or narrative "
            "content (" + ", ".join(low_value_matches) + ") without "
            "sufficient numeric or table-like evidence."
        )

    failed_checks = []

    if not matched_metrics:
        failed_checks.append("no template metrics matched")

    if not categories.intersection(HIGH_PRIORITY_CATEGORIES):
        if detected_headings:
            failed_checks.append(
                "no matching high-priority heading; detected headings: "
                + ", ".join(dict.fromkeys(detected_headings))
            )
        else:
            failed_checks.append(
                "no high-priority financial statement or report heading matched"
            )

    if not has_note_heading:
        failed_checks.append("no financial notes heading matched")
    elif not (has_table or keywords or unit_matches):
        failed_checks.append(
            "the notes heading lacked supporting financial terms or table evidence"
        )

    if "accounting_policies" not in categories:
        failed_checks.append("no accounting-policy heading matched")
    elif not (has_table or strong_matches):
        failed_checks.append(
            "accounting-policy content lacked supporting financial evidence"
        )

    if "financial_summary" not in categories:
        failed_checks.append("no financial-summary heading matched")
    elif not has_table:
        failed_checks.append(
            "the financial-summary page lacked numeric or table-like evidence"
        )

    if not (
        has_table
        and (keywords or unit_matches or signals["year_count"] >= 2)
    ):
        failed_checks.append(
            "the page did not meet the combined financial-table "
            "and supporting-signal requirement"
        )

    if not (
        signals["year_count"] >= 2
        and signals["numeric_density"] >= 0.04
        and signals["table_structure_score"] >= 0.5
    ):
        failed_checks.append(
            "the page did not meet the existing multi-year table requirement"
        )

    supporting_evidence = []
    if keywords:
        supporting_evidence.append(
            "financial terms found: " + ", ".join(keywords)
        )
    if unit_matches:
        supporting_evidence.append(
            "financial units found: " + ", ".join(unit_matches)
        )
    if strong_matches:
        supporting_evidence.append(
            "strong financial terms found: " + ", ".join(strong_matches)
        )

    reason = (
        "Not selected because none of the applicable inclusion rules passed. "
        + "; ".join(dict.fromkeys(failed_checks))
        + "."
    )

    if supporting_evidence:
        reason += (
            " Supporting evidence found but insufficient on its own: "
            + "; ".join(supporting_evidence)
            + "."
        )

    return reason

def _is_financial_continuation(info):
    """Check whether a neighbouring page looks like part of a financial table."""

    text = info["page"]["text"]
    signals = info["signals"]

    has_marker = bool(
        matched_phrases(text, CONTINUATION_MARKERS)
    )

    if (
        has_marker
        and signals["table_structure_score"] >= 0.5
    ):
        return True

    return _has_numeric_table_evidence(signals)


def _expand_financial_continuations(page_infos, selected_indices):
    """Retain adjacent table-like pages that may contain continued values."""

    queue = deque()

    for index in selected_indices:
        info = page_infos[index]

        is_financial_seed = bool(
            info["matched_keys"]
            or info["categories"] & PRIMARY_CATEGORIES
            or info["categories"] & FINANCIAL_CATEGORIES
        )

        if is_financial_seed:
            queue.append(index)

    visited = set(queue)

    while queue:
        current_index = queue.popleft()

        for neighbour_index in (
            current_index - 1,
            current_index + 1,
        ):
            if (
                neighbour_index < 0
                or neighbour_index >= len(page_infos)
                or neighbour_index in selected_indices
            ):
                continue

            neighbour = page_infos[neighbour_index]
            text = neighbour["page"]["text"]

            has_low_value_heading = _is_low_value_heading(text)
            has_table_evidence = _is_financial_continuation(neighbour)

            # A neighbouring narrative page is not added simply because
            # it is adjacent; it must also contain numeric/table evidence.
            if has_low_value_heading and not has_table_evidence:
                continue

            if not has_table_evidence:
                continue

            # neighbour["selection_reason"] = (
            #     "adjacent_financial_continuation"
            # )
            # neighbour["categories"].add(
            #     "financial_continuation"
            # )
            neighbour["added_as_continuation"] = True
            neighbour["categories"].add("financial_continuation")
            selected_indices.add(neighbour_index)

            if neighbour_index not in visited:
                queue.append(neighbour_index)
                visited.add(neighbour_index)


def _finalize_page_categories(info):
    """Assign a useful category to every selected page."""

    categories = set(info["categories"])
    matched_families = info["matched_families"]

    has_note_heading = info["has_note_heading"]

    if has_note_heading:
        categories.update(matched_families)

        if not matched_families:
            text = normalize_text(info["page"]["text"])

            balance_terms = [
                "assets",
                "liabilities",
                "receivables",
                "payables",
                "borrowings",
                "equity",
                "inventory",
            ]
            income_terms = [
                "revenue",
                "sales",
                "expenses",
                "profit",
                "loss",
                "tax",
                "earnings",
            ]
            cash_flow_terms = [
                "cash flow",
                "operating activities",
                "investing activities",
                "financing activities",
            ]

            if any(
                contains_phrase(text, term)
                for term in cash_flow_terms
            ):
                categories.add("notes_cash_flow")
            elif any(
                contains_phrase(text, term)
                for term in balance_terms
            ):
                categories.add("notes_balance_sheet")
            elif any(
                contains_phrase(text, term)
                for term in income_terms
            ):
                categories.add("notes_income_statement")
            else:
                categories.add("other_financial_notes")

    elif (
        not categories & PRIMARY_CATEGORIES
        and not categories & {
            "company_metadata",
            "auditor_report",
        }
    ):
        if info["matched_keys"]:
            categories.update(matched_families)
        elif not categories & {
            "accounting_policies",
            "financial_summary",
        }:
            categories.add("other_financial_notes")

    if not categories:
        categories.add("other_financial_notes")

    return sorted(categories)


def _baseline_selection(pdf_pages, settings):
    """Reproduce the existing selector for baseline comparison."""

    first_n_pages = max(
        0,
        int(getattr(settings, "first_n_pages", 0)),
    )
    threshold = float(
        getattr(settings, "page_score_threshold", 1)
    )

    baseline_pages = []

    for index, page in enumerate(pdf_pages):
        is_initial_page = index < first_n_pages
        has_keyword_score = (
            page_score(page.get("text", "")) > threshold
        )

        if is_initial_page or has_keyword_score:
            baseline_pages.append(page)

    # Deliberately no small-PDF full-document fallback.
    return baseline_pages


def select_pages(state: FinancialGraphState) -> dict:
    """Select relevant pages and return both categorized and flat outputs."""

    settings = get_settings()
    raw_pages = state.get("pdf_pages", [])
    excel_data = state.get("excel_data", [])
    errors = list(state.get("errors", []))

    pdf_pages = [
        _to_page_record(page, index)
        for index, page in enumerate(raw_pages)
    ]

    baseline_pages = _baseline_selection(
        pdf_pages,
        settings,
    )

    categorized_pages = {
        category: []
        for category in CATEGORY_ORDER
    }

    if not isinstance(excel_data, list) or not excel_data:
        errors.append(
            "Page selection requires template metrics in excel_data. "
            "Run read_creditlens_template before select_pages."
        )

        return {
            "pdf_pages": pdf_pages,
            "selected_pages": [],
            "baseline_selected_pages": baseline_pages,
            "categorized_pages": categorized_pages,
            "errors": errors,
        }

    template_metrics = _build_template_metrics(excel_data)
    page_infos = []

    # Stage 1: identify section headings, signals, and template matches.
    for index, page in enumerate(pdf_pages):
        text = page["text"]
        page_number = page["page_number"]

        normalized_text = normalize_text(text)

        matched_keys, matched_labels, matched_families = (
            _find_metric_matches(
                normalized_text,
                template_metrics,
            )
        )

        signals = page_relevance_score(text)

        info = {
            "index": index,
            "page": page,
            "categories": _page_heading_categories(
                text,
                page_number,
            ),
            "matched_keys": matched_keys,
            "matched_metrics": matched_labels,
            "matched_families": matched_families,
            "signals": signals,
            "has_note_heading": _has_note_heading(text),
            "selection_reason": None,
        }

        info["keep"] = _should_keep_page(info)
        page_infos.append(info)

    # Stage 2: keep adjacent table pages that may contain
    # the continuation of a relevant statement or financial note.
    selected_indices = {
        info["index"]
        for info in page_infos
        if info["keep"]
    }

    _expand_financial_continuations(
        page_infos,
        selected_indices,
    )

    # # Stage 3: attach final categories and retain document order.
    # selected_pages = []
    # matched_metric_keys = set()

    # for info in page_infos:
    #     if info["index"] not in selected_indices:
    #         continue

    #     page = info["page"]
    #     categories = _finalize_page_categories(info)

    #     page["categories"] = categories
    #     page["matched_metrics"] = info["matched_metrics"]
    #     page["selection_reason"] = info["selection_reason"]
    #     page["relevance_score"] = info["signals"]["score"]

    #     selected_pages.append(page)
    #     matched_metric_keys.update(info["matched_keys"])

    #     for category in categories:
    #         categorized_pages.setdefault(category, [])

    #         if page["page_number"] not in categorized_pages[category]:
    #             categorized_pages[category].append(
    #                 page["page_number"]
    #             )

# Stage 3: record selection evidence for every PDF page.
    selected_pages = []
    matched_metric_keys = set()

    for info in page_infos:
        page = info["page"]
        is_selected = info["index"] in selected_indices

        if is_selected:
            categories = _finalize_page_categories(info)
        else:
            categories = sorted(info["categories"])

        page["categories"] = categories
        page["selected"] = is_selected
        page["matched_metrics"] = info["matched_metrics"]
        page["matched_keywords"] = info["signals"]["keyword_matches"]
        page["strong_matches"] = info["signals"]["strong_matches"]
        page["unit_matches"] = info["signals"]["unit_matches"]
        page["low_value_matches"] = info["signals"]["low_value_matches"]
        page["numeric_density"] = info["signals"]["numeric_density"]
        page["table_structure_score"] = (
            info["signals"]["table_structure_score"]
        )
        page["financial_year_count"] = info["signals"]["year_count"]
        page["relevance_score"] = info["signals"]["score"]
        page["selection_reason"] = _build_page_decision_reason(
            info,
            is_selected,
        )

        if not is_selected:
            continue

        selected_pages.append(page)
        matched_metric_keys.update(info["matched_keys"])

        for category in categories:
            categorized_pages.setdefault(category, [])

            if page["page_number"] not in categorized_pages[category]:
                categorized_pages[category].append(page["page_number"])

    if not selected_pages:
        errors.append(
            "No pages met the financial-page selection rules. "
            "Review the template variable names and selection thresholds."
        )

    selected_page_numbers = [
        page["page_number"]
        for page in selected_pages
    ]

    print("Selected page numbers:", selected_page_numbers)
    print("Selected page count:", len(selected_pages))
    print(
        "Matched template metrics:",
        len(matched_metric_keys),
        "of",
        len(
            {
                metric["key"]
                for metric in template_metrics
            }
        ),
    )
    print("Categorized pages:", categorized_pages)

    for page in selected_pages:
        print(
            f"Page {page['page_number']}: "
            f"categories={page['categories']}, "
            f"reason={page['selection_reason']}"
        )

    return {
        "pdf_pages": pdf_pages,
        "selected_pages": selected_pages,
        "baseline_selected_pages": baseline_pages,
        "categorized_pages": categorized_pages,
        "errors": errors,
    }