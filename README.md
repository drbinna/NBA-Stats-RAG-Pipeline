# Courtside — NBA Stats Assistant

Ask questions about NBA games and players in plain English and get answers grounded in real box-score data.

Courtside is a **tool-using agent**, not a retrieval-over-embeddings RAG. The model never sees a dump of the database. Instead it resolves player names and calls typed, parameterized SQL tools against 36,000+ historical box scores (plus two live-data tools for the current season), then answers only from what those tools return. Every answer ships with the list of tool calls that produced it.

**Live:** https://nba-stats-rag-pipeline-zeab.vercel.app

```
Q: How many points did SGA score on 4/8?
A: SGA scored 42 points on April 8, 2025 against the Lakers at home. The Thunder won 136-120.
   evidence: search_players({"name": "SGA"}) → player_game_stats({"player_id": 1628983, "game_date": "2025-04-08"})
```

## What it can answer

| Category | Example |
|----------|---------|
| Player stats on a date | "How many points did SGA score on 4/8?" |
| Player vs. opponent | "How did Chet do against the Lakers?" |
| Season averages | "What is SGA averaging?" |
| Top single-game performances | "Who had the most points in a single game?" |
| Stat leaders | "Who leads the league in assists per game?" |
| Triple-doubles | "Who recorded the most triple-doubles?" |
| Game results | "What games happened on Christmas?" |
| Live / recent games | "What did the Thunder do last night?" |

The historical database covers **Oct 2023 – Apr 2025**. Questions about dates after that route to the balldontlie API. If a tool returns nothing, the assistant says so instead of guessing.

## How a question is answered

1. The model receives the question, today's date, and the database's actual date range.
2. It calls `search_players` to resolve a name or nickname ("SGA", "Chet", "Joker") to a `player_id`. A small alias table catches nicknames a substring match would miss.
3. It calls one or more typed tools. Each tool is a parameterized SQL query (or a balldontlie request); the model chooses arguments, never raw SQL.
4. It answers from the returned rows. Up to 6 tool rounds are allowed; after that the agent is forced to answer from what it has.

### Tools

| Tool | Source | Purpose |
|------|--------|---------|
| `search_players` | Postgres | Name/nickname → player_id, with games-in-db count |
| `player_game_stats` | Postgres | One player's box scores, filtered by date or opponent |
| `player_averages` | Postgres | Per-game averages over a date range |
| `top_performances` | Postgres | Best single games by any stat, optional triple-double filter |
| `stat_leaders` | Postgres | Per-game leaders with a minimum-games threshold |
| `triple_double_counts` | Postgres | Triple-double totals by player |
| `game_results` | Postgres | Scores by team, date, or range |
| `list_teams` | Postgres | Team names and abbreviations |
| `live_games` | balldontlie | Scores for today or the last N days |
| `live_player_season_averages` | balldontlie | Current-season averages |

## Architecture

```
Browser (Angular)
      │  POST /api/chat {question}
      ▼
Vercel Python Function (FastAPI)
      │
      ├── Fireworks AI ──── open model with tool use (Anthropic-compatible Messages API)
      ├── Neon Postgres ─── teams, players, game_details, player_box_scores
      └── balldontlie ───── live scores and current-season averages
```

## Tech stack

| Layer | Technology |
|-------|------------|
| Frontend | Angular 15, SCSS |
| API | Python, FastAPI on Vercel Functions (30s max duration) |
| Database | Neon serverless PostgreSQL, SQLAlchemy |
| AI | Fireworks AI via the `anthropic` SDK pointed at Fireworks' Anthropic-compatible endpoint; default model `qwen3p7-plus` |
| Live data | balldontlie.io API |

## Project structure

```
├── api/
│   └── index.py            # Vercel entrypoint: re-exports the FastAPI app
├── backend/
│   ├── server.py           # Tools, system prompt, agent loop, /api/chat, /api/health
│   ├── config.py           # Env var resolution (DB DSN, keys, model)
│   ├── ingest.py           # Bulk-loads the CSVs into Postgres with COPY
│   └── data/               # teams, players, game_details, player_box_scores (CSV)
├── frontend/               # Angular app (chat UI)
├── tests/
│   └── eval.py             # End-to-end question/answer checks
├── requirements.txt
├── vercel.json             # Function config + SPA rewrites
└── .env.example
```

## Configuration

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `POSTGRES_URL` | Yes | — | Neon connection string. `DATABASE_URL`, `DB_DSN`, and `RAG_URL_`-prefixed variants are also accepted. |
| `FIREWORKS_API_KEY` | Yes | — | [fireworks.ai](https://fireworks.ai/account/api-keys) |
| `MODEL_ID` | No | `accounts/fireworks/models/qwen3p7-plus` | Any Fireworks serverless model that supports tool calling |
| `BALLDONTLIE_API_KEY` | No | — | Without it, live_* tools report data as unavailable |

Swapping models is a one-variable change. Pick from the [Fireworks model library](https://app.fireworks.ai/models?filter=LLM&serverless=true); the model must support function calling.

## API

**`POST /api/chat`**
```json
{ "question": "Who had the most points in a single game?" }
```
Response:
```json
{ "answer": "...", "evidence": [{ "tool": "top_performances", "input": { "stat": "points", "n": 10 } }] }
```
Questions are capped at 500 characters. Errors return a friendly `answer` with empty `evidence` rather than an HTTP error.

**`GET /api/health`** — reports whether the DB and model are configured and which model is active.

## Local development

**Prerequisites:** Python 3.11+, Node 18+, a Postgres database (Neon free tier works), a Fireworks API key.

```bash
# 1. Environment
cp .env.example .env            # fill in POSTGRES_URL, FIREWORKS_API_KEY, BALLDONTLIE_API_KEY
pip install -r requirements.txt pandas

# 2. Load the data (one time, ~38k rows)
python -m backend.ingest

# 3. API
uvicorn backend.server:app --reload --port 8000

# 4. Frontend (separate terminal)
cd frontend && npm install && npm start     # http://localhost:4200
```

Point the frontend at the local API by editing `frontend/src/environments/environment.ts`.

## Evaluation

`tests/eval.py` runs a fixed set of natural-language questions through the agent and checks each answer for an expected substring, printing the tools called and timing:

```bash
POSTGRES_URL=... FIREWORKS_API_KEY=... BALLDONTLIE_API_KEY=... python -m tests.eval
```

Use it as a smoke test after changing the prompt, the tools, or `MODEL_ID`.

## Deployment

The repo is linked to Vercel; pushes to `main` deploy automatically.

For a fresh deployment:

1. Import the repo at [vercel.com/new](https://vercel.com/new)
2. In **Storage**, create or link a Neon Postgres database (this sets `POSTGRES_URL`)
3. Add `FIREWORKS_API_KEY` and `BALLDONTLIE_API_KEY` under **Environment Variables**
4. Run `python -m backend.ingest` locally against the Neon DSN to load the data
5. Deploy

## Author

**Obinna Amadi**
