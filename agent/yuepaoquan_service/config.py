import os

class Config:
    DATABASE_URL = os.getenv("DATABASE_URL", "mongodb://localhost:27017")
    API_KEY = os.getenv("API_KEY")
