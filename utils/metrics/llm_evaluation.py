from custom_lcel_components.llm import create_llm
from langchain_core.prompts import ChatPromptTemplate
from mlflow.entities import Feedback

LLM = create_llm(
    azure_deployment="gpt-4.1",
    api_version="2024-05-01-preview",
    temperature=0,
)

import json

from mlflow.genai.scorers import scorer


def parse_trace(inputs, outputs):
    """Extract the question and answer from a trace's inputs and outputs.

    Args:
        inputs: Trace inputs containing a ``messages`` key.
        outputs: JSON-encoded trace outputs containing a ``choices`` key.

    Returns:
        A tuple ``(question, answer)`` as JSON strings.

    Raises:
        ValueError: If the question or answer cannot be parsed.
    """
    try:
        question = json.dumps(inputs["messages"])
    except Exception as e:
        raise ValueError("Error with question parse: " + str(e))

    try:
        answer = json.dumps(json.loads(outputs)["choices"])
    except Exception as e:
        raise ValueError("Error with answer parse: " + str(e))
    return question, answer


def _is_valid_score(score: str) -> bool:
    """A score is valid if it is 'yes', 'no', or a number."""
    normalized = score.split(":", 1)[-1].strip().lower()
    if normalized in ("yes", "no"):
        return True
    try:
        float(normalized)
        return True
    except ValueError:
        return False


def get_score(question, answer, prompt, max_retries: int = 4) -> Feedback:
    """Run the evaluation prompt and return a validated Feedback.

    The chain is re-invoked until the parsed score is valid (``yes``, ``no``,
    or a number) or ``max_retries`` is reached.

    Args:
        question: The reference context/question as a JSON string.
        answer: The answer to evaluate as a JSON string.
        prompt: The chat prompt template used to score the answer.
        max_retries: Maximum number of evaluation attempts.

    Returns:
        A :class:`Feedback` with the score value and justification rationale.
        The value is ``None`` if no valid score is produced within the retries.
    """

    score_chain = prompt | LLM
    score = ""
    justification = ""
    for attempt in range(max_retries):
        evaluation = score_chain.invoke(
            {"question": question, "answer": answer}
        ).content
        lines = evaluation.split("\n")
        score = lines[0].replace("**", "")
        justification = lines[1] if len(lines) > 1 else ""
        if _is_valid_score(score):
            break
    else:
        score = None
    print("score: ", score)
    return Feedback(value=score, rationale=justification)


@scorer
def hallucination(inputs, outputs) -> Feedback:
    """Score whether the answer contains hallucinations unsupported by the context."""
    question, answer = parse_trace(inputs, outputs)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """You are an evaluator tasked with determining whether the provided answer contains hallucinations.
    
    ### Inputs:
    - **Answer:** {answer}
    - **Reference Context:** {question}  (This is the ground truth information)
    
    ### Task:
    Decide if the answer includes any information that is **not supported by the reference context** or contradicts it.
    
    ### Output:
    Respond with only one of the following:
    - **YES** if the answer contains hallucinated or unsupported information.
    - **NO** if the answer is fully supported by the context and contains no hallucinations.
    
    Keep the Justification **very concise**. Structure it in two parts:
    - **Strengths:** 
    - **Weaknesses:** (omit Weaknesses if NO; omit strengths if YES).
    
    Let the result be in the following format:
    Score: <Yes or No> \n
    Justification: <Detailed Explanation>
    
    """,
            )
        ]
    )
    feedback = get_score(question, answer, prompt)

    return feedback


@scorer
def numerical_inaccuracy(inputs, outputs) -> Feedback:
    """Score whether numbers in the answer faithfully match the source text."""
    question, answer = parse_trace(inputs, outputs)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """You are a dedicated Numerical Data Integrity Auditor. Your sole function is to compare the figures in the provided LLM Summary against the Source Text (original document) to identify and report any numerical discrepancies, **while allowing for standard rounding**.
    
    ### Evaluation Protocol:
    Scope: ONLY compare numerical data (dates, percentages, currency amounts, counts, totals, etc.). Ignore all non-numerical content.
    Matching: Check if every number present in the Summary is a **faithful representation** of the figure reported in the Source Text, following these rules:
    **Exact Match Required:** Dates (e.g., 2023, Q3/2024), specific counts (e.g., 5 employees), and unique identifiers (e.g., Form 10-K) must match exactly.
    **Rounding Tolerance:** Discrepancies due to **simple, mathematically correct rounding** (e.g., $99.7 Million to $100 Million) are **not** counted as inconsistencies. An inconsistency only exists if the number in the Summary is a fundamental error or a miscalculation.

    ### Inputs:
    Source Text: {question}
    Summary: {answer}

    ### Your Task: Evaluate the Summary based on the Evaluation Protocol and assign YES or NO and add the justification. If the numbers in the summary are a failthful representation with no discrepencies in the source text assign NO else assign YES.
   
    Keep the justification extremely concise. Structure it in two parts based on the score:
    - **Strengths:** 
    - **Weaknesses:** (omit Weaknesses if NO; omit strengths if YES).
    

    Let the result be in the following format:
    Score: <Yes or No> \n
    Justification: <Detailed Explanation>""",
            )
        ]
    )
    feedback = get_score(question, answer, prompt)

    return feedback
