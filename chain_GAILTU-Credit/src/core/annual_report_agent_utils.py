from operator import itemgetter

from agent_system_prompt import rag_system_prompt
from custom_lcel_components.chains import get_translate_chain
from custom_lcel_components.create_agent import create_llm_agent
from custom_lcel_components.create_rag_agent import get_rag_agent_chain
from custom_lcel_components.utils import (
    select_columns,
)
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda


def get_reviewer_chain(config):
    """
    Build and return a reviewer chain that critiques and rewrites
    an annual-report analysis draft.

    The chain:
    1. Creates a reviewer LLM agent using the configured model and
       reviewer-specific system prompt.
    2. Generates a review prompt containing the draft response.
    3. Invokes the reviewer agent to assess and improve the draft.
    4. Extracts the final revised answer from the agent's response.

    Args:
        config (dict): Configuration dictionary containing runtime
            settings. Must include the key ``llm_model_agent`` that
            specifies the reviewer model.

    Returns:
        Runnable: A LangChain runnable chain that accepts a
        ``draft_response`` input and returns a dictionary in the form:

            {
                "answer": <reviewed_and_rewritten_response>
            }
    """
    from agent_system_prompt import reviewer_system_prompt

    reviewer_agent = create_llm_agent(
        model_name=config["llm_model_agent"],
        tools=[],
        system_prompt=reviewer_system_prompt,
    )

    # Prompt: review and improvement
    review_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "user",
                (
                    "Review and rewrite the following annual-report analysis.\n"
                    "Draft answer:\n{draft_response}"
                ),
            )
        ]
    )

    extract_message_content = RunnableLambda(
        lambda response: {"answer": response.get("messages", [])[-1].content}
    )

    reviewer_chain = review_prompt | reviewer_agent | extract_message_content

    return reviewer_chain


def get_ar_agent_qa_chain_with_translation(
    config,
    keys_to_select,
):
    """
    Build an agent QA chain that generates an answer, reviews it, translates
    it to the requested language, and returns only the selected output fields.

    The chain performs the following steps:
    1. Generates a draft answer using the RAG agent chain.
    2. Reviews and refines the draft answer using the reviewer chain.
    3. Extracts the reviewed answer.
    4. Translates the answer into the target language specified by
       ``generated_report_language``.
    5. Selects and returns the requested columns.

    Args:
        config: Configuration object used to initialize the component chains.
        keys_to_select: Collection of output field names to include.

    Returns:
        Runnable: A composed LangChain runnable that produces translated,
        reviewed answers and returns only the specified output fields.
    """
    rag_chain = get_rag_agent_chain(
        config,
        keys_to_select=["answer", "page_no"],
        agent_system_prompt=rag_system_prompt,
    )
    reviewer_chain = get_reviewer_chain(config)
    translate_chain = get_translate_chain()

    agent_qa_chain = (
        {
            "title": itemgetter("title"),
            "question": itemgetter("question"),
            "generated_report_language": itemgetter("generated_report_language"),
            "answer": (
                {"draft_response": rag_chain} | reviewer_chain | itemgetter("answer")
            ),
        }
        | translate_chain
        | RunnableLambda(select_columns).bind(keys_to_select=keys_to_select)
    )

    return agent_qa_chain
