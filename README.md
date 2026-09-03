# Courtside - NBA Stats Assistant

An NBA statistics assistant that answers questions about games, players, and performances. It is a tool-using agent: the model resolves players and runs typed, parameterized SQL queries against 36,000+ box scores, then answers only from what those queries return. Runs on an open model via Fireworks AI, with live data from the balldontlie API for anything after the historical cutoff.

**Live Demo:** [https://nba-stats-rag-pipeline-zeab.vercel.app](https://nba-stats-rag-pipeline-zeab.vercel.app)

## Features

- **Natural Language Queries** - Ask questions in plain English about NBA stats
- **Historical Data** - Access to 36,000+ player box scores from Oct 2023 - Apr 2025
- **Live Game Data** - Real-time scores and recent games via balldontlie API
- **Player Stats by Date** - Look up specific player performances on any date
- **Grounded Answers** - Every number comes from a SQL query the model chose to run; no guessing from memory
- **Swappable Model** - Any function-calling model on Fireworks AI, set with one env var

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
│   PostgreSQL    │  │  balldontlie    │  │  Fireworks AI   │
│    (Neon)       │  │      API        │  │  (open model)   │
│  ────────────   │  │  ────────────   │  │  ────────────   │
│  Historical     │  │  Live Games     │  │  Tool-calling   │
│  Box Scores     │  │  Recent Scores  │  │  agent          │
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
- **AI:** Fireworks AI (default `qwen3p7-plus`) via the Anthropic-compatible Messages API with tool use
- **Live Data:** balldontlie.io API

## Deployment with Vercel

The project is optimized for zero-config deployment on Vercel.

1. Connect your repository to Vercel.
2. Link a **Vercel Postgres (Neon)** database in the Storage tab.
3. Configure the following Environment Variables in Vercel:
   - `FIREWORKS_API_KEY`
   - `MODEL_ID` (optional, defaults to `accounts/fireworks/models/qwen3p7-plus`)
   - `BALLDONTLIE_API_KEY`
   - `POSTGRES_URL` (Automatically added when linking Neon)

## How it answers a question

1. The model receives the question plus the database's real date range.
2. It calls `search_players` to resolve a name or nickname ("SGA", "Chet") to a player_id.
3. It calls one or more typed tools: `player_game_stats`, `player_averages`, `top_performances`, `game_results`, `list_teams`, or the `live_*` tools for dates after the cutoff.
4. It answers from the returned rows. If a tool returns nothing, it says so rather than guessing.

Run `python -m tests.eval` with the env vars set to check behaviour end to end.

## Author

**Obinna Amadi**
