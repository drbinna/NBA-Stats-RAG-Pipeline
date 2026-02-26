import os

# Prioritize Vercel/Neon variables
DB_DSN = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL") or os.getenv("DB_DSN")

if not DB_DSN:
    raise ValueError("ERROR: No database connection string found in environment variables (POSTGRES_URL, DATABASE_URL, or DB_DSN). Please link your Neon database in the Vercel 'Storage' tab.")

if DB_DSN.startswith("postgres://"):
    DB_DSN = DB_DSN.replace("postgres://", "postgresql://", 1)

# Debug print (will show in Vercel logs)
import re
masked_dsn = re.sub(r':([^:@]+)@', ':***@', DB_DSN)
print(f"DATABASE CONFIG: Using DSN {masked_dsn}")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BALLDONTLIE_API_KEY = os.getenv("BALLDONTLIE_API_KEY")
