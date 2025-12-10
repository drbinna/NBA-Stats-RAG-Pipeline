"""
embed.py - Generate embeddings for NBA game data

This script:
1. Loads game_details and player_box_scores from PostgreSQL
2. Serializes records into natural language text with:
   - Multiple date formats for query matching
   - Special event tags (Christmas, NYE, Season opener)
   - Achievement tags (40-point game, triple-double, NBA debut)
   - Leading scorer tags
   - Team names and abbreviations
3. Generates embeddings using Ollama nomic-embed-text
4. Stores embeddings back in PostgreSQL with HNSW index
"""

import pandas as pd
import sqlalchemy as sa
from sqlalchemy import text
from backend.config import DB_DSN, EMBED_MODEL
from backend.utils import ollama_embed


# =============================================================================
# SERIALIZATION HELPER FUNCTIONS
# =============================================================================

def get_season_text(season):
    """Convert season int to readable format (e.g., 2023 -> '2023-24 NBA Season. 2023 NBA Season.')"""
    if pd.isna(season):
        return ""
    s = int(season)
    return f"{s}-{str(s+1)[-2:]} NBA Season. {s} NBA Season."


def get_special_date_tags(dt):
    """Identify special games (Christmas, NYE, etc.)"""
    if pd.isna(dt):
        return ""
    tags = []
    month, day = dt.month, dt.day
    if month == 12 and day == 25:
        tags.extend(["Christmas Day game", "Christmas game"])
    if month == 12 and day == 31:
        tags.extend(["New Years Eve game", "NYE game"])
    if month == 1 and day == 1:
        tags.append("New Years Day game")
    if month == 10 and day <= 30:
        tags.extend(["Season opener", "Opening week"])
    return ". ".join(tags)


def format_date_multiple(dt):
    """Return multiple date formats for better query matching"""
    if pd.isna(dt):
        return ""
    d = pd.to_datetime(dt)
    # Use zero-padded formats for cross-platform compatibility
    formats = [
        d.strftime('%B %d, %Y'),       # December 25, 2023
        d.strftime('%m/%d/%Y'),         # 12/25/2023
        f"{d.month}/{d.day}/{d.year}",  # 1/26/2024 (no leading zeros)
        f"{d.month}-{d.day}-{str(d.year)[-2:]}",  # 1-26-24 (no leading zeros)
        d.strftime('%b %d, %Y'),        # Dec 25, 2023
        d.strftime('%Y-%m-%d'),         # 2023-12-25
    ]
    return ". ".join(formats)


def get_player_achievement_tags(pts, reb, ast, stl, blk, player_id, game_dt, player_id_to_draft_year):
    """Generate achievement tags for a player performance"""
    tags = []
    
    # Point milestones
    if pts >= 50:
        tags.extend(["50-point game", "50+ points"])
    elif pts >= 40:
        tags.extend(["40-point game", "40+ points"])
    elif pts >= 30:
        tags.append("30-point game")
    
    # Triple-double / Double-double
    double_digit_cats = sum([pts >= 10, reb >= 10, ast >= 10, stl >= 10, blk >= 10])
    if double_digit_cats >= 3:
        tags.extend(["Triple-double", "triple double"])
    elif double_digit_cats >= 2:
        tags.append("Double-double")
    
    # NBA Debut detection (2023 draft class playing in Oct 2023)
    draft_year = player_id_to_draft_year.get(player_id)
    if draft_year and not pd.isna(draft_year) and game_dt:
        game_date = pd.to_datetime(game_dt)
        try:
            if int(draft_year) == 2023 and game_date.year == 2023 and game_date.month == 10:
                tags.extend(["NBA debut", "First NBA game", "Rookie debut"])
        except (ValueError, TypeError):
            pass
    
    return ". ".join(tags) if tags else ""


# =============================================================================
# SERIALIZATION FUNCTIONS
# =============================================================================

def serialize_game(row, team_id_to_name, team_id_to_abbr):
    """Serialize a game_details row to natural language"""
    home_team = team_id_to_name.get(row['home_team_id'], str(row['home_team_id']))
    away_team = team_id_to_name.get(row['away_team_id'], str(row['away_team_id']))
    home_abbr = team_id_to_abbr.get(row['home_team_id'], '')
    away_abbr = team_id_to_abbr.get(row['away_team_id'], '')
    
    home_pts = int(row['home_points'])
    away_pts = int(row['away_points'])
    
    winner = home_team if home_pts > away_pts else away_team
    winner_pts = max(home_pts, away_pts)
    loser_pts = min(home_pts, away_pts)
    
    game_dt = pd.to_datetime(row['game_timestamp'])
    date_str = format_date_multiple(game_dt)
    special_tags = get_special_date_tags(game_dt)
    season_text = get_season_text(row['season'])
    
    result = f"NBA Game on {date_str}. "
    if special_tags:
        result += f"{special_tags}. "
    if season_text:
        result += f"{season_text} "
    result += f"{home_team} ({home_abbr}) vs {away_team} ({away_abbr}). "
    result += f"Home team: {home_team} scored {home_pts} points. "
    result += f"Away team: {away_team} scored {away_pts} points. "
    result += f"Final score: {winner_pts}-{loser_pts}. {winner} won."
    
    return result


def serialize_box_score(row, team_id_to_name, team_id_to_abbr, player_id_to_name, 
                         player_id_to_draft_year, game_top_scorers):
    """Serialize a player_box_scores row to natural language"""
    player_id = row['person_id']
    player_name = player_id_to_name.get(player_id, "Unknown Player")
    team_name = team_id_to_name.get(row['team_id'], str(row['team_id']))
    team_abbr = team_id_to_abbr.get(row['team_id'], '')
    
    pts = int(row['points']) if not pd.isna(row['points']) else 0
    reb = int(row.get('offensive_reb', 0) or 0) + int(row.get('defensive_reb', 0) or 0)
    ast = int(row['assists']) if not pd.isna(row['assists']) else 0
    stl = int(row['steals']) if not pd.isna(row['steals']) else 0
    blk = int(row['blocks']) if not pd.isna(row['blocks']) else 0
    
    # Get opponent team
    if row['team_id'] == row['home_team_id']:
        opponent = team_id_to_name.get(row['away_team_id'], '')
        opponent_abbr = team_id_to_abbr.get(row['away_team_id'], '')
    else:
        opponent = team_id_to_name.get(row['home_team_id'], '')
        opponent_abbr = team_id_to_abbr.get(row['home_team_id'], '')
    
    game_dt = row['game_dt']
    date_str = format_date_multiple(game_dt)
    special_tags = get_special_date_tags(game_dt)
    season_text = get_season_text(row['season'])
    achievement_tags = get_player_achievement_tags(pts, reb, ast, stl, blk, player_id, game_dt, player_id_to_draft_year)
    
    # Check if top scorer
    is_top_scorer = game_top_scorers.get(row['game_id']) == player_id
    
    result = f"Player: {player_name}. Team: {team_name} ({team_abbr}). "
    result += f"Date: {date_str}. "
    if special_tags:
        result += f"{special_tags}. "
    if season_text:
        result += f"{season_text} "
    result += f"Points: {pts}. Rebounds: {reb}. Assists: {ast}. "
    if is_top_scorer:
        result += "Leading scorer. Top scorer. High scorer of the game. "
    if achievement_tags:
        result += f"{achievement_tags}. "
    result += f"Opponent: {opponent} ({opponent_abbr})."
    
    return result


# =============================================================================
# MAIN EMBEDDING PIPELINE
# =============================================================================

def main():
    print("=" * 60)
    print("NBA RAG Embedding Pipeline")
    print("=" * 60)
    
    eng = sa.create_engine(DB_DSN)
    
    with eng.begin() as cx:
        # =====================================================================
        # [1/7] Load lookup tables
        # =====================================================================
        print("\n[1/7] Loading lookup tables...")
        teams = pd.read_sql("SELECT * FROM teams", cx)
        players = pd.read_sql("SELECT * FROM players", cx)
        
        team_id_to_name = dict(zip(teams['team_id'], teams['city'] + ' ' + teams['name']))
        team_id_to_abbr = dict(zip(teams['team_id'], teams['abbreviation']))
        player_id_to_name = dict(zip(players['player_id'], players['first_name'] + ' ' + players['last_name']))
        player_id_to_draft_year = dict(zip(players['player_id'], players['draft_year']))
        
        print(f"  Loaded {len(teams)} teams, {len(players)} players")
        
        # =====================================================================
        # [2/7] Load game data
        # =====================================================================
        print("\n[2/7] Loading game data...")
        games = pd.read_sql("SELECT * FROM game_details", cx)
        box_scores = pd.read_sql("SELECT * FROM player_box_scores", cx)
        print(f"  Loaded {len(games)} games, {len(box_scores)} box scores")
        
        # =====================================================================
        # [3/7] Prepare data
        # =====================================================================
        print("\n[3/7] Preparing data...")
        games['game_dt'] = pd.to_datetime(games['game_timestamp'])
        
        # Merge box scores with game info for opponent lookup
        box_scores = box_scores.merge(
            games[['game_id', 'game_dt', 'home_team_id', 'away_team_id', 'season']],
            on='game_id',
            how='left'
        )
        
        # Pre-compute top scorer per game
        game_top_scorers = box_scores.groupby('game_id').apply(
            lambda x: x.loc[x['points'].idxmax(), 'person_id'],
            include_groups=False
        ).to_dict()
        print(f"  Computed top scorers for {len(game_top_scorers)} games")
        
        # =====================================================================
        # [4/7] Add embedding columns
        # =====================================================================
        print("\n[4/7] Adding embedding columns...")
        cx.execute(text("ALTER TABLE game_details ADD COLUMN IF NOT EXISTS embedding vector(768);"))
        cx.execute(text("ALTER TABLE player_box_scores ADD COLUMN IF NOT EXISTS embedding vector(768);"))
        print("  Columns added")
        
        # =====================================================================
        # [5/7] Embed game_details
        # =====================================================================
        print("\n[5/7] Embedding game_details...")
        for i, (_, row) in enumerate(games.iterrows()):
            text_content = serialize_game(row, team_id_to_name, team_id_to_abbr)
            vec = ollama_embed(EMBED_MODEL, text_content)
            
            cx.execute(
                text("UPDATE game_details SET embedding = :v WHERE game_id = :gid"),
                {"v": vec, "gid": int(row['game_id'])}
            )
            
            if (i + 1) % 100 == 0:
                print(f"  Progress: {i + 1}/{len(games)}")
        
        print(f"  Embedded {len(games)} games")
        
        # =====================================================================
        # [6/7] Embed player_box_scores
        # =====================================================================
        print("\n[6/7] Embedding player_box_scores...")
        for i, (_, row) in enumerate(box_scores.iterrows()):
            text_content = serialize_box_score(
                row, team_id_to_name, team_id_to_abbr,
                player_id_to_name, player_id_to_draft_year, game_top_scorers
            )
            vec = ollama_embed(EMBED_MODEL, text_content)
            
            cx.execute(
                text("UPDATE player_box_scores SET embedding = :v WHERE game_id = :gid AND person_id = :pid"),
                {"v": vec, "gid": int(row['game_id']), "pid": int(row['person_id'])}
            )
            
            if (i + 1) % 500 == 0:
                print(f"  Progress: {i + 1}/{len(box_scores)}")
        
        print(f"  Embedded {len(box_scores)} box scores")
        
        # =====================================================================
        # [7/7] Create HNSW indexes
        # =====================================================================
        print("\n[7/7] Creating HNSW indexes...")
        cx.execute(text("CREATE INDEX IF NOT EXISTS idx_game_details_embedding ON game_details USING hnsw (embedding vector_cosine_ops);"))
        cx.execute(text("CREATE INDEX IF NOT EXISTS idx_box_scores_embedding ON player_box_scores USING hnsw (embedding vector_cosine_ops);"))
        print("  HNSW indexes created")
    
    print("\n" + "=" * 60)
    print("Embedding pipeline complete!")
    print(f"  Total vectors: {len(games) + len(box_scores)}")
    print("=" * 60)


if __name__ == "__main__":
    main()