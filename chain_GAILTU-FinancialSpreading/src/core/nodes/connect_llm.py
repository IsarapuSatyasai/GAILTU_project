"""Node: Connect to LLM.

Initialises the Azure OpenAI chat model and validates the connection.
"""


from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage


from config import get_settings
from graph.graph_state import FinancialGraphState

def connect_llm(state: FinancialGraphState) -> dict:
    """Initialise AzureChatOpenAI and validate the connection."""

    settings = get_settings()

    try:
        llm = AzureChatOpenAI(
            azure_deployment=settings.azure_openai_deployment,
            api_version=settings.azure_openai_api_version,
            # temperature=settings.llm_temperature,
            top_p=settings.llm_top_p,
            seed=settings.llm_seed,
        )

        # Quick connectivity check with retry
        llm.with_retry(wait_exponential_jitter=True, stop_after_attempt=3).invoke([HumanMessage(content="ping")])

        return {"llm": llm, "errors": state.get("errors", [])}

    except Exception as e:
        return {
            "llm": None,
            "errors": state.get("errors", []) + [f"LLM connection error: {str(e)}"],
        }