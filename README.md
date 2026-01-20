# Courtside - NBA Stats Assistant

An AI-powered NBA statistics assistant that answers questions about games, players, and performances using Claude AI and live data from the balldontlie API.

**Live Demo:** [https://nba-stats-frontend.onrender.com](https://nba-stats-frontend.onrender.com)

## Features

- **Natural Language Queries** - Ask questions in plain English about NBA stats
- **Historical Data** - Access to 36,000+ player box scores from Oct 2023 - Apr 2025
- **Live Game Data** - Real-time scores and recent games via balldontlie API
- **Player Stats by Date** - Look up specific player performances on any date
- **Claude AI Powered** - Intelligent responses using Anthropic's Claude API

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Render Static Site                       │
│                   (Angular Frontend)                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ HTTPS
┌─────────────────────────────────────────────────────────────┐
│                   Render Web Service                        │
│                    (FastAPI Backend)                         │
│         Question Parsing • Data Retrieval • Response         │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   PostgreSQL    │  │  balldontlie    │  │   Claude API    │
│    (Render)     │  │      API        │  │   (Anthropic)   │
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
- **Hosting:** Render (Web Service, Static Site)

## Local Development

### Prerequisites
- Python 3.11+
- Node.js 16+
- Docker (for local PostgreSQL)
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
export $(cat .env | xargs) && python -m backend.ingest
```

### 5. Start Backend

```bash
export $(cat .env | xargs) && uvicorn backend.server:app --port 8000 --reload
```

### 6. Start Frontend (new terminal)

```bash
cd frontend && npm start
```

Access the application at `http://localhost:4200`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | Submit a question, get AI response |
| `/api/health` | GET | Health check |
| `/api/debug` | GET | Database connection status |

### Example Request

```bash
curl -X POST https://nba-stats-api.onrender.com/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "How many points did SGA score on 4/8?"}'
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
├── Dockerfile          # Backend container image
├── docker-compose.yml  # Local development database
├── requirements.txt    # Python dependencies
└── .env               # API keys (not committed)
```

## Deployment

### AWS Architecture

| Component | Service | Details |
|-----------|---------|---------|
| Frontend | S3 + CloudFront | Static hosting with global CDN |
| Backend | Lightsail Container | Docker container running FastAPI |
| Database | Render PostgreSQL | Managed PostgreSQL instance |

### Deploy to Render

The project includes a `render.yaml` file for Blueprint deployments.

1. Connect your repository to Render.
2. Render will automatically detect the `render.yaml` and prompt you to create the services.
3. Configure the following Environment Variables in the Render Dashboard for the `nba-stats-api` service:
   - `ANTHROPIC_API_KEY`
   - `BALLDONTLIE_API_KEY`
   - `DB_DSN`

## Author

**Obinna Amadi**
