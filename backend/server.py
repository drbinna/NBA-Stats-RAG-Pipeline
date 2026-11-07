"""
Courtside — NBA stats assistant built on retrieval-augmented generation.

Every question is answered from passages retrieved out of pgvector: one passage
per game and one per player per game, embedded with nomic-embed-text-v1.5.
Retrieval is hybrid: entity filters (players, teams, dates, seasons, stat
thresholds) narrow the passages, then vector similarity ranks them. Questions that need arithmetic over many games ("who leads
the league in assists") go to typed SQL aggregate tools instead, because
retrieving passages can't count or average reliably.

The model runs on Fireworks AI through the Anthropic-compatible Messages API,
and every response reports its token usage, latency by stage and cost.
"""
import json
import logging
import re
import time
import traceback
from datetime import date
from functools import lru_cache

import anthropic
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from backend import retrieval
from backend.config import (SA_DSN, EMBED_PRICE_PER_M, FIREWORKS_API_KEY, MODEL_ID,
                            PRICE_IN_PER_M, PRICE_OUT_PER_M)

log = logging.getLogger("courtside")
logging.basicConfig(level=logging.INFO)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

eng = sa.create_engine(SA_DSN, pool_pre_ping=True) if SA_DSN else None
llm = (anthropic.Anthropic(api_key=FIREWORKS_API_KEY, base_url="https://api.fireworks.ai/inference")
       if FIREWORKS_API_KEY else None)

MAX_TOOL_ROUNDS = 5
STATS = {"points": "pts", "rebounds": "reb", "assists": "ast", "steals": "stl", "blocks": "blk",
         "turnovers": "tov", "threes": "fg3m", "minutes": "minutes"}
TD = "((pts >= 10)::int + (reb >= 10)::int + (ast >= 10)::int + (stl >= 10)::int + (blk >= 10)::int) >= 3"


def rows(sql, params):
    with eng.connect() as cx:
        out = []
        for r in cx.execute(text(sql), params):
            out.append({k: (v.isoformat() if isinstance(v, date) else float(v) if hasattr(v, "is_finite") else v)
                        for k, v in r._mapping.items()})
        return out


@lru_cache(maxsize=1)
def db_date_range():
    if not eng:
        return None, None
    with eng.connect() as cx:
        lo, hi = cx.execute(text("SELECT MIN(game_date), MAX(game_date) FROM games")).fetchone()
    return (lo.isoformat() if lo else None, hi.isoformat() if hi else None)


# --------------------------------------------------------------------------- tools

def tool_search_records(a, ctx):
    res = retrieval.search(eng, a["query"], k=int(a.get("k") or 8))
    ctx["embed_tokens"] += res["embed_tokens"]
    for stage, ms in res["timing_ms"].items():
        ctx["timing_ms"][stage] = ctx["timing_ms"].get(stage, 0) + ms
    ctx["retrieved"] += [h["doc_id"] for h in res["hits"]]
    ctx["passages"].update({h["doc_id"]: h["content"] for h in res["hits"]})
    return {"filters_applied": res["filters"],
            "passages": [{"id": h["doc_id"], "text": h["content"]} for h in res["hits"]]}


def _range(a, params, alias="pg"):
    where = []
    if a.get("season"):
        where.append(f"{alias}.season = :season"); params["season"] = a["season"]
    if a.get("date_from"):
        where.append(f"{alias}.game_date >= :df"); params["df"] = a["date_from"]
    if a.get("date_to"):
        where.append(f"{alias}.game_date <= :dt"); params["dt"] = a["date_to"]
    if a.get("team"):
        where.append(f"{alias}.team = :team"); params["team"] = a["team"].upper()
    return where


def tool_stat_leaders(a, ctx):
    col = STATS.get(a.get("stat", "points"), "pts")
    params = {"n": min(int(a.get("n") or 10), 25), "ming": max(1, int(a.get("min_games") or 20))}
    where = _range(a, params)
    return rows(f"""SELECT p.name AS player, MAX(pg.team) AS team, COUNT(*) AS games,
                           ROUND(AVG(pg.{col})::numeric, 1) AS per_game, MAX(pg.{col}) AS best
                    FROM player_games pg JOIN players p USING (player_id)
                    {('WHERE ' + ' AND '.join(where)) if where else ''}
                    GROUP BY p.player_id, p.name HAVING COUNT(*) >= :ming
                    ORDER BY per_game DESC LIMIT :n""", params)


def tool_player_averages(a, ctx):
    found = retrieval.parse(a["player"], eng)["players"]
    if not found:
        return {"error": f"no player matching '{a['player']}'"}
    params = {"pid": found[0][0]}
    where = ["pg.player_id = :pid"] + _range(a, params)
    return rows(f"""SELECT p.name AS player, pg.season, COUNT(*) AS games,
                           ROUND(AVG(pts)::numeric, 1) AS ppg, ROUND(AVG(reb)::numeric, 1) AS rpg,
                           ROUND(AVG(ast)::numeric, 1) AS apg, MAX(pts) AS high
                    FROM player_games pg JOIN players p USING (player_id)
                    WHERE {' AND '.join(where)} GROUP BY p.name, pg.season ORDER BY pg.season""", params)


def tool_triple_double_counts(a, ctx):
    params = {"n": min(int(a.get("n") or 10), 25)}
    where = [TD] + _range(a, params)
    return rows(f"""SELECT p.name AS player, COUNT(*) AS triple_doubles
                    FROM player_games pg JOIN players p USING (player_id)
                    WHERE {' AND '.join(where)} GROUP BY p.name ORDER BY triple_doubles DESC LIMIT :n""", params)


RANGE_PROPS = {"season": {"type": "string", "description": "e.g. 2024-25"},
               "date_from": {"type": "string"}, "date_to": {"type": "string"},
               "team": {"type": "string", "description": "team abbreviation, e.g. OKC"}}
TOOLS = [
    {"name": "search_records",
     "description": "Retrieve passages about specific games and player performances (scores, box-score lines, who won, "
                    "how a player did on a date or against a team). Pass the user's question in their own words. Never add a year, "
                    "date, name or other detail they didn't give: names, teams, dates, seasons and stat thresholds in the "
                    "query become filters, so a guessed detail returns the wrong games.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "k": {"type": "integer", "default": 8}},
                      "required": ["query"]}},
    {"name": "stat_leaders",
     "description": "Players ranked by per-game average for a stat. Use for 'who leads', 'best scorer', 'most per game'.",
     "input_schema": {"type": "object", "properties": {"stat": {"type": "string", "enum": list(STATS)},
                                                       "min_games": {"type": "integer", "default": 20},
                                                       "n": {"type": "integer", "default": 10}} | RANGE_PROPS}},
    {"name": "player_averages",
     "description": "A player's per-game averages by season, with an optional date range.",
     "input_schema": {"type": "object", "properties": {"player": {"type": "string"}} | RANGE_PROPS, "required": ["player"]}},
    {"name": "triple_double_counts",
     "description": "Players ranked by number of triple-doubles.",
     "input_schema": {"type": "object", "properties": {"n": {"type": "integer", "default": 10}} | RANGE_PROPS}},
]
TOOL_FUNCS = {"search_records": tool_search_records, "stat_leaders": tool_stat_leaders,
              "player_averages": tool_player_averages, "triple_double_counts": tool_triple_double_counts}


def system_prompt() -> str:
    lo, hi = db_date_range()
    return f"""You are Courtside, an NBA statistics assistant.

Today is {date.today().isoformat()}. The database holds regular-season games from {lo} to {hi}.

Rules:
- For a specific game, date, matchup or player performance, call search_records and answer from the passages it returns.
- For rankings, averages or counts across many games, use stat_leaders, player_averages or triple_double_counts.
- Answer ONLY from tool results. Never use statistics from memory. If the results don't contain the answer, say so.
- A date without a year means its most recent occurrence in the database unless the question implies otherwise.
- Cite the passage ids you used in square brackets, e.g. [line:0022401153:1628983].
- Be concise: lead with the number or result asked for, then one line of context. Plain text, no markdown."""


def strip_markdown(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"^#{1,6}\s*", "", s, flags=re.M)
    return s.replace("`", "")


def _cost(ctx):
    embed = ctx["embed_tokens"] / 1e6 * EMBED_PRICE_PER_M
    if PRICE_IN_PER_M is None or PRICE_OUT_PER_M is None:
        return None
    return round(ctx["input_tokens"] / 1e6 * PRICE_IN_PER_M + ctx["output_tokens"] / 1e6 * PRICE_OUT_PER_M + embed, 6)


def run_agent(question: str) -> dict:
    t0 = time.perf_counter()
    ctx = {"input_tokens": 0, "output_tokens": 0, "embed_tokens": 0, "timing_ms": {}, "retrieved": [], "passages": {}, "llm_calls": 0}
    messages = [{"role": "user", "content": question}]
    calls, answer = [], None

    def call_llm(**kw):
        t = time.perf_counter()
        resp = llm.messages.create(model=MODEL_ID, system=system_prompt(), messages=messages, **kw)
        ctx["timing_ms"]["generate"] = ctx["timing_ms"].get("generate", 0) + round((time.perf_counter() - t) * 1000, 1)
        ctx["llm_calls"] += 1
        if getattr(resp, "usage", None):
            ctx["input_tokens"] += resp.usage.input_tokens or 0
            ctx["output_tokens"] += resp.usage.output_tokens or 0
        return resp

    for _ in range(MAX_TOOL_ROUNDS):
        resp = call_llm(max_tokens=2500, tools=TOOLS)
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            answer = " ".join(b.text for b in resp.content if b.type == "text").strip()
            break
        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            try:
                out = TOOL_FUNCS[block.name](block.input or {}, ctx)
            except Exception:
                log.exception("tool %s failed", block.name)
                out = {"error": f"{block.name} failed"}
            calls.append({"tool": block.name, "input": block.input})
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(out, default=str)[:12000]})
        messages.append({"role": "user", "content": results})
    if answer is None:
        messages.append({"role": "user", "content": "Stop using tools. Answer now from the results above, or say what you could not find."})
        resp = call_llm(max_tokens=400)
        answer = " ".join(b.text for b in resp.content if b.type == "text").strip()

    cited = re.findall(r"\[((?:line|game):[\w:]+)\]", answer or "")
    evidence = [{"table": "documents", "id": d} for d in dict.fromkeys(cited or ctx["retrieved"][:3])]
    sources = [{"id": e["id"], "text": ctx["passages"][e["id"]]} for e in evidence if e["id"] in ctx["passages"]]
    usage = {"model": MODEL_ID, "llm_calls": ctx["llm_calls"], "input_tokens": ctx["input_tokens"],
             "output_tokens": ctx["output_tokens"], "embed_tokens": ctx["embed_tokens"],
             "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
             "timing_ms": {k: round(v, 1) for k, v in ctx["timing_ms"].items()},
             "cost_usd": _cost(ctx), "tools": [c["tool"] for c in calls]}
    log.info("usage %s", json.dumps(usage))
    return {"answer": strip_markdown(answer or "") or "I couldn't find that in the available data.",
            "evidence": evidence, "sources": sources, "trace": calls, "usage": usage}


# --------------------------------------------------------------------------- HTTP

class Q(BaseModel):
    question: str


@app.post("/api/chat")
def chat(q: Q):
    if not eng:
        return {"answer": "The stats database isn't available right now. Please try again later.", "evidence": []}
    if not llm:
        return {"answer": "The AI service isn't configured. Please try again later.", "evidence": []}
    question = q.question.strip()[:500]
    if not question:
        return {"answer": "Ask me something about NBA games or players.", "evidence": []}
    try:
        return run_agent(question)
    except Exception:
        log.error("chat failed:\n%s", traceback.format_exc())
        return {"answer": "Something went wrong answering that. Please try again in a moment.", "evidence": []}


@app.get("/api/search")
def search(q: str, k: int = 8, mode: str = "filtered"):
    """Retrieval only, no generation. Useful for debugging what the model will see."""
    if mode not in ("filtered", "vector", "fusion"):
        mode = "filtered"
    return retrieval.search(eng, q[:500], k=max(1, min(k, 25)), mode=mode)


@app.get("/api/health")
def health():
    lo, hi = db_date_range()
    return {"status": "ok", "db_configured": eng is not None, "ai_configured": llm is not None,
            "model": MODEL_ID, "data_from": lo, "data_to": hi}
