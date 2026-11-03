import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

from custom_lcel_components.create_agent import create_llm_agent
from custom_lcel_components.create_tool import create_rag_tool

logger = logging.getLogger(__name__)


def get_rag_agent_chain(config, keys_to_select, agent_system_prompt):
    """
    Create and return a Retrieval-Augmented Generation (RAG) agent chain.

    The chain performs the following steps:
    1. Creates a RAG tool using the provided configuration.
    2. Creates an LLM agent that can use the RAG tool to retrieve
       information from an annual report.
    3. Generates a prompt containing the user's question and source.
    4. Invokes the agent and extracts the content of the final response
       message.

    Args:
        config (dict):
            Configuration dictionary containing agent settings, including
            the LLM model name under the key ``"llm_model_agent"``.
        keys_to_select: Collection of output field names to include.
        agent_system_prompt (str):
            System prompt that defines the agent's behavior and instructions.

    Returns:
        Runnable:
            A LangChain runnable chain that accepts ``question`` and
            ``collection_name`` inputs and returns the generated answer as
            message content.
    """
    # create agent chain
    rag_tool = create_rag_tool(config, keys_to_select)

    rag_agent = create_llm_agent(
        model_name=config["llm_model_agent"],
        tools=[rag_tool],
        system_prompt=agent_system_prompt,
    )

    # Prompt: initial answer generation
    rag_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "user",
                (
                    "Answer this question using the annual report:\n"
                    "Question: {question}\n"
                    "collection_name: {collection_name}"
                ),
            )
        ]
    )

    # extract_message_content = RunnableLambda(
    #     lambda response: (
    #         response["messages"][-1].content
    #         if response.get("messages")
    #         else None
    #     )
    # )
    extract_message_content = RunnableLambda(
        lambda response: (
            response["messages"][-1].content
            if response.get("messages")
            else (logger.warning("No messages found in response."), "")[1]
        )
    )

    rag_agent_chain = rag_prompt | rag_agent | extract_message_content

    return rag_agent_chain
