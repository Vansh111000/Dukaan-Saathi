# Dukaan Saathi

Dukaan Saathi is a voice-first assistant concept for neighborhood shops. This repository currently contains a working FastAPI calling backend for owner authentication and udhaar, plus written plans for additional business-intelligence features. It does not yet contain a frontend or implementations of the planned analytics and inventory features.

## What is implemented

- FastAPI service for health checks, PIN verification, call sessions, udhaar creation, and udhaar questions.
- MongoDB Atlas persistence for shops, sessions, and udhaar, with tenant-scoped reads and writes.
- Bcrypt PIN hashing, expiring bearer sessions, session termination, and PIN retry limiting.
- Sarvam Voice Agent integration instructions in [`docs/sarvam-agent-instructions.md`](docs/sarvam-agent-instructions.md).
- SQLite-to-MongoDB migration utility and its report in [`migration-report.json`](migration-report.json).
- Automated API and migration tests using an isolated MongoDB mock.

## Project plans

The following files describe proposed features; they are plans, not working API features in this repository:

- [`business_insights.md`](business_insights.md): daily business summaries, restock advice, and item-level profit.
- [`localmarketintelligence.md`](localmarketintelligence.md): local price index and neighborhood alerts.

## Try the calling feature

The Sarvam calling number supplied for this deployment is **+91 7965481872**. Call it from the shop owner's registered phone. The backend uses Sarvam's inbound caller metadata to look up that registered number; an unregistered caller cannot access shop data. When prompted, enter the shop PIN privately. PINs are credentials, so they are intentionally not published in this README or in agent instructions.

After verification, try this conversation:

1. Say: “I want to add udhaar.”
2. Give the customer's name, phone number, address, and the amount owed. The agent should ask for missing details one at a time.
3. Listen while the agent reads all four fields back. Confirm only if they are correct.
4. The agent calls the backend after confirmation and reports the backend result.
5. Ask a supported question, for example: “What is my total pending udhaar?”, “How much udhaar did I add today?”, “How many udhaar entries do I have?”, or “Show my recent udhaar entries.”

The Sarvam deployment must be active and its API tools must point to a publicly reachable HTTPS backend. A local address such as `127.0.0.1` is not reachable by Sarvam. Configure the public backend URL in the Sarvam dashboard; no deployment domain is stored in this repository.

## Run locally

Requirements: Python 3.10+ and access to the configured MongoDB Atlas cluster.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Set `MONGODB_URI` and `MONGODB_DATABASE` in `.env`. Start the API:

```bash
uvicorn dukaan_saathi.main:app --reload
```

On startup, the service connects to Atlas, pings it, and ensures indexes. Open `http://127.0.0.1:8000/docs` for interactive API documentation. For Sarvam calls, expose the service through a secure public HTTPS deployment or tunnel and use that HTTPS base URL in the Voice Agent tools.

Never commit `.env`. Use `.env.example` as a template, and keep database passwords and shop PINs out of source control, prompts, logs, and API responses. `SARVAM_API_KEY` is retained as a server-side setting; these FastAPI routes are called by Sarvam Voice Agents and do not call Sarvam's model API directly.

## API reference

All endpoints use JSON. The protected endpoints require the session token returned by `/auth/verify`:

```http
Authorization: Bearer <session_token>
```

The token is per session, expires according to `SESSION_EXPIRY_MINUTES`, and is invalidated by `/session/end`. Map the token dynamically from the successful `/auth/verify` response in Sarvam; do not use a fixed token.

### `GET /health`

Returns `{ "success": true, "status": "healthy" }` when Atlas is reachable; otherwise returns HTTP 503.

### `POST /auth/verify`

Request body:

```json
{
  "phone_number": "<trusted inbound caller number>",
  "pin": "<shop PIN entered by the owner>"
}
```

Map `phone_number` from Sarvam's inbound **User Identifier** call context, not from a number spoken in conversation. Indian 10-digit mobile numbers are normalized to `+91`. Optionally send Sarvam's Interaction ID as `X-Call-ID` to correlate the active session with the call.

A successful response contains `success`, `verified`, `shop_name`, `session_token`, and `expires_at`. Incorrect or unregistered details return HTTP 401 with a generic message; too many failed attempts return HTTP 429.

### `POST /udhaar/add`

Requires the bearer session token. Required fields are `name`, `phone_number`, `address`, `due`, and `confirmed`. `due` must be a positive integer rupee amount, and `confirmed` must be the JSON boolean `true` after the owner has reviewed the entry.

```json
{
  "name": "Customer name",
  "phone_number": "+919876543210",
  "address": "Customer address",
  "due": 500,
  "confirmed": true
}
```

`idempotency_key` is optional. If supplied, use a unique per-entry key; reusing a key for the same shop returns the earlier record with `operation: "already_saved"`. Without a body/header key, the backend derives a key from the call ID and entry fields when available.

### `POST /query`

Requires the bearer session token. Supported requests are udhaar totals, today's additions, entry count, and recent entries.

```json
{
  "query": "What is my total pending udhaar?"
}
```

The response contains concise text in `response`. Unsupported questions return `success: false` and a supported-query message; they do not execute arbitrary SQL or database commands.

### `POST /session/end`

Requires the bearer session token and deactivates that session. Configure the Sarvam call-end flow to call this endpoint when possible.

Request validation errors return HTTP 422. Session errors return HTTP 401. Udhaar confirmation failures return HTTP 400; failed writes return HTTP 500. The agent must not claim a new entry was saved unless the response has `success: true` and `operation: "saved"`; `operation: "already_saved"` means the request matched an existing idempotency key.

## MongoDB and migration

The application uses the `shops`, `sessions`, and `udhaar` collections in the database named by `MONGODB_DATABASE` (currently configured as `dukaan_saathi`). Indexes enforce unique shop phone numbers and per-shop idempotency keys and support session expiry, shop/date queries, and customer lookups.

The SQLite source file is retained; API routes use MongoDB. To preview or rerun the insert-only migration:

```bash
python -m dukaan_saathi.migrate_sqlite_to_mongodb --dry-run
python -m dukaan_saathi.migrate_sqlite_to_mongodb
```

The migrator preserves IDs, bcrypt hashes, timestamps, and relationships; it skips identical records and reports conflicts without overwriting them. It writes `migration-report.json`. The initial migration report records 1 shop, 6 sessions, and 1 udhaar record copied and verified.

To provision another shop, run `python -m dukaan_saathi.seed_shop --name "Shop name" --phone +919876543210`; the command prompts for the PIN without echoing it and stores a bcrypt hash.

## Tests

```bash
python -m pytest
```

Install `requirements-dev.txt` first. Tests use an isolated in-memory MongoDB mock and do not connect to the Atlas database.
