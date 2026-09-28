from unittest.mock import MagicMock, patch

import pytest

from backend.src.services.video_indexer import VideoIndexerService


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setenv("AWS_S3_BUCKET_NAME", "test-bucket")
    with patch("backend.src.services.video_indexer.boto3.client") as mock_client:
        mock_client.side_effect = lambda *args, **kwargs: MagicMock()
        yield VideoIndexerService()


def test_upload_strips_existing_extension(service):
    assert service.upload_video("local.mp4", "clip.mp4") == "videos/clip.mp4"
    assert service.upload_video("local.mp4", "clip") == "videos/clip.mp4"
    service.s3_client.upload_file.assert_called_with("local.mp4", "test-bucket", "videos/clip.mp4")


def test_wait_for_processing_collects_all_pages(service):
    service.rekognition_client.start_text_detection.return_value = {"JobId": "job-1"}
    service.rekognition_client.get_text_detection.side_effect = [
        {
            "JobStatus": "SUCCEEDED",
            "TextDetections": [{"TextDetection": {"DetectedText": "page one"}}],
            "VideoMetadata": {"DurationMillis": 30000},
            "NextToken": "token-2",
        },
        {"TextDetections": [{"TextDetection": {"DetectedText": "page two"}}]},
    ]

    raw = service.wait_for_processing("videos/clip.mp4")

    assert len(raw["rekognition_text_detections"]) == 2
    assert raw["video_metadata_raw"] == {"DurationMillis": 30000}


def test_wait_for_processing_raises_on_failed_job(service):
    service.rekognition_client.start_text_detection.return_value = {"JobId": "job-1"}
    service.rekognition_client.get_text_detection.return_value = {"JobStatus": "FAILED"}

    with pytest.raises(Exception, match="failed"):
        service.wait_for_processing("videos/clip.mp4")


def test_extract_data_dedupes_ocr_and_converts_duration(service):
    raw = {
        "rekognition_text_detections": [
            {"TextDetection": {"DetectedText": "Neutrogena"}},
            {"TextDetection": {"DetectedText": "Neutrogena"}},
            {"TextDetection": {"DetectedText": "SHEER"}},
            {"TextDetection": {}},
        ],
        "video_metadata_raw": {"DurationMillis": 30030},
    }

    data = service.extract_data(raw)

    assert data["ocr_text"] == ["Neutrogena", "SHEER"]
    assert data["video_metadata"]["duration"] == 30.03
    assert "transcript" not in data


def test_missing_bucket_env_raises(monkeypatch):
    monkeypatch.delenv("AWS_S3_BUCKET_NAME", raising=False)
    with patch("backend.src.services.video_indexer.boto3.client"):
        with pytest.raises(Exception, match="AWS_S3_BUCKET_NAME"):
            VideoIndexerService()
