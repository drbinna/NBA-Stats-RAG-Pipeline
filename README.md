# Courtside - NBA Stats Assistant

An AI-powered NBA statistics assistant that answers questions about games, players, and performances using Claude AI and live data from the balldontlie API.

**Live Demo:** [https://nba-stats-rag-pipeline-zeab.vercel.app](https://nba-stats-rag-pipeline-zeab.vercel.app)

## Features

- **Natural Language Queries** - Ask questions in plain English about NBA stats
- **Historical Data** - Access to 36,000+ player box scores from Oct 2023 - Apr 2025
- **Live Game Data** - Real-time scores and recent games via balldontlie API
- **Player Stats by Date** - Look up specific player performances on any date
- **Claude AI Powered** - Intelligent responses using Anthropic's Claude API

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Vercel                               │
│                (Angular + Python Backend)                   │
└─────────────────────────────────────────────────────────────┘
                               │
                               ▼ HTTPS
┌─────────────────────────────────────────────────────────────┐
│                    Neon Serverless DB                       │
│                       (PostgreSQL)                          │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   PostgreSQL    │  │  balldontlie    │  │   Claude API    │
│    (Neon)       │  │      API        │  │   (Anthropic)   │
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

- **Frontend:** Angular 15
- **Backend:** Python (FastAPI) on Vercel Functions
- **Database:** Neon Serverless PostgreSQL
- **AI:** Claude API (Anthropic)
- **Live Data:** balldontlie.io API

## Deployment with Vercel

The project is optimized for zero-config deployment on Vercel.

1. Connect your repository to Vercel.
2. Link a **Vercel Postgres (Neon)** database in the Storage tab.
3. Configure the following Environment Variables in Vercel:
   - `ANTHROPIC_API_KEY`
   - `BALLDONTLIE_API_KEY`
   - `POSTGRES_URL` (Automatically added when linking Neon)

## Author

**Obinna Amadi**
