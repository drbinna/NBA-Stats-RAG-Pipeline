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
# SQLAlchemy URL with the driver named, since newer SQLAlchemy defaults to psycopg 3.
SA_DSN = DB_DSN.replace("postgresql://", "postgresql+psycopg2://", 1) if DB_DSN else None

# Generation runs on Fireworks AI through its Anthropic-compatible endpoint.
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")
MODEL_ID = os.getenv("MODEL_ID", "accounts/fireworks/models/deepseek-v4p1-flash")

# Embeddings: nomic-embed-text-v1.5 (768 dimensions). "fireworks" calls the hosted model;
# "local" runs the same model on this machine with fastembed (ingest and evaluation only).
EMBED_PROVIDER = os.getenv("EMBED_PROVIDER", "fireworks")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-ai/nomic-embed-text-v1.5")
EMBED_DIM = 768

# Optional prices in US dollars per million tokens, used to report cost per request.
def _price(name):
    v = os.getenv(name)
    return float(v) if v else None

PRICE_IN_PER_M = _price("MODEL_PRICE_INPUT_PER_M")
PRICE_OUT_PER_M = _price("MODEL_PRICE_OUTPUT_PER_M")
EMBED_PRICE_PER_M = _price("EMBED_PRICE_PER_M") or 0.008
