import firebase_admin
from firebase_admin import credentials, firestore

from app import config

if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate(config.FIREBASE_SERVICE_ACCOUNT_FILE))

db = firestore.client(database_id=config.FIRESTORE_DATABASE_ID)
