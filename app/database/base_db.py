from typing import Dict, Optional
from pymongo import MongoClient
from app.config import Config

class BaseDatabase:
    """Base database interface with common functionality"""
    
    def __init__(self):
        self.client = MongoClient(Config.DB_URI)
        self.db = self.client[Config.DB_NAME]

    def _insert_one(self, collection: str, data: Dict) -> bool:
        """Insert one document into collection"""
        try:
            self.db[collection].insert_one(data)
            return True
        except Exception:
            return False

    def _find_one(self, collection: str, query: Dict) -> Optional[Dict]:
        """Find one document from collection"""
        try:
            return self.db[collection].find_one(query)
        except Exception:
            return None

    def _update_one(self, collection: str, query: Dict, update: Dict) -> bool:
        """Update one document in collection"""
        try:
            result = self.db[collection].update_one(query, update)
            return result.modified_count > 0
        except Exception:
            return False 