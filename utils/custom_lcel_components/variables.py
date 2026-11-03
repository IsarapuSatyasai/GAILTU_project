# current embedding size of the models we use is +-8k tokens, rougly 3 chars per token so we use this to cap the chunks
_MAX_EMBED_LENGTH = 8000  # max length of embedding model in terms of number of tokens
_CHROMA_FOLDER = "/tmp/chroma_db"
COLLECTION_NAME_MAX_LENGTH = 63
PREFIX_COLLECTION_NAME = "user_"
EMBEDDING_API_VERSION = "2024-10-21"
EMBEDDING_COSTS = 0.000125
EMBEDDING_TIMEOUT = (
    60  # seconds; fail fast instead of hanging on a blocked APIM/network call
)
EMBEDDING_MAX_RETRIES = 2
API_VERSION = "2023-05-15"  # llm
SEED = 1234
TF_CPP_MIN_LOG_LEVEL = "3"  # postretrieval
DEFAULT_SENTENCE_TRANSFORMER_MAX_LENGTH = 512
AUGMENTATION_PROMPT = """Answer the question based only on the following context: \n{context}. \n\nQuestion: {question}"""
_MIN_QUERY_LENGTH = 3
