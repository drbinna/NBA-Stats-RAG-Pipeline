from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlalchemy as sa
from sqlalchemy import text
from backend.config import DB_DSN, BALLDONTLIE_API_KEY
import anthropic
import os
import json
import requests
from datetime import datetime, timedelta

app = FastAPI()

# Balldontlie API configuration
BALLDONTLIE_BASE_URL = "https://api.balldontlie.io/v1"
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
eng = sa.create_engine(DB_DSN)

# Initialize Claude client
claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def get_balldontlie_headers():
    """Get headers for balldontlie API requests."""
    return {"Authorization": BALLDONTLIE_API_KEY}


def fetch_live_games(date_str: str = None) -> list:
    """Fetch games from balldontlie API for a specific date."""
    if not BALLDONTLIE_API_KEY:
        return []
    try:
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        url = f"{BALLDONTLIE_BASE_URL}/games"
        params = {"dates[]": date_str}
        resp = requests.get(url, headers=get_balldontlie_headers(), params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception as e:
        print(f"Error fetching games: {e}")
        return []


def fetch_recent_games(days: int = 7) -> list:
    """Fetch games from the last N days."""
    all_games = []
    for i in range(days):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        games = fetch_live_games(date)
        all_games.extend(games)
    return all_games


def fetch_player_stats(player_id: int, season: int = None) -> dict:
    """Fetch season averages for a player."""
    if not BALLDONTLIE_API_KEY:
        return {}
    try:
        if not season:
            season = datetime.now().year if datetime.now().month > 9 else datetime.now().year - 1
        url = f"{BALLDONTLIE_BASE_URL}/season_averages"
        params = {"season": season, "player_ids[]": player_id}
        resp = requests.get(url, headers=get_balldontlie_headers(), params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return data[0] if data else {}
    except Exception as e:
        print(f"Error fetching player stats: {e}")
        return {}


def search_players(query: str) -> list:
    """Search for players by name."""
    if not BALLDONTLIE_API_KEY:
        return []
    try:
        url = f"{BALLDONTLIE_BASE_URL}/players"
        params = {"search": query, "per_page": 10}
        resp = requests.get(url, headers=get_balldontlie_headers(), params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception as e:
        print(f"Error searching players: {e}")
        return []


def fetch_box_scores(game_id: int) -> list:
    """Fetch box score stats for a game."""
    if not BALLDONTLIE_API_KEY:
        return []
    try:
        url = f"{BALLDONTLIE_BASE_URL}/stats"
        params = {"game_ids[]": game_id, "per_page": 50}
        resp = requests.get(url, headers=get_balldontlie_headers(), params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception as e:
        print(f"Error fetching box scores: {e}")
        return []


def query_player_game_from_db(player_search: str, date_str: str) -> str:
    """Query our local database for a player's game stats on a specific date."""
    try:
        with eng.connect() as cx:
            # Search for player by name (partial match)
            result = cx.execute(text("""
                SELECT p.first_name || ' ' || p.last_name as player_name,
                       t.abbreviation as team,
                       pbs.points,
                       pbs.assists,
                       pbs.offensive_reb + pbs.defensive_reb as rebounds,
                       pbs.steals,
                       pbs.blocks,
                       pbs.turnovers,
                       ROUND((pbs.seconds / 60.0)::numeric, 1) as minutes,
                       gd.game_timestamp::date as game_date,
                       ht.abbreviation as home_team,
                       at.abbreviation as away_team,
                       gd.home_points,
                       gd.away_points
                FROM player_box_scores pbs
                JOIN players p ON pbs.person_id = p.player_id
                JOIN teams t ON pbs.team_id = t.team_id
                JOIN game_details gd ON pbs.game_id = gd.game_id
                JOIN teams ht ON gd.home_team_id = ht.team_id
                JOIN teams at ON gd.away_team_id = at.team_id
                WHERE (LOWER(p.first_name) LIKE :search
                       OR LOWER(p.last_name) LIKE :search
                       OR LOWER(p.first_name || ' ' || p.last_name) LIKE :search)
                  AND gd.game_timestamp::date = :game_date
            """), {"search": f"%{player_search.lower()}%", "game_date": date_str}).fetchall()

            if result:
                lines = []
                for r in result:
                    lines.append(
                        f"DATABASE STATS - {r[0]} ({r[1]}) on {r[9]}:\n"
                        f"  Points: {r[2]}, Rebounds: {r[4]}, Assists: {r[3]}, "
                        f"Steals: {r[5]}, Blocks: {r[6]}, Turnovers: {r[7]}, Minutes: {r[8]}\n"
                        f"  Game: {r[11]} ({r[13]}) @ {r[10]} ({r[12]})"
                    )
                return "\n".join(lines)
    except Exception as e:
        print(f"Error querying player game from DB: {e}")
    return ""


def parse_date_from_question(question: str) -> str:
    """Try to parse a date from the question."""
    import re
    ql = question.lower()

    # Match patterns like 4/9, 04/09, 4-9, etc.
    date_patterns = [
        r'(\d{1,2})[/-](\d{1,2})',  # 4/9, 04/09, 4-9
        r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})',  # 4/9/24, 04/09/2024
    ]

    for pattern in date_patterns:
        match = re.search(pattern, question)
        if match:
            groups = match.groups()
            month = int(groups[0])
            day = int(groups[1])
            if len(groups) == 3:
                year = int(groups[2])
                if year < 100:
                    year += 2000
            else:
                # Assume current season
                year = datetime.now().year if datetime.now().month > 9 else datetime.now().year
                # If month is later in year, might be previous year
                if month > datetime.now().month:
                    year -= 1

            return f"{year}-{month:02d}-{day:02d}"

    return None


def get_live_data_context(question: str) -> str:
    """Fetch live data from balldontlie based on the question."""
    ql = question.lower()
    results = []

    # Check for specific player + date questions
    date_str = parse_date_from_question(question)
    if date_str:
        # Common player name mappings
        player_aliases = {
            'sga': 'Gilgeous-Alexander',
            'lebron': 'LeBron',
            'curry': 'Curry',
            'steph': 'Curry',
            'durant': 'Durant',
            'kd': 'Durant',
            'giannis': 'Antetokounmpo',
            'jokic': 'Jokic',
            'luka': 'Doncic',
            'tatum': 'Tatum',
            'embiid': 'Embiid',
            'ant': 'Edwards',
            'edwards': 'Edwards',
            'morant': 'Morant',
            'ja': 'Morant',
        }

        for alias, name in player_aliases.items():
            if alias in ql:
                # Query our local database for player stats on that date
                db_stats = query_player_game_from_db(name, date_str)
                if db_stats:
                    results.append(db_stats)
                break

    # Check for today/recent/current game questions
    if any(word in ql for word in ['today', 'tonight', 'last night', 'yesterday', 'recent', 'latest', 'current']):
        # Fetch recent games
        games = fetch_recent_games(days=3)
        if games:
            game_lines = []
            for g in games[:15]:  # Limit to 15 games
                home = g.get('home_team', {})
                away = g.get('visitor_team', {})
                game_lines.append(
                    f"- {g.get('date', 'N/A')[:10]}: {away.get('full_name', 'N/A')} ({g.get('visitor_team_score', 0)}) @ "
                    f"{home.get('full_name', 'N/A')} ({g.get('home_team_score', 0)}) - Status: {g.get('status', 'N/A')}"
                )
            results.append("LIVE/RECENT GAMES:\n" + "\n".join(game_lines))

    # Check for specific player mentions - search for player and get stats
    player_keywords = ['lebron', 'curry', 'durant', 'giannis', 'jokic', 'luka', 'tatum', 'embiid', 'morant', 'edwards']
    for player in player_keywords:
        if player in ql:
            players = search_players(player)
            if players:
                p = players[0]
                stats = fetch_player_stats(p['id'])
                if stats:
                    results.append(
                        f"LIVE STATS - {p.get('first_name', '')} {p.get('last_name', '')} ({p.get('team', {}).get('abbreviation', 'N/A')}):\n"
                        f"  Games: {stats.get('games_played', 0)}, PPG: {stats.get('pts', 0)}, "
                        f"RPG: {stats.get('reb', 0)}, APG: {stats.get('ast', 0)}, "
                        f"FG%: {stats.get('fg_pct', 0)*100:.1f}%, 3P%: {stats.get('fg3_pct', 0)*100:.1f}%"
                    )
                break

    return "\n\n".join(results) if results else ""


class Q(BaseModel):
    question: str


def get_database_context(cx) -> str:
    """Get a summary of available data for Claude's context."""
    # Get sample data to help Claude understand the schema
    teams = cx.execute(text("SELECT abbreviation, city, name FROM teams LIMIT 10")).fetchall()

    # Get date range
    date_range = cx.execute(text("""
        SELECT MIN(game_timestamp)::date as min_date,
               MAX(game_timestamp)::date as max_date,
               COUNT(*) as game_count
        FROM game_details
    """)).fetchone()

    # Get sample players
    players = cx.execute(text("""
        SELECT DISTINCT p.first_name || ' ' || p.last_name as name
        FROM players p
        JOIN player_box_scores pbs ON p.player_id = pbs.person_id
        ORDER BY name
        LIMIT 20
    """)).fetchall()

    return f"""
NBA Database Context:
- Games from {date_range[0]} to {date_range[1]} ({date_range[2]} games)
- Teams: {', '.join([f"{t[0]} ({t[1]} {t[2]})" for t in teams])}...
- Sample players: {', '.join([p[0] for p in players])}...

Tables:
- game_details: game_id, game_timestamp, home_team_id, away_team_id, home_points, away_points, season
- player_box_scores: game_id, person_id, team_id, points, assists, offensive_reb, defensive_reb, steals, blocks, turnovers, minutes
- players: player_id, first_name, last_name, draft_year
- teams: team_id, abbreviation, city, name
"""


def query_relevant_data(cx, question: str) -> str:
    """Query database for data relevant to the question."""
    ql = question.lower()
    results = []

    # Check for specific player mentions
    if any(word in ql for word in ['player', 'score', 'points', 'triple', 'double', 'debut']):
        # Get recent high-scoring games
        data = cx.execute(text("""
            SELECT p.first_name || ' ' || p.last_name as player,
                   t.abbreviation as team,
                   pbs.points,
                   pbs.assists,
                   pbs.offensive_reb + pbs.defensive_reb as rebounds,
                   gd.game_timestamp::date as game_date
            FROM player_box_scores pbs
            JOIN players p ON pbs.person_id = p.player_id
            JOIN teams t ON pbs.team_id = t.team_id
            JOIN game_details gd ON pbs.game_id = gd.game_id
            ORDER BY pbs.points DESC
            LIMIT 50
        """)).fetchall()
        results.append("Top scoring performances:\n" + "\n".join([
            f"- {r[0]} ({r[1]}): {r[2]} pts, {r[3]} ast, {r[4]} reb on {r[5]}"
            for r in data
        ]))

    # Check for game/team questions
    if any(word in ql for word in ['game', 'team', 'vs', 'versus', 'play', 'won', 'lost']):
        data = cx.execute(text("""
            SELECT ht.abbreviation as home_team,
                   at.abbreviation as away_team,
                   gd.home_points,
                   gd.away_points,
                   gd.game_timestamp::date as game_date
            FROM game_details gd
            JOIN teams ht ON gd.home_team_id = ht.team_id
            JOIN teams at ON gd.away_team_id = at.team_id
            ORDER BY gd.game_timestamp DESC
            LIMIT 30
        """)).fetchall()
        results.append("Recent games:\n" + "\n".join([
            f"- {r[4]}: {r[0]} {r[2]} vs {r[1]} {r[3]}"
            for r in data
        ]))

    # Check for Christmas games
    if 'christmas' in ql:
        data = cx.execute(text("""
            SELECT ht.name as home_team,
                   at.name as away_team,
                   gd.home_points,
                   gd.away_points,
                   gd.game_timestamp::date as game_date
            FROM game_details gd
            JOIN teams ht ON gd.home_team_id = ht.team_id
            JOIN teams at ON gd.away_team_id = at.team_id
            WHERE EXTRACT(MONTH FROM gd.game_timestamp) = 12
              AND EXTRACT(DAY FROM gd.game_timestamp) = 25
        """)).fetchall()
        if data:
            results.append("Christmas Day games:\n" + "\n".join([
                f"- {r[4]}: {r[0]} {r[2]} vs {r[1]} {r[3]}"
                for r in data
            ]))

    # Check for triple-doubles
    if 'triple' in ql and 'double' in ql:
        data = cx.execute(text("""
            SELECT p.first_name || ' ' || p.last_name as player,
                   t.abbreviation as team,
                   pbs.points,
                   pbs.assists,
                   pbs.offensive_reb + pbs.defensive_reb as rebounds,
                   pbs.steals,
                   pbs.blocks,
                   gd.game_timestamp::date as game_date
            FROM player_box_scores pbs
            JOIN players p ON pbs.person_id = p.player_id
            JOIN teams t ON pbs.team_id = t.team_id
            JOIN game_details gd ON pbs.game_id = gd.game_id
            WHERE pbs.points >= 10
              AND pbs.assists >= 10
              AND (pbs.offensive_reb + pbs.defensive_reb) >= 10
            ORDER BY gd.game_timestamp DESC
        """)).fetchall()
        if data:
            results.append("Triple-doubles:\n" + "\n".join([
                f"- {r[0]} ({r[1]}): {r[2]} pts, {r[3]} ast, {r[4]} reb on {r[7]}"
                for r in data
            ]))

    return "\n\n".join(results) if results else "No specific data found for this query."


@app.post("/api/chat")
def answer(q: Q):
    """Answer question using Claude with database context and live data."""
    try:
        print(f'Received question: {q.question}')

        with eng.connect() as cx:
            # Get database context and relevant data
            db_context = get_database_context(cx)
            relevant_data = query_relevant_data(cx, q.question)

        # Get live data from balldontlie API
        live_data = get_live_data_context(q.question)

        # Build the context
        context_parts = [db_context, f"Historical Data:\n{relevant_data}"]
        if live_data:
            context_parts.append(f"Live/Current Data (from balldontlie API):\n{live_data}")

        full_context = "\n\n".join(context_parts)

        # Ask Claude
        message = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": f"""You are an NBA statistics assistant. Answer the following question using the data provided.

{full_context}

Question: {q.question}

Provide a clear, concise answer. Prioritize live/current data when answering questions about recent or current events. Use historical data for past seasons and records. If the data doesn't contain enough information, say so."""
                }
            ]
        )

        answer_text = message.content[0].text

        return {
            "answer": answer_text,
            "evidence": [],
            "used_live_data": bool(live_data)
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f'Error in /api/chat: {str(e)}')
        return {
            "answer": f"Error processing question: {str(e)}",
            "evidence": []
        }


@app.get("/api/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/debug")
def debug():
    """Debug endpoint to test database connection."""
    import re
    # Mask password in DSN for display
    masked_dsn = re.sub(r':([^:@]+)@', ':***@', DB_DSN)
    try:
        with eng.connect() as cx:
            result = cx.execute(text("SELECT COUNT(*) FROM teams")).scalar()
            return {"db_dsn": masked_dsn, "db_status": "connected", "teams_count": result}
    except Exception as e:
        return {"db_dsn": masked_dsn, "db_status": "error", "error": str(e)}
