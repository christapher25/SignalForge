import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
import config

engine = create_engine(f"sqlite:///{config.DB_PATH}")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    schema_path = BASE_DIR / 'db' / 'schema.sql'

    with open(schema_path, 'r') as f:
        schema_sql = f.read()

    with engine.begin() as conn:
        for statement in schema_sql.split(';'):
            stmt = statement.strip()
            if stmt:
                conn.execute(text(stmt))


if __name__ == "__main__":
    init_db()