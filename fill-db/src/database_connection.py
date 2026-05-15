"""Database connection and operations management module.

Provides a wrapper class for PostgreSQL database connections and query
execution, including support for single queries, batch operations, and
transaction management.
"""

import psycopg2
from config import *
from typing import List, Tuple, Optional, Any

class DatabaseConnection:
    """
    Manages database connections and query execution.
    
    Handles connection lifecycle, query execution (single and batch),
    transaction management (commit/rollback), and error handling for
    PostgreSQL databases.
    
    Attributes:
        conn (Optional[psycopg2.connection]): PostgreSQL database connection object.
        cursor (Optional[psycopg2.cursor]): Database cursor for executing queries.
    """
    
    def __init__(self) -> None:
        """
        Initialize the DatabaseConnection object.
        
        Returns:
            None
        """
        self.conn = None
        self.cursor = None
    

    def connect(self) -> None:
        """
        Establish connection to PostgreSQL database.
        
        Attempt to connect using credentials from environment variables.
        
        Returns:
            None
            
        Raises:
            Exception: If connection to the database fails.
        """
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
    

    def close(self) -> None:
        """
        Close database connection and cursor.
        
        Returns:
            None
        """
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        print("✓ Database connection closed")
    

    def execute(self, query: str, params: Optional[Tuple] = None) -> psycopg2.extensions.cursor:
        """
        Execute a single query.
        
        Args:
            query (str): SQL query string.
            params (Optional[Tuple]): Tuple of parameters for parameterized query. Defaults to None.
        
        Returns:
            psycopg2.extensions.cursor: Database cursor after query execution.
            
        Raises:
            Exception: If query execution fails.
        """
        try:
            self.cursor.execute(query, params)
            return self.cursor
        except Exception as e:
            print(f"✗ Query failed: {e}")
            print(f"  Query: {query}")
            self.conn.rollback()
            raise
    

    def executemany(self, query: str, params_list: List[Tuple]) -> int:
        """
        Execute multiple queries for batch insert/update.
        
        Args:
            query (str): SQL query string.
            params_list (List[Tuple]): List of parameter tuples for batch execution.
        
        Returns:
            int: Number of items processed.
            
        Raises:
            Exception: If batch query execution fails.
        """
        try:
            self.cursor.executemany(query, params_list)
            return len(params_list)
        except Exception as e:
            print(f"✗ Batch query failed: {e}")
            print(f"  Query: {query}")
            self.conn.rollback()
            raise
    

    def commit(self) -> None:
        """
        Commit the current transaction.
        
        Returns:
            None
            
        Raises:
            Exception: If commit fails.
        """
        try:
            self.conn.commit()
        except Exception as e:
            print(f"✗ Commit failed: {e}")
            self.conn.rollback()
            raise
    

    def rollback(self) -> None:
        """
        Rollback the current transaction.
        
        Returns:
            None
        """
        self.conn.rollback()