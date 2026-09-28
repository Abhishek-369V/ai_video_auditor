"""FastAPI server exposing the audit pipeline over HTTP.

Run locally:
    uvicorn backend.src.api.server:app --reload

Docs:   http://localhost:8000/docs
Health: GET  /health
Audit:  POST /audit  {"video_url": "https://youtu.be/..."}
"""

import uuid   
import logging 
from typing import List 

from fastapi import FastAPI, HTTPException  
from pydantic import BaseModel  


# STEP 1: LOAD ENVIRONMENT VARIABLES
from dotenv import load_dotenv
load_dotenv(override=True)  


# STEP 2: IMPORT WORKFLOW GRAPH
from backend.src.graph.workflow import app as compliance_graph


# STEP 3: CONFIGURE LOGGING
logging.basicConfig(level=logging.INFO)  
logger = logging.getLogger("api-server")  


# STEP 4: CREATE FASTAPI APPLICATION 
app = FastAPI(
    title="Brand Guardian AI API",
    description="AI Video Auditor for evaluating video advertisements against brand compliance rules.",
    version="1.0.0"
)


# STEP 5: DEFINE DATA MODELS (PYDANTIC)

# --- REQUEST MODEL ---
class AuditRequest(BaseModel):
    video_url: str  

# --- NESTED MODEL ---
class ComplianceIssue(BaseModel):
    category: str       # Example: "Misleading Claims"
    severity: str       # Example: "CRITICAL"
    description: str    # Example: "Absolute guarantee detected at 00:32"

# --- RESPONSE MODEL ---
class AuditResponse(BaseModel):
    session_id: str     # Unique audit session ID
    video_id: str       # Shortened video identifier
    status: str         # PASS or FAIL
    final_report: str   # AI-generated summary
    compliance_results: List[ComplianceIssue] # List of violations (can be empty)


# STEP 6: DEFINE MAIN ENDPOINT
@app.post("/audit", response_model=AuditResponse)

def audit_video(request: AuditRequest):
    
    # GENERATE SESSION ID 
    session_id = str(uuid.uuid4())  
    video_id_short = f"vid_{session_id[:8]}"  # Takes first 8 characters: "vid_ce6c43bb", Easier to reference in logs/UI than full UUID
    
    # LOG INCOMING REQUEST 
    logger.info(f"Received Audit Request: {request.video_url} (Session: {session_id})")

    # PREPARE GRAPH INPUT
    initial_inputs = {
        "video_url": request.video_url,  # From the API request
        "video_id": video_id_short,      # Generated ID
        "compliance_results": [],        # Will be populated by Auditor
        "errors": []                     # Tracks any processing errors
    }

    try:
        # INVOKE LANGGRAPH WORKFLOW
        final_state = compliance_graph.invoke(initial_inputs) 
        
        # MAP GRAPH OUTPUT TO API RESPONSE
        return AuditResponse(
            session_id=session_id,
            video_id=final_state.get("video_id"),  # .get() safely retrieves value (None if missing)
            status=final_state.get("final_status", "UNKNOWN"), # Defaults to "UNKNOWN" if key doesn't exist
            final_report=final_state.get("final_report", "No report generated."),
            compliance_results=final_state.get("compliance_results", []) # Returns empty list [] if no violations
        )
    
    except Exception as e:
        logger.error(f"Audit Failed: {str(e)}")  
        
        raise HTTPException(
            status_code=500,
            detail=f"Workflow Execution Failed: {str(e)}"
        )


# STEP 7: HEALTH CHECK ENDPOINT
@app.get("/health")

def health_check():
    return {"status": "healthy", "service": "Brand Guardian AI"}