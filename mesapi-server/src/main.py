"""
Main entry point for the MES API server.

This module sets up a FastAPI application, to simulate MES operations.
It handles database connections via SQLAlchemy, implements application lifespan
management for telemetry initialization and shutdown, and provides endpoints 
for health checks and active prodction order retrieval.
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Generator, Optional, Any
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from mesapi_server_telemetry import MESAPIServerTelemetry

# Initialize the logger for the module
logger = logging.getLogger("mesapi-server-logger")

# Initialize telemetry instance (will be set up in the lifespan context)
telemetry: Optional[MESAPIServerTelemetry] = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage application startup and shutdown lifecycle.
    
    Initialize the OpenTelemetry integration using environment variables 
    and ensure proper resource cleanup upon application shutdown.

    Args:
        app (FastAPI): FastAPI application instance.

    Yields:
        None: Control back to the FastAPI framework during app execution.

    Raises:
        TypeError: If port environment variable cannot be cast to an integer.
    """

    global telemetry
    
    # Startup
    telemetry = MESAPIServerTelemetry(
        endpoint_host=os.getenv("OTEL_HOST"),
        endpoint_port=int(os.getenv("OTEL_PORT")),
        service_name=os.getenv("OTEL_SERVICE_NAME"),
        deployment_environment=os.getenv("OTEL_DEPLOYMENT_ENVIRONMENT")
    )
    telemetry.setup()
    logger.info("API started.")
    
    yield
    
    # Shutdown
    logger.info("Shutdown invoked.")
    if telemetry:
        telemetry.shutdown()


app = FastAPI(title="MES Simulation API", lifespan=lifespan)

# Database configuration using environment variables
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
host = os.getenv("DB_HOST")
port = int(os.getenv("DB_PORT"))
dbname = os.getenv("DB_NAME")

DB_URL = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Generator[Session, None, None]:
    """
    Provide a transactional scope for database operations.

    Create a new SQLAlchemy session for a single request and ensure
    the connection is closed after the request is processed.

    Yields:
        Generator[Session, None, None]: A SQLAlchemy database session object.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health_check() -> dict[str, str]:
    """
    Verify the operational status of the API server.

    Returns:
        dict[str, str]: Dictionary with 'status' key set to 'ok' and a 'message'
        field containing a confirmation that the MES Simulation API is running.
    """
    logger.info("GET /health called.")
    return {"status": "ok", "message": "MES Simulation API is running."}


@app.get("/active-order-id")
def get_active_order(machine: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Retrieve the currently active order ID for a specific machine.

    Query the database for an order assigned to the given machine ID
    where the current time falls between the order's start and end timestamps.
    
    Args:
        machine (str): Identifier of the machine.
        db (Session): Database session provided by dependency injection.

    Returns:
        dict[str, Any]: Dictionary containing the machine ID and active order ID.

    Raises:
        HTTPException: 500 status code if a database error occurs.
        HTTPException: 404 status code if no active order is found for the machine
    """

    query = text("""
        SELECT id 
        FROM orders 
        WHERE machine_id = :line 
        AND NOW() BETWEEN start_date AND end_date
    """)
    
    try:
        result = db.execute(query, {"line": machine}).fetchone()
    except Exception as e:
        logger.error(f"GET /active-order-id called for machine: {machine}. Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Database connection error")

    if not result:
        logger.warning(f"GET /active-order-id called for machine: {machine}. No active order found.")
        raise HTTPException(
            status_code=404, 
            detail=f"No active order found for machine: {machine}"
        )

    order_id = result[0]
    logger.info(f"GET /active-order-id called for machine: {machine}. Active order ID: {order_id}.")
    
    return {
        "machine": machine,
        "active_order_id": order_id
    }