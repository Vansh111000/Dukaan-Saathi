import sqlite3

import mongomock

from dukaan_saathi.migrate_sqlite_to_mongodb import migrate
from dukaan_saathi.mongodb import mongo_manager
from dukaan_saathi.security import hash_pin


def make_source(path):
    conn = sqlite3.connect(path)
    conn.executescript("""
    CREATE TABLE shops(id TEXT PRIMARY KEY, shop_name TEXT, registered_phone_number TEXT, pin_hash TEXT, created_at TEXT);
    CREATE TABLE sessions(id TEXT PRIMARY KEY, shop_id TEXT, caller_phone_number TEXT, call_id TEXT, created_at TEXT, expires_at TEXT, is_active INTEGER);
    CREATE TABLE udhaar(id TEXT PRIMARY KEY, shop_id TEXT, customer_name TEXT, customer_phone_number TEXT, customer_address TEXT, due_amount INTEGER, idempotency_key TEXT, created_at TEXT);
    """)
    conn.execute("INSERT INTO shops VALUES(?,?,?,?,?)", ("shop-1", "A", "+919876543210", hash_pin("1234"), "2026-01-01T00:00:00+00:00"))
    conn.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?)", ("session-1", "shop-1", "+919876543210", "call-1", "2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00", 0))
    conn.execute("INSERT INTO udhaar VALUES(?,?,?,?,?,?,?,?)", ("entry-1", "shop-1", "Ravi", "+919876543211", "Main Road", 300, "key-12345678", "2026-01-01T00:00:00+00:00"))
    conn.commit()
    conn.close()


def setup_target(monkeypatch):
    db = mongomock.MongoClient()["migration_test"]
    original_connect, original_close = mongo_manager.connect, mongo_manager.close
    def fake_connect():
        mongo_manager._database = db
        return db
    monkeypatch.setattr(mongo_manager, "connect", fake_connect)
    monkeypatch.setattr(mongo_manager, "close", lambda: setattr(mongo_manager, "_database", None))
    for coll in ("shops", "sessions", "udhaar"):
        db[coll].create_index("_id", unique=True)
    db.shops.create_index("registered_phone_number", unique=True)
    db.udhaar.create_index([("shop_id", 1), ("idempotency_key", 1)], unique=True)
    return db


def test_migration_preserves_records_and_is_rerunnable(tmp_path, monkeypatch):
    source = tmp_path / "source.sqlite3"
    make_source(source)
    db = setup_target(monkeypatch)
    first = migrate(str(source))
    assert first["verification"]["passed"] is True
    assert first["collections"]["shops"]["migrated_records"] == 1
    assert first["collections"]["sessions"]["migrated_records"] == 1
    assert first["collections"]["udhaar"]["migrated_records"] == 1
    assert db.shops.find_one({"_id":"shop-1"})["shop_name"] == "A"
    assert db.sessions.find_one({"_id":"session-1"})["shop_id"] == "shop-1"
    assert db.udhaar.find_one({"_id":"entry-1"})["idempotency_key"] == "key-12345678"
    second = migrate(str(source))
    assert second["verification"]["passed"] is True
    assert second["skipped_records"] == 3
    assert db.udhaar.count_documents({}) == 1


def test_migration_does_not_overwrite_conflicting_mongo_record(tmp_path, monkeypatch):
    source = tmp_path / "source.sqlite3"
    make_source(source)
    db = setup_target(monkeypatch)
    db.shops.insert_one({"_id":"shop-1", "shop_name":"Existing", "registered_phone_number":"+919876543210", "pin_hash":"existing", "created_at":"old"})
    result = migrate(str(source))
    assert result["failed_records"] == 1
    assert result["verification"]["passed"] is False
    assert db.shops.find_one({"_id":"shop-1"})["shop_name"] == "Existing"
