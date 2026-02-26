import os

# Prioritize Vercel/Neon variables
DB_DSN = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL") or os.getenv("DB_DSN")

if not DB_DSN:
    # Hardcoded fallback (Render) - only used if no environment variables are set
    DB_DSN = "postgresql://ragchatbotbackend_user:XJS3FqDsbqYIK55Z0wPtpNCX3DWATiIO@dpg-d5b1ko3uibrs73c52sig-a.oregon-postgres.render.com/ragchatbotbackend"

if DB_DSN.startswith("postgres://"):
    DB_DSN = DB_DSN.replace("postgres://", "postgresql://", 1)

# Debug print (will show in Vercel logs)
import re
masked_dsn = re.sub(r':([^:@]+)@', ':***@', DB_DSN)
print(f"DATABASE CONFIG: Using DSN {masked_dsn}")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BALLDONTLIE_API_KEY = os.getenv("BALLDONTLIE_API_KEY")
