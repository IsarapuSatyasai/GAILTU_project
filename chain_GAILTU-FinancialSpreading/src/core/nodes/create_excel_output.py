"""Create template-aligned Excel output."""

import pandas as pd

from graph.graph_state import FinancialGraphState
from template.excel_writer import excel_write

def _safe_source_fields(val):
    if isinstance(val, (list, tuple)):
        return list(val)
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return []
    return [str(val)]

def _safe_text(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val)

def create_excel_output(state: FinancialGraphState):
    """Create Excel output using template-defined metrics."""

    excel_data = state.get("excel_data", [])
    answers = state.get("answers", [])
    output_path = state.get("output_path", "")
    pdf_file_name = state.get("pdf_file_name", "")
    errors = list(state.get("errors", []))

    if not excel_data:
        return {
            "output_excel": "",
            "comparison_excel": "",
            "errors": errors + ["No template metrics available for Excel output."],
        }

    output_name = (
        pdf_file_name.removeprefix("InputData").removesuffix(".pdf") + ".xlsx"
    )
    output_excel = output_path.rstrip("/") + "/" + output_name

    comparison_name = (
        pdf_file_name.removeprefix("InputData").removesuffix(".pdf")
        + "-page-selection.xlsx"
    )
    comparison_excel = output_path.rstrip("/") + "/" + comparison_name

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
            row[f"{prefix}source_fields"] = _safe_source_fields(match.get("source_fields"))
            row[f"{prefix}formula"] = _safe_text(match.get("formula"))
            row[f"{prefix}source_link"] = _safe_text(match.get("source_link") or "N/A")
            row[f"{prefix}source_heading"] = _safe_text(match.get("source_heading"))
            row[f"{prefix}source_text"] = _safe_text(match.get("source_text"))

        worksheet_dict.setdefault(worksheet, []).append(row)

    worksheet_dict = {
        worksheet: pd.DataFrame(rows)
        for worksheet, rows in worksheet_dict.items()
    }

    # Page selection comparison sheet
    selected_numbers = {p.get("page_number") for p in state.get("selected_pages", [])}
    page_rows = []
    for page in state.get("pdf_pages", []):
        page_number = page.get("page_number")
        page_rows.append({
            "Page Number": page_number,
            "Selected": "Selected" if page_number in selected_numbers else "Not Selected",
            "Exact Reason": page.get("selection_reason", "Selection evidence was not recorded."),
        })
    comparison_dict = {
        "Page Selection": pd.DataFrame(page_rows, columns=["Page Number", "Selected", "Exact Reason"])
    }

    try:
        print(f"Creating Excel output: {output_excel}")
        print(f"Template metrics: {len(excel_data)}")
        print(f"Years: {years}")
        print(f"Worksheets: {list(worksheet_dict.keys())}")

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
            "errors": errors,
        }

    except Exception as exc:
        error = f"Error writing excel file: {exc}"
        print(error)
        return {
            "output_excel": "",
            "comparison_excel": "",
            "errors": errors + [error],
        }