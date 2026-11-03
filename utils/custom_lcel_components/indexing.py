"""This module provides functions for managing collections and documents in ChromaDB and for indexing text chunks using the Llama model."""

import json
import logging
import os
import random
import re
import string
from collections import defaultdict
from typing import Dict, List, Tuple

import chromadb
import numpy as np
import tiktoken
from chromadb.api.client import Client
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings
from llama_index.core import Settings as LlamaSettings
from llama_index.core import VectorStoreIndex
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes
from llama_index.core.schema import Document
from llama_index.core.storage.docstore import BaseDocumentStore, SimpleDocumentStore
from llama_index.core.storage.storage_context import StorageContext
from llama_index.vector_stores.chroma import ChromaVectorStore
from mlflow.tracing.provider import trace_disabled

from custom_lcel_components.llm import create_embedding_model
from custom_lcel_components.variables import (
    _CHROMA_FOLDER,
    COLLECTION_NAME_MAX_LENGTH,
    EMBEDDING_COSTS,
    PREFIX_COLLECTION_NAME,
)

logger = logging.getLogger(__name__)


def derive_collection_name_from_source(
    _dir: dict, unique_collection_name: bool = False, source_key="source"
) -> str:
    """Derives a collection name from the given directory source.

    Args:
        _dir (dict): A dictionary containing the source path under the key "source".
        unique_collection_name (bool): If True, a unique prefix is added to the collection name.

    Note for ChromaDB the collection name can contain only 63 tokens, therefore we only take the last items of the path and cap the length
    For example ...test/test1/test2/test.pdf becomes test2test.pdf

    Returns:
        str: The name of the collection that is created.

    """
    if isinstance(_dir[source_key], str):
        source = _dir[source_key]
    else:
        source = _dir[source_key][0]

    derived_collection_name = re.sub(
        r"[^a-zA-Z0-9]", "", "".join(source.split("/")[-2:])
    )

    if unique_collection_name:
        user_id = (
            PREFIX_COLLECTION_NAME
            + "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
            + "_"
        )
        derived_collection_name_cap = derived_collection_name[
            -(COLLECTION_NAME_MAX_LENGTH - len(user_id)) :
        ]
        collection_name = user_id + derived_collection_name_cap
    else:
        collection_name = derived_collection_name[-COLLECTION_NAME_MAX_LENGTH:]

    # This check is to make sure the name satisfies chroma's collection name requirements
    if not collection_name[0].isalnum():
        collection_name = "1" + collection_name[1:]
    if not collection_name[-1].isalnum():
        collection_name = collection_name[:-1] + "1"

    logger.warning(f"The following collection name is used: {collection_name}")

    return collection_name


@trace_disabled
def index_docs_with_hierarchy(
    _dir: dict,
    embedding_model_name: str = "text-embedding-3-large",
    chunk_sizes: List[int] = [2048, 512, 128],
    chunk_overlap: int = 10,
) -> str:
    """Index documents with a hierarchical structure using a specified embedding model.

    This function indexes documents from a given directory with a hierarchical structure.
    It first generates hierarchical nodes from the documents, then creates a vector store using the specified embedding model.
    If no documents are provided, it skips the indexing process.

    Args:
        _dir (dict): A dictionary containing the collection name and documents to be indexed.
        embedding_model_name (str, optional): The name of the embedding model to use. Defaults to "text-embedding-3-large".
        chunk_sizes (list, optional): A list of chunk sizes for hierarchical parsing. Defaults to [2048, 512, 128].
        chunk_overlap (int, optional): The overlap size between chunks. Defaults to 10.

    Returns:
        str: The name of the collection that was indexed.
    """
    collection_name = _dir["collection_name"]
    documents = _dir["documents"]
    if not documents:
        logger.warning("skip indexing because of existing vector store...")
        return collection_name

    nodes, leaf_nodes = _get_nodes_with_hierarchy(
        documents, chunk_sizes=chunk_sizes, chunk_overlap=chunk_overlap
    )

    logger.warning("Indexing with hierarchy...")
    _create_llamaindex_vector_store(
        collection_name, nodes, embedding_model_name, leaf_nodes=leaf_nodes
    )
    calculate_embedding_costs(documents, embedding_model_name)

    return collection_name


def calculate_embedding_costs(docs: List[dict], model_name: str):
    """Calculates the cost of embedding documents using a specified model.

    This function calculates the cost of embedding a list of documents based on the number of tokens
    and the specified embedding model. If the model is not supported, a warning is logged.

    Args:
        docs (List[dict]): A list of dictionaries, where each dictionary contains a "text" key.
        model_name (str): The name of the embedding model to use for cost calculation.

    Returns:
        None
    """
    if model_name != "text-embedding-3-large":
        logger.warning(
            "Cost calculation not implemented for this model: " + model_name + "..."
        )
    number_of_tokens = 0
    for doc in docs:
        tokenizer = tiktoken.get_encoding("cl100k_base")
        sample_encode = tokenizer.encode(doc["text"])
        number_of_tokens += len(sample_encode)
    costs = np.round((number_of_tokens / 1000) * EMBEDDING_COSTS, 3)
    logger.warning("Cost of embedding model" + model_name + " equals: " + str(costs))


@trace_disabled
def index_chunks_llama(
    _dir,
    embedding_model_name="text-embedding-3-large",
    sentence_window_retrieval=True,
    window_size=2,
) -> str:
    """Index text chunks using the Llama model with optional sentence window retrieval.

    This function indexes a collection of text chunks using the specified embedding model.
    It can optionally include a window of surrounding sentences for each chunk to enhance
    retrieval performance. The function handles the creation of nodes, logging, and the
    setup of the vector store.

    Args:
        _dir (dict): Dictionary containing the collection name and text chunks (dict object with text and metadata keys).
        embedding_model_name (str): Name of the embedding model to use. Default is "text-embedding-3-large".
        sentence_window_retrieval (bool): Whether to include sentence window retrieval. Default is True.
        window_size (int): Number of surrounding sentences to include in the window. Default is 2.

    Returns:
        str: The name of the collection being indexed.
    """
    collection_name = _dir["collection_name"]
    chunks = _dir["chunks"]
    if not chunks:
        logger.warning("skip indexing because of existing vector store...")
        return collection_name
    if sentence_window_retrieval:
        nodes = _get_nodes_with_sentence_window(chunks, window_size=window_size)
        logger.warning("indexing with sentence window...")
    else:
        nodes = _create_llama_nodes(chunks)
        logger.warning("indexing...")

    _create_llamaindex_vector_store(
        collection_name,
        nodes,
        embedding_model_name,
    )

    calculate_embedding_costs(chunks, embedding_model_name)

    return collection_name


def reset_chroma_db(collection_name: str) -> None:
    """Resets the specified Chroma database collection.

    This function resets a collection in the Chroma database by deleting the collection and its associated document store file.
    It logs warnings about the reset process and the status of the document store file.

    Args:
        collection_name (str): The name of the collection to reset.
    """
    logger.warning("RESETTING THE COLLECTION: " + collection_name)
    settings = Settings(allow_reset=True)
    chroma_client = chromadb.PersistentClient(path=_CHROMA_FOLDER, settings=settings)
    chroma_client.delete_collection(collection_name)
    doc_store_file = os.path.join(_CHROMA_FOLDER, collection_name + ".json")
    if os.path.isfile(doc_store_file):
        logger.warning("the docstore is deleted (" + doc_store_file + ")...")
        os.remove(doc_store_file)
    else:
        logger.warning("the doc store is not deleted(" + doc_store_file + ")...")


def _create_chroma_collection(collection_name: str) -> Collection | Client:
    """Creates a ChromaDB collection.

    This function attempts to retrieve the specified collection from ChromaDB. If the collection
    exists, it deletes the collection before creating a new one. If the collection does not exist,
    it creates a new collection.

    Parameters:
    collection_name (str): The name of the collection to create or reset.

    Returns:
    tuple: A tuple containing the created collection and the ChromaDB client.
    """
    settings = Settings(allow_reset=True)
    chroma_client = chromadb.PersistentClient(path=_CHROMA_FOLDER, settings=settings)
    logger.warning("the following collection is used: " + collection_name)
    try:
        chroma_collection = chroma_client.get_collection(collection_name)
        logger.warning(
            "existing collection is found deleting the collection before creation..."
        )
        chroma_client.delete_collection(collection_name)
    except Exception:
        # set hnsw search to make sure consistency across search results, the number is equal to the maximum size of the vector db in terms of number of docs
        chroma_collection = chroma_client.create_collection(
            collection_name, metadata={"hnsw:search_ef": 1000000000}
        )

    return chroma_collection, chroma_client


def _create_doc_store(nodes: List[Document], collection_name: str) -> BaseDocumentStore:
    """Create and persist a document store with the given nodes.

    This function creates a document store and inserts the provided nodes. The document
    store is then persisted to a JSON file named after the collection.

    Args:
        nodes (List[Document]): List of document nodes to be added to the store.
        collection_name (str): Name of the collection for the document store.

    Returns:
        BaseDocumentStore: The created and persisted document store.
    """
    # if nodes are passed they will be inserted, otherwise the doc store will be loaded from filesystem
    logger.warning("inserting the documents in the document store...")
    # construct a store for the documents
    docstore = SimpleDocumentStore()

    # note that the document store contains all the nodes, including the one higher in the tree

    docstore.add_documents(nodes)

    doc_store_file = _CHROMA_FOLDER + "/" + collection_name + ".json"

    if os.path.isfile(doc_store_file):
        logger.warning(
            "existing docstore found with the same name, deleting before creating..."
        )
        os.remove(doc_store_file)
    docstore.persist(doc_store_file)

    return docstore


def _create_llamaindex_vector_store(
    collection_name: str,
    nodes: list[Document],
    embedding_model_name: str,
    leaf_nodes: list[Document] = None,
) -> Tuple[StorageContext, VectorStoreIndex, Client]:
    """Creates and returns a LlamaIndex vector store along with its storage context and Chroma client.

    This function sets up the embedding model for LlamaIndex, creates a Chroma collection, constructs
    a vector store, and initializes a document store. It then inserts the provided nodes or tree nodes
    into the document store and creates a VectorStoreIndex with the embeddings.

    Args:
        collection_name (str): The name of the collection to be used for the document store and vector store.
        nodes (list[Document]): A list of nodes to be inserted into the document store.
        embedding_model_name (str): The name of the embedding model to be used.
        leaf_nodes (list[Document], optional): A list of tree nodes to be inserted into the document store. Defaults to None.

    Returns:
        tuple: A tuple containing the storage context, the base index, and the Chroma client.
    """

    logger.warning("creating the embedding model...")
    # Set service context for llamaindex
    # timeout/max_retries so a blocked APIM/network call fails fast instead of hanging indefinitely
    embed_model = create_embedding_model(embedding_model_name)
    LlamaSettings.embed_model = embed_model

    logger.warning("creating the chroma collection...")

    chroma_collection, chroma_client = _create_chroma_collection(collection_name)

    # construct vector store
    logger.warning("creating the vector store...")
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

    logger.warning("creating the document store...")
    docstore = _create_doc_store(
        nodes=nodes,
        collection_name=collection_name,
    )

    logger.warning("creating the storage context...")
    storage_context = StorageContext.from_defaults(
        vector_store=vector_store, docstore=docstore
    )

    logger.warning("inserting the embeddings in the vector store...")
    if leaf_nodes:
        base_index = VectorStoreIndex(
            leaf_nodes,
            storage_context=storage_context,  # , use_async=True
        )
    else:
        base_index = VectorStoreIndex(
            nodes,
            storage_context=storage_context,  # , use_async=True
        )
    return storage_context, base_index, chroma_client


# TODO note this part is not evaluated yet and the quality still needs to be tested
def _get_nodes_with_hierarchy(
    documents, chunk_sizes=[2048, 512, 128], chunk_overlap=10
):
    """Generate hierarchical nodes from a list of documents.

    This function creates hierarchical nodes from the provided documents using specified chunk sizes and overlap.
    It first converts the documents into a list of llama nodes, then parses these nodes into a hierarchical structure.
    Finally, it extracts and returns both the hierarchical nodes and the leaf nodes.

    Args:
        documents (list): A list of documents to be processed.
        chunk_sizes (list, optional): A list of chunk sizes for hierarchical parsing. Defaults to [2048, 512, 128].
        chunk_overlap (int, optional): The overlap size between chunks. Defaults to 10.

    Returns:
        tuple: A tuple containing two elements:
            - nodes (list): The hierarchical nodes generated from the documents.
            - leaf_nodes (list): The leaf nodes extracted from the hierarchical nodes.
    """
    llama_doc_list = _create_llama_nodes(documents)

    node_parser = HierarchicalNodeParser.from_defaults(
        chunk_sizes=chunk_sizes, chunk_overlap=chunk_overlap
    )
    nodes = node_parser.get_nodes_from_documents(llama_doc_list)
    leaf_nodes = get_leaf_nodes(nodes)
    return nodes, leaf_nodes


def _create_llama_nodes(documents: List[Dict]) -> List[Document]:
    """Converts a list of dictionaries into a list of Document objects.

    This function takes a list of dictionaries, each containing text and metadata,
    and converts them into a list of Document objects.

    Args:
        documents (List[Dict]): A list of dictionaries, where each dictionary contains "text" and "metadata" keys.

    Returns:
        List[Document]: A list of Document objects created from the input dictionaries.
    """
    llama_doc_list = []
    for document in documents:
        llama_doc = Document(
            text=document["text"], metadata=json.loads(document["metadata"])
        )
        llama_doc.excluded_embed_metadata_keys.extend(llama_doc.metadata.keys())
        llama_doc.excluded_llm_metadata_keys.extend(llama_doc.metadata.keys())
        llama_doc_list.append(llama_doc)
    return llama_doc_list


def _get_nodes_with_sentence_window(
    chunks: List[Dict],
    window_metadata_key="window",
    original_text_metadata_key="original",
    window_size=2,
) -> List[Document]:
    """
    Adds a sentence window to each document node for context, grouped by source.
    """
    # Group chunks by metadata['source']
    grouped_chunks = defaultdict(list)
    for chunk in chunks:
        md = chunk.get("metadata", {})
        if isinstance(md, str):
            try:
                md = json.loads(md)
            except Exception:
                md = {}
        source = md.get("source", "unknown")
        grouped_chunks[source].append(chunk)

    all_nodes = []

    # Process each group separately
    for source_chunks in grouped_chunks.values():
        nodes = _create_llama_nodes(source_chunks)

        # add window to each node within the same source group
        for i, node in enumerate(nodes):
            window_nodes = nodes[
                max(0, i - window_size) : min(i + window_size + 1, len(nodes))
            ]

            # ensure metadata exists
            if getattr(node, "metadata", None) is None:
                node.metadata = {}

            node.metadata[original_text_metadata_key] = node.text
            node.metadata[window_metadata_key] = " ".join(n.text for n in window_nodes)

            # exclude window metadata from embed and llm
            if not hasattr(node, "excluded_embed_metadata_keys"):
                node.excluded_embed_metadata_keys = []
            if not hasattr(node, "excluded_llm_metadata_keys"):
                node.excluded_llm_metadata_keys = []

            node.excluded_embed_metadata_keys.extend(
                [window_metadata_key, original_text_metadata_key]
            )
            node.excluded_llm_metadata_keys.extend(
                [window_metadata_key, original_text_metadata_key]
            )

            all_nodes.append(node)

    return all_nodes
