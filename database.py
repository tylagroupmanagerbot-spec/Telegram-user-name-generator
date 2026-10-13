# ============================================================
# TELEGRAM USERNAME TOOL
# File: database.py
# Local SQLite storage
# ============================================================

import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATABASE_FILE = BASE_DIR / "username_tool.db"


def get_connection():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def set_setting(key, value):
    conn = get_connection()

    conn.execute("""
        INSERT INTO settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key)
        DO UPDATE SET value = excluded.value
    """, (key, str(value)))

    conn.commit()
    conn.close()


def get_setting(key, default=None):
    conn = get_connection()

    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        (key,)
    ).fetchone()

    conn.close()

    if row is None:
        return default

    return row["value"]


def save_candidate(username, status):
    conn = get_connection()

    conn.execute("""
        INSERT OR REPLACE INTO candidates (username, status)
        VALUES (?, ?)
    """, (username, status))

    conn.commit()
    conn.close()


def get_candidates():
    conn = get_connection()

    rows = conn.execute("""
        SELECT username, status, created_at
        FROM candidates
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return rows
