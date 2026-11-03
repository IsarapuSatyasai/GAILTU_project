import os
from typing import Callable, Optional

from azure.identity import ClientSecretCredential
from langchain_openai import AzureChatOpenAI
from llama_index.embeddings.azure_openai import AzureOpenAIEmbedding

from custom_lcel_components.variables import (
    API_VERSION,
    EMBEDDING_API_VERSION,
    EMBEDDING_MAX_RETRIES,
    EMBEDDING_TIMEOUT,
    SEED,
)

# Token scope used when authenticating to the APIM-fronted Azure OpenAI with a
# service principal instead of an API key.
AZURE_AD_TOKEN_SCOPE = os.environ.get(
    "AZURE_OPENAI_AD_SCOPE",
    "api://65f49c64-0cc5-4cc9-9c23-a70ab5210734/.default",
)


def _uses_api_key() -> bool:
    """Return ``True`` when API key authentication should be used."""
    return "AZURE_OPENAI_API_KEY" in os.environ


def _get_azure_ad_token_provider() -> Callable[[], str]:
    """Build a callable returning Azure AD tokens from a service principal.

    Reads the ``AZURE_TENANT_ID_JOB``, ``AZURE_CLIENT_ID_JOB`` and
    ``AZURE_CLIENT_SECRET_JOB`` env vars to construct a
    ``ClientSecretCredential`` and returns a function that yields access tokens
    for ``AZURE_AD_TOKEN_SCOPE``.
    """
    tenant_id = os.environ["AZURE_TENANT_ID_JOB"]
    client_id = os.environ["AZURE_CLIENT_ID_JOB"]
    client_secret = os.environ["AZURE_CLIENT_SECRET_JOB"]

    credential = ClientSecretCredential(tenant_id, client_id, client_secret)

    def get_token() -> str:
        return credential.get_token(AZURE_AD_TOKEN_SCOPE).token

    return get_token


def create_llm(
    azure_deployment: str,
    api_version: str = API_VERSION,
    top_p: float = 1,
    temperature: Optional[float] = None,
    seed: int = SEED,
    azure_endpoint: Optional[str] = None,
    **kwargs,
) -> AzureChatOpenAI:
    """Create an ``AzureChatOpenAI`` client using the available credentials.

    When ``AZURE_OPENAI_API_KEY`` is present in the environment, the client is
    built with API key authentication (the endpoint and key are picked up from
    the environment by the SDK). Otherwise a service principal is used: the
    ``AZURE_CLIENT_ID``, ``AZURE_TENANT_ID`` and ``AZURE_CLIENT_SECRET`` env
    vars are read to obtain an Azure AD token provider.

    Args:
        azure_deployment: Azure deployment name of the chat model.
        api_version: Azure OpenAI API version.
        top_p: Nucleus sampling parameter.
        temperature: Sampling temperature. When ``None`` the model default is
            used.
        seed: Seed for deterministic sampling.
        azure_endpoint: Azure OpenAI endpoint. Falls back to the
            ``AZURE_OPENAI_ENDPOINT`` env var. Note: it must NOT include the
            ``/openai`` suffix, the SDK appends it automatically.
        **kwargs: Additional keyword arguments forwarded to ``AzureChatOpenAI``.

    Returns:
        AzureChatOpenAI: A configured chat model client.
    """
    common_kwargs = {
        "azure_deployment": azure_deployment,
        "api_version": api_version,
        "top_p": top_p,
        "seed": seed,
        **kwargs,
    }
    if temperature is not None:
        common_kwargs["temperature"] = temperature

    if azure_endpoint is None:
        azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    if azure_endpoint is not None:
        common_kwargs["azure_endpoint"] = azure_endpoint

    if _uses_api_key():
        return AzureChatOpenAI(**common_kwargs)

    return AzureChatOpenAI(
        azure_ad_token_provider=_get_azure_ad_token_provider(),
        **common_kwargs,
    )


def create_embedding_model(
    embedding_model_name: str,
    api_version: str = EMBEDDING_API_VERSION,
    timeout: float = EMBEDDING_TIMEOUT,
    max_retries: int = EMBEDDING_MAX_RETRIES,
    azure_endpoint: Optional[str] = None,
    **kwargs,
) -> AzureOpenAIEmbedding:
    """Create an ``AzureOpenAIEmbedding`` client using the available credentials.

    Uses the same authentication strategy as :func:`create_llm`: when
    ``AZURE_OPENAI_API_KEY`` is present the client is built with API key
    authentication, otherwise a service principal is used to obtain an Azure AD
    token provider.

    Args:
        embedding_model_name: Azure deployment name of the embedding model.
        api_version: Azure OpenAI API version for embeddings.
        timeout: Request timeout in seconds so a blocked call fails fast.
        max_retries: Maximum number of retries for transient errors.
        azure_endpoint: Azure OpenAI endpoint. Falls back to the
            ``AZURE_OPENAI_ENDPOINT`` env var. Note: it must NOT include the
            ``/openai`` suffix, the SDK appends it automatically.
        **kwargs: Additional keyword arguments forwarded to
            ``AzureOpenAIEmbedding``.

    Returns:
        AzureOpenAIEmbedding: A configured embedding model client.
    """
    common_kwargs = {
        "model_name": embedding_model_name,
        "deployment_name": embedding_model_name,
        "azure_endpoint": os.environ["AZURE_OPENAI_ENDPOINT"],
        "api_version": api_version,
        "timeout": timeout,
        "max_retries": max_retries,
        **kwargs,
    }

    if _uses_api_key():
        return AzureOpenAIEmbedding(**common_kwargs)

    return AzureOpenAIEmbedding(
        use_azure_ad=True,
        azure_ad_token_provider=_get_azure_ad_token_provider(),
        **common_kwargs,
    )
