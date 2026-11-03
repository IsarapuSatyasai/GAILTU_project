"""Refine and verify existing financial extractions."""

from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from config import get_settings
from graph.graph_state import FinancialGraphState
from models import RefinementResponse
from nodes.answer_questions import build_hyperlink
from prompts.refinement_prompt import (
    REFINEMENT_SYSTEM_PROMPT,
    build_refinement_prompt,
)


# MAX_REFINEMENT_ATTEMPTS = 2


def _metric_key(metric: Dict[str, Any]) -> tuple:
    """Return the unique template key for a metric."""
    return (
        metric["worksheet"],
        metric["variable"],
    )


def _build_template_keys(
    excel_data: List[Dict[str, Any]],
) -> set:
    """Build allowed metric keys from the template."""
    return {
        _metric_key(metric)
        for metric in excel_data
    }


def _build_pdf_context(
    selected_pages: List[Dict[str, Any]],
) -> str:
    """Build PDF context for refinement."""
    return "\n\n".join(
        f'--- Page {page.get("page_number", index + 1)} ---\n'
        f'{page.get("text", "")}'
        for index, page in enumerate(selected_pages)
    )


def _select_metrics_for_refinement(
    excel_data: List[Dict[str, Any]],
    original_answers: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Select existing template metrics that need verification."""

    answer_map = {
        _metric_key(answer): answer
        for answer in original_answers
    }

    metrics = []

    for template_metric in excel_data:
        key = _metric_key(template_metric)
        answer = answer_map.get(key)

        if answer is None:
            answer = {
                "worksheet": template_metric["worksheet"],
                "variable": template_metric["variable"],
                "answer": "N/A",
                "confidence": 0.0,
                "page_number": -1,
                "source_fields": [],
                "formula": None,
            }

        metric = {
            **template_metric,
            **answer,
        }

        confidence = float(
            metric.get("confidence", 0.0)
        )

        if confidence > 0:
            metrics.append(metric)

    return metrics


def _normalize_answer(
    answer: Dict[str, Any],
    source_link: str,
) -> Dict[str, Any]:
    """Normalize refinement output."""

    if not answer.get("answer"):
        answer["answer"] = "N/A"

    if answer["answer"] == "N/A":
        answer["confidence"] = 0.0
        answer["page_number"] = -1
        answer["source_fields"] = []
        answer["formula"] = None
        answer["source_link"] = "N/A"

        return answer

    answer["source_link"] = build_hyperlink(
        answer.get("page_number"),
        source_link,
    )

    return answer


def _merge_refined_answers(
    excel_data: List[Dict[str, Any]],
    original_answers: List[Dict[str, Any]],
    refined_answers: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge refined values while preserving the template."""

    original_map = {
        _metric_key(answer): answer
        for answer in original_answers
    }

    refined_map = {
        _metric_key(answer): answer
        for answer in refined_answers
    }

    final_answers = []

    for template_metric in excel_data:
        key = _metric_key(template_metric)

        original = original_map.get(key, {})
        refined = refined_map.get(key)

        if refined and refined.get("is_supported"):
            selected = {
                **original,
                **refined,
            }
        else:
            selected = original.copy()

        selected["worksheet"] = template_metric["worksheet"]
        selected["variable"] = template_metric["variable"]

        if not selected.get("answer"):
            selected["answer"] = "N/A"

        final_answers.append(selected)

    return final_answers


# def confidence_refinement(
#     state: FinancialGraphState,
# ) -> dict:
#     """Run a maximum of two refinement attempts."""

#     llm = state.get("llm")

#     if llm is None:
#         return {
#             "answers": state.get("original_answers", []),
#             "refined_answers": [],
#             "errors": state.get("errors", []) + [
#                 "LLM not available for refinement."
#             ],
#         }

#     excel_data = state.get("excel_data", [])
#     original_answers = state.get("original_answers", [])
#     selected_pages = state.get("selected_pages", [])

#     settings = get_settings()

#     source_link = (
#         settings.sharepoint_link
#         + state.get("pdf_file_name", "").replace(" ", "%20")
#     )

#     metrics = _select_metrics_for_refinement(
#         excel_data,
#         original_answers,
#     )

#     if not metrics:
#         return {
#             "answers": original_answers,
#             "refined_answers": [],
#             "refinement_attempt": 0,
#         }

#     pdf_context = _build_pdf_context(selected_pages)

#     current_answers = metrics
#     all_refined_answers = []

#     for attempt in range(1, MAX_REFINEMENT_ATTEMPTS + 1):
#         prompt = build_refinement_prompt(
#             current_answers,
#             pdf_context,
#             attempt,
#         )

#         messages = [
#             SystemMessage(
#                 content=REFINEMENT_SYSTEM_PROMPT
#             ),
#             HumanMessage(content=prompt),
#         ]

#         try:
#             structured_llm = llm.with_structured_output(
#                 RefinementResponse
#             )

#             response = structured_llm.invoke(messages)

#         except Exception as exc:
#             error = (
#                 f"Refinement attempt {attempt} failed: {exc}"
#             )

#             return {
#                 "answers": state.get(
#                     "original_answers",
#                     [],
#                 ),
#                 "refined_answers": all_refined_answers,
#                 "refinement_attempt": attempt,
#                 "errors": state.get(
#                     "errors",
#                     [],
#                 ) + [error],
#             }

#         refined = [
#             _normalize_answer(
#                 answer.model_dump(),
#                 source_link,
#             )
#             for answer in response.answers
#         ]

#         all_refined_answers.extend(refined)

#         current_answers = [
#             {
#                 **metric,
#                 **refined_answer,
#             }
#             for metric in metrics
#             for refined_answer in refined
#             if _metric_key(metric)
#             == _metric_key(refined_answer)
#         ]

#         metrics = current_answers

#     final_answers = _merge_refined_answers(
#         excel_data,
#         original_answers,
#         all_refined_answers,
#    )

#     return {
#         "answers": final_answers,
#         "refined_answers": all_refined_answers,
#         "refinement_attempt": MAX_REFINEMENT_ATTEMPTS,
#         "errors": state.get("errors", []),
#     }

def confidence_refinement(
    state: FinancialGraphState,
) -> dict:
    """Run the configured number of refinement attempts."""

    settings = get_settings()

    # Skip refinement when attempts are set to zero.
    if settings.refinement_attempts <= 0:
        original_answers = state.get("original_answers", [])

        return {
            "answers": original_answers,
            "refined_answers": [],
            "refinement_attempt": 0,
            "errors": state.get("errors", []),
        }

    llm = state.get("llm")

    if llm is None:
        return {
            "answers": state.get("original_answers", []),
            "refined_answers": [],
            "errors": state.get("errors", []) + [
                "LLM not available for refinement."
            ],
        }

    excel_data = state.get("excel_data", [])
    original_answers = state.get("original_answers", [])
    selected_pages = state.get("selected_pages", [])

    source_link = (
        settings.sharepoint_link
        + state.get("pdf_file_name", "").replace(" ", "%20")
    )

    metrics = _select_metrics_for_refinement(
        excel_data,
        original_answers,
    )

    if not metrics:
        return {
            "answers": original_answers,
            "refined_answers": [],
            "refinement_attempt": 0,
        }

    pdf_context = _build_pdf_context(selected_pages)

    current_answers = metrics
    all_refined_answers = []

    for attempt in range(1, settings.refinement_attempts + 1):
        prompt = build_refinement_prompt(
            current_answers,
            pdf_context,
            attempt,
        )

        messages = [
            SystemMessage(
                content=REFINEMENT_SYSTEM_PROMPT
            ),
            HumanMessage(content=prompt),
        ]

        try:
            structured_llm = llm.with_structured_output(
                RefinementResponse
            )

            response = structured_llm.invoke(messages)

        except Exception as exc:
            error = (
                f"Refinement attempt {attempt} failed: {exc}"
            )

            return {
                "answers": state.get(
                    "original_answers",
                    [],
                ),
                "refined_answers": all_refined_answers,
                "refinement_attempt": attempt,
                "errors": state.get(
                    "errors",
                    [],
                ) + [error],
            }

        refined = [
            _normalize_answer(
                answer.model_dump(),
                source_link,
            )
            for answer in response.answers
        ]

        all_refined_answers.extend(refined)

        current_answers = [
            {
                **metric,
                **refined_answer,
            }
            for metric in metrics
            for refined_answer in refined
            if _metric_key(metric)
            == _metric_key(refined_answer)
        ]

        metrics = current_answers

    final_answers = _merge_refined_answers(
        excel_data,
        original_answers,
        all_refined_answers,
    )

    return {
        "answers": final_answers,
        "refined_answers": all_refined_answers,
        "refinement_attempt": settings.refinement_attempts,
        "errors": state.get("errors", []),
    }