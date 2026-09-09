import operator
from typing import Annotated, List, Dict, Optional, Any, TypedDict

# 1. Define the Schema for a Single Compliance Result
# This ensures structural consistency for every issue detected by the AI.
class ComplianceIssue(TypedDict):
    category: str           # e.g., "FTC_DISCLOSURE"
    description: str        # Specific detail of the violation
    severity: str           # "CRITICAL" | "WARNING"
    timestamp: Optional[str]# Timestamp of occurrence (if applicable)

# 2. Define the Global Graph State
class VideoAuditState(TypedDict):
    """
    Defines the data schema for the LangGraph execution context.
    """
    # --- Input Parameters ---
    video_url: str
    video_id: str

    # --- Ingestion & Extraction Data ---
    # Optional because they are populated asynchronously by the Indexer Node.
    local_file_path: Optional[str]  
    video_metadata: Dict[str, Any]  # e.g., {"duration": 15, "resolution": "1080p"}
    transcript: Optional[str]       # Full extracted speech-to-text
    ocr_text: List[str]             # List of recognized on-screen text

    # --- Analysis Output ---
    # annotated with operator.add to allow append-only updates from multiple nodes.
    compliance_results: Annotated[List[ComplianceIssue], operator.add]
    
    # --- Final Deliverables ---
    final_status: str               # "PASS" | "FAIL"
    final_report: str               # Markdown summary for the frontend
    
    # --- System Observability ---
    # Appends system-level errors (e.g., API timeouts) without halting execution logic.
    errors: Annotated[List[str], operator.add]