import psycopg2
from typing import List, Tuple
from config import *

class DatabaseConnection:
    """Manages database connection and operations."""
    
    def __init__(self):
        self.conn = None
        self.cursor = None
    
    def connect(self):
        """Establish connection to PostgreSQL database."""
        try:
            self.conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME
            )
            self.cursor = self.conn.cursor()
            print(f"✓ Connected to database {DB_NAME}")
        except Exception as e:
            print(f"✗ Failed to connect to database: {e}")
            raise
    
    def close(self):
        """Close database connection."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        print("✓ Database connection closed")
    
    def execute(self, query: str, params: Tuple = None):
        """Execute a single query."""
        try:
            self.cursor.execute(query, params)
            return self.cursor
        except Exception as e:
            print(f"✗ Query failed: {e}")
            print(f"  Query: {query}")
            self.conn.rollback()
            raise
    
    def executemany(self, query: str, params_list: List[Tuple]):
        """Execute multiple queries for batch insert/update."""
        try:
            self.cursor.executemany(query, params_list)
            return len(params_list)
        except Exception as e:
            print(f"✗ Batch query failed: {e}")
            print(f"  Query: {query}")
            self.conn.rollback()
            raise
    
    def commit(self):
        """Commit transaction."""
        try:
            self.conn.commit()
        except Exception as e:
            print(f"✗ Commit failed: {e}")
            self.conn.rollback()
            raise
    
    def rollback(self):
        """Rollback transaction."""
        self.conn.rollback()