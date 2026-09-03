"""
Courtside — NBA stats assistant.

Architecture: a tool-using agent. The model never sees a dump of the database;
it calls typed, parameterized SQL tools (plus two live-data tools) and answers
only from what they return. Runs on Fireworks AI via the Anthropic-compatible
Messages API, so the model is a config value (MODEL_ID).
"""
import json
import logging
import traceback
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Optional

import anthropic
import requests
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from backend.config import DB_DSN, BALLDONTLIE_API_KEY, FIREWORKS_API_KEY, MODEL_ID

log = logging.getLogger("courtside")
logging.basicConfig(level=logging.INFO)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

eng = sa.create_engine(DB_DSN, pool_pre_ping=True) if DB_DSN else None
llm = (
    anthropic.Anthropic(api_key=FIREWORKS_API_KEY, base_url="https://api.fireworks.ai/inference")
    if FIREWORKS_API_KEY else None
)

BALLDONTLIE_BASE_URL = "https://api.balldontlie.io/v1"
MAX_TOOL_ROUNDS = 6

# Nicknames a substring match on the players table won't catch.
ALIASES = {
    "sga": "Shai Gilgeous-Alexander", "shai": "Shai Gilgeous-Alexander",
    "chet": "Chet Holmgren", "jdub": "Jalen Williams", "j-dub": "Jalen Williams",
    "dort": "Luguentz Dort", "lu dort": "Luguentz Dort",
    "joker": "Nikola Jokic", "jokic": "Nikola Jokic",
    "bron": "LeBron James", "lebron": "LeBron James",
    "steph": "Stephen Curry", "curry": "Stephen Curry",
    "giannis": "Giannis Antetokounmpo", "luka": "Luka Doncic",
    "ant": "Anthony Edwards", "wemby": "Victor Wembanyama",
    "tatum": "Jayson Tatum", "kd": "Kevin Durant",
}

STAT_COLUMNS = {
    "points": "pbs.points", "assists": "pbs.assists",
    "rebounds": "(pbs.offensive_reb + pbs.defensive_reb)",
    "steals": "pbs.steals", "blocks": "pbs.blocks", "turnovers": "pbs.turnovers",
    "minutes": "(pbs.seconds / 60.0)",
}


# --------------------------------------------------------------------------- DB helpers

def rows_to_dicts(result) -> list:
    keys = list(result.keys())
    out = []
    for r in result.fetchall():
        d = {}
        for k, v in zip(keys, r):
            if isinstance(v, (date, datetime)):
                v = v.isoformat()
            elif v is not None and not isinstance(v, (int, float, bool, str)) and hasattr(v, "__float__"):
                v = float(v)
            d[k] = v
        out.append(d)
    return out


@lru_cache(maxsize=1)
def db_date_range():
    if not eng:
        return None, None
    with eng.connect() as cx:
        r = cx.execute(text("SELECT MIN(game_timestamp)::date, MAX(game_timestamp)::date FROM game_details")).fetchone()
    return (r[0].isoformat() if r[0] else None, r[1].isoformat() if r[1] else None)


BOX_SELECT = """
    SELECT p.player_id,
           p.first_name || ' ' || p.last_name AS player,
           t.abbreviation AS team,
           gd.game_timestamp::date AS game_date,
           CASE WHEN pbs.team_id = gd.home_team_id THEN at.abbreviation ELSE ht.abbreviation END AS opponent,
           CASE WHEN pbs.team_id = gd.home_team_id THEN 'home' ELSE 'away' END AS venue,
           pbs.points, pbs.assists,
           pbs.offensive_reb + pbs.defensive_reb AS rebounds,
           pbs.steals, pbs.blocks, pbs.turnovers,
           ROUND((pbs.seconds / 60.0)::numeric, 1) AS minutes,
           ht.abbreviation AS home_team, gd.home_points,
           at.abbreviation AS away_team, gd.away_points
    FROM player_box_scores pbs
    JOIN players p ON pbs.person_id = p.player_id
    JOIN teams t ON pbs.team_id = t.team_id
    JOIN game_details gd ON pbs.game_id = gd.game_id
    JOIN teams ht ON gd.home_team_id = ht.team_id
    JOIN teams at ON gd.away_team_id = at.team_id
"""


def tool_search_players(name: str) -> list:
    q = ALIASES.get(name.strip().lower(), name).strip().lower()
    with eng.connect() as cx:
        res = cx.execute(text("""
            SELECT p.player_id,
                   p.first_name || ' ' || p.last_name AS name,
                   (SELECT t.abbreviation
                      FROM player_box_scores b
                      JOIN teams t ON b.team_id = t.team_id
                      JOIN game_details g ON b.game_id = g.game_id
                     WHERE b.person_id = p.player_id
                     ORDER BY g.game_timestamp DESC LIMIT 1) AS latest_team,
                   COUNT(pbs.game_id) AS games_in_db
            FROM players p
            LEFT JOIN player_box_scores pbs ON pbs.person_id = p.player_id
            WHERE LOWER(p.first_name || ' ' || p.last_name) LIKE :q
               OR LOWER(p.last_name) LIKE :q
            GROUP BY p.player_id, p.first_name, p.last_name
            ORDER BY games_in_db DESC
            LIMIT 8
        """), {"q": f"%{q}%"})
        return rows_to_dicts(res)


def tool_player_game_stats(player_id: int, game_date: Optional[str] = None,
                           opponent: Optional[str] = None, limit: int = 5) -> list:
    where = ["p.player_id = :pid"]
    params = {"pid": player_id, "lim": max(1, min(int(limit or 5), 25))}
    if game_date:
        where.append("gd.game_timestamp::date = :d"); params["d"] = game_date
    if opponent:
        where.append("(ht.abbreviation = :opp OR at.abbreviation = :opp) AND t.abbreviation <> :opp")
        params["opp"] = opponent.upper()
    sql = BOX_SELECT + " WHERE " + " AND ".join(where) + " ORDER BY gd.game_timestamp DESC LIMIT :lim"
    with eng.connect() as cx:
        return rows_to_dicts(cx.execute(text(sql), params))


def tool_player_averages(player_id: int, date_from: Optional[str] = None, date_to: Optional[str] = None) -> list:
    where = ["pbs.person_id = :pid"]
    params = {"pid": player_id}
    if date_from:
        where.append("gd.game_timestamp::date >= :df"); params["df"] = date_from
    if date_to:
        where.append("gd.game_timestamp::date <= :dt"); params["dt"] = date_to
    with eng.connect() as cx:
        res = cx.execute(text(f"""
            SELECT p.first_name || ' ' || p.last_name AS player,
                   COUNT(*) AS games,
                   ROUND(AVG(pbs.points)::numeric, 1) AS ppg,
                   ROUND(AVG(pbs.assists)::numeric, 1) AS apg,
                   ROUND(AVG(pbs.offensive_reb + pbs.defensive_reb)::numeric, 1) AS rpg,
                   ROUND(AVG(pbs.steals)::numeric, 1) AS spg,
                   ROUND(AVG(pbs.blocks)::numeric, 1) AS bpg,
                   MAX(pbs.points) AS high_points,
                   MIN(gd.game_timestamp)::date AS first_game,
                   MAX(gd.game_timestamp)::date AS last_game
            FROM player_box_scores pbs
            JOIN players p ON pbs.person_id = p.player_id
            JOIN game_details gd ON pbs.game_id = gd.game_id
            WHERE {' AND '.join(where)}
            GROUP BY p.player_id, p.first_name, p.last_name
        """), params)
        return rows_to_dicts(res)


def tool_top_performances(stat="points", n=10, date_from=None, date_to=None, team=None, triple_double=False) -> list:
    col = STAT_COLUMNS.get(stat, STAT_COLUMNS["points"])
    where, params = [], {"lim": max(1, min(int(n or 10), 50))}
    if date_from:
        where.append("gd.game_timestamp::date >= :df"); params["df"] = date_from
    if date_to:
        where.append("gd.game_timestamp::date <= :dt"); params["dt"] = date_to
    if team:
        where.append("t.abbreviation = :team"); params["team"] = team.upper()
    if triple_double:
        where.append("""(
            (CASE WHEN pbs.points >= 10 THEN 1 ELSE 0 END) +
            (CASE WHEN pbs.assists >= 10 THEN 1 ELSE 0 END) +
            (CASE WHEN pbs.offensive_reb + pbs.defensive_reb >= 10 THEN 1 ELSE 0 END) +
            (CASE WHEN pbs.steals >= 10 THEN 1 ELSE 0 END) +
            (CASE WHEN pbs.blocks >= 10 THEN 1 ELSE 0 END)) >= 3""")
    sql = BOX_SELECT + (" WHERE " + " AND ".join(where) if where else "") + \
        f" ORDER BY {col} DESC, gd.game_timestamp DESC LIMIT :lim"
    with eng.connect() as cx:
        return rows_to_dicts(cx.execute(text(sql), params))


def tool_game_results(team=None, game_date=None, date_from=None, date_to=None, n=10) -> list:
    where, params = [], {"lim": max(1, min(int(n or 10), 50))}
    if team:
        where.append("(ht.abbreviation = :team OR at.abbreviation = :team)"); params["team"] = team.upper()
    if game_date:
        where.append("gd.game_timestamp::date = :d"); params["d"] = game_date
    if date_from:
        where.append("gd.game_timestamp::date >= :df"); params["df"] = date_from
    if date_to:
        where.append("gd.game_timestamp::date <= :dt"); params["dt"] = date_to
    sql = f"""
        SELECT gd.game_id, gd.game_timestamp::date AS game_date,
               ht.abbreviation AS home_team, gd.home_points,
               at.abbreviation AS away_team, gd.away_points,
               CASE WHEN gd.home_points > gd.away_points THEN ht.abbreviation ELSE at.abbreviation END AS winner
        FROM game_details gd
        JOIN teams ht ON gd.home_team_id = ht.team_id
        JOIN teams at ON gd.away_team_id = at.team_id
        {('WHERE ' + ' AND '.join(where)) if where else ''}
        ORDER BY gd.game_timestamp DESC LIMIT :lim
    """
    with eng.connect() as cx:
        return rows_to_dicts(cx.execute(text(sql), params))


def tool_list_teams() -> list:
    with eng.connect() as cx:
        return rows_to_dicts(cx.execute(text("SELECT abbreviation, city, name FROM teams ORDER BY abbreviation")))


# --------------------------------------------------------------------------- live data

class LiveDataUnavailable(Exception):
    pass


def _bdl(path: str, params: dict) -> list:
    if not BALLDONTLIE_API_KEY:
        raise LiveDataUnavailable("live data is not configured")
    r = requests.get(f"{BALLDONTLIE_BASE_URL}/{path}", headers={"Authorization": BALLDONTLIE_API_KEY},
                     params=params, timeout=10)
    r.raise_for_status()
    return r.json().get("data", [])


def tool_live_games(game_date=None, days_back=0) -> list:
    end = datetime.strptime(game_date, "%Y-%m-%d").date() if game_date else date.today()
    out = []
    for i in range(max(0, min(int(days_back or 0), 14)) + 1):
        d = (end - timedelta(days=i)).isoformat()
        for g in _bdl("games", {"dates[]": d}):
            out.append({
                "date": g.get("date"), "status": g.get("status"),
                "home_team": g.get("home_team", {}).get("abbreviation"), "home_score": g.get("home_team_score"),
                "visitor_team": g.get("visitor_team", {}).get("abbreviation"), "visitor_score": g.get("visitor_team_score"),
            })
    return out


def tool_live_player_season_averages(name: str, season=None) -> dict:
    name = ALIASES.get(name.strip().lower(), name)
    players = _bdl("players", {"search": name.split()[-1], "per_page": 5})
    if not players:
        return {"error": "player not found in live API"}
    p = players[0]
    if not season:
        now = date.today()
        season = now.year if now.month >= 10 else now.year - 1
    avg = _bdl("season_averages", {"season": season, "player_ids[]": p["id"]})
    return {"player": f"{p['first_name']} {p['last_name']}", "team": (p.get("team") or {}).get("abbreviation"),
            "season": season, "averages": avg[0] if avg else None}


# --------------------------------------------------------------------------- tool registry

TOOLS = [
    {"name": "search_players",
     "description": "Resolve a player name or nickname (e.g. 'SGA', 'Chet', 'Jokic') to a player_id. Always call this before any player stat tool.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "player_game_stats",
     "description": "Box score lines for one player from the historical database. Filter by exact game_date (YYYY-MM-DD) and/or opponent team abbreviation; otherwise returns the most recent games.",
     "input_schema": {"type": "object", "properties": {
         "player_id": {"type": "integer"}, "game_date": {"type": "string"}, "opponent": {"type": "string"},
         "limit": {"type": "integer", "default": 5}}, "required": ["player_id"]}},
    {"name": "player_averages",
     "description": "Per-game averages and highs for a player over an optional date range (historical database).",
     "input_schema": {"type": "object", "properties": {
         "player_id": {"type": "integer"}, "date_from": {"type": "string"}, "date_to": {"type": "string"}},
         "required": ["player_id"]}},
    {"name": "top_performances",
     "description": "Highest single-game performances for a stat. Set triple_double=true to list triple-doubles. Optional date range and team filter.",
     "input_schema": {"type": "object", "properties": {
         "stat": {"type": "string", "enum": list(STAT_COLUMNS.keys())}, "n": {"type": "integer", "default": 10},
         "date_from": {"type": "string"}, "date_to": {"type": "string"}, "team": {"type": "string"},
         "triple_double": {"type": "boolean", "default": False}}}},
    {"name": "game_results",
     "description": "Final scores from the historical database, filtered by team abbreviation, exact date, or date range. Use for 'who won', 'what games happened on', and schedules within the database range.",
     "input_schema": {"type": "object", "properties": {
         "team": {"type": "string"}, "game_date": {"type": "string"}, "date_from": {"type": "string"},
         "date_to": {"type": "string"}, "n": {"type": "integer", "default": 10}}}},
    {"name": "list_teams",
     "description": "All team abbreviations with city and name. Use when unsure of an abbreviation.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "live_games",
     "description": "Live/recent scores from the balldontlie API. Use ONLY for dates after the historical database ends. game_date defaults to today; days_back looks further back.",
     "input_schema": {"type": "object", "properties": {
         "game_date": {"type": "string"}, "days_back": {"type": "integer", "default": 0}}}},
    {"name": "live_player_season_averages",
     "description": "Current-season averages for a player from the live API. Use for seasons after the historical database ends.",
     "input_schema": {"type": "object", "properties": {
         "name": {"type": "string"}, "season": {"type": "integer"}}, "required": ["name"]}},
]

TOOL_FUNCS = {
    "search_players": lambda a: tool_search_players(a["name"]),
    "player_game_stats": lambda a: tool_player_game_stats(a["player_id"], a.get("game_date"), a.get("opponent"), a.get("limit", 5)),
    "player_averages": lambda a: tool_player_averages(a["player_id"], a.get("date_from"), a.get("date_to")),
    "top_performances": lambda a: tool_top_performances(a.get("stat", "points"), a.get("n", 10), a.get("date_from"), a.get("date_to"), a.get("team"), a.get("triple_double", False)),
    "game_results": lambda a: tool_game_results(a.get("team"), a.get("game_date"), a.get("date_from"), a.get("date_to"), a.get("n", 10)),
    "list_teams": lambda a: tool_list_teams(),
    "live_games": lambda a: tool_live_games(a.get("game_date"), a.get("days_back", 0)),
    "live_player_season_averages": lambda a: tool_live_player_season_averages(a["name"], a.get("season")),
}


def system_prompt() -> str:
    lo, hi = db_date_range()
    return f"""You are Courtside, an NBA statistics assistant with a focus on the Oklahoma City Thunder.

Today is {date.today().isoformat()}.
The historical database covers games from {lo or 'unknown'} to {hi or 'unknown'}. For anything after {hi or 'that range'}, use the live_* tools.

Rules:
- Always resolve a player with search_players before calling a player stat tool. If several match, prefer the one with the most games_in_db unless the question implies otherwise.
- Answer ONLY from tool results. Never estimate or recall statistics from memory.
- If a tool returns no data or an error, stop and tell the user. Do not retry the same lookup through other tools.
- A date without a year refers to the most recent season in the database unless it falls after the database ends, in which case use live data.
- Be concise: lead with the number asked for, then one line of context (opponent, result). Plain text, no markdown tables."""


# --------------------------------------------------------------------------- agent loop

def run_agent(question: str) -> dict:
    messages = [{"role": "user", "content": question}]
    calls = []
    for _ in range(MAX_TOOL_ROUNDS):
        resp = llm.messages.create(model=MODEL_ID, max_tokens=800, system=system_prompt(), tools=TOOLS, messages=messages)
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            answer = " ".join(b.text for b in resp.content if b.type == "text").strip()
            return {"answer": answer or "I couldn't produce an answer for that.", "evidence": calls}
        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            try:
                out = TOOL_FUNCS[block.name](block.input or {})
            except LiveDataUnavailable:
                out = {"error": "Live data is unavailable right now. Tell the user this date is outside the historical database and live scores are not available."}
            except Exception:
                log.exception("tool %s failed", block.name)
                out = {"error": f"{block.name} failed; try a different query"}
            calls.append({"tool": block.name, "input": block.input})
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(out, default=str)[:12000]})
        messages.append({"role": "user", "content": results})
    # Round limit hit: force a final answer from whatever was gathered.
    messages.append({"role": "user", "content": "Stop using tools. Answer now from the results above, or say what you could not find."})
    resp = llm.messages.create(model=MODEL_ID, max_tokens=400, system=system_prompt(), messages=messages)
    answer = " ".join(b.text for b in resp.content if b.type == "text").strip()
    return {"answer": answer or "I couldn't find that in the available data.", "evidence": calls}


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


@app.get("/api/health")
def health():
    return {"status": "ok", "db_configured": eng is not None, "ai_configured": llm is not None, "model": MODEL_ID}
