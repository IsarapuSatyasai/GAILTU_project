from operator import itemgetter

from agent_system_prompt import financial_analysis_agent_system_prompt
from custom_lcel_components.chains import get_translate_chain
from custom_lcel_components.create_rag_agent import get_rag_agent_chain
from custom_lcel_components.utils import (
    select_columns,
)
from langchain_core.runnables import RunnableLambda

section_analysis_question_template = """
Rewrite this financial analysis with additional annual-report-supported reasons.

Financial analysis:
{financial_analysis}
""".strip()


def build_section_inputs(_dict):
    """
    Build section-level analysis inputs from credit lens responses.

    This function extracts the generated report language and credit lens
    responses from the input dictionary. It converts the responses into a
    lookup dictionary keyed by response title and generates a question payload
    for each predefined financial analysis section.

    Expected structure of `_dict`:
       {
          "credit_lens_chain_responses": [
                {
                   "title": "Financial performance realised and projected$Profitability",
                   "answer": "..."
                },
                {
                   "title": "Financial performance realised and projected$Liquidity / Cash Flow",
                   "answer": "..."
                },
                {
                   "title": "Financial performance realised and projected$Solvency",
                   "answer": "..."
                }
          ],
          "generated_report_language": "English"
       }

    Args:
       _dict (dict): Source dictionary containing credit lens responses and
          generated report language.

    Returns:
       _dict: The updated input dictionary with an additional
             ``questions`` key containing a list of section payloads.
    """
    sections = [
        "Financial performance realised and projected$Profitability",
        "Financial performance realised and projected$Liquidity / Cash Flow",
        "Financial performance realised and projected$Solvency",
    ]

    credit_responses = _dict.get("credit_lens_chain_responses", [])

    credit_response_map = {
        item.get("title"): item.get("answer", "")
        for item in credit_responses
        if isinstance(item, dict)
    }

    questions = [
        {
            "title": section,
            "question": section_analysis_question_template.format(
                financial_analysis=credit_response_map.get(section, "")
            ),
        }
        for section in sections
    ]

    _dict["questions"] = questions

    return _dict


def get_agent_qa_chain_with_translation(
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
        agent_system_prompt=financial_analysis_agent_system_prompt,
    )
    translate_chain = get_translate_chain()

    agent_qa_chain = (
        {
            "title": itemgetter("title"),
            "question": itemgetter("question"),
            "generated_report_language": itemgetter("generated_report_language"),
            "answer": rag_chain,
        }
        | translate_chain
        | RunnableLambda(select_columns).bind(keys_to_select=keys_to_select)
    )

    return agent_qa_chain
