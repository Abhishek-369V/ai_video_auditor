from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage

from backend.src.graph.nodes import audit_content_node


@patch("backend.src.graph.nodes.ChatGroq")
@patch("backend.src.graph.nodes.ComplianceRetriever")
def test_audit_content_node_success(mock_retriever_cls, mock_chat_groq_cls):
    # 1. Mock the Retriever Instance & Method
    mock_retriever_instance = MagicMock()
    mock_retriever_instance.retrieve.return_value = [
        {"content": "Mocked compliance rule: Do not swear."}
    ]
    mock_retriever_cls.return_value = mock_retriever_instance

    # 2. Mock the Groq LLM Instance & Method
    mock_llm_instance = MagicMock()
    fake_llm_json = """
    {
        "compliance_results": [],
        "status": "PASS",
        "final_report": "No violations detected in the mocked test."
    }
    """
    mock_llm_instance.invoke.return_value = AIMessage(content=fake_llm_json)
    mock_chat_groq_cls.return_value = mock_llm_instance

    # 3. Define a Mock LangGraph state
    test_state = {
        "video_url": "https://youtu.be/fake",
        "video_id": "vid_test",
        "transcript": "Welcome to our brand safe video.",
        "ocr_text": ["Buy Now"]
    }

    # 4. Execute the node
    result = audit_content_node(test_state)

    # 5. Assertions
    assert result["final_status"] == "PASS"
    assert result["final_report"] == "No violations detected in the mocked test."
    assert result["compliance_results"] == []

    # Verify our system actually instantiated the classes and invoked them
    mock_chat_groq_cls.assert_called_once()
    mock_llm_instance.invoke.assert_called_once()