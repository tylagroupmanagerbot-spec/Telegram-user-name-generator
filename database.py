# ============================================================
# PERSONAL TELEGRAM USERNAME TOOL
# File: database.py
# ============================================================

import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATABASE_FILE = BASE_DIR / "username_tool.db"


def connection():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    conn = connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def save_candidate(username, status):
    conn = connection()

    conn.execute("""
        INSERT INTO candidates(username, status)
        VALUES (?, ?)
        ON CONFLICT(username)
        DO UPDATE SET status = excluded.status
    """, (username, status))

    conn.commit()
    conn.close()


def get_candidates(limit=20):
    conn = connection()

    rows = conn.execute("""
        SELECT username, status, created_at
        FROM candidates
        ORDER BY id DESC
        LIMIT ?
    """, (limit,)).fetchall()

    conn.close()
    return rows
