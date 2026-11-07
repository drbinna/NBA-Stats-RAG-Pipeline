"""
Retrieval evaluation: does the right passage come back?

Builds a labeled question set from the database (seeded, so it is the same every
run), sends each question through three retrieval modes and reports Recall@1/5/10,
MRR@10, how often the parser found the right entities, and retrieval latency.

    vector    embedding similarity only (baseline)
    filtered  entity filters (player, team, date, season, stat threshold) + embedding similarity (production)
    fusion    filters + embedding similarity fused with full-text rank (reciprocal rank fusion)

Two sets: "standard" (template questions with clean names and dates) and "hard"
(typos, unknown nicknames, players described by their stats, city names only).

Usage:  POSTGRES_URL=... python -m tests.retrieval_eval [--set standard|hard] [--n 40]
Embeddings use EMBED_PROVIDER, the same as ingestion.
"""
import argparse
import json
import random
import statistics
import time

import sqlalchemy as sa
from sqlalchemy import text

from backend import retrieval
from backend.config import SA_DSN, EMBED_MODEL, EMBED_PROVIDER
from backend.teams import TEAMS

MODES = ["vector", "filtered", "fusion"]
ALIAS_OF = {v: k for k, v in retrieval.PLAYER_ALIASES.items() if len(k) > 2}


def fmt_date(d, rng):
    return rng.choice([f"{d.month}/{d.day}", f"{d.strftime('%B')} {d.day}", f"{d.strftime('%B')} {d.day}, {d.year}",
                       f"{d.month}/{d.day}/{d.year}", f"{d.strftime('%b')} {d.day}"])


def player_ref(name, rng):
    if name in ALIAS_OF and rng.random() < 0.5:
        return ALIAS_OF[name].upper() if len(ALIAS_OF[name]) <= 3 else ALIAS_OF[name].title()
    return name


def build_questions(eng, n, seed=7):
    rng = random.Random(seed)
    with eng.connect() as cx:
        lines = [dict(r._mapping) for r in cx.execute(text("""
            SELECT pg.game_id, pg.player_id, p.name, pg.game_date, pg.team, pg.opponent, pg.pts, pg.reb, pg.ast,
                   ((pts>=10)::int+(reb>=10)::int+(ast>=10)::int+(stl>=10)::int+(blk>=10)::int) >= 3 AS td
            FROM player_games pg JOIN players p USING (player_id) WHERE pg.minutes >= 24"""))]
        games = [dict(r._mapping) for r in cx.execute(text("SELECT * FROM games"))]
    qs = []
    for r in rng.sample(lines, n):
        qs.append({"type": "player_on_date", "gold": [f"line:{r['game_id']}:{r['player_id']}"],
                   "expect": {"player": r["name"], "date": r["game_date"].isoformat()},
                   "q": rng.choice(["How many points did {p} score on {d}?", "What was {p}'s stat line on {d}?",
                                    "How many rebounds did {p} have on {d}?"]).format(p=player_ref(r["name"], rng), d=fmt_date(r["game_date"], rng))})
    for r in rng.sample(lines, n):
        opp = TEAMS[r["opponent"]][1]
        qs.append({"type": "player_vs_team_on_date", "gold": [f"line:{r['game_id']}:{r['player_id']}"],
                   "expect": {"player": r["name"], "team": r["opponent"], "date": r["game_date"].isoformat()},
                   "q": f"How did {player_ref(r['name'], rng)} play against the {opp} on {fmt_date(r['game_date'], rng)}?"})
    for g in rng.sample(games, n):
        a, b = rng.sample([g["home_team"], g["away_team"]], 2)
        tmpl = rng.choice(["Who won the {a} vs {b} game on {d}?", "What was the final score of {a} and {b} on {d}?",
                           "Did the {a} beat the {b} on {d}?"])
        qs.append({"type": "game_result", "gold": [f"game:{g['game_id']}"], "expect": {"team": a, "date": g["game_date"].isoformat()},
                   "q": tmpl.format(a=TEAMS[a][1], b=TEAMS[b][1], d=fmt_date(g["game_date"], rng))})
    # Questions with no date: the right answer is any passage in the gold set.
    tds = {}
    for r in lines:
        if r["td"]:
            tds.setdefault((r["player_id"], r["name"], r["opponent"]), []).append(f"line:{r['game_id']}:{r['player_id']}")
    for (pid, name, opp), gold in rng.sample(sorted(tds.items()), min(n, len(tds))):
        qs.append({"type": "triple_double_vs_team", "gold": gold, "expect": {"player": name, "team": opp},
                   "q": f"When did {player_ref(name, rng)} have a triple-double against the {TEAMS[opp][1]}?"})
    return qs


FIRST_NAMES = {"Zion Williamson": "Zion", "Bam Adebayo": "Bam", "Kawhi Leonard": "Kawhi", "Trae Young": "Trae",
               "Damian Lillard": "Dame", "Ja Morant": "Ja", "Domantas Sabonis": "Sabonis", "Jimmy Butler": "Jimmy Buckets"}


def misspell(name, rng):
    first, *rest = name.split(" ", 1)
    if not rest or len(rest[0]) < 5:
        return name
    last = rest[0]
    i = rng.randrange(1, len(last) - 1)
    return f"{first} {last[:i]}{last[i + 1:]}"


def build_hard_questions(eng, n, seed=13):
    """Questions written the way people actually ask: typos, first names and nicknames the parser
    doesn't know, players described by what they did instead of who they are, and cities."""
    rng = random.Random(seed)
    with eng.connect() as cx:
        lines = [dict(r._mapping) for r in cx.execute(text("""
            SELECT pg.*, p.name FROM player_games pg JOIN players p USING (player_id) WHERE pg.minutes >= 24"""))]
        games = [dict(r._mapping) for r in cx.execute(text("SELECT * FROM games"))]
    by_game = {}
    for r in lines:
        by_game.setdefault(r["game_id"], []).append(r)
    qs = []
    for r in rng.sample([r for r in lines if len(r["name"].split(" ", 1)[-1]) >= 6], n):
        qs.append({"type": "misspelled_name", "gold": [f"line:{r['game_id']}:{r['player_id']}"], "expect": {"date": r["game_date"].isoformat()},
                   "q": f"how many points did {misspell(r['name'], rng).lower()} score on {fmt_date(r['game_date'], rng)}"})
    known = [r for r in lines if r["name"] in FIRST_NAMES]
    for r in rng.sample(known, min(n, len(known))):
        qs.append({"type": "unknown_nickname", "gold": [f"line:{r['game_id']}:{r['player_id']}"], "expect": {"date": r["game_date"].isoformat()},
                   "q": f"What did {FIRST_NAMES[r['name']]} do against {TEAMS[r['opponent']][0]} on {fmt_date(r['game_date'], rng)}?"})
    big = [r for r in lines if r["pts"] >= 35]
    for r in rng.sample(big, min(n, len(big))):
        gold = [f"line:{x['game_id']}:{x['player_id']}" for x in by_game[r["game_id"]] if x["pts"] >= 35 and x["team"] == r["team"]]
        qs.append({"type": "described_not_named", "gold": gold, "expect": {"team": r["team"], "date": r["game_date"].isoformat()},
                   "q": f"Who dropped {r['pts'] // 5 * 5}+ points for the {TEAMS[r['team']][1]} on {fmt_date(r['game_date'], rng)}?"})
    for g in rng.sample(games, n):
        a, b = TEAMS[g["away_team"]][0], TEAMS[g["home_team"]][0]
        qs.append({"type": "cities_only", "gold": [f"game:{g['game_id']}"], "expect": {"date": g["game_date"].isoformat()},
                   "q": f"{a} at {b}, {fmt_date(g['game_date'], rng)}. What was the final?"})
    return qs


def score(hits, gold):
    ids = [h["doc_id"] for h in hits]
    rank = next((i + 1 for i, d in enumerate(ids) if d in gold), None)
    return {"r1": rank == 1, "r5": rank is not None and rank <= 5, "r10": rank is not None and rank <= 10,
            "rr": 1 / rank if rank else 0.0}


def parse_ok(eng, q):
    f = retrieval.parse(q["q"], eng)
    e = q["expect"]
    ok = True
    if "player" in e:
        ok &= e["player"] in [n for _, n in f["players"]]
    if "team" in e:
        ok &= e["team"] in f["teams"]
    if "date" in e:
        ok &= e["date"] in [d.isoformat() for d in f["dates"]]
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40, help="questions per type")
    ap.add_argument("--set", choices=["standard", "hard"], default="standard")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    eng = sa.create_engine(SA_DSN)
    with eng.connect() as cx:
        corpus = cx.execute(text("SELECT COUNT(*) FROM documents WHERE embedding IS NOT NULL")).scalar()
        seasons = [r[0] for r in cx.execute(text("SELECT DISTINCT season FROM documents ORDER BY 1"))]
    qs = build_questions(eng, args.n) if args.set == "standard" else build_hard_questions(eng, args.n)
    args.out = args.out or f"eval/retrieval_{args.set}.json"
    print(f"{len(qs)} questions over {corpus:,} passages ({', '.join(seasons)}), embeddings: {EMBED_PROVIDER} {EMBED_MODEL}")
    rows, lat, failures = {m: [] for m in MODES}, {m: [] for m in MODES}, []
    parse_hits = []
    for i, q in enumerate(qs):
        parse_hits.append(parse_ok(eng, q))
        for m in MODES:
            t = time.perf_counter()
            res = retrieval.search(eng, q["q"], k=10, mode=m)
            lat[m].append((time.perf_counter() - t) * 1000)
            s = score(res["hits"], set(q["gold"])) | {"type": q["type"]}
            rows[m].append(s)
            if m == "filtered" and not s["r1"]:
                failures.append({"q": q["q"], "gold": q["gold"][:3], "got": [h["doc_id"] for h in res["hits"][:3]], "filters": res["filters"]})
        if (i + 1) % 40 == 0:
            print(f"  {i + 1}/{len(qs)}")

    def agg(rs):
        n = len(rs)
        return {"n": n, "recall@1": round(sum(r["r1"] for r in rs) / n, 3), "recall@5": round(sum(r["r5"] for r in rs) / n, 3),
                "recall@10": round(sum(r["r10"] for r in rs) / n, 3), "mrr@10": round(sum(r["rr"] for r in rs) / n, 3)}

    types = sorted({q["type"] for q in qs})
    report = {"set": args.set, "corpus_passages": corpus, "seasons": seasons, "embedding": f"{EMBED_PROVIDER}:{EMBED_MODEL}", "questions": len(qs),
              "entity_parse_accuracy": round(sum(parse_hits) / len(parse_hits), 3), "modes": {}}
    for m in MODES:
        report["modes"][m] = {"overall": agg(rows[m]), "by_type": {t: agg([r for r in rows[m] if r["type"] == t]) for t in types},
                              "latency_ms": {"p50": round(statistics.median(lat[m]), 1),
                                             "p95": round(sorted(lat[m])[int(0.95 * len(lat[m])) - 1], 1)}}
    report["production_misses_at_1"] = failures[:25]
    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=2, default=str)
    print(f"\nentity parse accuracy: {report['entity_parse_accuracy']:.1%}")
    print(f"{'mode':10} {'R@1':>6} {'R@5':>6} {'R@10':>6} {'MRR':>6} {'p50 ms':>8}")
    for m in MODES:
        o = report["modes"][m]["overall"]
        print(f"{m:10} {o['recall@1']:6.1%} {o['recall@5']:6.1%} {o['recall@10']:6.1%} {o['mrr@10']:6.3f} {report['modes'][m]['latency_ms']['p50']:8.1f}")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
