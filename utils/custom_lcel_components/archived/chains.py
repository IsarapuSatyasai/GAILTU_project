from operator import itemgetter

from custom_lcel_components.indexing import (
    derive_collection_name_from_source,
    index_docs_with_hierarchy,
)
from custom_lcel_components.ingest import ingest_documents
from custom_lcel_components.postretrieval import (
    create_context_from_chunks,
    get_issue_pages_no_from_chunks,
    get_page_no_from_chunks,
    rerank_chunks,
)
from custom_lcel_components.preprocessing import (
    clean_documents,
)
from custom_lcel_components.retrieval import (
    retrieve_from_llama_store,
)
from custom_lcel_components.variables import (
    API_VERSION,
    SEED,
)
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts.chat import (
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_openai import AzureChatOpenAI

TRANSFORM_QUERY_TEMPLATE = """Please write a passage to answer the question\nTry to include as many key details as possible.\n\n\n{context_str}\n\n\nPassage:"""
TRANSFORMED_QUERY = """{question}\n{generated_answer}
"""
QUERY_KEY = "question"
NUM_QUERIES_KEY = "num_queries"

QUERY_GENERATION_TEMPLATE = """"You are a helpful assistant that generates multiple search queries based on a single input query. Do not use any form of enumeration.
Generate {num_queries} search queries, one on each line, related to the following input query:  
Query: {question}"""
SINGLE_QUERY_GENERATION_TEMPLATE = """"You are a helpful assistant that generates a single search query based on a single input query.   Do not use any form of enumeration.
Generate {num_queries} search query, related to the following input query:
Query: {question} """


def get_query_transform_chain(llm_step):
    """This function sets up a chain of operations to generate and transform search queries based on an input query.

    Example:
    from langchain_openai import AzureChatOpenAI
    from custom_lcel_components.chains import get_query_transform_chain

    llm_step = AzureChatOpenAI(
        azure_deployment="gpt-4o",
        top_p=1,
        temperature=0,
    )

    chain = get_query_transform_chain(llm_step)
    output = chain.invoke({"question":"Can you summarize the annual report?"})
    """
    generate_answer_chain = RunnablePassthrough.assign(
        generated_answer={"context_str": itemgetter(QUERY_KEY)}
        | ChatPromptTemplate.from_template(TRANSFORM_QUERY_TEMPLATE)
        | llm_step
        | StrOutputParser()
    )

    combine_answer_and_question_chain = (
        {
            QUERY_KEY: itemgetter(QUERY_KEY),
            "generated_answer": itemgetter("generated_answer"),
        }
        | ChatPromptTemplate.from_template(TRANSFORMED_QUERY)
        | StrOutputParser()
    )

    query_transform_chain = generate_answer_chain | combine_answer_and_question_chain
    return query_transform_chain


def get_query_generation_chain(llm_step, num_queries=5):
    """This function sets up a chain of operations to generate search queries based on an input query.
    Depending on the number of queries specified, it uses either a single query template or a multiple query template.
    The chain processes the input query and generates the desired number of search queries.
    Example:

    from langchain_openai import AzureChatOpenAI
    from custom_lcel_components.chains import get_query_generation_chain

    llm_step = AzureChatOpenAI(
        azure_deployment="gpt-4o",
        top_p=1,
        temperature=0,
    )

    chain = get_query_generation_chain(llm_step)
    output = chain.invoke({"question":"Can you summarize the annual report?"})
    """
    if num_queries == 1:
        query_template = SINGLE_QUERY_GENERATION_TEMPLATE.replace(
            "{num_queries}", str(num_queries)
        )
    else:
        query_template = QUERY_GENERATION_TEMPLATE.replace(
            "{num_queries}", str(num_queries)
        )

    generate_query_chain = RunnablePassthrough.assign(
        generated_queries=ChatPromptTemplate.from_template(query_template)
        | llm_step
        | StrOutputParser()
    )

    combine_answer_chain = (
        {
            QUERY_KEY: itemgetter(QUERY_KEY),
            "generated_answer": itemgetter("generated_queries"),
        }
        | ChatPromptTemplate.from_template(TRANSFORMED_QUERY)
        | StrOutputParser()
    )

    query_generation_chain = generate_query_chain | combine_answer_chain

    return query_generation_chain


def get_pdf_loader_chain(config):
    """
    Creates a pdf loader chain to load and clean text from PDF files.

    This function builds a chain of operations to process PDF documents.
    The chain starts with loading the documents using a specified PDF loader type
    and then proceeds to clean the loaded documents.

    Args:
        config (dict): Configuration dictionary containing the keys
                       "pdf_loader_type" and "source_key".

    Returns:
        RunnableChain: A chain of operations that first ingests the PDF documents
                       and then cleans the loaded documents.
    """
    ingest_documents_step = RunnableLambda(ingest_documents).bind(
        pdf_loader_type=config["pdf_loader_type"], source_key=config["source_key"]
    )

    pdf_loader_chain = ingest_documents_step | RunnableLambda(clean_documents)

    return pdf_loader_chain


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

    if temperature:
        llm = (
            AzureChatOpenAI(
                azure_deployment=llm_model,
                top_p=top_p,
                api_version=API_VERSION,
                seed=SEED,
                temperature=temperature,
            )
            .with_retry(wait_exponential_jitter=True, stop_after_attempt=3)
            .with_fallbacks([RunnableLambda(lambda _: AIMessage(content=""))])
        )
    else:
        llm = (
            AzureChatOpenAI(
                azure_deployment=llm_model,
                top_p=top_p,
                api_version=API_VERSION,
                seed=SEED,
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


def get_hierarchical_rag_chain_from_config(config):
    """This chain takes into account the hierarchy of the chunks in the documents.
    In the retrieval step this is used to extract parent chunks in case many child chunks have a high relevance score.

    On a high level this chain includes the following steps:
    -derive collection name
    -ingest
    -clean documents
    -index (including the hierarchical chunking step)
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

    preproc_core_chain = ingest_documents_step | RunnableLambda(clean_documents)
    preproc_core_chain.name = "preprocessing_chain"
    preproc_chain = {
        "documents": preproc_core_chain,
        "collection_name": itemgetter("collection_name"),
    }

    # Step to index with Chroma
    index_step = RunnableLambda(index_docs_with_hierarchy).bind(
        embedding_model_name=config["embedding_model_name"],
        chunk_sizes=config["hierarch_chunk_sizes"],
    )

    index_core_chain = derive_collection_step | preproc_chain | index_step
    index_core_chain.name = "index_chain_hierarch"

    retrieve_step = RunnablePassthrough.assign(
        retrieved_chunks=RunnableLambda(retrieve_from_llama_store).bind(
            embedding_model_name=config["embedding_model_name"],
            similarity_top_k=config["similarity_top_k"],
            hybrid_search_args=config["hybrid_search_args"],
            hierarch_retrieval=True,
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
    rag_chain.name = "RAG_chain_hierarch"

    return rag_chain, index_core_chain, chain_without_index
