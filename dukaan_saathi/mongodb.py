import os
from pymongo import MongoClient
from pymongo.database import Database
from dotenv import load_dotenv

load_dotenv()

class MongoManager:
    def __init__(self):
        self._client: MongoClient | None = None
        self._database: Database | None = None

    def connect(self) -> Database:
        uri = os.getenv("MONGODB_URI", "").strip()
        name = os.getenv("MONGODB_DATABASE", "dukaan_saathi").strip()
        if not uri:
            raise RuntimeError("MONGODB_URI is not configured")
        if not name:
            raise RuntimeError("MONGODB_DATABASE is not configured")
        try:
            self._client = MongoClient(
                uri,
                appname="DukaanSaathi",
                connectTimeoutMS=int(os.getenv("MONGODB_CONNECT_TIMEOUT_MS", "10000")),
                serverSelectionTimeoutMS=int(os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "10000")),
                socketTimeoutMS=int(os.getenv("MONGODB_SOCKET_TIMEOUT_MS", "20000")),
                maxPoolSize=int(os.getenv("MONGODB_MAX_POOL_SIZE", "50")),
                minPoolSize=int(os.getenv("MONGODB_MIN_POOL_SIZE", "0")),
                retryWrites=True,
            )
            self._client.admin.command("ping")
            self._database = self._client[name]
            self.ensure_indexes()
            return self._database
        except Exception:
            self.close()
            raise

    @property
    def database(self) -> Database:
        if self._database is None:
            return self.connect()
        return self._database

    def ensure_indexes(self) -> None:
        if self._database is None:
            raise RuntimeError("MongoDB is not connected")
        self._database.shops.create_index("registered_phone_number", unique=True, name="shops_phone_unique")
        self._database.sessions.create_index([("shop_id", 1), ("is_active", 1)], name="sessions_shop_active")
        self._database.sessions.create_index("expires_at", name="sessions_expiry")
        self._database.udhaar.create_index([("shop_id", 1), ("idempotency_key", 1)], unique=True, name="udhaar_shop_idempotency_unique")
        self._database.udhaar.create_index([("shop_id", 1), ("created_at", -1)], name="udhaar_shop_created")
        self._database.udhaar.create_index([("shop_id", 1), ("customer_phone_number", 1)], name="udhaar_shop_customer_phone")
        self._database.udhaar.create_index([("shop_id", 1), ("customer_name", 1)], name="udhaar_shop_customer_name")

    def ping(self) -> bool:
        self.database.command("ping")
        return True

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
        self._client = None
        self._database = None

mongo_manager = MongoManager()

def get_db() -> Database:
    return mongo_manager.database
