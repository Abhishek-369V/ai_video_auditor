"""CLI entry point: runs the full audit pipeline on one YouTube video.

Pipeline: [YouTube -> Whisper (transcript) -> S3 + Rekognition (on-screen text)
           -> FAISS retrieval (policy rules) -> Groq LLM (compliance audit)]

Usage:
    python -m main [youtube_url]
"""

import uuid
import json
import logging
import sys

from dotenv import load_dotenv
load_dotenv(override=True)

from backend.src.graph.workflow import app

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'  
    # Format: timestamp - logger_name - severity - message
    # Example: "2024-01-15 10:30:45 - brand-guardian - INFO - Starting audit"
)
logger = logging.getLogger("brand-guardian.cli") 

DEFAULT_VIDEO_URL = "https://youtu.be/dT7S75eYhcQ"


def run_cli(video_url:str) -> None:
  
    # STEP 1: GENERATE SESSION ID
    session_id = str(uuid.uuid4())  
    logger.info(f"Starting Audit Session: {session_id}") 

    # STEP 2: DEFINE INITIAL STATE\
    initial_inputs = {
        "video_url": video_url,
        "video_id": f"vid_{session_id[:8]}",
        "compliance_results": [],
        "errors": []
    }

    # DISPLAY SECTION: INPUT SUMMARY
    print("\n--- 1.Input Payload: INITIALIZING WORKFLOW ---")
    print(f"I {json.dumps(initial_inputs, indent=2)}")

    # STEP 3: EXECUTE GRAPH 
    try:
        final_state = app.invoke(initial_inputs)

        print("\n--- 2. WORKFLOW EXECUTION COMPLETE ---")
        
        # STEP 4: OUTPUT RESULTS     
        print("\n=== COMPLIANCE AUDIT REPORT ===")
        
        print(f"Video ID:    {final_state.get('video_id')}")
        print(f"Status:      {final_state.get('final_status')}")   # Shows PASS or FAIL status
        print("\n[ VIOLATIONS DETECTED ]")  # violations section
        
        results = final_state.get('compliance_results', [])
        
        if results:
            for issue in results:
                print(f"- [{issue.get('severity')}] {issue.get('category')}: {issue.get('description')}")
        else:
            print("No violations found.")

        print("\n[ FINAL SUMMARY ]")
        print(final_state.get('final_report'))

    except Exception as e:
        logger.error(f"Workflow Execution Failed: {str(e)}")
        raise e


if __name__ == "__main__":
    run_cli(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VIDEO_URL)