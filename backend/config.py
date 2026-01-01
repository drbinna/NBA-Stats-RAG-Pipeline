import os

DB_DSN = os.getenv("DB_DSN", "postgresql://nba:nba@localhost:5432/nba")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BALLDONTLIE_API_KEY = os.getenv("BALLDONTLIE_API_KEY")
