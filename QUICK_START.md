# Quick Start Guide

This guide ensures your app compiles and runs correctly on first run.

## Prerequisites

- Docker Desktop installed and running
- Node.js 16.x or higher installed

## Automated Setup (Recommended)

Run the setup script for a hassle-free first run:

```bash
chmod +x setup.sh
./setup.sh
```

This script will:
1. ✅ Start database and Ollama services
2. ✅ Pull only the required models (nomic-embed-text, llama3.2:1b)
3. ✅ Build the application container
4. ✅ Initialize the database (if needed)
5. ✅ Install frontend dependencies
6. ✅ Provide clear next steps

## Manual Setup

If you prefer manual setup:

### 1. Start Services
```bash
docker compose up -d db ollama
```

### 2. Wait for Ollama
```bash
# Wait until this command succeeds
docker exec ollama ollama list
```

### 3. Pull Models (Only 1b, not 3b)
```bash
docker exec ollama ollama pull nomic-embed-text
docker exec ollama ollama pull llama3.2:1b
```

### 4. Build App
```bash
docker compose build app
```

### 5. Initialize Database
```bash
# Ingest data
docker compose run --rm app python -m backend.ingest

# Generate embeddings (optional, can take 10-20 minutes)
docker compose run --rm app python -m backend.embed
```

### 6. Install Frontend Dependencies
```bash
cd frontend
npm install --force
cd ..
```

## Starting the Application

### Backend (Terminal 1)
```bash
docker compose run --rm --service-ports app uvicorn backend.server:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend (Terminal 2)
```bash
cd frontend
npm start
# or: npx ng serve
```

### Access
- Frontend: http://localhost:4200
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## Why llama3.2:1b Instead of 3b?

**Efficiency Benefits:**
- ⚡ **2-3x faster** response times
- 💾 **~700MB less** memory usage (1.3GB vs 2GB)
- 💿 **~700MB less** disk space
- ✅ **Same accuracy** when provided with good context from RAG

The 1b model is sufficient for RAG applications where the LLM's job is to format and present retrieved facts, not generate knowledge from scratch.

## Troubleshooting

### Frontend won't compile
- Ensure `node_modules` exists: `cd frontend && npm install --force`
- Use `npx ng serve` if `ng` command not found

### Backend errors
- Check Docker is running: `docker info`
- Check services are up: `docker compose ps`
- Check models are pulled: `docker exec ollama ollama list`

### Database issues
- Reset database: `docker compose down -v` then restart services
- Re-run ingestion: `docker compose run --rm app python -m backend.ingest`
