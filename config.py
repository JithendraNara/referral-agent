import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore

# Load environment variables from .env file
load_dotenv()

# Environment variables
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL")  # Where to send alerts

def initialize_firebase():
    """
    Initialize Firebase Admin SDK.
    Uses Application Default Credentials for Cloud Run,
    or GOOGLE_APPLICATION_CREDENTIALS env var for local development.
    """
    if not firebase_admin._apps:
        # Check if running in Cloud Run (has default credentials)
        # or local with service account key
        try:
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred)
        except Exception:
            # Fallback for local development with service account JSON
            service_account_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if service_account_path:
                cred = credentials.Certificate(service_account_path)
                firebase_admin.initialize_app(cred)
            else:
                raise RuntimeError(
                    "Firebase credentials not found. Set GOOGLE_APPLICATION_CREDENTIALS "
                    "or configure Application Default Credentials."
                )

# Initialize Firebase on module import
initialize_firebase()

# Export Firestore client
db = firestore.client()
