import os

DB_DSN = os.getenv("POSTGRES_URL") or os.getenv("DB_DSN", "postgresql://ragchatbotbackend_user:XJS3FqDsbqYIK55Z0wPtpNCX3DWATiIO@dpg-d5b1ko3uibrs73c52sig-a.oregon-postgres.render.com/ragchatbotbackend")
if DB_DSN and DB_DSN.startswith("postgres://"):
    DB_DSN = DB_DSN.replace("postgres://", "postgresql://", 1)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BALLDONTLIE_API_KEY = os.getenv("BALLDONTLIE_API_KEY")
