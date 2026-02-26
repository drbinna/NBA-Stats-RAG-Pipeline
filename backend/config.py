import os

# Prioritize Vercel/Neon variables
DB_DSN = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL") or os.getenv("DB_DSN")

if DB_DSN and DB_DSN.startswith("postgres://"):
    DB_DSN = DB_DSN.replace("postgres://", "postgresql://", 1)

# Debug printing for Vercel logs
import re
if DB_DSN:
    masked_dsn = re.sub(r':([^:@]+)@', ':***@', DB_DSN)
    print(f"DATABASE CONFIG: Loaded DSN {masked_dsn}")
else:
    print("DATABASE CONFIG: No database DSN found in environment variables!")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BALLDONTLIE_API_KEY = os.getenv("BALLDONTLIE_API_KEY")

# Debug print (will show in Vercel logs)
import re
masked_dsn = re.sub(r':([^:@]+)@', ':***@', DB_DSN)
print(f"DATABASE CONFIG: Using DSN {masked_dsn}")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BALLDONTLIE_API_KEY = os.getenv("BALLDONTLIE_API_KEY")
