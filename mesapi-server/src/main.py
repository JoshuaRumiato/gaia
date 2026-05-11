import os
import logging
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from mesapi_server_telemetry import MESAPIServerTelemetry

# Initialize the logger for the module
logger = logging.getLogger("mesapi-server-logger")

# Initialize telemetry instance (will be set up in the lifespan context)
telemetry: Optional[MESAPIServerTelemetry] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan: startup and shutdown.
    
    Handles the initialization and teardown of telemetry on app startup/shutdown.
    
    Yields:
        None
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

# Configurazione Database tramite variabili d'ambiente
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
host = os.getenv("DB_HOST")
port = int(os.getenv("DB_PORT"))
dbname = os.getenv("DB_NAME")

DB_URL = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Generator per la sessione del database.
    
    Yields:
        Session: Connessione al database SQLAlchemy.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/health")
def health_check():
    """Endpoint di health check per verificare che il server sia attivo."""
    logger.info("GET /health called.")
    return {"status": "ok", "message": "MES Simulation API is running."}


@app.get("/active-order-id")
def get_active_order(machine: str, db: Session = Depends(get_db)):
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