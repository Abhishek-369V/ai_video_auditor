from unittest.mock import MagicMock, patch

from backend.src.services.retriever import ComplianceRetriever


@patch("backend.src.services.retriever.HuggingFaceEmbeddings")
@patch("backend.src.services.retriever.FAISS.load_local")
def test_retrieve_returns_content_and_source(mock_load_local, _mock_embeddings):
    doc = MagicMock()
    doc.page_content = "Mocked rule: No false claims."
    doc.metadata = {"source": "ftc-guide.pdf"}

    mock_db = MagicMock()
    mock_db.similarity_search.return_value = [doc] * 4
    mock_load_local.return_value = mock_db

    results = ComplianceRetriever().retrieve("test transcript", k=4)

    assert len(results) == 4
    assert results[0] == {"content": "Mocked rule: No false claims.", "source": "ftc-guide.pdf"}
    mock_db.similarity_search.assert_called_once_with("test transcript", k=4)


@patch("backend.src.services.retriever.HuggingFaceEmbeddings")
@patch("backend.src.services.retriever.FAISS.load_local")
def test_retrieve_defaults_source_to_unknown(mock_load_local, _mock_embeddings):
    doc = MagicMock()
    doc.page_content = "Some rule"
    doc.metadata = {}

    mock_db = MagicMock()
    mock_db.similarity_search.return_value = [doc]
    mock_load_local.return_value = mock_db

    results = ComplianceRetriever().retrieve("query")

    assert results[0]["source"] == "unknown"
