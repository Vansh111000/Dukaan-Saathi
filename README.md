# Dukaan Saathi Calling API

FastAPI backend for Sarvam voice-agent calls, shop-owner PIN verification, authenticated sessions, and shop-scoped udhaar records. MongoDB Atlas is the live database. The original SQLite file is retained as the migration source and is not used by API routes.

## Configure and run

1. Create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements-dev.txt
   ```

2. Set `MONGODB_URI` and `MONGODB_DATABASE` in `.env`. The URI password must be percent-encoded (for example `@` becomes `%40`). Do not commit or print `.env`. Optional connection pool and timeout settings are in `.env.example`.
3. Start the API:

   ```bash
   uvicorn dukaan_saathi.main:app --reload
   ```

   Startup connects to Atlas, pings it, and ensures the required indexes. `/health` checks Atlas connectivity. The Mongo client closes on application shutdown. Open `/docs` for Swagger.

`SARVAM_API_KEY` remains a server-side environment setting, but these routes do not call Sarvam's model API directly; Sarvam Voice Agents call the configured HTTP API tools.

## API contract

The routes and authentication format remain compatible with the existing Sarvam tool setup:

- `GET /health` returns `{ "success": true, "status": "healthy" }` when MongoDB is reachable.
- `POST /auth/verify` body: `{ "phone_number": "9999999999", "pin": "1234" }`. Use Sarvam's trusted User Identifier as `phone_number`; the owner must still provide their PIN. A local 10-digit Indian mobile is normalized to `+91`. Optional `X-Call-ID` can carry the Sarvam interaction ID. Success returns `success`, `verified`, `shop_name`, `session_token`, and `expires_at`.
- `POST /udhaar/add` requires `Authorization: Bearer <session_token>`. Body: `{ "name": "Ravi", "phone_number": "+919876543211", "address": "Main Road", "due": 500, "confirmed": true }`; optional `idempotency_key` remains supported. The Swagger request example intentionally omits the optional key. Do not reuse a key for a new debt: the same key in a shop returns its earlier saved record. When omitted, a stable key is derived from the session's call ID and entry fields when available.
- `POST /query` requires the same bearer token and accepts `{ "query": "What is my pending udhaar total?" }`. It supports total, today's additions, entry count, and recent entries; unsupported queries preserve the existing response format.
- `POST /session/end` requires the same bearer token and deactivates that session.

PIN verification errors, bearer-session errors, and validation responses retain the current API response formats. Shop IDs are always derived from the authenticated session; request-supplied shop IDs are not authoritative.

## MongoDB collections and indexes

Database name: `MONGODB_DATABASE` (configured here as `dukaan_saathi`). Collections: `shops`, `sessions`, and `udhaar`.

Indexes include a unique registered shop phone, session shop/activity and expiry indexes, udhaar shop/date and shop/customer-phone indexes, and a unique `(shop_id, idempotency_key)` constraint. Existing bcrypt hashes are preserved. Session IDs remain the bearer token references, with their shop relation stored in `shop_id`.

To add a shop after migration, run `python -m dukaan_saathi.seed_shop --name "New Shop" --phone +919876543210`; the PIN is prompted without echo and stored as a bcrypt hash.

## SQLite to Atlas migration

The migration is insert-only: it keeps SQLite IDs, timestamps, PIN hashes, and references; skips identical records on rerun; and reports conflicting records instead of overwriting them. It verifies record counts and fields and writes `migration-report.json`.

```bash
python -m dukaan_saathi.migrate_sqlite_to_mongodb --dry-run
python -m dukaan_saathi.migrate_sqlite_to_mongodb
```

Pass `--sqlite /path/to/source.sqlite3` to select another source and `--report /path/to/report.json` to choose the report path. The SQLite database is never deleted or modified by the migrator.

The migration completed for this workspace: 1 shop, 6 sessions, and 1 udhaar record migrated; 0 skipped; 0 failed; all 8 source records matched in Atlas. See [migration-report.json](migration-report.json).

## Tests

Install `requirements-dev.txt` and run:

```bash
python -m pytest
```

Tests use an isolated in-memory MongoDB mock and never connect to the production Atlas database.
