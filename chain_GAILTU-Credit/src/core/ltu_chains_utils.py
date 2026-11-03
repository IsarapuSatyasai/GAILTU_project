from operator import itemgetter

from annual_report_agent_utils import get_ar_agent_qa_chain_with_translation
from annual_report_prompts import (
    ltu_annual_report_countries_agent_prompts_dict,
    ltu_annual_report_countries_prompts_dict,
)
from annual_report_utils import (
    update_agent_questions,
    update_esg_checkers,
    update_responses_with_financial_product_catalogue,
    update_responses_with_issue_pages,
)
from custom_lcel_components.chains import (
    get_qa_chain_with_translation,
    get_sentence_window_rag_chain_from_config,
)
from custom_lcel_components.ingest import ingest_documents
from custom_lcel_components.preprocessing import (
    combine_documents,
)
from custom_lcel_components.utils import (
    expand_question_list,
    get_country_prompts_list_per_country,
)
from financial_analysis_agent_utils import (
    build_section_inputs,
    get_agent_qa_chain_with_translation,
)
from financial_analysis_prompts import (
    ltu_financial_analysis_countries_prompts_dict,
)
from financial_analysis_utils import (
    clean_conversion_block,
    generate_final_response,
    remove_currency_block,
)
from financial_product_catalogue_dec import (
    fpc_local_product_dec_dicts,
    fpc_product_dec_dict,
)
from langchain_core.runnables import RunnableBranch, RunnableLambda, RunnablePassthrough
from langchain_core.runnables.base import RunnableEach
from red_list import (
    red_list,
)


def get_financial_analysis_chain():
    """
    Build and return the end-to-end financial analysis LCEL pipeline.

    The pipeline analyzes company annual reports and supplementary financial
    documents to generate structured insights for credit assessment workflows.
    It combines document ingestion, question generation, retrieval-augmented
    generation (RAG), multilingual question answering, and response aggregation.

    Workflow:
        1. Ingest and preprocess Credit Lens documents.
        2. Generate country-specific financial analysis questions.
        3. Execute QA over Credit Lens content with translation support.
        4. Build and query a vector index for additional reports using RAG.
        5. Execute agent-based QA for supplementary report sections.
        6. Merge Credit Lens and additional report results into a final
           financial analysis response.

    Returns:
        Runnable:
            A LangChain LCEL runnable named
            ``chain_GAILTU-FinancialAnalysis`` that accepts analysis inputs
            (e.g., report sources and target language) and returns a final
            consolidated financial analysis report.

    Notes:
        - Uses GPT models for both standard QA and agent-driven workflows.
        - Supports multilingual output through translation-enabled QA chains.
        - Additional report analysis is executed only when supplementary
          documents are provided and Credit Lens results are available.
        - Financial outputs use standardized currency formatting and
          human-readable number scaling (k, mln, bln).
    """
    config = {
        "llm_model": "gpt-5.2",  # This model is used for RAG and non-RAG requests.
        "llm_model_agent": "gpt-5.4",  # This model is used for agent requests.
        "temperature": 0,
        "top_p": 1,
        "embedding_model_name": "text-embedding-3-large",
        "pdf_loader_type_credit_lens": "PyPDFLoader",  # pdf loader for credit lens
        "pdf_loader_type": "PyMuPDFLoader",  # pdf loader for annual report
        "include_source": False,  # if set to True, the document will be refered to as well, if False only the page number
        "hybrid_search_args": None,
        "remove_duplicate_chunks": True,
        "sentence_chunker_window_size": 5,
        "similarity_top_k": 20,
        "source_key": "additional_report_source",  # This key is needed for the rag chain to know which key to use for the location of the source to ingest.
        "rerank_args": {"top_n": 10, "model": "cross-encoder/ms-marco-MiniLM-L-2-v2"},
        "system_message": "You are an intelligent financial assistant helping credit teams analyze and extract valuable insights from annual reports of companies. If no information is available about asked question, skip that section entirely. Do not include any inferences or placeholders. Always write in a clear and simple way. Use short sentences. Avoid complex words. When mentioning money, use the full currency code (e.g., EUR, USD, GBP) instead of symbols (€, $, £). Convert large numbers into a more readable format using terms like k (thousand), mln (million), or bln (billion). All monetary values should follow the format: CURRENCY_CODE XX unit, e.g., EUR 25 mln.",
    }

    # COMMAND ----------

    # """Pipeline functions"""
    # # in the future when env vars can be passed to the deployment;
    # # we do not need the custom function and we can pass the llm directly in LCEL

    """LCEL pipeline"""

    # define LCEL runnables
    # Assigns a chain of operations to ingest documents
    ingest_chain = (
        RunnableLambda(ingest_documents).bind(
            pdf_loader_type=config["pdf_loader_type_credit_lens"],
            source_key="credit_lens_source",
        )
        | RunnableLambda(clean_conversion_block)
        | RunnableLambda(remove_currency_block)
        | RunnableLambda(combine_documents)
        | RunnableLambda(lambda output: output[0]["text"])
    )

    # Assigns a chain to get country-specific prompts
    get_country_prompts_list = RunnableLambda(
        get_country_prompts_list_per_country
    ).bind(countries_prompts_dict=ltu_financial_analysis_countries_prompts_dict)

    expand_question_with_context_runnable = RunnableLambda(expand_question_list).bind(
        keys=["generated_report_language", "context"]
    )

    qa_chain_with_translation = get_qa_chain_with_translation(
        system_prompt=config["system_message"],
        llm_model=config["llm_model"],
        top_p=config["top_p"],
        keys_to_select=["question", "answer", "title"],
    )

    credit_lens_chain = (
        {
            "questions": get_country_prompts_list,
            "context": ingest_chain,
            "generated_report_language": itemgetter("generated_report_language"),
        }
        | expand_question_with_context_runnable
        | RunnableEach(bound=qa_chain_with_translation)
    )

    credit_lens_chain_step = RunnableBranch(
        (
            lambda x: x["credit_lens_source"] != "",
            credit_lens_chain,
        ),
        lambda x: [],
    )

    # Create a passthrough step to assign the country prompts dictionary
    expand_question_with_collection_name_runnable = RunnableLambda(
        expand_question_list
    ).bind(keys=["generated_report_language", "collection_name"])

    agent_qa_chain_with_translation = get_agent_qa_chain_with_translation(
        config,
        keys_to_select=["title", "question", "answer"],
    )

    build_section_inputs_step = RunnableLambda(build_section_inputs)

    additional_report_core_chain = (
        {
            "collection_name": itemgetter("rag_collection_name"),
            "generated_report_language": itemgetter("generated_report_language"),
            "credit_lens_chain_responses": itemgetter("credit_lens_chain_responses"),
        }
        | build_section_inputs_step
        | expand_question_with_collection_name_runnable
        | RunnableEach(bound=agent_qa_chain_with_translation).with_config(
            max_concurrency=2
        )
    )

    # The code defines a RunnableBranch named additional_report_chain that processes an input dictionary x based on the presence or absence of the key "additional_report_source".
    # Only when additional_report_source is not None, the additional_report_core_chain is invoked.
    additional_report_chain_step = RunnableBranch(
        (
            lambda x: (
                x.get("additional_report_source", "") != ""
                and bool(x.get("credit_lens_chain_responses"))
            ),
            additional_report_core_chain,
        ),
        lambda x: [],
    )

    # # Step to assign the final response generation function
    get_final_response_step = RunnablePassthrough.assign(
        financial_analysis_responses=RunnableLambda(generate_final_response)
    )

    # Define the financial analysis chain
    financial_analysis_chain = (
        RunnablePassthrough.assign(
            credit_lens_chain_responses=credit_lens_chain_step,
        )
        | RunnablePassthrough.assign(
            additional_report_chain_responses=additional_report_chain_step
        )
        | get_final_response_step
    )
    financial_analysis_chain.name = "chain_GAILTU-FinancialAnalysis"

    return financial_analysis_chain


def get_annual_report_chain(
    return_rag_chain=False,
):
    """
    Build and configure the annual report generation chain.

    This factory function creates a Retrieval-Augmented Generation (RAG) pipeline
    for annual report analysis and summarization. The pipeline combines document
    retrieval, language detection, country-specific prompt generation, financial
    analysis, ESG validation, product catalogue enrichment, and issue-page
    referencing to generate structured annual report outputs.

    The chain uses:
        - RAG-based question answering for report content extraction.
        - Agent-based reasoning for country-specific insights.
        - Financial analysis prompts tailored to country requirements.
        - Automatic language detection and translation support.
        - ESG compliance checks.
        - Financial product catalogue enrichment.
        - Source page tracking for report references.

    Args:
        return_rag_chain (bool, optional):
            If True, returns both the complete annual report chain and the
            underlying RAG retrieval chain. If False, returns only the complete
            annual report chain. Defaults to False.

    Returns:
        Runnable:
            The fully configured annual report generation chain when
            `return_rag_chain` is False.

        tuple[Runnable, Runnable]:
            A tuple containing:
                - annual_report_final_chain: The complete report generation chain.
                - rag_chain: The underlying retrieval and QA chain.
            Returned only when `return_rag_chain` is True.

    Notes:
        - Uses GPT-based models for both retrieval QA and agent workflows.
        - Relies on sentence-window retrieval for improved context grounding.
        - Country-specific prompts are loaded from predefined prompt dictionaries.
        - Financial and ESG post-processing steps are applied before returning
          the final report output.
    """
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
        "system_message": """You are an intelligent assistant that summarizes complex content into clear, structured outputs and extracts key financial insights from annual reports. Follow these rules:
        Structure
        - Add up to 4 key bullet points for major details, metrics, or actions, and after each bullet point, provide a short summary. Important: Do not use nested bullet points. Each bullet point must stand alone and include its short explanation in the same line.
        - Skip sections entirely if no information is available. Do not fabricate or assume data.

        Style
        - Use clear, concise sentences and avoid jargon.
        - Maintain a professional, neutral tone.
        - For financial content:
            - Use full currency codes (e.g., EUR, USD, GBP) instead of symbols.
            - Convert large numbers into readable formats: k (thousand), mln (million), bln (billion).
            - Format monetary values as: CURRENCY_CODE XX unit (e.g., EUR 25 mln).
        - Focus only on major financial metrics, trends, risks, and decisions; ignore minor details.

        Formatting
        - Keep each section under 200 words.
        - Do not fabricate or assume information; summarize or paraphrase only what is clearly stated.""",
    }

    (
        rag_chain,
        index_chain,
        chain_without_index,
    ) = get_sentence_window_rag_chain_from_config(config)

    agent_country_prompts_list = RunnableLambda(
        get_country_prompts_list_per_country
    ).bind(countries_prompts_dict=ltu_annual_report_countries_agent_prompts_dict)

    rag_country_prompts_list = RunnableLambda(
        get_country_prompts_list_per_country
    ).bind(countries_prompts_dict=ltu_annual_report_countries_prompts_dict)

    financial_analysis_country_prompts_list = RunnableLambda(
        get_country_prompts_list_per_country
    ).bind(countries_prompts_dict=ltu_financial_analysis_countries_prompts_dict)

    update_agent_questions_step = RunnablePassthrough.assign(
        agent_questions=RunnableLambda(update_agent_questions)
    )

    agent_expand_question_with_context_runnable = RunnableLambda(
        expand_question_list
    ).bind(
        questions_key="agent_questions",
        keys=["generated_report_language", "collection_name"],
    )

    rag_expand_question_with_context_runnable = RunnableLambda(
        expand_question_list
    ).bind(
        questions_key="rag_questions",
        keys=["generated_report_language", "collection_name"],
    )

    qa_chain_with_translation = get_qa_chain_with_translation(
        system_prompt=config["system_message"],
        llm_model=config["llm_model"],
        top_p=config["top_p"],
        keys_to_select=["title", "question", "answer", "issued_pages", "page_no"],
    )

    agent_qa_chain_with_translation = get_ar_agent_qa_chain_with_translation(
        config,
        keys_to_select=["title", "question", "answer"],
    )

    core_chain = (
        RunnablePassthrough.assign(
            rag_questions=rag_country_prompts_list,
            agent_questions=agent_country_prompts_list,
            financial_analysis_questions=financial_analysis_country_prompts_list,
            collection_name=itemgetter("rag_collection_name"),
            generated_report_language=itemgetter("generated_report_language"),
            credit_lens_source=itemgetter("credit_lens_source"),
        )
        | update_agent_questions_step
        | RunnablePassthrough.assign(
            rag_responses=rag_expand_question_with_context_runnable
            | RunnableEach(
                bound=chain_without_index | qa_chain_with_translation
            ).with_config(max_concurrency=2),
            agent_responses=agent_expand_question_with_context_runnable
            | RunnableEach(bound=agent_qa_chain_with_translation).with_config(
                max_concurrency=2
            ),
        )
    )

    add_financial_product_catalogue_step = RunnablePassthrough.assign(
        rag_responses=RunnableLambda(
            update_responses_with_financial_product_catalogue
        ).bind(
            fpc_local_product_dec_dicts=fpc_local_product_dec_dicts,
            fpc_product_dec_dict=fpc_product_dec_dict,
        )
    )

    add_issue_pages_reference_step = RunnablePassthrough.assign(
        rag_responses=RunnableLambda(update_responses_with_issue_pages)
    )

    update_esg_checkers_step = RunnablePassthrough.assign(
        rag_responses=RunnableLambda(update_esg_checkers).bind(red_list=red_list)
    )

    annual_report_final_chain = (
        core_chain
        | update_esg_checkers_step
        | add_financial_product_catalogue_step
        | add_issue_pages_reference_step
    )

    annual_report_final_chain.name = "chain_GAILTU-AnnualReport"

    if return_rag_chain:
        return annual_report_final_chain, index_chain | chain_without_index
    else:
        return annual_report_final_chain
