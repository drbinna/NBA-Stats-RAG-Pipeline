import os

# Prioritize Vercel/Neon variables (including common prefixes like RAG_URL_)
DB_DSN = (
    os.getenv("RAG_URL_POSTGRES_URL")
    or os.getenv("RAG_URL_DATABASE_URL")
    or os.getenv("POSTGRES_URL")
    or os.getenv("DATABASE_URL")
    or os.getenv("DB_DSN")
)

if DB_DSN and DB_DSN.startswith("postgres://"):
    DB_DSN = DB_DSN.replace("postgres://", "postgresql://", 1)

# Model runs on Fireworks AI through its Anthropic-compatible endpoint.
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")
MODEL_ID = os.getenv("MODEL_ID", "accounts/fireworks/models/qwen3p7-plus")

BALLDONTLIE_API_KEY = os.getenv("BALLDONTLIE_API_KEY")
