import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS shops (
 id TEXT PRIMARY KEY,
 shop_name TEXT NOT NULL CHECK(length(trim(shop_name)) > 0),
 registered_phone_number TEXT NOT NULL UNIQUE,
 pin_hash TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 id TEXT PRIMARY KEY,
 shop_id TEXT NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
 caller_phone_number TEXT NOT NULL,
 call_id TEXT,
 created_at TEXT NOT NULL,
 expires_at TEXT NOT NULL,
 is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1))
);
CREATE INDEX IF NOT EXISTS idx_sessions_shop_active ON sessions(shop_id, is_active, expires_at);
CREATE TABLE IF NOT EXISTS udhaar (
 id TEXT PRIMARY KEY,
 shop_id TEXT NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
 customer_name TEXT NOT NULL,
 customer_phone_number TEXT NOT NULL,
 customer_address TEXT NOT NULL,
 due_amount INTEGER NOT NULL CHECK(due_amount > 0),
 idempotency_key TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(shop_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_udhaar_shop_created ON udhaar(shop_id, created_at);
"""

def database_path() -> str:
    return os.getenv("DATABASE_PATH", "./dukaan_saathi.sqlite3")

def connect(path: str | None = None) -> sqlite3.Connection:
    db_path = path or database_path()
    if db_path != ":memory:":
        Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db(path: str | None = None) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)

@contextmanager
def transaction(path: str | None = None):
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
