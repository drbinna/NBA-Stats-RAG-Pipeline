"""
End-to-end evaluation: question in, answer out, checked against the database.

Each question's expected answer is computed from player_games and games, so the
check is exact rather than hand-written. Reports accuracy plus average latency,
tokens and cost per request (set MODEL_PRICE_INPUT_PER_M / MODEL_PRICE_OUTPUT_PER_M
to get cost).

Usage:  POSTGRES_URL=... FIREWORKS_API_KEY=... python -m tests.eval [--n 10] [--out eval/answer_results.json]
"""
import argparse
import json
import random
import re
import statistics

from sqlalchemy import text

from backend import server as s
from backend.teams import TEAMS


def cases(n, seed=11):
    rng = random.Random(seed)
    with s.eng.connect() as cx:
        lines = [dict(r._mapping) for r in cx.execute(text(
            "SELECT p.name, pg.game_date, pg.pts, pg.opponent FROM player_games pg JOIN players p USING (player_id) WHERE minutes >= 28"))]
        games = [dict(r._mapping) for r in cx.execute(text("SELECT * FROM games"))]
        leader = cx.execute(text("""SELECT p.name FROM player_games pg JOIN players p USING (player_id)
                                    WHERE season = (SELECT MAX(season) FROM games WHERE season < (SELECT MAX(season) FROM games))
                                       OR (SELECT COUNT(DISTINCT season) FROM games) = 1
                                    GROUP BY p.name HAVING COUNT(*) >= 50 ORDER BY AVG(ast) DESC LIMIT 1""")).scalar()
    out = []
    for r in rng.sample(lines, n):
        d = r["game_date"]
        out.append((f"How many points did {r['name']} score against the {TEAMS[r['opponent']][1]} on {d.strftime('%B')} {d.day}, {d.year}?",
                    [str(r["pts"])]))
    for g in rng.sample(games, n):
        d = g["game_date"]
        out.append((f"Who won the {TEAMS[g['home_team']][1]} vs {TEAMS[g['away_team']][1]} game on {d.month}/{d.day}/{d.year}, and what was the score?",
                    [TEAMS[g["winner"]][1], str(max(g["home_points"], g["away_points"])), str(min(g["home_points"], g["away_points"]))]))
    out.append(("Who averaged the most assists per game last season? Minimum 50 games.", [leader.split()[-1]]))
    out.append(("How many points did Zorp Blatt score last night?", ["n't", "no ", "not"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--out", default="eval/answer_results.json")
    args = ap.parse_args()
    results = []
    for q, expect in cases(args.n):
        r = s.run_agent(q)
        a = r["answer"].lower()
        # The last case passes if any refusal phrase appears; the rest need every expected value.
        ok = any(e in a for e in expect) if "n't" in expect else all(re.search(rf"\b{re.escape(e.lower())}\b", a) for e in expect)
        results.append({"q": q, "expect": expect, "answer": r["answer"], "ok": ok, "usage": r["usage"]})
        print(f"{'PASS' if ok else 'FAIL'} {r['usage']['latency_ms'] / 1000:4.1f}s  {q}\n      {r['answer'][:160]}")
    u = [x["usage"] for x in results]
    costs = [x["cost_usd"] for x in u if x["cost_usd"] is not None]
    summary = {"model": s.MODEL_ID, "questions": len(results), "accuracy": round(sum(x["ok"] for x in results) / len(results), 3),
               "latency_ms_p50": statistics.median(x["latency_ms"] for x in u),
               "avg_input_tokens": round(statistics.mean(x["input_tokens"] for x in u)),
               "avg_output_tokens": round(statistics.mean(x["output_tokens"] for x in u)),
               "avg_cost_usd": round(statistics.mean(costs), 6) if costs else None}
    with open(args.out, "w") as fh:
        json.dump({"summary": summary, "results": results}, fh, indent=2, default=str)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
