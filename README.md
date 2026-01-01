# Courtside - NBA Stats Assistant

An AI-powered NBA statistics assistant that answers questions about games, players, and performances using Claude AI and live data from the balldontlie API.

**Live Demo:** [https://courtside.vercel.app](https://courtside.vercel.app) *(add your Vercel URL here)*

## Features

- **Natural Language Queries** - Ask questions in plain English about NBA stats
- **Historical Data** - Access to 36,000+ player box scores from Oct 2023 - Apr 2025
- **Live Game Data** - Real-time scores and recent games via balldontlie API
- **Player Stats by Date** - Look up specific player performances on any date
- **Claude AI Powered** - Intelligent responses using Anthropic's Claude API

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Angular Frontend                         │
│              (Interactive Chat Interface)                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ HTTP/REST
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                          │
│         Question Parsing • Data Retrieval • Response         │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   PostgreSQL    │  │  balldontlie    │  │   Claude API    │
│   + pgvector    │  │      API        │  │   (Anthropic)   │
│  ────────────   │  │  ────────────   │  │  ────────────   │
│  Historical     │  │  Live Games     │  │  AI Response    │
│  Box Scores     │  │  Recent Scores  │  │  Generation     │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

## Question Types Supported

| Category | Example Questions |
|----------|-------------------|
| **Player Stats by Date** | "How many points did SGA score on 4/8?" |
| **Top Performances** | "Who had the most points in a single game?" |
| **Recent Games** | "What games happened recently?" |
| **Triple-Doubles** | "Who recorded triple-doubles?" |
| **Christmas Games** | "What games happened on Christmas?" |

## Tech Stack

- **Frontend:** Angular 15, TypeScript, SCSS
- **Backend:** Python 3.11, FastAPI, SQLAlchemy
- **Database:** PostgreSQL 16 with pgvector
- **AI:** Claude API (Anthropic)
- **Live Data:** balldontlie.io API

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 16+
- Docker (for PostgreSQL database)
- Anthropic API key
- balldontlie API key

### 1. Clone and Install Dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd frontend && npm install && cd ..
```

### 2. Environment Setup

Create a `.env` file in the project root:

```bash
ANTHROPIC_API_KEY=your-anthropic-key
BALLDONTLIE_API_KEY=your-balldontlie-key
DB_DSN=postgresql://nba:nba@localhost:5432/nba
```

### 3. Start Database

```bash
docker compose up -d db
```

### 4. Ingest Data

```bash
# Load environment variables and run ingestion
export $(cat .env | xargs) && python -m backend.ingest
```

### 5. Start Backend

```bash
export $(cat .env | xargs) && uvicorn backend.server:app --host 0.0.0.0 --port 8000 --reload
```

### 6. Start Frontend (new terminal)

```bash
cd frontend
npm start
```

Access the application at `http://localhost:4200`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | Submit a question, get AI response |
| `/api/health` | GET | Health check |

### Example Request

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "How many points did SGA score on 4/8?"}'
```

### Example Response

```json
{
  "answer": "On April 8, 2025, Shai Gilgeous-Alexander had an outstanding performance for the Oklahoma City Thunder. He scored 32 points, grabbed 5 rebounds, and dished out 8 assists in 36.2 minutes of play.",
  "evidence": [],
  "used_live_data": false
}
```

## Database Schema

| Table | Records | Description |
|-------|---------|-------------|
| `players` | 683 | Player profiles |
| `teams` | 30 | NBA teams |
| `game_details` | 1,682 | Game scores and metadata |
| `player_box_scores` | 36,222 | Individual player game stats |

## Project Structure

```
├── backend/
│   ├── config.py       # Environment configuration
│   ├── ingest.py       # Data ingestion pipeline
│   ├── server.py       # FastAPI endpoints + Claude integration
│   └── data/           # Source CSV files
│
├── frontend/
│   └── src/app/        # Angular application
│
├── docker-compose.yml  # Database service
├── requirements.txt    # Python dependencies
└── .env               # API keys (not committed)
```

## Deployment

### Vercel (Frontend)

1. Connect your GitHub repository to Vercel
2. Set root directory: `frontend`
3. Build command: `npm run build`
4. Output directory: `dist/app`

### Backend

Deploy to any Python-compatible platform (Railway, Render, Fly.io):

1. Set environment variables for API keys
2. Connect to PostgreSQL database
3. Run with: `uvicorn backend.server:app --host 0.0.0.0 --port $PORT`

## Author

**Obinna Amadi**

---


