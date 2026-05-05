"""Database population script for MES system.

Generates and populates articles, orders, and progress statements following the algorithm
defined in the specification file.
"""

import random
from datetime import timedelta
from typing import List, Tuple, Dict
from database_connection import DatabaseConnection
from config import *

def create_schema(db: DatabaseConnection):
    """Create database schema if tables don't exist."""
    print("\n[PHASE 0] Creating schema...")
    
    # Drop existing tables if they exist (for idempotency)
    drop_statements = [
        "DROP TABLE IF EXISTS order_progress_statements CASCADE;",
        "DROP TABLE IF EXISTS orders CASCADE;",
        "DROP TABLE IF EXISTS articles CASCADE;",
    ]
    
    for stmt in drop_statements:
        db.execute(stmt)
    db.commit()
    
    # Create articles table
    db.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id VARCHAR(10) PRIMARY KEY,
            description VARCHAR(255) NOT NULL
        );
    """)
    
    # Create orders table
    db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            article_id VARCHAR(10) NOT NULL,
            machine_id INTEGER NOT NULL,
            target_qty INTEGER NOT NULL,
            start_date TIMESTAMP,
            end_date TIMESTAMP,
            FOREIGN KEY (article_id) REFERENCES articles(id),
            CHECK (start_date <= end_date OR (start_date IS NULL AND end_date IS NULL))
        );
    """)
    
    # Create order_progress_statements table
    db.execute("""
        CREATE TABLE IF NOT EXISTS order_progress_statements (
            order_id INTEGER NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            produced_qty INTEGER NOT NULL,
            discarded_qty INTEGER NOT NULL,
            PRIMARY KEY (order_id, timestamp),
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
            CHECK (produced_qty >= 0 AND discarded_qty >= 0)
        );
    """)
    
    # Create indexes for performance
    db.execute("CREATE INDEX IF NOT EXISTS idx_orders_machine ON orders(machine_id);")
    db.execute("CREATE INDEX IF NOT EXISTS idx_orders_article ON orders(article_id);")
    db.execute("CREATE INDEX IF NOT EXISTS idx_progress_order ON order_progress_statements(order_id);")
    db.execute("CREATE INDEX IF NOT EXISTS idx_progress_timestamp ON order_progress_statements(timestamp);")
    
    db.commit()
    print("✓ Schema created successfully")


def phase_1_generate_articles(db: DatabaseConnection) -> List[Tuple[str, str]]:
    """PHASE 1: Generate and insert articles."""
    print("\n[PHASE 1] Generating articles...")
    
    articles_data = []
    for i, article_id in enumerate(ARTICLES):
        articles_data.append((article_id, ARTICLE_DESCRIPTIONS[i]))
    
    query = "INSERT INTO articles (id, description) VALUES (%s, %s);"
    db.executemany(query, articles_data)
    db.commit()
    
    print(f"✓ Inserted {len(articles_data)} articles")
    return articles_data


def phase_2_generate_orders(db: DatabaseConnection) -> Dict[int, Dict]:
    """PHASE 2: Generate and insert orders with round-robin machine assignment."""
    print("\n[PHASE 2] Generating orders...")
    
    random.seed(RANDOM_SEED)
    orders_data = []
    orders_map = {}  # order_id -> {machine_id, target_qty, article_id}
    
    for i in range(NUM_ARTICLES * ORDERS_PER_ARTICLE):
        # Sequenziale article assignment
        article_idx = (i // ORDERS_PER_ARTICLE) % NUM_ARTICLES
        article_id = ARTICLES[article_idx]
        
        # Round-robin machine assignment
        machine_id = MACHINES[i % len(MACHINES)]
        
        # Random target quantity (multiple of 500 between 9000-15000)
        num_steps = (TARGET_QTY_MAX - TARGET_QTY_MIN) // TARGET_QTY_STEP + 1
        target_qty = TARGET_QTY_MIN + random.randint(0, num_steps - 1) * TARGET_QTY_STEP
        
        orders_data.append((article_id, machine_id, target_qty, None, None))
    
    query = "INSERT INTO orders (article_id, machine_id, target_qty, start_date, end_date) VALUES (%s, %s, %s, %s, %s) RETURNING id;"
    
    # Insert in batches to get back IDs
    batch_size = 1000
    order_id = 1
    for batch_start in range(0, len(orders_data), batch_size):
        batch = orders_data[batch_start:batch_start + batch_size]
        for order_data in batch:
            db.execute(
                query,
                order_data
            )
            orders_map[order_id] = {
                'article_id': order_data[0],
                'machine_id': order_data[1],
                'target_qty': order_data[2],
            }
            order_id += 1
    
    db.commit()
    print(f"✓ Inserted {len(orders_data)} orders")
    return orders_map


def phase_3_generate_progress_statements(db: DatabaseConnection, orders_map: Dict[int, Dict]) -> List[Tuple]:
    """PHASE 3: Generate progress statements for all orders.
    
    Generates progress statements sequentially for each machine,
    accumulating them in a global list for later ordering and insertion.
    """
    print("\n[PHASE 3] Generating progress statements...")
    
    random.seed(RANDOM_SEED)
    all_statements = []  # Will contain (order_id, timestamp, produced_qty, discarded_qty)
    
    # Group orders by machine
    orders_by_machine = {}
    for order_id, order_data in orders_map.items():
        machine_id = order_data['machine_id']
        if machine_id not in orders_by_machine:
            orders_by_machine[machine_id] = []
        orders_by_machine[machine_id].append(order_id)
    
    # Sort orders within each machine to maintain sequence
    for machine_id in orders_by_machine:
        orders_by_machine[machine_id].sort()
    
    # Generate statements for each machine
    for machine_id in MACHINES:
        if machine_id not in orders_by_machine:
            continue
        
        # Machine time offset
        offset_minutes = MACHINE_TIME_OFFSETS[machine_id]
        current_time = START_DATE + timedelta(minutes=offset_minutes)
        
        machine_orders = orders_by_machine[machine_id]
        
        for order_id in machine_orders:
            target_qty = orders_map[order_id]['target_qty']
            quantità_netta = 0
            
            # Generate statements for this order until target is reached
            while quantità_netta < target_qty:
                # Increment time by 10-20 minutes
                current_time += timedelta(minutes=random.uniform(INTERVAL_MIN, INTERVAL_MAX))
                
                # Generate produced and discarded quantities
                produced_qty = random.randint(PRODUCED_QTY_MIN, PRODUCED_QTY_MAX)
                scrap_pct = random.uniform(SCRAP_PCT_MIN, SCRAP_PCT_MAX)
                discarded_qty = round(produced_qty * scrap_pct / 100)
                
                # Add statement
                all_statements.append((order_id, current_time, produced_qty, discarded_qty))
                
                # Update running total
                quantità_netta += produced_qty - discarded_qty
    
    print(f"✓ Generated {len(all_statements)} progress statements")
    return all_statements


def phase_4_insert_progress_statements(db: DatabaseConnection, all_statements: List[Tuple]):
    """PHASE 4: Sort globally by timestamp and insert into database."""
    print("\n[PHASE 4] Sorting and inserting progress statements...")
    
    # Sort by timestamp
    all_statements.sort(key=lambda x: x[1])
    
    query = "INSERT INTO order_progress_statements (order_id, timestamp, produced_qty, discarded_qty) VALUES (%s, %s, %s, %s);"
    
    batch_size = 10000
    for batch_start in range(0, len(all_statements), batch_size):
        batch = all_statements[batch_start:batch_start + batch_size]
        db.executemany(query, batch)
        db.commit()
        print(f"  Inserted {min(batch_size, len(all_statements) - batch_start)} statements")
    
    print(f"✓ All {len(all_statements)} progress statements inserted")


def phase_5_calculate_dates(db: DatabaseConnection, orders_map: Dict[int, Dict]):
    """PHASE 5: Calculate and update start_date and end_date retroactively."""
    print("\n[PHASE 5] Calculating start_date and end_date...")
    
    # Get first and last timestamp for each order
    db.execute("""
        SELECT order_id, 
               MIN(timestamp) as start_date,
               MAX(timestamp) as end_date
        FROM order_progress_statements
        GROUP BY order_id;
    """)
    
    results = db.cursor.fetchall()
    update_data = [(start_date, end_date, order_id) for order_id, start_date, end_date in results]
    
    query = "UPDATE orders SET start_date = %s, end_date = %s WHERE id = %s;"
    db.executemany(query, update_data)
    db.commit()
    
    print(f"✓ Updated {len(update_data)} orders with start_date and end_date")


def main() -> None:
    print("=" * 60)
    print("MES DATABASE POPULATION SCRIPT")
    print("=" * 60)
    
    db = DatabaseConnection()
    try:
        db.connect()
        create_schema(db)
        
        # Phase 1: Articles
        phase_1_generate_articles(db)
        
        # Phase 2: Orders
        orders_map = phase_2_generate_orders(db)
        
        # Phase 3-5: Progress statements
        all_statements = phase_3_generate_progress_statements(db, orders_map)
        phase_4_insert_progress_statements(db, all_statements)
        phase_5_calculate_dates(db, orders_map)
        
        print("\n" + "=" * 60)
        print("✓ Database population completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Error during execution: {e}")
        if db.conn:
            db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
