This folder holds the code for any custom components that can be used in a LangChain pipeline with LCEL.
Given the step functions are defined, below is an example of a LCEL definition for a E2E RAG pipeline:

```
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough

"""LCEL RAG pipeline"""

# define LCEL runnables
ingest_step = RunnablePassthrough.assign(
    documents={
        "folder_path": itemgetter("folder_path"),
        "storage_account": itemgetter("storage_account"),
    }
    | RunnableLambda(ingest_documents)
)

chunk_step = RunnablePassthrough.assign(
    chunked_documents=itemgetter("documents") | RunnableLambda(chunk_func)
)

retrieve_step = RunnablePassthrough.assign(
    relevant_docs={
        "chunked_documents": itemgetter("chunked_documents"),
        "question": itemgetter("question"),
    }
    | RunnableLambda(retriever_func)
)

context_step = {
    "context": itemgetter("relevant_docs") | RunnableLambda(combine_fun),
    "question": itemgetter("question"),
}

prompt_step = ChatPromptTemplate.from_template(template_for_final_prompt)

# combine the steps into a chain
chain = (
    ingest_step
    | chunk_step
    | retrieve_step
    | context_step
    | prompt_step
    | RunnableLambda(llm_func)
    | StrOutputParser()
)
```