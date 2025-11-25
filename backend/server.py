from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlalchemy as sa
from backend.config import DB_DSN, EMBED_MODEL, LLM_MODEL
from backend.utils import ollama_embed, ollama_generate
from sqlalchemy import text

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
eng = sa.create_engine(DB_DSN)


class Q(BaseModel):
    question: str


@app.post("/api/chat")
def answer(q: Q):
    print('Received question')
    qvec = ollama_embed(EMBED_MODEL, q.question)
    with eng.begin() as cx:
       rows = cx.execute(
            text(
                "SELECT game_id, game_timestamp, home_team_id, away_team_id, home_points, away_points "
                "FROM game_details ORDER BY embedding <-> :q LIMIT :k"
            ),
            {"q": qvec, "k": 5},
        ).mappings().all()
    ctx = "\n".join([str(dict(r)) for r in rows])
    resp = ollama_generate(LLM_MODEL, f"Use context only:\n{ctx}\n\nQ:{q.question}\nA:")
    return {
            "answer": resp,
            "evidence": [{"table": "game_details", "id": int(r["game_id"])} for r in rows],
        }