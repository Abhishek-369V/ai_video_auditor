# AI Video Auditor 🎥🔍

> ⚠️ **Status: In active development** — building in public, day by day. Final version with full architecture, demo video, and results coming soon (see progress log below).

An AI-powered compliance auditing pipeline that analyzes video content (ads, brand content) against a knowledge base of policy/compliance guidelines, using a LangGraph-orchestrated agentic workflow and Retrieval-Augmented Generation (RAG).

## Why this project
Manually reviewing video content against brand/compliance guidelines doesn't scale. This project automates that review using cloud-native video intelligence + LLM-based reasoning grounded in real policy documents (not hallucinated judgments).

## Core Architecture

```text
               ┌───────────────────────┐
               │    FastAPI Server     │
               └───────────┬───────────┘
                           │ (POST /audit)
                           ▼
               ┌───────────────────────┐
               │  LangGraph Workflow   │
               └───────────┬───────────┘
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
 ┌───────────────────────┐   ┌───────────────────────┐
 │  1. Video Indexer     │   │ 2. Compliance Auditor │
 ├───────────────────────┤   ├───────────────────────┤
 │ • AWS S3 Data Ingest  │   │ • RAG Knowledge Base  │
 │ • AWS Rekognition Video│  │ • Amazon Bedrock LLM  │
 └───────────────────────┘   └───────────────────────┘
```

- **API Layer**: FastAPI web server with robust Pydantic data schemas.
- **Orchestration**: LangGraph state machine tracking an append-only stateless execution context (`VideoAuditState`).
- **Video Processing**: AWS Rekognition Video + Secure Amazon S3 raw ingestion staging.
- **Knowledge Retrieval**: RAG ingestion indexing localized policy guidelines using Amazon OpenSearch Service.
- **LLM Reasoning**: Amazon Bedrock foundation models parsing audit checks with strict JSON constraints.
- **Account Security**: Built inside isolated IAM developer environment layers with a multi-tiered AWS Budgets cost protection safety net.

## Tech Stack
`Python 3.11` `LangGraph` `FastAPI` `AWS Rekognition` `Amazon S3` `Amazon Bedrock` `Amazon OpenSearch` `uv` `Docker`

## Revised Progress Log
- [x] **Day 1** — Project initiation, package compilation (`uv`), IAM security policy separation.
- [x] **Day 2** — Bulletproof financial protection layer (AWS Budgets multi-trigger setup) & LangGraph state definitions.
- [ ] **Day 3** — AWS S3 secure data ingestion and AWS Rekognition video insight extraction pipeline node.
- [ ] **Day 4** — Document indexing workflow and embedding logic with Amazon OpenSearch vector spaces.
- [ ] **Day 5** — Amazon Bedrock compliance audit engine and RAG orchestration routing graph execution.
- [ ] **Day 6** — FastAPI endpoint integration, multi-stage Docker wrapping, and cloud testing deployment validation.

## Containerized Local Setup

This project uses `uv` for ultra-fast dependency tracking and is completely containerized for uniform deployment:

```bash
# 1. Clone the repository workspace
git clone <your-repo-url>
cd ai-video-auditor

# 2. Build the production multi-stage container
docker build -t video-auditor-backend -f backend/Dockerfile .

# 3. Spin up the application stack
docker run -p 8000:8000 --env-file backend/.env video-auditor-backend
```
Once initialized, open your local browser to access the auto-generated interactive OpenAPI documentation playground at `http://localhost:8000/docs`.

---
🔨 Actively maintained. Full architecture walkthrough and evaluation execution summaries will be updated here as each block clears production testing.
