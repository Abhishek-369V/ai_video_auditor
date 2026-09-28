import operator
from typing import Annotated, List, Dict, Optional, Any, TypedDict

class ComplianceIssue(TypedDict):
    category: str             # e.g., "FTC_DISCLOSURE"
    description: str          # Specific detail of the violation
    severity: str             # "CRITICAL" | "WARNING"
    timestamp: Optional[str]  # Timestamp of occurrence (if applicable)


class VideoAuditState(TypedDict):
    """Shared state passed between the indexer and auditor nodes."""

    # Input Parameters
    video_url: str
    video_id: str

    # Populated by the indexer node
    local_file_path: Optional[str]  
    video_metadata: Dict[str, Any]  # e.g., {"duration": 15, "resolution": "1080p"}
    transcript: Optional[str]       # Full extracted speech-to-text
    ocr_text: List[str]             # List of recognized on-screen text

    # Populated by the auditor node (append-only via operator.add)
    compliance_results: Annotated[List[ComplianceIssue], operator.add]
    # Final Deliverables
    final_status: str               # "PASS" | "FAIL"
    final_report: str               # Markdown summary for the frontend
    
    # Non-fatal errors from any node (append-only)
    errors: Annotated[List[str], operator.add]