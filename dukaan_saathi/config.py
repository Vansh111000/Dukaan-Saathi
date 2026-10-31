import os
from dotenv import load_dotenv
load_dotenv()
SESSION_EXPIRY_MINUTES = int(os.getenv("SESSION_EXPIRY_MINUTES", "120"))
MAX_PIN_ATTEMPTS = int(os.getenv("MAX_PIN_ATTEMPTS", "5"))
PIN_ATTEMPT_WINDOW_MINUTES = int(os.getenv("PIN_ATTEMPT_WINDOW_MINUTES", "15"))
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
