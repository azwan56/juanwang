from .config import Config
import pymongo
import logging

logger = logging.getLogger(__name__)


class DatabaseConnector:
    """Lazy-initialized MongoDB connector using centralized Config."""

    def __init__(self):
        self._client = None
        self._collection = None

    def _ensure_connection(self):
        """Lazy connect: only open the connection on first actual use."""
        if self._client is None:
            db_url = Config.DATABASE_URL
            if not db_url:
                raise RuntimeError(
                    "DATABASE_URL is not configured. "
                    "Set it in .env or as an environment variable."
                )
            logger.info(f"Connecting to database: {Config.DATABASE_NAME}")
            self._client = pymongo.MongoClient(db_url, serverSelectionTimeoutMS=5000)
            db = self._client.get_database(Config.DATABASE_NAME)
            self._collection = db.get_collection(Config.COLLECTION_NAME)

    def save_activity(self, activity_data):
        """Saves normalized activity data to MongoDB."""
        self._ensure_connection()
        return self._collection.insert_one(activity_data)
