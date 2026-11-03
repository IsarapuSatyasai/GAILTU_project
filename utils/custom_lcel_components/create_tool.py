from langchain_core.runnables import RunnableLambda
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from custom_lcel_components.chains import (
    get_qa_chain,
    get_sentence_window_rag_chain_from_config,
)
from custom_lcel_components.utils import (
    select_columns,
)


# -----------------------------------------------------------------
# Schemas
# -----------------------------------------------------------------
class RAGInput(BaseModel):
    question: str = Field(
        ..., description="Question to answer using the annual report."
    )
    collection_name: str = Field(..., description="Collection name")


def create_rag_tool(config: dict, keys_to_select: list[str]) -> BaseTool:
    """
    Create a RAG-based tool for answering questions over annual reports.

    Args:
        config (dict): Configuration for the RAG pipeline, including model,
            retrieval, and chunking parameters. Must already include
            'system_message' if required by the pipeline.
        keys_to_select: Collection of output field names to include.

    Returns:
        Tool: A LangChain-compatible tool that accepts:
            - question: user query
            - collection_name: collection name
    """
    # -----------------------------------------------------------------
    # Build RAG chain
    # -----------------------------------------------------------------
    _, _, chain_without_index = get_sentence_window_rag_chain_from_config(config)

    qa_chain = get_qa_chain(
        system_prompt=config["system_message"],
        llm_model=config["llm_model"],
        top_p=config["top_p"],
    )

    rag_chain = (
        chain_without_index
        | qa_chain
        | RunnableLambda(select_columns).bind(keys_to_select=keys_to_select)
    )

    # -----------------------------------------------------------------
    # Create tool
    # -----------------------------------------------------------------
    rag_tool = rag_chain.as_tool(
        name="annual_report",
        description=(
            "Answers questions about the annual report using a sentence-window "
            "RAG pipeline. Requires question, collection_name, and language."
        ),
        args_schema=RAGInput,
    )

    return rag_tool
