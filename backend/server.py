from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlalchemy as sa
from backend.config import DB_DSN
from backend.rag import answer_question
import json
import os

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
eng = sa.create_engine(DB_DSN)

# Load questions.json for return_schema lookup
BASE_DIR = os.path.dirname(__file__)
QUESTIONS_PATH = os.path.normpath(os.path.join(BASE_DIR, "..", "part1", "questions.json"))


class Q(BaseModel):
    question: str


def infer_return_schema(question: str):
    """Heuristic return schema when the question isn't an exact match."""
    ql = question.lower()

    def player_schema(include_reb=False, include_ast=False):
        schema = {
            "player_name": "str",
            "points": "int",
            "evidence": [{"table": "player_box_score", "id": "int"}],
        }
        if include_reb:
            schema["rebounds"] = "int"
        if include_ast:
            schema["assists"] = "int"
        return schema

    # Triple-double: need points, rebounds, assists
    if "triple-double" in ql or "triple double" in ql:
        return player_schema(include_reb=True, include_ast=True)

    # Leading scorer or points by a player
    scorer_keywords = [
        "leading scorer",
        "top scorer",
        "how many points",
        "score did",
        "points did",
        "points on",
        "had 40 points",
    ]
    if any(k in ql for k in scorer_keywords):
        return player_schema()

    # Fallback to game schema
    return {
        "answer": "str",
        "evidence": [{"table": "game_details", "id": "int"}],
    }


@app.post("/api/chat")
def answer(q: Q):
    """Answer question using full RAG pipeline with cached embeddings"""
    try:
        print(f'Received question: {q.question[:60]}...')
        
        # Try to find matching return_schema from questions.json
        return_schema = None
        try:
            with open(QUESTIONS_PATH, 'r') as f:
                questions = json.load(f)
                for question_obj in questions:
                    if question_obj['question'] == q.question:
                        return_schema = question_obj['return']
                        break
        except Exception as e:
            print(f'Error loading questions.json: {e}')
        
        # Default schema if not found
        if return_schema is None:
            return_schema = infer_return_schema(q.question)
        
        # Use full RAG pipeline (with cached embeddings)
        with eng.begin() as cx:
            result = answer_question(cx, q.question, return_schema)
        
        if result:
            # Return answer text and evidence
            answer_text = result.get('answer', '')
            if not answer_text:
                # Fallback: create answer from structured data
                answer_text = json.dumps({k: v for k, v in result.items() if k != 'evidence'})
            
            return {
                "answer": answer_text,
                "evidence": result.get('evidence', [])
            }
        else:
            return {
                "answer": "No data found for this question.",
                "evidence": []
            }
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        print(f'Error in /api/chat: {error_msg}')
        return {
            "answer": f"Error processing question: {error_msg}",
            "evidence": []
        }