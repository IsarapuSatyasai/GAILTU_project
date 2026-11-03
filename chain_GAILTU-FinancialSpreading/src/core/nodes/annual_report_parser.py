"""Node: Parse PDF Document.

Reads and parses the PDF (supports scanned PDFs via OCR) using the
existing ingest_documents utility.
"""

from graph.graph_state import FinancialGraphState
from custom_lcel_components.ingest import ingest_documents

#Maybe here I can also combine from custom_lcel_components.indexing import derive_collection_name_from_source 


def annual_report_parser(state: FinancialGraphState) -> dict:
    """Parse the PDF document, extracting text per page.

    Delegates to `ingest_documents` which handles:
    - Standard PDF text extraction (PyMuPDFLoader)
    - Scanned PDF detection and OCR via pytesseract
    - Image-based text extraction using LLM for problematic pages
    """
    pdf_source = state["pdf_source"]

    try:
        _dir = {"source": pdf_source}
        pdf_pages = ingest_documents(
            _dir,
            pdf_loader_type="PyMuPDFLoader",
            source_key="source",
        )

        if not pdf_pages:
            return {
                "pdf_pages": [],
                "errors": state.get("errors", []) + ["No pages extracted from PDF"],
            }

        return {"pdf_pages": pdf_pages, "errors": state.get("errors", [])}

    except Exception as e:
        return {
            "pdf_pages": [],
            "errors": state.get("errors", []) + [f"PDF parse error: {str(e)}"],
        }
