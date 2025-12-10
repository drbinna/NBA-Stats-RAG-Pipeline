"""
rag.py - RAG pipeline for NBA stats Q&A

This script:
1. Parses questions to extract filters (dates, teams, players)
2. Uses hybrid search (SQL filters + vector similarity)
3. Retrieves relevant context from game_details and player_box_scores
4. Uses LLM to generate grounded answers
5. Outputs JSON matching the required format
"""

import json
import re
import os
import sqlalchemy as sa
from sqlalchemy import text
from backend.config import DB_DSN, EMBED_MODEL, LLM_MODEL
from backend.utils import ollama_embed, ollama_chat


BASE_DIR = os.path.dirname(__file__)
QUESTIONS_PATH = os.path.normpath(os.path.join(BASE_DIR, "..", "part1", "questions.json"))
ANSWERS_PATH = os.path.normpath(os.path.join(BASE_DIR, "..", "part1", "answers.json"))
QUERY_EMBEDDINGS_CACHE = os.path.normpath(os.path.join(BASE_DIR, "..", "part1", "query_embeddings_cache.json"))


# =============================================================================
# DATE PARSING
# =============================================================================

MONTH_MAP = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
}


def parse_date(question):
    """Extract date from question in various formats"""
    question_lower = question.lower()
    
    # Pattern: "October 27, 2023" or "December 25, 2023"
    match = re.search(r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2}),?\s+(\d{4})', question_lower)
    if match:
        month = MONTH_MAP[match.group(1)]
        day = int(match.group(2))
        year = int(match.group(3))
        return f"{year}-{month:02d}-{day:02d}"
    
    # Pattern: "1-26-24" or "1/26/24"
    match = re.search(r'(\d{1,2})[-/](\d{1,2})[-/](\d{2})(?!\d)', question)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        year = int(match.group(3))
        year = 2000 + year if year < 50 else 1900 + year
        return f"{year}-{month:02d}-{day:02d}"
    
    # Pattern: "2/1/2025"
    match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', question)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        year = int(match.group(3))
        return f"{year}-{month:02d}-{day:02d}"
    
    # Pattern: "4/9" (month/day without year - infer from season or use 2024)
    match = re.search(r'(\d{1,2})/(\d{1,2})(?!\d)', question)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        # If season is mentioned, use that year; otherwise default to 2024
        season_match = re.search(r'(\d{4})(?:-\d{2})?\s*(?:nba\s*)?season', question_lower)
        if season_match:
            season_year = int(season_match.group(1))
            # NBA season spans two years - April is in the second year
            return f"{season_year + 1}-{month:02d}-{day:02d}"
        # Default to 2024 if no season specified
        return f"2024-{month:02d}-{day:02d}"
    
    return None


def parse_season(question):
    """Extract season year from question"""
    question_lower = question.lower()
    
    # Pattern: "2023 NBA Season" or "2023-24 season"
    match = re.search(r'(\d{4})(?:-\d{2})?\s*(?:nba\s*)?season', question_lower)
    if match:
        return int(match.group(1))
    
    return None


# =============================================================================
# TEAM PARSING
# =============================================================================

TEAM_ALIASES = {
    'warriors': 'GSW', 'golden state': 'GSW', 'gsw': 'GSW',
    'kings': 'SAC', 'sacramento': 'SAC', 'sac': 'SAC',
    'lakers': 'LAL', 'los angeles lakers': 'LAL', 'la lakers': 'LAL', 'lal': 'LAL',
    'celtics': 'BOS', 'boston': 'BOS', 'bos': 'BOS',
    'nuggets': 'DEN', 'denver': 'DEN', 'den': 'DEN',
    'thunder': 'OKC', 'oklahoma city': 'OKC', 'okc': 'OKC',
    'timberwolves': 'MIN', 'minnesota': 'MIN', 'min': 'MIN', 'wolves': 'MIN',
    'mavericks': 'DAL', 'dallas': 'DAL', 'dal': 'DAL', 'mavs': 'DAL',
    'hawks': 'ATL', 'atlanta': 'ATL', 'atl': 'ATL',
    'jazz': 'UTA', 'utah': 'UTA', 'uta': 'UTA',
    'spurs': 'SAS', 'san antonio': 'SAS', 'sas': 'SAS',
    'rockets': 'HOU', 'houston': 'HOU', 'hou': 'HOU',
    'clippers': 'LAC', 'la clippers': 'LAC', 'lac': 'LAC',
    'suns': 'PHX', 'phoenix': 'PHX', 'phx': 'PHX',
    'blazers': 'POR', 'portland': 'POR', 'por': 'POR', 'trail blazers': 'POR',
    'grizzlies': 'MEM', 'memphis': 'MEM', 'mem': 'MEM',
    'pelicans': 'NOP', 'new orleans': 'NOP', 'nop': 'NOP',
    'heat': 'MIA', 'miami': 'MIA', 'mia': 'MIA',
    'bulls': 'CHI', 'chicago': 'CHI', 'chi': 'CHI',
    'cavaliers': 'CLE', 'cleveland': 'CLE', 'cle': 'CLE', 'cavs': 'CLE',
    'pistons': 'DET', 'detroit': 'DET', 'det': 'DET',
    'pacers': 'IND', 'indiana': 'IND', 'ind': 'IND',
    'bucks': 'MIL', 'milwaukee': 'MIL', 'mil': 'MIL',
    'knicks': 'NYK', 'new york': 'NYK', 'nyk': 'NYK',
    'nets': 'BKN', 'brooklyn': 'BKN', 'bkn': 'BKN',
    '76ers': 'PHI', 'sixers': 'PHI', 'philadelphia': 'PHI', 'phi': 'PHI',
    'raptors': 'TOR', 'toronto': 'TOR', 'tor': 'TOR',
    'wizards': 'WAS', 'washington': 'WAS', 'was': 'WAS',
    'hornets': 'CHA', 'charlotte': 'CHA', 'cha': 'CHA',
    'magic': 'ORL', 'orlando': 'ORL', 'orl': 'ORL',
}


def parse_teams(question):
    """Extract team abbreviations from question in order they appear"""
    question_lower = question.lower()
    team_positions = []
    
    # Find all team mentions with their positions
    for alias, abbr in TEAM_ALIASES.items():
        pos = question_lower.find(alias)
        if pos != -1 and abbr not in [t[1] for t in team_positions]:
            team_positions.append((pos, abbr, alias))
    
    # Sort by position (order of appearance)
    team_positions.sort(key=lambda x: x[0])
    
    # Return abbreviations in order, max 2
    return [t[1] for t in team_positions[:2]]


# =============================================================================
# SPECIAL EVENT PARSING
# =============================================================================

def parse_special_event(question):
    """Detect special game events"""
    question_lower = question.lower()
    
    if 'christmas' in question_lower:
        return 'christmas'
    if "new year" in question_lower or 'nye' in question_lower:
        return 'nye'
    if 'debut' in question_lower:
        return 'debut'
    
    return None


# =============================================================================
# PLAYER PARSING
# =============================================================================

PLAYER_ALIASES = {
    'lebron': 'LeBron James',
    'lebron james': 'LeBron James',
    'luka': 'Luka Doncic',
    'luka doncic': 'Luka Doncic',
    'luka dončić': 'Luka Doncic',
    'dončić': 'Luka Doncic',
    'doncic': 'Luka Doncic',
    'wembanyama': 'Victor Wembanyama',
    'victor wembanyama': 'Victor Wembanyama',
    'wemby': 'Victor Wembanyama',
    'jokic': 'Nikola Jokic',
    'nikola jokic': 'Nikola Jokic',
    'jokić': 'Nikola Jokic',
    'curry': 'Stephen Curry',
    'steph curry': 'Stephen Curry',
    'stephen curry': 'Stephen Curry',
    'giannis': 'Giannis Antetokounmpo',
    'anthony davis': 'Anthony Davis',
    'ad': 'Anthony Davis',
    'sga': 'Shai Gilgeous-Alexander',
    'shai': 'Shai Gilgeous-Alexander',
    'gilgeous-alexander': 'Shai Gilgeous-Alexander',
}

# Global cache for database player names (lazy-loaded)
_PLAYER_DB_CACHE = None


def _load_player_database(cx):
    """Load all player names from database and create searchable index"""
    global _PLAYER_DB_CACHE
    
    if _PLAYER_DB_CACHE is not None:
        return _PLAYER_DB_CACHE
    
    # Query all players
    sql = """
        SELECT 
            player_id,
            first_name || ' ' || last_name as full_name,
            first_name,
            last_name,
            LOWER(first_name || ' ' || last_name) as full_name_lower,
            LOWER(first_name) as first_name_lower,
            LOWER(last_name) as last_name_lower
        FROM players
        ORDER BY player_id
    """
    
    results = cx.execute(text(sql))
    players = results.fetchall()
    
    # Build searchable index: lowercase variations -> full name
    index = {}
    for player_id, full_name, first_name, last_name, full_lower, first_lower, last_lower in players:
        # Full name variations
        index[full_lower] = full_name
        index[first_lower + ' ' + last_lower] = full_name
        
        # First name only (if unique enough)
        if len(first_name) > 3:
            index[first_lower] = full_name
        
        # Last name only
        index[last_lower] = full_name
        
        # Common nickname patterns
        if first_name and last_name:
            # First initial + last name (e.g., "L Doncic")
            if len(first_name) > 0:
                index[f"{first_name[0].lower()} {last_lower}"] = full_name
    
    _PLAYER_DB_CACHE = index
    return index


def parse_player(question, cx=None):
    """Extract player name from question using hardcoded aliases + database lookup"""
    question_lower = question.lower()
    
    # Step 1: Try hardcoded aliases first (fast path for common players)
    sorted_aliases = sorted(PLAYER_ALIASES.keys(), key=len, reverse=True)
    
    for alias in sorted_aliases:
        # Use word boundaries to avoid false matches (e.g., "had" matching "ad")
        if len(alias) <= 2:
            pattern = r'\b' + re.escape(alias) + r'\b'
        else:
            pattern = re.escape(alias)
        
        if re.search(pattern, question_lower):
            return PLAYER_ALIASES[alias]
    
    # Step 2: Database lookup fallback (if connection provided)
    if cx is not None:
        try:
            player_index = _load_player_database(cx)
            
            # Get team names/abbreviations to avoid false matches
            team_names_lower = {name.lower() for name in TEAM_ALIASES.keys()}
            team_abbrs_lower = {abbr.lower() for abbr in TEAM_ALIASES.values()}
            
            # Try to match player names from database
            # Look for full names first (2+ words)
            words = question_lower.split()
            for i in range(len(words) - 1):
                # Try 2-word combinations (first + last name)
                two_word = f"{words[i]} {words[i+1]}"
                if two_word in player_index:
                    # Avoid matching team names (e.g., "boston celtics", "los angeles")
                    if two_word not in team_names_lower:
                        return player_index[two_word]
            
            # Try single words (last names or unique first names)
            for word in words:
                # Skip common words and team names
                skip_words = {'the', 'a', 'an', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 
                             'did', 'was', 'were', 'had', 'has', 'have', 'score', 'scored', 'points', 
                             'game', 'games', 'season', 'nba', 'team', 'teams', 'won', 'win', 'victory',
                             'between', 'against', 'over', 'versus', 'vs', 'v'}
                if word in skip_words or word in team_names_lower or word in team_abbrs_lower:
                    continue
                
                if word in player_index:
                    return player_index[word]
        except Exception:
            # Silently fail - database lookup is optional
            pass
    
    return None


# =============================================================================
# QUERY TYPE DETECTION
# =============================================================================

def detect_query_type(return_schema):
    """Determine if question is about game or player stats based on return schema"""
    evidence = return_schema.get('evidence', [])
    if evidence:
        table = evidence[0].get('table', '')
        if 'player' in table:
            return 'player'
        if 'game' in table:
            return 'game'
    
    # Check for player-specific fields
    if 'player_name' in return_schema:
        return 'player'
    
    return 'game'


# =============================================================================
# QUERY EMBEDDING CACHE
# =============================================================================

def load_query_embeddings_cache():
    """Load cached query embeddings from file"""
    if os.path.exists(QUERY_EMBEDDINGS_CACHE):
        try:
            with open(QUERY_EMBEDDINGS_CACHE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_query_embeddings_cache(cache):
    """Save query embeddings cache to file"""
    with open(QUERY_EMBEDDINGS_CACHE, 'w') as f:
        json.dump(cache, f, indent=2)


def get_query_embedding(question):
    """Get embedding for question, using cache if available (only for questions in questions.json)"""
    cache = load_query_embeddings_cache()
    
    # Check cache first
    if question in cache:
        return cache[question]
    
    # Only cache if this is one of the official questions
    is_official_question = False
    try:
        with open(QUESTIONS_PATH, 'r') as f:
            questions = json.load(f)
            official_questions = {q['question'] for q in questions}
            is_official_question = question in official_questions
    except Exception:
        pass
    
    # Generate embedding
    embedding = ollama_embed(EMBED_MODEL, question)
    
    # Only save to cache if it's an official question
    if is_official_question:
        cache[question] = embedding
        save_query_embeddings_cache(cache)
    
    return embedding


def precompute_query_embeddings():
    """Pre-compute and cache embeddings for all questions"""
    print("Pre-computing query embeddings...")
    
    with open(QUESTIONS_PATH, 'r') as f:
        questions = json.load(f)
    
    cache = load_query_embeddings_cache()
    new_count = 0
    
    for q in questions:
        question = q['question']
        if question not in cache:
            print(f"  Embedding: {question[:60]}...")
            embedding = ollama_embed(EMBED_MODEL, question)
            cache[question] = embedding
            new_count += 1
    
    save_query_embeddings_cache(cache)
    print(f"✅ Cached {new_count} new embeddings. Total: {len(cache)}")
    return cache


# =============================================================================
# HYBRID SEARCH FUNCTIONS
# =============================================================================

def search_games_hybrid(cx, question, date=None, teams=None, season=None, special_event=None, top_k=5):
    """Hybrid search: SQL filters + vector similarity for games"""
    
    # Build SQL filter
    filters = []
    if date:
        filters.append(f"g.game_timestamp::date = '{date}'")
    if teams:
        team_conditions = []
        for team in teams:
            team_conditions.append(f"t1.abbreviation = '{team}' OR t2.abbreviation = '{team}'")
        if team_conditions:
            filters.append(f"({' OR '.join(team_conditions)})")
    if season:
        filters.append(f"g.season = {season}")
    if special_event == 'christmas':
        filters.append("EXTRACT(MONTH FROM g.game_timestamp::timestamp) = 12 AND EXTRACT(DAY FROM g.game_timestamp::timestamp) = 25")
    if special_event == 'nye':
        filters.append("EXTRACT(MONTH FROM g.game_timestamp::timestamp) = 12 AND EXTRACT(DAY FROM g.game_timestamp::timestamp) = 31")
    
    where_clause = " AND ".join(filters) if filters else "1=1"
    
    # Get embedding for semantic search (use cache if available)
    query_emb = get_query_embedding(question)
    emb_str = "[" + ",".join(map(str, query_emb)) + "]"
    
    sql = f"""
        SELECT g.game_id, g.game_timestamp, g.season,
               t1.city || ' ' || t1.name as home_team, t1.abbreviation as home_abbr,
               t2.city || ' ' || t2.name as away_team, t2.abbreviation as away_abbr,
               g.home_points, g.away_points,
               1 - (g.embedding <=> '{emb_str}'::vector) as similarity
        FROM game_details g
        JOIN teams t1 ON g.home_team_id = t1.team_id
        JOIN teams t2 ON g.away_team_id = t2.team_id
        WHERE {where_clause} AND g.embedding IS NOT NULL
        ORDER BY g.embedding <=> '{emb_str}'::vector
        LIMIT {top_k}
    """
    
    results = cx.execute(text(sql))
    return results.fetchall()


def search_box_scores_hybrid(cx, question, date=None, teams=None, season=None, 
                              player_name=None, special_event=None, top_k=5):
    """Hybrid search: SQL filters + vector similarity for player box scores"""
    
    # Build SQL filter
    filters = []
    if date:
        filters.append(f"g.game_timestamp::date = '{date}'")
    if teams:
        team_conditions = []
        for team in teams:
            team_conditions.append(f"t.abbreviation = '{team}'")
            team_conditions.append(f"t1.abbreviation = '{team}'")
            team_conditions.append(f"t2.abbreviation = '{team}'")
        if team_conditions:
            filters.append(f"({' OR '.join(team_conditions)})")
    if season:
        filters.append(f"g.season = {season}")
    if player_name:
        name_parts = player_name.split()
        if len(name_parts) >= 2:
            # More flexible matching - handle special characters and variations
            # Use OR logic for first/last name to catch variations
            first_name = name_parts[0].replace("'", "''")  # Escape SQL quotes
            last_name = name_parts[-1].replace("'", "''")
            # Match if first name matches OR last name matches (more permissive)
            filters.append(f"((p.first_name ILIKE '%{first_name}%' AND p.last_name ILIKE '%{last_name}%') OR (p.first_name ILIKE '%{first_name}%' OR p.last_name ILIKE '%{last_name}%'))")
        else:
            player_name_escaped = player_name.replace("'", "''")
            filters.append(f"(p.first_name ILIKE '%{player_name_escaped}%' OR p.last_name ILIKE '%{player_name_escaped}%')")
    if special_event == 'christmas':
        filters.append("EXTRACT(MONTH FROM g.game_timestamp::timestamp) = 12 AND EXTRACT(DAY FROM g.game_timestamp::timestamp) = 25")
    if special_event == 'nye':
        filters.append("EXTRACT(MONTH FROM g.game_timestamp::timestamp) = 12 AND EXTRACT(DAY FROM g.game_timestamp::timestamp) = 31")
    if special_event == 'debut':
        filters.append("p.draft_year = 2023 AND EXTRACT(MONTH FROM g.game_timestamp::timestamp) = 10 AND EXTRACT(YEAR FROM g.game_timestamp::timestamp) = 2023")
    
    # Filter by points if question mentions specific point totals
    question_lower = question.lower()
    if '40 points' in question_lower or '40 pts' in question_lower:
        filters.append("pb.points >= 40")
    elif '50 points' in question_lower or '50 pts' in question_lower:
        filters.append("pb.points >= 50")
    elif '30 points' in question_lower or '30 pts' in question_lower:
        filters.append("pb.points >= 30")
    
    where_clause = " AND ".join(filters) if filters else "1=1"
    
    # Get embedding for semantic search (use cache if available)
    query_emb = get_query_embedding(question)
    emb_str = "[" + ",".join(map(str, query_emb)) + "]"
    
    sql = f"""
        SELECT pb.game_id, pb.person_id, 
               p.first_name || ' ' || p.last_name as player_name,
               t.city || ' ' || t.name as team_name, t.abbreviation as team_abbr,
               pb.points, pb.assists, 
               COALESCE(pb.offensive_reb, 0) + COALESCE(pb.defensive_reb, 0) as rebounds,
               pb.steals, pb.blocks,
               g.game_timestamp, g.home_points, g.away_points,
               t1.abbreviation as home_abbr, t2.abbreviation as away_abbr,
               t1.city || ' ' || t1.name as home_team,
               t2.city || ' ' || t2.name as away_team,
               1 - (pb.embedding <=> '{emb_str}'::vector) as similarity
        FROM player_box_scores pb
        JOIN players p ON pb.person_id = p.player_id
        JOIN teams t ON pb.team_id = t.team_id
        JOIN game_details g ON pb.game_id = g.game_id
        JOIN teams t1 ON g.home_team_id = t1.team_id
        JOIN teams t2 ON g.away_team_id = t2.team_id
        WHERE {where_clause} AND pb.embedding IS NOT NULL
        ORDER BY pb.embedding <=> '{emb_str}'::vector
        LIMIT {top_k}
    """
    
    results = cx.execute(text(sql))
    return results.fetchall()


def get_top_scorer_for_game(cx, game_id):
    """Get the top scorer for a specific game"""
    sql = f"""
        SELECT pb.game_id, pb.person_id, 
               p.first_name || ' ' || p.last_name as player_name,
               t.abbreviation as team_abbr, pb.points,
               COALESCE(pb.offensive_reb, 0) + COALESCE(pb.defensive_reb, 0) as rebounds,
               pb.assists
        FROM player_box_scores pb
        JOIN players p ON pb.person_id = p.player_id
        JOIN teams t ON pb.team_id = t.team_id
        WHERE pb.game_id = {game_id}
        ORDER BY pb.points DESC
        LIMIT 1
    """
    
    result = cx.execute(text(sql))
    return result.fetchone()


def get_triple_double_player(cx, game_id):
    """Get player with triple-double in a specific game"""
    sql = f"""
        SELECT pb.game_id, pb.person_id, 
               p.first_name || ' ' || p.last_name as player_name,
               t.abbreviation as team_abbr, 
               pb.points,
               COALESCE(pb.offensive_reb, 0) + COALESCE(pb.defensive_reb, 0) as rebounds,
               pb.assists
        FROM player_box_scores pb
        JOIN players p ON pb.person_id = p.player_id
        JOIN teams t ON pb.team_id = t.team_id
        WHERE pb.game_id = {game_id}
          AND pb.points >= 10
          AND (COALESCE(pb.offensive_reb, 0) + COALESCE(pb.defensive_reb, 0)) >= 10
          AND pb.assists >= 10
        LIMIT 1
    """
    
    result = cx.execute(text(sql))
    return result.fetchone()


# =============================================================================
# ANSWER GENERATION
# =============================================================================

def generate_answer_for_game(cx, question, return_schema, date, teams, season, special_event):
    """Generate answer for game-related questions"""
    
    games = search_games_hybrid(cx, question, date, teams, season, special_event, top_k=1)
    
    if not games:
        return None, None
    
    game = games[0]
    game_id = int(game[0])
    home_team = game[3]
    home_abbr = game[4]
    away_team = game[5]
    away_abbr = game[6]
    home_points = int(game[7])
    away_points = int(game[8])
    
    winner = home_team if home_points > away_points else away_team
    score = f"{max(home_points, away_points)}-{min(home_points, away_points)}"
    
    result = {}
    
    # Fill in based on return schema
    if 'points' in return_schema and 'winner' not in return_schema:
        # Q1: How many points did team X score?
        # The FIRST team mentioned in `teams` list is the one we want points for
        if teams:
            target_team = teams[0]  # First team parsed from question
            if target_team == home_abbr:
                result['points'] = home_points
            elif target_team == away_abbr:
                result['points'] = away_points
            else:
                result['points'] = away_points  # Default
        else:
            result['points'] = home_points  # Default to home team
    
    if 'winner' in return_schema:
        result['winner'] = winner
    
    if 'score' in return_schema:
        result['score'] = score
    
    result['evidence'] = [{"table": "game_details", "id": game_id}]
    
    context_text = (
        f"Game: {away_team} ({away_abbr}) at {home_team} ({home_abbr}) on {game[1]}. "
        f"Score: {home_team} {home_points}, {away_team} {away_points}. Winner: {winner}."
    )
    
    return result, context_text


def generate_answer_for_player(cx, question, return_schema, date, teams, season, player_name, special_event):
    """Generate answer for player-related questions"""
    
    question_lower = question.lower()
    
    # Special handling for "leading scorer" questions
    if 'leading scorer' in question_lower or 'top scorer' in question_lower:
        games = search_games_hybrid(cx, question, date, teams, season, special_event, top_k=1)
        if games:
            game_id = int(games[0][0])
            game_timestamp = games[0][1]  # Get game date from search results
            game_date = game_timestamp.strftime('%B %d, %Y') if hasattr(game_timestamp, 'strftime') else str(game_timestamp)
            top_scorer = get_top_scorer_for_game(cx, game_id)
            if top_scorer:
                result = {
                    'player_name': top_scorer[2],
                    'points': int(top_scorer[4]),
                    'evidence': [{"table": "player_box_score", "id": int(top_scorer[1])}]
                }
                if 'rebounds' in return_schema:
                    result['rebounds'] = int(top_scorer[5])
                if 'assists' in return_schema:
                    result['assists'] = int(top_scorer[6])
                context_text = (
                    f"Top scorer in game on {game_date}: {top_scorer[2]} ({top_scorer[3]}) "
                    f"with {int(top_scorer[4])} points, {int(top_scorer[5])} rebounds, "
                    f"{int(top_scorer[6])} assists."
                )
                return result, context_text
    
    # Special handling for "triple-double" questions
    if 'triple-double' in question_lower or 'triple double' in question_lower:
        games = search_games_hybrid(cx, question, date, teams, season, special_event, top_k=1)
        if games:
            game_id = int(games[0][0])
            triple_double = get_triple_double_player(cx, game_id)
            if triple_double:
                context_text = (
                    f"Triple-double in game {game_id}: {triple_double[2]} ({triple_double[3]}) "
                    f"with {int(triple_double[4])} points, {int(triple_double[5])} rebounds, "
                    f"{int(triple_double[6])} assists."
                )
                return {
                    'player_name': triple_double[2],
                    'points': int(triple_double[4]),
                    'rebounds': int(triple_double[5]),
                    'assists': int(triple_double[6]),
                    'evidence': [{"table": "player_box_score", "id": int(triple_double[1])}]
                }, context_text
    
    # Regular player search - use top_k=5 to improve retrieval
    box_scores = search_box_scores_hybrid(cx, question, date, teams, season, player_name, special_event, top_k=5)
    
    # Fallback strategies if no results found
    if not box_scores:
        # Try 1: Remove team filter if we have date+player
        if date and player_name and teams:
            box_scores = search_box_scores_hybrid(cx, question, date, None, season, player_name, special_event, top_k=5)
        # Try 2: Remove player filter if we have date+teams (let vector search find the player)
        if not box_scores and date and teams and player_name:
            box_scores = search_box_scores_hybrid(cx, question, date, teams, season, None, special_event, top_k=5)
            # Filter results to find the player manually
            if box_scores:
                for bs in box_scores:
                    if player_name.lower() in bs[2].lower():  # bs[2] is player_name
                        box_scores = [bs]
                        break
                else:
                    box_scores = []
        # Try 3: Only date filter, then filter by player name in Python
        if not box_scores and date and player_name:
            box_scores = search_box_scores_hybrid(cx, question, date, None, season, None, special_event, top_k=10)
            # Filter results to find the player manually
            if box_scores:
                for bs in box_scores:
                    player_match = bs[2].lower()  # bs[2] is player_name
                    if any(part.lower() in player_match for part in player_name.split()):
                        box_scores = [bs]
                        break
                else:
                    box_scores = []
    
    if not box_scores:
        return None, None
    
    row = box_scores[0]
    result = {
        'player_name': row[2],
        'points': int(row[5]) if row[5] else 0,
        'evidence': [{"table": "player_box_score", "id": int(row[1])}]
    }
    
    if 'rebounds' in return_schema:
        result['rebounds'] = int(row[7]) if row[7] else 0
    if 'assists' in return_schema:
        result['assists'] = int(row[6]) if row[6] else 0
    
    context_text = (
        f"Player: {row[2]} ({row[3]} - {row[4]}). "
        f"Game: {row[15]} vs {row[16]}. "
        f"Points: {int(row[5]) if row[5] else 0}, "
        f"Rebounds: {int(row[7]) if row[7] else 0}, "
        f"Assists: {int(row[6]) if row[6] else 0}."
    )
    
    return result, context_text


# =============================================================================
# MAIN RAG PIPELINE
# =============================================================================

def answer_question(cx, question, return_schema):
    """Main RAG pipeline: parse, search, generate answer"""
    
    # Parse question (pass cx for database-backed player lookup)
    date = parse_date(question)
    teams = parse_teams(question)
    season = parse_season(question)
    player = parse_player(question, cx)  # Pass connection for DB lookup
    special_event = parse_special_event(question)
    query_type = detect_query_type(return_schema)
    
    # Generate answer based on query type
    if query_type == 'game':
        result, context_text = generate_answer_for_game(cx, question, return_schema, date, teams, season, special_event)
    else:
        result, context_text = generate_answer_for_player(cx, question, return_schema, date, teams, season, player, special_event)
    
    # Return early if no data found - with diagnostic information
    if not result:
        # Build diagnostic message explaining why data wasn't found
        diagnostic_parts = []
        
        if query_type == 'player':
            # Check what we tried to find
            if date:
                diagnostic_parts.append(f"searched for date: {date}")
            if teams:
                diagnostic_parts.append(f"searched for teams: {', '.join(teams)}")
            if player:
                diagnostic_parts.append(f"searched for player: {player}")
            if season:
                diagnostic_parts.append(f"searched for season: {season}")
            
            # Try to find if game exists without player filter
            if date and teams:
                games = search_games_hybrid(cx, question, date, teams, season, special_event, top_k=1)
                if games:
                    diagnostic_parts.append(f"Found the game, but could not find player '{player}' in that game's box scores")
                else:
                    # Try without team filter to see if date matches
                    games_no_teams = search_games_hybrid(cx, question, date, None, season, special_event, top_k=1)
                    if games_no_teams:
                        diagnostic_parts.append(f"Found games on that date, but none matching the specified teams ({', '.join(teams)}). The team abbreviations may not match (e.g., 'Rockets' should be 'HOU', 'Lakers' should be 'LAL')")
                    else:
                        diagnostic_parts.append(f"Could not find any games on the specified date ({date})")
            elif date:
                games = search_games_hybrid(cx, question, date, None, season, special_event, top_k=1)
                if games:
                    diagnostic_parts.append("Found games on that date, but none matching the specified teams")
                else:
                    diagnostic_parts.append(f"Could not find any games on the specified date ({date})")
        else:
            # Game query
            if date:
                diagnostic_parts.append(f"searched for date: {date}")
            if teams:
                diagnostic_parts.append(f"searched for teams: {', '.join(teams)}")
            if season:
                diagnostic_parts.append(f"searched for season: {season}")
            diagnostic_parts.append("Could not find a matching game in the database")
        
        diagnostic_msg = "No data found. " + ". ".join(diagnostic_parts) + "."
        return {
            'answer': diagnostic_msg,
            'evidence': []
        }
    
    # Build a deterministic fallback answer from structured data
    def build_structured_answer(res):
        # Player-centric answers
        if 'player_name' in res and 'points' in res:
            parts = [f"{res['player_name']} scored {res['points']} points"]
            if 'rebounds' in res:
                parts.append(f"{res['rebounds']} rebounds")
            if 'assists' in res:
                parts.append(f"{res['assists']} assists")
            return '. '.join(parts) + '.'

        # Game-centric answers
        if 'winner' in res or 'score' in res or 'points' in res:
            pieces = []
            if 'winner' in res:
                pieces.append(f"Winner: {res['winner']}")
            if 'score' in res:
                pieces.append(f"Score: {res['score']}")
            if 'points' in res and 'winner' not in res:
                pieces.append(f"Points: {res['points']}")
            if pieces:
                return '. '.join(pieces) + '.'

        return ""
    
    # Always try to use LLM for natural language generation (with fast timeout)
    if context_text and LLM_MODEL:
        # Directive prompt that forces the model to use provided historical data
        prompt = (
            "You are answering a question about historical NBA game data. "
            "The data below is from a database and is accurate. Use it to answer the question directly.\n\n"
            f"Question: {question}\n"
            f"Data: {context_text}\n\n"
            "Answer using ONLY the data provided. Do not refuse or say you don't have information. "
            "The data is historical and accurate. Answer:"
        )
        try:
            llm_resp = ollama_chat(LLM_MODEL, prompt, timeout=10)
            if llm_resp and len(llm_resp.strip()) > 5:
                # Filter out refusal responses
                refusal_phrases = [
                    "i can't", "i cannot", "i don't have", "i don't know",
                    "not available", "not provided", "cannot verify", "cannot provide",
                    "unable to", "don't have access", "knowledge cutoff", "i will need to look",
                    "however, since", "i can only provide", "real-time", "future scores"
                ]
                llm_resp_lower = llm_resp.strip().lower()
                first_100_chars = llm_resp_lower[:100]
                
                # Check if response contains refusal phrases
                if any(phrase in first_100_chars for phrase in refusal_phrases):
                    # LLM refused - fall through to structured answer
                    pass
                else:
                    # Clean up response
                    clean_resp = llm_resp.strip()
                    # Remove common prefixes
                    for prefix in ["Answer:", "A:", "The answer is", "Based on the data"]:
                        if clean_resp.lower().startswith(prefix.lower()):
                            clean_resp = clean_resp[len(prefix):].strip()
                            if clean_resp.startswith(':'):
                                clean_resp = clean_resp[1:].strip()
                    
                    # For questions asking for multiple stats (triple-double, etc.), take up to 3 sentences
                    # Otherwise take first sentence or first 200 chars
                    sentences = [s.strip() for s in clean_resp.split('.') if s.strip()]
                    if 'triple-double' in question.lower() or 'triple double' in question.lower() or 'rebounds' in question.lower() and 'assists' in question.lower():
                        # Multi-stat questions: take up to 3 sentences or 250 chars
                        if len(sentences) > 0:
                            answer_parts = sentences[:3]
                            answer_text = '. '.join(answer_parts) + '.'
                            if len(answer_text) > 250:
                                answer_text = answer_text[:250].strip() + '...'
                            result['answer'] = answer_text
                        elif len(clean_resp) > 10:
                            result['answer'] = clean_resp[:250].strip() + ('...' if len(clean_resp) > 250 else '')
                    else:
                        # Single-stat questions: take first sentence or first 200 chars
                        if len(sentences) > 0 and len(sentences[0]) < 200:
                            result['answer'] = sentences[0] + '.'
                        elif len(clean_resp) > 10:
                            result['answer'] = clean_resp[:200].strip() + ('...' if len(clean_resp) > 200 else '')
        except Exception:
            # Fall back to structured answer if LLM fails
            pass
    
    # Fallback to structured answer if LLM didn't provide one
    if not result.get('answer'):
        structured_answer = build_structured_answer(result)
        if structured_answer:
            result['answer'] = structured_answer
        elif context_text:
            # Last resort: return context
            result['answer'] = context_text

    # Ensure evidence is always present for frontend consumption
    if 'evidence' not in result:
        result['evidence'] = []
    
    return result


def process_questions():
    """Process all questions from JSON file and output answers"""
    
    # Load questions
    with open(QUESTIONS_PATH, 'r') as f:
        questions = json.load(f)
    
    engine = sa.create_engine(DB_DSN)
    answers = []
    
    with engine.begin() as cx:
        for q in questions:
            qid = q['id']
            question = q['question']
            return_schema = q['return']
            
            print(f"\nQ{qid}: {question[:60]}...")
            
            result = answer_question(cx, question, return_schema)
            
            if result:
                # Remove LLM-generated 'answer' field for Part 1 submission
                # (answers.json should only contain structured data with evidence)
                result_for_submission = {k: v for k, v in result.items() if k != 'answer'}
                answers.append({
                    "id": qid,
                    "result": result_for_submission
                })
                print(f"  Answer: {result_for_submission}")
            else:
                # No data found - return null values
                null_result = {k: (0 if v == "int" else "") for k, v in return_schema.items() if k != 'evidence'}
                null_result['evidence'] = []
                answers.append({
                    "id": qid,
                    "result": null_result
                })
                print("  No data found")
    
    # Save answers
    with open(ANSWERS_PATH, 'w') as f:
        json.dump(answers, f, indent=2)
    
    print(f"\n✅ Saved {len(answers)} answers to {ANSWERS_PATH}")


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys
    
    # Check if user wants to pre-compute embeddings
    if len(sys.argv) > 1 and sys.argv[1] == "--precompute-embeddings":
        precompute_query_embeddings()
    else:
        process_questions()