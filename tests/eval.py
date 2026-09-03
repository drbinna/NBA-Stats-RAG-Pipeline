"""
Run natural-language questions through the agent and print pass/fail.
Usage:  POSTGRES_URL=... FIREWORKS_API_KEY=... BALLDONTLIE_API_KEY=... python -m tests.eval
Each entry is (question, substring expected in the answer). Edit to match your database.
"""
import time
from backend import server as s

EXPECTED = [
    ("How many points did SGA score on 4/8?", "points"),
    ("How did Chet do against the Lakers?", "Holmgren"),
    ("Who recorded triple-doubles?", "triple"),
    ("What games happened on Christmas?", "12-25"),
    ("Who had the most points in a single game?", "points"),
    ("What is SGA averaging?", "averag"),
    ("What did the Thunder do last night?", ""),      # routes to live data without erroring
    ("How many points did Chet score on 4/9?", ""),   # a day past the DB cutoff
    ("Tell me about a player who doesn't exist, Zorp Blatt", "not"),
]

if __name__ == "__main__":
    print("model:", s.MODEL_ID, "| db range:", s.db_date_range())
    passed = 0
    for q, expect in EXPECTED:
        t = time.time()
        r = s.run_agent(q)
        ok = expect.lower() in r["answer"].lower()
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'} {time.time()-t:4.1f}s {[c['tool'] for c in r['evidence']]}\n   Q: {q}\n   A: {r['answer'][:200]}\n")
    print(f"{passed}/{len(EXPECTED)} passed")
