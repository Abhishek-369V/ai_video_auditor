"""LangGraph workflow: [START] -> indexer -> auditor -> [END].

Pipeline: YouTube -> Whisper (transcript) -> S3 + Rekognition (on-screen text)
          -> FAISS retrieval (policy rules) -> Groq LLM (compliance audit)
"""

from langgraph.graph import StateGraph, END

# Import the State Schema
from backend.src.graph.state import VideoAuditState

# Import the Functional Nodes
from backend.src.graph.nodes import index_video_node, audit_content_node

def create_graph():
    workflow = StateGraph(VideoAuditState)

    workflow.add_node("indexer", index_video_node)
    workflow.add_node("auditor", audit_content_node)

    workflow.set_entry_point("indexer")

    workflow.add_edge("indexer", "auditor")
    workflow.add_edge("auditor", END)

    app = workflow.compile()

    return app

app = create_graph()