"""
Database Reset Utility for API Security Research Testbed.
Drops existing tables and recreates them with the latest schema.
"""
import sys
import os

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import engine, Base
import app.models  # Ensure models are imported for metadata registration


def reset_database():
    print("Dropping existing tables...")
    Base.metadata.drop_all(bind=engine)
    print("Creating tables with updated schema...")
    Base.metadata.create_all(bind=engine)
    print("Database reset complete. All tables are ready.")


if __name__ == "__main__":
    reset_database()
