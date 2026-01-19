"""
Configuration management with validation and environment handling.
Professional setup with proper error handling and defaults.
"""
import os
import logging
from typing import Optional
from functools import lru_cache
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class Settings:
    """Application settings with validation."""
    
    def __init__(self):
        # Core settings
        self.GOOGLE_API_KEY: Optional[str] = os.getenv("GOOGLE_API_KEY")
        self.GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        
        # Email settings
        self.GMAIL_USER: Optional[str] = os.getenv("GMAIL_USER")
        self.GMAIL_APP_PASSWORD: Optional[str] = os.getenv("GMAIL_APP_PASSWORD")
        self.NOTIFICATION_EMAIL: Optional[str] = os.getenv("NOTIFICATION_EMAIL")
        
        # Webhook settings
        self.SLACK_WEBHOOK_URL: Optional[str] = os.getenv("SLACK_WEBHOOK_URL")
        self.DISCORD_WEBHOOK_URL: Optional[str] = os.getenv("DISCORD_WEBHOOK_URL")
        
        # App settings
        self.APP_ENV: str = os.getenv("APP_ENV", "production")
        self.DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
        
        # Rate limiting
        self.RATE_LIMIT_MIN_DELAY: float = float(os.getenv("RATE_LIMIT_MIN_DELAY", "2.0"))
        self.RATE_LIMIT_MAX_DELAY: float = float(os.getenv("RATE_LIMIT_MAX_DELAY", "5.0"))
        
        # Scraping settings
        self.SCRAPE_TIMEOUT: int = int(os.getenv("SCRAPE_TIMEOUT", "60"))
        self.MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
        
    @property
    def email_configured(self) -> bool:
        """Check if email notifications are properly configured."""
        return all([self.GMAIL_USER, self.GMAIL_APP_PASSWORD, self.NOTIFICATION_EMAIL])
    
    @property
    def llm_configured(self) -> bool:
        """Check if LLM is properly configured."""
        return bool(self.GOOGLE_API_KEY)
    
    def validate(self) -> list:
        """Validate configuration and return list of warnings."""
        warnings = []
        
        if not self.GOOGLE_API_KEY:
            warnings.append("GOOGLE_API_KEY not set - LLM features disabled")
        
        if not self.email_configured:
            warnings.append("Email credentials incomplete - email notifications disabled")
        
        return warnings


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


class FirebaseManager:
    """Manages Firebase connection with proper initialization."""
    
    _instance = None
    _db = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def initialize(self):
        """Initialize Firebase Admin SDK."""
        if self._initialized:
            return
        
        if not firebase_admin._apps:
            try:
                # Try Application Default Credentials (Cloud Run)
                cred = credentials.ApplicationDefault()
                firebase_admin.initialize_app(cred)
                logger.info("Firebase initialized with Application Default Credentials")
            except Exception as e:
                # Fallback to service account file
                service_account_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
                if service_account_path and os.path.exists(service_account_path):
                    cred = credentials.Certificate(service_account_path)
                    firebase_admin.initialize_app(cred)
                    logger.info(f"Firebase initialized with service account: {service_account_path}")
                else:
                    logger.error(f"Firebase initialization failed: {e}")
                    raise RuntimeError(
                        "Firebase credentials not found. Set GOOGLE_APPLICATION_CREDENTIALS "
                        "or configure Application Default Credentials."
                    )
        
        self._db = firestore.client()
        self._initialized = True
    
    @property
    def db(self):
        """Get Firestore client, initializing if needed."""
        if not self._initialized:
            self.initialize()
        return self._db


# Initialize Firebase manager
firebase_manager = FirebaseManager()
firebase_manager.initialize()

# Export for backward compatibility
db = firebase_manager.db
settings = get_settings()

# Legacy exports
GOOGLE_API_KEY = settings.GOOGLE_API_KEY
GMAIL_USER = settings.GMAIL_USER
GMAIL_APP_PASSWORD = settings.GMAIL_APP_PASSWORD
NOTIFICATION_EMAIL = settings.NOTIFICATION_EMAIL

# Log warnings on startup
for warning in settings.validate():
    logger.warning(warning)
