from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.src.api.server import app

client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "Brand Guardian AI"}


def test_audit_success():
    final_state = {
        "video_id": "vid_test",
        "final_status": "FAIL",
        "final_report": "One violation found.",
        "compliance_results": [
            {"category": "Claim Validation", "severity": "CRITICAL", "description": "Unverified claim."}
        ],
    }
    with patch("backend.src.api.server.compliance_graph.invoke", return_value=final_state):
        response = client.post("/audit", json={"video_url": "https://youtu.be/abc"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "FAIL"
    assert body["compliance_results"][0]["category"] == "Claim Validation"
    assert body["session_id"]


def test_audit_returns_500_when_workflow_raises():
    with patch("backend.src.api.server.compliance_graph.invoke", side_effect=Exception("boom")):
        response = client.post("/audit", json={"video_url": "https://youtu.be/abc"})

    assert response.status_code == 500
    assert "boom" in response.json()["detail"]


def test_audit_rejects_missing_video_url():
    response = client.post("/audit", json={})

    assert response.status_code == 422
