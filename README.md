# Ardia — Autonomous Research Agent

Submits a natural-language question, runs a five-stage LangGraph pipeline, and returns a signed download link to a formatted DOCX report.

## Architecture

```
POST /research
      │
      ▼
  Celery task
      │
      ▼
┌─────────────────────────────────────────────┐
│  LangGraph pipeline                         │
│                                             │
│  Planner → Retriever → Evaluator            │
│                  ▲          │               │
│                  │          ▼               │
│             (gap loop)  Synthesizer         │
│                              │              │
│                              ▼              │
│                          Formatter          │
└─────────────────────────────────────────────┘
      │
      ▼
  MinIO (S3-compatible)
      │
      ▼
  Presigned URL → client
```

| Stage | What it does |
|---|---|
| **Planner** | Decomposes the question into 3–5 focused sub-queries |
| **Retriever** | Searches the web concurrently for each sub-query (DuckDuckGo) |
| **Evaluator** | Scores every result on relevance, recency, and credibility; filters composite < 0.6 |
| **Synthesizer** | Produces a structured `ReportDraft` JSON; identifies unanswered gaps |
| **Formatter** | Renders the draft to DOCX via a Node.js script, uploads to MinIO |

The synthesizer loops back to the retriever when gaps remain, up to the per-mode limit.

| Mode | Max iterations |
|---|---|
| `quick` | 1 |
| `standard` | 2 |
| `deep` | 3 |

## Tech stack

| Layer | Choice |
|---|---|
| Orchestration | LangGraph 0.2.x |
| LLM | Any HuggingFace Inference API model (configurable) |
| Web search | DuckDuckGo via LangChain Community |
| Document generation | `docx` npm package (Node.js subprocess) |
| Backend API | FastAPI + Python 3.12 |
| Async tasks | Celery 5 + Redis 7 |
| Object storage | MinIO (S3-compatible — swap to AWS S3 with one config change) |
| Tracing | LangSmith |
| Frontend | React 18 + Tailwind CSS |
| Infra | Docker Compose |

## Project layout

```
ardia/
├── backend/
│   ├── api/
│   │   ├── main.py          # FastAPI app — /research endpoints + /health
│   │   └── schemas.py       # ResearchRequest / ResearchResponse
│   ├── agent/
│   │   ├── graph.py         # LangGraph pipeline definition
│   │   ├── llm.py           # LangChain model factory (swap providers here)
│   │   ├── state.py         # AgentState TypedDict
│   │   ├── models.py        # Pydantic v2 data contracts
│   │   └── nodes/
│   │       ├── planner.py
│   │       ├── retriever.py
│   │       ├── evaluator.py
│   │       ├── synthesizer.py
│   │       └── formatter.py
│   ├── tasks.py             # Celery task wrapping graph.run()
│   ├── storage.py           # MinIO upload + presigned URL helpers
│   └── config.py            # pydantic-settings — all env vars
├── document-gen/
│   ├── generate.js          # Node.js DOCX builder
│   └── package.json
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── api.js
│       └── components/
│           ├── ResearchForm.jsx
│           ├── StatusPoller.jsx
│           └── ResultCard.jsx
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Quick start

```bash
# 1. Copy and fill in your credentials
cp .env.example .env

# 2. Build and start all services
docker compose up --build

# 3. Open the frontend
#    http://localhost:5173

# 4. MinIO console (create/inspect buckets)
#    http://localhost:9001
```

Services started by Docker Compose:

| Service | Port | Description |
|---|---|---|
| `redis` | 6379 | Celery broker + result backend |
| `minio` | 9000 / 9001 | Object storage API / admin console |
| `minio-init` | — | One-shot container that creates the bucket |
| `api` | 8000 | FastAPI backend |
| `worker` | — | Celery worker (2 concurrent jobs) |
| `frontend` | 5173 | Vite dev server |

## Environment variables

Copy `.env.example` to `.env` and fill in the required values.

| Variable | Required | Default | Description |
|---|---|---|---|
| `HUGGINGFACE_API_KEY` | Yes | — | HuggingFace Inference API key |
| `LLM_MODEL` | No | `mistralai/Mistral-7B-Instruct-v0.3` | Any HF chat model repo ID |
| `LLM_PROVIDER` | No | — | HuggingFace Inference provider (e.g. `featherless-ai`, `together`). Unset to use HuggingFace's own infrastructure |
| `LANGSMITH_API_KEY` | Yes | — | LangSmith tracing key |
| `LANGSMITH_PROJECT` | No | `research-agent` | LangSmith project name |
| `MINIO_ENDPOINT` | No | `http://minio:9000` | Internal MinIO URL used by backend services |
| `MINIO_PUBLIC_ENDPOINT` | No | `http://localhost:9000` | Host-accessible MinIO URL embedded in presigned download links |
| `MINIO_ACCESS_KEY` | Yes | — | MinIO root user |
| `MINIO_SECRET_KEY` | Yes | — | MinIO root password |
| `MINIO_BUCKET` | No | `research-reports` | Bucket for report files |
| `REDIS_URL` | No | `redis://redis:6379/0` | Celery broker URL |
| `ENVIRONMENT` | No | `development` | Set to `production` to restrict CORS |
| `VITE_API_URL` | No | `http://localhost:8000` | Frontend → API base URL |

## Swapping the LLM provider

All LLM calls go through [`backend/agent/llm.py`](backend/agent/llm.py). To switch providers, change the two lines inside `get_llm()`:

```python
# HuggingFace (default)
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint

# OpenAI
from langchain_openai import ChatOpenAI
return ChatOpenAI(model="gpt-4o", api_key=settings.openai_api_key)

# Ollama (local)
from langchain_ollama import ChatOllama
return ChatOllama(model="llama3")
```

No other files need to change.

## Swapping to AWS S3

MinIO and AWS S3 share the same API. To switch:

1. Remove `MINIO_*` vars; add `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET`, `AWS_REGION`.
2. In [`backend/storage.py`](backend/storage.py), remove `endpoint_url` from the client call and update the setting references.
3. Remove the `minio` and `minio-init` services from `docker-compose.yml`.

## API reference

### `POST /research`

Start a research job.

```json
// Request
{ "question": "What are the latest advances in fusion energy?", "mode": "standard" }

// Response 202
{ "job_id": "abc-123", "status": "queued" }
```

### `GET /research/{job_id}`

Poll job status.

```json
// Done
{ "job_id": "abc-123", "status": "done", "output_url": "http://minio:9000/..." }

// Failed
{ "job_id": "abc-123", "status": "failed", "error": "..." }
```

### `GET /health`

Returns `{"status": "ok"}`. Used by Docker Compose health checks.
