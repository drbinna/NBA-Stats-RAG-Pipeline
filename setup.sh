#!/bin/bash
# Setup script to ensure first-run compilation works without issues
# This script sets up the entire project for first-time use

set -e  # Exit on any error

echo "🚀 Setting up NBA RAG Application..."
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop first."
    exit 1
fi

echo "✅ Docker is running"
echo ""

# Step 1: Start database and Ollama
echo "📦 Starting database and Ollama services..."
docker compose up -d db ollama

# Wait for Ollama to be healthy
echo "⏳ Waiting for Ollama to be ready..."
timeout=60
counter=0
while ! docker exec ollama ollama list > /dev/null 2>&1; do
    sleep 2
    counter=$((counter + 2))
    if [ $counter -ge $timeout ]; then
        echo "❌ Ollama failed to start within $timeout seconds"
        exit 1
    fi
done
echo "✅ Ollama is ready"
echo ""

# Step 2: Pull only the models we need (1b, not 3b)
echo "📥 Pulling required models (this may take a few minutes)..."
echo "  - Pulling nomic-embed-text (embedding model)..."
docker exec ollama ollama pull nomic-embed-text

echo "  - Pulling llama3.2:1b (LLM model - smaller, faster)..."
docker exec ollama ollama pull llama3.2:1b

echo "✅ Models downloaded"
echo ""

# Step 3: Build the app container
echo "🔨 Building application container..."
docker compose build app
echo "✅ Application container built"
echo ""

# Step 4: Check if database needs initialization
echo "🔍 Checking database status..."
GAME_COUNT=$(docker compose exec -T db psql -U nba -d nba -t -c "SELECT COUNT(*) FROM game_details;" 2>/dev/null | xargs || echo "0")

if [ "$GAME_COUNT" = "0" ] || [ -z "$GAME_COUNT" ]; then
    echo "📊 Database is empty. Initializing..."
    echo "  - Ingesting data..."
    docker compose run --rm app python -m backend.ingest
    
    echo "  - Generating embeddings (this may take 10-20 minutes)..."
    echo "    ⚠️  You can skip this for now and run it later with:"
    echo "       docker compose run --rm app python -m backend.embed"
    read -p "    Generate embeddings now? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker compose run --rm app python -m backend.embed
        echo "✅ Embeddings generated"
    else
        echo "⏭️  Skipping embeddings for now"
    fi
else
    echo "✅ Database already initialized with $GAME_COUNT games"
fi
echo ""

# Step 5: Install frontend dependencies
echo "📦 Installing frontend dependencies..."
cd frontend
if [ ! -d "node_modules" ]; then
    npm install --force
    echo "✅ Frontend dependencies installed"
else
    echo "✅ Frontend dependencies already installed"
fi
cd ..
echo ""

# Step 6: Summary
echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "To start the application:"
echo ""
echo "1. Start backend server:"
echo "   docker compose run --rm --service-ports app uvicorn backend.server:app --host 0.0.0.0 --port 8000 --reload"
echo ""
echo "2. In another terminal, start frontend:"
echo "   cd frontend && npm start"
echo ""
echo "3. Open http://localhost:4200 in your browser"
echo ""
echo "Note: Only llama3.2:1b model is installed (not 3b) for better efficiency."
echo "      This saves ~2GB disk space and improves response times."
