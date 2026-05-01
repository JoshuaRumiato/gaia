import os
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

app = FastAPI(title="MES Simulation API")

# Configurazione Database tramite variabili d'ambiente
DB_URL = os.getenv("DATABASE_URL", "postgresql://user:password@db:5432/mes_db")
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

@app.get("/active-order-id")
def get_active_order(production_line: str, db: Session = Depends(get_db)):
    """Recupera l'ID dell'ordine di produzione corrente per una specifica linea.

    Esegue una query sul database PostgreSQL per trovare l'ordine con stato 'IN_PROGRESS'
    associato alla linea di produzione indicata.

    Args:
        production_line (str): Identificativo della linea di produzione (es. 'LINE_A').
        db (Session): Istanza della sessione DB iniettata da FastAPI.

    Returns:
        dict: Un dizionario contenente l'ID dell'ordine attivo.
            Esempio: {"production_line": "LINE_A", "active_order_id": 12345}

    Raises:
        HTTPException: 404 se non viene trovato alcun ordine attivo per la linea.
        HTTPException: 500 in caso di errori di connessione al database.
    """
    query = text("""
        SELECT order_id 
        FROM production_orders 
        WHERE production_line = :line 
        AND status = 'IN_PROGRESS' 
        LIMIT 1
    """)
    
    try:
        result = db.execute(query, {"line": production_line}).fetchone()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Database connection error")

    if not result:
        raise HTTPException(
            status_code=404, 
            detail=f"No active order found for line: {production_line}"
        )

    return {
        "production_line": production_line,
        "active_order_id": result[0]
    }