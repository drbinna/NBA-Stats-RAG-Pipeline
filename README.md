# Courtside: NBA Stats RAG Pipeline

Ask questions about NBA games and players in plain English and get answers grounded in retrieved box-score passages, with the passages cited.

Courtside is a retrieval-augmented generation (RAG) system. Every regular-season game and every player's line in it becomes a text passage, embedded with `nomic-embed-text-v1.5` and indexed in PostgreSQL with pgvector. A question is answered from the passages that hybrid retrieval returns: SQL filters built from the question narrow the passages, and vector similarity ranks what's left. The model cites the ids of the passages it used.

```
Q: How many points did SGA score on 4/8?
A: Shai Gilgeous-Alexander scored 42 points on April 8, 2025 in a 136-120 home win over the Lakers. [line:0022401153:1628983]
```

## Results

Retrieval measured with `tests/retrieval_eval.py` on the 2024-25 season (27,381 passages), comparing the baseline (vector similarity alone) with production retrieval (entity filters, then vector similarity). Questions are built from the database with a fixed seed, so every run uses the same set.

| Question set | Questions | Recall@1 | Recall@5 | MRR@10 | Fusion Recall@1 |
|---|---:|---:|---:|---:|---:|
| Standard: clean names and dates | 160 | 46% → **100%** | 74% → **100%** | 0.59 → **1.00** | 97% |
| Hard: typos, unknown nicknames, stat-described players, cities only | 160 | 22% → **94%** | 41% → **100%** | 0.31 → **0.96** | 87% |

By question type, Recall@1 for vector alone, then production:

| Question type | Set | Vector only | Production |
|---|---|---:|---:|
| Game result | Standard | 62% | **100%** |
| Player on a date | Standard | 5% | **100%** |
| Player vs a team on a date | Standard | 50% | **100%** |
| Triple-doubles vs a team (no date) | Standard | 68% | **100%** |
| Games named by city only | Hard | 60% | **100%** |
| Players described by a stat line, not named | Hard | 0% | **92%** |
| Misspelled names | Hard | 2% | **100%** |
| Nicknames the parser doesn't know | Hard | 28% | **82%** |

What the numbers say:
- **Vector search alone isn't enough for stats.** A box score for one player on one date looks almost identical to hundreds of others, so similarity alone found the right passage first only 5% of the time for "player on a date" questions. Filtering on the parsed player and date fixes that.
- **Embeddings can't compare numbers.** "Who dropped 35+ points for the Suns?" scored 0% with vector search. Parsing stat thresholds into SQL filters raised it to 92%.
- **Keyword fusion was tested and left out.** Fusing vector rank with Postgres full-text rank (reciprocal rank fusion) lowered Recall@1 on both sets, because common words such as "points" and month names match thousands of passages. It is still available as `mode=fusion`.
- **Remaining misses** are nicknames the parser doesn't know (for example "Dame" and "Ja", deliberately left out of the alias list so the test stays honest). They still land in the top 5.

Median retrieval latency is 59 ms per question, including parsing and the query embedding. These figures used a local quantized copy of `nomic-embed-text-v1.5`; the hosted Fireworks model is the same model, so results should be close. 

End to end (`tests/eval.py`, 22 questions whose answers are checked against values computed from the database, including an aggregate question and a player who doesn't exist): **100% correct**, median latency **1.4 s**, about 2,052 input and 146 output tokens, **$0.0008 per question** with `deepseek-v4p1-flash` at Fireworks' listed $0.30 / $1.20 per million input / output tokens.

## How a question is answered

```
question ─► entity parser ─► SQL filters ─► candidate passages ─► rank by cosine similarity ─► top-k ─► LLM ─► cited answer
   │        (players, teams,   (metadata +                              ▲
   │         dates, seasons,    stat joins)                             │
   │         stat thresholds)                                           │
   └─► query embedding (nomic-embed-text-v1.5) ─────────────────────────┘
```

1. **Parse.** The question is scanned for players (full names, nicknames such as "SGA" or "Wemby", typos, or an unambiguous surname), teams (names, cities, abbreviations), dates ("4/8", "April 8, 2025", "Christmas"), seasons ("2024-25") and stat thresholds ("35+ points", "triple-double"). A date without a year matches every season it occurred in.
2. **Filter.** Those become SQL filters on the passages' metadata, joined to the box scores for stat thresholds, so a question about one player on one date searches a handful of passages instead of the whole corpus. If the filters leave nothing, they are relaxed one at a time.
3. **Rank.** Candidates are ranked by cosine similarity to the question's embedding. With no filters, the HNSW index does an approximate nearest-neighbor search over the whole corpus.
4. **Generate.** The model reads the top passages and answers only from them, citing passage ids. The API returns those ids as `evidence`.

Retrieval can't count or average across hundreds of games reliably, so "who leads the league in assists" goes to typed SQL aggregate tools (`stat_leaders`, `player_averages`, `triple_double_counts`). The model chooses between retrieval and aggregates, and it never writes SQL itself.

### Passages

```
Shai Gilgeous-Alexander (OKC, Oklahoma City Thunder) vs Los Angeles Lakers (LAL), April 8, 2025 (4/8/2025, 2025-04-08),
2024-25 season, home win 136-120: 42 points, 6 rebounds, 6 assists, 0 steals, 1 blocks, 1 turnovers, 14-26 FG, 5-9 3PT,
9-11 FT, 36 minutes, +7 plus-minus. 40-point game.
```

Each passage repeats facts in the forms people ask about them: three date formats, team names and abbreviations, and tags such as "triple-double", "Christmas Day game" or "overtime". Game passages carry the final score, the margin and each team's leading scorer.

## Observability

Every `/api/chat` response includes a `usage` block, and the same record is logged as one JSON line:

```json
{"model": "...", "llm_calls": 2, "input_tokens": 3120, "output_tokens": 96, "embed_tokens": 14,
 "latency_ms": 2841.0, "timing_ms": {"parse": 1.2, "embed": 180.4, "retrieve": 22.7, "generate": 2611.3},
 "cost_usd": 0.00041, "tools": ["search_records"]}
```

Set `MODEL_PRICE_INPUT_PER_M` and `MODEL_PRICE_OUTPUT_PER_M` to the model's prices to get `cost_usd`. `GET /api/search?q=...&mode=filtered|vector|fusion` returns retrieval results alone, without generation.

## Evaluation

| Script | Measures | Needs |
|---|---|---|
| `tests/retrieval_eval.py` | Recall@1/5/10 and MRR for three retrieval modes on a standard and a hard question set, entity-parse accuracy, retrieval latency | Database, embeddings |
| `tests/eval.py` | Answer accuracy against values computed from the database, latency, tokens and cost per request | Database, Fireworks key |
| `tests/test_parse.py` | Entity parsing unit tests | Database |

The retrieval set is built from the database with a fixed seed: questions about a player on a date, a player against a team on a date, a game's result, and a player's triple-doubles against a team. Results are written to `eval/`.

## Data

[NBA Player Game Logs](https://huggingface.co/datasets/cbratkovics/nba-game-logs) on Hugging Face, a CC0 1.0 packaging of Eoin Moore's [Kaggle dataset](https://www.kaggle.com/datasets/eoinamoore/historical-nba-data-and-player-box-scores). Regular season only, one row per player per game. The ingest script downloads it, so no data is stored in this repository. The dataset's own notes describe it as derived from NBA.com and published for non-commercial portfolio use, which is how it is used here.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, shadcn/ui structure |
| API | Python, FastAPI on Vercel Functions |
| Database | PostgreSQL with pgvector (HNSW, cosine), on Neon |
| Embeddings | `nomic-ai/nomic-embed-text-v1.5`, 768 dimensions, via Fireworks AI (or locally with fastembed) |
| Generation | Fireworks AI through its Anthropic-compatible Messages API; the model is one environment variable |

## Run it

```bash
cp .env.example .env                      # POSTGRES_URL, FIREWORKS_API_KEY
pip install -r requirements-ingest.txt

python -m backend.ingest                  # download, load, embed and index (all seasons since 2023-24)
python -m tests.retrieval_eval --set hard # retrieval metrics (also --set standard)
python -m tests.eval                      # answer accuracy, latency, tokens, cost

uvicorn backend.server:app --reload --port 8000
cd frontend && npm install && npm run dev  # http://localhost:5173, proxies /api to port 8000
```

`python -m backend.ingest --seasons 2024-25` loads one season. `EMBED_PROVIDER=local` embeds on your machine with the same model instead of calling Fireworks. Re-running ingest replaces every table.

## Deployment

The repo is linked to Vercel; pushes to `main` deploy automatically. Set `POSTGRES_URL` and `FIREWORKS_API_KEY` in the project's environment variables, and run `python -m backend.ingest` once against the database. The database needs the `vector` extension, which Neon provides.

## Author

**Obinna Amadi**
