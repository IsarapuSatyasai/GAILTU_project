from collections import defaultdict
from copy import deepcopy

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.table import Table
from docx.text.paragraph import Paragraph

SUBSECTION_BREAK = "__SUBSECTION_BREAK__"


def iter_blocks(doc):
    """
    Yield paragraphs and tables in the order they appear in a Word document.

    This function iterates through the document body and returns each
    paragraph and table object sequentially, preserving the original
    document structure.

    Args:
        doc (Document):
            A python-docx Document object.

    Yields:
        Paragraph | Table:
            Paragraph and table objects in document order.
    """
    for element in doc.element.body:
        if element.tag == qn("w:p"):
            yield Paragraph(element, doc)
        elif element.tag == qn("w:tbl"):
            yield Table(element, doc)


def set_font(run, font_name, font_size, bold=None):
    """
    Apply explicit font settings to a run and remove theme font overrides.

    This ensures that Microsoft Word does not replace the selected font with
    a theme font by setting all font mappings (ASCII, East Asian, complex
    script, etc.) and removing theme-based font attributes.

    Args:
        run (Run):
            The run whose formatting will be modified.
        font_name (str):
            Name of the font to apply.
        font_size (int | float):
            Font size in points.
        bold (bool | None, optional):
            Whether the text should be bold. If None, the existing bold
            setting is preserved.

    Returns:
        None
    """
    run.font.name = font_name
    run.font.size = Pt(font_size)

    if bold is not None:
        run.bold = bold

    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()

    rfonts.set(qn("w:ascii"), font_name)
    rfonts.set(qn("w:hAnsi"), font_name)
    rfonts.set(qn("w:eastAsia"), font_name)
    rfonts.set(qn("w:cs"), font_name)

    # Prevent Word from overriding the font with theme fonts.
    for name in (
        "asciiTheme",
        "hAnsiTheme",
        "eastAsiaTheme",
        "cstheme",
    ):
        attribute = qn(f"w:{name}")
        rfonts.attrib.pop(attribute, None)


def replace_paragraph_text(
    paragraph,
    text,
    font_name,
    font_size,
    bold=None,
    alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
):
    """
    Replace the contents of a paragraph and apply consistent formatting.

    Existing paragraph text is replaced while preserving the paragraph
    itself. The first run is reused where possible and all additional
    runs are cleared. Font properties and alignment are applied to the
    resulting text.

    Args:
        paragraph (Paragraph):
            Target paragraph.
        text (str):
            New text to insert.
        font_name (str):
            Font name to apply.
        font_size (int | float):
            Font size in points.
        bold (bool | None, optional):
            Whether text should be bold.
        alignment (WD_PARAGRAPH_ALIGNMENT, optional):
            Paragraph alignment. Defaults to justified.

    Returns:
        None
    """
    if paragraph.runs:
        run = paragraph.runs[0]
        run.text = text

        for extra_run in paragraph.runs[1:]:
            extra_run.text = ""
    else:
        run = paragraph.add_run(text)

    set_font(
        run,
        font_name=font_name,
        font_size=font_size,
        bold=bold,
    )

    paragraph.alignment = alignment


def parse_markdown_table(lines):
    """
    Convert Markdown table text into a list of row values.

    The function strips Markdown formatting characters, removes the
    separator row (for example '| --- | --- |'), and returns the table
    content as a list of rows.

    Args:
        lines (list[str]):
            Markdown table lines.

    Returns:
        list[list[str]]:
            Parsed table rows and cell values.
    """
    rows = [
        [cell.strip().replace("**", "") for cell in line.strip().strip("|").split("|")]
        for line in lines
    ]

    # Remove separator row: | --- | --- |
    if len(rows) > 1 and all(
        not cell.replace("-", "").replace(":", "").strip() for cell in rows[1]
    ):
        rows.pop(1)

    return rows


def replace_section(
    doc,
    start_heading,
    end_heading,
    answer,
    font_name="Arial",
    font_size=10,
    table_font_size=7,
    table_header_font_size=7,
    alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
):
    """
    Replace all content between two headings in a Word document.

    Content located between `start_heading` and `end_heading` is removed
    and replaced with text and Markdown-formatted tables extracted from
    `answer`. Paragraph and table formatting are copied from the original
    content where possible, while font properties are explicitly controlled
    by the provided arguments.

    Features:
        - Preserves document structure and ordering.
        - Reuses paragraph formatting from existing content.
        - Reuses table styles and layouts when possible.
        - Supports Markdown tables.
        - Supports subsection breaks using the
          '__SUBSECTION_BREAK__' marker.
        - Applies explicit font settings to prevent Word theme overrides.

    Args:
        doc (Document):
            The Word document to modify.
        start_heading (str):
            Heading marking the beginning of the section to replace.
        end_heading (str):
            Heading marking the end of the section to replace.
        answer (str):
            New content to insert. May contain plain text, Markdown
            tables, and subsection break markers.
        font_name (str, optional):
            Font name applied to inserted content.
        font_size (int | float, optional):
            Font size for normal paragraphs.
        table_font_size (int | float, optional):
            Font size for table body cells.
        table_header_font_size (int | float, optional):
            Font size for table header cells.
        alignment (WD_PARAGRAPH_ALIGNMENT, optional):
            Alignment applied to inserted paragraphs.

    Returns:
        Document:
            The modified document instance.

    Raises:
        ValueError:
            If either heading cannot be found or the section boundaries
            are invalid.
    """
    items = list(iter_blocks(doc))

    start = next(
        (
            index
            for index, item in enumerate(items)
            if isinstance(item, Paragraph)
            and item.text.strip().casefold() == start_heading.strip().casefold()
        ),
        None,
    )

    end = next(
        (
            index
            for index, item in enumerate(items)
            if start is not None
            and index > start
            and isinstance(item, Paragraph)
            and item.text.strip().casefold() == end_heading.strip().casefold()
        ),
        None,
    )

    if start is None or end is None:
        raise ValueError(
            f"Section not found:\nStart: {start_heading!r}\nEnd: {end_heading!r}"
        )

    old_content = items[start + 1 : end]
    end_paragraph = items[end]

    # Copy formatting from the first original body paragraph.
    paragraph_template = next(
        (
            item
            for item in old_content
            if isinstance(item, Paragraph) and item.text.strip()
        ),
        None,
    )

    # Copy table structure/style from the first original table.
    table_template = next(
        (item for item in old_content if isinstance(item, Table)),
        None,
    )

    # Remove old paragraphs and tables.
    for item in old_content:
        parent = item._element.getparent()

        if parent is not None:
            parent.remove(item._element)

    def add_paragraph(text):
        """
        Insert a new paragraph before the end heading.

        The paragraph inherits formatting from the original section template,
        applies standardized spacing settings, and inserts the provided text.
        """
        # Create a new paragraph XML
        new_xml = OxmlElement("w:p")

        # Copy only paragraph formatting from template
        if paragraph_template is not None and paragraph_template._p.pPr is not None:
            new_xml.append(deepcopy(paragraph_template._p.pPr))

        paragraph = Paragraph(
            new_xml,
            end_paragraph._parent,
        )

        # Normalize formatting
        fmt = paragraph.paragraph_format

        fmt.space_before = Pt(0)
        fmt.space_after = Pt(0)
        fmt.line_spacing = 1

        # Prevent Word from moving paragraphs around
        fmt.keep_with_next = False
        fmt.keep_together = False
        fmt.page_break_before = False

        # Add content
        if text:
            replace_paragraph_text(
                paragraph=paragraph,
                text=text,
                font_name=font_name,
                font_size=font_size,
                alignment=alignment,
            )
        else:
            paragraph.add_run("")

        # Insert before end heading
        end_paragraph._p.addprevious(new_xml)

    def add_table(table_lines):
        """
        Insert a table generated from Markdown rows.

        Attempts to reuse the structure and styling of an existing template
        table. If no compatible table is available, a new table is created.
        Text formatting is applied to all cells explicitly.
        """
        rows = parse_markdown_table(table_lines)

        if not rows:
            return

        column_count = max(len(row) for row in rows)

        if table_template is not None and len(table_template.columns) == column_count:
            # Copy the complete original table structure and formatting.
            new_xml = deepcopy(table_template._tbl)
            table = Table(
                new_xml,
                end_paragraph._parent,
            )

            # Adjust the number of rows.
            while len(table.rows) < len(rows):
                table.add_row()

            while len(table.rows) > len(rows):
                table._tbl.remove(table.rows[-1]._tr)

            end_paragraph._p.addprevious(new_xml)

        else:
            # Create a new table if no compatible template exists.
            table = doc.add_table(
                rows=len(rows),
                cols=column_count,
            )

            if table_template is not None and table_template.style is not None:
                table.style = table_template.style
            else:
                table.style = "Table Grid"

            end_paragraph._p.addprevious(table._tbl)

        # Populate the table and explicitly set fonts.
        for row_index, values in enumerate(rows):
            for column_index in range(column_count):
                value = values[column_index] if column_index < len(values) else ""

                cell = table.cell(
                    row_index,
                    column_index,
                )

                paragraph = cell.paragraphs[0]

                replace_paragraph_text(
                    paragraph=paragraph,
                    text=value,
                    font_name=font_name,
                    font_size=(
                        table_header_font_size if row_index == 0 else table_font_size
                    ),
                    bold=(row_index == 0),
                    alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
                )

                # Clear additional paragraphs copied from the template.
                for extra_paragraph in cell.paragraphs[1:]:
                    for run in extra_paragraph.runs:
                        run.text = ""

    table_lines = []

    for raw_line in str(answer).splitlines():
        line = raw_line.strip()

        # Detect Markdown table rows.
        if line.startswith("|") and line.endswith("|") and line.count("|") >= 2:
            table_lines.append(line)
            continue

        # Insert a collected table.
        if table_lines:
            add_table(table_lines)
            table_lines = []

        if line == "__SUBSECTION_BREAK__":
            add_paragraph("")
            continue

        if not line:
            continue

        # Remove basic Markdown formatting.
        line = line.lstrip("#").strip()
        line = line.replace("**", "")

        add_paragraph(line)

    # Handle an answer that ends with a table.
    if table_lines:
        add_table(table_lines)

    # Add one blank line after the complete answer
    add_paragraph("")

    return doc


def prepare_input(items):
    """Prepare hierarchical input data grouped by top-level title.

    Each item's `title` field may contain a hierarchy separated by "$".
    The first hierarchy level is used as the group key, while the remaining
    levels are combined into a subtitle. For each item, a content block is
    created containing:
      - the subtitle (if present),
      - the item's answer (if present),
      - a page reference (if available).

    Items sharing the same top-level title are grouped together. Within a
    group, blocks are concatenated and separated by `SUBSECTION_BREAK`.

    Args:
        items (list[dict]): List of dictionaries containing:
            - "title" (str): Hierarchical title separated by "$".
            - "answer" (str, optional): Associated content.
            - "page_no" (int, optional): Page reference.

    Returns:
        dict[str, str]: Mapping from top-level title to a merged text block
        containing all grouped content and subsection separators.
    """
    grouped = defaultdict(list)

    for item in items:
        raw_title = item.get("title", "").strip()

        # Split all hierarchy levels
        parts = [p.strip() for p in raw_title.split("$") if p.strip()]

        if parts:
            title = parts[0]
            subtitle = "\n".join(parts[1:])
        else:
            title = ""
            subtitle = ""

        block = []

        if subtitle:
            block.append(subtitle)

        answer = item.get("answer")
        if answer:
            block.append(answer)

        page_no = item.get("page_no")
        if page_no is not None:
            block.append(f"Page reference {page_no}")

        grouped[title].append(block)

    result = {}

    for title, blocks in grouped.items():
        merged = []

        for idx, block in enumerate(blocks):
            merged.extend(block)

            # Insert separator between subsections
            if idx < len(blocks) - 1:
                merged.append(SUBSECTION_BREAK)

        result[title] = "\n".join(merged)

    return result
    grouped = defaultdict(list)

    for item in items:
        raw_title = item.get("title", "").strip()

        # Split all hierarchy levels
        parts = [p.strip() for p in raw_title.split("$") if p.strip()]

        if parts:
            title = parts[0]
            subtitle = "\n".join(parts[1:])
        else:
            title = ""
            subtitle = ""

        block = []

        if subtitle:
            block.append(subtitle)

        answer = item.get("answer")
        if answer:
            block.append(answer)

        page_no = item.get("page_no")
        if page_no is not None:
            block.append(f"Page reference {page_no}")

        grouped[title].append(block)

    result = {}

    for title, blocks in grouped.items():
        merged = []

        for idx, block in enumerate(blocks):
            merged.extend(block)

            # Insert separator between subsections
            if idx < len(blocks) - 1:
                merged.append(SUBSECTION_BREAK)

        result[title] = "\n".join(merged)

    return result


def replace_cell_text_keep_format(cell, new_text):
    """
    Replace the visible text of a cell while preserving the existing
    run/paragraph/cell formatting as much as possible.
    """

    # Find all text nodes <w:t> inside this cell
    text_nodes = cell._tc.xpath(".//w:t")

    if not text_nodes:
        # If there is no existing text node, fallback
        if cell.paragraphs:
            cell.paragraphs[0].add_run(new_text)
        return

    # Put new text in the first existing text node
    text_nodes[0].text = new_text

    # Clear all other text nodes
    for t in text_nodes[1:]:
        t.text = ""
