from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from backend.src.graph.workflow import app

LLM_RESPONSE = """
{
    "compliance_results": [
        {"category": "Claim Validation", "severity": "CRITICAL", "description": "Unverified SPF claim."}
    ],
    "status": "FAIL",
    "final_report": "One critical violation."
}
"""


def _fake_download(url, output_path):
    with open(output_path, "wb") as f:
        f.write(b"fake video bytes")
    return output_path


def test_full_graph_runs_indexer_then_auditor(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with patch("backend.src.graph.nodes.VideoIndexerService") as mock_service_cls, patch(
        "backend.src.graph.nodes.ComplianceRetriever"
    ) as mock_retriever_cls, patch("backend.src.graph.nodes.ChatGroq") as mock_groq_cls:
        service = mock_service_cls.return_value
        service.download_youtube_video.side_effect = _fake_download
        service.transcribe_locally.return_value = "Ultra Sheer gives you high SPF protection."
        service.upload_video.return_value = "videos/vid_test.mp4"
        service.wait_for_processing.return_value = {}
        service.extract_data.return_value = {
            "ocr_text": ["SHEER"],
            "video_metadata": {"duration": 30.0, "platform": "youtube"},
        }

        mock_retriever_cls.return_value.retrieve.return_value = [{"content": "Claims need substantiation."}]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content=LLM_RESPONSE)
        mock_groq_cls.return_value = mock_llm

        final_state = app.invoke(
            {
                "video_url": "https://youtu.be/abc",
                "video_id": "vid_test",
                "compliance_results": [],
                "errors": [],
            }
        )

    assert final_state["transcript"] == "Ultra Sheer gives you high SPF protection."
    assert final_state["ocr_text"] == ["SHEER"]
    assert final_state["final_status"] == "FAIL"
    assert final_state["compliance_results"][0]["category"] == "Claim Validation"
    assert final_state["errors"] == []


def test_graph_skips_audit_when_indexing_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with patch("backend.src.graph.nodes.VideoIndexerService") as mock_service_cls, patch(
        "backend.src.graph.nodes.ChatGroq"
    ) as mock_groq_cls:
        mock_service_cls.return_value.download_youtube_video.side_effect = Exception("download failed")

        final_state = app.invoke(
            {
                "video_url": "https://youtu.be/abc",
                "video_id": "vid_test",
                "compliance_results": [],
                "errors": [],
            }
        )

        mock_groq_cls.assert_not_called()

    assert final_state["final_status"] == "FAIL"
    assert "download failed" in final_state["errors"][0]
    assert "No Transcript" in final_state["final_report"]
