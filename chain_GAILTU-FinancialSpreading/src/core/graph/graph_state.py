"""Graph state for financial spreading"""

from typing import List, Dict, Any, Optional
from typing_extensions import TypedDict
from langchain_openai import AzureChatOpenAI

class Metric(TypedDict):
    worksheet: str
    variable: str
    description: str
    formula: str | None
    remarks: str | None

class FinancialGraphState(TypedDict, total=False):
    # Input
    excel_path: str
    pdf_source: str
    output_path: str
    pdf_file_name: str

    # Intermediate
    excel_data: List[Metric]
    pdf_pages: List[Dict[str, Any]]
    source_language: str
    llm: Optional[AzureChatOpenAI]
    selected_pages: List[Dict[str, Any]]
    baseline_selected_pages: List[Dict[str, Any]]

    # Answers
    original_answers: List[Dict[str, Any]]
    refined_answers: List[Dict[str, Any]]
    answers: List[Dict[str, Any]]
    years: List[int]
    answers_by_year: Dict[int, List[Dict[str, Any]]]

    # RAG
    rag_collection_name: Optional[str]
    rag_config: Optional[Dict[str, Any]]  # chain config returned by build_index, reused for retrieval
    use_rag: bool

    # Control
    refinement_attempt: int
    errors: List[str]
    extraction_completed: bool
    categorized_pages: Dict[str, List[int]]

    # RAG fields
    rag_collection_name: Optional[str]
    use_rag: bool
    rag_context: Optional[str]