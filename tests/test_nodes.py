from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from backend.src.graph.nodes import audit_content_node, index_video_node

TEMP_VIDEO_PATH = "temp_audit_video.mp4"

STATE = {
    "video_url": "https://youtu.be/fake",
    "video_id": "vid_test",
    "transcript": "Welcome to our brand safe video.",
    "ocr_text": ["Buy Now"],
}


def _run_auditor(llm_content, state=STATE):
    """Run audit_content_node with the retriever and LLM mocked out."""
    with patch("backend.src.graph.nodes.ComplianceRetriever") as mock_retriever_cls, patch(
        "backend.src.graph.nodes.ChatGroq"
    ) as mock_groq_cls:
        mock_retriever_cls.return_value.retrieve.return_value = [
            {"content": "Mocked compliance rule: Do not swear."}
        ]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content=llm_content)
        mock_groq_cls.return_value = mock_llm

        result = audit_content_node(state)
        return result, mock_llm


def test_audit_pass():
    result, mock_llm = _run_auditor(
        '{"compliance_results": [], "status": "PASS", "final_report": "All clear."}'
    )

    assert result["final_status"] == "PASS"
    assert result["final_report"] == "All clear."
    assert result["compliance_results"] == []
    mock_llm.invoke.assert_called_once()


def test_audit_parses_markdown_fenced_json():
    fenced = (
        "```json\n"
        '{"compliance_results": [{"category": "Claim Validation", "severity": "CRITICAL", '
        '"description": "Unverified claim."}], "status": "FAIL", "final_report": "Violation found."}\n'
        "```"
    )
    result, _ = _run_auditor(fenced)

    assert result["final_status"] == "FAIL"
    assert result["compliance_results"][0]["category"] == "Claim Validation"


def test_audit_returns_fail_and_error_on_invalid_json():
    result, _ = _run_auditor("this is not json")

    assert result["final_status"] == "FAIL"
    assert len(result["errors"]) == 1


def test_audit_skipped_without_transcript():
    with patch("backend.src.graph.nodes.ComplianceRetriever") as mock_retriever_cls, patch(
        "backend.src.graph.nodes.ChatGroq"
    ) as mock_groq_cls:
        result = audit_content_node({**STATE, "transcript": ""})

        mock_retriever_cls.assert_not_called()
        mock_groq_cls.assert_not_called()

    assert result["final_status"] == "FAIL"
    assert "No Transcript" in result["final_report"]


def test_indexer_rejects_non_youtube_url():
    from backend.src.graph.nodes import index_video_node

    with patch("backend.src.graph.nodes.VideoIndexerService"):
        result = index_video_node({"video_url": "https://example.com/video.mp4", "video_id": "vid_x"})

    assert result["final_status"] == "FAIL"
    assert "YouTube" in result["errors"][0]


def test_indexer_returns_transcript_and_ocr_and_removes_temp_file(tmp_path, monkeypatch):

    monkeypatch.chdir(tmp_path)

    def fake_download(url, output_path):
        with open(output_path, "wb") as f:
            f.write(b"fake video bytes")
        return output_path

    with patch("backend.src.graph.nodes.VideoIndexerService") as mock_service_cls:
        service = mock_service_cls.return_value
        service.download_youtube_video.side_effect = fake_download
        service.transcribe_locally.return_value = "spoken words"
        service.upload_video.return_value = "videos/vid_x.mp4"
        service.wait_for_processing.return_value = {"raw": "insights"}
        service.extract_data.return_value = {"ocr_text": ["SHEER"], "video_metadata": {"duration": 30.0}}

        result = index_video_node({"video_url": "https://youtu.be/abc", "video_id": "vid_x"})

    assert result["transcript"] == "spoken words"
    assert result["ocr_text"] == ["SHEER"]
    assert not (tmp_path / TEMP_VIDEO_PATH).exists()


def test_indexer_removes_temp_file_when_pipeline_fails(tmp_path, monkeypatch):

    monkeypatch.chdir(tmp_path)

    def fake_download(url, output_path):
        with open(output_path, "wb") as f:
            f.write(b"fake video bytes")
        return output_path

    with patch("backend.src.graph.nodes.VideoIndexerService") as mock_service_cls:
        service = mock_service_cls.return_value
        service.download_youtube_video.side_effect = fake_download
        service.transcribe_locally.side_effect = Exception("whisper exploded")

        result = index_video_node({"video_url": "https://youtu.be/abc", "video_id": "vid_x"})

    assert result["final_status"] == "FAIL"
    assert "whisper exploded" in result["errors"][0]
    assert not (tmp_path / TEMP_VIDEO_PATH).exists()