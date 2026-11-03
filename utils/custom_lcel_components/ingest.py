"""The main function (ingest_documents) implements the logic to load pdf files from blob storage.

It expects a dictionary with the storage account name, the folder path (source) and optionally a collection name as input and returns a list of documents.
"""

import base64
import copy
import json
import logging
import os
import re
import string
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import chromadb
import cv2
import fitz
import numpy as np
import pytesseract
from chromadb.config import Settings
from docx import Document as WordDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from langchain_classic.docstore.document import Document
from langchain_classic.document_loaders import (
    PDFPlumberLoader,
    PyMuPDFLoader,
    PyPDFLoader,
)
from langchain_classic.document_loaders.pdf import BasePDFLoader
from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda
from mlflow.tracing.provider import trace_disabled
from pytesseract import Output

from custom_lcel_components.downloadblob import (
    download_files_from_storage_account,
)
from custom_lcel_components.llm import create_llm
from custom_lcel_components.variables import (
    _CHROMA_FOLDER,
)

logger = logging.getLogger(__name__)


def ingest_documents(
    _dir: Dict,
    pdf_loader_type: str = "PyPDFLoader",
    source_key: str = "source",
) -> list[Dict]:
    path = _dir[source_key]

    storage_account = os.environ["STORAGE_ACCOUNT"]

    """
    Ingests documents from a specified directory and processes them into a list of formatted pages.

    This function downloads files from a cloud storage account, loads the pages from the files using a specified PDF loader,
    and formats the pages into a list of dictionaries. If a collection name is provided and the collection already exists,
    the ingestion process is skipped.

    Args:
        _dir (Dict): A dictionary containing the source path information.
        pdf_loader_type (str, optional): The type of PDF loader to use. Defaults to "PyPDFLoader".

    Returns:
        List[Dict]: A list of dictionaries with formatted page text and metadata.

    Note: if the given path is a folder, all pdf files from the folder will be ingested and the output is a list of pages containing the pages of all documents.
    """
    if "collection_name" in _dir.keys():
        collection_name = _dir["collection_name"]
        # If there is an existing vector db collection it should not ingest again
        if _check_if_collection_exists(_CHROMA_FOLDER, collection_name):
            logger.warning("skip ingestion because collection exists...")
            return []

    with tempfile.TemporaryDirectory() as tmpdir:
        downloaded_file_names = download_files_from_storage_account(
            path, tmpdir, storage_account
        )

        if len(downloaded_file_names) > 0:
            logger.warning("ingesting files...")
            formatted_pages = []

            for i, path in enumerate(downloaded_file_names):
                file_type = _get_file_type(path)

                if file_type == "pdf_doc":
                    pdf_loader = _get_pdf_loader(pdf_loader_type, [path])
                    loaded_pages = pdf_loader.load()

                    pdf_has_tounicode_issue_ind = _pdf_has_tounicode_issue(path)
                    percentage_of_pages_with_no_text = _check_missing_text_percentage(
                        loaded_pages
                    )

                    has_issue, assessment, issued_pages = _assess_pages_quality(
                        loaded_pages
                    )

                    # Check average words per page; if flagged low, it means this is likely a scanned PDF
                    # where only titles/headings were extracted, but the real page content was not loaded.
                    avg_words, is_low_content = _average_words_per_page(loaded_pages)

                    if (
                        (percentage_of_pages_with_no_text == 100)
                        or pdf_has_tounicode_issue_ind
                        or is_low_content
                    ):
                        logger.warning("Converting all pages to text from images")
                        image_base64_list = _convert_pdf_to_base64_images(path)
                        formatted = _extract_text_from_images(path, image_base64_list)
                    elif has_issue:
                        logger.warning(
                            "Converting only selected pages to text from images"
                        )
                        # Convert the reported 1-based "issued pages" into 0-based indices expected by downstream functions
                        zero_based_issue_indice = [x - 1 for x in issued_pages]

                        # Use the scanned PDF loader *only for the issued pages* so we re-extract images just for those pages
                        image_base64_list = _convert_pdf_to_base64_images(
                            path, pages=zero_based_issue_indice
                        )
                        formatted_issue_page = _extract_text_from_images(
                            path,
                            image_base64_list,
                            page_numbers=zero_based_issue_indice,
                        )

                        formatted_loaded_pages = _format_pages(loaded_pages)

                        # Replace the old content of the issued pages with the freshly re-parsed results,
                        # leaving all other pages untouched. `deep_copy=True` avoids mutating the original data.
                        formatted = replace_pages(
                            formatted_loaded_pages,
                            zero_based_issue_indice,
                            formatted_issue_page,
                            deep_copy=True,
                        )
                    else:
                        formatted = _format_pages(loaded_pages)

                    formatted_pages.extend(formatted)
                elif file_type == "word_doc":
                    formatted = _load_and_clean_word_doc(path)
                    formatted_pages.extend(formatted)
                elif file_type == "unknown":
                    logger.warning(
                        "Currently, only Word and PDF formats are supported for ingestion."
                    )
                _add_issue_pages_to_docs(formatted_pages)
        else:
            logger.warning("no files found on the given path...")
            return []

    logger.warning("files are ingested!")

    return formatted_pages


def _add_issue_pages_to_docs(pages):
    """
    Annotate each page dictionary in the provided list with a list of problematic (issued) page numbers.

    This function assesses the quality of the provided pages, identifies pages with issues (such as unreadable or blank pages),
    and adds an "issue_pages" field to the metadata of each page. The "issue_pages" field contains a JSON-encoded list of
    page numbers that are considered problematic.

    Args:
        pages (List[Dict]): A list of page dictionaries, each with "text" and "metadata" fields.

    Returns:
        None. The function modifies the input list in place.
    """

    has_issue_final, _, issued_pages_final = _assess_pages_quality(pages)
    for page in pages:
        json_metadata = json.loads(page["metadata"])
        json_metadata["issue_pages"] = json.dumps(issued_pages_final)
        page["metadata"] = json.dumps(json_metadata)


def _check_if_collection_exists(
    persistent_db_location: str, collection_name: str
) -> bool:
    """Checks if a collection exists in the specified persistent database location.

    This function verifies whether a collection with the given name exists in the specified
    persistent database location. It returns True if the collection exists, and False otherwise.

    Args:
        persistent_db_location (str): The path to the persistent database location.
        collection_name (str): The name of the collection to check.

    Returns:
        bool: True if the collection exists, False otherwise.
    """
    try:
        settings = Settings(allow_reset=True)
        db = chromadb.PersistentClient(path=persistent_db_location, settings=settings)
    except Exception as e:
        raise ValueError("Failed to create chroma client: " + str(e))

    try:
        _ = db.get_collection(collection_name)
        return True
    except Exception:
        return False


def _get_pdf_loader(
    pdf_loader_type: str, downloaded_file_names: List[str]
) -> BasePDFLoader:
    """Returns the appropriate PDF loader based on the specified type and downloaded file names.

    This function selects and returns a PDF loader based on the provided loader type and the list of downloaded file names.
    If multiple files are provided, a directory loader is used. Otherwise, a specific loader type is chosen based on the file path.

    Args:
        pdf_loader_type (str): The type of PDF loader to use. Options include "PyPDFLoader", "PyMuPDFLoader", and "PDFPlumberLoader".
        downloaded_file_names (List[str]): A list of downloaded file names.

    Returns:
        BasePDFLoader: An instance of the appropriate PDF loader.
    """
    if len(downloaded_file_names) > 1:
        directory = os.path.dirname(downloaded_file_names[0])
        pdf_loader = PyPDFDirectoryLoader(path=directory)
    else:
        local_path = downloaded_file_names[0]
        if pdf_loader_type == "PyPDFLoader":
            pdf_loader = PyPDFLoader(local_path)
        elif pdf_loader_type == "PyMuPDFLoader":
            pdf_loader = PyMuPDFLoader(local_path)
        elif pdf_loader_type == "PDFPlumberLoader":
            pdf_loader = PDFPlumberLoader(local_path)
        elif pdf_loader_type == "fitz":
            pdf_loader = fitz.open(local_path)
        else:
            raise ValueError(f"Unknown pdf_loader_type: {pdf_loader_type}")
    return pdf_loader


def _check_missing_text_percentage(pages: Union[List[dict], List["Document"]]) -> int:
    """
    Calculates the percentage of pages with no meaningful text content.

    Args:
        pages (Union[List[dict], List[Document]]): A list of either dictionaries with 'text' and 'metadata',
                                                   or Document objects with 'page_content'.

    Returns:
        float: Percentage of pages with no text.
    """
    missing_pages = []
    all_pages = []

    if not pages:
        logger.warning("No pages provided.")
        return 100.0

    # Determine input type
    is_dict_format = isinstance(pages[0], dict) and "text" in pages[0]

    for i, page in enumerate(pages):
        if is_dict_format:
            metadata = json.loads(page["metadata"])
            page_no = metadata.get("page_no", i + 1)
            text = page["text"]
        else:
            page_no = i + 1
            text = page.page_content

        all_pages.append(page_no)
        if not text.strip():
            missing_pages.append(page_no)

    total_pages = len(all_pages)
    missing_count = len(missing_pages)
    missing_percentage = (
        round((missing_count / total_pages) * 100, 2) if total_pages > 0 else 0.0
    )

    # Logging diagnostics
    if missing_percentage == 100.0:
        logger.warning(f"0 pages out of {total_pages} are loaded with text.")
    elif missing_percentage == 0.0:
        logger.warning(f"All {total_pages} pages are loaded with content.")
    else:
        logger.warning(f"Percentage of pages with no text: {missing_percentage}%")

    return int(missing_percentage)


def _convert_pdf_to_base64_images(
    doc_path: str,
    num_threads: int = 4,
    pages: Optional[Iterable[int]] = None,
) -> List[str]:
    """Convert each page of a PDF document to an image, deskew it using Tesseract's orientation detection, and encode the image in base64 format.

    Args:
        doc_path (str): Path to the PDF document to be processed.
        num_threads (int): Number of threads to use for parallel processing.
        pages (Optional[Iterable[int]]): 0-based page indices to process. If None, process all pages.

    Returns:
        list: A list of base64-encoded strings, each representing an image of a page from the PDF.
    """
    doc = fitz.open(doc_path)
    selected_pages = (
        range(len(doc))
        if pages is None
        else [p for p in pages if isinstance(p, int) and 0 <= p < len(doc)]
    )
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        # Map _process_page over each selected page number (order preserved)
        return list(
            executor.map(lambda page_num: _process_page(page_num, doc), selected_pages)
        )


@trace_disabled
def _extract_text_from_images(
    doc_path: str,
    image_base64_list: List[str],
    page_numbers: Optional[List[int]] = None,
) -> List[Dict]:
    """Extract and format text from base64-encoded page images using a vision LLM.

    A ``RunnableEach`` runs the vision model over every page image and returns the
    extracted text, which is then wrapped with page metadata.

    Args:
        doc_path (str): Path to the source PDF document.
        image_base64_list (List[str]): Base64-encoded PNG images, one per page.
        page_numbers (Optional[List[int]]): 0-based page indices matching the images.

    Returns:
        List[Dict]: A list of dictionaries with the extracted text and page metadata.
    """
    # This part is used for the scanned pdf loader
    scanned_page_prompt = """Extract all contents from the attached image. Only show the content (no explanations, no formatting, no extra text). If the page/image contains no readable or meaningful content (blank, fully obscured, or no text), return an empty response."""
    llm_image_to_text = (
        create_llm(
            azure_deployment="gpt-4.1",
            top_p=0.1,
            temperature=0,
        )
        .with_retry(wait_exponential_jitter=True, stop_after_attempt=3)
        .with_fallbacks([RunnableLambda(lambda _: AIMessage(content=""))])
    )

    build_messages = RunnableLambda(
        lambda image_b64: [
            SystemMessage(content=scanned_page_prompt),
            HumanMessage(
                content=[
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    }
                ]
            ),
        ]
    )
    extract_chain = build_messages | llm_image_to_text | StrOutputParser()

    texts = extract_chain.batch(image_base64_list)

    if page_numbers is None:
        page_numbers = list(range(len(image_base64_list)))

    source = _extract_filename(os.path.basename(doc_path))
    return [
        {
            "text": text,
            "metadata": json.dumps(
                {"page_no": page_numbers[i] + 1, "source": source, "scanned_pdf": True}
            ),
        }
        for i, text in enumerate(texts)
    ]


def _format_pages(loaded_pages: List[Document]) -> List[Dict]:
    """Formats a list of loaded pages into a list of dictionaries with text and metadata.

    This function takes a list of Document objects representing loaded pages and formats them
    into a list of dictionaries. Each dictionary contains the page text and metadata, including
    the page number and source.

    Args:
        loaded_pages (List[Document]): A list of Document objects, each containing page content and metadata.

    Returns:
        List[Dict]: A list of dictionaries with formatted page text and metadata.
    """
    formatted_pages = []
    for page in loaded_pages:
        page_no = page.metadata["page"]

        source = page.metadata["source"].split("/")[-1]
        updated_source = _extract_filename(source)

        formatted_page = {
            "text": page.page_content,
            "metadata": json.dumps(
                {"page_no": page_no + 1, "source": updated_source, "scanned_pdf": False}
            ),
        }
        formatted_pages.append(formatted_page)
    return formatted_pages


def _process_page(page_num, doc):
    """
    Processes a single page from a PDF document and returns a base64-encoded PNG image of the page,
    correctly oriented based on detected text orientation.

    Parameters:
    ----------
    page_num : int
        The page number to process (0-indexed).
    doc : fitz.Document
        The PDF document object from PyMuPDF.

    Returns:
    -------
    str
        A base64-encoded string representing the processed PNG image of the page.

    Notes:
    -----
    - The function uses PyMuPDF to render the page as an image.
    - It attempts to detect the orientation of the text using Tesseract's OSD (Orientation and Script Detection).
    - If OSD fails, it falls back to a heuristic based on the number of characters extracted.
    - The image is rotated accordingly and encoded to PNG format.
    - The final image is returned as a base64 string for easy embedding or transmission.
    """
    # Load the page
    page = doc.load_page(page_num)
    # Set resolution to 300 DPI
    pix = page.get_pixmap(dpi=300)

    # Convert pixmap to image array
    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n
    )

    # Convert to BGR if needed
    if pix.n == 4:
        image = cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
    elif pix.n == 1:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

    # Encode and decode to ensure proper format
    _, encoded = cv2.imencode(".png", image)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)

    # Fallback rotation angle
    angle = 0

    try:
        # Try OSD for orientation
        osd = pytesseract.image_to_osd(image, output_type=Output.DICT)
        angle = osd.get("rotate", 0)
    except Exception as e:
        # Fallback: try to extract text and decide based on character count
        text = pytesseract.image_to_string(image)
        num_characters = len(text)

        if num_characters > 50:
            # Log and skip rotation
            logger.warning(
                f"Page {page_num}: OSD failed with {num_characters} characters. Defaulting to no rotation. Error: {e}"
            )
        else:
            logger.info(
                f"Page {page_num}: Too few characters ({num_characters}). Skipping OSD and rotation."
            )

    # Rotate if needed
    if angle != 0:
        # Get the image center
        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)

        # Calculate the rotation matrix
        M = cv2.getRotationMatrix2D(center, -angle, 1.0)

        # Calculate the sine and cosine of the rotation angle
        cos = np.abs(M[0, 0])
        sin = np.abs(M[0, 1])

        # Compute the new bounding dimensions of the image
        new_w = int((h * sin) + (w * cos))
        new_h = int((h * cos) + (w * sin))

        # Adjust the rotation matrix to take into account the translation
        M[0, 2] += (new_w / 2) - center[0]
        M[1, 2] += (new_h / 2) - center[1]

        # Perform the actual rotation and return the image
        rotated = cv2.warpAffine(
            image,
            M,
            (new_w, new_h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
    else:
        rotated = image

    # Convert to base64
    _, buffer = cv2.imencode(".png", rotated)
    base64_string = base64.b64encode(buffer).decode("utf-8")

    return base64_string


def _is_readable(data, *, control_threshold: float = 0.15) -> bool:
    """
    Determine if `data` looks like readable text using a simple control-byte heuristic.

    Heuristic:
      - If input is a Python `str`, it will be encoded to UTF-8 with 'ignore' to obtain bytes.
      - If any NUL byte (0x00) is present, treat as not readable.
      - Compute the ratio of control bytes (0x00–0x1F and 0x7F), excluding common whitespace:
          \t (0x09), \n (0x0A), \r (0x0D).
        If the ratio exceeds `control_threshold` (default 0.15), treat as not readable.
      - Otherwise, consider it readable.

    Parameters
    ----------
    data : Union[str, bytes]
        The text or bytes to evaluate.
    control_threshold : float, optional
        Maximum allowed ratio of control bytes (excluding \t, \n, \r). Defaults to 0.15.

    Returns
    -------
    bool
        True if the input is considered readable text, False if it looks like control/binary junk.
    """
    if isinstance(data, str):
        data = data.encode("utf-8", "ignore")
    if not data:
        return False  # empty isn't readable

    # Immediate red flag: NUL bytes
    if data.count(0) > 0:
        return False

    # Count control bytes (excluding common whitespace)
    SAFE_WS = {9, 10, 13}  # \t, \n, \r
    controls = sum(1 for b in data if (b < 32 and b not in SAFE_WS) or b == 127)
    ratio = controls / len(data)
    return ratio <= control_threshold


def _pdf_has_tounicode_issue(
    pdf_path: str, sample_pages: int = 5, *, control_threshold: float = 0.15
) -> bool:
    """
    Checks whether a PDF file has a ToUnicode mapping issue by evaluating the readability
    of text extracted from a sample of pages.

    The function considers the PDF to have a ToUnicode issue only if **all** sampled pages
    are unreadable based on the `is_readable` function and a control character threshold.

    Args:
        pdf_path (str): Path to the PDF file.
        sample_pages (int, optional): Number of pages to sample for readability check. Defaults to 5.
        control_threshold (float, optional): Threshold for control character ratio to determine readability. Defaults to 0.15.

    Returns:
        bool: True if all sampled pages are unreadable (indicating a ToUnicode issue), False otherwise.
    """
    doc = None
    try:
        doc = fitz.open(pdf_path)
        pages_to_check = min(len(doc), max(0, int(sample_pages)))

        all_unreadable = True

        for pno in range(pages_to_check):
            page = doc[pno]
            text = page.get_text("text") or ""
            readable = _is_readable(text, control_threshold=control_threshold)
            if readable:
                all_unreadable = False

        issue_found = all_unreadable
        return issue_found
    finally:
        if doc is not None:
            doc.close()


def _get_file_type(file_path):
    """
    Determines the type of file based on its extension.

    Args:
        file_path (str): Path to the file.

    Returns:
        str: The type of the file (e.g., 'word_doc', 'pdf_doc', 'unknown').
    """
    extension_map = {".doc": "word_doc", ".docx": "word_doc", ".pdf": "pdf_doc"}

    _, ext = os.path.splitext(file_path)
    return extension_map.get(ext.lower(), "unknown")


def _iter_block_items(parent):
    """
    Iterate through block-level elements (Paragraphs and Tables) in a Word document
    or within a table cell, preserving their original order.

    This function is useful when you need to extract text from a Word document
    while maintaining the sequence of paragraphs and tables, including nested
    structures such as tables inside content controls.

    Args:
        parent (Document | _Cell):
            The container to iterate over. This can be:
            - A `Document` object (for the entire Word file)
            - A `_Cell` object (for iterating inside a table cell)

    Yields:
        Union[Paragraph, Table]:
            Each block-level element found in the parent container, in the order
            they appear in the document.

    Notes:
        - Handles standard paragraphs (`w:p`) and tables (`w:tbl`).
        - Recursively processes content controls (`w:sdt`) to extract their
          inner paragraphs and tables.
        - Useful for extracting text from complex Word documents with mixed
          content types.
    """
    if isinstance(parent, _Cell):
        parent_elm = parent._tc
    else:
        parent_elm = parent.element.body

    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):  # Paragraph
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):  # Table
            yield Table(child, parent)
        elif child.tag.endswith("}sdt"):  # Content control
            sdt_content = child.find(".//w:sdtContent", namespaces=child.nsmap)
            if sdt_content is not None:
                for gc in sdt_content.iterchildren():
                    if isinstance(gc, CT_P):
                        yield Paragraph(gc, parent)
                    elif isinstance(gc, CT_Tbl):
                        yield Table(gc, parent)


def _load_and_clean_word_doc(file_path: str) -> List[Dict]:
    """
    Loads a Word document, extracts and cleans its text, and formats it using the file name as source.

    Args:
        file_path (str): Path to the .docx file.

    Returns:
        List[Dict]: A list of dictionaries with formatted page text and metadata.
    """
    # Extract file name without extension to use as source
    file_name = os.path.basename(file_path)
    source = os.path.splitext(file_name)[0]

    updated_source = _extract_filename(source)

    # Load the document
    doc = WordDocument(file_path)

    # Collect text from paragraphs and tables
    text_blocks = []
    for block in _iter_block_items(doc):
        if isinstance(block, Paragraph):
            if block.text.strip():
                text_blocks.append(block.text.strip())
        elif isinstance(block, Table):
            for row in block.rows:
                row_text = [
                    cell.text.strip() for cell in row.cells if cell.text.strip()
                ]
                if row_text:
                    text_blocks.append(" | ".join(row_text))

    combined_text = "\n".join(text_blocks)

    # Remove lines like "Page reference: ['5', '6', '4', '1', '2', '3', '7']"
    cleaned_text = re.sub(
        r"(?im)^\s*page\s*reference[s]?\s*:\s*\[[^\]]*\]\s*$", "", combined_text
    )

    # Format the output
    formatted_page = {
        "text": cleaned_text.strip(),
        "metadata": json.dumps(
            {"page_no": "all", "source": updated_source, "scanned_pdf": False},
            ensure_ascii=False,
        ),
    }

    return [formatted_page]


def _extract_filename(source: str) -> str:
    """
    Extract the filename from a given source coming from two environments.

    We receive source from two environments:
    - Databricks:
        source is a normal file path, and after splitting by "/", we already
        receive a clean filename without any "__" segments.
        Example:
            projects/LTU/Sales/Testing/.../2024 - Lukotrans Logistics - ...

    - Production:
        a flattened metadata string containing several "__" segments, where the
        actual filename is the part after the last "__".
        Example:
            '__General__LTU_Belgium_request__DEV__2026__January__test_20260114_124327__sales_report_RR Europa Beheer BV Concept Financieel versla.pdf'

    This conditional ensures we correctly extract the filename only for the
    metadata-encoded production format, while leaving normal Databricks paths
    untouched.

    Parameters
    ----------
    source : str
        The raw source string representing either a Databricks path or an
        encoded production metadata string.

    Returns
    -------
    str
        The extracted filename based on the environment-specific logic.
    """
    if "__" in source:
        updated_source = source.split("__")[-1]
    else:
        updated_source = source

    return updated_source


def _is_text_readable(text):
    """
    Analyze whether a given text string appears to be readable human text
    or corrupted / encoding-broken text extracted from a PDF.

    This function computes two quality indicators:
    1. Printable character ratio
    3. Ratio of non‑ASCII ("weird") characters

    It then returns all metrics plus a final boolean: "readable".
    """

    # ---------------------------------------------------------
    # 1) PRINTABLE CHARACTER RATIO
    # ---------------------------------------------------------
    # We check what percentage of characters belong to Python's
    # standard printable set (letters, numbers, punctuation, whitespace).
    #
    # Why:
    #   Garbled PDF text typically contains many control characters,
    #   null bytes, and symbols outside the printable ASCII range.
    #
    # A high printable_ratio (~0.85+) usually means clean text.
    # A low ratio means likely corrupted text.
    # ---------------------------------------------------------
    printable_ratio = sum(c in string.printable for c in text) / max(len(text), 1)

    # ---------------------------------------------------------
    # 2) WEIRD UNICODE RATIO
    # ---------------------------------------------------------
    # Count how many characters have Unicode codepoints > 127.
    #
    # Why:
    #   - Standard English text mostly stays within ASCII (<=127).
    #   - Bad PDF extraction often yields many extended-latin glyphs
    #       (č, ƀ, ŧ, ř, ʉ etc.) as a sign of missing ToUnicode maps.
    #   - A weird_ratio above ~0.20 strongly indicates broken extraction.
    # ---------------------------------------------------------
    weird_ratio = sum(ord(c) > 127 for c in text) / max(len(text), 1)

    # ---------------------------------------------------------
    # 3) FINAL READABLE DECISION
    # ---------------------------------------------------------
    # Combine all two heuristics into a simple rule:
    #   - Must be mostly printable text (>85%)
    #   - Must have reasonable average word length (<10 chars)
    #
    # These thresholds work well for distinguishing real text
    # from corrupted PDF extraction output.
    # ---------------------------------------------------------
    readable = printable_ratio > 0.85 and weird_ratio < 0.20

    return readable


def _assess_pages_quality(
    pages: Union[List[dict], List["Document"]],
) -> Tuple[Dict[str, float], List[int]]:
    """
    Assess the readability of pages using `_is_text_readable(text)`.

    This function iterates through provided pages, determines which pages are unreadable,
    and returns an overall assessment plus the list of issued (problem) pages.

    Input formats supported:
      1) List[dict] where each dict contains:
         - "text": str
         - "metadata": JSON-serialized string with possibly "page_no"
      2) List[Document]-like objects with:
         - .page_content: str

    Rules:
      - A page is considered "unreadable" if:
          * its text is empty/whitespace, OR
          * `_is_text_readable(text)` returns False.
      - Page numbers are taken from metadata["page_no"] when present (dict case),
        otherwise fall back to index + 1.

    Returns:
      Tuple[
        assessment: Dict[str, float],  # summary metrics
        issued_pages: List[int]         # page numbers that are unreadable
      ]

      Where `assessment` contains:
        - "total_pages": int
        - "readable_count": int
        - "unreadable_count": int
        - "unreadable_percentage": int  # 0–100
    """
    issued_pages: List[int] = []
    all_pages: List[int] = []

    if not pages:
        logger.warning("No pages provided.")
        assessment = {
            "total_pages": 0,
            "readable_count": 0,
            "unreadable_count": 0,
            "unreadable_percentage": 100,  # if nothing was provided, treat as fully missing
        }
        return assessment, issued_pages

    # Determine input type (dict format with "text" and "metadata")
    is_dict_format = isinstance(pages[0], dict) and "text" in pages[0]

    for i, page in enumerate(pages):
        if is_dict_format:
            # Extract page_no from JSON metadata if available, else fallback
            try:
                metadata_raw = page.get("metadata", "{}")
                metadata = (
                    json.loads(metadata_raw)
                    if isinstance(metadata_raw, str)
                    else metadata_raw
                )
            except Exception:
                metadata = {}
            page_no = metadata.get("page_no", i + 1)
            text = page.get("text", "")
        else:
            page_no = i + 1
            # For Document-like objects, assume `.page_content` holds the text
            text = getattr(page, "page_content", "")

        all_pages.append(page_no)
        text_stripped = (text or "").strip()

        # Unreadable if empty or _is_text_readable returns False
        if (not text_stripped) or (not _is_text_readable(text_stripped)):
            issued_pages.append(page_no)

    total_pages = len(all_pages)
    unreadable_count = len(issued_pages)
    readable_count = total_pages - unreadable_count
    unreadable_percentage = int(
        round((unreadable_count / total_pages) * 100, 2) if total_pages > 0 else 0.0
    )

    # Logging diagnostics similar to the style in _check_missing_text_percentage
    if total_pages == 0:
        logger.warning("No pages to assess for readability.")
    elif unreadable_percentage == 100:
        logger.warning(f"All {total_pages} pages appear unreadable.")
    elif unreadable_percentage == 0:
        logger.warning(f"All {total_pages} pages appear readable.")
    else:
        logger.warning(
            f"Percentage of unreadable pages: {unreadable_percentage}% "
            f"({unreadable_count}/{total_pages}), issued_pages={issued_pages}"
        )

    assessment: Dict[str, int] = {
        "total_pages": total_pages,
        "readable_count": readable_count,
        "unreadable_count": unreadable_count,
        "unreadable_percentage": unreadable_percentage,
    }

    # Issue indicator
    has_issue = unreadable_count != 0

    return has_issue, assessment, issued_pages


def replace_pages(
    pages: List[Dict],
    indices: Sequence[int],
    replacements: Sequence[Dict],
    *,
    in_place: bool = False,
    deep_copy: bool = False,
) -> List[Dict]:
    """
    Replace items in `pages` at positions given by `indices` with corresponding items in `replacements`.

    Parameters
    ----------
    pages : List[Dict]
        The original list containing page info (each element is a dict).
    indices : Sequence[int]
        Zero-based indices in `pages` to replace. The order in this list determines the
        mapping to `replacements`. e.g., indices[i] -> replacements[i].
    replacements : Sequence[Dict]
        Replacement page dicts. Must have the same length as `indices`.
    in_place : bool, optional (default: False)
        If True, mutate `pages` directly and return it. If False, work on a copy and return the new list.
    deep_copy : bool, optional (default: False)
        If True, make a deep copy of `pages` before replacement (when in_place=False), and also deep-copy
        each replacement dict before assigning. Use this if you want to fully detach objects.

    Returns
    -------
    List[Dict]
        The updated list of page dicts.
    """
    # Choose working list
    if in_place:
        target = pages
    else:
        target = copy.deepcopy(pages) if deep_copy else pages.copy()

    # Perform replacements following the order of `indices`
    for idx, rep in zip(indices, replacements):
        target[idx] = copy.deepcopy(rep) if deep_copy else rep

    return target


def _average_words_per_page(loaded_pages, threshold: int = 50):
    """
    Calculate average words per page for a PDF and flag low‑content documents.

    Args:
        loaded_pages: List of LangChain Document objects returned by PyMuPDFLoader.load()
        threshold (int): Minimum acceptable average words per page

    Returns:
        avg_words (float): Average number of words per page
        has_issue (bool): True if avg_words < threshold
    """
    if not loaded_pages:
        return 0.0, True  # empty PDF = issue

    # Count words on every page
    word_counts = [len(page.page_content.split()) for page in loaded_pages]

    # Average words per page
    avg_words = sum(word_counts) / len(word_counts)

    # Determine if the PDF has an issue
    has_issue = avg_words < threshold

    if has_issue:
        logger.warning(f"Low average word count detected: {avg_words}")
    return avg_words, has_issue

def load_document(
    _dir: Dict,
    pdf_loader_type: str = "PyPDFLoader",
    source_key: str = "source",
) -> Any:
    """
    Download a single document from Azure Storage and return a document object.

    The function retrieves the storage path from ``_dir[source_key]``, downloads
    the file to a temporary directory, determines its type, and returns the
    corresponding document object.

    Supported file types:
        - PDF: Returns the configured PDF loader instance.
        - Word (.docx): Returns a ``docx.Document`` instance.

    Args:
        _dir: Dictionary containing the source storage path.
        pdf_loader_type: Name of the PDF loader implementation to use.
            Defaults to ``"PyPDFLoader"``.
        source_key: Key in ``_dir`` that contains the source path.
            Defaults to ``"source"``.

    Returns:
        Any:
            - PDF loader object for PDF files.
            - ``docx.Document`` object for Word files.
            - Empty list (``[]``) if no file is found or the file type is
              unsupported.
    """
    path = _dir[source_key]
    storage_account = os.environ["STORAGE_ACCOUNT"]

    with tempfile.TemporaryDirectory() as tmpdir:
        downloaded_file_names = download_files_from_storage_account(
            path, tmpdir, storage_account
        )

        if not downloaded_file_names:
            logger.warning("No files found on the given path.")
            return []

        file_path = downloaded_file_names[0]
        file_type = _get_file_type(file_path)

        if file_type == "pdf_doc":
            return _get_pdf_loader(
                pdf_loader_type,
                [file_path],
            )

        if file_type == "word_doc":
            return WordDocument(file_path)

        logger.warning(
            "Currently, only Word and PDF formats are supported for ingestion."
        )
        return []