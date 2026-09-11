import json
import os
import logging
import re
from typing import Dict, Any, List

from langchain_aws import ChatBedrock
from langchain_core.messages import SystemMessage, HumanMessage

# State & Services
from backend.src.graph.state import VideoAuditState
from backend.src.services.video_indexer import VideoIndexerService
from backend.src.services.retriever import ComplianceRetriever

# Configure Logger
logger = logging.getLogger("brand-guardian")
logging.basicConfig(level=logging.INFO)


# --- NODE 1: THE INDEXER ---
def index_video_node(state: VideoAuditState) -> Dict[str, Any]:
    """
    Downloads YouTube video, uploads to AWS S3, and extracts OCR + Audio transcription.
    """
    video_url = state.get("video_url")
    video_id_input = state.get("video_id", "vid_demo")

    logger.info(f"--- [Node: Indexer] Processing: {video_url} ---")

    local_filename = "temp_audit_video.mp4"

    try:
        vi_service = VideoIndexerService()

        # 1. DOWNLOAD
        if "youtube.com" in video_url or "youtu.be" in video_url:
            local_path = vi_service.download_youtube_video(video_url, output_path=local_filename)
        else:
            raise Exception("Please provide a valid YouTube URL for this test.")

        # 2. UPLOAD
        s3_video_key = vi_service.upload_video(local_path, video_name=video_id_input)
        logger.info(f"Upload Success. S3 video key: {s3_video_key}")

        # 3. CLEANUP LOCAL FILE
        if os.path.exists(local_path):
            os.remove(local_path)

        # 4. WAIT & PROCESS (Rekognition + Transcribe)
        raw_insights = vi_service.wait_for_processing(s3_video_key)

        # 5. EXTRACT
        clean_data = vi_service.extract_data(raw_insights)

        logger.info("--- [Node: Indexer] Extraction Complete ---")
        return clean_data

    except Exception as e:
        logger.error(f"Video Indexer Failed: {e}")
        return {
            "errors": [str(e)],
            "final_status": "FAIL",
            "transcript": "",
            "ocr_text": []
        }


# --- NODE 2: THE COMPLIANCE AUDITOR ---
def audit_content_node(state: VideoAuditState) -> Dict[str, Any]:
    """
    Performs Retrieval-Augmented Generation (RAG) using local FAISS and Amazon Bedrock.
    """
    logger.info("--- [Node: Auditor] Querying Knowledge Base & LLM ---")

    transcript = state.get("transcript", "")

    if not transcript:
        logger.warning("No transcript available. Skipping Audit.")
        return {
            "final_status": "FAIL",
            "final_report": "Audit skipped because video processing failed (No Transcript)."
        }

    # 1. Local FAISS Retrieval
    retriever = ComplianceRetriever()
    ocr_text = state.get("ocr_text", [])
    query_text = f"{transcript} {' '.join(ocr_text)}"
    
    # Retrieve top relevant rule chunks
    relevant_chunks = retriever.retrieve(query_text, k=4)
    retrieved_rules = "\n\n".join([chunk["content"] for chunk in relevant_chunks]) 

    # 2. Initialize Amazon Bedrock (Claude 3 Haiku for cost efficiency)
    region = os.getenv("AWS_DEFAULT_REGION", "ap-south-2")
    llm = ChatBedrock(
        model_id="anthropic.claude-3-haiku-20240307-v1:0",
        region_name=region,
        model_kwargs={"temperature": 0.0, "max_tokens": 2048}
    )

    # 3. Prompt Construction
    system_prompt = f"""
    You are a Senior Brand Compliance Auditor.

    OFFICIAL REGULATORY RULES:
    {retrieved_rules}

    INSTRUCTIONS:
    1. Analyze the Transcript and OCR text below.
    2. Identify ANY violations of the rules.
    3. Return strictly valid JSON in the following format:

    {{
        "compliance_results": [
            {{
                "category": "Claim Validation",
                "severity": "CRITICAL",
                "description": "Explanation of the violation..."
            }}
        ],
        "status": "FAIL",
        "final_report": "Summary of findings..."
    }}

    If no violations are found, set "status" to "PASS" and "compliance_results" to [].
    """

    user_message = f"""
    VIDEO METADATA: {state.get('video_metadata', {})}
    TRANSCRIPT: {transcript}
    ON-SCREEN TEXT (OCR): {ocr_text}
    """

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message)
        ])

        # 4. Clean Markdown formatting if present (```json ... ```)
        content = response.content
        if "```" in content:
            match = re.search(r"```(?:json)?(.*?)```", content, re.DOTALL)
            if match:
                content = match.group(1)

        audit_data = json.loads(content.strip())

        return {
            "compliance_results": audit_data.get("compliance_results", []),
            "final_status": audit_data.get("status", "FAIL"),
            "final_report": audit_data.get("final_report", "No report generated.")
        }

    except Exception as e:
        logger.error(f"System Error in Auditor Node: {str(e)}")
        raw_llm = response.content if "response" in locals() else "None"
        logger.error(f"Raw LLM Response: {raw_llm}")
        return {
            "errors": [str(e)],
            "final_status": "FAIL"
        }