import logging
import os

from create_credit_report_word_template_utils import (
    generate_final_response,
    populate_credit_report,
)
from custom_lcel_components.chains import (
    get_sentence_window_rag_chain_from_config,
)
from custom_lcel_components.utils import (
    init_lang_detect,
)
from langchain_core.runnables import (
    RunnableBranch,
    RunnableLambda,
    RunnablePassthrough,
)
from ltu_chains_utils import (
    get_annual_report_chain,
    get_financial_analysis_chain,
)
from mlflow.models import set_model

logger = logging.getLogger(__name__)


def get_ltu_chain(
    experiment=True,
):
    config = {
        "llm_model": "gpt-5.2",  # This model is used for RAG requests.
        "llm_model_agent": "gpt-5.4",  # This model is used for agent requests.
        "temperature": 0,
        "top_p": 1,
        "embedding_model_name": "text-embedding-3-large",
        "pdf_loader_type": "PyMuPDFLoader",
        "include_source": False,
        "hybrid_search_args": None,
        "remove_duplicate_chunks": True,
        "sentence_chunker_window_size": 5,
        "similarity_top_k": 20,
        "source_key": "additional_report_source",  # This key is needed for the rag chain to know which key to use for the location of the source to ingest.
        "rerank_args": {"top_n": 10, "model": "cross-encoder/ms-marco-MiniLM-L-2-v2"},
    }

    (_, index_chain, _) = get_sentence_window_rag_chain_from_config(config)

    init_lang_detect_step = RunnablePassthrough.assign(
        responses=RunnableLambda(init_lang_detect)
    )

    financial_analysis_chain = get_financial_analysis_chain()
    annual_report_chain = get_annual_report_chain()

    # Step to assign the final response generation function
    get_final_response_step = RunnablePassthrough.assign(
        responses=RunnableLambda(generate_final_response)
    )

    if experiment:
        logger.warning(
            "Experiment mode is enabled. The final output will be a dictionary with the responses and the final docx file. In production, only the docx file will be returned."
        )
        format_output = RunnablePassthrough.assign(
            final_response_doc=RunnableLambda(populate_credit_report)
        )
    else:
        logger.warning(
            "Production mode is enabled. The final output will be a docx file only. In experiment mode, the output will be a dictionary with the responses and the final docx file."
        )
        format_output = RunnableLambda(populate_credit_report)

    conditional_annual_report_chain = RunnableBranch(
        (
            lambda x: bool(x.get("additional_report_source", "").strip()),
            annual_report_chain,
        ),
        RunnablePassthrough(),  # skip annual report analysis
    )

    conditional_collection_step = RunnableBranch(
        (
            lambda x: bool(x.get("additional_report_source", "").strip()),
            RunnablePassthrough.assign(rag_collection_name=index_chain),
        ),
        RunnablePassthrough(),
    )

    # Define the financial analysis chain
    ltu_chain = (
        init_lang_detect_step
        | conditional_collection_step
        | RunnablePassthrough.assign(
            financial_analysis=financial_analysis_chain,
            annual_report=conditional_annual_report_chain,
        )
        | get_final_response_step
        | format_output
    )
    ltu_chain.name = "chain_GAILTU-Credit"

    return ltu_chain


environment_name = os.getenv("ENVIRONMENT", "")
experiment_mode = environment_name == "testing"
set_model(get_ltu_chain(experiment=experiment_mode))
