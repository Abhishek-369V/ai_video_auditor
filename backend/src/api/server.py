import uuid        # Generate unique session IDs
import logging     # Application logging
from fastapi import FastAPI, HTTPException  
# ↑ FastAPI = modern web framework (like Flask but faster)
# ↑ HTTPException = handles errors with proper HTTP status codes

from pydantic import BaseModel  
# ↑ Pydantic = data validation library (ensures API requests have correct format)

from typing import List, Optional  
# ↑ Type hints for better code clarity and auto-completion


# ========== STEP 1: LOAD ENVIRONMENT VARIABLES ==========
# CRITICAL: Must happen BEFORE importing modules that need env vars
from dotenv import load_dotenv
load_dotenv(override=True)  
# Reads .env file and sets environment variables
# override=True = .env values replace system environment variables
# Example .env contents:
#   AZURE_SEARCH_KEY=abc123
#   APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=...


# ========== STEP 2: INITIALIZE TELEMETRY ==========
from backend.src.api.telemetry import setup_telemetry
setup_telemetry()  
# ☝️ "Activates the sensors" - starts tracking all API activity
# Must happen AFTER load_dotenv() but BEFORE creating FastAPI app


# ========== STEP 3: IMPORT WORKFLOW GRAPH ==========
from backend.src.graph.workflow import app as compliance_graph
# Imports your LangGraph workflow (Indexer → Auditor)
# Renamed to 'compliance_graph' to avoid confusion with FastAPI's 'app'


# ========== STEP 4: CONFIGURE LOGGING ==========
logging.basicConfig(level=logging.INFO)  
# Sets default log level (INFO = important events, not debug spam)

logger = logging.getLogger("api-server")  
# Creates named logger for this module


# ========== STEP 5: CREATE FASTAPI APPLICATION ==========
app = FastAPI(
    # Metadata for auto-generated API documentation (Swagger UI)
    title="Brand Guardian AI API",
    description="API for auditing video content against brand compliance rules.",
    version="1.0.0"
)
# FastAPI automatically creates:
# - Interactive docs at http://localhost:8000/docs
# - OpenAPI schema at http://localhost:8000/openapi.json


# ========== STEP 6: DEFINE DATA MODELS (PYDANTIC) ==========

# --- REQUEST MODEL ---
class AuditRequest(BaseModel):
    """
    Defines the expected structure of incoming API requests.
    
    Pydantic validates that:
    - The request contains a 'video_url' field
    - The value is a string (not int, list, etc.)
    
    Example valid request:
    {
        "video_url": "https://youtu.be/abc123"
    }
    
    Example invalid request (raises 422 error):
    {
        "video_url": 12345  ← Not a string!
    }
    """
    video_url: str  # Required string field


# --- NESTED MODEL ---
class ComplianceIssue(BaseModel):
    """
    Defines the structure of a single compliance violation.
    
    Used inside AuditResponse to represent each violation found.
    """
    category: str      # Example: "Misleading Claims"
    severity: str      # Example: "CRITICAL"
    description: str   # Example: "Absolute guarantee detected at 00:32"


# --- RESPONSE MODEL ---
class AuditResponse(BaseModel):
    """
    Defines the structure of API responses.
    
    FastAPI uses this to:
    1. Validate the response before sending (catches bugs)
    2. Auto-generate API documentation (shows users what to expect)
    3. Provide type hints for frontend developers
    
    Example response:
    {
        "session_id": "ce6c43bb-c71a-4f16-a377-8b493502fee2",
        "video_id": "vid_ce6c43bb",
        "status": "FAIL",
        "final_report": "Video contains 2 critical violations...",
        "compliance_results": [
            {
                "category": "Misleading Claims",
                "severity": "CRITICAL",
                "description": "Absolute guarantee at 00:32"
            }
        ]
    }
    """
    session_id: str                           # Unique audit session ID
    video_id: str                             # Shortened video identifier
    status: str                               # PASS or FAIL
    final_report: str                         # AI-generated summary
    compliance_results: List[ComplianceIssue] # List of violations (can be empty)


# ========== STEP 7: DEFINE MAIN ENDPOINT ==========
@app.post("/audit", response_model=AuditResponse)
# ↑ @app.post = Decorator that registers this function as a POST endpoint
# ↑ "/audit" = URL path (http://localhost:8000/audit)
# ↑ response_model = Tells FastAPI to validate response matches AuditResponse

async def audit_video(request: AuditRequest):
    """
    Main API endpoint that triggers the compliance audit workflow.
    
    HTTP Method: POST
    URL: http://localhost:8000/audit
    
    Request Body:
    {
        "video_url": "https://youtu.be/abc123"
    }
    
    Response: AuditResponse object (defined above)
    
    Process:
    1. Generate unique session ID
    2. Prepare input for LangGraph workflow
    3. Invoke the graph (Indexer → Auditor)
    4. Return formatted results
    """
    
    # ========== GENERATE SESSION ID ==========
    session_id = str(uuid.uuid4())  
    # Creates unique ID like: "ce6c43bb-c71a-4f16-a377-8b493502fee2"
    
    video_id_short = f"vid_{session_id[:8]}"  
    # Takes first 8 characters: "vid_ce6c43bb"
    # Easier to reference in logs/UI than full UUID
    
    # ========== LOG INCOMING REQUEST ==========
    logger.info(f"Received Audit Request: {request.video_url} (Session: {session_id})")
    # Example output: "Received Audit Request: https://youtu.be/abc (Session: ce6c43bb...)"

    # ========== PREPARE GRAPH INPUT ==========
    initial_inputs = {
        "video_url": request.video_url,  # From the API request
        "video_id": video_id_short,      # Generated ID
        "compliance_results": [],        # Will be populated by Auditor
        "errors": []                     # Tracks any processing errors
    }

    try:
        # ========== INVOKE LANGGRAPH WORKFLOW ==========
        # This is the SAME logic from main.py - just wrapped in an API
        final_state = compliance_graph.invoke(initial_inputs)
        # ↑ Blocking call - waits for entire workflow to complete
        # ↑ Flow: START → Indexer → Auditor → END
        # ↑ Returns: Final state dictionary with all results
        
        # NOTE: In production, you'd use:
        # await compliance_graph.ainvoke(initial_inputs)
        # ↑ Async version - doesn't block the server while processing
        
        # ========== MAP GRAPH OUTPUT TO API RESPONSE ==========
        return AuditResponse(
            session_id=session_id,
            video_id=final_state.get("video_id"),  
            # .get() safely retrieves value (None if missing)
            
            status=final_state.get("final_status", "UNKNOWN"),  
            # Defaults to "UNKNOWN" if key doesn't exist
            
            final_report=final_state.get("final_report", "No report generated."),
            
            compliance_results=final_state.get("compliance_results", [])
            # Returns empty list [] if no violations
        )
        # FastAPI automatically converts this Pydantic object to JSON

    except Exception as e:
        # ========== ERROR HANDLING ==========
        logger.error(f"Audit Failed: {str(e)}")  
        # Log the error for debugging
        
        raise HTTPException(
            status_code=500,  # 500 = Internal Server Error
            detail=f"Workflow Execution Failed: {str(e)}"
            # Returns this error message to the client
        )
        # Example error response:
        # {
        #     "detail": "Workflow Execution Failed: YouTube download error"
        # }


# ========== STEP 8: HEALTH CHECK ENDPOINT ==========
@app.get("/health")
# ↑ GET request at http://localhost:8000/health
def health_check():
    """
    Simple endpoint to verify the API is running.
    
    Used by:
    - Load balancers (to check if server is alive)
    - Monitoring systems (uptime checks)
    - Developers (quick test that server started)
    
    Example usage:
    curl http://localhost:8000/health
    
    Response:
    {
        "status": "healthy",
        "service": "Brand Guardian AI"
    }
    """
    return {"status": "healthy", "service": "Brand Guardian AI"}
    # FastAPI automatically converts dict to JSON response


# ========== STEP 9: RUN INSTRUCTIONS (IN COMMENTS) ==========
'''
To execute: 
uv run uvicorn backend.src.api.server:app --reload

Command breakdown:
- uv run          = Run with UV package manager
- uvicorn         = ASGI server (like Gunicorn but async)
- backend.src.api.server:app = Python path to FastAPI app object
- --reload        = Auto-restart server when code changes (dev mode)

Server starts at: http://localhost:8000

Access points:
- API Docs:    http://localhost:8000/docs (interactive Swagger UI)
- Health:      http://localhost:8000/health
- Main API:    POST http://localhost:8000/audit
'''

'''
## How the API Works (Request Flow)
```
1. Client sends POST request:
   POST http://localhost:8000/audit
   Body: {"video_url": "https://youtu.be/abc123"}
   
2. FastAPI receives request:
   - Validates request matches AuditRequest model
   - Calls audit_video() function
   
3. audit_video() executes:
   - Generates session ID
   - Prepares initial_inputs dict
   - Calls compliance_graph.invoke()
   
4. LangGraph workflow runs:
   START → Indexer → Auditor → END
   
5. Function returns AuditResponse:
   - FastAPI validates response matches model
   - Converts Pydantic object to JSON
   - Sends HTTP response to client
   
6. Azure Monitor captures:
   - Request duration
   - HTTP status code
   - Any errors
   - Graph execution trace

'''