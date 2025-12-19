# NBA Stats RAG Pipeline

A production-grade Retrieval-Augmented Generation (RAG) system for NBA statistics, demonstrating end-to-end ML/AI pipeline architecture from data ingestion through deployment.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     Angular 15 SPA (TypeScript)                      │   │
│  │              Interactive Chat Interface + Real-time UX              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼ HTTP/REST
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API LAYER                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    FastAPI (Python 3.11)                            │   │
│  │           Async Request Handling • CORS • Input Validation          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PROCESSING LAYER                                   │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌─────────────────┐   │
│  │   Query Parser       │  │   Hybrid Retrieval   │  │  LLM Response   │   │
│  │  ─────────────────   │  │  ─────────────────   │  │  ────────────   │   │
│  │  • Date Extraction   │  │  • SQL Filtering     │  │  • Context      │   │
│  │  • Entity Recognition│  │  • Vector Similarity │  │    Assembly     │   │
│  │  • Season Inference  │  │  • Fallback Logic    │  │  • Generation   │   │
│  └──────────────────────┘  └──────────────────────┘  └─────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DATA LAYER                                        │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌─────────────────┐   │
│  │   PostgreSQL 16      │  │      pgvector        │  │     Ollama      │   │
│  │  ─────────────────   │  │  ─────────────────   │  │  ────────────   │   │
│  │  • Structured Data   │  │  • 768-dim Vectors   │  │  • Embeddings   │   │
│  │  • 38K+ Records      │  │  • HNSW Indexing     │  │  • LLM Inference│   │
│  │  • Relational Joins  │  │  • ANN Search        │  │  • Model Cache  │   │
│  └──────────────────────┘  └──────────────────────┘  └─────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Key Architectural Decisions

### 1. Microservices Design with Container Orchestration

The system uses a decoupled microservices architecture orchestrated via Docker Compose:

| Service | Purpose | Scaling Strategy |
|---------|---------|------------------|
| `db` | PostgreSQL + pgvector | Vertical scaling, read replicas |
| `ollama` | LLM/Embedding inference | Horizontal scaling behind load balancer |
| `app` | FastAPI application | Stateless, horizontally scalable |

**Design Rationale**: Each service can be independently scaled, updated, and monitored. The stateless API layer enables horizontal scaling, while the database layer maintains consistency.

### 2. Hybrid Search Architecture

Rather than relying solely on vector similarity, the system implements a **hybrid retrieval strategy**:

```
Query → Parse Entities → SQL Filters → Vector Search → Rank → LLM
              │                │              │
              ▼                ▼              ▼
         Dates, Teams,    Structured      Semantic
         Players, Season   Pruning        Matching
```

**Why Hybrid?** Pure vector search struggles with precise constraints (exact dates, specific teams). SQL pre-filtering reduces the search space, improving both accuracy and performance.

### 3. Vector Index Selection (HNSW vs IVFFlat)

With ~38,000 vectors (1,682 games + 36,222 player box scores):

| Index Type | Training Required | Update Cost | Use Case |
|------------|------------------|-------------|----------|
| **HNSW** (selected) | No | Low | Dynamic data, <100K vectors |
| IVFFlat | Yes | High (rebuild) | Static data, >1M vectors |

**Decision**: HNSW provides approximate nearest neighbor search without training overhead and handles incremental updates efficiently.

### 4. Model Selection Trade-offs

Selected `llama3.2:1b` over `llama3.2:3b`:

| Metric | 1B Model | 3B Model |
|--------|----------|----------|
| Response Time | ~2-3x faster | Baseline |
| Memory | ~1.3GB | ~2GB |
| Accuracy (with good context) | High | Marginally higher |

**Insight**: For RAG applications, embedding quality and retrieval precision matter more than raw model size. Well-structured context compensates for smaller models.

### 5. Embedding Strategy

Text serialization includes multiple representations to maximize retrieval coverage:

- **Multiple date formats**: ISO, MM/DD/YY, natural language ("October 27, 2023")
- **Special event tags**: Christmas Day, New Year's Eve, Season Opener
- **Achievement markers**: Triple-double, 40-point game, NBA debut
- **Computed fields**: Leading scorer per game, team standings context

## Data Pipeline

```
CSV Files → Bulk Ingestion → Text Serialization → Vector Embedding → HNSW Index
    │            │                   │                  │               │
    ▼            ▼                   ▼                  ▼               ▼
 4 tables    COPY command      Multi-format        768-dim         Sub-ms
 38K rows    (bypass SQL)      representations    nomic-embed       ANN
```

### Performance Optimizations

1. **Bulk Loading**: PostgreSQL `COPY` command streams CSV data directly, bypassing SQL parsing
2. **Batch Embedding**: Process records in batches to maximize GPU/CPU utilization
3. **Query Caching**: Embedding cache for repeated queries eliminates redundant API calls
4. **Connection Pooling**: SQLAlchemy connection pool minimizes database overhead

## Technology Stack

### Backend
- **Python 3.11** - Core runtime
- **FastAPI** - Async API framework with automatic OpenAPI docs
- **SQLAlchemy** - ORM with raw SQL escape hatches for performance
- **pgvector** - Vector similarity search extension
- **Ollama** - Local LLM inference (nomic-embed-text, llama3.2:1b)

### Frontend
- **Angular 15** - Component-based SPA framework
- **TypeScript 4.9** - Type-safe development
- **RxJS** - Reactive async handling

### Infrastructure
- **Docker Compose** - Multi-service orchestration
- **PostgreSQL 16** - Primary datastore with pgvector extension
- **AWS S3** - Large asset storage (video demos >100MB)
- **Hugging Face Hub** - Model artifact deployment

## Cloud-Native Design Patterns

While deployed locally via Docker, the architecture maps directly to cloud services:

| Local Component | Cloud Equivalent |
|-----------------|------------------|
| PostgreSQL + pgvector | Amazon RDS/Aurora, Azure Cosmos DB, Cloud SQL |
| Ollama (LLM/Embeddings) | Amazon Bedrock, Azure OpenAI, Vertex AI |
| FastAPI container | AWS Lambda, Cloud Run, Azure Functions |
| Docker Compose | ECS/Fargate, Kubernetes, Cloud Run |
| S3 (video storage) | Native cloud object storage |

## Quick Start

### Prerequisites
- Docker Desktop
- Node.js 16.x
- 8GB+ RAM recommended

### 1. Start Services

```bash
# Automated setup (recommended)
chmod +x setup.sh
./setup.sh

# Or manual setup
docker compose up -d db ollama
docker exec ollama ollama pull nomic-embed-text
docker exec ollama ollama pull llama3.2:1b
docker compose build app
```

### 2. Initialize Data Pipeline

```bash
# Ingest CSV data into PostgreSQL
docker compose run --rm app python -m backend.ingest

# Generate embeddings (time-intensive on first run)
docker compose run --rm app python -m backend.embed

# Run RAG pipeline against test questions
docker compose run --rm app python -m backend.rag
```

### 3. Launch Application

```bash
# Start backend API
docker compose run --rm --service-ports app uvicorn backend.server:app --host 0.0.0.0 --port 8000 --reload

# In a new terminal - start frontend
cd frontend
npm install --force
npm start
```

Access the application at `http://localhost:4200`

## Project Structure

```
├── backend/
│   ├── config.py          # Service configuration
│   ├── ingest.py          # Data ingestion pipeline
│   ├── embed.py           # Embedding generation
│   ├── rag.py             # Hybrid search + RAG logic
│   ├── server.py          # FastAPI endpoints
│   ├── utils.py           # Ollama API utilities
│   └── data/              # Source CSV files
│
├── frontend/
│   └── src/app/           # Angular application
│       ├── app.component.ts
│       └── services/      # API client services
│
├── part1/                 # RAG evaluation results
├── part2/                 # Demo video (S3 link)
├── part3/                 # Technical writeup
├── part4/                 # Fine-tuning experiments
│
├── docker-compose.yml     # Service orchestration
├── Dockerfile            # Python app container
├── setup.sh              # Automated setup script
└── requirements.txt      # Python dependencies
```

## Results

### RAG Pipeline Performance

| Metric | Value |
|--------|-------|
| Top-1 Accuracy | 78% (7/9) |
| Top-5 Accuracy | 100% (9/9) |
| Total Vectors | 37,904 |
| Avg Query Time | <500ms |

### Fine-Tuned Embedding Model

Deployed to Hugging Face Hub: [`drbinna/e5-nba-finetuned`](https://huggingface.co/drbinna/e5-nba-finetuned)

```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("drbinna/e5-nba-finetuned")
```

| Metric | Baseline E5 | Fine-tuned |
|--------|-------------|------------|
| Recall@1 | 0% | 10% |
| Recall@5 | 90% | 100% |

## Scalability Considerations

### Horizontal Scaling Path
1. **API Layer**: Stateless design enables load-balanced replicas
2. **Embedding Service**: Queue-based batch processing for high throughput
3. **Vector Database**: Partitioning by season/team for distributed search
4. **Caching Layer**: Redis for query/embedding caching

### Production Hardening
- [ ] Implement circuit breakers for external service calls
- [ ] Add distributed tracing (OpenTelemetry)
- [ ] Set up health check endpoints and liveness probes
- [ ] Configure rate limiting and request throttling
- [ ] Implement async embedding generation queue

## Author

**Obinna Amadi**

---

*Built with a focus on production-grade architecture, demonstrating end-to-end ML pipeline design from data engineering through model deployment.*
