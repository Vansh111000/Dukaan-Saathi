"""Safely copy SQLite shops, sessions, and udhaar into MongoDB without overwrites."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

from pymongo.errors import DuplicateKeyError, PyMongoError

from .database import database_path
from .mongodb import mongo_manager

COLLECTION_FIELDS = {
    "shops": ("shop_name", "registered_phone_number", "pin_hash", "created_at"),
    "sessions": ("shop_id", "caller_phone_number", "call_id", "created_at", "expires_at", "is_active"),
    "udhaar": ("shop_id", "customer_name", "customer_phone_number", "customer_address", "due_amount", "idempotency_key", "created_at"),
}

def source_document(table, row):
    values = dict(row)
    document = {"_id": values.pop("id")}
    document.update(values)
    return document

def migrate(sqlite_path: str, dry_run: bool = False) -> dict:
    report = {
        "sqlite_path": sqlite_path,
        "mongo_database": None,
        "dry_run": dry_run,
        "collections": {},
        "skipped_records": 0,
        "failed_records": 0,
        "verification": {"passed": False, "source_records_checked": 0, "matching_records": 0, "issues": []},
    }
    db = mongo_manager.connect()
    report["mongo_database"] = db.name
    source = sqlite3.connect(sqlite_path)
    source.row_factory = sqlite3.Row
    try:
        for table, fields in COLLECTION_FIELDS.items():
            rows = source.execute(f"SELECT * FROM {table}").fetchall()
            collection = db[table]
            migrated = skipped = failed = matched = 0
            for row in rows:
                doc = source_document(table, row)
                try:
                    existing = collection.find_one({"_id": doc["_id"]})
                    if existing is not None:
                        if all(existing.get(key) == doc.get(key) for key in ("_id", *fields)):
                            skipped += 1
                            matched += 1
                        else:
                            failed += 1
                            report["verification"]["issues"].append(f"{table}: conflicting existing record for source ID {doc['_id']}")
                        continue
                    if dry_run:
                        migrated += 1
                        matched += 1
                        continue
                    collection.insert_one(doc)
                    migrated += 1
                    matched += 1
                except (DuplicateKeyError, PyMongoError, ValueError, TypeError) as exc:
                    failed += 1
                    report["verification"]["issues"].append(f"{table}: could not migrate source ID {doc.get('_id')}: {type(exc).__name__}")
            report["collections"][table] = {
                "source_records": len(rows),
                "migrated_records": migrated,
                "skipped_records": skipped,
                "failed_records": failed,
                "matching_records": matched,
                "target_records_after_run": collection.count_documents({}) if not dry_run else None,
            }
            report["skipped_records"] += skipped
            report["failed_records"] += failed

        if not dry_run:
            verification_ok = True
            for table, fields in COLLECTION_FIELDS.items():
                rows = source.execute(f"SELECT * FROM {table}").fetchall()
                collection = db[table]
                target_count = collection.count_documents({})
                if target_count != len(rows):
                    verification_ok = False
                    report["verification"]["issues"].append(f"{table}: source count {len(rows)} != target count {target_count}")
                for row in rows:
                    doc = source_document(table, row)
                    found = collection.find_one({"_id": doc["_id"]})
                    report["verification"]["source_records_checked"] += 1
                    if found and all(found.get(key) == doc.get(key) for key in ("_id", *fields)):
                        report["verification"]["matching_records"] += 1
                    else:
                        verification_ok = False
                        report["verification"]["issues"].append(f"{table}: field verification failed for source ID {doc['_id']}")
            report["verification"]["passed"] = verification_ok and report["failed_records"] == 0
        else:
            report["verification"]["passed"] = report["failed_records"] == 0
            report["verification"]["issues"].append("Dry run only: no records were written or compared against migrated target counts.")
        return report
    finally:
        source.close()
        mongo_manager.close()

def main():
    parser = argparse.ArgumentParser(description="Copy SQLite Dukaan Saathi data to MongoDB Atlas without overwriting existing records.")
    parser.add_argument("--sqlite", default=database_path(), help="Path to the source SQLite database")
    parser.add_argument("--dry-run", action="store_true", help="Check what would be copied without writing")
    parser.add_argument("--report", default="migration-report.json", help="Write the JSON migration report to this path")
    args = parser.parse_args()
    path = Path(args.sqlite).expanduser()
    if not path.is_file():
        parser.error(f"SQLite source does not exist: {path}")
    try:
        report = migrate(str(path), args.dry_run)
    except Exception as exc:
        print(json.dumps({"success": False, "error": type(exc).__name__, "message": "Migration could not connect or complete. Check database configuration and source data."}, indent=2), file=sys.stderr)
        raise SystemExit(1)
    rendered = json.dumps(report, indent=2)
    Path(args.report).expanduser().write_text(rendered + "\n")
    print(rendered)
    if report["failed_records"] or not report["verification"]["passed"]:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
