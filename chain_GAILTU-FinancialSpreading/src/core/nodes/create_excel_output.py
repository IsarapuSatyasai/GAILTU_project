"""Create template-aligned Excel output."""

import pandas as pd

from graph.graph_state import FinancialGraphState
from template.excel_writer import excel_write


def align_answers_to_template(
    excel_data,
    answers,
):
    """Ensure final output contains exactly template metrics."""

    answer_map = {
        (
            answer["worksheet"],
            answer["variable"],
        ): answer
        for answer in answers
    }

    aligned = []

    for metric in excel_data:
        key = (
            metric["worksheet"],
            metric["variable"],
        )

        answer = answer_map.get(key, {})

        aligned.append(
            {
                "worksheet": metric["worksheet"],
                "variable": metric["variable"],
                "answer": answer.get(
                    "answer",
                    "N/A",
                ),
                "confidence": answer.get(
                    "confidence",
                    0.0,
                ),
                "page_number": answer.get(
                    "page_number",
                    -1,
                ),
                "source_fields": answer.get(
                    "source_fields",
                    [],
                ),
                "formula": answer.get(
                    "formula",
                ),
                "source_link": answer.get(
                    "source_link",
                    "N/A",
                ),
                "source_heading": answer.get(
                    "source_heading",
                ),
                "source_text": answer.get(
                    "source_text",
                ),
            }
        )

    return aligned


def build_comparison_dataframes(
    excel_data,
    original_answers,
    final_answers,
    baseline_pages,
    improved_pages,
):
    """Create comparison worksheets."""

    original_map = {
        (
            answer["worksheet"],
            answer["variable"],
        ): answer
        for answer in original_answers
    }

    final_map = {
        (
            answer["worksheet"],
            answer["variable"],
        ): answer
        for answer in final_answers
    }

    baseline_numbers = {
        page.get("page_number")
        for page in baseline_pages
    }

    improved_numbers = {
        page.get("page_number")
        for page in improved_pages
    }

    comparison_data = {}

    for metric in excel_data:
        worksheet = metric["worksheet"]

        key = (
            worksheet,
            metric["variable"],
        )

        original = original_map.get(key, {})
        final = final_map.get(key, {})

        original_answer = original.get(
            "answer",
            "N/A",
        )

        refined_answer = final.get(
            "answer",
            original_answer,
        )

        confidence = original.get(
            "confidence",
            0.0,
        )

        original_page = original.get(
            "page_number",
            -1,
        )

        refined_page = final.get(
            "page_number",
            original_page,
        )

        original_source_fields = original.get(
            "source_fields",
            [],
        )

        refined_source_fields = final.get(
            "source_fields",
            original_source_fields,
        )

        original_formula = original.get(
            "formula",
        )

        refined_formula = final.get(
            "formula",
            original_formula,
        )

        original_source_link = original.get(
            "source_link",
            "N/A",
        )

        refined_source_link = final.get(
            "source_link",
            original_source_link,
        )

        baseline_page = original_page
        improved_page = refined_page

        baseline_selected = (
            baseline_page in baseline_numbers
        )

        improved_selected = (
            improved_page in improved_numbers
        )

        page_changed = (
            baseline_page != improved_page
        )

        changed = (
            original_answer != refined_answer
            or page_changed
            or (
                original_source_fields
                != refined_source_fields
            )
            or (
                original_formula
                != refined_formula
            )
            or (
                original_source_link
                != refined_source_link
            )
        )

        row = {
            "variable": metric["variable"],
            "answer_original": original_answer,
            "answer_refined": refined_answer,
            "confidence": confidence,
            "baseline_page": baseline_page,
            "improved_page": improved_page,
            "page_changed": page_changed,
            "baseline_selected": baseline_selected,
            "improved_selected": improved_selected,
            "source_fields_original": (
                original_source_fields
            ),
            "source_fields_refined": (
                refined_source_fields
            ),
            "formula_original": original_formula,
            "formula_refined": refined_formula,
            "source_link_original": (
                original_source_link
            ),
            "source_link_refined": (
                refined_source_link
            ),
        }

        comparison_data.setdefault(
            worksheet,
            [],
        ).append(row)

    return {
        worksheet: pd.DataFrame(rows)
        for worksheet, rows in comparison_data.items()
    }


def build_page_selection_comparison(pdf_pages, selected_pages):
    """Build a page-by-page selection validation report."""

    selected_numbers = {
        page.get("page_number")
        for page in selected_pages
    }

    rows = []

    for page in pdf_pages:
        page_number = page.get("page_number")
        is_selected = page_number in selected_numbers

        rows.append(
            {
                "Page Number": page_number,
                "Selected": (
                    "Selected" if is_selected else "Not Selected"
                ),
                "Exact Reason": page.get(
                    "selection_reason",
                    "Selection evidence was not recorded.",
                ),
            }
        )

    return pd.DataFrame(
        rows,
        columns=["Page Number", "Selected", "Exact Reason"],
    )


def create_excel_output(
    state: FinancialGraphState,
):
    """Create Excel output using template-defined metrics."""

    excel_data = state.get(
        "excel_data",
        [],
    )

    original_answers = state.get(
        "original_answers",
        [],
    )

    answers = state.get(
        "answers",
        [],
    )

    output_path = state.get(
        "output_path",
        "",
    )

    pdf_file_name = state.get(
        "pdf_file_name",
        "",
    )

    if not excel_data:
        return {
            "output_excel": "",
            "comparison_excel": "",
            "errors": state.get(
                "errors",
                [],
            ) + [
                "No template metrics available for Excel output."
            ],
        }

    if not answers:
        answers = []

    output_name = (
        pdf_file_name.removeprefix(
            "InputData"
        ).removesuffix(
            ".pdf"
        )
        + ".xlsx"
    )

    output_excel = (
        output_path.rstrip("/")
        + "/"
        + output_name
    )

    comparison_name = (
        pdf_file_name.removeprefix("InputData").removesuffix(".pdf")
        + "-page-selection.xlsx"
    )

    comparison_excel = (
        output_path.rstrip("/")
        + "/"
        + comparison_name
    )

    years = sorted(
        [y for y in state.get("years", []) if y is not None],
        reverse=True,
    )
    answers_by_year = state.get("answers_by_year", {})

    if not years and answers:
        years = [None]

    worksheet_dict = {}

    for metric in excel_data:
        worksheet = metric["worksheet"]
        variable = metric["variable"]

        row = {"variable": variable, "Remarks": ""}

        for year in years:
            year_answers = answers_by_year.get(year, [])
            match = next(
                (a for a in year_answers if a.get("variable") == variable),
                {},
            )
            prefix = f"{year}_" if year is not None else ""
            row[f"{prefix}answer"] = match.get("answer", "N/A")
            row[f"{prefix}confidence"] = match.get("confidence", 0.0)
            row[f"{prefix}page_number"] = match.get("page_number", -1)
            row[f"{prefix}source_fields"] = match.get("source_fields", [])
            row[f"{prefix}formula"] = match.get("formula")
            row[f"{prefix}source_link"] = match.get("source_link", "N/A")
            row[f"{prefix}source_heading"] = match.get("source_heading")
            row[f"{prefix}source_text"] = match.get("source_text")

        worksheet_dict.setdefault(
            worksheet,
            [],
        ).append(row)

    worksheet_dict = {
        worksheet: pd.DataFrame(rows)
        for worksheet, rows in worksheet_dict.items()
    }

    page_selection_comparison = build_page_selection_comparison(
        state.get("pdf_pages", []),
        state.get("selected_pages", []),
    )
    comparison_dict = {
        "Page Selection": page_selection_comparison,
    }

    try:
        print(
            f"Creating Excel output: {output_excel}"
        )

        print(
            f"Creating comparison output: {comparison_excel}"
        )

        print(
            f"Template metrics: {len(excel_data)}"
        )

        print(
            f"Final answers: {len(answers)}"
        )

        print(
            f"Worksheets: {list(worksheet_dict.keys())}"
        )

        print(
            f"Comparison worksheets: "
            f"{list(comparison_dict.keys())}"
        )

        status = excel_write(
            dataframes=worksheet_dict,
            output_path=output_excel,
        )

        comparison_status = excel_write(
            dataframes=comparison_dict,
            output_path=comparison_excel,
        )

        return {
            "output_excel": status,
            "comparison_excel": comparison_status,
            "errors": state.get(
                "errors",
                [],
            ),
        }

    except Exception as exc:
        error = f"Error writing excel file: {exc}"

        print(error)

        return {
            "output_excel": "",
            "comparison_excel": "",
            "errors": state.get(
                "errors",
                [],
            ) + [error],
        }