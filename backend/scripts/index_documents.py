"""Build the FAISS index from the policy PDFs in backend/data."""

import os
import glob
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("indexer")

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def index_docs():
    """
    Reads PDFs from backend/data, chunks them, embeds locally, 
    and saves a FAISS vector index to disk under backend/data/faiss_index.
    """

    current_dir = Path(__file__).resolve().parent.parent
    data_folder = current_dir / "data"
    index_save_path = data_folder / "faiss_index"


    logger.info("=" * 60)
    logger.info("Local Embedding + FAISS Indexing")
    logger.info(f"Embedding model: {EMBEDDING_MODEL_NAME}")
    logger.info(f"Data folder: {data_folder}")
    logger.info(f"Index will be saved to: {index_save_path}")
    logger.info("=" * 60)

    try:
        logger.info("Loading local embedding model (first run downloads it)...")
        embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)
        logger.info("[DONE] Embedding model ready")
    except Exception as e:
        logger.error(f"Failed to load embedding model: {e}")
        return

    pdf_files = glob.glob(os.path.join(data_folder, "*.pdf"))
    if not pdf_files:
        logger.warning(f"No PDFs found in {data_folder}. Please add files.")
        return

    logger.info(f"Found {len(pdf_files)} PDFs: {[os.path.basename(f) for f in pdf_files]}")

    all_splits = []
    for pdf_path in pdf_files:
        try:
            logger.info(f"Loading: {os.path.basename(pdf_path)}...")
            loader = PyPDFLoader(pdf_path)
            raw_docs = loader.load()

            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200
            )
            splits = text_splitter.split_documents(raw_docs)

            for split in splits:
                split.metadata["source"] = os.path.basename(pdf_path)

            all_splits.extend(splits)
            logger.info(f" -> Split into {len(splits)} chunks.")
        except Exception as e:
            logger.error(f"Failed to process {pdf_path}: {e}")

    if not all_splits:
        logger.warning("No documents were processed.")
        return

    logger.info(f"Embedding {len(all_splits)} chunks and building FAISS index...")
    try:
        vector_store = FAISS.from_documents(all_splits, embeddings)
        vector_store.save_local(index_save_path)
        logger.info("=" * 60)
        logger.info("[DONE] Indexing Complete! FAISS index saved locally.")
        logger.info(f"Total chunks indexed: {len(all_splits)}")
        logger.info(f"Index location: {index_save_path}")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"Failed to build/save FAISS index: {e}")


if __name__ == "__main__":
    index_docs()