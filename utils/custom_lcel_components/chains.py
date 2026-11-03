from operator import itemgetter

from langchain_core.messages import AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts.chat import (
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from langchain_core.runnables import RunnableBranch, RunnableLambda, RunnablePassthrough

from custom_lcel_components.chunk import base_chunker, sentence_chunker
from custom_lcel_components.indexing import (
    derive_collection_name_from_source,
    index_chunks_llama,
)
from custom_lcel_components.ingest import ingest_documents
from custom_lcel_components.llm import create_llm
from custom_lcel_components.postretrieval import (
    add_sentence_window,
    create_context_from_chunks,
    get_issue_pages_no_from_chunks,
    get_page_no_from_chunks,
    rerank_chunks,
)
from custom_lcel_components.preprocessing import (
    clean_documents,
    combine_documents,
    sentence_window_cleaning_step,
)
from custom_lcel_components.retrieval import (
    retrieve_from_llama_store,
)
from custom_lcel_components.utils import (
    detect_language,
    select_columns,
)

# from custom_lcel_components.llm import disabled_trace_llm, session_id_llm

"""
This file contains the implementation of frequently used chains. See the below notebook for an example.
Notebook example:
# COMMAND ----------
%pip install -r ../../scripts/requirements.txt
# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------

import sys
import os 

sys.path.insert(0, "../../scripts")

os.environ["OPENAI_API_KEY"] = dbutils.secrets.get(
    scope="azure-key-vault-scope", key="openai-eu-accesskey"
)
os.environ["SA_ACCESSKEY"] = dbutils.secrets.get(
    scope="azure-key-vault-scope", key="sta-eu-accesskey"
)
file_location = "projects/LTU/France/annual_reports/LOXAM-Q4-FY-2022-audited-Investor-Report.pdf"
ENVIRONMENT="dev"

from custom_lcel_components.chains import get_sentence_window_rag_chain_from_config
config = {
    "llm_model": "gpt-4o",
    "temperature": 0,
    "top_p": 1,
    "embedding_model_name": "text-embedding-3-large",
    "pdf_loader_type": "PyMuPDFLoader",
    "sentence_chunker_window_size": 5,
    "similarity_top_k": 20,
    "rerank_args": {"top_n": 10, "model": "cross-encoder/ms-marco-MiniLM-L-2-v2"},
    "system_message": "You are an intelligent financial assistant helping credit teams analyze and extract valuable insights from annual reports of companies. If no information is available about asked question, skip that section entirely. Do not include any inferences or placeholders.",
}
rag_chain = get_sentence_window_rag_chain_from_config(config)


output = await rag_chain.ainvoke({
    "question": "who is the CEO?",
    "source": file_location,
})

# COMMAND ----------
#This function can be used to reset the vector db, the collection name can be found as warning of the chain invoke script
from custom_lcel_components.retrieval import (
    reset_chroma_db,
)
reset_chroma_db("annualreportsLOXAMQ4FY2022auditedInvestorReportpdf")"""


def get_sentence_window_rag_chain_from_config(config):
    """On a high level this chain includes the following steps:
    -derive collection name
    -ingest
    -clean documents
    -chunk document into sentences
    -index
    -retrieve
    -addition of the window sentences to the retrieved ones
    -reranking
    -context creation (merging the reranked chunks into one string)
    -prompt augmentation (adding the context and question together into the prompt)
    -answer generation (sending the prompt to GPT)
    """

    ingest_documents_step = RunnableLambda(ingest_documents).bind(
        pdf_loader_type=config["pdf_loader_type"], source_key=config["source_key"]
    )

    derive_collection_step = RunnablePassthrough.assign(
        collection_name=RunnableLambda(derive_collection_name_from_source).bind(
            source_key=config["source_key"]
        )
    )
    derive_collection_step.name = "collection_name_step"

    preproc_core_chain = (
        ingest_documents_step
        | RunnableLambda(clean_documents).bind(
            custom_cleaning_step=sentence_window_cleaning_step
        )
        | RunnableLambda(sentence_chunker).bind(
            remove_duplicates=config["remove_duplicate_chunks"]
        )
    )
    preproc_core_chain.name = "preprocessing_chain"
    preproc_chain = {
        "chunks": preproc_core_chain,
        "collection_name": itemgetter("collection_name"),
    }

    # Step to index with Chroma
    index_step = RunnableLambda(index_chunks_llama).bind(
        embedding_model_name=config["embedding_model_name"],
        sentence_window_retrieval=True,
        window_size=config["sentence_chunker_window_size"],
    )

    index_core_chain = derive_collection_step | preproc_chain | index_step
    index_core_chain.name = "index_chain"

    retrieve_step = RunnablePassthrough.assign(
        retrieved_chunks=RunnableLambda(retrieve_from_llama_store).bind(
            embedding_model_name=config["embedding_model_name"],
            similarity_top_k=config["similarity_top_k"],
            hybrid_search_args=config["hybrid_search_args"],
        )
    )

    sentence_window_step = RunnablePassthrough.assign(
        retrieved_chunks=RunnableLambda(add_sentence_window),
    )

    rerank_step = RunnablePassthrough.assign(
        retrieved_chunks=RunnableLambda(rerank_chunks),
    )

    context_step = RunnablePassthrough.assign(
        page_no=RunnableLambda(get_page_no_from_chunks).bind(
            include_source=config["include_source"]
        ),
        context=RunnableLambda(create_context_from_chunks),
        issued_pages=RunnableLambda(get_issue_pages_no_from_chunks),
    )

    chain_without_index = (
        retrieve_step | sentence_window_step | rerank_step | context_step
    )
    chain_without_index.name = "retrieval_chain"

    rag_chain = (
        RunnablePassthrough.assign(collection_name=index_core_chain)
        | retrieve_step
        | sentence_window_step
        | rerank_step
        | context_step
    )
    rag_chain.name = "RAG_chain_sentence_window"

    return rag_chain, index_core_chain, chain_without_index


def get_default_rag_chain_from_config(config):
    """This chain uses a fixed size chunker. Other than chunking strategy and the sentence window addition, the chain is similar to the sentence window chain.
    -derive collection name
    -ingest
    -clean documents
    -chunk document into fixed size chunks
    -index
    -retrieve
    -reranking
    -context creation (merging the reranked chunks into one string)
    -prompt augmentation (adding the context and question together into the prompt)
    -answer generation (sending the prompt to GPT)
    """
    ingest_documents_step = RunnableLambda(ingest_documents).bind(
        pdf_loader_type=config["pdf_loader_type"], source_key=config["source_key"]
    )

    derive_collection_step = RunnablePassthrough.assign(
        collection_name=RunnableLambda(derive_collection_name_from_source).bind(
            source_key=config["source_key"]
        )
    )
    derive_collection_step.name = "collection_name_step"

    preproc_core_chain = (
        ingest_documents_step
        | RunnableLambda(clean_documents)
        | RunnableLambda(base_chunker).bind(
            remove_duplicates=config["remove_duplicate_chunks"],
            chunk_size=config["chunk_size"],
            chunk_overlap=config["chunk_overlap"],
        )
    )
    preproc_core_chain.name = "preprocessing_chain"
    preproc_chain = {
        "chunks": preproc_core_chain,
        "collection_name": itemgetter("collection_name"),
    }

    # Step to index with Chroma
    index_step = RunnableLambda(index_chunks_llama).bind(
        embedding_model_name=config["embedding_model_name"],
    )

    index_core_chain = derive_collection_step | preproc_chain | index_step
    index_core_chain.name = "index_chain"

    retrieve_step = RunnablePassthrough.assign(
        retrieved_chunks=RunnableLambda(retrieve_from_llama_store).bind(
            embedding_model_name=config["embedding_model_name"],
            similarity_top_k=config["similarity_top_k"],
            hybrid_search_args=config["hybrid_search_args"],
        )
    )

    rerank_step = RunnablePassthrough.assign(
        retrieved_chunks=RunnableLambda(rerank_chunks),
    )

    context_step = RunnablePassthrough.assign(
        page_no=RunnableLambda(get_page_no_from_chunks).bind(
            include_source=config["include_source"]
        ),
        context=RunnableLambda(create_context_from_chunks),
        issued_pages=RunnableLambda(get_issue_pages_no_from_chunks),
    )

    qa_chain = get_qa_chain(
        system_prompt=config["system_message"],
        llm_model=config["llm_model"],
        top_p=config["top_p"],
    )

    chain_without_index = retrieve_step | rerank_step | context_step | qa_chain
    chain_without_index.name = "retrieval_chain"

    rag_chain = (
        RunnablePassthrough.assign(collection_name=index_core_chain)
        | retrieve_step
        | rerank_step
        | context_step
        | qa_chain
    )
    rag_chain.name = "RAG_chain_default"

    return rag_chain, index_core_chain, chain_without_index


def get_chain_without_rag_from_config(config):
    """
    Creates a processing chain for the LCEL pipeline without retrieval-augmented generation (RAG).

    Args:
        config (dict): Configuration dictionary containing parameters for the pipeline.

    Returns:
        chain_without_rag: A processing chain composed of ingest and question-answering
        steps. The output includes both ``answer`` and ``message`` keys, where
        ``message`` mirrors ``answer`` for backward compatibility.
    """
    source_key = config.get("source_key", "source")

    ingest_chain = RunnablePassthrough.assign(
        context=RunnableLambda(ingest_documents).bind(
            pdf_loader_type=config["pdf_loader_type"], source_key=source_key
        )
        | RunnableLambda(clean_documents)
        | RunnableLambda(combine_documents)
        | RunnableLambda(lambda output: output[0]["text"])
    )

    qa_chain = get_qa_chain(
        system_prompt=config["system_message"],
        llm_model=config["llm_model"],
        top_p=config["top_p"],
        temperature=config.get("temperature"),
    )

    chain_without_rag = ingest_chain | qa_chain

    return chain_without_rag


def get_translate_chain():
    """Build a chain that translates the ``answer`` into a target language.

    The chain first detects the language of the incoming ``answer`` and only
    translates when it differs from the requested ``generated_report_language``;
    otherwise the input is passed through unchanged.

    Expected input keys:
        answer (str): The text to (potentially) translate.
        generated_report_language (str): The desired output language.

    Returns:
        Runnable: A chain that returns the input dict with ``answer`` translated
        into ``generated_report_language`` when needed.
    """
    llm = create_llm(
        azure_deployment="gpt-4o",
        top_p=0.1,
        temperature=0,
    )
    system_prompt_translate = SystemMessagePromptTemplate.from_template(
        "You are a multilingual translation assistant. Your primary function is to accurately and fluently translate text between languages while preserving the original meaning, tone, and context."
    )

    # 2️⃣ Define the user prompt (dynamic input from user)
    user_prompt_translate = HumanMessagePromptTemplate.from_template(
        "Please translate the following text into {generated_report_language} and return only the translated text: {answer}"
    )

    chat_prompt_translate = ChatPromptTemplate.from_messages(
        [system_prompt_translate, user_prompt_translate]
    )
    detect_language_chain = RunnablePassthrough.assign(
        detected_language={
            "answer": itemgetter("answer"),
            "generated_report_language": itemgetter("generated_report_language"),
        }
        | RunnableLambda(detect_language)
    )

    translate_step = RunnablePassthrough.assign(
        answer=chat_prompt_translate | llm | StrOutputParser()
    )
    translate_chain = detect_language_chain | RunnableBranch(
        (
            lambda x: x["detected_language"] != x["generated_report_language"],
            translate_step,
        ),
        lambda x: x,
    )

    return translate_chain


def get_qa_chain(system_prompt: str, llm_model: str, top_p: float, temperature=None):
    """Build a question-answering chain backed by Azure OpenAI.

    The chain augments the input with a system prompt and the shared
    ``AUGMENTATION_PROMPT`` template, invokes the LLM, and stores the result
    under the ``answer`` key. The LLM is configured to retry transient errors
    and fall back to an empty message so the chain does not fail hard.

    Args:
        system_prompt (str): System message that sets the assistant's behaviour.
        llm_model (str): Azure deployment name of the chat model to use.
        top_p (float): Nucleus sampling parameter passed to the model.
        temperature (float, optional): Sampling temperature. When falsy, the
            model's default temperature is used.

    Returns:
        Runnable: A chain that adds an ``answer`` key with the model response.
    """
    from custom_lcel_components.variables import AUGMENTATION_PROMPT

    llm = (
        create_llm(
            azure_deployment=llm_model,
            top_p=top_p,
            temperature=temperature if temperature else None,
        )
        .with_retry(wait_exponential_jitter=True, stop_after_attempt=3)
        .with_fallbacks([RunnableLambda(lambda _: AIMessage(content=""))])
    )

    user_prompt = HumanMessagePromptTemplate.from_template(AUGMENTATION_PROMPT)

    system_prompt_runnable = SystemMessagePromptTemplate.from_template(system_prompt)

    prompt_step = ChatPromptTemplate.from_messages(
        [system_prompt_runnable, user_prompt]
    )

    qa_chain = RunnablePassthrough.assign(answer=prompt_step | llm | StrOutputParser())

    return qa_chain


def get_qa_chain_with_translation(
    system_prompt: str,
    llm_model: str,
    top_p: float,
    temperature=None,
    keys_to_select=["question", "answer", "title"],
):
    """Build a question-answering chain with translation.

    This chain first performs question-answering using the specified system
    prompt and LLM model, and then translates the answer into the requested
    language if necessary.

    Args:
        system_prompt (str): System message that sets the assistant's behaviour.
        llm_model (str): Azure deployment name of the chat model to use.
        top_p (float): Nucleus sampling parameter passed to the model.
        temperature (float, optional): Sampling temperature. When falsy, the
            model's default temperature is used.
    returns:
        Runnable: A chain that adds an ``answer`` key with the model response,
        translated into the requested language if needed.
    """

    translate_chain = get_translate_chain()
    qa_chain = get_qa_chain(
        system_prompt=system_prompt,
        llm_model=llm_model,
        top_p=top_p,
        temperature=temperature,
    )

    qa_chain_with_translation = (
        qa_chain
        | translate_chain
        | RunnableLambda(select_columns).bind(keys_to_select=keys_to_select)
    )

    return qa_chain_with_translation
