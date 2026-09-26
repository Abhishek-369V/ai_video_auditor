from unittest.mock import patch, MagicMock
from backend.src.services.retriever import ComplianceRetriever

# Intercept whatever vector store or embedding your retriever uses internally
# Adjust the patch path if your FAISS import is different (e.g., langchain_community.vectorstores.FAISS)
@patch("backend.src.services.retriever.FAISS.load_local")
def test_retriever_returns_correct_chunk_count(mock_faiss_load):
    # 1. Setup a Mock FAISS Database Object
    mock_db = MagicMock()
    mock_faiss_load.return_value = mock_db
    
    # 2. Setup Mock Documents returned by the similarity search
    mock_doc = MagicMock()
    mock_doc.page_content = "Mocked rule: No false claims."
    
    # Simulate FAISS returning 4 document chunks
    mock_db.similarity_search.return_value = [mock_doc, mock_doc, mock_doc, mock_doc]
    
    # 3. Initialize your Retriever (Zero cost, zero disk read)
    # We patch the embeddings inside so it doesn't try to hit an embedding API
    with patch("backend.src.services.retriever.HuggingFaceEmbeddings"): 
        retriever = ComplianceRetriever()
        results = retriever.retrieve("test video transcript", k=4)
    
    # 4. Assert your code handled the FAISS output correctly
    assert len(results) == 4
    assert results[0]["content"] == "Mocked rule: No false claims."
    
    # Verify your code actually called the search function
    mock_db.similarity_search.assert_called_once()