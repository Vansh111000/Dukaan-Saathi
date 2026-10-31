from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import re
import uuid
from collections import defaultdict, deque
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, PyMongoError

from .config import MAX_PIN_ATTEMPTS, PIN_ATTEMPT_WINDOW_MINUTES, SESSION_EXPIRY_MINUTES
from .mongodb import get_db, mongo_manager
from .security import hash_pin, new_token, normalize_phone, verify_pin

@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        mongo_manager.connect()
    except Exception as exc:
        raise RuntimeError("Unable to connect to MongoDB Atlas. Check MONGODB_URI and MONGODB_DATABASE.") from exc
    yield
    mongo_manager.close()

app = FastAPI(
    title="Dukaan Saathi Calling API",
    version="1.0.0",
    description="Secure calling integration for shop-owner udhaar.",
    lifespan=lifespan,
)
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="SessionBearer",
    bearerFormat="Session token",
    description="Paste the raw session_token returned by POST /auth/verify. Swagger adds the Bearer prefix automatically.",
)
_attempts: dict[str, deque[datetime]] = defaultdict(deque)

def now() -> datetime:
    return datetime.now(timezone.utc)

def stamp(value: datetime) -> str:
    return value.isoformat()

def api_error(status: int, code: str, message: str):
    raise HTTPException(status_code=status, detail={"success": False, "error": {"code": code, "message": message}})

class VerifyRequest(BaseModel):
    phone_number: str = Field(min_length=10, max_length=20)
    pin: str = Field(min_length=4, max_length=12, pattern=r"^\d+$")
    @field_validator("phone_number")
    @classmethod
    def phone(cls, v): return normalize_phone(v)

class UdhaarRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "name": "Ravi",
        "phone_number": "9999999999",
        "address": "Main Road",
        "due": 500,
        "confirmed": True,
    }]})

    name: str = Field(min_length=1, max_length=120)
    phone_number: str = Field(min_length=8, max_length=20)
    address: str = Field(min_length=1, max_length=500)
    due: int = Field(gt=0, le=100_000_000)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=160)
    confirmed: bool
    @field_validator("name", "address")
    @classmethod
    def nonempty(cls, v):
        v = v.strip()
        if not v: raise ValueError("must not be empty")
        return v
    @field_validator("phone_number")
    @classmethod
    def phone(cls, v): return normalize_phone(v)

class QueryRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)

class SessionContext(BaseModel):
    id: str
    shop_id: str
    shop_name: str
    caller_phone_number: str
    call_id: str | None

def authenticated_session(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    db: Database = Depends(get_db),
) -> SessionContext:
    if not credentials or credentials.scheme.lower() != "bearer":
        api_error(401, "unauthorized", "A valid active session is required. Verify at /auth/verify, then authorize with its session_token.")
    token = credentials.credentials.strip()
    if not token or len(token) > 200:
        api_error(401, "unauthorized", "A valid active session is required.")
    try:
        row = db.sessions.find_one({"_id": token})
        if not row or not row.get("is_active", False) or datetime.fromisoformat(row["expires_at"]) <= now():
            if row and row.get("is_active"):
                db.sessions.update_one({"_id": token}, {"$set": {"is_active": False}})
            api_error(401, "session_invalid", "Your session has expired or ended. Please verify again.")
        shop = db.shops.find_one({"_id": row["shop_id"]}, {"shop_name": 1})
        if not shop:
            api_error(401, "session_invalid", "Your session has expired or ended. Please verify again.")
    except PyMongoError:
        api_error(503, "database_unavailable", "The service is temporarily unavailable.")
    return SessionContext(id=row["_id"], shop_id=row["shop_id"], shop_name=shop["shop_name"], caller_phone_number=row["caller_phone_number"], call_id=row.get("call_id"))

@app.get("/health")
def health():
    try:
        mongo_manager.ping()
        return {"success": True, "status": "healthy"}
    except PyMongoError:
        api_error(503, "database_unavailable", "The service is temporarily unavailable.")

@app.post("/auth/verify")
def verify_auth(
    body: VerifyRequest,
    db: Database = Depends(get_db),
    x_call_id: Annotated[str | None, Header(alias="X-Call-ID")] = None,
):
    # The caller number comes from Sarvam's trusted User Identifier context;
    # the PIN is still required and caller ID alone never authenticates.
    key = body.phone_number
    current = now()
    attempts = _attempts[key]
    cutoff = current - timedelta(minutes=PIN_ATTEMPT_WINDOW_MINUTES)
    while attempts and attempts[0] < cutoff: attempts.popleft()
    if len(attempts) >= MAX_PIN_ATTEMPTS:
        api_error(429, "retry_later", "Too many attempts. Please try again later.")
    try:
        shop = db.shops.find_one({"registered_phone_number": body.phone_number}, {"shop_name": 1, "pin_hash": 1})
    except PyMongoError:
        api_error(503, "database_unavailable", "The service is temporarily unavailable.")
    if not shop or not verify_pin(body.pin, shop["pin_hash"] if shop else ""):
        attempts.append(current)
        api_error(401, "verification_failed", "We could not verify those details. Check your PIN or contact your shop administrator.")
    attempts.clear()
    token = new_token()
    created = now()
    expiry = created + timedelta(minutes=SESSION_EXPIRY_MINUTES)
    try:
        db.sessions.insert_one({
            "_id": token,
            "shop_id": shop["_id"],
            "caller_phone_number": body.phone_number,
            "call_id": x_call_id,
            "created_at": stamp(created),
            "expires_at": stamp(expiry),
            "is_active": True,
        })
    except PyMongoError:
        api_error(503, "database_unavailable", "The service is temporarily unavailable.")
    return {"success": True, "verified": True, "shop_name": shop["shop_name"], "session_token": token, "expires_at": stamp(expiry)}

@app.post("/udhaar/add")
def add_udhaar(
    body: UdhaarRequest,
    session: Annotated[SessionContext, Depends(authenticated_session)],
    db: Database = Depends(get_db),
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
):
    if not body.confirmed:
        api_error(400, "confirmation_required", "Read the entry back and obtain explicit confirmation before saving.")
    idempotency_key = body.idempotency_key or x_idempotency_key
    if not idempotency_key and session.call_id:
        canonical = "|".join((session.call_id, body.name.casefold(), body.phone_number, body.address.casefold(), str(body.due)))
        idempotency_key = hashlib.sha256(canonical.encode()).hexdigest()
    if not idempotency_key:
        idempotency_key = str(uuid.uuid4())
    record_id = str(uuid.uuid4())
    created = stamp(now())
    document = {
        "_id": record_id,
        "shop_id": session.shop_id,
        "customer_name": body.name,
        "customer_phone_number": body.phone_number,
        "customer_address": body.address,
        "due_amount": body.due,
        "idempotency_key": idempotency_key,
        "created_at": created,
    }
    try:
        existing = db.udhaar.find_one({"shop_id": session.shop_id, "idempotency_key": idempotency_key})
        if existing:
            return {"success": True, "operation": "already_saved", "record": {"id": existing["_id"], "name": existing["customer_name"], "due": existing["due_amount"], "created_at": existing["created_at"]}, "message": f"This entry was already saved for {existing['customer_name']}."}
        db.udhaar.insert_one(document)
    except DuplicateKeyError:
        existing = db.udhaar.find_one({"shop_id": session.shop_id, "idempotency_key": idempotency_key})
        if existing:
            return {"success": True, "operation": "already_saved", "record": {"id": existing["_id"], "name": existing["customer_name"], "due": existing["due_amount"], "created_at": existing["created_at"]}, "message": f"This entry was already saved for {existing['customer_name']}."}
        api_error(500, "save_failed", "The udhaar entry could not be saved. Please try again.")
    except PyMongoError:
        api_error(500, "save_failed", "The udhaar entry could not be saved. Please try again.")
    return {"success": True, "operation": "saved", "record": {"id": record_id, "name": body.name, "due": body.due, "created_at": created}, "message": f"Saved {body.due} rupees due from {body.name}."}

@app.post("/query")
def query(body: QueryRequest, session: Annotated[SessionContext, Depends(authenticated_session)], db: Database = Depends(get_db)):
    q = re.sub(r"[^a-z0-9 ]", " ", body.query.lower())
    q = " ".join(q.split())
    try:
        if any(term in q for term in ("how many", "number of", "count")) and any(term in q for term in ("customer", "people", "entries", "udhaar")):
            count = db.udhaar.count_documents({"shop_id": session.shop_id})
            return {"success": True, "response": f"You have {count} udhaar entries."}
        if any(term in q for term in ("today", "added today")) and any(term in q for term in ("udhaar", "due", "added")):
            today = now().date().isoformat()
            total = sum(doc["due_amount"] for doc in db.udhaar.find({"shop_id": session.shop_id, "created_at": {"$regex": "^" + today}}, {"due_amount": 1}))
            return {"success": True, "response": f"You added {total} rupees of udhaar today."}
        if any(term in q for term in ("total", "how much", "pending amount", "overall")) and any(term in q for term in ("udhaar", "due", "owe", "pending")):
            pipeline = [
                {"$match": {"shop_id": session.shop_id}},
                {"$group": {"_id": None, "total": {"$sum": "$due_amount"}, "entries": {"$sum": 1}}},
            ]
            row = next(db.udhaar.aggregate(pipeline), {"total": 0, "entries": 0})
            return {"success": True, "response": f"Your pending udhaar total is {row['total']} rupees across {row['entries']} entries."}
        if any(term in q for term in ("show", "list", "entries", "records")) and any(term in q for term in ("udhaar", "customer", "pending", "owe")):
            rows = list(db.udhaar.find({"shop_id": session.shop_id}, {"customer_name": 1, "due_amount": 1}).sort("created_at", -1).limit(20))
            if not rows: response = "You have no udhaar entries yet."
            else: response = "Your recent udhaar entries are: " + "; ".join(f"{r['customer_name']}, {r['due_amount']} rupees" for r in rows)
            return {"success": True, "response": response}
    except PyMongoError:
        api_error(503, "database_unavailable", "The service is temporarily unavailable.")
    return {"success": False, "code": "unsupported_request", "response": "I can answer questions about your pending udhaar total, today's additions, customer count, or recent udhaar entries."}

@app.post("/session/end")
def end_session(session: Annotated[SessionContext, Depends(authenticated_session)], db: Database = Depends(get_db)):
    try:
        db.sessions.update_one({"_id": session.id, "shop_id": session.shop_id}, {"$set": {"is_active": False}})
    except PyMongoError:
        api_error(503, "database_unavailable", "The service is temporarily unavailable.")
    return {"success": True, "message": "Your calling session has ended."}

# Local-only shop provisioning; never expose this as an HTTP endpoint.
def create_shop(shop_name: str, phone: str, pin: str, db: Database | None = None) -> str:
    phone = normalize_phone(phone)
    if not re.fullmatch(r"\d{4,12}", pin): raise ValueError("PIN must contain 4 to 12 digits")
    shop_id = str(uuid.uuid4())
    (db or get_db()).shops.insert_one({"_id": shop_id, "shop_name": shop_name.strip(), "registered_phone_number": phone, "pin_hash": hash_pin(pin), "created_at": stamp(now())})
    return shop_id
