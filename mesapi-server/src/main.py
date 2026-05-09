import os
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

app = FastAPI(title="MES Simulation API")

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
    return {"status": "ok", "message": "MES Simulation API is running."}


@app.get("/active-order-id")
def get_active_order(machine: str, db: Session = Depends(get_db)):
    """Recupera l'ID dell'ordine di produzione corrente per una specifica linea.

    Esegue una query sul database PostgreSQL per trovare l'ordine con stato 'IN_PROGRESS'
    associato alla linea di produzione indicata.

    Args:
        machine (str): Identificativo della macchina di produzione (es. 'LINE_A').
        db (Session): Istanza della sessione DB iniettata da FastAPI.

    Returns:
        dict: Un dizionario contenente l'ID dell'ordine attivo.
            Esempio: {"machine": "LINE_A", "active_order_id": 12345}

    Raises:
        HTTPException: 404 se non viene trovato alcun ordine attivo per la linea.
        HTTPException: 500 in caso di errori di connessione al database.
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
        raise HTTPException(status_code=500, detail=f"Database connection error: {e}")

    if not result:
        raise HTTPException(
            status_code=404, 
            detail=f"No active order found for machine: {machine}"
        )

    return {
        "machine": machine,
        "active_order_id": result[0]
    }