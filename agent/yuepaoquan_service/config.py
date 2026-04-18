import os

class Config:
    DATABASE_URL = os.getenv("DATABASE_URL", "mongodb://localhost:27017")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "yuepaoquan_db")
    COLLECTION_NAME = os.getenv("COLLECTION_NAME", "activities")
    API_KEY = os.getenv("API_KEY")
    WECOM_WEBHOOK_URL = os.getenv("WECOM_WEBHOOK_URL")
