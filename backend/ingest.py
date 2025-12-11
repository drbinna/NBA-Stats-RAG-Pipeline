import os
import pandas as pd
import sqlalchemy as sa
from sqlalchemy import text
from pathlib import Path
from io import StringIO
from backend.config import DB_DSN

# Load tables in dependency order: teams, players, game_details, player_box_scores
TABLES = ["teams", "players", "game_details", "player_box_scores"]
DATA_DIR = Path(__file__).resolve().parent / "data"

def main():
    print('Starting Database Ingestion')
    eng = sa.create_engine(DB_DSN)
    with eng.begin() as cx:
        # Ensure pgvector extension is available for the `vector` type used to store embeddings
        cx.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        
        # Get raw psycopg2 connection for COPY command
        raw_conn = cx.connection.dbapi_connection
        cursor = raw_conn.cursor()
        
        for table_name in TABLES:
            path = os.path.join(DATA_DIR, f"{table_name}.csv")
            if not os.path.exists(path):
                print(f"Warning: {path} not found, skipping {table_name}")
                continue
            
            print(f"Loading {table_name}...")
            df = pd.read_csv(path)
            
            # Create empty table schema first
            df.head(0).to_sql(table_name, cx, if_exists="replace", index=False)
            
            # Convert DataFrame to CSV format in memory
            buffer = StringIO()
            df.to_csv(buffer, index=False, header=False, na_rep='')
            buffer.seek(0)
            
            # Use COPY command for fast bulk loading
            copy_sql = f"COPY {table_name} FROM STDIN WITH CSV"
            cursor.copy_expert(copy_sql, buffer)
            
            # Get row count using cursor (table_name is from whitelist, safe)
            # Validate table_name is in whitelist to prevent SQL injection
            if table_name not in TABLES:
                raise ValueError(f"Invalid table name: {table_name}")
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cursor.fetchone()[0]
            print(f"  ✓ Loaded {row_count:,} rows into {table_name}")
        
        cursor.close()
    print('Finished Database Ingestion')


if __name__ == "__main__":
    main()
