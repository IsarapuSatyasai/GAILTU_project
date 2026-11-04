"""Retrieve context using the existing RAG chain."""

import json
import re
from bisect import bisect_right

from custom_lcel_components.chains import get_sentence_window_rag_chain_from_config

_SEG_WORDS = 25  # words per segment when locating passage text in the PDF
_FRAG = 20       # characters per fallback fingerprint fragment (segments that straddle a page break)


def _alnum(text: str) -> str:
    """Lowercase letters/digits only, so PDF text and cleaned chunk text compare reliably."""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def load_page_texts(pdf_path: str) -> dict:
    """{1-based page number: page text} for a local PDF path (PyMuPDF, same loader the index uses)."""
    import fitz

    doc = fitz.open(pdf_path)
    return {i + 1: doc[i].get_text() for i in range(doc.page_count)}


def build_page_index(page_texts: dict) -> dict:
    """Whole document as one normalised string plus page start offsets; build once per PDF."""
    pages = sorted(page_texts)
    parts, starts, pos = [], [], 0
    for p in pages:
        a = _alnum(page_texts[p])
        starts.append(pos)
        parts.append(a)
        pos += len(a)
    return {"doc": "".join(parts), "starts": starts, "pages": pages, "cache": {}}


def _page_at(index: dict, pos: int) -> int:
    return index["pages"][bisect_right(index["starts"], pos) - 1]


def locate_segment(seg: str, index: dict):
    """PDF page a short text segment comes from, or None if it cannot be found.

    Exact match of the whole normalised segment first; if it straddles a page break (or text was
    altered by cleaning), majority vote over fixed-size fragments.
    """
    a = _alnum(seg)
    if len(a) < 12:  # too short to be distinctive
        return None
    cache = index["cache"]
    if a in cache:
        return cache[a]
    doc = index["doc"]
    hit = doc.find(a)
    page = _page_at(index, hit) if hit >= 0 else None
    if page is None:
        votes = {}
        for i in range(0, len(a) - _FRAG + 1, _FRAG):
            j = doc.find(a[i:i + _FRAG])
            if j >= 0:
                pg = _page_at(index, j)
                votes[pg] = votes.get(pg, 0) + 1
        page = max(votes, key=votes.get) if votes else None
    cache[a] = page
    return page


def label_pages_inline(text: str, index: dict, fallback_page=None) -> str:
    """Insert a [Page N] marker at the start of the text and wherever the page changes.

    Retrieved sentence windows over tables are long (10k+ chars) and can cover several pages (and
    neighbouring chunks are not always adjacent in the document), so one label per passage is wrong.
    The text is cut into ~25-word segments, each located in the PDF; segments that cannot be located
    inherit the previous page.
    """
    words = text.split()
    segs = [" ".join(words[i:i + _SEG_WORDS]) for i in range(0, len(words), _SEG_WORDS)]
    out, current = [], None
    for seg in segs:
        page = locate_segment(seg, index) or current or fallback_page
        if page != current and page is not None:
            out.append(f"[Page {page}]")
            current = page
        out.append(seg)
    return " ".join(out)


def _chunk_page(chunk: dict):
    """1-based PDF page of a retrieved chunk from its metadata ("page_no", e.g. 193 or "193,194")."""
    meta = chunk.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except json.JSONDecodeError:
            return None
    page = meta.get("page_no")
    return str(page).strip() if page not in (None, "") else None


def format_chunks_with_pages(chunks: list, page_index: dict = None) -> str:
    """Join retrieved chunks into one context string with page labels, passages separated by blank lines.

    The chain's own context is the chunk texts concatenated with no separator and no page info,
    so the LLM had to guess page numbers.
    - With `page_index` (from build_page_index): [Page N] markers are inserted inline wherever the
      text's real PDF page changes (see label_pages_inline).
    - Without it: each passage gets the page_no stored in the index. That is the page of the window's
      centre sentence and is often off for long table windows (e.g. balance-sheet text on p.194
      stored as 192 or 197), so pass page_index whenever the PDF is available.
    """
    passages = []
    for chunk in chunks:
        text = (chunk.get("text") or "").strip()
        if not text:
            continue
        stored = _chunk_page(chunk)
        if page_index:
            labelled = label_pages_inline(text, page_index, fallback_page=stored)
            passages.append(labelled if labelled.startswith("[Page ") else text)
        else:
            passages.append(f"[Page {stored}]\n{text}" if stored else text)
    return "\n\n".join(passages)


def retrieve_context(collection_name: str, query: str, config: dict, page_index: dict = None) -> str:
    _, _, rag_qa_chain = get_sentence_window_rag_chain_from_config(config)
    result = rag_qa_chain.invoke({
        "question": query,
        "collection_name": collection_name,
    })
    chunks = result.get("retrieved_chunks")
    if chunks:
        return format_chunks_with_pages(chunks, page_index)
    return (
        result.get("context")
        or result.get("source_documents")
        or result.get("answer")
        or ""
    )