"""
database.py
-----------
Handles MongoDB connection setup using environment variables.
All other modules import `db` from here — single source of truth for DB access.
"""

import os
from pymongo import MongoClient, ASCENDING
from dotenv import load_dotenv

# Load variables from .env file into the environment
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME   = os.getenv("DB_NAME",   "public_sector_datalake")

# Create a single MongoClient instance (connection pooled by PyMongo)
client = MongoClient(MONGO_URI)
db     = client[DB_NAME]

# ------------------------------------------------------------------
# Ensure the `ledger` collection has an index on `dataset_id` so
# history queries are fast even with millions of blocks.
# ------------------------------------------------------------------
db["ledger"].create_index([("dataset_id", ASCENDING)])