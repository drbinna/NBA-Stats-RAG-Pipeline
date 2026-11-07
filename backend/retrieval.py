"""Hybrid retrieval over the embedded passages.

A question is parsed for what people ask about: players (including nicknames
and typos), teams, dates, seasons and stat thresholds ("35+ points"). Those
become SQL filters that narrow the candidate passages, which are then ranked by
cosine similarity to the question's embedding (pgvector). If the filters leave
nothing, they are relaxed one at a time. With no filters, the HNSW index does
an approximate nearest-neighbor search over the whole corpus.
"""
import difflib
import re
import time
import unicodedata
from datetime import date
from functools import lru_cache

from sqlalchemy import text

from backend.embeddings import embed_query, to_pgvector
from backend.teams import TEAM_ALIASES, TEAMS

# Nicknames a name match won't catch.
PLAYER_ALIASES = {
    "sga": "Shai Gilgeous-Alexander", "shai": "Shai Gilgeous-Alexander", "chet": "Chet Holmgren",
    "jdub": "Jalen Williams", "j-dub": "Jalen Williams", "lu dort": "Luguentz Dort", "joker": "Nikola Jokić",
    "bron": "LeBron James", "king james": "LeBron James", "steph": "Stephen Curry", "giannis": "Giannis Antetokounmpo",
    "the greek freak": "Giannis Antetokounmpo", "luka": "Luka Dončić", "ant": "Anthony Edwards", "ant-man": "Anthony Edwards",
    "wemby": "Victor Wembanyama", "kd": "Kevin Durant", "ad": "Anthony Davis", "cp3": "Chris Paul", "jokic": "Nikola Jokić",
    "embiid": "Joel Embiid", "tatum": "Jayson Tatum", "brunson": "Jalen Brunson", "harden": "James Harden",
}
MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}
MONTHS |= {k[:3]: v for k, v in MONTHS.items()} | {"sept": 9}
HOLIDAYS = {"christmas": (12, 25), "new year's eve": (12, 31), "new years eve": (12, 31)}
RRF_K = 60
STAT_WORDS = {"points": "pts", "pts": "pts", "point": "pts", "rebounds": "reb", "boards": "reb", "rebound": "reb",
              "assists": "ast", "dimes": "ast", "assist": "ast", "blocks": "blk", "block": "blk", "steals": "stl",
              "steal": "stl", "threes": "fg3m", "3s": "fg3m", "three-pointers": "fg3m", "3-pointers": "fg3m"}
TD_SQL = "((pts>=10)::int+(reb>=10)::int+(ast>=10)::int+(stl>=10)::int+(blk>=10)::int)"


def ascii_key(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace(".", "").replace("'", "").split())


@lru_cache(maxsize=1)
def player_index(eng):
    with eng.connect() as cx:
        rows = cx.execute(text("""
            SELECT p.player_id, p.name, p.name_key, COUNT(pg.game_id) AS games
            FROM players p LEFT JOIN player_games pg USING (player_id)
            GROUP BY p.player_id, p.name, p.name_key""")).fetchall()
    full, last = {}, {}
    for pid, name, key, games in rows:
        full[key] = (pid, name, games)
        last.setdefault(key.split()[-1], []).append((pid, name, games))
    return full, last


@lru_cache(maxsize=1)
def game_dates(eng):
    with eng.connect() as cx:
        return sorted(r[0] for r in cx.execute(text("SELECT DISTINCT game_date FROM games")).fetchall())


def _team_words():
    words = {}
    for abbr, (city, nick) in TEAMS.items():
        words[nick.lower()] = abbr
        if city not in ("LA", "Los Angeles", "New York"):
            words[city.lower()] = abbr
    words |= {k.lower(): v for k, v in TEAM_ALIASES.items() if not k.isupper()}
    words["new york"] = "NYK"
    return words


TEAM_WORDS = _team_words()


def parse(question: str, eng) -> dict:
    """Pull players, teams, dates and seasons out of a question."""
    question = re.sub(r"['’]s\b", "", question)  # possessives: "Trae Young's" -> "Trae Young"
    q_ascii = ascii_key(question)
    found = {"players": [], "teams": [], "dates": [], "season": None, "stats": []}
    full, last = player_index(eng)

    def has(phrase):
        return re.search(rf"(?<![\w-]){re.escape(phrase)}(?![\w-])", q_ascii) is not None

    for alias, name in PLAYER_ALIASES.items():
        if has(alias) and ascii_key(name) in full:
            found["players"].append(full[ascii_key(name)][:2])
    for key, (pid, name, _) in full.items():
        if len(key) > 4 and has(key) and (pid, name) not in found["players"]:
            found["players"].append((pid, name))
    if not found["players"]:
        # Typos: compare each two- or three-word span with known full names.
        toks = q_ascii.split()
        spans = {" ".join(toks[i:i + n]) for n in (2, 3) for i in range(len(toks) - n + 1)}
        best = None
        for span in spans:
            for key in difflib.get_close_matches(span, full.keys(), n=1, cutoff=0.88):
                score = difflib.SequenceMatcher(None, span, key).ratio()
                best = max(best or (0, None), (score, key))
        if best:
            found["players"].append(full[best[1]][:2])
    if not found["players"]:
        # A capitalized surname on its own ("How did Holmgren do?"), when only one regular has it.
        team_words = set(TEAM_WORDS)
        for word in re.findall(r"\b[A-Z][a-zA-Z'\-]+\b", question):
            k = ascii_key(word)
            cands = sorted(last.get(k, []), key=lambda c: -c[2])
            if k in team_words or not cands:
                continue
            if len(cands) == 1 or cands[0][2] >= 3 * cands[1][2]:
                found["players"].append(cands[0][:2])

    for word, abbr in sorted(TEAM_WORDS.items(), key=lambda kv: -len(kv[0])):
        if has(word) and abbr not in found["teams"]:
            found["teams"].append(abbr)
    for tok in re.findall(r"\b[A-Z]{2,4}\b", question):
        abbr = TEAM_ALIASES.get(tok, tok)
        if abbr in TEAMS and abbr not in found["teams"]:
            found["teams"].append(abbr)

    m = re.search(r"\b(20\d\d)[-–/](20)?(\d\d)\s*(season)?\b", q_ascii)
    if m and int(m.group(3)) == (int(m.group(1)) + 1) % 100:
        found["season"] = f"{m.group(1)}-{m.group(3)}"
    found["dates"] = _dates(q_ascii, eng)
    # "35+ points", "40 or more points", "at least 10 rebounds": numbers embeddings can't compare.
    stat_re = "|".join(sorted(map(re.escape, STAT_WORDS), key=len, reverse=True))
    for m in re.finditer(rf"(?:at least |over |more than )?(\d{{1,2}})\s*(\+|or more|plus)?\s*({stat_re})\b", q_ascii):
        n, col = int(m.group(1)), STAT_WORDS[m.group(3)]
        if m.group(2) or m.group(0).startswith(("at least", "over", "more than")) or "who" in q_ascii:
            n += 1 if m.group(0).startswith(("over", "more than")) else 0
            found["stats"].append((col, n))
    if "triple-double" in q_ascii or "triple double" in q_ascii:
        found["stats"].append(("triple_double", 3))
    return found


def _dates(q: str, eng) -> list:
    """Every date the question could mean. A date without a year matches each season it occurred in."""
    md, year = [], None
    for m in re.finditer(r"\b(20\d\d)-(\d\d)-(\d\d)\b", q):
        return [date(int(m.group(1)), int(m.group(2)), int(m.group(3)))]
    for m in re.finditer(r"(?<![\d-])(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?![\d/])", q):
        md.append((int(m.group(1)), int(m.group(2))))
        if m.group(3):
            y = int(m.group(3))
            year = y + 2000 if y < 100 else y
    month_re = "|".join(sorted(MONTHS, key=len, reverse=True))
    for m in re.finditer(rf"\b({month_re})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(20\d\d))?\b", q):
        md.append((MONTHS[m.group(1)], int(m.group(2))))
        year = int(m.group(3)) if m.group(3) else year
    for name, mmdd in HOLIDAYS.items():
        if mmdd and name in q:
            md.append(mmdd)
    out = []
    for mo, d in md:
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            continue
        out += [g for g in game_dates(eng) if g.month == mo and g.day == d and (year is None or g.year == year)]
    return sorted(set(out))


def or_query(question: str) -> str:
    """Full-text query that matches passages containing ANY of the question's words."""
    words = re.findall(r"[a-z0-9]+", ascii_key(question))
    return " | ".join(dict.fromkeys(words)) or "nba"


def _where(f: dict, params: dict, relax=()):
    where = ["embedding IS NOT NULL"]
    if f["players"] and "players" not in relax:
        where.append("player_id = ANY(:pids)"); params["pids"] = [p for p, _ in f["players"]]
    if f["teams"] and "teams" not in relax:
        where.append("teams @> CAST(:teams AS text[])"); params["teams"] = f["teams"][:2]
    if f["dates"] and "dates" not in relax:
        where.append("game_date = ANY(:dates)"); params["dates"] = f["dates"]
    if f["season"] and "season" not in relax:
        where.append("season = :season"); params["season"] = f["season"]
    if f.get("stats") and "stats" not in relax:
        conds = [f"{TD_SQL} >= 3" if col == "triple_double" else f"pg.{col} >= {int(n)}" for col, n in f["stats"]]
        where.append("kind = 'player_game' AND EXISTS (SELECT 1 FROM player_games pg WHERE pg.game_id = documents.game_id "
                     f"AND pg.player_id = documents.player_id AND {' AND '.join(conds)})")
    return " AND ".join(where)


def search(eng, question: str, k: int = 8, mode: str = "filtered", filters: dict = None) -> dict:
    """Return the k best passages and timing/usage details.

    mode: "filtered" (entity filters + embedding similarity; production), "vector"
    (embedding only, the baseline) or "fusion" (filters + embedding fused with
    full-text rank, which measured worse; see tests/retrieval_eval.py).
    """
    t0 = time.perf_counter()
    f = filters if filters is not None else (parse(question, eng) if mode != "vector" else
                                             {"players": [], "teams": [], "dates": [], "season": None, "stats": []})
    t_parse = time.perf_counter()
    qvec, embed_tokens = embed_query(question)
    t_embed = time.perf_counter()
    hits, relaxed = [], []
    for relax in ((), ("stats",), ("stats", "season"), ("stats", "season", "dates"), ("stats", "season", "dates", "teams"),
                  ("stats", "season", "dates", "teams", "players")):
        params = {"q": to_pgvector(qvec), "k": k, "ts": or_query(question)}
        where = _where(f, params, relax)
        filtered = where != "embedding IS NOT NULL"
        with eng.connect() as cx:
            if mode == "fusion":
                sql = f"""
                    WITH cand AS MATERIALIZED (SELECT doc_id, kind, content, embedding, tsv FROM documents WHERE {where}
                                               {'' if filtered else 'ORDER BY embedding <=> CAST(:q AS vector) LIMIT 200'}),
                         v AS (SELECT doc_id, ROW_NUMBER() OVER (ORDER BY embedding <=> CAST(:q AS vector)) AS r FROM cand),
                         t AS (SELECT doc_id, ROW_NUMBER() OVER (ORDER BY ts_rank_cd(tsv, to_tsquery('english', :ts)) DESC) AS r
                               FROM cand WHERE tsv @@ to_tsquery('english', :ts))
                    SELECT c.doc_id, c.kind, c.content,
                           COALESCE(1.0 / ({RRF_K} + v.r), 0) + COALESCE(1.0 / ({RRF_K} + t.r), 0) AS score
                    FROM cand c JOIN v USING (doc_id) LEFT JOIN t USING (doc_id)
                    ORDER BY score DESC LIMIT :k"""
            else:
                inner = f"SELECT doc_id, kind, content, embedding FROM documents WHERE {where}"
                sql = (f"WITH cand AS MATERIALIZED ({inner}) SELECT doc_id, kind, content, 1 - (embedding <=> CAST(:q AS vector)) AS score "
                       f"FROM cand ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k") if filtered else \
                      ("SELECT doc_id, kind, content, 1 - (embedding <=> CAST(:q AS vector)) AS score FROM documents "
                       "WHERE embedding IS NOT NULL ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k")
            hits = [dict(r._mapping) for r in cx.execute(text(sql), params)]
        if hits or not filtered:
            relaxed = list(relax)
            break
    t_done = time.perf_counter()
    return {
        "hits": hits,
        "filters": {"players": [n for _, n in f["players"]], "teams": f["teams"],
                    "dates": [d.isoformat() for d in f["dates"]], "season": f["season"],
                    "stats": [f"{c}>={n}" for c, n in f.get("stats", [])], "relaxed": relaxed},
        "timing_ms": {"parse": round((t_parse - t0) * 1000, 1), "embed": round((t_embed - t_parse) * 1000, 1),
                      "retrieve": round((t_done - t_embed) * 1000, 1)},
        "embed_tokens": embed_tokens,
    }
