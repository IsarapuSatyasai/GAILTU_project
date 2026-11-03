import re
from datetime import datetime
from typing import Any, Dict, Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt


def clean_responses(responses):
    """
    Clean response records.

    Removes duplicated headings from question/answer fields when the
    first line matches the last segment of the title hierarchy.

    Example:
        title  = "Business description$Introduction"
        answer = "## Introduction:\n- KLM was founded in 1919"

    becomes:

        answer = "- KLM was founded in 1919"
    """

    def is_header_line(title: str, line: str) -> bool:
        """
        Matches:
            Introduction
            Introduction:
            # Introduction
            ## Introduction
            **Introduction**
            ## Introduction:
        """
        pattern = (
            rf"^(?:#+\s*)?"
            rf"(?:\*\*)?\s*"
            rf"{re.escape(title)}"
            rf"\s*(?:\*\*)?"
            rf"(?::)?$"
        )

        return re.fullmatch(
            pattern,
            line.strip(),
            flags=re.IGNORECASE,
        ) is not None

    def clean_text(title: str, text: str) -> str:
        if not text:
            return text

        lines = str(text).splitlines()

        # Remove duplicated title only if there is actual content after it
        if len(lines) > 1 and is_header_line(title, lines[0]):
            text = "\n".join(lines[1:])
        else:
            text = str(text)

        # Remove markdown heading markers
        text = re.sub(r"(?m)^\s*#+\s*", "", text)

        # Convert **bold** -> plain text
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)

        # Collapse excessive blank lines
        text = re.sub(r"\n{2,}", "\n", text)

        return text.strip()

    cleaned = []

    for record in responses:
        record = dict(record)

        title_parts = [
            p.strip()
            for p in str(record.get("title", "")).split("$")
            if p.strip()
        ]

        current_title = title_parts[-1] if title_parts else ""

        if current_title:
            record["answer"] = clean_text(
                current_title,
                record.get("answer", ""),
            )

            record["question"] = clean_text(
                current_title,
                record.get("question", ""),
            )

        cleaned.append(record)

    return cleaned

def parse_markdown_table(markdown_text):
    """
    Parses a markdown table and returns a list of rows with cell values.

    Args:
        markdown_text (str): The markdown text containing the table.

    Returns:
        list: A list of rows, where each row is a list of cell values.
    """
    rows = [line.strip("|").split("|") for line in markdown_text.strip().split("\n")]
    return [list(map(str.strip, row)) for row in rows if len(row) > 1]


def string_to_docx(
    _dir: dict,
    generated_report_name,
    response_key="responses",
    table_font_size: int = 9,
    table_header_font_size: int | None = None,
):
    """
    Creates a Word document from a list of response dictionaries.

    Expected format:
        _dir[response_key] = [
            {
                "title": "Heading 1$Heading 2$Heading 3",
                "question": "optional question",
                "answer": "answer text",
                "page_no": "optional page reference"
            },
            ...
        ]

    The "$" in `title` defines the heading hierarchy.

    Parameters:
        _dir (dict): Dictionary containing response list under `response_key`.
        generated_report_name (str): The name/title of the generated report.
        response_key (str): Key containing the response list. Default is "responses".
        table_font_size (int): Font size for table body cells. Default is 9.
        table_header_font_size (int | None): Font size for table header cells.
                                            If None, uses table_font_size.
        include_question (bool): Whether to include the "question" field in the document.

    Returns:
        Document: A python-docx Document object.
    """

    if table_header_font_size is None:
        table_header_font_size = table_font_size

    def set_custom_font(run, font_name="Arial", font_size=10):
        """
        Applies font formatting to a given run.
        """
        font = run.font
        font.name = font_name
        font.size = Pt(font_size)
        run._element.rPr.rFonts.set(qn("w:eastAsia"), font_name)

    def add_paragraph_with_font(
        doc,
        text,
        font_size=10,
        italic=False,
        bold=False,
        alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
    ):
        """
        Adds a paragraph with consistent formatting.
        """
        para = doc.add_paragraph()
        para.paragraph_format.space_after = 0
        para.paragraph_format.space_before = 0
        para.alignment = alignment

        run = para.add_run(text)
        run.italic = italic
        run.bold = bold
        set_custom_font(run, font_size=font_size)

        return para

    def is_markdown_table_line(line: str) -> bool:
        """
        Detects markdown table rows.
        Example:
            | Column A | Column B |
            |----------|----------|
            | Value A  | Value B  |
        """
        stripped = line.strip()
        return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2

    def is_markdown_separator_row(row):
        """
        Detects markdown separator rows like:
            | --- | --- |
            | :--- | ---: |
        """
        return all(
            re.match(r"^:?-{3,}:?$", cell.strip()) is not None
            for cell in row
        )

    def create_table_from_markdown(doc, table_lines):
        """
        Creates a Word table from collected markdown table lines.
        """
        rows = parse_markdown_table("\n".join(table_lines))
        if not rows:
            return

        header = rows[0]

        # Remove markdown separator row if present
        body_rows = rows[1:]
        if body_rows and is_markdown_separator_row(body_rows[0]):
            body_rows = body_rows[1:]

        table = doc.add_table(rows=1, cols=len(header))
        table.style = "Table Grid"

        # Header row
        for idx, cell_data in enumerate(header):
            cell = table.rows[0].cells[idx]
            cell.text = str(cell_data)

            for paragraph in cell.paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                for run in paragraph.runs:
                    run.bold = True
                    set_custom_font(
                        run,
                        font_name="Arial",
                        font_size=table_header_font_size,
                    )

        # Body rows
        for row_data in body_rows:
            row = table.add_row()

            for idx in range(len(header)):
                cell_data = row_data[idx] if idx < len(row_data) else ""
                cell = row.cells[idx]
                cell.text = str(cell_data)

                for paragraph in cell.paragraphs:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    for run in paragraph.runs:
                        set_custom_font(
                            run,
                            font_name="Arial",
                            font_size=table_font_size,
                        )

        # Add a small spacer after the table
        spacer = doc.add_paragraph()
        spacer.paragraph_format.space_after = Pt(6)

    def add_text_with_tables(doc, text):
        """
        Adds normal text and markdown tables to the document.
        """
        if text is None:
            return

        text = str(text)
        lines = text.split("\n")

        table_lines = []

        for line in lines:
            if is_markdown_table_line(line):
                table_lines.append(line)
            else:
                if table_lines:
                    create_table_from_markdown(doc, table_lines)
                    table_lines = []

                if line.strip():
                    add_paragraph_with_font(doc, line)
                else:
                    doc.add_paragraph()

        if table_lines:
            create_table_from_markdown(doc, table_lines)

    def add_heading(doc, title, level):
        """
        Adds a heading with consistent font.
        Word supports heading levels 1-9.
        """
        level = min(max(level, 1), 9)
        heading = doc.add_heading(title, level=level)

        for run in heading.runs:
            set_custom_font(run)

        return heading

    def add_record_body(doc, record):
        """
        Adds question, answer, and page reference for one response record.
        """
        text = record.get("answer")
        page_ref = record.get("page_no")

        if text:
            add_text_with_tables(doc, text)

        if page_ref:
            add_paragraph_with_font(
                doc,
                f"Page reference: {page_ref}",
                font_size=9,
                italic=True,
                alignment=WD_ALIGN_PARAGRAPH.LEFT,
            )

    responses = _dir.get(response_key, [])
    responses = clean_responses(responses)

    if not isinstance(responses, list):
        raise TypeError(
            f"_dir[{response_key!r}] must be a list of dictionaries, "
            f"but got {type(responses).__name__}."
        )

    doc = Document()

    # Report title
    heading = doc.add_heading(str(generated_report_name), 0)
    for run in heading.runs:
        set_custom_font(run, font_size=26)

    # Date
    current_date = datetime.now().strftime("%Y-%m-%d")
    date_para = doc.add_paragraph(f"Date: {current_date}")
    for run in date_para.runs:
        set_custom_font(run)
    
    h1_counter = 0
    heading_counters = []
    previous_title_parts = []

    for record in responses:
        title_parts = [
            p.strip()
            for p in record.get("title", "").split("$")
            if p.strip()
        ]

        if not title_parts:
            continue

        # Find common prefix with previous record
        common_prefix_len = 0
        for old, new in zip(previous_title_parts, title_parts):
            if old == new:
                common_prefix_len += 1
            else:
                break

        # Add only the new headings
        for i in range(common_prefix_len, len(title_parts)):
            level = i + 1

            # Build numbering
            if i == 0:
                # New H1
                h1_counter += 1
                numbering = f"{h1_counter}."
                heading_counters = [h1_counter]

            else:
                # Ensure counter exists
                while len(heading_counters) <= i:
                    heading_counters.append(0)

                heading_counters[i] += 1

                # Reset deeper counters
                heading_counters = heading_counters[: i + 1]

                numbering = ".".join(
                    str(x) for x in heading_counters[: i + 1]
                )

            heading_text = f"{numbering} {title_parts[i]}"

            heading = doc.add_heading(heading_text, level=level)
            for run in heading.runs:
                set_custom_font(run)

        add_record_body(doc, record)

        previous_title_parts = title_parts

    return doc