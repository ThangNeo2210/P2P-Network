from pymongo import MongoClient

# Test connection
client = MongoClient("mongodb://localhost:27017/")
db = client["bittorrent"]
print("Connected to MongoDB!")

# Test collections
print("Collections:", db.list_collection_names())