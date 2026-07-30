import os

from dotenv import load_dotenv

load_dotenv()

FIREBASE_SERVICE_ACCOUNT_FILE = os.getenv("FIREBASE_SERVICE_ACCOUNT_FILE", "serviceAccountKey.json")
FIRESTORE_DATABASE_ID = os.getenv("FIRESTORE_DATABASE_ID", "(default)")

GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")
GITHUB_APP_SLUG = os.getenv("GITHUB_APP_SLUG", "vanguardgate")
GITHUB_PRIVATE_KEY_PATH = os.getenv("GITHUB_PRIVATE_KEY_PATH")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
