import os
import pymongo

class DatabaseConnector:
    def __init__(self):
        # Assumes CloudBase / MongoDB environment variables are set
        self.db_url = os.getenv("DATABASE_URL")
        self.client = pymongo.MongoClient(self.db_url)
        self.db = self.client.get_database("yuepaoquan_db")
        self.collection = self.db.get_collection("activities")

    def save_activity(self, activity_data):
        # Supports HR data by schema-less insertion in MongoDB
        return self.collection.insert_one(activity_data)
