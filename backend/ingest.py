"""Builds the database: loads public NBA game logs, writes the structured tables,
turns every game and player line into a text passage, embeds the passages and
indexes them with pgvector (HNSW, cosine distance).

Data: "NBA Player Game Logs" by cbratkovics on Hugging Face (CC0 1.0 packaging of
Eoin Moore's Kaggle dataset), regular season only.

Usage:
    python -m backend.ingest                       # default seasons, Fireworks embeddings
    python -m backend.ingest --seasons 2024-25     # one season
    EMBED_PROVIDER=local python -m backend.ingest  # embed on this machine instead
    python -m backend.ingest --skip-embed          # tables only
"""
import argparse
import io
import time
import unicodedata

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

from backend.config import DB_DSN, EMBED_DIM, EMBED_PRICE_PER_M
from backend.documents import game_text, player_line_text
from backend.embeddings import embed, to_pgvector

HF_URL = "https://huggingface.co/datasets/cbratkovics/nba-game-logs/resolve/main/game_logs/game_logs_{}.parquet"
DEFAULT_SEASONS = ["2023-24", "2024-25", "2025-26", "2026-27"]
# Tables from the project's first version. They are dropped so no older data stays behind.
LEGACY_TABLES = ["player_box_scores", "game_details"]

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;
DROP TABLE IF EXISTS documents, player_games, games, players, teams, {", ".join(LEGACY_TABLES)} CASCADE;
CREATE TABLE teams (abbreviation text PRIMARY KEY, city text, name text);
CREATE TABLE players (player_id bigint PRIMARY KEY, name text NOT NULL, name_key text NOT NULL);
CREATE TABLE games (
    game_id text PRIMARY KEY, game_date date NOT NULL, season text NOT NULL,
    home_team text NOT NULL, away_team text NOT NULL, home_points int, away_points int,
    winner text, overtime boolean);
CREATE TABLE player_games (
    game_id text REFERENCES games, player_id bigint REFERENCES players, game_date date, season text,
    team text, opponent text, home boolean, minutes real, pts int, reb int, ast int, stl int, blk int,
    tov int, fgm int, fga int, fg3m int, fg3a int, ftm int, fta int, oreb int, dreb int, pf int,
    plus_minus int, PRIMARY KEY (game_id, player_id));
CREATE TABLE documents (
    doc_id text PRIMARY KEY, kind text NOT NULL, game_id text, player_id bigint, game_date date,
    season text, teams text[], content text NOT NULL, embedding vector({EMBED_DIM}),
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS player_games_player_date ON player_games (player_id, game_date);
CREATE INDEX IF NOT EXISTS player_games_date ON player_games (game_date);
CREATE INDEX IF NOT EXISTS games_date ON games (game_date);
CREATE INDEX IF NOT EXISTS documents_date ON documents (game_date);
CREATE INDEX IF NOT EXISTS documents_player ON documents (player_id);
CREATE INDEX IF NOT EXISTS documents_teams ON documents USING gin (teams);
CREATE INDEX IF NOT EXISTS documents_tsv ON documents USING gin (tsv);
"""
# Built after the vectors are written, which is much faster than updating the graph row by row.
VECTOR_INDEX = """
CREATE INDEX IF NOT EXISTS documents_embedding_hnsw ON documents USING hnsw (embedding vector_cosine_ops);
ANALYZE;
"""


def name_key(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace(".", "").replace("'", "").split())


def load_frames(seasons, local_dir=None):
    frames = []
    for s in seasons:
        src = f"{local_dir}/game_logs_{s}.parquet" if local_dir else HF_URL.format(s)
        print(f"reading {s} from {src}")
        frames.append(pd.read_parquet(src))
    df = pd.concat(frames, ignore_index=True)
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.date
    return df


def build_games(df):
    team_pts = df.groupby(["game_id", "team"], as_index=False).agg(
        pts=("pts", "sum"), home=("home", "first"), minutes=("minutes", "sum"),
        game_date=("game_date", "first"), season=("season", "first"))
    home = team_pts[team_pts.home].rename(columns={"team": "home_team", "pts": "home_points"})
    away = team_pts[~team_pts.home][["game_id", "team", "pts"]].rename(columns={"team": "away_team", "pts": "away_points"})
    g = home.merge(away, on="game_id")
    g["winner"] = g.apply(lambda r: r.home_team if r.home_points > r.away_points else r.away_team, axis=1)
    g["overtime"] = g["minutes"] > 242  # five players x 48 minutes, plus rounding
    openers = g.groupby("season")["game_date"].transform("min")
    g["season_opener"] = g["game_date"] == openers
    return g[["game_id", "game_date", "season", "home_team", "away_team", "home_points", "away_points", "winner", "overtime", "season_opener"]]


def copy_df(cur, table, df):
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False)
    buf.seek(0)
    cur.copy_expert(f"COPY {table} ({','.join(df.columns)}) FROM STDIN WITH CSV", buf)


def build_documents(df, games):
    g = games.set_index("game_id")
    docs = []
    for game_id, rows in df.groupby("game_id"):
        gr = g.loc[game_id]
        top = rows.sort_values("pts", ascending=False).groupby("team").head(1)
        top = top.sort_values("pts", ascending=False)
        game = gr.to_dict() | {"top_scorers": list(zip(top.player_name, top.pts, top.team))}
        teams = [gr.home_team, gr.away_team]
        docs.append((f"game:{game_id}", "game", game_id, None, gr.game_date, gr.season, teams, game_text(game)))
        for r in rows.to_dict("records"):
            home_pts, away_pts = int(gr.home_points), int(gr.away_points)
            r |= {"team_points": home_pts if r["home"] else away_pts,
                  "opp_points": away_pts if r["home"] else home_pts,
                  "season_opener": bool(gr.season_opener)}
            docs.append((f"line:{game_id}:{r['player_id']}", "player_game", game_id, int(r["player_id"]),
                         r["game_date"], r["season"], teams, player_line_text(r)))
    return docs


def embed_documents(conn, batch=128):
    cur = conn.cursor()
    cur.execute("SELECT doc_id, content FROM documents WHERE embedding IS NULL ORDER BY doc_id")
    todo = cur.fetchall()
    print(f"embedding {len(todo):,} passages")
    t0, tokens = time.time(), 0
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        vecs, n = embed([c for _, c in chunk], kind="document")
        tokens += n
        execute_values(cur, "UPDATE documents d SET embedding = v.e::vector FROM (VALUES %s) AS v(id, e) WHERE d.doc_id = v.id",
                       [(doc_id, to_pgvector(v)) for (doc_id, _), v in zip(chunk, vecs)])
        conn.commit()
        if (i // batch) % 20 == 0:
            rate = (i + len(chunk)) / max(time.time() - t0, 1e-6)
            print(f"  {i + len(chunk):,}/{len(todo):,}  {rate:,.0f}/s")
    if tokens:
        print(f"embedding tokens: {tokens:,} (about ${tokens / 1e6 * EMBED_PRICE_PER_M:.4f})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", default=DEFAULT_SEASONS)
    ap.add_argument("--local-dir", help="read game_logs_<season>.parquet files from this folder")
    ap.add_argument("--skip-embed", action="store_true")
    ap.add_argument("--embed-only", action="store_true", help="only embed passages that have no vector yet")
    args = ap.parse_args()
    conn = psycopg2.connect(DB_DSN)
    if not args.embed_only:
        df = load_frames(args.seasons, args.local_dir)
        games = build_games(df)
        players = df.groupby("player_id", as_index=False)["player_name"].last().rename(columns={"player_name": "name"})
        players["name_key"] = players["name"].map(name_key)
        from backend.teams import TEAMS
        teams = pd.DataFrame([(a, c, n) for a, (c, n) in TEAMS.items()], columns=["abbreviation", "city", "name"])
        cols = ["game_id", "player_id", "game_date", "season", "team", "opponent", "home", "minutes", "pts", "reb", "ast",
                "stl", "blk", "tov", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "pf", "plus_minus"]
        cur = conn.cursor()
        cur.execute(SCHEMA)
        copy_df(cur, "teams", teams)
        copy_df(cur, "players", players)
        copy_df(cur, "games", games.drop(columns=["season_opener"]))
        copy_df(cur, "player_games", df[cols])
        docs = build_documents(df, games)
        execute_values(cur, "INSERT INTO documents (doc_id, kind, game_id, player_id, game_date, season, teams, content) VALUES %s",
                       docs, page_size=2000)
        conn.commit()
        print(f"loaded {len(players):,} players, {len(games):,} games, {len(df):,} player lines, {len(docs):,} passages")
    cur = conn.cursor()
    cur.execute(INDEXES)
    conn.commit()
    if not args.skip_embed:
        cur.execute("DROP INDEX IF EXISTS documents_embedding_hnsw")
        conn.commit()
        embed_documents(conn)
        cur.execute(VECTOR_INDEX)
        conn.commit()
    print("indexes built")


if __name__ == "__main__":
    main()
