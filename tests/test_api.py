from datetime import datetime, timedelta, timezone

import mongomock
import pytest
from fastapi.testclient import TestClient

from dukaan_saathi.main import app, create_shop
from dukaan_saathi.mongodb import get_db, mongo_manager

@pytest.fixture
def client(monkeypatch):
    db = mongomock.MongoClient()["dukaan_saathi_test"]
    mongo_manager._database = db
    mongo_manager.ensure_indexes()
    monkeypatch.setattr(mongo_manager, "ping", lambda: True)
    app.dependency_overrides[get_db] = lambda: db
    from dukaan_saathi import main as api_module
    api_module._attempts.clear()
    monkeypatch.setattr(api_module, "MAX_PIN_ATTEMPTS", 3)
    # Do not enter TestClient's lifespan: that intentionally connects to Atlas.
    c = TestClient(app)
    c.db = db
    yield c
    app.dependency_overrides.clear()
    mongo_manager._database = None

def shop(client, name, phone, pin):
    return create_shop(name, phone, pin, client.db)

def auth(client, phone, pin="1234", call_id="call-1"):
    headers = {"X-Call-ID": call_id} if call_id else {}
    return client.post("/auth/verify", json={"phone_number": phone, "pin": pin}, headers=headers)

def session_headers(token):
    return {"Authorization": f"Bearer {token}"}

def test_mongodb_indexes(client):
    indexes = {collection: client.db[collection].index_information() for collection in ("shops", "sessions", "udhaar")}
    assert indexes["shops"]["shops_phone_unique"]["unique"] is True
    assert "sessions_expiry" in indexes["sessions"]
    assert indexes["udhaar"]["udhaar_shop_idempotency_unique"]["unique"] is True
    assert "udhaar_shop_created" in indexes["udhaar"]
    assert "udhaar_shop_customer_name" in indexes["udhaar"]

def test_registered_and_unregistered_caller(client):
    shop(client, "Corner Shop", "+919876543210", "1234")
    assert auth(client, "+919876543210").status_code == 200
    response = auth(client, "+919876543211")
    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "verification_failed"

def test_correct_incorrect_pin_and_retry_limit(client):
    shop(client, "A", "+919876543210", "1234")
    assert auth(client, "+919876543210", "1234").json()["verified"]
    assert auth(client, "+919876543210", "0000").status_code == 401
    assert auth(client, "+919876543210", "0000").status_code == 401
    assert auth(client, "+919876543210", "0000").status_code == 401
    assert auth(client, "+919876543210", "1234").status_code == 429

def test_session_creation_expiry_and_termination(client):
    shop(client, "A", "+919876543210", "1234")
    response = auth(client, "+919876543210")
    assert response.status_code == 200
    token = response.json()["session_token"]
    row = client.db.sessions.find_one({"_id": token})
    assert row["call_id"] == "call-1" and row["is_active"] is True
    expired = (datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
    client.db.sessions.update_one({"_id": token}, {"$set": {"expires_at": expired}})
    assert client.post("/query", json={"query":"total udhaar"}, headers=session_headers(token)).status_code == 401
    response = auth(client, "+919876543210")
    token = response.json()["session_token"]
    assert client.post("/session/end", headers=session_headers(token)).status_code == 200
    assert client.post("/query", json={"query":"total udhaar"}, headers=session_headers(token)).status_code == 401

def test_unauthenticated_and_confirmation_required(client):
    assert client.post("/query", json={"query":"total udhaar"}).status_code == 401
    shop(client, "A", "+919876543210", "1234")
    token = auth(client, "+919876543210").json()["session_token"]
    data = {"name":"Ravi","phone_number":"+919876543211","address":"Main Road","due":500,"idempotency_key":"call-1-record-1","confirmed":False}
    assert client.post("/udhaar/add", json=data, headers=session_headers(token)).status_code == 400
    data["confirmed"] = True
    assert client.post("/udhaar/add", json=data, headers=session_headers(token)).status_code == 200

def test_invalid_udhaar_and_idempotency(client):
    shop(client, "A", "+919876543210", "1234")
    token = auth(client, "+919876543210").json()["session_token"]
    headers = session_headers(token)
    base = {"name":"Ravi","phone_number":"+919876543211","address":"Main Road","due":500,"idempotency_key":"call-2-record-1","confirmed":True}
    assert client.post("/udhaar/add", json=dict(base, due=0), headers=headers).status_code == 422
    first = client.post("/udhaar/add", json=base, headers=headers).json()
    second = client.post("/udhaar/add", json=base, headers=headers).json()
    assert first["record"]["id"] == second["record"]["id"]
    assert second["operation"] == "already_saved"

def test_total_query_and_shop_isolation(client):
    a = shop(client, "A", "+919876543210", "1234")
    shop(client, "B", "+919876543212", "4321")
    token_a = auth(client, "+919876543210").json()["session_token"]
    token_b = auth(client, "+919876543212", "4321").json()["session_token"]
    base = {"name":"Ravi","phone_number":"+919876543211","address":"Main Road","due":700,"idempotency_key":"call-3-record-1","confirmed":True}
    assert client.post("/udhaar/add", json=base, headers=session_headers(token_a)).status_code == 200
    body = dict(base, name="Meena", due=900, idempotency_key="call-4-record-1", shop_id=a)
    assert client.post("/udhaar/add", json=body, headers=session_headers(token_b)).status_code == 200
    result = client.post("/query", json={"query":"What is my total pending udhaar?"}, headers=session_headers(token_a)).json()
    assert "700 rupees" in result["response"]
    listing = client.post("/query", json={"query":"show my udhaar entries"}, headers=session_headers(token_a)).json()
    assert "Ravi" in listing["response"] and "Meena" not in listing["response"]
    assert client.db.udhaar.count_documents({"shop_id": a}) == 1

def test_unsupported_query(client):
    shop(client, "A", "+919876543210", "1234")
    token = auth(client, "+919876543210").json()["session_token"]
    result = client.post("/query", json={"query":"Tell me the weather"}, headers=session_headers(token)).json()
    assert result["success"] is False
    assert result["code"] == "unsupported_request"

def test_today_query(client):
    shop(client, "A", "+919876543210", "1234")
    token = auth(client, "+919876543210").json()["session_token"]
    record = {"name":"Ravi","phone_number":"+919876543211","address":"Main Road","due":250,"idempotency_key":"call-today-entry","confirmed":True}
    assert client.post("/udhaar/add", json=record, headers=session_headers(token)).status_code == 200
    result = client.post("/query", json={"query":"How much udhaar did I add today?"}, headers=session_headers(token)).json()
    assert "250 rupees" in result["response"]

def test_auth_body_is_phone_and_pin_only_with_local_indian_number(client):
    shop(client, "A", "+919999999999", "1234")
    response = client.post("/auth/verify", json={"phone_number":"9999999999", "pin":"1234"})
    assert response.status_code == 200
    assert response.json()["verified"] is True
    row = client.db.sessions.find_one({"_id": response.json()["session_token"]})
    assert row["caller_phone_number"] == "+919999999999"
    assert row["call_id"] is None

def test_idempotency_key_optional_and_call_retries_deduplicate(client):
    shop(client, "A", "+919876543210", "1234")
    token = auth(client, "+919876543210", call_id="sarvam-interaction-1").json()["session_token"]
    record = {"name":"Sounbha","phone_number":"8454055780","address":"BARC","due":1000000,"confirmed":True}
    headers = session_headers(token)
    first = client.post("/udhaar/add", json=record, headers=headers)
    second = client.post("/udhaar/add", json=record, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["record"]["id"] == second.json()["record"]["id"]

def test_swagger_declares_bearer_auth_for_protected_routes(client):
    schema = client.get("/openapi.json").json()
    assert schema["components"]["securitySchemes"]["SessionBearer"]["scheme"] == "bearer"
    assert schema["paths"]["/udhaar/add"]["post"]["security"] == [{"SessionBearer": []}]
    assert schema["paths"]["/query"]["post"]["security"] == [{"SessionBearer": []}]
    example = schema["components"]["schemas"]["UdhaarRequest"]["examples"][0]
    assert "idempotency_key" not in example


def test_health_reports_mongodb_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"success": True, "status": "healthy"}
