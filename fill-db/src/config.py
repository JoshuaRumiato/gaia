"""Configuration module for database connection and script parameters."""

import os
from datetime import datetime

# Database configuration
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# Script parameters
RANDOM_SEED = 42
START_DATE = datetime(2026, 5, 1, 0, 0, 0)

# Machine configuration
MACHINES = [1123, 9987, 5563, 3311, 7742]
MACHINE_TIME_OFFSETS = {
    1123: 0,      # 0 minutes
    9987: 30,     # 30 minutes
    5563: 60,     # 60 minutes
    3311: 90,     # 90 minutes
    7742: 120,    # 120 minutes
}

# Article configuration
NUM_ARTICLES = 20
ARTICLES = [f"MOB_{i:03d}" for i in range(1, NUM_ARTICLES + 1)]

ARTICLE_DESCRIPTIONS = [
    "Tavolo da cucina in legno massello",
    "Sedia ergonomica con schienale regolabile",
    "Libreria componibile a 5 ripiani",
    "Scrivania per ufficio con cassettiera",
    "Poltrona in tessuto ignifugo",
    "Letto matrimoniale con testiera",
    "Armadio a 3 ante con specchio",
    "Scaffale industriale in metallo",
    "Banco da laboratorio resistente",
    "Tavolo riunioni per 8 persone",
    "Divano 3 posti in pelle sintetica",
    "Comodino con cassetti",
    "Ante scorrevoli per armadio",
    "Mensola da muro in acciaio",
    "Sedute modulari per sala d'attesa",
    "Tavolo pieghevole da evento",
    "Cassettiera 4 cassetti cromata",
    "Porte in legno lamellare",
    "Sgabelli da bar con poggiapiedi",
    "Partizione divisoria in alluminio",
]

# Order configuration
ORDERS_PER_ARTICLE = 100
TARGET_QTY_MIN = 9000
TARGET_QTY_MAX = 15000
TARGET_QTY_STEP = 500

# Progress statement configuration
INTERVAL_MIN = 10  # minutes
INTERVAL_MAX = 20  # minutes
PRODUCED_QTY_MIN = 90
PRODUCED_QTY_MAX = 150
SCRAP_PCT_MIN = 0.0
SCRAP_PCT_MAX = 1.5
