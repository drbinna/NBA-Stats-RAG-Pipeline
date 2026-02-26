import os
import re

# Prioritize Vercel/Neon variables
DB_DSN = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL") or os.getenv("DB_DSN")

if DB_DSN:
    if DB_DSN.startswith("postgres://"):
        DB_DSN = DB_DSN.replace("postgres://", "postgresql://", 1)
    
    # Mask password for logging
    masked_dsn = re.sub(r':([^:@]+)@', ':***@', DB_DSN)
    print(f"DATABASE CONFIG: Loaded DSN {masked_dsn}")
else:
    print("DATABASE CONFIG: CRITICAL ERROR - No database DSN found in environment variables!")
    # We don't raise an error here to allow the health check to work for diagnostics
    DB_DSN = ""

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BALLDONTLIE_API_KEY = os.getenv("BALLDONTLIE_API_KEY")

if not ANTHROPIC_API_KEY:
    print("API CONFIG: CRITICAL ERROR - ANTHROPIC_API_KEY is missing!")
if not BALLDONTLIE_API_KEY:
    print("API CONFIG: CRITICAL ERROR - BALLDONTLIE_API_KEY is missing!")
