"""pydantic response model"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, TypedDict


class ExtractedAnswer(BaseModel):
    """For each metric extraction, LLM should follow this schema"""

    worksheet: str = Field(
        description="The worksheet name this variable belongs to"
    )
    variable: str = Field(
        description="The name of the variable being extracted"
    )
    year: Optional[int] = Field(default=None, description="Financial year this answer applies to")
    answer: str = Field(
        description="The extracted value as given in the source document, or 'N/A' if not found"
    )
    confidence: float = Field(
        description="Confidence score between 0.0 and 1.0 based on how clearly the document states the value. It helps user to understand wether the metric is extracted, inferred, or ambiguous."
    )
    page_number: int = Field(
        description="The page number where the information was found. Set to -1 if not found."
    )
    source_fields: List[str] = Field(
        default_factory=list,
        description="List of fields in the source document that were used to extract the answer. One name for 1 to 1 mapping. List of several names if there is a calculation"
    )
    formula: str = Field(
        default=None,
        description="Formula used to calculate the answer based on source fields. Set to null if not applicable for e.g. in case of 1 to 1 mapping."
    )
    source_link: str = Field(
        default="N/A",
        description="Hyperlink formula pointing to the source PDF page. Populated post-extraction."
    )
    source_heading: Optional[str] = Field(
        default=None,
        description="The section, table, or paragraph heading where the value was found in the PDF."
    )
    source_text: Optional[str] = Field(
        default=None,
        description="The complete relevant paragraph or full table from the PDF that contains the extracted value, including surrounding context for verification."
    )


class ExtractionResponse(BaseModel):
    """Overall extracted response from the LLM model."""

    year: Optional[int] = Field(
        default=None,
        description="The financial year this metric applies to (e.g., 2023, 2024). Set to null if not found."
    )
    currency: Optional[str] = Field(
        default=None,
        description="The currency used for e.g. 'EUR', 'GBP', 'USD'. Set to null if not found."
    )
    scale: Optional[str] = Field(
        default=None,
        description="The scale used for e.g. 'thousands' or 'millions'. Set to null if not found."
    )
    answers: List[ExtractedAnswer] = Field(
        default_factory=list,
        description="List of extracted answers for all requested variables."
    )
    errors: List[str] = Field(
        default_factory=list
    )


class RefinementAnswer(BaseModel):
    """Refined answer for an existing template metric."""

    worksheet: str
    variable: str
    answer: str = Field(
        description="Improved value or N/A if unavailable."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0
    )
    page_number: int
    source_fields: List[str] = Field(
        default_factory=list
    )
    formula: Optional[str] = None

    is_supported: bool = Field(
        description="Whether the answer is directly supported by the PDF."
    )

    refinement_reason: str = Field(
        description="Brief explanation of what was corrected or verified."
    )


class RefinementResponse(BaseModel):
    """Response from one refinement attempt."""

    answers: List[RefinementAnswer] = Field(
        default_factory=list
    )
    errors: List[str] = Field(
        default_factory=list
    )

class MultiYearExtractionResponse(BaseModel):
    years: List[int] = Field(default_factory=list)
    answers: List[ExtractedAnswer] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)