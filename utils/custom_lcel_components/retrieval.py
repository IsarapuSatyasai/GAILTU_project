"""This module provides classes and functions for hybrid search and document retrieval using ChromaDB and LlamaIndex."""

import json
import logging
from typing import Dict, List, Optional, Tuple

import chromadb
from chromadb.api.client import Client
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings
from llama_index.core import Settings as LlamaSettings
from llama_index.core import VectorStoreIndex
from llama_index.core.callbacks.base import CallbackManager
from llama_index.core.constants import DEFAULT_SIMILARITY_TOP_K
from llama_index.core.retrievers import BaseRetriever, QueryFusionRetriever
from llama_index.core.retrievers.auto_merging_retriever import AutoMergingRetriever
from llama_index.core.retrievers.fusion_retriever import FUSION_MODES
from llama_index.core.schema import Document, IndexNode, NodeWithScore, QueryBundle
from llama_index.core.storage.docstore import BaseDocumentStore, SimpleDocumentStore
from llama_index.core.storage.storage_context import StorageContext
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.vector_stores.chroma import ChromaVectorStore
from mlflow.tracing.provider import trace_disabled

from custom_lcel_components.llm import create_embedding_model
from custom_lcel_components.variables import (
    _CHROMA_FOLDER,
    _MIN_QUERY_LENGTH,
)

logger = logging.getLogger(__name__)


class HybridSearch(QueryFusionRetriever):
    """
    HybridSearch is a retriever that combines multiple retrieval methods to enhance search results.

    This class supports various fusion modes to aggregate results from different retrievers,
    providing a more comprehensive and accurate retrieval process. It can operate asynchronously
    for improved performance and supports different ranking functions based on the selected fusion mode.

    Attributes:
        mode (FUSION_MODES): The fusion mode to use for combining results.
        similarity_top_k (int): The number of top results to return based on similarity.
        use_async (bool): Whether to use asynchronous retrieval.
        retrievers (List[BaseRetriever]): A list of retrievers to combine.
        verbose (bool): Whether to enable verbose logging.
        callback_manager (Optional[CallbackManager]): Manager for handling callbacks.
        objects (Optional[List[IndexNode]]): List of index nodes.
        object_map (Optional[dict]): Mapping of objects.
        retriever_weights (Optional[List[float]]): Weights for each retriever.

    Methods:
        _retrieve(query_bundle) -> List[NodeWithScore]:
            Retrieves and fuses results from multiple retrievers based on the specified fusion mode.
    """

    def __init__(
        self,
        retrievers: List[BaseRetriever],
        mode: FUSION_MODES = FUSION_MODES.SIMPLE,
        similarity_top_k: int = DEFAULT_SIMILARITY_TOP_K,
        use_async: bool = True,
        verbose: bool = False,
        callback_manager: Optional[CallbackManager] = None,
        objects: Optional[List[IndexNode]] = None,
        object_map: Optional[dict] = None,
        retriever_weights: Optional[List[float]] = None,
    ):
        self.mode = mode
        self.similarity_top_k = similarity_top_k
        self.use_async = use_async

        super().__init__(
            retrievers=retrievers,
            mode=mode,
            similarity_top_k=similarity_top_k,
            use_async=use_async,
            verbose=verbose,
            callback_manager=callback_manager,
            objects=objects,
            object_map=object_map,
            retriever_weights=retriever_weights,
            num_queries=1,  # we disable query generation as it is implemented seperately
        )

    def _retrieve(self, query_bundle) -> List[NodeWithScore]:
        queries = query_bundle.query_str.split("\n")
        queries_bundles = [
            QueryBundle(query_str=query)
            for query in queries
            if len(query) > _MIN_QUERY_LENGTH
        ]
        logger.warning(
            "number of generated queries equals: " + str(len(queries_bundles) - 1)
        )

        if self.use_async:
            results = super()._run_nested_async_queries(queries_bundles)
        else:
            results = super()._run_sync_queries(queries_bundles)
        if self.mode == FUSION_MODES.RECIPROCAL_RANK:
            logger.warning("using reciprocal rank function for hybrid search...")
            return super()._reciprocal_rerank_fusion(results)[: self.similarity_top_k]
        elif self.mode == FUSION_MODES.RELATIVE_SCORE:
            logger.warning("using relative score rank function for hybrid search...")
            return super()._relative_score_fusion(results)[: self.similarity_top_k]
        elif self.mode == FUSION_MODES.DIST_BASED_SCORE:
            logger.warning("using distance based function for hybrid search...")
            return super()._relative_score_fusion(results, dist_based=True)[
                : self.similarity_top_k
            ]
        elif self.mode == FUSION_MODES.SIMPLE:
            logger.warning("using simple rank function for hybrid search...")
            return super()._simple_fusion(results)[: self.similarity_top_k]
        else:
            raise ValueError(f"Invalid fusion mode: {self.mode}")


def _load_chroma_collection(collection_name: str) -> Collection | Client:
    """
    Loads a Chroma collection and returns the collection along with the client.

    This function initializes a Chroma PersistentClient with specific settings, retrieves the
    specified collection, and logs the collection name being used.

    Args:
        collection_name (str): The name of the Chroma collection to load.

    Returns:
        Collection: The loaded Chroma collection.
        Client: The Chroma client used to load the collection.
    """

    settings = Settings(allow_reset=True)
    chroma_client = chromadb.PersistentClient(path=_CHROMA_FOLDER, settings=settings)
    # logger.warning("the following collection is used: " + collection_name)

    chroma_collection = chroma_client.get_collection(collection_name)
    return chroma_collection, chroma_client


def _load_doc_store(collection_name: str) -> BaseDocumentStore:
    """
    Loads an existing document store from a specified collection.

    This function retrieves a document store by loading it from a persistent path based on the
    provided collection name. It logs a warning message indicating the loading process.

    Args:
        collection_name (str): The name of the collection to load the document store from.

    Returns:
        BaseDocumentStore: The loaded document store.
    """

    # logger.warning("loading the existing document storage...")
    docstore = SimpleDocumentStore.from_persist_path(
        _CHROMA_FOLDER + "/" + collection_name + ".json"
    )
    return docstore


def _create_llamaindex_relevance_retriever(
    base_index: VectorStoreIndex, similarity_top_k: int, hybrid_search_args: dict
) -> BaseRetriever:
    """
    Creates a relevance retriever for the LlamaIndex.

    This function constructs a retriever to obtain relevant documents based on the provided base index.
    It supports both vector-based retrieval and hybrid search retrieval using BM25 and vector retrievers.

    Parameters:
    - base_index: The base index used to create the retriever.
    - similarity_top_k: The number of top similar documents to retrieve.
    - hybrid_search_args: Arguments for configuring the hybrid search retriever. If None, only vector-based retrieval is used.

    Returns:
    - retriever: A configured retriever instance for retrieving relevant documents.

    If hybrid_search_args are provided, a hybrid search retriever is created using both vector and BM25 retrievers.
    The hybrid search retriever supports various modes for calculating the final relevance score.
    """

    vector_retriever = base_index.as_retriever(similarity_top_k=similarity_top_k)

    if hybrid_search_args:
        # TODO note this part is not evaluated yet and the quality still needs to be tested
        logger.warning("using the hybrid search retriever...")
        bm25_retriever = BM25Retriever.from_defaults(
            docstore=base_index.docstore,
            similarity_top_k=similarity_top_k,
        )

        retriever = HybridSearch(
            [vector_retriever, bm25_retriever],
            similarity_top_k=similarity_top_k,
            mode=hybrid_search_args["mode"],
            retriever_weights=hybrid_search_args["retriever_weights"],
            use_async=False,
        )
    else:
        retriever = vector_retriever

    return retriever


# @trace_disabled
def _load_llamaindex_vector_store(
    collection_name: str, embedding_model_name: str
) -> Tuple[StorageContext, VectorStoreIndex, Client]:
    """
    Loads a vector store for LlamaIndex using specified collection and embedding model.

    This function initializes an embedding model with Azure OpenAI settings, loads the Chroma
    collection and document store, and creates a storage context and base index for the vector store.

    Args:
        collection_name (str): The name of the collection to load.
        embedding_model_name (str): The name of the embedding model to use.

    Returns:
        Tuple[StorageContext, VectorStoreIndex, Client]: A tuple containing the storage context,
        base index, and Chroma client.
    """

    embed_model = create_embedding_model(embedding_model_name)
    LlamaSettings.embed_model = embed_model

    chroma_collection, chroma_client = _load_chroma_collection(collection_name)

    vector_store = ChromaVectorStore(
        chroma_collection=chroma_collection,
    )

    docstore = _load_doc_store(
        collection_name=collection_name,
    )

    storage_context = StorageContext.from_defaults(
        vector_store=vector_store, docstore=docstore
    )

    base_index = VectorStoreIndex([], storage_context=storage_context)

    return storage_context, base_index, chroma_client


def format_nodes(nodes: List[Document]) -> List[Dict]:
    """
    Formats a list of Document nodes into a list of dictionaries.

    This function processes each node to extract its text, similarity score, and metadata,
    and then compiles these into a list of dictionaries for easier handling and display.

    Args:
        nodes (List[Document]): A list of Document nodes to format.

    Returns:
        List[Dict]: A list of dictionaries containing the formatted node data.
    """

    cleaned_chunks = []

    for node in nodes:
        cleaned_chunk = {}
        cleaned_chunk["text"] = node.node.text
        cleaned_chunk["similarity_score"] = node.score
        cleaned_chunk["metadata"] = json.dumps(node.node.metadata)
        cleaned_chunks.append(cleaned_chunk)

    return cleaned_chunks


@trace_disabled
def retrieve_from_llama_store(
    _dir,
    embedding_model_name="text-embedding-3-large",
    similarity_top_k=20,
    hybrid_search_args=None,
    hierarch_retrieval=False,
) -> List[dict]:
    """
    Retrieves relevant nodes from the LlamaIndex vector store based on a given question.

    This function initializes the vector store and relevance retriever, optionally wraps the retriever
    for hierarchical retrieval, retrieves relevant nodes, formats them, and logs the number of relevant nodes.

    Args:
        _dir (dict): A dictionary containing the question and collection name.
        embedding_model_name (str): The name of the embedding model to use. Defaults to "text-embedding-3-large".
        similarity_top_k (int): The number of top similar nodes to retrieve. Defaults to 20.
        hybrid_search_args (dict, optional): Additional arguments for hybrid search. Defaults to None.
        hierarch_retrieval (bool, optional): Whether to use hierarchical retrieval. Defaults to False.

    Returns:
        list: A list of formatted chunks representing the relevant nodes.
    """
    question = _dir["question"]
    collection_name = _dir["collection_name"]

    storage_context, base_index, chroma_client = _load_llamaindex_vector_store(
        collection_name, embedding_model_name
    )

    # create the relevance retriever
    retriever = _create_llamaindex_relevance_retriever(
        base_index,
        similarity_top_k,
        hybrid_search_args,
    )

    # wrap a retriever around the relevance retrievar for hierarichal retrieval
    if hierarch_retrieval:
        logger.warning("using hierarchical retrieval...")
        retriever = AutoMergingRetriever(retriever, storage_context, verbose=True)

    relevant_nodes = retriever.retrieve(question)

    output_chunks = format_nodes(relevant_nodes)

    # logger.warning(
    #     "these are the number of relevant nodes: " + str(len(relevant_nodes))
    # )
    if len(relevant_nodes) == 0:
        logger.warning(
            "Number of relevant nodes is equal to 0, most likely the vectorDB has not been filled properly, restart compute or delete the vectorDB and try again..."
        )
    return output_chunks
