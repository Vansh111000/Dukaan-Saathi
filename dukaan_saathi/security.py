import re
import secrets
import bcrypt

PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")

def normalize_phone(value: str) -> str:
    cleaned = re.sub(r"[\s().-]", "", value.strip())
    # Accept an Indian 10-digit local number and normalize it to E.164.
    if re.fullmatch(r"[6-9]\d{9}", cleaned):
        cleaned = "+91" + cleaned
    if not PHONE_RE.fullmatch(cleaned):
        raise ValueError("Phone number must be a valid international number or a 10-digit Indian mobile number")
    return cleaned

def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt(rounds=12)).decode()

def verify_pin(pin: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pin.encode(), hashed.encode())
    except (ValueError, TypeError):
        return False

def new_token() -> str:
    return secrets.token_urlsafe(32)
