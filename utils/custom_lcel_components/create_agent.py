from typing import Awaitable, Callable, List, Union

from langchain.agents import create_agent
from langchain.agents.middleware.types import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

from custom_lcel_components.llm import create_llm


# -----------------------------------------------------------------
# Tool error handler middleware
# -----------------------------------------------------------------
class ToolErrorMiddleware(AgentMiddleware):
    """Convert tool exceptions into model-readable ToolMessages."""

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage],
    ) -> ToolMessage:
        try:
            return handler(request)
        except Exception as e:
            return ToolMessage(
                content=f"Tool error: Please check your input and try again. ({e})",
                tool_call_id=request.tool_call["id"],
            )

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage]],
    ) -> ToolMessage:
        try:
            return await handler(request)
        except Exception as e:
            return ToolMessage(
                content=f"Tool error: Please check your input and try again. ({e})",
                tool_call_id=request.tool_call["id"],
            )


def create_llm_agent(
    model_name: str = "gpt-5.4",
    tools: Union[BaseTool, List[BaseTool], None] = None,
    system_prompt: str = "",
) -> Runnable:
    """
    Create and configure an LLM agent with optional tool support and
    Azure OpenAI integration.

    This function initializes an AzureChatOpenAI model and optionally attaches
    one or more tools. Tools can be provided as a single tool, a list of tools,
    or omitted entirely. When tools are present, tool execution is wrapped
    with middleware that converts runtime exceptions into structured
    ToolMessage responses.

    The resulting agent can operate either as:
    - a pure LLM agent (no tools), or
    - a tool-enabled agent with safe error handling.

    Args:
        model_name (str, optional):
            Name of the Azure OpenAI deployment to use.
            Defaults to "gpt-5.4".

        tools (Union[BaseTool, List[BaseTool], None], optional):
            A single tool, a list of tools, or None.
            If provided, the agent can invoke these tools during execution.

        system_prompt (str):
            System-level prompt defining the agent's behavior and guidelines.

    Returns:
        Runnable:
            A fully configured agent integrating the specified model,
            optional tools, system prompt, and middleware,
            ready to be invoked.
    """
    # -----------------------------------------------------------------
    # Normalize tools → always a list
    # -----------------------------------------------------------------
    if tools is None:
        tools = []
    elif not isinstance(tools, list):
        tools = [tools]

    # -----------------------------------------------------------------
    # Initialize LLM
    # -----------------------------------------------------------------
    llm = create_llm(
        azure_deployment=model_name,
        top_p=1,
        temperature=0,
    )

    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        middleware=[ToolErrorMiddleware()],
    )

    return agent
