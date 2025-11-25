import os
import json
import sqlalchemy as sa
from sqlalchemy import text
from backend.config import DB_DSN, EMBED_MODEL, LLM_MODEL
from backend.utils import ollama_embed, ollama_generate

BASE_DIR = os.path.dirname(__file__)
QUESTIONS_PATH = os.path.normpath(os.path.join(BASE_DIR, "..", "part1", "questions.json"))
ANSWERS_PATH = os.path.normpath(os.path.join(BASE_DIR, "..", "part1", "answers.json"))
TEMPLATE_PATH = os.path.normpath(os.path.join(BASE_DIR, "..", "part1", "answers_template.json"))


def retrieve(cx, qvec, k=5):
    sql = (
       "SELECT game_id, game_timestamp, home_team_id, away_team_id, home_points, away_points, "
        "1 - (embedding <=> (:q)::vector) AS score FROM game_details ORDER BY embedding <-> (:q)::vector LIMIT :k"
    )
    return cx.execute(text(sql), {"q": qvec, "k": k}).mappings().all()


def build_context(rows):
    return "\n".join(
        [
            f"{r['game_id']} {r['game_timestamp']} {r['home_team_id']} vs {r['away_team_id']} {r['home_points']}-{r['away_points']}"
            for r in rows
        ]
    )


# Feel free to edit this prompt, but ensure it still uses context directly from the embeddings
def answer(question, rows):
    # Use answers template in the response
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        answers_template = json.load(f)
    ctx = build_context(rows)
    prompt = (
        f"Use this format to answer the questions:\n{json.dumps(answers_template)}\n"
        f"Answer using only this context. Cite game_ids used.\n"
        f"Context:\n{ctx}\n\nQ: {question}\nA:"
    )
    return ollama_generate(LLM_MODEL, prompt)


if __name__ == "__main__":
    eng = sa.create_engine(DB_DSN)
    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        qs = json.load(f)
    outs = []
    with eng.begin() as cx:
        for q in qs:
            qvec = ollama_embed(EMBED_MODEL, q["question"])
            rows = retrieve(cx, qvec, 5)
            ans = answer(q["question"], rows)
            outs.append({
                "answer": ans,
                "evidence": [{"table": "game_details", "id": int(r["game_id"])} for r in rows],
            })
    with open(ANSWERS_PATH, "w", encoding="utf-8") as f:
        json.dump(outs, f, ensure_ascii=False, indent=2)
