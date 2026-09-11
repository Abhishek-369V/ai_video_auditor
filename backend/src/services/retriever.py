import os
import logging
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

logger = logging.getLogger("retriever")

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

class ComplianceRetriever:
    def __init__(self, index_path=None):
        if index_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            index_path = os.path.join(current_dir, "../../data/faiss_index")

        logger.info(f"Loading FAISS index from: {index_path}")
        embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)

        self.vector_store = FAISS.load_local(
            index_path,
            embeddings,
            allow_dangerous_deserialization=True  # safe: it's our own locally-built index
        )
        logger.info("✓ FAISS index loaded")

    def retrieve(self, query, k=4):
        """Returns top-k relevant chunks for a query, with source metadata."""
        results = self.vector_store.similarity_search(query, k=k)
        return [
            {"content": doc.page_content, "source": doc.metadata.get("source", "unknown")}
            for doc in results
        ]